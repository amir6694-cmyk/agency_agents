"""Type checks for JSON an agent wrote from web pages: a wrong value is named, never guessed."""

import math
import re
from datetime import date
from typing import Any, Dict, List, Optional, Type

MAX_TEXT = 600
LONG_TEXT = 2000
MAX_NUMBER = 1e12
MAX_SHOWN = 200
# Line breaks, control and bidirectional-override characters, and lone surrogates.
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069\ud800-\udfff]")
_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?")


class InputError(ValueError):
    pass


def _shown(value: Any) -> str:
    """A value as an error message may quote it: bounded, and safe for input nested past the interpreter's depth."""
    try:
        text = repr(value)
    except RecursionError:
        return "a deeply nested value"
    return text if len(text) <= MAX_SHOWN else text[:MAX_SHOWN] + "..."


class Check:
    def __init__(self, error: Type[InputError], where: str):
        self.error = error
        self.where = where

    def fail(self, name: str, problem: str, value: Any) -> InputError:
        return self.error(f"{self.where}: {name} {problem}, got {_shown(value)}")

    def text(self, name: str, value: Any, limit: int = MAX_TEXT) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise self.fail(name, "must be text", value)
        if _CONTROL.search(value):
            raise self.fail(name, "must be one line of text without control characters", value)
        if len(value) > limit:
            raise self.error(f"{self.where}: {name} is longer than {limit} characters")
        return value.strip()

    def number(self, name: str, value: Any, low: float = 0.0, high: float = MAX_NUMBER, open_low: bool = True) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise self.fail(name, "must be a number, not text", value)
        # An integer too large for a float cannot be tested with isfinite.
        outside = isinstance(value, int) and abs(value) > MAX_NUMBER
        if outside or not math.isfinite(value) or value > high or value < low or (open_low and value == low):
            sign = ">" if open_low else ">="
            raise self.fail(name, f"must be a number {sign} {low:g} and <= {high:g}", "a very large number" if outside else value)
        return value

    def integer(self, name: str, value: Any, low: int, high: int) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise self.fail(name, "must be a whole number", value)
        if not low <= value <= high:
            raise self.fail(name, f"must be between {low} and {high}", value)
        return value

    def boolean(self, name: str, value: Any) -> Optional[bool]:
        if value is None or isinstance(value, bool):
            return value
        raise self.fail(name, "must be true, false or null (not text)", value)

    def strings(self, name: str, value: Any) -> List[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise self.fail(name, "must be a list of text values", value)
        return [text for text in (self.text(name, item) for item in value) if text]

    def mapping(self, name: str, value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise self.fail(name, "must be an object", value)
        return value

    def choice(self, name: str, value: str, allowed) -> str:
        if value not in allowed:
            raise self.fail(name, f"must be one of {tuple(allowed)}", value)
        return value

    def day(self, name: str, value: Any) -> Optional[str]:
        if value is None or value == "":
            return None
        match = _ISO_DATE.fullmatch(value) if isinstance(value, str) else None
        if match:
            try:
                return date(*(int(part) for part in match.groups())).isoformat()
            except ValueError:
                pass
        raise self.fail(name, "must be a date written YYYY-MM-DD", value)
