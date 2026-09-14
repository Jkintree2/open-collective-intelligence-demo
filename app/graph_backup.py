"""Admin transaction orchestration. Query text is defined only in graph.py."""

import json
from neo4j.exceptions import ServiceUnavailable
from app import graph
from app.backup import FORMAT, VERSION, LABEL_KEYS, InvalidBackup, encode_value, validate_record


class NonemptyRecord(ValueError):
    """Restore is allowed only into an empty database."""


def _transaction(work, *, write=False):
    try:
        with graph.driver().session(database=graph.database()) as session:
            return (session.execute_write if write else session.execute_read)(work)
    except ServiceUnavailable as exc:
        raise graph.RecordAsleep("The record cannot be reached.") from exc


def delete_post(post_id):
    def work(tx):
        row = tx.run(graph.DELETE_POST, id=post_id).single()
        if row is None:
            return False
        tx.run(graph.DELETE_POST_ORPHANS, touched=row["touched"]).consume()
        return True
    return _transaction(work, write=True)


def _reference(labels, props):
    if len(labels) != 1 or labels[0] not in LABEL_KEYS:
        raise InvalidBackup("The record contains unsupported labels.")
    return {"label": labels[0], "identity": props.get(LABEL_KEYS[labels[0]])}


def export_record():
    def work(tx):
        nodes = [{**_reference(row["labels"], row["properties"]),
                  "properties": {k: encode_value(v) for k, v in row["properties"].items()}}
                 for row in tx.run(graph.EXPORT_NODES)]
        relationships = [{"type": row["type"],
                          "source": _reference(row["source_labels"], row["source_properties"]),
                          "target": _reference(row["target_labels"], row["target_properties"]),
                          "properties": {k: encode_value(v) for k, v in row["properties"].items()}}
                         for row in tx.run(graph.EXPORT_RELATIONSHIPS)]
        result = {"format": FORMAT, "version": VERSION, "nodes": nodes, "relationships": relationships}
        validate_record(result)
        nodes.sort(key=lambda n: (n["label"], n["identity"]))
        relationships.sort(key=lambda r: json.dumps(r, sort_keys=True))
        return result
    return _transaction(work)


def restore_record(data):
    """Validate first, then guard and restore in one atomic write transaction."""
    record = validate_record(data)

    def work(tx):
        if tx.run(graph.COUNT_NODES).single()["n"]:
            raise NonemptyRecord("Restore refused: the database is not empty.")
        for node in record["nodes"]:
            query = graph.RESTORE_NODE.format(label=node["label"], key=LABEL_KEYS[node["label"]])
            tx.run(query, identity=node["identity"], properties=node["properties"]).consume()
        for rel in record["relationships"]:
            source, target = rel["source"], rel["target"]
            query = graph.RESTORE_RELATIONSHIP.format(
                source_label=source["label"], source_key=LABEL_KEYS[source["label"]],
                target_label=target["label"], target_key=LABEL_KEYS[target["label"]], type=rel["type"])
            tx.run(query, source=source["identity"], target=target["identity"],
                   properties=rel["properties"]).consume()
        return len(record["nodes"]), len(record["relationships"])
    return _transaction(work, write=True)
