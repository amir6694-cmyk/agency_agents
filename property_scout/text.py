"""Text and date normalisation shared by the brief, listing and matching code."""

import re
import unicodedata
from datetime import date
from typing import Optional, Tuple

_QUARTER_FIRST_MONTH = {1: 1, 2: 4, 3: 7, 4: 10}
_MONTHS = {
    name: number
    for number, names in enumerate(
        ("jan january", "feb february", "mar march", "apr april", "may", "jun june", "jul july",
         "aug august", "sep sept september", "oct october", "nov november", "dec december"),
        start=1,
    )
    for name in names.split()
}
_COMPLETION_ALIASES = {
    "off_plan": "offplan",
    "under_construction": "offplan",
    "completed": "ready",
    "secondary": "ready",
    "resale": "ready",
}
# Short forms buyers and adverts use for a community, mapped to the name portals file it under.
_PLACE_ALIASES = {
    "jvc": "jumeirah village circle",
    "jvt": "jumeirah village triangle",
    "jlt": "jumeirah lake towers",
    "jbr": "jumeirah beach residence",
    "dso": "dubai silicon oasis",
    "silicon oasis": "dubai silicon oasis",
    "dip": "dubai investment park",
    "difc": "dubai international financial centre",
    "downtown": "downtown dubai",
    "marina": "dubai marina",
    "the palm": "palm jumeirah",
    "palm": "palm jumeirah",
    "dubai hills": "dubai hills estate",
    "creek harbour": "dubai creek harbour",
    "sports city": "dubai sports city",
    "mbr city": "mohammed bin rashid city",
    "al reem": "al reem island",
    "reem island": "al reem island",
    "al maryah": "al maryah island",
    "maryah island": "al maryah island",
    "yas": "yas island",
    "saadiyat": "saadiyat island",
    "al marjan": "al marjan island",
    "marjan island": "al marjan island",
}


def norm(value: Optional[str]) -> str:
    """Lower-case letters and digits of any script, accents and punctuation removed."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    kept = "".join(ch if ch.isalnum() else " " for ch in decomposed.casefold() if not unicodedata.combining(ch))
    return " ".join(kept.split())


def slug(value: Optional[str]) -> str:
    return norm(value).replace(" ", "_")


def completion_slug(value: str) -> str:
    key = slug(value)
    return _COMPLETION_ALIASES.get(key, key)


def place(value: Optional[str]) -> str:
    key = norm(value)
    return _PLACE_ALIASES.get(key, key)


def same_place(a: Optional[str], b: Optional[str]) -> bool:
    return bool(place(a)) and place(a) == place(b)


def has_words(haystack: Optional[str], needle: Optional[str]) -> bool:
    wanted = norm(needle)
    return bool(wanted) and f" {wanted} " in f" {norm(haystack)} "


def parse_period(value: str) -> Tuple[int, int, int]:
    """(year, first month, last month) of '2027-Q4', 'Q4 2027', '2027-11', 'Nov 2027', '2027-11-30' or '2027'."""
    text = " ".join(str(value).replace(",", " ").split()).upper()
    match = re.fullmatch(r"(\d{4})[-\s]?Q([1-4])", text)
    if match:
        first = _QUARTER_FIRST_MONTH[int(match.group(2))]
        return int(match.group(1)), first, first + 2
    match = re.fullmatch(r"Q([1-4])[-\s]?(\d{4})", text)
    if match:
        first = _QUARTER_FIRST_MONTH[int(match.group(1))]
        return int(match.group(2)), first, first + 2
    match = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-\d{1,2})?", text)
    if match and 1 <= int(match.group(2)) <= 12:
        return int(match.group(1)), int(match.group(2)), int(match.group(2))
    match = re.fullmatch(r"([A-Z]+)\s+(\d{4})", text)
    if match and match.group(1).lower() in _MONTHS:
        month = _MONTHS[match.group(1).lower()]
        return int(match.group(2)), month, month
    match = re.fullmatch(r"(\d{4})", text)
    if match:
        return int(match.group(1)), 1, 12
    raise ValueError(f"unrecognised period {value!r}; write it as 2027-Q4, 2027-11, Nov 2027, 2027-11-30 or 2027")


def months_until(period: str, today: date, start: bool = False) -> int:
    """Whole months from today to the end of the period, or to its start."""
    year, first, last = parse_period(period)
    return (year - today.year) * 12 + ((first if start else last) - today.month)
