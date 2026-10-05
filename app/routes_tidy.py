"""Tidying the issue tree and the list of changes (sub-plan E, D5, Q28 to Q32)."""

from datetime import datetime, timezone
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import graph, graph_tidy, tidy
from app.members import Member, require_member, require_same_origin
from app.pages import page

router = APIRouter()


def require_tidier(member: Member = Depends(require_member)) -> Member:
    if not tidy.can_tidy(member):
        raise HTTPException(404)
    return member


def _back(key: str, **query: str) -> RedirectResponse:
    address = f"/issues/{quote(key, safe='')}"
    if query:  # an answer lands on the tidying section, where it is written
        address += "?" + urlencode(query) + "#tidy"
    return RedirectResponse(address, status_code=303)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/issues/{key}/rename", dependencies=[Depends(require_same_origin)])
def rename(key: str, new_name: str = Form(""), member: Member = Depends(require_tidier)) -> Response:
    outcome, shown = graph_tidy.rename_issue(member.key, key, new_name, _now())
    if outcome == "gone":
        return RedirectResponse("/issues", status_code=303)
    if outcome == "renamed":
        return _back(shown, done="renamed")
    return _back(shown) if outcome == "same" else _back(key, problem=outcome)


@router.post("/issues/{key}/move", dependencies=[Depends(require_same_origin)])
def move(key: str, parent: str = Form(""), member: Member = Depends(require_tidier)) -> Response:
    outcome = graph_tidy.move_issue(member.key, key, parent or None, _now())
    if outcome == "gone":
        return RedirectResponse("/issues", status_code=303)
    if outcome == "moved":
        return _back(key, done="moved")
    return _back(key) if outcome == "same" else _back(key, problem=outcome)


@router.get("/issues/{key}/merge")
def merge_question(request: Request, key: str, other: str = "", member: Member = Depends(require_tidier)) -> Response:
    kept = graph.issue_header(key)
    if kept is None:
        return RedirectResponse("/issues", status_code=303)
    merged = graph.issue_header(other) if other and other != key else None
    if merged is None:
        return _back(key, problem="choose_other")
    return page(request, "merge_confirm.html", {"kept": kept, "merged": merged})


@router.post("/issues/{key}/merge", dependencies=[Depends(require_same_origin)])
def merge(key: str, other: str = Form(""), member: Member = Depends(require_tidier)) -> Response:
    outcome, change_id = graph_tidy.merge_issues(member.key, key, other, _now())
    if outcome == "merged":
        return _back(key, done="merged", change=change_id)
    if graph.issue_header(key) is None:
        return RedirectResponse("/issues", status_code=303)
    return _back(key, problem="choose_other")


@router.get("/changes")
def changes(request: Request, member: Member = Depends(require_member)) -> Response:
    return page(request, "changes.html", {"changes": [tidy.sentence(row) for row in graph_tidy.list_changes()]})
