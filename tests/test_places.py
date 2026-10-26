"""Phase 3: the country list, country_code() and a town or area (app/places.py). No I/O."""

import pytest

from app import places


def test_every_iso_country_once_with_a_two_letter_code():
    assert len(places.COUNTRIES) == 249
    assert all(len(code) == 2 and code.isupper() for code in places.COUNTRIES)
    assert len(set(places.COUNTRIES.values())) == 249


def test_the_list_runs_a_to_z_by_name_with_accents_in_their_place():
    names = [name for _, name in places.choices()]
    assert names[:3] == ["Afghanistan", "Åland Islands", "Albania"]
    assert names[-1] == "Zimbabwe"
    assert names.index("Côte d'Ivoire") < names.index("Croatia")
    assert len(names) == 249


def test_no_dashes_in_the_names_people_read():
    for name in [places.NOT_ONE_PLACE, *places.COUNTRIES.values()]:
        assert "–" not in name and "—" not in name and " - " not in name


@pytest.mark.parametrize("text, code", [
    ("Germany", "DE"), ("germany ", "DE"), ("DE", "DE"), ("de", "DE"),
    ("United States", "US"), ("USA", "US"), ("U.S.A.", "US"), ("US", "US"), ("United States of America", "US"),
    ("America", "US"), ("UK", "GB"), ("U.K.", "GB"), ("Great Britain", "GB"), ("England", "GB"),
    ("Scotland", "GB"), ("the Netherlands", "NL"), ("Holland", "NL"), ("The Bahamas", "BS"), ("The Gambia", "GM"),
    ("Côte d’Ivoire", "CI"), ("Cote d'Ivoire", "CI"), ("Ivory Coast", "CI"), ("Turkey", "TR"), ("Türkiye", "TR"),
    ("Turkiye", "TR"), ("Czech Republic", "CZ"), ("Russian Federation", "RU"), ("South Korea", "KR"),
    ("North Korea", "KP"), ("DRC", "CD"), ("Democratic Republic of the Congo", "CD"), ("Congo", "CG"),
    ("Burma", "MM"), ("Viet Nam", "VN"), ("UAE", "AE"), ("Aland Islands", "AX"), ("Curacao", "CW"),
])
def test_country_code_reads_the_usual_ways_of_writing_a_country(text, code):
    assert places.country_code(text) == code


@pytest.mark.parametrize("text", [None, "", "   ", "Korea", "Deutschland", "Narnia", "Europe", "St. Louis"])
def test_country_code_is_none_for_what_it_cannot_be_sure_of(text):
    assert places.country_code(text) is None


def test_every_alias_names_a_country_in_the_list():
    assert set(places.ALIASES.values()) <= set(places.COUNTRIES)


def test_a_town_or_area_is_cleaned_like_a_name_and_cut_to_80_characters():
    assert places.clean_area("  st. louis\n") == "St. louis"
    assert places.clean_area("Berlin Kreuzberg.") == "Berlin Kreuzberg"
    assert places.clean_area("x" * 200) == "X" + "x" * 79
    assert places.clean_area("") is None and places.clean_area("  \n ") is None and places.clean_area(None) is None


def test_two_spellings_of_one_town_share_a_key():
    assert places.area_key("St. Louis") == places.area_key("st louis") == "st louis"
    assert places.area_key(None) is None and places.area_key("") is None


def test_the_line_under_a_post():
    assert places.place_text("US", "St. Louis") == "St. Louis, United States"
    assert places.place_text("de", None) == "Germany"
    assert places.place_text(None, None) is None
    assert places.place_text(None, "St. Louis") is None
    assert places.place_text("ZZ", "Somewhere") is None
