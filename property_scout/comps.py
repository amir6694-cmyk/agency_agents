"""Benchmark from raw comparable rows: the median, not a portal's headline average."""

from calendar import monthrange
from collections import Counter
from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Any, Dict, List, Optional, Sequence

from .fields import Check, InputError
from .text import completion_slug, norm

SIZE_BAND = 0.20
MIN_COMPS = 5
CONCENTRATION_LIMIT = 0.5
FULL_YEAR_MONTHS = 12


class CompsError(InputError):
    pass


@dataclass
class CompSummary:
    used: int
    dropped: Dict[str, int]
    median_psf: Optional[float]
    low_psf: Optional[float]
    high_psf: Optional[float]
    median_price: Optional[float]
    first_date: Optional[str]
    last_date: Optional[str]
    largest_project_share: Optional[float]
    thin: bool

    projects: int = 0

    @property
    def concentrated(self) -> bool:
        """One project among several supplies most of the rows; a single-building benchmark is not concentrated."""
        return self.projects > 1 and self.largest_project_share > CONCENTRATION_LIMIT


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
    new_leases: bool = False,
    exclude_projects: Sequence[str] = (),
) -> CompSummary:
    """Median of the rows that are comparable to the subject.

    A row needs price_aed and size_sqft; date, completion, project, contract and
    term_months are used when present. Rows outside the size band, the look-back
    window or the wanted completion status are dropped and counted, as are
    renewals and short lets when only new twelve-month leases are wanted. A row
    dated after the valuation date is a mistyped one and is dropped with the old ones.
    A row that carries a reason in `excluded` (a bulk transfer, a sale between related
    parties) and a row of a project named for exclusion stay in the file and are counted as left out.
    """
    wanted = completion_slug(completion) if completion else None
    earliest = _months_back(today, months)
    unwanted = {norm(name) for name in exclude_projects}
    dropped = {"incomplete": 0, "excluded": 0, "project": 0, "size": 0, "date": 0, "completion": 0, "contract": 0}
    psf: List[float] = []
    prices: List[float] = []
    dates: List[str] = []
    projects: Counter = Counter()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise CompsError(f"row {index}: each comparable must be a JSON object")
        check = Check(CompsError, f"row {index}")
        price = check.number("price_aed", row.get("price_aed"), open_low=False)
        size = check.number("size_sqft", row.get("size_sqft"), open_low=False)
        day = check.day("date", row.get("date"))
        project = norm(check.text("project", row.get("project")))
        if not price or not size or price < 1 or size < 1:
            dropped["incomplete"] += 1
            continue
        if check.text("excluded", row.get("excluded")):
            dropped["excluded"] += 1
            continue
        if project and project in unwanted:
            dropped["project"] += 1
            continue
        if subject_size_sqft and abs(size - subject_size_sqft) > SIZE_BAND * subject_size_sqft:
            dropped["size"] += 1
            continue
        if day and not earliest <= date.fromisoformat(day) <= today:
            dropped["date"] += 1
            continue
        if wanted and row.get("completion") and completion_slug(check.text("completion", row["completion"])) != wanted:
            dropped["completion"] += 1
            continue
        if new_leases:
            renewed = norm(check.text("contract", row.get("contract"))) not in ("", "new")
            term = check.number("term_months", row.get("term_months"))
            if renewed or (term is not None and term != FULL_YEAR_MONTHS):
                dropped["contract"] += 1
                continue
        psf.append(price / size)
        prices.append(price)
        if day:
            dates.append(day)
        if project:
            projects[project] += 1
    if not psf:
        return CompSummary(0, dropped, None, None, None, None, None, None, None, thin=True)
    return CompSummary(
        used=len(psf),
        dropped=dropped,
        median_psf=median(psf),
        low_psf=min(psf),
        high_psf=max(psf),
        median_price=median(prices),
        first_date=min(dates) if dates else None,
        last_date=max(dates) if dates else None,
        largest_project_share=max(projects.values()) / len(psf) if projects else None,
        thin=len(psf) < MIN_COMPS,
        projects=len(projects),
    )
