"""GitHub issue 55 (John, 30 October 2026): a page for each solution (/solutions/<key>) and each piece of
evidence (/evidence/<key>), each with a Write link at the top, as an issue page has. Reached from the chips
under posts, the names on issue pages, search on the Issues page, My statements and the sources under an
answer. An unknown key goes to the Issues page, as an unknown issue does."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response

from app import config, confidence, graph_evidence, graph_item_pages
from app.members import member_key, require_access
from app.pages import page

router = APIRouter()
FEED_LIMIT = 60
# John's display verbs (CLAUDE.md): "supports issue of", "refutes solution of", "supports evidence of".
VERBS = {"SUPPORTS": "Supports", "REFUTES": "Refutes"}


def solution_href(key: str) -> str:
    return f"/solutions/{quote(key, safe='')}"


def evidence_href(key: str) -> str:
    return f"/evidence/{quote(key, safe='')}"


def _issue_crumbs(key: str, name: str, parent_key: str | None, parent_name: str | None) -> list[dict]:
    crumbs = [{"name": "Issues", "href": "/issues"}]
    if parent_key:
        crumbs.append({"name": parent_name, "href": f"/issues/{quote(parent_key, safe='')}"})
    return crumbs + [{"name": name, "href": f"/issues/{quote(key, safe='')}"}]


def solution_crumbs(solution: dict) -> list[dict]:
    """Back to the first issue that took the solution up; the page lists every one."""
    first = solution["issues"][0] if solution["issues"] else None
    if first is None:
        return [{"name": "Issues", "href": "/issues"}]
    return _issue_crumbs(first["key"], first["name"], first["parent_key"], first["parent_name"])


def evidence_crumbs(evidence: dict) -> list[dict]:
    """Back to the first thing the evidence speaks to: an issue, a solution under its issue, or other evidence."""
    target = evidence["targets"][0] if evidence["targets"] else None
    if target is None:
        return [{"name": "Issues", "href": "/issues"}]
    if target["kind"] == "issue":
        return _issue_crumbs(target["key"], target["name"], target["parent_key"], target["parent_name"])
    if target["kind"] == "solution":
        crumbs = _issue_crumbs(target["home_key"], target["home_name"], target["parent_key"], target["parent_name"]) \
            if target["home_key"] else [{"name": "Issues", "href": "/issues"}]
        return crumbs + [{"name": target["name"], "href": solution_href(target["key"])}]
    return [{"name": "Issues", "href": "/issues"}, {"name": target["name"], "href": evidence_href(target["key"])}]


def target_href(target: dict) -> str:
    if target["kind"] == "issue":
        return f"/issues/{quote(target['key'], safe='')}"
    return solution_href(target["key"]) if target["kind"] == "solution" else evidence_href(target["key"])


def _recent(**about: str) -> list[dict]:
    from app.routes_ask import recent_questions  # the router's own reader; routers load in name order
    return recent_questions(None, **about) if config.get_settings().ask_enabled else []


def _posts(request: Request, posts: list[dict]) -> list[dict]:
    from app.main import _decorate_posts
    return _decorate_posts(posts, me=member_key(request))


def about_solution(key: str | None) -> dict | None:
    """The write page's summary for a solution (/?solution=<key>): its issues, its counts and the three
    positions, its evidence. `issue_name` and `issue_key` are its first issue's, which the card starts from;
    `issue_keys` are all of them, which the card holds too (John, 31 October 2026)."""
    solution = graph_item_pages.solution(key) if key else None
    if solution is None:
        return None
    first = solution["issues"][0] if solution["issues"] else {"key": "", "name": ""}
    return {"kind": "solution", "solution": solution, "issue_key": first["key"], "issue_name": first["name"],
            "issue_keys": [item["key"] for item in solution["issues"]], "href": solution_href(key)}


def about_evidence(key: str | None) -> dict | None:
    """The write page's summary for a piece of evidence (/?evidence=<key>): its source and what it supports or
    refutes. The card starts from the issue the first of those belongs to, if any."""
    evidence = graph_item_pages.evidence(key) if key else None
    if evidence is None:
        return None
    for target in evidence["targets"]:
        target["verb"] = VERBS[target["stance"]].lower()
    home = next(((t["key"], t["name"]) if t["kind"] == "issue" else (t["home_key"], t["home_name"])
                 for t in evidence["targets"] if t["kind"] == "issue" or t["home_key"]), ("", ""))
    return {"kind": "evidence", "evidence": evidence, "issue_key": home[0], "issue_name": home[1],
            "href": evidence_href(key)}


@router.get("/solutions/{key}", dependencies=[Depends(require_access)])
def solution_page(request: Request, key: str) -> Response:
    solution = graph_item_pages.solution(key, me=member_key(request))
    if solution is None:
        return RedirectResponse("/issues", status_code=303)
    settings = config.get_settings()
    if settings.evidence_check_enabled and solution["issues"]:
        # Q39 for the solution's first issue holds every evidence edge into the solution, so its lines read
        # as they do under the solution on that issue page.
        home = solution["issues"][0]["key"]
        confidence.annotate(home, [], [solution], graph_evidence.issue_confidence(home))
    return page(request, "solution.html", {
        "solution": solution, "crumbs": solution_crumbs(solution),
        "posts": _posts(request, graph_item_pages.solution_posts(key, FEED_LIMIT)),
        "recent_questions": _recent(solution_key=key)})


@router.get("/evidence/{key}", dependencies=[Depends(require_access)])
def evidence_page(request: Request, key: str) -> Response:
    evidence = graph_item_pages.evidence(key)
    if evidence is None:
        return RedirectResponse("/issues", status_code=303)
    settings = config.get_settings()
    for target in evidence["targets"]:
        target["href"] = target_href(target)
        target["verb"] = VERBS[target["stance"]]
    own_source = source_note = None
    if settings.evidence_check_enabled:
        own_source = confidence.own_source(evidence)
        confidence.mark_targets(key, evidence["targets"], graph_item_pages.evidence_confidence(key))
        # With no link, the line the issue page gives such evidence, also only with the switch (a writer's own
        # words get theirs in the page whatever the switch says, as the source link does).
        if not evidence["url"] and not evidence["answers_key"]:
            source_note = confidence.PERSONAL if evidence["personal"] else confidence.NO_SOURCE
    return page(request, "evidence.html", {
        "evidence": evidence, "crumbs": evidence_crumbs(evidence), "own_source": own_source,
        "source_note": source_note,
        "posts": _posts(request, graph_item_pages.evidence_posts(key, FEED_LIMIT)),
        "recent_questions": _recent(evidence_key=key)})
