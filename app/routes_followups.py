"""Phase 3: POST /api/follow-ups, questions that would make a statement clearer, for the card's new rows."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app import config, followups
from app.auth import DailyLimit, KeyedLimit, MinuteBucket
from app.members import require_access, require_same_origin
from app.routes_evidence import reader_key

router = APIRouter()

# The card's reading allows 6 a minute and 300 a day for the site; follow-ups have their own allowance of
# the same size, so asking them never spends a reading. One person: 10 cards in ten minutes.
person_limit = KeyedLimit(10, 600)
site_minute = MinuteBucket(capacity=6, period=60.0)
site_daily = DailyLimit(capacity=300)


class CardRow(BaseModel):
    row: Literal["issue", "solution", "evidence"]
    name: str = Field(default="", max_length=300)
    existing: bool = False
    url: str | None = Field(default=None, max_length=2000)
    personal: bool = False


class FollowUpRequest(BaseModel):
    text: str = Field(default="", max_length=4000)
    rows: list[CardRow] = Field(default_factory=list, max_length=13)


@router.post("/api/follow-ups", dependencies=[Depends(require_access), Depends(require_same_origin)])
def follow_up_questions(request: Request, data: FollowUpRequest) -> Response:
    settings = config.get_settings()
    if not settings.follow_ups_enabled:
        return JSONResponse({"message": "Not found"}, status_code=404)
    # Only rows the record does not hold yet get questions (04_interface.md, "Follow-up questions on the card").
    rows = [followups.Row(item.row, item.name.strip(), item.url, item.personal) for item in data.rows
            if not item.existing and item.name.strip()]
    if not rows:
        return JSONResponse({"questions": []})
    who = reader_key(request)
    result = followups.follow_ups(data.text, rows, settings, request_id=getattr(request.state, "request_id", None),
                                  limited=lambda: not person_limit.take(who) or not site_daily.take(site_minute))
    return JSONResponse({"questions": result.questions})
