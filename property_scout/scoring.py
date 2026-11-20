"""Hard filters, criterion scores, risk flags and the final ranking.

Unknown is not the same as bad: a criterion with no data scores a neutral 50 and
lowers the listing's completeness, so a thinly documented offer cannot outrank a
well documented one on the strength of a single good number.
"""

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Dict, List, Optional

from .brief import CRITERIA, Brief
from .comps import MIN_COMPS
from .costs import GOLDEN_VISA_MIN_AED, Buyer, CostBreakdown, Purchase, acquisition_costs
from .dedupe import dedupe
from .listing import Listing
from .messages import Note
from .metrics import PlanValue, benchmark_gap, gross_yield, net_yield, plan_value
from .text import has_words, months_until, same_place, slug

PROFILES: Dict[str, Dict[str, float]] = {
    "yield": {"value": 0.25, "yield": 0.40, "fit": 0.10, "trust": 0.20, "terms": 0.05},
    "growth": {"value": 0.40, "yield": 0.10, "fit": 0.15, "trust": 0.25, "terms": 0.10},
    "end_use": {"value": 0.25, "yield": 0.00, "fit": 0.45, "trust": 0.25, "terms": 0.05},
    "golden_visa": {"value": 0.30, "yield": 0.15, "fit": 0.20, "trust": 0.30, "terms": 0.05},
    "balanced": {"value": 0.30, "yield": 0.25, "fit": 0.15, "trust": 0.25, "terms": 0.05},
}

NEUTRAL = 50.0
# Asks sat about 11% above registered prices in November 2026, so an ask level with
# the sold median is already a good one and scores in the upper third.
VALUE_WORST_GAP = 0.20
VALUE_BEST_GAP = -0.10
IMPLAUSIBLE_GAP = -0.30
IMPLAUSIBLE_GROSS_YIELD = 0.15
NET_YIELD_RANGE = (0.02, 0.075)
# Management at 5% of rent plus one vacant month in twelve.
RUNNING_COST_RATIO = 0.13
# What service charges and running costs take off a gross yield when they are not known.
ASSUMED_YIELD_LOSS = 0.025
# Close to what a UAE mortgage costs once its fixed period ends (EIBOR plus the bank margin).
DEFAULT_DISCOUNT_RATE = 0.06
TERMS_BEST_BENEFIT = 0.10
# Off-plan registered a third to a half above same-district resale in 2026.
OFFPLAN_PREMIUM_LIMIT = 0.50
STALE_AFTER_DAYS = 90
FRESH_WITHIN_DAYS = 3
RECENT_WITHIN_DAYS = 14
INSPECTION_STALE_DAYS = 92
SIZE_SHORTFALL_FLOOR = 0.80
LATE_HANDOVER_PENALTY_PER_MONTH = 10.0
SHORTLIST_SCORE = 65.0
CONSIDER_SCORE = 50.0
# Below this share of the weighted criteria, a score says more about what is missing than about the offer.
RATED_CONFIDENCE = 0.60
# A criterion resting on few rows or on an estimate counts for half, and its score is pulled halfway to neutral.
PARTIAL = 0.5
VISA_MARGIN = 0.05
LOW_TURNOVER_SALES = 6
PERMIT_EMIRATES = ("dubai", "abu_dhabi")
DEVELOPER_TIER_POINTS = {1: 1.0, 2: 0.6, 3: 0.2}
UNKNOWN_TIER_POINTS = 0.2
EVIDENCE_POINTS = {"page": 1.0, "card": 0.5, "lead": 0.0}
VERDICTS = ("shortlist", "consider", "pass", "needs_data", "verify_first")
SEVERITIES = ("critical", "warning", "info")


@dataclass
class Criterion:
    name: str
    score: Optional[float]
    notes: List[Note]
    applicable: bool = True
    evidence: float = 1.0


@dataclass
class Flag:
    severity: str
    note: Note

    @property
    def code(self) -> str:
        return self.note.code.split(".", 1)[1]


