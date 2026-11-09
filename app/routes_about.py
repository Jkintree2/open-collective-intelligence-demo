"""Phase 3: the About page (04_interface.md, "About"), behind ABOUT_ENABLED. It opens without signing in,
reads nothing from the record but the signed-in account (for the menu) and calls no reading service; the
three guiding documents come from the same text that app/principles.py puts at the start of the instructions."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app import config, principles
from app.about_site import site_context
from app.members import current_member
from app.pages import page

router = APIRouter()

def about_on() -> None:
    if not config.get_settings().about_enabled:
        raise HTTPException(404)


@router.get("/about", dependencies=[Depends(about_on)])
def about(request: Request) -> Response:
    settings = config.get_settings()
    # The page opens without signing in, so require_access never looked; a signed-in member gets the whole menu.
    current_member(request)
    return page(request, "about.html", {**site_context(settings), "documents": principles.DOCUMENTS})
