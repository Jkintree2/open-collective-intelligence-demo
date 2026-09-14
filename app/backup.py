"""Version 1 portable record format and validation, with no database access.

Nodes use (label, identity), where identity is Post.id or the other labels' key.
Relationships are a list, not a set: identical per-post facts remain distinct.
Properties retain their names and values; temporal tags preserve nanoseconds.
"""

import base64
import json
import math
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from neo4j.time import Date, DateTime, Duration, Time

FORMAT = "oci-record"
VERSION = 1
LABEL_KEYS = {"Person": "key", "Issue": "key", "Solution": "key", "Evidence": "key", "Post": "id"}
DIRECTIONS = {
    "POSTED": ("Person", {"Post"}), "CLAIM": ("Person", {"Issue"}),
    "SUBMIT": ("Person", {"Evidence"}), "PROPOSE": ("Person", {"Solution"}),
    "HAVE_PROPOSED": ("Issue", {"Solution"}), "APPROVE": ("Person", {"Solution"}),
    "OPPOSE": ("Person", {"Solution"}), "PART_OF": ("Issue", {"Issue"}),
    "SUPPORTS": ("Evidence", {"Issue", "Solution", "Evidence"}),
    "REFUTES": ("Evidence", {"Issue", "Solution", "Evidence"}),
}
TEMPORALS = {"DateTime": DateTime, "Date": Date, "Time": Time, "Duration": Duration}


class InvalidBackup(ValueError):
    """Invalid input; messages contain no record or connection contents."""


def encode_value(value):
    if isinstance(value, datetime):
        value = DateTime.from_native(value)
    elif isinstance(value, date):
        value = Date.from_native(value)
    elif isinstance(value, time):
        value = Time.from_native(value)
    elif isinstance(value, timedelta):
        value = Duration(days=value.days, seconds=value.seconds, nanoseconds=value.microseconds * 1000)
    if type(value).__name__ in TEMPORALS and isinstance(value, tuple(TEMPORALS.values())):
        result = {"$type": type(value).__name__, "value": value.iso_format()}
        zone = getattr(getattr(value, "tzinfo", None), "zone", None)
        zone = zone or getattr(getattr(value, "tzinfo", None), "key", None)
        if zone and isinstance(value, DateTime):
            result["zone"] = zone
        return result
    if isinstance(value, (bytes, bytearray)):
        return {"$type": "Bytes", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, list):
        return [encode_value(item) for item in value]
    if type(value) in (str, bool, int, float):
        return value
    raise InvalidBackup("Unsupported property value.")


def decode_value(value):
    if type(value) in (str, bool):
        return value
    if type(value) is int and -(2**63) <= value < 2**63:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, list):
        decoded = [decode_value(item) for item in value]
        if any(isinstance(item, (list, bytes, bytearray)) for item in decoded):
            raise InvalidBackup("Nested property arrays are not supported.")
        kinds = {type(item) for item in decoded}
        if len(kinds) > 1:
            raise InvalidBackup("Property arrays must have one value type.")
        return decoded
    if isinstance(value, dict):
        if (set(value) not in ({"$type", "value"}, {"$type", "value", "zone"})
                or not isinstance(value.get("value"), str)):
            raise InvalidBackup("Malformed property tag.")
        kind = value.get("$type")
        try:
            if kind == "Bytes" and "zone" not in value:
                return bytearray(base64.b64decode(value["value"], validate=True))
            if kind not in TEMPORALS:
                raise InvalidBackup("Unknown property tag.")
            decoded = TEMPORALS[kind].from_iso_format(value["value"])
            # The driver parses a zero offset as named UTC. Keep offset-only
            # timestamps offset-only instead of inventing a zone on export.
            if kind == "DateTime" and "zone" not in value and decoded.tzinfo is not None:
                decoded = decoded.replace(tzinfo=timezone(decoded.utcoffset()))
            if "zone" in value:
                if kind != "DateTime" or decoded.tzinfo is None or not isinstance(value["zone"], str):
                    raise InvalidBackup("Malformed time zone.")
                decoded = decoded.as_timezone(ZoneInfo(value["zone"]))
            if decoded.iso_format() != value["value"]:
                raise InvalidBackup("Temporal properties must use canonical ISO values.")
            return decoded
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise InvalidBackup("Malformed temporal or byte property.") from exc
    raise InvalidBackup("Unsupported or malformed property value.")


