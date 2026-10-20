"""The emails the site sends, word for word from docs/planning/04_interface.md. Plain text only.
Sent from John's address, so they sign off as John (D1)."""


def invitation(site_name: str, name: str, inviter_name: str, relationship: str, url: str) -> tuple[str, str]:
    subject = f"Your invitation to {site_name}"
    text = (
        f"Hello {name},\n\n"
        f"Thank you for agreeing to take part in {site_name}, an invitation-only test of a shared database "
        "of issues, solutions, and evidence that people are claiming, proposing, and submitting.\n\n"
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


def password_link(site_name: str, name: str, url: str) -> tuple[str, str]:
    subject = f"Choose a new password for {site_name}"
    text = (
        f"Hello {name},\n\n"
        f"Someone asked for a new password for your account on {site_name}. "
        "If it was you, open this link to choose one:\n"
        f"{url}\n\n"
        "The link works once, for one hour. Your current password keeps working until you choose a new one.\n\n"
        "If it was not you, you can ignore this email.\n\n"
        "John Kintree\n"
    )
    return subject, text


def email_change_link(site_name: str, name: str, url: str) -> tuple[str, str]:
    """X2: to the new address only."""
    subject = f"Confirm your new email for {site_name}"
    text = (
        f"Hello {name},\n\n"
        f"You asked to use this address for your account on {site_name}. To confirm, open this link:\n"
        f"{url}\n\n"
        "The link works once, for 24 hours. Until you open it, sign in with your old address.\n\n"
        "If it was not you, you can ignore this email.\n\n"
        "John Kintree\n"
    )
    return subject, text


def email_change_notice(site_name: str, name: str, new_email: str) -> tuple[str, str]:
    """X2: to the old address, which keeps working until the link is opened."""
    subject = f"Your email on {site_name} is being changed"
    text = (
        f"Hello {name},\n\n"
        f"Someone signed in to your account on {site_name} asked to change its email to {new_email}. "
        "Nothing changes until the link sent to that address is opened.\n\n"
        "If it was not you, please change your password and reply to this email.\n\n"
        "John Kintree\n"
    )
    return subject, text
