"""v0.3: one box for Write and Ask on the Home page, behind HOME_ENABLED (app/home.py). home.js asks
POST /api/home/kind what a text is, then starts the reading or the answer in place. Without JavaScript the box posts
to /home: a statement is posted as POST /posts posts it, a question is answered as POST /ask answers it (on the Ask
page), and when the site can't tell, Home comes back with the text and two buttons. The box on Issues, My statements
and About posts to /home with start set, and Home carries on with the text. With ASK_ENABLED off, every text is a
statement."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import config, home
from app.members import require_access, require_same_origin
from app.pages import page
from app.text import TEXT_MAX

router = APIRouter()
CHOICES = ("statement", "question")
GUARDS = [Depends(require_access), Depends(require_same_origin), Depends(home.require_home)]


def kind_for(text: str, choice: str = "") -> str:
    """What Home does with a text. With ASK_ENABLED off, always a statement. Over the write limit, a statement, so
    the write path gives its own message. Otherwise the writer's choice from the two buttons, else the rules."""
    if not config.get_settings().ask_enabled or len(text) > TEXT_MAX:
        return "statement"
    return choice if choice in CHOICES else home.kind_of(text)


class KindRequest(BaseModel):
    text: str = Field(default="", max_length=4 * TEXT_MAX)


@router.post("/api/home/kind", dependencies=GUARDS)
def kind(data: KindRequest) -> dict[str, str]:
    return {"kind": kind_for(data.text)}


@router.post("/home", dependencies=GUARDS)
def home_form(request: Request, text: str = Form("", max_length=4 * TEXT_MAX), kind: str = Form("", max_length=20),
              anonymous: str | None = Form(None), start: str = Form("", max_length=5)) -> Response:
    from app import main, routes_ask  # main loads the routers last
    if start:
        return main._render_index(request, text=text[:TEXT_MAX].strip(), start=True)
    chosen = kind_for(text, kind)
    if chosen == "statement":
        return main.create_post(request, display_name="", anonymous=anonymous, text=text)
    if chosen == "question":
        return routes_ask.ask_form(request, question=text, issue="", solution="", evidence="", earlier=[])
    return main._render_index(request, text=text.strip(), unsure=True)


@router.get("/home/mine", dependencies=[Depends(require_access), Depends(home.require_home)])
def home_mine(request: Request) -> Response:
    """The list under Home's button, which app.js draws again after a post or an answer."""
    from app import main
    return page(request, "_home_mine.html", {"home_mine": main._home_mine(request), "home_ask": home.home_asks(request)},
                private=True)
