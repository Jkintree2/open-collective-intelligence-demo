def card(**extra):
    return {"text": "Flooding is getting worse", "issues": [{"name": "Flooding"}], **extra}


def test_a_named_post_is_credited_to_the_account_whatever_the_request_says(member_app):
    member_app.sign_in()
    result = member_app.client.post("/api/posts", json=card(display_name="Somebody Else"))
    assert result.status_code == 201
    args, _ = member_app.writes[0]
    assert args[:4] == ("acct:ada", "Ada Tester", False, "Ada Tester")
    assert "oci_name" not in result.headers.get("set-cookie", "")


def test_an_anonymous_post_still_belongs_to_the_account(member_app):
    member_app.sign_in()
    result = member_app.client.post("/api/posts", json=card(anonymous=True))
    args, _ = member_app.writes[0]
    assert args[:4] == ("acct:ada", None, True, None)
    assert "oci_anon" not in result.headers.get("set-cookie", "")


def test_the_plain_form_posts_as_the_account_too(member_app, monkeypatch):
    raw = []
    monkeypatch.setattr(member_app.main.graph, "create_raw_post", lambda *args: raw.append(args))
    member_app.sign_in()
    member_app.client.post("/posts", data={"text": "Plain statement", "display_name": "Somebody Else"})
    assert raw == [("acct:ada", "Ada Tester", False, "Ada Tester", "Plain statement")]


def test_the_preview_speaks_in_the_account_name(member_app):
    member_app.sign_in()
    result = member_app.client.post("/api/preview", json=card(display_name="Somebody Else"))
    assert result.json()["sentences"] == ["Ada Tester claims Flooding"]


def test_the_write_page_has_no_name_field_and_explains_anonymous(member_app):
    member_app.sign_in()
    page = member_app.client.get("/").text
    assert 'id="display_name"' not in page
    assert 'data-member="Ada Tester"' in page
    assert ("Your name is not shown to others. The record still knows the post is yours, "
            "so you can edit or delete it later.") in page