@dataclass
class Assessment:
    listing: Listing
    score: float
    confidence: float
    verdict: str
    criteria: List[Criterion]
    flags: List[Flag]
    costs: CostBreakdown
    benchmark_gap: Optional[float]
    gross_yield: Optional[float]
    net_yield: Optional[float]
    plan: Optional[PlanValue]
    duplicates: List[Listing] = field(default_factory=list)

    @property
    def has_critical_flag(self) -> bool:
        return any(flag.severity == "critical" for flag in self.flags)

    @property
    def rated(self) -> bool:
        return self.confidence >= RATED_CONFIDENCE

    @property
    def cash_at_booking(self) -> Optional[float]:
        if self.plan is None or not self.listing.offplan:
            return None
        return self.listing.price_aed * self.plan.booking_pct / 100 + self.costs.total_costs


@dataclass
class Rejection:
    listing: Listing
    reasons: List[Note]


@dataclass
class Result:
    brief: Brief
    as_of: date
    ranked: List[Assessment]
    rejected: List[Rejection]
    weights: Dict[str, float]
    received: int


def _scale(value: float, worst: float, best: float) -> float:
    return 100 * min(max((value - worst) / (best - worst), 0.0), 1.0)


def _thin(count: Optional[int]) -> bool:
    return count is None or count < MIN_COMPS


def weights_for(brief: Brief) -> Dict[str, float]:
    weights = dict(PROFILES[brief.purpose])
    weights.update(brief.weights)
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("criterion weights sum to zero")
    return {name: weights[name] / total for name in CRITERIA}


def _in_area(listing: Listing, area: str) -> bool:
    return any(same_place(spot, area) for spot in (listing.community, listing.sub_community, listing.building))


def _excluded(listing: Listing, term: str) -> bool:
    if slug(term) and slug(term) in listing.tags:
        return True
    return _in_area(listing, term) or has_words(listing.building, term) or has_words(listing.developer, term)


def _months_late(brief: Brief, listing: Listing, today: date) -> Optional[int]:
    if not (brief.handover_by and listing.offplan and listing.scheduled_handover):
        return None
    return months_until(listing.scheduled_handover, today) - months_until(brief.handover_by, today)


def costs_for(brief: Brief, listing: Listing) -> CostBreakdown:
    purchase = Purchase(
        price=listing.price_aed,
        emirate=listing.emirate,
        community=listing.community,
        completion=listing.completion,
        sale_type=listing.sale_type,
        transfer_fee_waived=listing.transfer_fee_waived,
    )
    buyer = Buyer(brief.buyer_nationality, brief.financing, brief.loan_to_value, brief.is_first_home)
    return acquisition_costs(purchase, buyer)


def hard_filter(brief: Brief, listing: Listing, costs: CostBreakdown, today: date) -> List[Note]:
    reasons: List[Note] = []
    spend = costs.total_outlay if brief.budget_includes_costs else listing.price_aed
    if spend > brief.budget_max:
        code = "reject.over_budget_costs" if brief.budget_includes_costs else "reject.over_budget"
        reasons.append(Note(code, {"spend": spend, "budget": brief.budget_max}))
    if listing.price_aed < brief.budget_min:
        reasons.append(Note("reject.under_budget", {"price": listing.price_aed, "minimum": brief.budget_min}))
    if brief.market != "any" and listing.completion and listing.completion != brief.market:
        reasons.append(Note("reject.market", {"completion": listing.completion, "market": brief.market}))
    if brief.emirates and listing.emirate and listing.emirate not in brief.emirates:
        reasons.append(Note("reject.emirate", {"emirate": listing.emirate}))
    if brief.property_types and listing.property_type and listing.property_type not in brief.property_types:
        reasons.append(Note("reject.type", {"type": listing.property_type}))
    if listing.bedrooms is not None:
        if brief.bedrooms_min is not None and listing.bedrooms < brief.bedrooms_min:
            reasons.append(Note("reject.beds_low", {"beds": listing.bedrooms, "wanted": brief.bedrooms_min}))
        if brief.bedrooms_max is not None and listing.bedrooms > brief.bedrooms_max:
            reasons.append(Note("reject.beds_high", {"beds": listing.bedrooms, "wanted": brief.bedrooms_max}))
    if brief.areas_strict and brief.areas and not any(_in_area(listing, area) for area in brief.areas):
        reasons.append(Note("reject.area"))
    for term in brief.exclude:
        if _excluded(listing, term):
            reasons.append(Note("reject.excluded", {"term": term}))
    late = _months_late(brief, listing, today)
    if brief.handover_strict and late is not None and late > 0:
        reasons.append(Note("reject.handover", {"handover": listing.scheduled_handover, "wanted": brief.handover_by}))
    if brief.purpose == "golden_visa" and listing.price_aed < GOLDEN_VISA_MIN_AED:
        reasons.append(Note("reject.golden_visa", {"threshold": GOLDEN_VISA_MIN_AED}))
    return reasons


