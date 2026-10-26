"""Phase 3: a place on each post. The country list (ISO 3166 two-letter codes, English short names),
country_code() for what an account's free-text country says, and cleaning a town or area. No I/O."""

from __future__ import annotations

import unicodedata

from app.text import clean_name, make_key, normalise

# Client facing: the first choice in the Place list (04_interface.md, "A place on the card").
NOT_ONE_PLACE = "Not about one place"
AREA_MAX = 80

COUNTRIES: dict[str, str] = {
    "AF": "Afghanistan", "AX": "Åland Islands", "AL": "Albania", "DZ": "Algeria", "AS": "American Samoa",
    "AD": "Andorra", "AO": "Angola", "AI": "Anguilla", "AQ": "Antarctica", "AG": "Antigua and Barbuda",
    "AR": "Argentina", "AM": "Armenia", "AW": "Aruba", "AU": "Australia", "AT": "Austria", "AZ": "Azerbaijan",
    "BS": "Bahamas", "BH": "Bahrain", "BD": "Bangladesh", "BB": "Barbados", "BY": "Belarus", "BE": "Belgium",
    "BZ": "Belize", "BJ": "Benin", "BM": "Bermuda", "BT": "Bhutan", "BO": "Bolivia",
    "BQ": "Bonaire, Sint Eustatius and Saba", "BA": "Bosnia and Herzegovina", "BW": "Botswana",
    "BV": "Bouvet Island", "BR": "Brazil", "IO": "British Indian Ocean Territory", "BN": "Brunei",
    "BG": "Bulgaria", "BF": "Burkina Faso", "BI": "Burundi", "CV": "Cabo Verde", "KH": "Cambodia",
    "CM": "Cameroon", "CA": "Canada", "KY": "Cayman Islands", "CF": "Central African Republic", "TD": "Chad",
    "CL": "Chile", "CN": "China", "CX": "Christmas Island", "CC": "Cocos (Keeling) Islands", "CO": "Colombia",
    "KM": "Comoros", "CG": "Congo", "CD": "Democratic Republic of the Congo", "CK": "Cook Islands",
    "CR": "Costa Rica", "CI": "Côte d'Ivoire", "HR": "Croatia", "CU": "Cuba", "CW": "Curaçao", "CY": "Cyprus",
    "CZ": "Czechia", "DK": "Denmark", "DJ": "Djibouti", "DM": "Dominica", "DO": "Dominican Republic",
    "EC": "Ecuador", "EG": "Egypt", "SV": "El Salvador", "GQ": "Equatorial Guinea", "ER": "Eritrea",
    "EE": "Estonia", "SZ": "Eswatini", "ET": "Ethiopia", "FK": "Falkland Islands", "FO": "Faroe Islands",
    "FJ": "Fiji", "FI": "Finland", "FR": "France", "GF": "French Guiana", "PF": "French Polynesia",
    "TF": "French Southern Territories", "GA": "Gabon", "GM": "Gambia", "GE": "Georgia", "DE": "Germany",
    "GH": "Ghana", "GI": "Gibraltar", "GR": "Greece", "GL": "Greenland", "GD": "Grenada", "GP": "Guadeloupe",
    "GU": "Guam", "GT": "Guatemala", "GG": "Guernsey", "GN": "Guinea", "GW": "Guinea-Bissau", "GY": "Guyana",
    "HT": "Haiti", "HM": "Heard Island and McDonald Islands", "VA": "Holy See", "HN": "Honduras",
    "HK": "Hong Kong", "HU": "Hungary", "IS": "Iceland", "IN": "India", "ID": "Indonesia", "IR": "Iran",
    "IQ": "Iraq", "IE": "Ireland", "IM": "Isle of Man", "IL": "Israel", "IT": "Italy", "JM": "Jamaica",
    "JP": "Japan", "JE": "Jersey", "JO": "Jordan", "KZ": "Kazakhstan", "KE": "Kenya", "KI": "Kiribati",
    "KP": "North Korea", "KR": "South Korea", "KW": "Kuwait", "KG": "Kyrgyzstan", "LA": "Laos", "LV": "Latvia",
    "LB": "Lebanon", "LS": "Lesotho", "LR": "Liberia", "LY": "Libya", "LI": "Liechtenstein", "LT": "Lithuania",
    "LU": "Luxembourg", "MO": "Macao", "MG": "Madagascar", "MW": "Malawi", "MY": "Malaysia", "MV": "Maldives",
    "ML": "Mali", "MT": "Malta", "MH": "Marshall Islands", "MQ": "Martinique", "MR": "Mauritania",
    "MU": "Mauritius", "YT": "Mayotte", "MX": "Mexico", "FM": "Micronesia", "MD": "Moldova", "MC": "Monaco",
    "MN": "Mongolia", "ME": "Montenegro", "MS": "Montserrat", "MA": "Morocco", "MZ": "Mozambique",
    "MM": "Myanmar", "NA": "Namibia", "NR": "Nauru", "NP": "Nepal", "NL": "Netherlands", "NC": "New Caledonia",
    "NZ": "New Zealand", "NI": "Nicaragua", "NE": "Niger", "NG": "Nigeria", "NU": "Niue", "NF": "Norfolk Island",
    "MK": "North Macedonia", "MP": "Northern Mariana Islands", "NO": "Norway", "OM": "Oman", "PK": "Pakistan",
    "PW": "Palau", "PS": "Palestine", "PA": "Panama", "PG": "Papua New Guinea", "PY": "Paraguay", "PE": "Peru",
    "PH": "Philippines", "PN": "Pitcairn", "PL": "Poland", "PT": "Portugal", "PR": "Puerto Rico", "QA": "Qatar",
    "RE": "Réunion", "RO": "Romania", "RU": "Russia", "RW": "Rwanda", "BL": "Saint Barthélemy",
    "SH": "Saint Helena, Ascension and Tristan da Cunha", "KN": "Saint Kitts and Nevis", "LC": "Saint Lucia",
    "MF": "Saint Martin (French part)", "PM": "Saint Pierre and Miquelon",
    "VC": "Saint Vincent and the Grenadines", "WS": "Samoa", "SM": "San Marino", "ST": "Sao Tome and Principe",
    "SA": "Saudi Arabia", "SN": "Senegal", "RS": "Serbia", "SC": "Seychelles", "SL": "Sierra Leone",
    "SG": "Singapore", "SX": "Sint Maarten (Dutch part)", "SK": "Slovakia", "SI": "Slovenia",
    "SB": "Solomon Islands", "SO": "Somalia", "ZA": "South Africa",
    "GS": "South Georgia and the South Sandwich Islands", "SS": "South Sudan", "ES": "Spain", "LK": "Sri Lanka",
    "SD": "Sudan", "SR": "Suriname", "SJ": "Svalbard and Jan Mayen", "SE": "Sweden", "CH": "Switzerland",
    "SY": "Syria", "TW": "Taiwan", "TJ": "Tajikistan", "TZ": "Tanzania", "TH": "Thailand", "TL": "Timor-Leste",
    "TG": "Togo", "TK": "Tokelau", "TO": "Tonga", "TT": "Trinidad and Tobago", "TN": "Tunisia", "TR": "Türkiye",
    "TM": "Turkmenistan", "TC": "Turks and Caicos Islands", "TV": "Tuvalu", "UG": "Uganda", "UA": "Ukraine",
    "AE": "United Arab Emirates", "GB": "United Kingdom", "US": "United States",
    "UM": "United States Minor Outlying Islands", "UY": "Uruguay", "UZ": "Uzbekistan", "VU": "Vanuatu",
    "VE": "Venezuela", "VN": "Vietnam", "VG": "Virgin Islands (British)", "VI": "Virgin Islands (U.S.)",
    "WF": "Wallis and Futuna", "EH": "Western Sahara", "YE": "Yemen", "ZM": "Zambia", "ZW": "Zimbabwe",
}

