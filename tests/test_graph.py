from app.graph import person_key


def test_person_key_for_a_name_uses_the_normalised_key():
    assert person_key("John Kintree", False, "ignored") == "name:john kintree"


def test_person_key_for_anonymous_uses_the_browser_id():
    assert person_key("John Kintree", True, "1234") == "anon:1234"
