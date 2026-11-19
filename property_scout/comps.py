"""Benchmark from raw comparable rows: the median, not a portal's headline average."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Any, Dict, List, Optional

from .text import completion_slug

SIZE_BAND = 0.20
MIN_COMPS = 5


class CompsError(ValueError):
    pass


@dataclass
class CompSummary:
    used: int
    dropped: Dict[str, int]
    median_psf: Optional[float]
    low_psf: Optional[float]
    high_psf: Optional[float]
    median_price: Optional[float]
    thin: bool


def _months_back(today: date, months: int) -> date:
    index = today.year * 12 + today.month - 1 - months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(today.day, monthrange(year, month + 1)[1]))


def summarise(
    rows: List[Dict[str, Any]],
    today: date,
    subject_size_sqft: Optional[float] = None,
    months: int = 3,
    completion: Optional[str] = None,
) -> CompSummary:
    """Median price per sqft of the rows that are comparable to the subject.

    Each row needs price_aed and size_sqft; date (ISO) and completion are used
    when present. Rows outside the size band, the look-back window or the wanted
    completion status are dropped and counted, so the caller can report them.
    """
    wanted = completion_slug(completion) if completion else None
    earliest = _months_back(today, months)
    dropped = {"incomplete": 0, "size": 0, "date": 0, "completion": 0}
    psf: List[float] = []
    prices: List[float] = []
    for row in rows:
        if not isinstance(row, dict):
            raise CompsError("each comparable must be a JSON object")
        price, size = row.get("price_aed"), row.get("size_sqft")
        if not price or not size or price <= 0 or size <= 0:
            dropped["incomplete"] += 1
            continue
        if subject_size_sqft and abs(size - subject_size_sqft) > SIZE_BAND * subject_size_sqft:
            dropped["size"] += 1
            continue
        if row.get("date") and date.fromisoformat(row["date"]) < earliest:
            dropped["date"] += 1
            continue
        if wanted and row.get("completion") and completion_slug(row["completion"]) != wanted:
            dropped["completion"] += 1
            continue
        psf.append(price / size)
        prices.append(price)
    if not psf:
        return CompSummary(0, dropped, None, None, None, None, thin=True)
    return CompSummary(
        used=len(psf),
        dropped=dropped,
        median_psf=median(psf),
        low_psf=min(psf),
        high_psf=max(psf),
        median_price=median(prices),
        thin=len(psf) < MIN_COMPS,
    )
