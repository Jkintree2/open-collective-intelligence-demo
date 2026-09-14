import subprocess
import sys

from app.graph import person_key


def test_the_orchestration_modules_import_on_their_own():
    """They read the query text from graph.py, which must not need them back at import time."""
    for module in ("app.graph_posts", "app.graph_backup", "app.graph"):
        result = subprocess.run([sys.executable, "-c", f"import {module}"], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def test_person_key_for_a_name_uses_the_normalised_key():
    assert person_key("John Kintree", False, "ignored") == "name:john kintree"


def test_person_key_for_anonymous_uses_the_browser_id():
    assert person_key("John Kintree", True, "1234") == "anon:1234"


def test_merge_is_one_transaction_and_stores_final_payload_without_anonymous_name(monkeypatch):
    import json
    from app import graph
    from app.extract import CardPayload, Candidates, resolve_payload

    calls, transactions = [], []

    class Transaction:
        def run(self, query, **parameters):
            calls.append((query, parameters))

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute_write(self, work):
            transactions.append(True)
            work(Transaction())

    class Driver:
        def session(self, **kwargs):
            return Session()

    monkeypatch.setattr(graph, "driver", lambda: Driver())
    payload = resolve_payload(CardPayload.model_validate({"issues": [{"name": "Flooding"}]}), Candidates.empty())
    graph.merge_post("anon:test", "Private name", True, "Private name", "Flooding matters", payload)
    assert len(transactions) == 1
    person = next(params for query, params in calls if query == graph.MERGE_PERSON)
    post = next(params for query, params in calls if query == graph.CREATE_POST)
    assert person["name"] is None and post["display_name"] is None
    assert json.loads(post["payload"])["issues"][0]["key"] == "flooding"
