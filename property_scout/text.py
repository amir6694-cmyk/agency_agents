"""Text and date normalisation shared by the brief, listing and matching code."""

import re
from datetime import date
from typing import Optional, Tuple

_QUARTER_END_MONTH = {1: 3, 2: 6, 3: 9, 4: 12}


def norm(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def slug(value: str) -> str:
    return norm(value).replace(" ", "_")


_COMPLETION_ALIASES = {
    "off_plan": "offplan",
    "under_construction": "offplan",
    "completed": "ready",
    "secondary": "ready",
    "resale": "ready",
}


def completion_slug(value: str) -> str:
    key = slug(value)
    return _COMPLETION_ALIASES.get(key, key)


def contains(haystack: Optional[str], needle: str) -> bool:
    wanted = norm(needle)
    return bool(wanted) and f" {wanted} " in f" {norm(haystack)} "


def parse_period(value: str) -> Tuple[int, int]:
    """Turn '2027-Q4', 'Q4 2027', '2027-11' or '2027' into (year, last month of the period)."""
    text = value.strip().upper()
    match = re.fullmatch(r"(\d{4})[-\s]?Q([1-4])", text)
    if match:
        return int(match.group(1)), _QUARTER_END_MONTH[int(match.group(2))]
    match = re.fullmatch(r"Q([1-4])[-\s]?(\d{4})", text)
    if match:
        return int(match.group(2)), _QUARTER_END_MONTH[int(match.group(1))]
    match = re.fullmatch(r"(\d{4})-(\d{1,2})", text)
    if match and 1 <= int(match.group(2)) <= 12:
        return int(match.group(1)), int(match.group(2))
    match = re.fullmatch(r"(\d{4})", text)
    if match:
        return int(match.group(1)), 12
    raise ValueError(f"unrecognised period {value!r}; use 2027-Q4, 2027-11 or 2027")


def months_until(period: str, today: date) -> int:
    year, month = parse_period(period)
    return (year - today.year) * 12 + (month - today.month)