def _value(listing: Listing, gap: Optional[float]) -> Criterion:
    if listing.price_psf is None:
        return Criterion("value", None, [Note("value.no_size")], evidence=0.0)
    if gap is None:
        return Criterion("value", None, [Note("value.no_benchmark")], evidence=0.0)
    notes = [
        Note(
            "value.scored",
            {"psf": listing.price_psf, "gap": gap, "benchmark": listing.benchmark_psf, "basis": listing.benchmark_basis},
        )
    ]
    score = _scale(gap, VALUE_WORST_GAP, VALUE_BEST_GAP)
    if not _thin(listing.benchmark_count):
        return Criterion("value", score, notes)
    notes.append(Note("value.thin"))
    return Criterion("value", NEUTRAL + (score - NEUTRAL) * PARTIAL, notes, evidence=PARTIAL)


def _yield(listing: Listing, gross: Optional[float], net: Optional[float], costs: CostBreakdown) -> Criterion:
    if gross is None:
        return Criterion("yield", None, [Note("yield.none")], evidence=0.0)
    if net is None:
        estimate = gross - ASSUMED_YIELD_LOSS
        note = Note("yield.gross", {"gross": gross, "net": estimate, "basis": listing.rent_basis})
        return Criterion("yield", _scale(estimate, *NET_YIELD_RANGE), [note], evidence=PARTIAL)
    notes = [Note("yield.net", {"net": net, "gross": gross, "basis": listing.rent_basis})]
    if _thin(listing.rent_count) or not costs.rates_known:
        notes.append(Note("yield.thin"))
        return Criterion("yield", _scale(net, *NET_YIELD_RANGE), notes, evidence=PARTIAL)
    return Criterion("yield", _scale(net, *NET_YIELD_RANGE), notes)


def _fit(brief: Brief, listing: Listing, today: date) -> Criterion:
    parts: List[float] = []
    notes: List[Note] = []
    if brief.areas and not brief.areas_strict:
        hit = any(_in_area(listing, area) for area in brief.areas)
        parts.append(100.0 if hit else 0.0)
        notes.append(Note("fit.area_hit" if hit else "fit.area_miss"))
    if brief.must_have:
        met = sum(1 for term in brief.must_have if slug(term) in listing.tags)
        parts.append(100.0 * met / len(brief.must_have))
        notes.append(Note("fit.must_have", {"met": met, "wanted": len(brief.must_have)}))
    if brief.size_min_sqft and listing.size_sqft:
        parts.append(_scale(listing.size_sqft / brief.size_min_sqft, SIZE_SHORTFALL_FLOOR, 1.0))
        notes.append(Note("fit.size", {"size": float(listing.size_sqft), "wanted": float(brief.size_min_sqft)}))
    if brief.handover_by and listing.offplan:
        late = _months_late(brief, listing, today)
        if late is None:
            parts.append(NEUTRAL)
            notes.append(Note("fit.handover_unknown"))
        else:
            parts.append(max(0.0, 100.0 - LATE_HANDOVER_PENALTY_PER_MONTH * max(late, 0)))
            notes.append(Note("fit.handover_ok") if late <= 0 else Note("fit.handover_late", {"late": late}))
    if not parts:
        return Criterion("fit", None, [Note("fit.none")], applicable=False, evidence=0.0)
    return Criterion("fit", sum(parts) / len(parts), notes)


