from app.auth import MinuteBucket, check_gate_token, make_gate_token

NOW = 1_800_000_000.0
DAY = 86400


def test_gate_token_round_trip():
    token = make_gate_token(NOW, secret_key="k", passphrase="maple river stone")
    assert check_gate_token(token, NOW + 60, secret_key="k", passphrase="maple river stone")


def test_token_made_under_a_different_passphrase_fails():
    token = make_gate_token(NOW, secret_key="k", passphrase="old words here")
    assert not check_gate_token(token, NOW + 60, secret_key="k", passphrase="maple river stone")


def test_token_expires_after_thirty_days():
    token = make_gate_token(NOW, secret_key="k", passphrase="p")
    assert check_gate_token(token, NOW + 29 * DAY, secret_key="k", passphrase="p")
    assert not check_gate_token(token, NOW + 31 * DAY, secret_key="k", passphrase="p")


def test_malformed_tokens_fail():
    for bad in (None, "", "abc", "123.", ".deadbeef", "notanumber.deadbeef"):
        assert not check_gate_token(bad, NOW, secret_key="k", passphrase="p")


def test_bucket_allows_six_a_minute_then_refuses():
    bucket = MinuteBucket(capacity=6, period=60)
    assert all(bucket.take(now=100.0) for _ in range(6))
    assert not bucket.take(now=100.0)


def test_bucket_refills_with_time():
    bucket = MinuteBucket(capacity=6, period=60)
    for _ in range(6):
        bucket.take(now=100.0)
    assert not bucket.take(now=105.0)
    assert bucket.take(now=111.0)


def test_post_spacing_holds_one_source_for_twenty_seconds_and_forgets_it_later():
    from app.auth import PostSpacing
    spacing = PostSpacing(seconds=20)
    assert spacing.take("john", now=100.0)
    assert not spacing.take("john", now=110.0)
    assert spacing.take("anon:1", now=110.0)
    assert spacing.take("john", now=120.0)
    assert len(spacing.last) <= 2
