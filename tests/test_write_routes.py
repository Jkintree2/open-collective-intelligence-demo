"""Every route that writes must refuse a post from another site (members.require_same_origin)."""
import importlib

from app.members import require_same_origin

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
OWN_CHECK = ("/enter", "/admin")  # the passphrase gate and the back room have their own checks


def _main(monkeypatch):
    from app.config import Settings
    settings = Settings("gate", "secret", "admin", "unused", "unused", "unused", app_env="local")
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    return importlib.import_module("app.main")


def _write_routes(routes):
    """Every route with a write method, looking inside included routers as test_seams does."""
    for route in routes:
        if getattr(route, "path", None) is not None and WRITE_METHODS & set(getattr(route, "methods", None) or ()):
            yield route
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _write_routes(inner.routes)


def _calls(dependant):
    for sub in dependant.dependencies:
        yield sub.call
        yield from _calls(sub)


def test_every_write_route_checks_it_comes_from_this_site(monkeypatch):
    main = _main(monkeypatch)
    routes = list(_write_routes(main.app.routes))
    assert len(routes) > 10  # the walk really found the routers' routes
    unchecked = sorted(
        f"{sorted(WRITE_METHODS & route.methods)} {route.path}" for route in routes
        if not route.path.startswith(OWN_CHECK) and require_same_origin not in set(_calls(route.dependant)))
    assert unchecked == []


SAME = {"origin": "http://testserver"}


def test_a_failed_save_gives_the_posting_slot_back(member_app, monkeypatch):
    """Review, 11 November 2026: a save that failed on the server still took the writer's twenty seconds, so pressing
    Post again said "Please wait a moment before posting again." although nothing had been saved, and the plain link
    looked like the way out."""
    member_app.sign_in()
    tries = []

    def write(*args, **kwargs):
        tries.append(1)
        if len(tries) == 1:
            raise RuntimeError("write failed")
        return "post-id"
    monkeypatch.setattr(member_app.main.graph, "merge_post", write)
    card = {"text": "The river floods every spring.", "issues": [{"name": "Flooding"}]}
    assert member_app.client.post("/api/posts", json=card, headers=SAME).status_code == 500
    again = member_app.client.post("/api/posts", json=card, headers=SAME)
    assert again.status_code == 201 and len(tries) == 2
    # A save that went in still holds the slot.
    assert member_app.client.post("/api/posts", json=card, headers=SAME).status_code == 429
