"""Phase 3, ask the record: the question query (search.question_query) and the search that picks a
whole-record question's issues (ask.issue_query). lucene_query is unchanged."""

import pytest

from app import ask, search


def test_stop_words_go_and_the_rest_are_ored():
    assert search.question_query("What are the reasons for opposition to the carbon tax?") == \
        "(opposition opposition* oppos*) (carbon carbon*) (tax tax*)"


def test_a_common_ending_is_also_taken_off():
    """No stemmer in the indexes: "opposing" must also find "oppose" and "opposed"."""
    assert search.question_query("approvals amendments") == \
        "(approvals approvals* approval*) (amendments amendments* amendment*)"
    assert search.question_query("tax veto rule") == "(tax tax*) (veto veto*) (rule rule*)"


def test_words_about_the_record_itself_find_nothing():
    """The walk of 26 October: "solutions" picked the issues whose names say solutions."""
    assert search.question_query("What reasons do people give for opposing solutions?") == "(opposing opposing* oppos*)"
    assert search.question_query("Which evidence here is most supported by other evidence?") == \
        "(supported supported* support*)"


def test_the_issues_search_box_still_needs_every_word():
    assert search.lucene_query("carbon tax") == "+(carbon carbon*) +(tax tax*)"


def test_punctuation_around_a_word_is_dropped_and_repeats_are_kept_once():
    assert search.question_query('"Veto," veto; (veto) ... veto?!') == "(veto veto*)"
    assert search.question_query("Who's opposing it, and why?") == "(opposing opposing* oppos*)"


@pytest.mark.parametrize("typed, query", [
    ("a:b", "(a\\:b a\\:b*)"),
    ("c++ rules", "(rules rules* rule*)"),  # one character left: dropped
    ("c#++x", "(c#\\+\\+x c#\\+\\+x*)"),
    ("sub-issue", "(sub\\-issue sub\\-issue*)"),
    ("path/to", "(path\\/to path\\/to*)"),
    ("back\\slash", "(back\\\\slash back\\\\slash*)"),
    ("x^3 ~fuzzy", "(x\\^3 x\\^3*) (fuzzy fuzzy*)"),
    ("AND OR NOT veto", "(veto veto*)"),
    ("ho*ing", "(ho\\*ing ho\\*ing*)"),
])
def test_everything_left_is_escaped(typed, query):
    assert search.question_query(typed) == query


@pytest.mark.parametrize("typed", ["", "   ", "?", "What is it?", "Why? How? Who?", "!!! ???", "&& ||"])
def test_nothing_to_look_for(typed):
    assert search.question_query(typed) is None


def test_ten_words_at_most_from_five_hundred_characters():
    assert search.question_query(" ".join(f"word{n}" for n in range(30))).count("*") == 10
    late = "the " * 120 + "climate"  # 480 characters of stop words, then a word
    assert search.question_query(late) == "(climate climate*)"
    assert search.question_query("the " * 130 + "climate") is None


@pytest.mark.parametrize("question, query", [
    # John, 29 October: the names found the evidence and solutions named after the documents, and the
    # three issues read were about supreme law, not climate.
    ("How does the issue of climate change relate to the principles of the Universal Declaration of Human "
     "Rights and the Earth Charter?",
     "(climate climate*) (change change*) (relate relate*) (principles principles* principl*)"),
    ("How does the carbon tax fit the UDHR?", "(carbon carbon*) (tax tax*) (fit fit*)"),
    ("How does the carbon tax fit the statement of purpose?", "(carbon carbon*) (tax tax*) (fit fit*)"),
    ("How does the carbon tax fit the guiding documents?", "(carbon carbon*) (tax tax*) (fit fit*)"),
])
def test_a_guiding_documents_name_does_not_pick_the_issues(question, query):
    assert ask.issue_query(question) == query


@pytest.mark.parametrize("question", [
    "What does the Earth Charter say?",  # nothing else to look for: the whole question, as before
    "What does the UN Charter say about the veto?",  # not a guiding document
    "Who opposes the carbon tax and why?",
])
def test_otherwise_the_whole_question_is_searched_as_before(question):
    assert ask.issue_query(question) == search.question_query(question)
