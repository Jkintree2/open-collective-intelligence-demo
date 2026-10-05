import time
from datetime import datetime, timedelta, timezone

import pytest

from app import accounts
from app.auth import KeyedLimit

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
# member_cookie_valid compares against the real clock, so the cookie tests start from it.
T = float(int(time.time()))


def test_a_password_checks_against_its_own_hash_only():
    stored = accounts.hash_password("correct horse battery")
    assert stored.startswith("scrypt$16384$8$1$")
    assert accounts.check_password("correct horse battery", stored)
    assert not accounts.check_password("correct horse batterY", stored)
    assert accounts.hash_password("correct horse battery") != stored  # a fresh salt each time


@pytest.mark.parametrize("stored", [None, "", "plain", "scrypt$1$2", "bcrypt$a$b$c$d$e", "scrypt$x$8$1$AA==$AA=="])
def test_a_missing_or_malformed_hash_never_matches(stored):
    assert not accounts.check_password("anything at all", stored)


def test_at_most_two_passwords_are_hashed_at_once(monkeypatch):
    """scrypt takes 16 MiB a run; the free instance has 512 MB and 40 request threads."""
    import threading
    import time
    running, peak, lock = [0], [0], threading.Lock()
    real = accounts.hashlib.scrypt

    def slow(*args, **kwargs):
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.05)
        with lock:
            running[0] -= 1
        return real(*args, **kwargs)
    monkeypatch.setattr(accounts.hashlib, "scrypt", slow)
    stored = accounts.hash_password("correct horse battery")
    threads = [threading.Thread(target=accounts.check_password, args=("correct horse battery", stored))
               for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert peak[0] == 2


@pytest.mark.parametrize("password, again, problem", [
    ("short", "short", "Please use at least 10 characters for your password."),
    ("ten chars!", "ten chars?", "The two passwords are not the same."),
    ("ten chars!", "ten chars!", None),
])
def test_password_rules_are_length_and_sameness_only(password, again, problem):
    assert accounts.password_problem(password, again) == problem


def test_emails_are_trimmed_and_lower_cased_and_checked_loosely():
    assert accounts.normalise_email("  Ada@Example.ORG ") == "ada@example.org"
    assert accounts.looks_like_email("ada@example.org")
    for bad in ("", "ada", "ada@", "@example.org", "ada@example", "a b@example.org"):
        assert not accounts.looks_like_email(bad)


def test_a_link_is_stored_only_as_its_hash():
    secret, stored = accounts.new_link()
    assert len(secret) >= 40 and stored == accounts.link_hash(secret) and secret not in stored
    assert accounts.new_link()[0] != secret


def test_link_lifetimes():
    assert accounts.link_expiry("invite", NOW) == NOW + timedelta(days=14)
    assert accounts.link_expiry("reset", NOW) == NOW + timedelta(hours=1)


@pytest.mark.parametrize("row, purpose, state", [
    (None, "invite", "gone"),
    ({"purpose": "reset", "active": True, "expires_at": NOW + timedelta(minutes=5)}, "invite", "gone"),
    ({"purpose": "invite", "active": False, "expires_at": NOW + timedelta(days=1)}, "invite", "gone"),
    ({"purpose": "invite", "active": True, "expires_at": NOW}, "invite", "expired"),
    ({"purpose": "invite", "active": True, "expires_at": NOW + timedelta(seconds=1)}, "invite", "ok"),
])
def test_link_state(row, purpose, state):
    assert accounts.link_state(row, purpose, NOW) == state


def test_member_cookie_round_trip_and_what_breaks_it():
    cookie = accounts.make_member_cookie("acct:1234", "scrypt$hash-one", "secret", now=T)
    assert accounts.member_cookie_key(cookie, now=T + 60) == "acct:1234"
    assert accounts.member_cookie_valid(cookie, "scrypt$hash-one", "secret")
    # A new password hash, another signing key or a changed key all break it.
    assert not accounts.member_cookie_valid(cookie, "scrypt$hash-two", "secret")
    assert not accounts.member_cookie_valid(cookie, "scrypt$hash-one", "other secret")
    assert not accounts.member_cookie_valid(cookie.replace("acct:1234", "acct:9999"), "scrypt$hash-one", "secret")
    assert not accounts.member_cookie_valid(cookie, None, "secret")
    # Thirty days, then gone.
    assert accounts.member_cookie_key(cookie, now=T + 29 * 86400)
    assert accounts.member_cookie_key(cookie, now=T + 31 * 86400) is None


@pytest.mark.parametrize("cookie", [None, "", "acct:1.2", "name:x.9999999999." + "0" * 64,
                                    "acct:1.notdigits." + "0" * 64, "acct:1.9999999999.short"])
def test_malformed_member_cookies_name_nobody(cookie):
    assert accounts.member_cookie_key(cookie, now=T) is None


def test_keyed_limit_counts_each_key_in_its_own_window():
    limit = KeyedLimit(count=3, period=3600)
    assert all(limit.take("ada@example.org", now=100.0) for _ in range(3))
    assert not limit.take("ada@example.org", now=200.0)
    assert limit.take("bob@example.org", now=200.0)
    assert limit.take("ada@example.org", now=3701.0)
    assert set(limit.uses) <= {"ada@example.org", "bob@example.org"}
