"""Inclusive issue counts and ordering."""

from typing import Any

SORTS = ("people", "recent", "evidence")


def _sort_key(sort: str):
    if sort == "recent":
        return lambda r: (r["last_activity"],)
    if sort == "evidence":
        return lambda r: (r["evidence"], r["claims"], r["last_activity"])
    return lambda r: (r["people"], r["claims"], r["last_activity"])


def group_issues(rows: list[dict[str, Any]], sort: str = "people") -> list[dict[str, Any]]:
    """Top-level rows with their children attached, ranked on inclusive counts."""
    sort = sort if sort in SORTS else "people"
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        item["own_claims"] = row["claims"]
        item["children"] = []
        by_key[row["key"]] = item
    top: list[dict[str, Any]] = []
    for item in by_key.values():
        parent = by_key.get(item["parent_key"]) if item.get("parent_key") else None
        if parent is not None and parent is not item:
            parent["children"].append(item)
        else:
            top.append(item)
    for item in top:
        if item["children"]:
            family = [item] + item["children"]
            people = set()
            evidence = set()
            for member in family:
                people.update(member.get("person_keys") or [])
                evidence.update(member.get("evidence_keys") or [])
            item["people"] = len(people)
            item["evidence"] = len(evidence)
            item["claims"] = sum(member["own_claims"] for member in family)
            item["solutions"] = sum(member["solutions"] for member in family)
            item["last_activity"] = max(member["last_activity"] for member in family)
            item["children"].sort(key=_sort_key(sort), reverse=True)
    top.sort(key=_sort_key(sort), reverse=True)
    return top
