import pytest

from app import search


def test_every_word_is_required_as_written_or_as_a_start():
    """X4: "Try another word, or fewer words" is true only if every word must match."""
    assert search.lucene_query("Housing  Costs") == "+(housing housing*) +(costs costs*)"


@pytest.mark.parametrize("typed, query", [
    ('"quoted', '+(\\"quoted \\"quoted*)'),
    ("a:b", "+(a\\:b a\\:b*)"),
    ("c++", "+(c\\+\\+ c\\+\\+*)"),
    ("(veto)", "+(\\(veto\\) \\(veto\\)*)"),
    ("path/to", "+(path\\/to path\\/to*)"),
    ("back\\slash", "+(back\\\\slash back\\\\slash*)"),
    ("AND housing", "+(and and*) +(housing housing*)"),
    ("sub-issue", "+(sub\\-issue sub\\-issue*)"),
])
def test_lucene_query_escapes_everything(typed, query):
    assert search.lucene_query(typed) == query


@pytest.mark.parametrize("typed", ["", "   ", "*", "!!! ???", "-", "&& ||"])
def test_nothing_to_look_for(typed):
    assert search.lucene_query(typed) is None


def test_long_input_is_cut_to_ten_words_and_two_hundred_characters():
    assert search.lucene_query(" ".join(f"w{n}" for n in range(30))).count("*") == 10
    assert len(search.lucene_query("x" * 500)) < 2 * 200 + 10
