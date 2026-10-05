def test_a_post_by_an_account_takes_the_one_stance_rule_and_a_passphrase_post_does_not(member_app, monkeypatch):
    """X1: with accounts off, a passphrase post writes today's stance statement."""
    card = {"text": "I oppose abolishing the veto", "issues": [{"name": "Flooding"}]}
    member_app.sign_in()
    assert member_app.client.post("/api/posts", json=card).status_code == 201
    assert member_app.writes[-1][1]["one_stance"] is True
    from dataclasses import replace
    off = replace(member_app.settings, accounts_enabled=False)
    for target in ("app.config.get_settings", "app.auth.get_settings"):
        monkeypatch.setattr(target, lambda: off)
    monkeypatch.setattr(member_app.main, "settings", off)
    member_app.client.post("/enter", data={"passphrase": "gate words"})
    assert member_app.client.post("/api/posts", json=card).status_code == 201
    assert member_app.writes[-1][1]["one_stance"] is False
