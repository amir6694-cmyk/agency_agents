"""Reading one JSON object into a record: unknown fields are named, required ones enforced, values typed."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional, Type

from property_scout.fields import MAX_NUMBER, Check, InputError, _shown

_CURRENCY = re.compile(r"[A-Za-z]{3}")
# ISO 8601 or MetaTrader's export form (2026.11.20 14:00), with an optional offset.
_INSTANT = re.compile(
    r"(\d{4})[-.](\d{2})[-.](\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?"
)


class Reader:
    def __init__(self, data: Any, allowed: Iterable[str], required: Iterable[str], error: Type[InputError], where: str):
        if not isinstance(data, dict) or not all(isinstance(key, str) for key in data):
            raise error(f"{where} must be a JSON object, got {_shown(data)}")
        allowed = list(allowed)
        unknown = sorted(set(data) - set(allowed))
        if unknown:
            raise error(f"{where}: unknown field {', '.join(unknown)}; the fields are {', '.join(allowed)}")
        missing = [name for name in required if data.get(name) is None]
        if missing:
            raise error(f"{where}: {', '.join(missing)} is required")
        self.data = data
        self.check = Check(error, where)

    def get(self, name: str) -> Any:
        return self.data.get(name)

    def number(self, name: str, low: float = 0.0, high: float = MAX_NUMBER, open_low: bool = True) -> Optional[float]:
        return self.check.number(name, self.data.get(name), low, high, open_low)

    def signed(self, name: str) -> Optional[float]:
        return self.check.number(name, self.data.get(name), -MAX_NUMBER, MAX_NUMBER, open_low=False)

    def integer(self, name: str, low: int, high: int) -> Optional[int]:
        return self.check.integer(name, self.data.get(name), low, high)

    def text(self, name: str) -> str:
        return self.check.text(name, self.data.get(name))

    def name(self, name: str) -> str:
        value = self.check.text(name, self.data.get(name))
        if not value:
            raise self.check.fail(name, "must not be empty", self.data.get(name))
        return value

    def choice(self, name: str, allowed) -> Optional[str]:
        value = self.data.get(name)
        return None if value is None else self.check.choice(name, value, allowed)

    def currency(self, name: str) -> Optional[str]:
        value = self.data.get(name)
        if value is None:
            return None
        if not isinstance(value, str) or not _CURRENCY.fullmatch(value):
            raise self.check.fail(name, "must be a three-letter currency code such as USD", value)
        return value.upper()

    def instant(self, name: str) -> Optional[datetime]:
        value = self.data.get(name)
        if value is None:
            return None
        match = _INSTANT.fullmatch(value) if isinstance(value, str) else None
        if match:
            year, month, day, hour, minute, second, offset = match.groups()
            try:
                moment = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second or 0))
            except ValueError:
                match = None
            else:
                return moment.replace(tzinfo=_zone(offset)) if offset else moment
        raise self.check.fail(name, "must be a date and time written YYYY-MM-DD HH:MM, with an optional offset", value)


def _zone(offset: str) -> timezone:
    if offset == "Z":
        return timezone.utc
    sign = 1 if offset[0] == "+" else -1
    digits = offset[1:].replace(":", "")
    return timezone(sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:])))


def one_clock(moments: Iterable[datetime], error: Type[InputError], what: str) -> None:
    """Times with and without an offset cannot be put in order against each other."""
    aware = {moment.tzinfo is not None for moment in moments}
    if len(aware) > 1:
        raise error(f"{what}: give every time with an offset or none of them; they cannot be ordered otherwise")
