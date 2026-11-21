"""Derived figures for one listing: benchmark gap, yields, payment-plan value."""

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from .listing import Listing
from .text import months_until, parse_period, period_end


FIRST_YEAR_MONTHS = 12
# A construction share smaller than this is rounding left over once the dated instalments are taken out.
UNDATED_FLOOR = 1e-9


@dataclass
class PlanValue:
    present_value_ratio: float
    deferral_benefit: float
    booking_pct: float
    paid_before_handover_pct: float
    months_to_handover: int
    due_in_first_year: float = 0.0
    dated_pct: float = 0.0


def benchmark_gap(listing: Listing) -> Optional[float]:
    """Asking price per sqft relative to the benchmark; negative means below it."""
    if listing.price_psf is None or listing.benchmark_psf is None:
        return None
    # Rounded so that an ask exactly 20% above lands on the threshold and not a hair under it.
    return round(listing.price_psf / listing.benchmark_psf - 1, 9)


def gross_yield(listing: Listing) -> Optional[float]:
    if listing.annual_rent_aed is None:
        return None
    return listing.annual_rent_aed / listing.price_aed


def net_yield(listing: Listing, total_cost: float, running_cost_ratio: float) -> Optional[float]:
    """Rent after service charges and running costs, over everything paid to acquire."""
    if listing.annual_rent_aed is None or listing.service_charge_psf is None or not listing.size_sqft:
        return None
    service_charges = listing.service_charge_psf * listing.size_sqft
    running_costs = listing.annual_rent_aed * running_cost_ratio
    return (listing.annual_rent_aed - service_charges - running_costs) / total_cost


def expected_handover(listing: Listing, today: date) -> Optional[str]:
    """The register's date while it is still ahead, otherwise the advert's; none once every stated date has passed."""
    for period in (listing.register_completion, listing.handover):
        if period and period_end(period) >= today:
            return period
    return None


def schedule_shortfall(listing: Listing, today: date) -> Optional[Tuple[float, float]]:
    """(share of the construction period elapsed, share built), when the register gives both ends.

    Elapsed time is counted to the inspection the progress figure comes from, or to today when its date is not known.
    """
    finish = listing.register_completion or listing.handover
    if not (listing.register_started and finish and listing.register_progress_pct is not None):
        return None
    start_year, start_month, _ = parse_period(listing.register_started)
    start = date(start_year, start_month, 1)
    total = (period_end(finish) - start).days
    if total <= 0:
        return None
    measured = date.fromisoformat(listing.register_inspected_on) if listing.register_inspected_on else today
    elapsed = (measured - start).days / total
    return min(max(elapsed, 0.0), 1.0), listing.register_progress_pct / 100


def months_to_handover(listing: Listing, today: date) -> Optional[int]:
    """Counted to the start of the stated period, so a vague date cannot flatter a plan.

    Zero for a finished unit or a date that has passed; unknown for an unbuilt one whose plan defers money to an undated handover.
    """
    if listing.completion == "ready":
        # A date on a finished home is history or a slip: nothing is deferred to it.
        return 0
    if listing.scheduled_handover:
        expected = expected_handover(listing, today)
        return max(months_until(expected, today, start=True), 0) if expected else 0
    deferred = any(listing.payment_plan.get(stage) for stage in ("during_construction", "on_handover", "post_handover"))
    if deferred and listing.completion != "ready":
        return None
    return 0


def plan_cashflows(listing: Listing, today: date) -> Optional[List[Tuple[int, float]]]:
    """Payment plan as (months from today, share of price).

    Instalments the developer dates are costed on their dates, a date already passed as due now;
    the rest of the construction share is spread evenly to handover.
    """
    plan = listing.payment_plan
    if not plan:
        return None
    months = months_to_handover(listing, today)
    if months is None:
        return None
    flows: List[Tuple[int, float]] = []
    if plan.get("on_booking"):
        flows.append((0, plan["on_booking"] / 100))
    during = plan.get("during_construction", 0) / 100
    for item in listing.instalments:
        due = item["after_months"] if "after_months" in item else max(months_until(item["due"], today, start=True), 0)
        flows.append((due, item["pct"] / 100))
        during -= item["pct"] / 100
    if during > UNDATED_FLOOR:
        if months == 0:
            flows.append((0, during))
        else:
            flows.extend((m, during / months) for m in range(1, months + 1))
    if plan.get("on_handover"):
        flows.append((months, plan["on_handover"] / 100))
    post = plan.get("post_handover", 0) / 100
    span = listing.post_handover_months
    if post and span:
        flows.extend((months + m, post / span) for m in range(1, span + 1))
    elif post:
        # A post-handover share with no stated period is costed as due on handover.
        flows.append((months, post))
    return flows


def plan_value(listing: Listing, today: date, annual_rate: float) -> Optional[PlanValue]:
    flows = plan_cashflows(listing, today)
    if flows is None:
        return None
    monthly = (1 + annual_rate) ** (1 / 12) - 1
    present = sum(share / (1 + monthly) ** month for month, share in flows)
    plan = listing.payment_plan
    return PlanValue(
        present_value_ratio=present,
        deferral_benefit=1 - present,
        booking_pct=plan.get("on_booking", 0),
        paid_before_handover_pct=plan.get("on_booking", 0) + plan.get("during_construction", 0),
        months_to_handover=months_to_handover(listing, today) or 0,
        due_in_first_year=sum(share for month, share in flows if month <= FIRST_YEAR_MONTHS),
        dated_pct=sum(item["pct"] for item in listing.instalments),
    )
