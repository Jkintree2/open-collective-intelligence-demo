from datetime import datetime, timedelta, timezone

from app.text import clean_name, make_key, normalise, relative_time


def test_leading_the_and_no_article_share_a_key():
    assert make_key("The need for world government") == "need for world government"
    assert make_key("Need for world government") == "need for world government"


def test_trailing_period_and_capitals_share_a_key():
    assert make_key("Security council veto.") == "security council veto"
    assert make_key("Security Council veto") == "security council veto"


def test_slash_keeps_the_leading_a():
    assert make_key("A/B testing") == "a b testing"


def test_only_punctuation_gives_none():
    assert make_key("!!!") is None


def test_bare_article_gives_none():
    assert make_key("The") is None


def test_single_character_key_is_rejected():
    assert make_key("x") is None


def test_normalise_applies_nfkc_lowercases_and_collapses_spaces():
    assert normalise("  Ｗorld   government ") == "world government"


def test_clean_name_keeps_iphone_case():
    assert clean_name("iPhone") == "iPhone"


def test_clean_name_keeps_ebay_case():
    assert clean_name("eBay") == "eBay"


def test_clean_name_uppercases_a_plain_lowercase_start():
    assert clean_name("security council veto.") == "Security council veto"


def test_clean_name_turns_newlines_into_spaces():
    assert clean_name("John\nKintree\r\n") == "John Kintree"


def test_clean_name_caps_at_120_characters():
    assert len(clean_name("a" * 200)) == 120


def test_clean_name_strips_trailing_punctuation():
    assert clean_name("Why not?!") == "Why not"


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def test_relative_time_under_a_minute_is_just_now():
    assert relative_time(NOW - timedelta(seconds=20), NOW) == "just now"


def test_relative_time_minutes_hours_days():
    assert relative_time(NOW - timedelta(minutes=5), NOW) == "5 minutes ago"
    assert relative_time(NOW - timedelta(hours=2), NOW) == "2 hours ago"
    assert relative_time(NOW - timedelta(days=3), NOW) == "3 days ago"


def test_relative_time_singular_units():
    assert relative_time(NOW - timedelta(minutes=1), NOW) == "1 minute ago"
    assert relative_time(NOW - timedelta(hours=1), NOW) == "1 hour ago"
    assert relative_time(NOW - timedelta(days=1), NOW) == "1 day ago"
