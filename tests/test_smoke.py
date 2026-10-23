"""scripts/smoke.py against a fake site: read-only checks after a deploy. No network."""

import httpx

from scripts.smoke import GATED, asset_version, run

STATIC = {"app.css": b"body {}", "card.js": b"// card"}


def site(static=STATIC, version=None, cookie_ok="good", gate=lambda path: "/sign-in?next=" + path):
    seen = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        path, cookie = request.url.path, request.headers.get("cookie", "")
        if path == "/sign-in":
            return httpx.Response(200, text=f'<link href="/static/app.css?v={version or asset_version(static)}">Sign in')
        if path.startswith("/static/"):
            body = static.get(path.removeprefix("/static/"))
            return httpx.Response(200, content=body) if body is not None else httpx.Response(404)
        if path == "/forgot-password":
            return httpx.Response(200, text="Forgot your password?")
        if path == "/admin":
            return httpx.Response(401, headers={"www-authenticate": 'Basic realm="admin"'})
        if path in GATED:
            if cookie == f"oci_member={cookie_ok}":
                pages = {"/": "Recent posts", "/issues": "Issues", "/my-statements": "<h1>My statements</h1>",
                         "/account": "<h1>My account</h1>"}
                return httpx.Response(200, text=pages.get(path, ""))
            return httpx.Response(303, headers={"location": "https://site.example" + gate(path)})
        return httpx.Response(404)
    return httpx.Client(base_url="https://site.example", transport=httpx.MockTransport(answer)), seen


def failed(checks):
    return [check.name for check in checks if not check.ok]


def test_a_site_running_the_commit_passes_with_get_requests_only():
    client, seen = site()
    checks = run(client, STATIC)
    assert failed(checks) == []
    assert {method for method, _ in seen} == {"GET"}
    assert len(checks) == 2 + len(STATIC) + len(GATED) + 3


def test_a_site_on_another_commit_fails_on_the_hash_and_the_changed_file():
    client, _ = site(static={**STATIC, "card.js": b"// older card"})
    assert failed(run(client, STATIC)) == ["scripts and style are this commit's", "/static/card.js"]


def test_a_page_left_open_signed_out_fails():
    client, _ = site(gate=lambda path: "/people" if path == "/people" else "/sign-in")
    assert failed(run(client, STATIC)) == ["/people signed out goes to sign in"]


def test_the_signed_in_pages_are_checked_only_with_a_cookie():
    client, _ = site()
    names = [check.name for check in run(client, STATIC, cookie="good")]
    assert "/my-statements signed in" in names and failed(run(client, STATIC, cookie="good")) == []
    assert failed(run(client, STATIC, cookie="stale")) == [f"{path} signed in" for path in
                                                          ("/", "/issues", "/my-statements", "/account")]
