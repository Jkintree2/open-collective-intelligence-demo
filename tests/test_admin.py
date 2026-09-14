"""Admin HTTP checks use stubs exclusively; no lifespan or database is opened."""

import importlib
import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from app.config import Settings


@pytest.fixture
def admin_client(monkeypatch):
    settings = Settings("gate", "signing secret", "admin password", "unused", "unused", "unused", app_env="local")
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    main = importlib.import_module("app.main")
    admin = importlib.import_module("app.admin")
    calls = []
    monkeypatch.setattr(main.graph, "driver", lambda: pytest.fail("No test may access a database"))
    monkeypatch.setattr(main.graph, "counts", lambda: ({"Person": 2, "Post": 1}, {"CLAIM": 3}))
    monkeypatch.setattr(main.graph, "list_posts", lambda limit: calls.append(("list", limit)) or [{
        "id": "post-id", "display_name": "<script>private</script>", "text": "<b>statement</b>",
        "created_at": datetime.now(timezone.utc), "seed": True}])
    monkeypatch.setattr(main.graph, "delete_post", lambda id: calls.append(("delete", id)) or True)
    monkeypatch.setattr(main.graph, "delete_everything", lambda: calls.append(("reset",)))
    monkeypatch.setattr(admin, "reload_seed", lambda: calls.append(("reload",)))
    monkeypatch.setattr(main.graph, "export_record", lambda: {"format": "oci-record", "version": 1})
    monkeypatch.setattr(admin.extract, "last_model_error", None)
    client = TestClient(main.app)
    yield client, admin, calls
    client.close()


PATHS = [("get", "/admin"), ("get", "/admin/export.json"), ("post", "/admin/reload"),
         ("post", "/admin/reset"), ("post", "/admin/posts/post-id/delete")]
AUTH = ("any username", "admin password")


@pytest.mark.parametrize("method,path", PATHS)
def test_every_admin_endpoint_requires_basic_auth(admin_client, method, path):
    client, _, calls = admin_client
    for auth in (None, ("admin", "wrong")):
        result = getattr(client, method)(path, auth=auth)
        assert result.status_code == 401
        assert result.headers["www-authenticate"].startswith("Basic")
    assert calls == []


def token(client):
    page = client.get("/admin", auth=AUTH)
    assert page.status_code == 200
    return re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)


def test_admin_page_counts_last_fifty_and_escaped_posts(admin_client):
    client, _, calls = admin_client
    result = client.get("/admin", auth=("", "admin password"))
    assert result.status_code == 200
    assert "People</dt><dd>2" in result.text and "Claims</dt><dd>3" in result.text
    assert "<p>none</p>" in result.text and "· seed" in result.text
    assert "&lt;script&gt;" in result.text and "<b>statement</b>" not in result.text
    assert calls == [("list", 50)]
    assert result.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", [path for method, path in PATHS if method == "post"])
def test_mutations_require_signed_token(admin_client, path):
    client, _, calls = admin_client
    for csrf in ("", "invalid", token(client) + "x"):
        result = client.post(path, auth=AUTH, data={"csrf_token": csrf, "confirmation": "RESET"})
        assert result.status_code == 403
    assert all(call[0] == "list" for call in calls)


@pytest.mark.parametrize("headers", [{"Origin": "https://other.example"}, {"Origin": "null"},
    {"Referer": "http://other.example/admin"}, {"Origin": "http://[broken"},
    {"Sec-Fetch-Site": "cross-site"}])
def test_foreign_or_malformed_origin_refused(admin_client, headers):
    client, _, calls = admin_client
    result = client.post("/admin/reload", auth=AUTH, headers=headers, data={"csrf_token": token(client)})
    assert result.status_code == 403
    assert ("reload",) not in calls


def test_an_https_origin_is_accepted_when_the_proxy_ends_tls(admin_client):
    """On the deployed site the browser sends https while the request itself reads as http."""
    client, _, calls = admin_client
    response = client.post("/admin/reload", auth=AUTH, headers={"Origin": "https://testserver"},
                           data={"csrf_token": token(client)}, follow_redirects=False)
    assert response.status_code == 303
    assert ("reload",) in calls


def test_a_seed_failure_after_a_reset_reports_the_empty_record(admin_client, monkeypatch):
    client, admin, calls = admin_client
    from scripts import seed

    def fail():
        raise seed.SeedError("seed post one lost items")

    monkeypatch.setattr(admin, "reload_seed", fail)
    response = client.post("/admin/reset", auth=AUTH, follow_redirects=False,
                           data={"csrf_token": token(client), "confirmation": "RESET"})
    assert response.status_code == 303 and response.headers["location"] == "/admin?done=empty"
    assert ("reset",) in calls
    page = client.get("/admin?done=empty", auth=AUTH)
    assert "The record was cleared, but the seed statements did not all load. Press Reload seed." in page.text


def test_a_seed_failure_on_reload_leaves_the_record_alone(admin_client, monkeypatch):
    client, admin, calls = admin_client
    from scripts import seed

    def fail():
        raise seed.SeedError("seed post one lost items")

    monkeypatch.setattr(admin, "reload_seed", fail)
    result = client.post("/admin/reload", auth=AUTH, data={"csrf_token": token(client)})
    assert result.status_code == 500
    assert "seed post one" not in result.text
    assert ("reset",) not in calls


def test_expired_or_rotated_token_refused(admin_client, monkeypatch):
    client, _, _ = admin_client
    csrf = token(client)
    monkeypatch.setattr("app.auth.time.time", lambda: 10**11)
    assert client.post("/admin/reload", auth=AUTH, data={"csrf_token": csrf}).status_code == 403


def test_reload_delete_and_typed_reset(admin_client):
    client, _, calls = admin_client
    data = {"csrf_token": token(client)}
    for confirmation in ("", "reset", " RESET"):
        result = client.post("/admin/reset", auth=AUTH, data={**data, "confirmation": confirmation})
        assert result.status_code == 400
    assert ("reset",) not in calls
    for path in ("/admin/reload", "/admin/posts/post-id/delete", "/admin/reset"):
        response = client.post(path, auth=AUTH, data={**data, "confirmation": "RESET"},
                               headers={"Origin": "http://testserver"}, follow_redirects=False)
        assert response.status_code == 303
    assert calls[-4:] == [("reload",), ("delete", "post-id"), ("reset",), ("reload",)]


def test_export_is_download_and_safe_error_never_uses_provider_text(admin_client, monkeypatch):
    client, admin, _ = admin_client
    monkeypatch.setattr(admin.extract, "last_model_error", {
        "http": 402, "message": "SECRET provider text <script>", "time": "2026-09-09T02:12:00+02:00"})
    page = client.get("/admin", auth=AUTH)
    assert "balance needs a top up" in page.text
    assert "9 September 2026, 00:12 UTC" in page.text
    assert "SECRET" not in page.text and "provider text" not in page.text
    result = client.get("/admin/export.json", auth=AUTH)
    assert result.status_code == 200 and result.json()["version"] == 1
    assert "attachment" in result.headers["content-disposition"]
    assert result.headers["cache-control"] == "no-store"


def test_reload_uses_existing_seed_loader(monkeypatch):
    admin = importlib.import_module("app.admin")
    from scripts import seed
    loaded = []
    monkeypatch.setattr(seed, "load", lambda data: loaded.append(data))
    admin.reload_seed()
    assert len(loaded[0]["posts"]) == 14
