"""Read-only checks on a deployed site, run after each deploy. GET requests only: nothing is posted,
signed in, read by the model or written to the record, so it is safe against production.

    python -m scripts.smoke --url https://the-site.example [--ref origin/main]

Signed out it checks the sign-in page, that every page behind it sends you there, the back room's
password prompt, and that the served scripts and style are exactly the ones in --ref (the hash the
pages put on their links, and each file's bytes). The pages behind a Phase 3 switch (`/about`, `/ask`)
pass either way, not found while the switch is off or the page when it is on, and the line says which.
With OCI_SMOKE_COOKIE set to an `oci_member` cookie copied from a signed-in browser, it also opens the
signed-in pages. The cookie is never printed.
"""

import argparse
import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

# Pages that need someone signed in; signed out, each one sends the reader to sign in.
GATED = ("/", "/issues", "/people", "/my-statements", "/account", "/changes")
SIGNED_IN = {"/": "Recent posts", "/issues": "Issues", "/my-statements": "<h1>My statements</h1>",
             "/account": "<h1>My account</h1>"}
# Pages behind a switch in the Render dashboard, not found while it is off. /about opens signed out;
# /ask, like the gated pages, sends a signed-out reader to sign in and shows its heading signed in.
ABOUT = ("/about", "<h1>About this site</h1>")
ASK = ("/ask", '<h1 id="ask-title">Ask the record</h1>')
WAKE_SECONDS = 90  # a free Render service asleep takes most of a minute to answer


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def expected_static(ref: str) -> dict[str, bytes]:
    """The files in app/static at `ref`, as the app reads them (top level only)."""
    listing = subprocess.run(["git", "ls-tree", ref, "app/static/"], capture_output=True, text=True, check=True)
    names = [line.split("\t", 1)[1].rsplit("/", 1)[1] for line in listing.stdout.splitlines() if " blob " in line]
    return {name: subprocess.run(["git", "show", f"{ref}:app/static/{name}"], capture_output=True, check=True).stdout
            for name in names}


def asset_version(static: dict[str, bytes]) -> str:
    """The same hash app/main.py puts on every script and style link."""
    return hashlib.sha256(b"".join(static[name] for name in sorted(static))).hexdigest()[:10]


def _sends_to_sign_in(response: httpx.Response) -> bool:
    path = urlsplit(response.headers.get("location", "")).path
    return response.status_code == 303 and path in ("/sign-in", "/enter")


def _switched(name: str, response: httpx.Response, on: bool) -> Check:
    """A page behind a switch: not found means off and passes; anything else must be the page as it is on."""
    if response.status_code == 404:
        return Check(f"{name} (switched off)", True)
    return Check(f"{name} (switched on)", on, f"answered {response.status_code}")


def run(client: httpx.Client, static: dict[str, bytes], cookie: str | None = None) -> list[Check]:
    checks: list[Check] = []
    sign_in = client.get("/sign-in", timeout=WAKE_SECONDS)
    checks.append(Check("sign-in page", sign_in.status_code == 200 and "Sign in" in sign_in.text,
                        f"answered {sign_in.status_code}"))
    served = re.search(r'/static/app\.css\?v=([0-9a-f]+)', sign_in.text)
    expected = asset_version(static)
    checks.append(Check("scripts and style are this commit's", bool(served) and served.group(1) == expected,
                        f"site {served.group(1) if served else 'none'}, commit {expected}"))
    for name, body in sorted(static.items()):
        response = client.get(f"/static/{name}")
        checks.append(Check(f"/static/{name}", response.status_code == 200 and response.content == body,
                            f"answered {response.status_code}" if response.status_code != 200 else "differs from the commit"))
    for path in GATED:
        response = client.get(path)
        checks.append(Check(f"{path} signed out goes to sign in", _sends_to_sign_in(response),
                            f"answered {response.status_code}"))
    forgot = client.get("/forgot-password")
    checks.append(Check("forgot password page", forgot.status_code == 200, f"answered {forgot.status_code}"))
    admin = client.get("/admin")
    checks.append(Check("back room asks for its password", admin.status_code == 401
                        and "basic" in admin.headers.get("www-authenticate", "").lower(), f"answered {admin.status_code}"))
    missing = client.get("/no-such-page-smoke-check")
    checks.append(Check("unknown page is not found", missing.status_code == 404, f"answered {missing.status_code}"))
    about = client.get(ABOUT[0])
    checks.append(_switched("/about opens signed out", about, about.status_code == 200 and ABOUT[1] in about.text))
    ask = client.get(ASK[0])
    checks.append(_switched("/ask signed out goes to sign in", ask, _sends_to_sign_in(ask)))
    if cookie:
        for path, marker in SIGNED_IN.items():
            response = client.get(path, headers={"Cookie": f"oci_member={cookie}"})
            checks.append(Check(f"{path} signed in", response.status_code == 200 and marker in response.text,
                                f"answered {response.status_code}" + ("" if response.status_code != 200 else ", marker missing")))
        ask = client.get(ASK[0], headers={"Cookie": f"oci_member={cookie}"})
        checks.append(_switched("/ask signed in", ask, ask.status_code == 200 and ASK[1] in ask.text))
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only checks on a deployed site.")
    parser.add_argument("--url", default=os.environ.get("SITE_URL"), help="the site's address (default SITE_URL)")
    parser.add_argument("--ref", default="origin/main", help="the commit the site should be running")
    args = parser.parse_args(argv)
    if not args.url or urlsplit(args.url).scheme not in ("http", "https"):
        print("Give the site's address with --url, or set SITE_URL.")
        return 2
    try:
        static = expected_static(args.ref)
    except subprocess.CalledProcessError:
        print(f"Could not read app/static at {args.ref}. Run git fetch first?")
        return 2
    cookie = os.environ.get("OCI_SMOKE_COOKIE") or None
    with httpx.Client(base_url=args.url.rstrip("/"), follow_redirects=False, timeout=20,
                      headers={"User-Agent": "oci-smoke-check"}) as client:
        try:
            checks = run(client, static, cookie)
        except httpx.RequestError as exc:
            print(f"FAIL  the site did not answer ({type(exc).__name__})")
            return 1
    for check in checks:
        print(f"ok    {check.name}" if check.ok else f"FAIL  {check.name}: {check.detail}")
    failed = sum(not check.ok for check in checks)
    print(f"{len(checks) - failed} of {len(checks)} passed{'' if cookie else ' (signed out only; set OCI_SMOKE_COOKIE for the signed-in pages)'}.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
