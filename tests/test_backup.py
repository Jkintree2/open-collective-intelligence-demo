"""Backup fidelity and guard checks on an in-memory transaction, never Neo4j."""

from copy import deepcopy
import json
import re
from types import SimpleNamespace

import pytest
from neo4j.time import DateTime, Date, Time, Duration
from app import graph
from app.backup import VERSION, InvalidBackup, encode_value, decode_value, validate_record
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
        {"label": "Change", "identity": "change", "properties": {"id": "change", "kind": "rename",
            "created_at": timestamp, "details": "{}"}},
    ]
    refs = {n["label"]: {k: n[k] for k in ("label", "identity")} for n in nodes}
    from app.backup import DIRECTIONS
    rels = []
    for kind, (source, targets) in DIRECTIONS.items():
        for target in sorted(targets):
            props = {"created_at": timestamp, "post_id": "deleted-post", "last_post_id": "latest"}
            rels.append({"type": kind, "source": refs[source], "target": refs[target], "properties": props})
    rels.append(deepcopy(next(r for r in rels if r["type"] == "CLAIM")))
    return {"format": "oci-record", "version": VERSION, "nodes": nodes, "relationships": rels}


def canonical(data):
    data = deepcopy(data)
    data["nodes"].sort(key=lambda n: (n["label"], n["identity"]))
    data["relationships"].sort(key=lambda r: json.dumps(r, sort_keys=True))
    return data


def test_full_round_trip_preserves_every_property_and_relationship_duplicate(monkeypatch):
    memory = Memory()
    monkeypatch.setattr(graph, "driver", lambda: memory)
    original = sample()
    assert graph.restore_record(original) == (len(original["nodes"]), len(original["relationships"]))
    assert memory.queries[0][0] == graph.COUNT_NODES and memory.transactions == 1
    exported = json.loads(json.dumps(graph.export_record()))
    assert exported == canonical(original)
    assert len([r for r in exported["relationships"] if r["type"] == "CLAIM"]) == 2


def test_change_records_round_trip():
    data = sample()
    assert {r["type"] for r in data["relationships"]} >= {"MADE", "CHANGED"}
    validate_record(data)


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
    lambda d: d.update(version=99), lambda d: d.update(version=True),
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


def test_export_leaves_out_passwords_and_links(monkeypatch):
    memory = Memory()
    memory.nodes["Person", "acct:ada"] = {"key": "acct:ada", "name": "Ada", "email": "ada@example.org",
        "password_hash": "scrypt$secret", "token_hash": "abc", "token_purpose": "email",
        "token_expires_at": DateTime(2026, 10, 6, 12, 0, 0, 0), "pending_email": "ada.new@example.org"}
    monkeypatch.setattr(graph, "driver", lambda: memory)
    exported = graph.export_record()
    person = next(n for n in exported["nodes"] if n["identity"] == "acct:ada")
    assert set(person["properties"]) == {"key", "name", "email"}
    assert exported["version"] == 2
    assert "scrypt$secret" not in json.dumps(exported) and "ada.new" not in json.dumps(exported)


@pytest.mark.parametrize("secret", ["password_hash", "token_hash", "token_purpose", "token_expires_at", "pending_email"])
def test_restore_refuses_a_file_with_password_or_link_fields(secret):
    data = sample()
    data["nodes"][0]["properties"][secret] = "anything"
    with pytest.raises(InvalidBackup):
        validate_record(data)


def test_restore_still_takes_a_version_one_copy():
    data = sample()
    data["version"] = 1
    validate_record(data)


def test_account_properties_round_trip():
    data = sample()
    data["nodes"][0]["properties"].update(email="ada@example.org", country="UK", postal_code="N1",
                                           admin=False, active=True)
    validate_record(data)
    data["nodes"][0]["properties"]["admin"] = "no"
    with pytest.raises(InvalidBackup):
        validate_record(data)


def test_a_bad_latency_is_refused():
    data = sample()
    data["nodes"][4]["properties"]["latency_ms"] = "fast"
    with pytest.raises(InvalidBackup):
        validate_record(data)


def test_phase_1_needs_no_new_copy_version():
    from app.backup import VERSION, VERSIONS
    assert (VERSION, VERSIONS) == (2, (1, 2))


def test_an_edited_time_must_be_a_timestamp():
    data = sample()
    post = next(node for node in data["nodes"] if node["label"] == "Post")
    post["properties"]["edited_at"] = post["properties"]["created_at"]
    validate_record(data)
    post["properties"]["edited_at"] = "2026-10-06"
    with pytest.raises(InvalidBackup):
        validate_record(data)


def _phase_2(data):
    timestamp = next(node for node in data["nodes"] if node["label"] == "Post")["properties"]["created_at"]
    evidence = next(node for node in data["nodes"] if node["label"] == "Evidence")
    edge = next(rel for rel in data["relationships"] if rel["type"] == "SUPPORTS")
    evidence["properties"].update(source_type="news", source_primary=False, source_published="2024-03",
                                  source_checked_at=timestamp)
    edge["properties"].update(check="refutes", check_quote="Flooding days doubled.", checked_at=timestamp)
    return evidence["properties"], edge["properties"]


