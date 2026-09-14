"""Backup fidelity and guard checks on an in-memory transaction, never Neo4j."""

from copy import deepcopy
import json
import re
from types import SimpleNamespace

import pytest
from neo4j.time import DateTime, Date, Time, Duration
from app import graph
from app.backup import InvalidBackup, encode_value, decode_value, validate_record
from app.graph_backup import NonemptyRecord


class Result(list):
    def single(self):
        return self[0] if self else None

    def consume(self):
        return None


class Memory:
    def __init__(self):
        self.nodes, self.relationships, self.queries = {}, [], []
        self.transactions = 0
        self.fail_after = None

    def session(self, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute_write(self, work):
        self.transactions += 1
        before = deepcopy((self.nodes, self.relationships))
        try:
            return work(self)
        except Exception:
            self.nodes, self.relationships = before
            raise

    def execute_read(self, work):
        return work(self)

    def run(self, query, **params):
        self.queries.append((query, params))
        if self.fail_after and len(self.queries) == self.fail_after:
            raise RuntimeError("Simulated transaction failure")
        if query == graph.COUNT_NODES:
            return Result([{"n": len(self.nodes)}])
        if query == graph.EXPORT_NODES:
            return Result([{"labels": [label], "properties": deepcopy(props)}
                           for (label, _), props in self.nodes.items()])
        if query == graph.EXPORT_RELATIONSHIPS:
            return Result([{"source_labels": [s[0]], "source_properties": self.nodes[s],
                            "target_labels": [t[0]], "target_properties": self.nodes[t],
                            "type": kind, "properties": deepcopy(props)}
                           for s, kind, t, props in self.relationships])
        from app.backup import LABEL_KEYS, DIRECTIONS
        for label, key in LABEL_KEYS.items():
            if query == graph.RESTORE_NODE.format(label=label, key=key):
                self.nodes[label, params["identity"]] = deepcopy(params["properties"])
                return Result()
        for kind, (source, targets) in DIRECTIONS.items():
            for target in targets:
                expected = graph.RESTORE_RELATIONSHIP.format(source_label=source, source_key=LABEL_KEYS[source],
                    target_label=target, target_key=LABEL_KEYS[target], type=kind)
                if query == expected:
                    self.relationships.append(((source, params["source"]), kind,
                        (target, params["target"]), deepcopy(params["properties"])))
                    return Result()
        pytest.fail("Unexpected query")


def sample():
    timestamp = {"$type": "DateTime", "value": "2026-09-09T00:12:13.123456789+00:00"}
    nodes = [
        {"label": "Person", "identity": "anon:one", "properties": {"key": "anon:one", "anonymous": True}},
        {"label": "Issue", "identity": "same", "properties": {"key": "same", "name": "Issue", "seed": True}},
        {"label": "Solution", "identity": "same", "properties": {"key": "same", "name": "Solution"}},
        {"label": "Evidence", "identity": "citation", "properties": {"key": "citation", "name": "Citation", "url": "https://example.org"}},
        {"label": "Post", "identity": "post", "properties": {"id": "post", "text": "Exact original",
            "created_at": timestamp, "payload": '{"issues": [{"key": "same"}]}',
            "extraction_raw": ' { "found" : true } ', "model": "reading-version", "latency_ms": 123,
            "source": "model", "anonymous": True, "seed": False}},
    ]
    refs = {n["label"]: {k: n[k] for k in ("label", "identity")} for n in nodes}
    from app.backup import DIRECTIONS
    rels = []
    for kind, (source, targets) in DIRECTIONS.items():
        for target in sorted(targets):
            props = {"created_at": timestamp, "post_id": "deleted-post", "last_post_id": "latest"}
            rels.append({"type": kind, "source": refs[source], "target": refs[target], "properties": props})
    rels.append(deepcopy(next(r for r in rels if r["type"] == "CLAIM")))
    return {"format": "oci-record", "version": 1, "nodes": nodes, "relationships": rels}


def canonical(data):
    data = deepcopy(data)
    data["nodes"].sort(key=lambda n: (n["label"], n["identity"]))
    data["relationships"].sort(key=lambda r: json.dumps(r, sort_keys=True))
    return data


def test_full_round_trip_preserves_every_property_and_relationship_duplicate(monkeypatch):
    memory = Memory()
    monkeypatch.setattr(graph, "driver", lambda: memory)
    original = sample()
    assert graph.restore_record(original) == (5, len(original["relationships"]))
    assert memory.queries[0][0] == graph.COUNT_NODES and memory.transactions == 1
    exported = json.loads(json.dumps(graph.export_record()))
    assert exported == canonical(original)
    assert len([r for r in exported["relationships"] if r["type"] == "CLAIM"]) == 2


def test_nonempty_guard_precedes_first_write_and_failure_rolls_back(monkeypatch):
    memory = Memory()
    monkeypatch.setattr(graph, "driver", lambda: memory)
    memory.nodes["Person", "existing"] = {"key": "existing"}
    with pytest.raises(NonemptyRecord):
        graph.restore_record(sample())
    assert [q for q, _ in memory.queries] == [graph.COUNT_NODES]
    memory.nodes.clear()
    memory.queries.clear()
    memory.fail_after = 4
    with pytest.raises(RuntimeError):
        graph.restore_record(sample())
    assert memory.nodes == {} and memory.relationships == []


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(version=2), lambda d: d.update(version=True),
    lambda d: d["nodes"].append(deepcopy(d["nodes"][0])),
    lambda d: d["nodes"][0].update(label="Unknown"),
    lambda d: d["nodes"][0].update(identity=""),
    lambda d: d["nodes"][0]["properties"].update(key="different"),
    lambda d: d["nodes"][0]["properties"].update(anonymous="false"),
    lambda d: d["nodes"][0]["properties"].update(name={"nested": "map"}),
    lambda d: d["nodes"][0]["properties"].update(created_at="2026-01-01"),
    lambda d: d["nodes"][0]["properties"].update(extra=None),
    lambda d: d["nodes"][0]["properties"].update(extra=2**63),
    lambda d: d["nodes"][0]["properties"].update(extra=float("nan")),
    lambda d: d["nodes"][0]["properties"].update(extra=[1, "two"]),
    lambda d: d["relationships"][-1].update(type="DECIDE"),
    lambda d: d["relationships"][-1]["target"].update(identity="missing"),
    lambda d: d["relationships"][-1].update(source=d["relationships"][-1]["target"]),
    lambda d: d["relationships"][-1]["properties"].update(created_at={"$type": "DateTime", "value": "invalid"}),
])
def test_entire_export_is_validated_before_driver_access(monkeypatch, mutate):
    data = sample()
    mutate(data)
    monkeypatch.setattr(graph, "driver", lambda: pytest.fail("Invalid input reached driver"))
    with pytest.raises(InvalidBackup):
        graph.restore_record(data)


