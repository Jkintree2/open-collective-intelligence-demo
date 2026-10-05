"""Tidying the issue tree: who may, what the pages say, and how a change reads (sub-plan E, D5)."""

import json

from fastapi import Request

from app.text import make_key

# Client facing copy, word for word from docs/planning/04_interface.md.
DONE = {"renamed": "Renamed.", "moved": "Moved.", "merged": "Merged. Everything about {other} is now here."}
PROBLEMS = {
    "taken": "Another issue already has that name. To join the two, use Merge.",
    "short": "That name is too short.",
    "self": "An issue cannot be part of itself.",
    "parent_is_sub": "That issue is part of another issue, so nothing can be part of it.",
    "has_children": "Other issues are part of this one, so it stays at the top level.",
    "choose_other": "Choose a different issue to merge.",
}


def can_tidy(member) -> bool:
    """D5: only John's account (admin) moves, renames and merges. If John lets every member tidy,
    this is the one line to change."""
    return bool(member is not None and member.admin)


def sentence(row: dict) -> str:
    details = json.loads(row["details"] or "{}")
    when = row["created_at"].strftime("%-d %B %Y, %H:%M")
    if row["kind"] == "rename":
        what = f"renamed {details['from_name']} to {details['to_name']}"
    elif row["kind"] == "merge":
        what = f"merged {details['merged_name']} into {details['kept_name']}"
    elif details.get("to_parent_name"):
        what = f"moved {details['issue_name']} under {details['to_parent_name']}"
    else:
        what = f"made {details['issue_name']} a top level issue"
    return f"{when} · {row['by']} {what}"


def tidied_names(changes: list[dict]) -> dict[str, str]:
    """Old issue key -> the issue's name now, from graph_tidy.renames_and_merges() (oldest first):
    every rename and every merge, followed to its end. A seed reload reads an old seed name through this."""
    step: dict[str, tuple[str, str]] = {}
    for change in changes:  # oldest first, so a later change of the same key wins
        details = json.loads(change["details"] or "{}")
        if change["kind"] == "rename":
            step.pop(details["to_key"], None)  # the key is live again: an older step away from it is stale
            step[details["from_key"]] = (details["to_key"], details["to_name"])
        elif change["kind"] == "merge":
            step.pop(details["kept_key"], None)
            step[details["merged_key"]] = (details["kept_key"], details["kept_name"])
    names = {}
    for old in step:
        key, seen = old, set()
        while key in step and key not in seen:
            seen.add(key)
            key, name = step[key]
        names[old] = name
    return names


def retidy(name: str | None, names: dict[str, str]) -> str | None:
    """A seed name as the issue it is now, after any rename or merge."""
    key = make_key(name or "")
    return names.get(key, name) if key else name


def page_context(request: Request, issue: dict) -> dict | None:
    """The tidying controls for the issue page, or None for anyone who may not tidy."""
    from app import graph_tidy
    from app.members import current_member
    if not can_tidy(current_member(request)):
        return None
    notice = DONE.get(request.query_params.get("done", ""))
    if notice and "{other}" in notice:
        change = graph_tidy.change(request.query_params.get("change", ""))
        details = json.loads(change["details"]) if change and change["kind"] == "merge" else None
        notice = notice.format(other=details["merged_name"]) if details else None
    return {**graph_tidy.tidy_choices(issue["key"]), "notice": notice,
            "problem": PROBLEMS.get(request.query_params.get("problem", ""))}