def _seen_points(listing: Listing, today: date, notes: List[Note]) -> float:
    if not listing.observed_on:
        notes.append(Note("trust.not_dated"))
        return 0.0
    age = (today - date.fromisoformat(listing.observed_on)).days
    if age < -1:
        notes.append(Note("trust.seen_future"))
        return 0.0
    age = max(age, 0)
    notes.append(Note("trust.seen", {"age": age}) if age else Note("trust.seen_today"))
    return 1.0 if age <= FRESH_WITHIN_DAYS else 0.5 if age <= RECENT_WITHIN_DAYS else 0.0


def _trust(listing: Listing, today: date) -> Criterion:
    """Every check counts whether or not it was made: one that was skipped scores nothing."""
    notes: List[Note] = [Note(f"trust.evidence_{listing.evidence}")]
    points: List[float] = [EVIDENCE_POINTS[listing.evidence], _seen_points(listing, today, notes)]
    if listing.permit_number or listing.verified:
        points.append(1.0)
        notes.append(Note("trust.permit" if listing.permit_number else "trust.verified"))
    else:
        points.append(0.0)
        notes.append(Note("trust.unverified" if listing.verified is False else "trust.unchecked"))
    if listing.offplan:
        if listing.developer_tier is None:
            points.append(UNKNOWN_TIER_POINTS)
            notes.append(Note("trust.tier_unknown"))
        else:
            points.append(DEVELOPER_TIER_POINTS[listing.developer_tier])
            notes.append(Note("trust.tier", {"tier": listing.developer_tier}))
        points.append(1.0 if listing.registration_verified else 0.0)
        notes.append(
            Note(
                "trust.registered" if listing.registration_verified
                else "trust.unregistered" if listing.registration_verified is False
                else "trust.registration_unchecked"
            )
        )
    return Criterion("trust", 100 * sum(points) / len(points), notes)


def _terms(listing: Listing, plan: Optional[PlanValue], costs: CostBreakdown, rate: float) -> Criterion:
    if listing.sale_type == "resale":
        return Criterion("terms", None, [Note("terms.resale")], applicable=False, evidence=0.0)
    if not listing.payment_plan and not listing.offplan:
        return Criterion("terms", None, [Note("terms.na")], applicable=False, evidence=0.0)
    if plan is None:
        return Criterion("terms", None, [Note("terms.missing")], evidence=0.0)
    notes = [
        Note(
            "terms.scored",
            {"pv": plan.present_value_ratio, "rate": rate, "before": f"{plan.paid_before_handover_pct:.0f}"},
        )
    ]
    if costs.waived_rate:
        notes.append(Note("terms.waiver", {"rate": costs.waived_rate}))
    return Criterion("terms", _scale(plan.deferral_benefit + costs.waived_rate, 0.0, TERMS_BEST_BENEFIT), notes)


def cost_flags(costs: CostBreakdown, emirate: Optional[str]) -> List[Flag]:
    """What a reader must know about a cost stack before relying on its total."""
    flags: List[Flag] = []

    def add(severity: str, code: str, **params) -> None:
        flags.append(Flag(severity, Note(f"flag.{code}", params)))

    if emirate is None:
        add("warning", "emirate_missing")
    elif not costs.rates_known:
        add("warning", "cost_rates_unknown")
    elif not costs.complete:
        add("warning", "cost_rates_partial")
    if costs.waiver_ignored:
        add("warning", "waiver_ignored")
    if costs.loan_ignored:
        add("warning", "offplan_finance", cap=costs.ltv_cap)
    elif costs.loan_capped:
        add("warning", "ltv_capped", ltv=costs.ltv_asked, cap=costs.ltv_cap)
    if costs.seller_pays_transfer:
        add("info", "transfer_seller_pays")
    elif costs.split_by_default:
        add("info", "transfer_split")
    return flags


