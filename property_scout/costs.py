"""Acquisition costs by emirate, from the fee schedules each land department publishes.

Covers what a buyer customarily pays to register a purchase, plus agency
commission and mortgage registration where an emirate publishes them. Lender
valuation and arrangement fees, developer no-objection and admin charges vary
case by case and are never included. Rates were read from official pages on
2026-11-19 and 2026-11-20.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .messages import Note
from .text import place

RATES_AS_OF = "2026-11"
VAT = 0.05
GOLDEN_VISA_MIN_AED = 2_000_000
# Central Bank of the UAE, Regulations Regarding Mortgage Loans, article 3.
LTV_CAP_OFFPLAN = 0.50
LTV_CAP_INVESTMENT = 0.60
LTV_CAP_HOME = 0.80
LTV_CAP_HOME_ABOVE_THRESHOLD = 0.70
LTV_HOME_THRESHOLD_AED = 5_000_000
LTV_NATIONAL_UPLIFT = 0.05
REDUCED_RATE_NATIONALITIES = ("uae", "gcc")
# ADGM registers these islands; its fee rules put the transfer fee on the seller.
SELLER_PAYS_TRANSFER = {"abu_dhabi": ("al reem island", "al maryah island")}


@dataclass(frozen=True)
class Schedule:
    transfer_rate: float
    fixed_ready: float
    fixed_offplan: float
    complete: bool
    transfer_rate_reduced: Optional[float] = None
    transfer_minimum: float = 0.0
    transfer_minimum_reduced: float = 0.0
    trustee_tiers: Tuple[Tuple[float, float], ...] = ()
    agency_rate: Optional[float] = None
    agency_cap: Optional[float] = None
    mortgage_rate: Optional[float] = None
    mortgage_fixed: float = 0.0
    split_by_default: bool = False


SCHEDULES: Dict[str, Schedule] = {
    # DLD service pages: 4% (law splits it, the buyer customarily bears it all), title deed 250 +
    # unit map 250 + 10 + 10, trustee 4,000 or 2,000 plus VAT; Oqood 4% + 10 + 10;
    # mortgage 0.25% + 250 + 10 + 10. Commission of 2% plus VAT is custom, not a rule.
    "dubai": Schedule(
        transfer_rate=0.04,
        fixed_ready=520,
        fixed_offplan=20,
        complete=True,
        trustee_tiers=((500_000, 2_000), (float("inf"), 4_000)),
        agency_rate=0.02,
        mortgage_rate=0.0025,
        mortgage_fixed=270,
    ),
    # DARI service cards: 2% of contract value, halved between the parties unless they agree
    # otherwise (Resolution 49/2018), + 875 on a resale or 450 off-plan; commission 2% capped at
    # 500,000 (Decision 183/2017); mortgage 0.1% + 450 + VAT.
    "abu_dhabi": Schedule(
        transfer_rate=0.02,
        fixed_ready=875,
        fixed_offplan=450,
        complete=True,
        agency_rate=0.02,
        agency_cap=500_000,
        mortgage_rate=0.001,
        mortgage_fixed=450 * (1 + VAT),
        split_by_default=True,
    ),
    # Executive Council Decision 37/2024 art. 18: buyer 4%, or 2% for UAE and GCC nationals.
    "sharjah": Schedule(transfer_rate=0.04, transfer_rate_reduced=0.02, fixed_ready=500, fixed_offplan=500, complete=False),
    # RAK Municipality service card: 2% from the buyer on market value, plan 200 + title deed 200.
    "ras_al_khaimah": Schedule(transfer_rate=0.02, fixed_ready=400, fixed_offplan=400, complete=False),
    # Ajman service catalogue: 3% for non-citizens (minimum 3,000), 2% for UAE and GCC nationals
    # (minimum 2,500), title deed 350.
    "ajman": Schedule(
        transfer_rate=0.03,
        transfer_rate_reduced=0.02,
        transfer_minimum=3_000,
        transfer_minimum_reduced=2_500,
        fixed_ready=350,
        fixed_offplan=350,
        complete=False,
    ),
}


@dataclass
class Purchase:
    price: float
    emirate: Optional[str] = None
    community: Optional[str] = None
    completion: Optional[str] = None
    sale_type: Optional[str] = None
    transfer_fee_waived: bool = False


@dataclass
class Buyer:
    nationality: str = "other"
    financing: str = "cash"
    loan_to_value: Optional[float] = None
    first_home: bool = False


@dataclass
class CostItem:
    note: Note
    amount: float


@dataclass
class CostBreakdown:
    price: float
    items: List[CostItem] = field(default_factory=list)
    rates_known: bool = True
    complete: bool = True
    loan: float = 0.0
    ltv_asked: Optional[float] = None
    ltv_cap: Optional[float] = None
    loan_ignored: bool = False
    waived_rate: float = 0.0
    waiver_ignored: bool = False
    seller_pays_transfer: bool = False
    split_by_default: bool = False

    @property
    def total_costs(self) -> float:
        return sum(item.amount for item in self.items)

    @property
    def total_outlay(self) -> float:
        return self.price + self.total_costs

    @property
    def own_funds(self) -> float:
        """Fees cannot be financed, so they sit on top of the down payment."""
        return self.total_outlay - self.loan

    @property
    def ltv_used(self) -> Optional[float]:
        return self.loan / self.price if self.loan else None

    @property
    def loan_capped(self) -> bool:
        return self.ltv_asked is not None and self.ltv_cap is not None and self.ltv_asked > self.ltv_cap


def ltv_cap(price: float, completion: Optional[str], first_home: bool, uae_national: bool) -> float:
    if completion == "offplan":
        return LTV_CAP_OFFPLAN
    if not first_home:
        cap = LTV_CAP_INVESTMENT
    else:
        cap = LTV_CAP_HOME if price <= LTV_HOME_THRESHOLD_AED else LTV_CAP_HOME_ABOVE_THRESHOLD
    return round(cap + (LTV_NATIONAL_UPLIFT if uae_national else 0.0), 2)


def _trustee_fee(schedule: Schedule, price: float) -> float:
    for ceiling, fee in schedule.trustee_tiers:
        if price < ceiling:
            return fee * (1 + VAT)
    return 0.0


def acquisition_costs(purchase: Purchase, buyer: Buyer) -> CostBreakdown:
    price = purchase.price
    schedule = SCHEDULES.get(purchase.emirate or "")
    if schedule is None:
        return CostBreakdown(price=price, rates_known=False, complete=False)
    result = CostBreakdown(price=price, complete=schedule.complete, split_by_default=schedule.split_by_default)
    primary = purchase.sale_type == "primary"
    offplan = purchase.completion == "offplan"

    rate, minimum = schedule.transfer_rate, schedule.transfer_minimum
    if buyer.nationality in REDUCED_RATE_NATIONALITIES and schedule.transfer_rate_reduced is not None:
        rate, minimum = schedule.transfer_rate_reduced, schedule.transfer_minimum_reduced
    if place(purchase.community) in SELLER_PAYS_TRANSFER.get(purchase.emirate, ()):
        result.seller_pays_transfer = True
        result.split_by_default = False
        result.items.append(CostItem(Note("cost.transfer_fee_seller", {"rate": rate}), 0.0))
    elif purchase.transfer_fee_waived and primary:
        result.waived_rate = rate
        result.items.append(CostItem(Note("cost.transfer_fee_waived", {"rate": rate}), 0.0))
    else:
        result.waiver_ignored = purchase.transfer_fee_waived
        result.items.append(CostItem(Note("cost.transfer_fee", {"rate": rate}), max(price * rate, minimum)))

    fixed = schedule.fixed_offplan if offplan else schedule.fixed_ready
    if fixed:
        result.items.append(CostItem(Note("cost.registration_fee"), fixed))
    if not primary:
        trustee = _trustee_fee(schedule, price)
        if trustee:
            result.items.append(CostItem(Note("cost.trustee_fee"), trustee))
        if schedule.agency_rate:
            commission = price * schedule.agency_rate
            if schedule.agency_cap:
                commission = min(commission, schedule.agency_cap)
            result.items.append(CostItem(Note("cost.agency_fee", {"rate": schedule.agency_rate}), commission * (1 + VAT)))

    if buyer.financing == "mortgage":
        if offplan:
            result.loan_ignored = True
            result.ltv_cap = LTV_CAP_OFFPLAN
        else:
            result.ltv_cap = ltv_cap(price, purchase.completion, buyer.first_home, buyer.nationality == "uae")
            result.ltv_asked = buyer.loan_to_value
            result.loan = price * min(buyer.loan_to_value or result.ltv_cap, result.ltv_cap)
            if schedule.mortgage_rate:
                amount = result.loan * schedule.mortgage_rate + schedule.mortgage_fixed
                result.items.append(CostItem(Note("cost.mortgage_registration", {"rate": schedule.mortgage_rate}), amount))
    return result