def test_phase_2_readings_and_source_facts_round_trip(monkeypatch):
    data = sample()
    _phase_2(data)
    memory = Memory()
    monkeypatch.setattr(graph, "driver", lambda: memory)
    graph.restore_record(deepcopy(data))
    assert json.loads(json.dumps(graph.export_record())) == canonical(data)


@pytest.mark.parametrize("field, bad", [
    ("check", "maybe"), ("check", True), ("check_quote", 3), ("checked_at", "2026-10-20"),
    ("source_type", False), ("source_primary", "no"), ("source_published", 2024), ("source_checked_at", "today")])
def test_phase_2_values_of_the_wrong_kind_are_refused(field, bad):
    data = sample()
    node, edge = _phase_2(data)
    validate_record(data)
    (edge if field.startswith("check") else node)[field] = bad
    with pytest.raises(InvalidBackup):
        validate_record(data)


def test_earlier_email_addresses_travel_as_two_lists_of_one_length():
    data = sample()
    person = data["nodes"][0]["properties"]
    until = encode_value(DateTime(2026, 10, 21, 9, 0, 0, 0))
    person.update(previous_emails=["ada@old.example.org"], previous_emails_until=[until])
    validate_record(data)
    for addresses, untils in ((["a@example.org", "b@example.org"], [until]), ([3], [until]),
                              (["a@example.org"], ["2026-10-21"]), ("a@example.org", [until])):
        person.update(previous_emails=addresses, previous_emails_until=untils)
        with pytest.raises(InvalidBackup):
            validate_record(data)
    del person["previous_emails_until"]
    person["previous_emails"] = ["ada@old.example.org"]
    with pytest.raises(InvalidBackup):
        validate_record(data)


def test_the_revision_round_properties_restore_with_their_types():
    from app.backup import properties
    decoded = properties({"check": "partly", "check_claim": "Flooding tripled.", "check_reason": "The page says doubled.",
                          "personal": True, "post_id": "p1"})
    assert decoded["check"] == "partly" and decoded["personal"] is True
    assert properties({"source_cites": False})["source_cites"] is False
    for bad in ({"check_claim": 3}, {"check_reason": True}, {"personal": "yes"}, {"source_cites": 1}, {"check": "agrees"}):
        with pytest.raises(InvalidBackup):
            properties(bad)


# John, 28 October: a copy carries the questions people asked, which have no edges and no asker.
def question_node(**props):
    base = {"key": "veto|why the veto", "text": "Why the veto?", "issue_key": "veto", "asked": 2,
            "created_at": encode_value(DateTime(2026, 10, 28, 20, 0, 0, tzinfo=None)),
            "asked_at": encode_value(DateTime(2026, 10, 29, 9, 0, 0, tzinfo=None))}
    return {"label": "Question", "identity": "veto|why the veto", "properties": {**base, **props}}


def test_a_question_travels_in_a_copy():
    validate_record({"format": "oci-record", "version": VERSION, "nodes": [question_node()], "relationships": []})


def test_a_question_travels_with_its_answer():
    """John, 30 October: a question is kept with the answer it got, as JSON text."""
    validate_record({"format": "oci-record", "version": VERSION, "relationships": [],
                     "nodes": [question_node(id="0f" * 16, answer='{"paragraphs": [], "sources": [], "partial": null}')]})


@pytest.mark.parametrize("bad", [{"asked": 0}, {"asked": "2"}, {"issue_key": 3}, {"asked_at": "yesterday"},
                                 {"answer": 3}])
def test_a_malformed_question_is_refused(bad):
    with pytest.raises(InvalidBackup):
        validate_record({"format": "oci-record", "version": VERSION, "nodes": [question_node(**bad)], "relationships": []})


# GitHub issue 55: a question asked on a solution's or a piece of evidence's page keeps that key, with no issue.
def test_a_question_on_a_solution_or_evidence_page_round_trips(monkeypatch):
    memory = Memory()
    monkeypatch.setattr(graph, "driver", lambda: memory)
    on_solution = question_node(key="solution:carbon tax|who pays", issue_key=None, solution_key="carbon tax")
    on_evidence = question_node(key="evidence:who pays|is it new", issue_key=None, evidence_key="who pays")
    for node in (on_solution, on_evidence):
        node["identity"] = node["properties"]["key"]
        del node["properties"]["issue_key"]  # null on these, so not stored
    original = {"format": "oci-record", "version": VERSION, "nodes": [on_solution, on_evidence], "relationships": []}
    assert graph.restore_record(original) == (2, 0)
    assert memory.nodes["Question", "solution:carbon tax|who pays"]["solution_key"] == "carbon tax"
    assert memory.nodes["Question", "evidence:who pays|is it new"]["evidence_key"] == "who pays"
    assert json.loads(json.dumps(graph.export_record())) == canonical(original)


@pytest.mark.parametrize("bad", [{"solution_key": 3}, {"solution_key": True}, {"evidence_key": 7},
                                 {"evidence_key": ["who pays"]}])
def test_a_solution_or_evidence_key_of_the_wrong_type_is_refused(bad):
    with pytest.raises(InvalidBackup):
        validate_record({"format": "oci-record", "version": VERSION, "nodes": [question_node(**bad)], "relationships": []})