def _flags(brief: Brief, listing: Listing, costs: CostBreakdown, gap: Optional[float], gross: Optional[float], today: date) -> List[Flag]:
    flags: List[Flag] = []

    def add(severity: str, code: str, **params) -> None:
        flags.append(Flag(severity, Note(f"flag.{code}", params)))

    offplan = listing.offplan
    if listing.analyst_cap:
        add("critical" if listing.analyst_cap == "verify_first" else "warning", "analyst", text=listing.analyst_note)
    if listing.evidence == "lead":
        add("critical", "unverified_lead")
    if gap is not None and gap <= IMPLAUSIBLE_GAP:
        add("critical", "implausible_price", gap=gap)
    if gross is not None and gross > IMPLAUSIBLE_GROSS_YIELD:
        add("critical", "implausible_yield", gross=gross)
    if offplan and listing.registration_verified is False:
        add("critical", "registration_not_found")

    if gap is not None and gap >= VALUE_WORST_GAP:
        add("warning", "overpriced", gap=gap)
    if listing.benchmark_psf is not None and listing.size_sqft and _thin(listing.benchmark_count):
        add("warning", "thin_benchmark")
    if listing.from_price:
        add("warning", "from_price")
    if listing.completion is None:
        add("warning", "completion_unknown")
    if listing.size_sqft is None:
        add("warning", "size_missing")
    if listing.listed_days_ago is not None and listing.listed_days_ago > STALE_AFTER_DAYS:
        add("warning", "stale", days=listing.listed_days_ago)
    if listing.observed_on and (date.fromisoformat(listing.observed_on) - today).days > 1:
        add("warning", "seen_in_future", seen=listing.observed_on)
    if offplan:
        if listing.registration_verified is None:
            add("warning", "registration_unchecked")
        if listing.developer_tier == 3:
            add("warning", "developer_unproven")
        if listing.price_psf and listing.ready_benchmark_psf:
            premium = listing.price_psf / listing.ready_benchmark_psf - 1
            if premium > OFFPLAN_PREMIUM_LIMIT:
                add("warning", "offplan_premium", premium=premium)
        if listing.register_completion and months_until(listing.register_completion, today) < 0:
            add("warning", "register_overdue", date=listing.register_completion, progress=listing.register_progress_pct)
        elif not listing.register_completion and listing.handover and months_until(listing.handover, today) < 0:
            add("warning", "handover_passed", handover=listing.handover)
        if listing.register_completion and listing.handover:
            gap_months = months_until(listing.register_completion, today) - months_until(listing.handover, today)
            if gap_months > 0:
                add("warning", "handover_mismatch", advert=listing.handover, register=listing.register_completion)
        if brief.handover_by and not listing.scheduled_handover:
            add("warning", "handover_unknown")
        late = _months_late(brief, listing, today)
        if late is not None and late > 0:
            add("warning", "late_handover", handover=listing.scheduled_handover, late=late, wanted=brief.handover_by)
        if listing.register_inspected_on and (today - date.fromisoformat(listing.register_inspected_on)).days > INSPECTION_STALE_DAYS:
            add("info", "inspection_stale", inspected=listing.register_inspected_on)
    if brief.purpose == "end_use" and "tenanted" in listing.tags:
        add("warning", "tenanted")
    flags.extend(cost_flags(costs, listing.emirate))
    if brief.financing == "mortgage" and not brief.resident:
        add("warning", "non_resident_finance")
    if brief.purpose == "golden_visa":
        if listing.price_aed < GOLDEN_VISA_MIN_AED * (1 + VISA_MARGIN):
            add("warning", "visa_margin", threshold=GOLDEN_VISA_MIN_AED)
        if listing.benchmark_psf and listing.size_sqft and listing.benchmark_psf * listing.size_sqft < GOLDEN_VISA_MIN_AED:
            add("warning", "visa_benchmark_below", implied=listing.benchmark_psf * listing.size_sqft, threshold=GOLDEN_VISA_MIN_AED)
        if offplan or brief.financing == "mortgage":
            add("warning", "visa_conditions")

    if costs.total_outlay > brief.budget_max:
        add("info", "costs_exceed_budget", outlay=costs.total_outlay)
    if listing.emirate in PERMIT_EMIRATES and not listing.permit_number:
        add("info", "no_permit")
    if listing.benchmark_psf is None and listing.size_sqft is not None:
        add("info", "no_benchmark")
    if offplan and listing.annual_rent_aed is not None:
        add("info", "projected_rent")
    if listing.building_sales_12m is not None and listing.building_sales_12m < LOW_TURNOVER_SALES:
        add("info", "low_turnover", sales=listing.building_sales_12m)
    if listing.evidence == "card":
        add("info", "card_only")
    return sorted(flags, key=lambda flag: SEVERITIES.index(flag.severity))


