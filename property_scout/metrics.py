"""Derived figures for one listing: price per sqft, benchmark gap, yields, payment-plan value."""

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from .listing import Listing
from .text import months_until


@dataclass
class PlanValue:
    present_value_ratio: float
    deferral_benefit: float
    paid_before_handover_pct: float
    months_to_handover: int


def benchmark_gap(listing: Listing) -> Optional[float]:
    """Asking price per sqft relative to the benchmark; negative means below it."""
    if listing.price_psf is None or listing.benchmark_psf is None:
        return None
    return listing.price_psf / listing.benchmark_psf - 1


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


def _months_to_handover(listing: Listing, today: date) -> Optional[int]:
    """Zero for a finished unit; unknown for an unbuilt one whose plan defers money to an undated handover."""
    if listing.handover:
        return max(months_until(listing.handover, today), 0)
    deferred = any(listing.payment_plan.get(stage) for stage in ("during_construction", "on_handover", "post_handover"))
    if deferred and listing.completion != "ready":
        return None
    return 0


def plan_cashflows(listing: Listing, today: date) -> Optional[List[Tuple[int, float]]]:
    """Payment plan as (months from today, share of price). Instalments are spread evenly."""
    plan = listing.payment_plan
    if not plan:
        return None
    months = _months_to_handover(listing, today)
    if months is None:
        return None
    flows: List[Tuple[int, float]] = []
    if plan.get("on_booking"):
        flows.append((0, plan["on_booking"] / 100))
    during = plan.get("during_construction", 0) / 100
    if during:
        if months == 0:
            flows.append((0, during))
        else:
            flows.extend((m, during / months) for m in range(1, months + 1))
    if plan.get("on_handover"):
        flows.append((months, plan["on_handover"] / 100))
    post = plan.get("post_handover", 0) / 100
    if post:
        span = listing.post_handover_months
        flows.extend((months + m, post / span) for m in range(1, span + 1))
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
        paid_before_handover_pct=plan.get("on_booking", 0) + plan.get("during_construction", 0),
        months_to_handover=_months_to_handover(listing, today) or 0,
    )
