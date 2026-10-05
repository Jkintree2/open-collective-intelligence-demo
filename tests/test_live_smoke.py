import pytest

pytestmark = pytest.mark.live


def test_the_test_database_answers_and_takes_the_constraints(live_graph):
    assert live_graph.health() == 0
