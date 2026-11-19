"""Hard filters, criterion scores, risk flags and the final ranking.

Unknown is not the same as bad: a criterion with no data scores a neutral 50 and
lowers the listing's confidence, so a thinly evidenced offer cannot outrank a
well evidenced one on the strength of a single good number.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from .brief import CRITERIA, Brief
from .comps import MIN_COMPS
from .costs import GOLDEN_VISA_MIN_AED, CostBreakdown, acquisition_costs, ltv_cap
from .dedupe import dedupe
from .listing import Listing
from .messages import Note
from .metrics import PlanValue, benchmark_gap, gross_yield, net_yield, plan_value
from .text import contains, months_until, norm

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
GROSS_YIELD_RANGE = (0.03, 0.09)
NET_YIELD_RANGE = (0.02, 0.075)
# Management at 5% of rent plus one vacant month in twelve.
RUNNING_COST_RATIO = 0.13
# Close to what a UAE mortgage costs once its fixed period ends (EIBOR plus the bank margin).
DEFAULT_DISCOUNT_RATE = 0.06
INVESTMENT_PURPOSES = ("yield", "growth")
TERMS_BEST_BENEFIT = 0.10
OFFPLAN_PREMIUM_LIMIT = 0.30
STALE_AFTER_DAYS = 90
FRESH_WITHIN_DAYS = 3
RECENT_WITHIN_DAYS = 14
SIZE_SHORTFALL_FLOOR = 0.80
LATE_HANDOVER_PENALTY_PER_MONTH = 10.0
SHORTLIST_SCORE = 65.0
CONSIDER_SCORE = 50.0
# Below this share of the weighted criteria, a score says more about what is missing than about the offer.
RATED_CONFIDENCE = 0.60
PERMIT_EMIRATES = ("dubai", "abu_dhabi")
DEVELOPER_TIER_POINTS = {1: 1.0, 2: 0.6, 3: 0.2}
EVIDENCE_POINTS = {"page": 1.0, "card": 0.5, "lead": 0.0}


@dataclass
class Criterion:
    name: str
    score: Optional[float]
    notes: List[Note]
    applicable: bool = True


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
    duplicate_urls: List[str] = field(default_factory=list)

    @property
    def has_critical_flag(self) -> bool:
        return any(flag.severity == "critical" for flag in self.flags)

    @property
    def rated(self) -> bool:
        return self.confidence >= RATED_CONFIDENCE


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
    position = (value - worst) / (best - worst)
    return round(100 * min(max(position, 0.0), 1.0), 1)


def weights_for(brief: Brief) -> Dict[str, float]:
    weights = dict(PROFILES[brief.purpose])
    weights.update(brief.weights)
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("criterion weights sum to zero")
    return {name: weights[name] / total for name in CRITERIA}


def _matches_area(listing: Listing, area: str) -> bool:
    return any(
        contains(place, area) or (place and contains(area, place))
        for place in (listing.community, listing.sub_community, listing.building)
    )


def _mentions(listing: Listing, term: str) -> bool:
    wanted = norm(term).replace(" ", "_")
    if wanted in listing.tags:
        return True
    return any(
        contains(text, term)
        for text in (listing.community, listing.sub_community, listing.building, listing.developer)
    )


def hard_filter(brief: Brief, listing: Listing, costs: CostBreakdown) -> List[Note]:
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
    if brief.areas_strict and brief.areas and not any(_matches_area(listing, a) for a in brief.areas):
        reasons.append(Note("reject.area"))
    for term in brief.exclude:
        if _mentions(listing, term):
            reasons.append(Note("reject.excluded", {"term": term}))
    if brief.purpose == "golden_visa" and listing.price_aed < GOLDEN_VISA_MIN_AED:
        reasons.append(Note("reject.golden_visa", {"threshold": GOLDEN_VISA_MIN_AED}))
    return reasons


def _value(listing: Listing, gap: Optional[float]) -> Criterion:
    if listing.price_psf is None:
        return Criterion("value", None, [Note("value.no_size")])
    if gap is None:
        return Criterion("value", None, [Note("value.no_benchmark")])
    note = Note(
        "value.scored",
        {"psf": listing.price_psf, "gap": gap, "benchmark": listing.benchmark_psf, "basis": listing.benchmark_basis},
    )
    return Criterion("value", _scale(gap, VALUE_WORST_GAP, VALUE_BEST_GAP), [note])


def _yield(listing: Listing, gross: Optional[float], net: Optional[float]) -> Criterion:
    if gross is None:
        return Criterion("yield", None, [Note("yield.none")])
    if net is not None:
        note = Note("yield.net", {"net": net, "gross": gross, "basis": listing.rent_basis})
        return Criterion("yield", _scale(net, *NET_YIELD_RANGE), [note])
    note = Note("yield.gross", {"gross": gross, "basis": listing.rent_basis})
    return Criterion("yield", _scale(gross, *GROSS_YIELD_RANGE), [note])


def _months_late(brief: Brief, listing: Listing, today: date) -> Optional[int]:
    if not (brief.handover_by and listing.handover and listing.completion == "offplan"):
        return None
    return months_until(listing.handover, today) - months_until(brief.handover_by, today)


def _fit(brief: Brief, listing: Listing, today: date) -> Criterion:
    parts: List[float] = []
    notes: List[Note] = []
    if brief.areas:
        hit = any(_matches_area(listing, area) for area in brief.areas)
        parts.append(100.0 if hit else 0.0)
        notes.append(Note("fit.area_hit" if hit else "fit.area_miss"))
    if brief.must_have:
        met = sum(1 for term in brief.must_have if _mentions(listing, term))
        parts.append(100.0 * met / len(brief.must_have))
        notes.append(Note("fit.must_have", {"met": met, "wanted": len(brief.must_have)}))
    if brief.size_min_sqft and listing.size_sqft:
        parts.append(_scale(listing.size_sqft / brief.size_min_sqft, SIZE_SHORTFALL_FLOOR, 1.0))
        notes.append(Note("fit.size", {"size": float(listing.size_sqft), "wanted": float(brief.size_min_sqft)}))
    late = _months_late(brief, listing, today)
    if late is not None:
        parts.append(max(0.0, 100.0 - LATE_HANDOVER_PENALTY_PER_MONTH * max(late, 0)))
        notes.append(Note("fit.handover_ok") if late <= 0 else Note("fit.handover_late", {"late": late}))
    if not parts:
        return Criterion("fit", None, [Note("fit.none")], applicable=False)
    return Criterion("fit", round(sum(parts) / len(parts), 1), notes)


def _trust(listing: Listing, today: date) -> Criterion:
    points: List[float] = [EVIDENCE_POINTS[listing.evidence]]
    notes: List[Note] = [Note(f"trust.evidence_{listing.evidence}")]
    if listing.permit_number:
        points.append(1.0)
        notes.append(Note("trust.permit"))
    if listing.verified is not None:
        points.append(1.0 if listing.verified else 0.0)
        notes.append(Note("trust.verified" if listing.verified else "trust.unverified"))
    if listing.observed_on:
        age = (today - date.fromisoformat(listing.observed_on)).days
        points.append(1.0 if age <= FRESH_WITHIN_DAYS else 0.5 if age <= RECENT_WITHIN_DAYS else 0.0)
        notes.append(Note("trust.seen", {"age": age}) if age else Note("trust.seen_today"))
    if listing.completion == "offplan":
        if listing.developer_tier is not None:
            points.append(DEVELOPER_TIER_POINTS[listing.developer_tier])
            notes.append(Note("trust.tier", {"tier": listing.developer_tier}))
        if listing.registration_verified is not None:
            points.append(1.0 if listing.registration_verified else 0.0)
            notes.append(Note("trust.registered" if listing.registration_verified else "trust.unregistered"))
    return Criterion("trust", round(100 * sum(points) / len(points), 1), notes)


def _terms(listing: Listing, plan: Optional[PlanValue], rate: float) -> Criterion:
    primary_offplan = listing.completion == "offplan" and listing.sale_type != "resale"
    if not listing.payment_plan and not primary_offplan:
        return Criterion("terms", None, [Note("terms.na")], applicable=False)
    if plan is None:
        return Criterion("terms", None, [Note("terms.missing")])
    note = Note(
        "terms.scored",
        {"pv": plan.present_value_ratio, "rate": rate, "before": f"{plan.paid_before_handover_pct:.0f}"},
    )
    return Criterion("terms", _scale(plan.deferral_benefit, 0.0, TERMS_BEST_BENEFIT), [note])


def _flags(brief: Brief, listing: Listing, costs: CostBreakdown, gap: Optional[float], today: date) -> List[Flag]:
    flags: List[Flag] = []

    def add(severity: str, code: str, **params) -> None:
        flags.append(Flag(severity, Note(f"flag.{code}", params)))

    offplan = listing.completion == "offplan"
    if listing.evidence == "lead":
        add("critical", "unverified_lead")
    if gap is not None and gap <= IMPLAUSIBLE_GAP:
        add("critical", "implausible_price", gap=gap)
    if offplan and listing.registration_verified is False:
        add("critical", "registration_not_found")
    if listing.completion is None:
        add("warning", "completion_unknown")
    if listing.size_sqft is None:
        add("warning", "size_missing")
    if listing.emirate in PERMIT_EMIRATES and not listing.permit_number:
        add("info", "no_permit")
    if listing.listed_days_ago is not None and listing.listed_days_ago > STALE_AFTER_DAYS:
        add("warning", "stale", days=listing.listed_days_ago)
    if offplan and listing.registration_verified is None:
        add("warning", "registration_unchecked")
    if offplan and listing.developer_tier == 3:
        add("warning", "developer_unproven")
    if offplan and listing.price_psf and listing.ready_benchmark_psf:
        premium = listing.price_psf / listing.ready_benchmark_psf - 1
        if premium > OFFPLAN_PREMIUM_LIMIT:
            add("warning", "offplan_premium", premium=premium)
    late = _months_late(brief, listing, today)
    if late is not None and late > 0:
        add("warning", "late_handover", handover=listing.handover, late=late, wanted=brief.handover_by)
    if brief.purpose == "end_use" and "tenanted" in listing.tags:
        add("warning", "tenanted")
    if not costs.rates_known:
        add("warning", "cost_rates_unknown")
    elif not costs.official:
        add("warning", "cost_rates_indicative")
    if brief.financing == "mortgage" and brief.loan_to_value:
        cap = ltv_cap(listing.price_aed, listing.completion, brief.purpose in INVESTMENT_PURPOSES)
        if offplan:
            add("warning", "offplan_finance", cap=cap)
        elif brief.loan_to_value > cap:
            add("warning", "ltv_over_cap", ltv=brief.loan_to_value, cap=cap)
    if brief.purpose == "golden_visa" and (offplan or brief.financing == "mortgage"):
        add("info", "golden_visa_conditions")
    if not brief.budget_includes_costs and costs.total_outlay > brief.budget_max:
        add("info", "costs_exceed_budget", outlay=costs.total_outlay)
    if listing.benchmark_psf is None and listing.size_sqft is not None:
        add("info", "no_benchmark")
    if listing.benchmark_psf is not None and listing.benchmark_count is not None and listing.benchmark_count < MIN_COMPS:
        add("warning", "thin_benchmark", count=listing.benchmark_count)
    if offplan and listing.annual_rent_aed is not None:
        add("info", "projected_rent")
    if listing.evidence == "card":
        add("info", "card_only")
    if listing.observed_on is None:
        add("info", "not_dated")
    return flags


def _verdict(score: float, confidence: float, critical: bool) -> str:
    if critical:
        return "verify_first"
    if confidence < RATED_CONFIDENCE:
        return "needs_data"
    if score >= SHORTLIST_SCORE:
        return "shortlist"
    if score >= CONSIDER_SCORE:
        return "consider"
    return "pass"


def assess_one(brief: Brief, listing: Listing, costs: CostBreakdown, weights: Dict[str, float], today: date) -> Assessment:
    rate = brief.discount_rate if brief.discount_rate is not None else DEFAULT_DISCOUNT_RATE
    gap = benchmark_gap(listing)
    gross = gross_yield(listing)
    net = net_yield(listing, costs.total_outlay, RUNNING_COST_RATIO)
    plan = plan_value(listing, today, rate)
    criteria = [
        _value(listing, gap),
        _yield(listing, gross, net),
        _fit(brief, listing, today),
        _trust(listing, today),
        _terms(listing, plan, rate),
    ]
    live = [c for c in criteria if c.applicable and weights[c.name] > 0]
    total = sum(weights[c.name] for c in live)
    if total == 0:
        score, confidence = NEUTRAL, 0.0
    else:
        score = sum(weights[c.name] * (NEUTRAL if c.score is None else c.score) for c in live) / total
        confidence = sum(weights[c.name] for c in live if c.score is not None) / total
    flags = _flags(brief, listing, costs, gap, today)
    critical = any(flag.severity == "critical" for flag in flags)
    return Assessment(
        listing=listing,
        score=round(score, 1),
        confidence=round(confidence, 2),
        verdict=_verdict(score, confidence, critical),
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
    unique, folded = dedupe(listings)
    ranked: List[Assessment] = []
    rejected: List[Rejection] = []
    for listing in unique:
        costs = acquisition_costs(
            listing.price_aed,
            listing.emirate,
            listing.completion,
            listing.sale_type,
            brief.financing,
            brief.loan_to_value,
            brief.gcc_national,
            listing.transfer_fee_waived,
        )
        reasons = hard_filter(brief, listing, costs)
        if reasons:
            rejected.append(Rejection(listing, reasons))
            continue
        assessment = assess_one(brief, listing, costs, weights, today)
        assessment.duplicate_urls = folded.get(listing.url, [])
        ranked.append(assessment)
    ranked.sort(key=lambda a: (a.has_critical_flag, not a.rated, -a.score, -a.confidence, a.listing.price_aed))
    return Result(brief=brief, as_of=today, ranked=ranked, rejected=rejected, weights=weights, received=len(listings))
