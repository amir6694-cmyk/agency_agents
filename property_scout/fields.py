"""Type checks for JSON an agent wrote from web pages: a wrong value is named, never guessed."""

import math
import re
from datetime import date
from typing import Any, Dict, List, Optional, Type

MAX_TEXT = 600
_CONTROL = re.compile("[\x00-\x1f\x7f\u2028\u2029]")
_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$")


class InputError(ValueError):
    pass


class Check:
    def __init__(self, error: Type[InputError], where: str):
        self.error = error
        self.where = where

    def fail(self, name: str, problem: str, value: Any) -> InputError:
        return self.error(f"{self.where}: {name} {problem}, got {value!r}")

    def text(self, name: str, value: Any) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise self.fail(name, "must be text", value)
        if _CONTROL.search(value):
            raise self.fail(name, "must be one line of text without control characters", value)
        if len(value) > MAX_TEXT:
            raise self.error(f"{self.where}: {name} is longer than {MAX_TEXT} characters")
        return value.strip()

    def number(self, name: str, value: Any, low: float = 0.0, high: float = math.inf, open_low: bool = True) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise self.fail(name, "must be a number, not text", value)
        if not math.isfinite(value) or value > high or value < low or (open_low and value == low):
            sign = ">" if open_low else ">="
            limit = f" and <= {high:g}" if math.isfinite(high) else ""
            raise self.fail(name, f"must be a number {sign} {low:g}{limit}", value)
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
        match = _ISO_DATE.match(value) if isinstance(value, str) else None
        if match:
            try:
                return date(*(int(part) for part in match.groups())).isoformat()
            except ValueError:
                pass
        raise self.fail(name, "must be a date written YYYY-MM-DD", value)
