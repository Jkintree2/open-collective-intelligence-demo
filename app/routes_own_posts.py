"""Editing and deleting one's own post (sub-plan D). The check is on the server, every time."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response

from app import graph_own_posts
from app.members import Member, require_member, require_same_origin
from app.pages import page

router = APIRouter()
# Client facing copy, word for word from docs/planning/04_interface.md.
NOT_YOURS = "You can change only your own posts."
GONE = "That post is no longer here."


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
