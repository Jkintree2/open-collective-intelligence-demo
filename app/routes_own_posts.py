"""Editing and deleting one's own post (sub-plan D). The check is on the server, every time."""

import json
from dataclasses import replace
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import ValidationError

from app import extract as reading, graph, graph_own_posts
from app.extract import CardPayload, ResolvedPayload, resolve_payload
from app.members import Member, posting_identity, require_member, require_same_origin
from app.pages import page
from app.text import sentences

router = APIRouter()
# Client facing copy, word for word from docs/planning/04_interface.md.
NOT_YOURS = "You can change only your own posts."
GONE = "That post is no longer here."
CHECK_THE_FORM = "Please check the form before posting."
UPDATED = "Your post is updated."


def _write_page(request: Request, message: str, status_code: int) -> Response:
    from app import main as site
    return site._render_index(request, message=message, status_code=status_code)


def _own(request: Request, member: Member, post_id: str) -> tuple[dict | None, Response | None]:
    row = graph_own_posts.post_owner(member.key, post_id)
    if row is None:
        return None, _write_page(request, GONE, 404)
    if not row["mine"]:
        return None, _write_page(request, NOT_YOURS, 403)
    return row, None


@router.get("/posts/{post_id}/delete")
def delete_question(request: Request, post_id: str, member: Member = Depends(require_member)) -> Response:
    row, problem = _own(request, member, post_id)
    return problem or page(request, "delete_post.html", {"post": row})


@router.post("/posts/{post_id}/delete", dependencies=[Depends(require_same_origin)])
def delete(request: Request, post_id: str, member: Member = Depends(require_member)) -> Response:
    row, problem = _own(request, member, post_id)
    if problem:
        return problem
    if not graph_own_posts.delete_own_post(member.key, post_id):  # gone a moment ago, in another tab
        return _write_page(request, GONE, 404)
    return RedirectResponse("/?done=deleted", status_code=303)


def edit_card(rows: list[dict], stored_json: str | None, issues: dict[str, dict]) -> dict:
    """The card for editing a post, built from the edges the post holds now (Q7's structure query), so
    an issue renamed or merged since shows under its current name and nothing comes back. `issues`
    maps issue keys to their Q2 header (`name`, `parent_name`). The stored payload gives only each
    evidence link's address. A solution's position is the stance edge this post still holds: one a
    click has since replaced, or one the person already held before the post, shows as no position, so
    an unchanged edit never undoes a later click (Q25: a position left off the card is not withdrawn)."""
    stored = json.loads(stored_json or "{}")
    urls = {row["key"]: row.get("url") for row in stored.get("evidence", [])}
    stored_homes = {row["key"]: row.get("for_issue_key") for row in stored.get("solutions", [])}
    proposed_from = {row["to_key"]: row["from_key"] for row in rows if row["rel"] == "HAVE_PROPOSED"}

    def name_of(key: str | None) -> str | None:
        return (issues.get(key) or {}).get("name") if key else None

    claimed: dict[str, dict] = {}
    solutions: dict[str, dict] = {}
    evidence: dict[str, dict] = {}
    for row in rows:
        rel = row["rel"]
        if rel == "CLAIM":
            claimed.setdefault(row["to_key"], {"name": row["to_name"],
                                               "parent": (issues.get(row["to_key"]) or {}).get("parent_name")})
        elif rel in ("PROPOSE", "APPROVE", "OPPOSE") and row["to_label"] == "Solution":
            key = row["to_key"]
            # The issue this post linked it to; else the one its payload named, if it still exists; else its home.
            home = proposed_from.get(key) or (stored_homes.get(key) if stored_homes.get(key) in issues else None)
            item = solutions.setdefault(key, {"name": row["to_name"], "for_issue": name_of(home or row.get("home_key")),
                                              "stance": "none"})
            if rel != "PROPOSE":
                item["stance"] = rel.lower()
        elif rel == "SUBMIT":
            evidence.setdefault(row["to_key"], {"name": row["to_name"], "url": urls.get(row["to_key"]),
                                                "stance": "supports", "about": None})
        elif rel in ("SUPPORTS", "REFUTES") and row["from_label"] == "Evidence":
            item = evidence.setdefault(row["from_key"], {"name": row["from_name"], "url": urls.get(row["from_key"]),
                                                         "stance": "supports", "about": None})
            item["stance"], item["about"] = rel.lower(), row["to_name"]
    return {"issues": list(claimed.values()), "solutions": list(solutions.values()),
            "evidence": list(evidence.values())}


