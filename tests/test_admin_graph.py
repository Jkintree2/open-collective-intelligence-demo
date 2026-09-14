"""Q11 transaction boundaries; full deletion behavior is rehearsed on a disposable record."""
import pytest
from app import graph


@pytest.mark.parametrize('touched', [None, [], ['4:issue:9', '4:evidence:10']])
def test_delete_cleans_only_returned_records_in_the_same_transaction(monkeypatch, touched):
    calls, transactions = [], []
    class Result:
        def single(self):
            return None if touched is None else {'touched': touched}
        def consume(self):
            pass
    class Transaction:
        def run(self, query, **params):
            calls.append((query, params))
            return Result()
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute_write(self, work):
            transactions.append(True)
            return work(Transaction())
    class Driver:
        def session(self, **kwargs): return Session()
    monkeypatch.setattr(graph, 'driver', Driver)
    assert graph.delete_post('chosen-post') is (touched is not None)
    assert len(transactions) == 1
    assert calls[0] == (graph.DELETE_POST, {'id': 'chosen-post'})
    if touched is None:
        assert len(calls) == 1  # Missing post must never trigger broad cleanup.
    else:
        assert calls[1:] == [(graph.DELETE_POST_ORPHANS, {'touched': touched})]
