"""Acquisition costs by emirate, from the fee schedules each land department publishes.

Covers what a buyer customarily pays to register a purchase, plus the agency
commission where it is regulated or settled custom. Lender arrangement and
valuation fees, developer NOC and admin charges vary case by case and are left
for the agent to quote separately. Rates were read from official pages on
2026-11-19; an emirate marked indicative publishes only part of its schedule.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .messages import Note

RATES_AS_OF = "2026-11"
VAT = 0.05
GOLDEN_VISA_MIN_AED = 2_000_000
LTV_CAP_OFFPLAN = 0.50
LTV_CAP_INVESTMENT = 0.60
LTV_CAP_HOME = 0.80
LTV_CAP_HOME_ABOVE_THRESHOLD = 0.70
LTV_HOME_THRESHOLD_AED = 5_000_000


@dataclass(frozen=True)
class Schedule:
    transfer_rate: float
    fixed_ready: float
    fixed_offplan: float
    official: bool
    transfer_rate_gcc: Optional[float] = None
    transfer_minimum: float = 0.0
    transfer_minimum_gcc: float = 0.0
    trustee_tiers: Tuple[Tuple[float, float], ...] = ()
    trustee_offplan_resale: float = 0.0
    agency_rate: Optional[float] = None
    agency_cap: Optional[float] = None
    mortgage_rate: Optional[float] = None
    mortgage_fixed: float = 0.0


SCHEDULES: Dict[str, Schedule] = {
    # DLD: 4% (the buyer customarily bears both halves), title deed 250 + unit map 250 + 10 + 10,
    # trustee 4,000 or 2,000 plus VAT; Oqood 4% + 10 + 10; mortgage 0.25% + 250 + 10 + 10.
    "dubai": Schedule(
        transfer_rate=0.04,
        fixed_ready=520,
        fixed_offplan=20,
        official=True,
        trustee_tiers=((500_000, 2_000), (float("inf"), 4_000)),
        trustee_offplan_resale=5_000,
        agency_rate=0.02,
        mortgage_rate=0.0025,
        mortgage_fixed=270,
    ),
    # DARI: 2% of contract value + 875; commission 2% capped at 500,000; mortgage 0.1% + 450 + VAT.
    "abu_dhabi": Schedule(
        transfer_rate=0.02,
        fixed_ready=875,
        fixed_offplan=875,
        official=True,
        agency_rate=0.02,
        agency_cap=500_000,
        mortgage_rate=0.001,
        mortgage_fixed=450 * (1 + VAT),
    ),
    # Executive Council Decision 37/2024: buyer 4%, or 2% for UAE and GCC nationals.
    "sharjah": Schedule(
        transfer_rate=0.04,
        transfer_rate_gcc=0.02,
        fixed_ready=500,
        fixed_offplan=500,
        official=False,
    ),
    # RAK Municipality: 2% from the buyer on market value, plan 200 + title deed 200.
    "ras_al_khaimah": Schedule(transfer_rate=0.02, fixed_ready=400, fixed_offplan=400, official=True),
    # Ajman: 3% for non-citizens (minimum 3,000), 2% for UAE and GCC nationals (minimum 2,500), deed 350.
    "ajman": Schedule(
        transfer_rate=0.03,
        transfer_rate_gcc=0.02,
        transfer_minimum=3_000,
        transfer_minimum_gcc=2_500,
        fixed_ready=350,
        fixed_offplan=350,
        official=False,
    ),
}


@dataclass
class CostItem:
    note: Note
    amount: float


@dataclass
class CostBreakdown:
    price: float
    items: List[CostItem] = field(default_factory=list)
    rates_known: bool = True
    official: bool = True
    loan: float = 0.0

    @property
    def total_costs(self) -> float:
        return sum(item.amount for item in self.items)

    @property
    def total_outlay(self) -> float:
        return self.price + self.total_costs

    @property
    def upfront_cash(self) -> float:
        """Own funds needed: fees cannot be financed, so they sit on top of the down payment."""
        return self.total_outlay - self.loan


def ltv_cap(price: float, completion: Optional[str], investment: bool) -> float:
    """Central Bank ceiling for an expatriate borrower; UAE nationals get five points more."""
    if completion == "offplan":
        return LTV_CAP_OFFPLAN
    if investment:
        return LTV_CAP_INVESTMENT
    return LTV_CAP_HOME if price <= LTV_HOME_THRESHOLD_AED else LTV_CAP_HOME_ABOVE_THRESHOLD


def _trustee_fee(schedule: Schedule, price: float, offplan: bool) -> float:
    if offplan:
        return schedule.trustee_offplan_resale * (1 + VAT)
    for ceiling, fee in schedule.trustee_tiers:
        if price < ceiling:
            return fee * (1 + VAT)
    return 0.0


def acquisition_costs(
    price: float,
    emirate: Optional[str],
    completion: Optional[str],
    sale_type: Optional[str],
    financing: str = "cash",
    loan_to_value: Optional[float] = None,
    gcc_national: bool = False,
    transfer_fee_waived: bool = False,
) -> CostBreakdown:
    schedule = SCHEDULES.get(emirate or "")
    if schedule is None:
        return CostBreakdown(price=price, rates_known=False, official=False)
    primary = sale_type == "primary"
    offplan = completion == "offplan"
    rate = schedule.transfer_rate
    minimum = schedule.transfer_minimum
    if gcc_national and schedule.transfer_rate_gcc is not None:
        rate = schedule.transfer_rate_gcc
        minimum = schedule.transfer_minimum_gcc
    if transfer_fee_waived:
        items = [CostItem(Note("cost.transfer_fee_waived", {"rate": rate}), 0.0)]
    else:
        items = [CostItem(Note("cost.transfer_fee", {"rate": rate}), max(price * rate, minimum))]
    fixed = schedule.fixed_offplan if offplan else schedule.fixed_ready
    if fixed:
        items.append(CostItem(Note("cost.registration_fee"), fixed))
    if not primary:
        trustee = _trustee_fee(schedule, price, offplan)
        if trustee:
            items.append(CostItem(Note("cost.trustee_fee"), trustee))
        if schedule.agency_rate:
            commission = price * schedule.agency_rate
            if schedule.agency_cap:
                commission = min(commission, schedule.agency_cap)
            items.append(CostItem(Note("cost.agency_fee", {"rate": schedule.agency_rate}), commission * (1 + VAT)))
    loan = 0.0
    if financing == "mortgage" and loan_to_value and not offplan:
        loan = price * loan_to_value
        if schedule.mortgage_rate:
            amount = loan * schedule.mortgage_rate + schedule.mortgage_fixed
            items.append(CostItem(Note("cost.mortgage_registration", {"rate": schedule.mortgage_rate}), amount))
    return CostBreakdown(price=price, items=items, official=schedule.official, loan=loan)