def current_card(post_id: str, stored_json: str | None) -> tuple[dict, set[str]]:
    """The edit card from the record as it is now, and the solutions this post itself proposes."""
    rows = graph.post_structure([post_id]).get(post_id, [])
    stored = json.loads(stored_json or "{}")
    keys = {row["to_key"] for row in rows if row["rel"] == "CLAIM"}
    keys |= {row["from_key"] for row in rows if row["rel"] == "HAVE_PROPOSED"}
    keys |= {row["home_key"] for row in rows if row.get("home_key")}
    keys |= {row["for_issue_key"] for row in stored.get("solutions", []) if row.get("for_issue_key")}
    issues = {key: header for key in keys if (header := graph.issue_header(key))}
    own = {row["to_key"] for row in rows if row["rel"] == "PROPOSE"}
    return edit_card(rows, stored_json, issues), own


def resolve_edit(data: CardPayload, own: set[str]) -> tuple[ResolvedPayload, CardPayload]:
    """resolve_payload for an edit. The post's own HAVE_PROPOSED links would make the solutions it
    proposed look like positions on solutions already listed (GitHub issue 4's rule), dropping its own
    claim and proposal; so for those solutions the record's links are left out, and they are proposed
    again under the same post id."""
    candidates = graph.candidates()
    candidates = replace(candidates, solution_issues={key: names for key, names in candidates.solution_issues.items()
                                                      if key not in own})
    incoming = data.model_copy(update={"found": True, "language_ok": True})
    return resolve_payload(incoming, candidates), reading.prepared_card(incoming, candidates)


def _save(member: Member, row: dict, post_id: str, text: str, resolved: ResolvedPayload, card: CardPayload,
          **reading_fields) -> bool:
    from app import main as site
    # Q25: an edited post keeps the name or Anonymous it was first posted with (D2's one rule).
    _, _, _, shown = posting_identity(member, bool(row["anonymous"]))
    statement = text or (". ".join(sentences(card, shown or "Anonymous")) + ".")[:site.TEXT_MAX]
    return graph_own_posts.edit_own_post(member.key, post_id, resolved, text=statement,
                                         now=datetime.now(timezone.utc), **reading_fields)


@router.get("/posts/{post_id}/edit")
def edit_page(request: Request, post_id: str, member: Member = Depends(require_member)) -> Response:
    from app import main as site
    row, problem = _own(request, member, post_id)
    if problem:
        return problem
    card, _ = current_card(post_id, row["payload"])
    editing = {"id": row["id"], "text": row["text"], "anonymous": bool(row["anonymous"]), "card": card}
    return site._render_index(request, text=row["text"], editing=editing)


@router.post("/posts/{post_id}/edit", dependencies=[Depends(require_same_origin)])
def save_plain_edit(request: Request, post_id: str, text: str = Form(""),
                    member: Member = Depends(require_member)) -> Response:
    """Save changes without JavaScript: the new text with the post's card as it is now. Never a new
    post: while editing, the write form posts here, not to /posts."""
    from app import main as site
    row, problem = _own(request, member, post_id)
    if problem:
        return problem
    card, own = current_card(post_id, row["payload"])
    if len(text) > site.TEXT_MAX:
        editing = {"id": row["id"], "text": row["text"], "anonymous": bool(row["anonymous"]), "card": card}
        return site._render_index(request, message=site.TOO_LONG, text=text, status_code=413, editing=editing)
    if not text.strip():
        return RedirectResponse(f"/posts/{quote(post_id, safe='')}/edit", status_code=303)
    resolved, prepared = resolve_edit(CardPayload.model_validate(card), own)
    if not _save(member, row, post_id, text.strip(), resolved, prepared, source="manual",
                 extraction_raw=None, model=None, latency_ms=None):
        return _write_page(request, GONE, 404)
    return RedirectResponse("/?done=edited", status_code=303)


@router.post("/api/posts/{post_id}", dependencies=[Depends(require_same_origin)])
def save_edit(request: Request, post_id: str, body: dict = Body(...),
              member: Member = Depends(require_member)) -> Response:
    from app import main as site
    try:
        data = site.PostRequest.model_validate(body)
    except ValidationError:
        return JSONResponse({"message": CHECK_THE_FORM}, status_code=422)
    error = site._text_error(data.text, allow_empty=True)
    if error is not None:
        return error
    row = graph_own_posts.post_owner(member.key, post_id)
    if row is None:
        return JSONResponse({"message": GONE}, status_code=404)
    if not row["mine"]:
        return JSONResponse({"message": NOT_YOURS}, status_code=403)
    _, own = current_card(post_id, row["payload"])
    resolved, card = resolve_edit(data, own)
    if resolved.dropped or (resolved.is_empty and not (data.plain and data.text.strip())):
        return JSONResponse({"message": CHECK_THE_FORM, "dropped": resolved.dropped}, status_code=422)
    source = data.source if data.text.strip() and not resolved.is_empty else "manual"
    if not _save(member, row, post_id, data.text.strip(), resolved, card, source=source,
                 extraction_raw=data.extraction_raw, model=data.model, latency_ms=data.latency_ms):
        return JSONResponse({"message": GONE}, status_code=404)
    return JSONResponse({"id": post_id, "message": UPDATED})