def _fields(value, required):
    if not isinstance(value, dict) or set(value) != set(required):
        raise InvalidBackup("Malformed record fields.")


def reference(value):
    _fields(value, ("label", "identity"))
    label, identity = value["label"], value["identity"]
    if not isinstance(label, str) or label not in LABEL_KEYS:
        raise InvalidBackup("Unknown record label.")
    if not isinstance(identity, str) or not identity or "\x00" in identity:
        raise InvalidBackup("A record identity must be a nonempty string.")
    return label, identity


def properties(value):
    if not isinstance(value, dict) or any(not isinstance(k, str) or not k or "\x00" in k for k in value):
        raise InvalidBackup("Malformed properties.")
    decoded = {k: decode_value(v) for k, v in value.items()}
    for key, item in decoded.items():
        if key in {"key", "id", "name", "text", "url", "display_name", "source", "extraction_raw",
                   "model", "payload", "post_id", "last_post_id"} and not isinstance(item, str):
            raise InvalidBackup("A text property has the wrong type.")
        if key in {"seed", "anonymous"} and type(item) is not bool:
            raise InvalidBackup("A boolean property has the wrong type.")
        if key == "latency_ms" and (type(item) is not int or item < 0):
            raise InvalidBackup("A latency property has the wrong type.")
        if key == "created_at" and not isinstance(item, DateTime):
            raise InvalidBackup("A timestamp property has the wrong type.")
    return decoded


def validate_record(data):
    """Validate the entire document and return its decoded, database-ready copy."""
    _fields(data, ("format", "version", "nodes", "relationships"))
    if data["format"] != FORMAT or type(data["version"]) is not int or data["version"] != VERSION:
        raise InvalidBackup("Unsupported export format or version.")
    if not isinstance(data["nodes"], list) or not isinstance(data["relationships"], list):
        raise InvalidBackup("Records must be lists.")
    seen, nodes, relationships = set(), [], []
    for node in data["nodes"]:
        _fields(node, ("label", "identity", "properties"))
        ref = reference({k: node[k] for k in ("label", "identity")})
        if ref in seen:
            raise InvalidBackup("Duplicate record identity.")
        seen.add(ref)
        props = properties(node["properties"])
        if props.get(LABEL_KEYS[ref[0]]) != ref[1]:
            raise InvalidBackup("Identity does not match its stored property.")
        nodes.append({**node, "properties": props})
    for rel in data["relationships"]:
        _fields(rel, ("type", "source", "target", "properties"))
        source, target = reference(rel["source"]), reference(rel["target"])
        if source not in seen or target not in seen:
            raise InvalidBackup("A connection refers to a missing record.")
        kind = rel["type"]
        if not isinstance(kind, str) or kind not in DIRECTIONS:
            raise InvalidBackup("Unknown connection type.")
        allowed_source, allowed_targets = DIRECTIONS[kind]
        if source[0] != allowed_source or target[0] not in allowed_targets:
            raise InvalidBackup("Invalid connection direction.")
        relationships.append({**rel, "properties": properties(rel["properties"])})
    return {**data, "nodes": nodes, "relationships": relationships}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidBackup("Duplicate JSON property.")
        result[key] = value
    return result


def read_record(path):
    """Reject invalid JSON and duplicate object keys before any driver is opened."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        validate_record(data)
        return data
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise InvalidBackup("The file is not a valid shared record export.") from exc
