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
