"""One-click approve and oppose on the issue page (sub-plan C, Q23)."""

from datetime import datetime, timezone
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app import graph_stances
from app.members import Member, require_member, require_same_origin, wants_json

router = APIRouter()
# Client facing copy, word for word from docs/planning/04_interface.md.
NOT_SAVED = "Your position was not saved. Please try again."
CHOICES = {"approve": "approve", "oppose": "oppose", "withdraw": None}


def solution_anchor(solution_key: str) -> str:
    return "solution-" + solution_key.replace(" ", "-")


@router.post("/solutions/{solution_key}/stance", dependencies=[Depends(require_same_origin)])
def stance(request: Request, solution_key: str, choice: str = Form(""), issue: str = Form(""),
           member: Member = Depends(require_member)) -> Response:
    result = None
    if choice in CHOICES:
        result = graph_stances.set_stance(member.key, solution_key, CHOICES[choice], datetime.now(timezone.utc))
    if wants_json(request):
        if result is None:
            return JSONResponse({"message": NOT_SAVED}, status_code=404 if choice in CHOICES else 422)
        return JSONResponse(result)
    # Without JavaScript every answer goes back to the page; a failure names the solution, and the
    # page shows NOT_SAVED in its stance line (_stance.html).
    if not issue:
        return RedirectResponse("/issues", status_code=303)
    back = f"/issues/{quote(issue, safe='')}"
    if result is None:
        back += "?" + urlencode({"not_saved": solution_key}, quote_via=quote)
    return RedirectResponse(f"{back}#{quote(solution_anchor(solution_key), safe='-')}", status_code=303)
