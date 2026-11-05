"""v0.3, one box for Write and Ask on the Home page, behind HOME_ENABLED (off, preview or on)."""

from __future__ import annotations

from fastapi import Request

from app import config


def home_on(request: Request) -> bool:
    """Whether this reader gets the Home page: every signed-in member with "on", only the members listed in
    HOME_PREVIEW with "preview", nobody with "off". Signed out, and on the passphrase site (accounts off), never.
    It reads only the member require_access (or the About page) already found, never the database, so an error or
    asleep page that draws the menu cannot fail on it."""
    settings = config.get_settings()
    if settings.home_enabled not in ("preview", "on") or not settings.accounts_enabled:
        return False
    member = getattr(request.state, "member", None)
    if member is None:
        return False
    return settings.home_enabled == "on" or member.email.strip().lower() in settings.home_preview
