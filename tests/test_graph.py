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


def test_a_position_on_an_existing_solution_writes_only_the_stance(monkeypatch):
    """GitHub issue 4: no CLAIM, no PROPOSE and no HAVE_PROPOSED for a plain approval."""
    from app import graph
    from app.extract import CardPayload, Candidates, resolve_payload

    calls = []

    class Transaction:
        def run(self, query, **parameters):
            calls.append((query, parameters))

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute_write(self, work):
            work(Transaction())

    class Driver:
        def session(self, **kwargs):
            return Session()

    monkeypatch.setattr(graph, "driver", lambda: Driver())
    known = Candidates(issues={"climate": {"name": "Climate", "parent_key": None}},
                       solutions={"ev fleets": "EV fleets", "carbon tax": "Carbon tax"},
                       solution_issues={"ev fleets": ["Climate"], "carbon tax": ["Climate"]})
    payload = resolve_payload(CardPayload.model_validate({
        "issues": [{"name": "Climate"}],
        "solutions": [{"name": "EV fleets", "for_issue": "Climate", "stance": "approve"}]}), known)
    graph.merge_post("anon:test", None, True, None, "I approve EV fleets", payload)
    queries = [query for query, _ in calls]
    assert graph.MERGE_ISSUE_CLAIM not in queries and graph.MERGE_SOLUTION_PROPOSE not in queries
    stances = [params for query, params in calls if query == graph.MERGE_STANCE.replace("{stance}", "APPROVE")]
    assert [params["solution_key"] for params in stances] == ["ev fleets"]


def test_an_accounts_post_writes_the_one_stance_statement(monkeypatch):
    """X1: the one-stance statement only when the caller says so (an account's post)."""
    from app import graph, graph_posts
    from app.extract import ResolvedPayload
    assert "{other}" in graph.MERGE_ONE_STANCE and "DELETE old" in graph.MERGE_ONE_STANCE
    assert graph.MERGE_ONE_STANCE.index("SET p.key = p.key") < graph.MERGE_ONE_STANCE.index("OPTIONAL MATCH")
    assert "{other}" not in graph.MERGE_STANCE  # 0.1's statement, unchanged
    payload = ResolvedPayload(solutions=[{"key": "abolish", "name": "Abolish", "for_issue_key": "veto",
                                          "stance": "oppose", "stance_only": True}])
    for one_stance, expected in ((True, graph.MERGE_ONE_STANCE.replace("{stance}", "OPPOSE").replace("{other}", "APPROVE")),
                                 (False, graph.MERGE_STANCE.replace("{stance}", "OPPOSE"))):
        queries = []
        tx = type("T", (), {"run": lambda self, query, **params: queries.append(query)})()
        graph_posts.write_payload(tx, payload, {"person_key": "acct:ada", "post_id": "p", "anonymous": False,
                                                "now": None, "seed": False}, one_stance=one_stance)
        assert queries == [expected]
