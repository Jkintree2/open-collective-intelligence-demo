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
