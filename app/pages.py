"""Rendering for router modules. Templates are created in main.py, so they are imported on use."""

from fastapi import Request
from fastapi.responses import Response

# Pages that hold a link or a password form: never cached, and no address leaks to another site.
# Not "no-referrer": under it a browser sends `Origin: null` with every form on the page, which
# members.require_same_origin must refuse (Fetch spec), so no one could sign in.
PRIVATE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "same-origin"}


# Emailed links never reach a log (03_schema.md): the secret part of the path is cut.
LINK_PATHS = ("/accept/", "/reset/")


def loggable_path(path: str) -> str:
    for prefix in LINK_PATHS:
        if path.startswith(prefix):
            return prefix + "\u2026"
    return path


def page(request: Request, name: str, context: dict | None = None, *, status_code: int = 200,
         private: bool = False) -> Response:
    from app.main import templates
    return templates.TemplateResponse(request, name, context or {}, status_code=status_code,
                                      headers=PRIVATE_HEADERS if private else None)


# Notices on the write page after a redirect (/?done=<name>), from 04_interface.md. Sub-plan D
# adds "deleted" and "edited".
WRITE_NOTICES = {"welcome": "Welcome, {name}. You are signed in.",
                 "reset": "Your new password is saved. You are signed out everywhere else."}


def write_notice(done: str | None, member) -> str | None:
    notice = WRITE_NOTICES.get(done or "")
    return notice.format(name=member.name) if notice and member else None


def link_problem(request: Request, problem: str, *, here: str, inviter_name: str | None = None) -> Response:
    """One page for every link that cannot be used (04_interface.md, Accepting). `here` is where
    "Sign out and continue" comes back to."""
    from app.members import current_member
    member = current_member(request)
    return page(request, "link_problem.html", {"problem": problem, "here": here, "inviter_name": inviter_name,
                                               "member_name": member.name if member else None}, private=True)
