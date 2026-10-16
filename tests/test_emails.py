import re

import pytest

from app import accounts, emails

TECHNICAL = re.compile(r"\b(node|edge|graph|cypher|model|extraction|entity|token|database)s?\b", re.I)


def assert_plain(text, allowed=()):
    """Client-facing rules: no dashes, no technical words, except words John chose himself."""
    assert "–" not in text and "—" not in text and " - " not in text
    found = [word for word in TECHNICAL.findall(text) if word.lower() not in allowed]
    assert not found, found


def test_invitation_email_word_for_word():
    subject, text = emails.invitation("Open Collective Intelligence", "Bob Smith", "Ada Tester", "neighbor",
                                      "https://record.example/accept/abc")
    assert subject == "Your invitation to Open Collective Intelligence"
    assert text == (
        "Hello Bob Smith,\n\n"
        "Thank you for agreeing to take part in Open Collective Intelligence, an invitation-only test of a shared database "
        "of issues, solutions, and evidence people are claiming, proposing, and submitting.\n\n"
        "Entered by: Ada Tester\n"
        "How you know each other: Neighbor\n\n"
        "To accept and choose your own password, open this link:\n"
        "https://record.example/accept/abc\n\n"
        "The link works once, for 14 days. If it has expired, ask Ada Tester to send a new one. "
        "If you were not expecting this email, you can ignore it.\n\n"
        "If you have a question, reply to this email.\n\n"
        "John Kintree\n")
    assert_plain(subject + text, allowed=("database",))  # John's wording, 16 Oct 2026, as on the sign in page
    assert "password:" not in text.lower()  # never a password, only the link


def test_first_account_email_word_for_word():
    subject, text = emails.first_account("Open Collective Intelligence", "John Kintree", "https://record.example/accept/abc")
    assert subject == "Choose your password for Open Collective Intelligence"
    assert text == ("Hello John Kintree,\n\n"
                    "Your account on Open Collective Intelligence is ready. To choose your password, open this link:\n"
                    "https://record.example/accept/abc\n\n"
                    "The link works once, for 14 days.\n")
    assert_plain(subject + text)


def test_an_invitation_for_the_root_has_no_entered_by_lines():
    """X3: John's root account has no ENTERED, so Q15 and Q17 give no inviter."""
    url = "https://record.example/accept/abc"
    assert emails.invitation_for("Open Collective Intelligence", "John Kintree", None, None, url) == \
        emails.first_account("Open Collective Intelligence", "John Kintree", url)
    assert emails.invitation_for("Open Collective Intelligence", "Bob Smith", "Ada Tester", "neighbor", url) == \
        emails.invitation("Open Collective Intelligence", "Bob Smith", "Ada Tester", "neighbor", url)


def test_links_are_built_from_the_site_address():
    assert accounts.link_url("https://record.example", "accept", "s3cret") == "https://record.example/accept/s3cret"
    assert accounts.link_url("https://record.example/", "reset", "s3cret") == "https://record.example/reset/s3cret"
    with pytest.raises(ValueError):
        accounts.link_url("https://record.example", "admin", "s3cret")


def test_password_email_word_for_word():
    subject, text = emails.password_link("Open Collective Intelligence", "Ada Tester",
                                         "https://record.example/reset/abc")
    assert subject == "Choose a new password for Open Collective Intelligence"
    assert text == (
        "Hello Ada Tester,\n\n"
        "Someone asked for a new password for your account on Open Collective Intelligence. "
        "If it was you, open this link to choose one:\n"
        "https://record.example/reset/abc\n\n"
        "The link works once, for one hour. Your current password keeps working until you choose a new one.\n\n"
        "If it was not you, you can ignore this email.\n\n"
        "John Kintree\n")
    assert_plain(subject + text)
    assert "password:" not in text.lower()  # never a password, only the link