@pytest.mark.parametrize("value", [Date(2026, 9, 9), Time(1, 2, 3, 123456789),
    DateTime(2026, 9, 9, 1, 2, 3, 987654321), Duration(months=1, days=2, seconds=3, nanoseconds=4),
    bytearray(b"\x00\xff"), [1, 2, 3], ["one", "two"]])
def test_property_types_and_precision_round_trip(value):
    decoded = decode_value(json.loads(json.dumps(encode_value(value))))
    assert type(decoded) is type(value) and decoded == value


def test_cli_rejects_file_before_connection_and_never_prints_failure_details(tmp_path, monkeypatch, capsys):
    from scripts import restore
    path = tmp_path / "invalid.json"
    path.write_text('{"format": "oci-record", "format": "duplicate"}')
    monkeypatch.setattr(graph, "open_driver", lambda settings: pytest.fail("Invalid file opened driver"))
    assert restore.main([str(path)]) == 2
    path.write_text(json.dumps(sample()))
    monkeypatch.setattr(restore, "load_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(graph, "open_driver", lambda settings: (_ for _ in ()).throw(RuntimeError("PASSWORD")))
    monkeypatch.setattr(graph, "close_driver", lambda: None)
    assert restore.main([str(path)]) == 1
    captured = capsys.readouterr()
    assert "PASSWORD" not in captured.err + captured.out