# Other ways people write a country, by their normalised form. Ambiguous words ("Korea", "Congo" for the
# Democratic Republic, "Virgin Islands") are left out: the account's country only prefills the list.
ALIASES: dict[str, str] = {
    "usa": "US", "u s a": "US", "u s": "US", "america": "US", "united states of america": "US",
    "uk": "GB", "u k": "GB", "great britain": "GB", "britain": "GB", "england": "GB", "scotland": "GB",
    "wales": "GB", "northern ireland": "GB", "united kingdom of great britain and northern ireland": "GB",
    "russian federation": "RU", "republic of korea": "KR", "korea republic of": "KR",
    "democratic people s republic of korea": "KP", "drc": "CD", "dr congo": "CD",
    "republic of the congo": "CG", "congo brazzaville": "CG", "congo kinshasa": "CD", "ivory coast": "CI",
    "czech republic": "CZ", "holland": "NL", "burma": "MM", "swaziland": "SZ", "macedonia": "MK", "turkey": "TR",
    "cape verde": "CV", "east timor": "TL", "vatican": "VA", "vatican city": "VA", "uae": "AE",
    "u a e": "AE", "viet nam": "VN", "lao people s democratic republic": "LA", "syrian arab republic": "SY",
    "iran islamic republic of": "IR", "bolivia plurinational state of": "BO", "brunei darussalam": "BN",
    "moldova republic of": "MD", "republic of moldova": "MD", "tanzania united republic of": "TZ",
    "united republic of tanzania": "TZ", "venezuela bolivarian republic of": "VE",
    "micronesia federated states of": "FM", "state of palestine": "PS", "palestine state of": "PS",
    "sao tome": "ST", "st kitts and nevis": "KN", "st lucia": "LC",
    "st vincent and the grenadines": "VC", "taiwan province of china": "TW", "hong kong sar": "HK",
    "macau": "MO",
}



def _fold(text: str) -> str:
    """normalise() without accents, so "Cote d'Ivoire" and "Côte d’Ivoire" are one."""
    decomposed = unicodedata.normalize("NFKD", text)
    return normalise("".join(ch for ch in decomposed if not unicodedata.combining(ch)))


# Name to code, from every name above and the codes themselves.
_BY_NAME: dict[str, str] = {
    **{_fold(code): code for code in COUNTRIES},
    **{_fold(name): code for code, name in COUNTRIES.items()},
    **ALIASES,
}


def choices() -> list[tuple[str, str]]:
    """The countries A to Z by name, as (code, name), for the Place list after "Not about one place"."""
    return sorted(COUNTRIES.items(), key=lambda item: _fold(item[1]))


def country_code(text: str | None) -> str | None:
    """The two-letter code for a country as someone wrote it ("USA", "the Netherlands", "de"), or None."""
    words = _fold(text or "")
    return _BY_NAME.get(words) or _BY_NAME.get(words.removeprefix("the ")) if words else None


def country_name(code: str | None) -> str | None:
    return COUNTRIES.get((code or "").upper()) if code else None


def clean_area(text: str | None) -> str | None:
    """A town or area as typed, tidied like any name and cut to 80 characters; None when empty."""
    area = clean_name(text or "")[:AREA_MAX].strip()
    return area or None


def area_key(area: str | None) -> str | None:
    """The form two towns or areas match in ("St. Louis" and "st louis" are one)."""
    return make_key(area) if area else None


def place_text(code: str | None, area: str | None) -> str | None:
    """"St. Louis, United States", "Germany", or None when the post has no place."""
    country = country_name(code)
    if not country:
        return None
    return f"{area}, {country}" if area else country
