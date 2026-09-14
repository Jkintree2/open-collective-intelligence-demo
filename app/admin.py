"""The password protected back room. All changes are submitted as forms."""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app import graph, extract
from app.auth import make_admin_csrf, require_admin, require_admin_mutation
from scripts import seed

log = logging.getLogger("oci")
router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])
ERRORS = {401: "The reading service did not accept its access key.",
          402: "The reading service balance needs a top up.",
          403: "The reading service refused access."}
LABEL_NAMES = {"Person": "People", "Issue": "Issues", "Solution": "Solutions",
               "Evidence": "Pieces of evidence", "Post": "Posts"}
REL_NAMES = {"POSTED": "Posts credited", "CLAIM": "Claims", "SUBMIT": "Citations",
             "PROPOSE": "Proposals", "HAVE_PROPOSED": "Solutions linked to issues",
             "SUPPORTS": "Statements of support", "REFUTES": "Statements against",
             "APPROVE": "Approvals", "OPPOSE": "Oppositions", "PART_OF": "Sub issues"}
NOTICES = {"reload": "Seed reloaded.", "reset": "Reset to seed.", "delete": "Post deleted.",
           "empty": "The record was cleared, but the seed statements did not all load. "
                    "Press Reload seed."}


def reading_error() -> str:
    error = extract.last_model_error
    if not error:
        return "none"
    message = ERRORS.get(error.get("http"), "The reading service could not complete a request.")
    try:
        timestamp = datetime.fromisoformat(error["time"])
        if timestamp.tzinfo is None:
            raise ValueError("Timestamp must have a time zone")
        when = timestamp.astimezone(timezone.utc).strftime("%-d %B %Y, %H:%M UTC")
    except (ValueError, TypeError, KeyError):
        return message
    return f"{message} Last recorded: {when}."


@router.get("")
def page(request: Request):
    from app.main import templates
    labels, relations = graph.counts()
    return templates.TemplateResponse(request=request, name="admin.html", context={
        "counts": [(name, labels.get(label, 0)) for label, name in LABEL_NAMES.items()],
        "relations": [(name, relations.get(rel, 0)) for rel, name in REL_NAMES.items()],
        "posts": graph.list_posts(limit=50), "csrf_token": make_admin_csrf(),
        "reading_error": reading_error(), "notice": NOTICES.get(request.query_params.get("done")),
    }, headers={"Cache-Control": "no-store"})


@router.get("/export.json")
def export():
    return JSONResponse(graph.export_record(), headers={
        "Content-Disposition": 'attachment; filename="shared-record.json"',
        "Cache-Control": "no-store",
    })


def seed_data() -> dict:
    return json.loads(seed.SEED_FILE.read_text(encoding="utf-8"))


def reload_seed() -> None:
    seed.load(seed_data())


@router.post("/reload", dependencies=[Depends(require_admin_mutation)])
def reload():
    try:
        reload_seed()
    except seed.SeedError as exc:
        log.error(json.dumps({"event": "seed_failed", "where": "reload", "error": str(exc)}))
        raise HTTPException(500, "The seed statements could not be loaded. Nothing was changed.")
    return RedirectResponse("/admin?done=reload", 303)


@router.post("/reset", dependencies=[Depends(require_admin_mutation)])
def reset(confirmation: str = Form("")):
    if confirmation != "RESET":
        raise HTTPException(400, "Type RESET to reset to seed.")
    # Read the seed file before anything is deleted: a broken file must not cost the record.
    seed_data()
    graph.delete_everything()
    try:
        reload_seed()
    except seed.SeedError as exc:
        # The record is empty at this point, so say so instead of answering with an error page.
        log.error(json.dumps({"event": "seed_failed", "where": "reset", "error": str(exc)}))
        return RedirectResponse("/admin?done=empty", 303)
    return RedirectResponse("/admin?done=reset", 303)


@router.post("/posts/{post_id}/delete", dependencies=[Depends(require_admin_mutation)])
def delete(post_id: str):
    if not graph.delete_post(post_id):
        raise HTTPException(404, "That post is no longer here.")
    return RedirectResponse("/admin?done=delete", 303)
