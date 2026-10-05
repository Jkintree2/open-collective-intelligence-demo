"""The emails the site sends, word for word from docs/planning/04_interface.md. Plain text only.
Sent from John's address, so they sign off as John (D1)."""


def invitation(site_name: str, name: str, inviter_name: str, relationship: str, url: str) -> tuple[str, str]:
    subject = f"Your invitation to {site_name}"
    text = (
        f"Hello {name},\n\n"
        f"Thank you for agreeing to take part in {site_name}, a closed test of a shared record "
        "of what people are claiming, proposing and citing.\n\n"
        f"Entered by: {inviter_name}\n"
        f"How you know each other: {relationship.capitalize()}\n\n"
        "To accept and choose your own password, open this link:\n"
        f"{url}\n\n"
        f"The link works once, for 14 days. If it has expired, ask {inviter_name} to send a new one. "
        "If you were not expecting this email, you can ignore it.\n\n"
        "If you have a question, reply to this email.\n\n"
        "John Kintree\n"
    )
    return subject, text


def first_account(site_name: str, name: str, url: str) -> tuple[str, str]:
    """John's own first email: no one entered him. make_admin.py sends nothing (X3); this goes
    when he uses "Forgot your password?" before he has chosen one."""
    subject = f"Choose your password for {site_name}"
    text = (
        f"Hello {name},\n\n"
        f"Your account on {site_name} is ready. To choose your password, open this link:\n"
        f"{url}\n\n"
        "The link works once, for 14 days.\n"
    )
    return subject, text


def invitation_for(site_name: str, name: str, inviter_name: str | None, relationship: str | None,
                   url: str) -> tuple[str, str]:
    """The email for any accept link: John's own wording when nobody entered the person."""
    if not inviter_name:
        return first_account(site_name, name, url)
    return invitation(site_name, name, inviter_name, relationship or "", url)