def _verdict(brief: Brief, listing: Listing, score: float, confidence: float, flags: List[Flag]) -> str:
    codes = {flag.code for flag in flags}
    if any(flag.severity == "critical" for flag in flags):
        return "verify_first"
    if confidence < RATED_CONFIDENCE:
        return "needs_data"
    verdict = "shortlist" if score >= SHORTLIST_SCORE else "consider" if score >= CONSIDER_SCORE else "pass"
    held_back = (
        listing.evidence != "page"
        or (listing.offplan and not listing.registration_verified)
        or "tenanted" in codes
        or listing.analyst_cap == "consider"
    )
    if verdict == "shortlist" and held_back:
        verdict = "consider"
    if listing.analyst_cap == "pass" or ("overpriced" in codes and "thin_benchmark" not in codes):
        verdict = "pass"
    return verdict


def assess_one(brief: Brief, listing: Listing, costs: CostBreakdown, weights: Dict[str, float], today: date) -> Assessment:
    rate = brief.discount_rate if brief.discount_rate is not None else DEFAULT_DISCOUNT_RATE
    gap = benchmark_gap(listing)
    gross = gross_yield(listing)
    net = net_yield(listing, costs.total_outlay, RUNNING_COST_RATIO)
    plan = plan_value(listing, today, rate)
    criteria = [
        _value(listing, gap),
        _yield(listing, gross, net, costs),
        _fit(brief, listing, today),
        _trust(listing, today),
        _terms(listing, plan, costs, rate),
    ]
    live = [c for c in criteria if c.applicable and weights[c.name] > 0]
    total = sum(weights[c.name] for c in live)
    if total == 0:
        score, confidence = NEUTRAL, 0.0
    else:
        score = sum(weights[c.name] * (NEUTRAL if c.score is None else c.score) for c in live) / total
        confidence = sum(weights[c.name] * c.evidence for c in live) / total
    score, confidence = round(score, 1), round(confidence, 2)
    flags = _flags(brief, listing, costs, gap, gross, today)
    return Assessment(
        listing=listing,
        score=score,
        confidence=confidence,
        verdict=_verdict(brief, listing, score, confidence, flags),
        criteria=criteria,
        flags=flags,
        costs=costs,
        benchmark_gap=gap,
        gross_yield=gross,
        net_yield=net,
        plan=plan,
    )


def assess(brief: Brief, listings: List[Listing], today: date) -> Result:
    weights = weights_for(brief)
    assumed = brief.emirates[0] if len(brief.emirates) == 1 else None
    survivors: List[Listing] = []
    rejected: List[Rejection] = []
    for listing in listings:
        if listing.emirate is None and assumed:
            listing = replace(listing, emirate=assumed)
        reasons = hard_filter(brief, listing, costs_for(brief, listing), today)
        if reasons:
            rejected.append(Rejection(listing, reasons))
        else:
            survivors.append(listing)
    ranked: List[Assessment] = []
    for listing, duplicates in dedupe(survivors):
        assessment = assess_one(brief, listing, costs_for(brief, listing), weights, today)
        assessment.duplicates = duplicates
        cheapest = min((d.price_aed for d in duplicates), default=listing.price_aed)
        if cheapest < listing.price_aed:
            assessment.flags.append(Flag("info", Note("flag.advertised_lower", {"price": cheapest})))
        ranked.append(assessment)
    ranked.sort(key=lambda a: (VERDICTS.index(a.verdict), -a.score, -a.confidence, a.listing.price_aed, a.listing.url))
    return Result(brief=brief, as_of=today, ranked=ranked, rejected=rejected, weights=weights, received=len(listings))
