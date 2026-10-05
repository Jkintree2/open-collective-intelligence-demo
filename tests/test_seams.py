"""Seams that let sub-plans C, D and E work in parallel without editing the same lines."""
import importlib
from pathlib import Path

import pytest

from app import graph
from app.extract import CardPayload, Candidates, resolve_payload


def test_posting_writes_its_edges_through_write_payload(monkeypatch):
    from app import graph_posts
    seen = []
    monkeypatch.setattr(graph_posts, "write_payload",
                        lambda tx, payload, common, **switches: seen.append((payload, common, switches)))

    class Transaction:
        def run(self, query, **parameters):
            pass

    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute_write(self, work): work(Transaction())

    monkeypatch.setattr(graph, "driver", lambda: type("D", (), {"session": lambda self, **kw: Session()})())
    payload = resolve_payload(CardPayload.model_validate({"issues": [{"name": "Flooding"}]}), Candidates.empty())
    graph.merge_post("anon:test", None, True, None, "Flooding matters", payload, post_id="p1")
    assert len(seen) == 1
    assert seen[0][1]["post_id"] == "p1" and seen[0][1]["person_key"] == "anon:test"
    assert seen[0][2] == {"one_stance": False}  # today's stance statement unless a caller asks (C2)


def _main(monkeypatch):
    from app.config import Settings
    settings = Settings("gate", "secret", "admin", "unused", "unused", "unused", app_env="local")
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    return importlib.import_module("app.main")


def _paths(routes):
    """Every path served by `routes`, looking inside included routers (newer FastAPI keeps an
    included router as one object without a `.path`, holding the original router's routes)."""
    found = set()
    for route in routes:
        path = getattr(route, "path", None)
        if path is not None:
            found.add(path)
        inner = getattr(route, "original_router", None)
        if inner is not None:
            found |= _paths(inner.routes)
    return found


def test_every_routes_module_is_included(monkeypatch):
    main = _main(monkeypatch)
    paths = _paths(main.app.routes)
    for module_file in sorted(Path(main.BASE).glob("routes_*.py")):
        module = importlib.import_module(f"app.{module_file.stem}")
        for route in module.router.routes:
            assert route.path in paths, f"{module_file.name} {route.path} is not wired"


def test_a_new_routes_module_is_picked_up_by_its_file_name(monkeypatch, tmp_path):
    """At A1 no app/routes_*.py exists yet, so the test above passes on an empty loop; this one
    proves the mechanism with a throwaway package of its own."""
    from fastapi import FastAPI
    package = tmp_path / "seam_pages"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "routes_dummy.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n\n\n@router.get('/dummy-seam')\ndef dummy():\n    return {}\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    target = FastAPI()
    _main(monkeypatch).include_routers(target, package, "seam_pages")
    assert "/dummy-seam" in _paths(target.routes)


def test_page_scripts_expose_the_card_to_later_scripts():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "window.oci = {setPositionOnExisting: card.setPositionOnExisting, card};" in source


def test_css_keeps_one_anchor_per_parallel_sub_plan():
    css = Path("app/static/app.css").read_text(encoding="utf-8")
    anchors = ["/* Phase 1: stances (sub-plan C) */", "/* Phase 1: own posts (sub-plan D) */",
               "/* Phase 1: search and tidying (sub-plan E) */"]
    positions = [css.index(anchor) for anchor in anchors]
    assert positions == sorted(positions)
