"""A gap in a record must never be what puts an offer on the shortlist.

Every optional field is dropped in turn from a few hundred generated records, under generated briefs,
and every pair of fields from a smaller sample. Four fields are left alone because their absence is a
statement, not a gap: without `from_price` the price is that of a specific unit, without
`transfer_fee_waived` the fee is due, `tags` are evidence that is either recorded or not, and without
`instalments` the construction share is spread evenly, as an advert that dates nothing states it.
"""

import random
from itertools import combinations
from datetime import timedelta

import pytest

from property_scout.brief import Brief
from property_scout.listing import REQUIRED, Listing, ListingError
from property_scout.scoring import SHORTLIST_SCORE, assess

STATEMENTS = ("from_price", "transfer_fee_waived", "tags", "instalments")
RECORDS = 300
PAIRED_RECORDS = 60
# Plans from the generous to the worst there is, so that leaving one out is tempting.
PLANS = (
    {"on_booking": 20, "on_handover": 80},
    {"on_booking": 40, "post_handover": 60},
    {"on_booking": 100},
    {"on_booking": 90, "on_handover": 10},
    {"on_booking": 70, "during_construction": 30},
    {"on_booking": 10, "during_construction": 50, "on_handover": 40},
    {"on_booking": 20, "during_construction": 30, "on_handover": 10, "post_handover": 40},
)


def generated_brief(rng):
    data = {
        "budget_max": 6_000_000,
        "purpose": rng.choice(["yield", "growth", "end_use", "balanced", "golden_visa"]),
        "emirates": rng.choice([["dubai"], ["dubai"], ["abu_dhabi"], ["sharjah"], ["fujairah"], ["dubai", "abu_dhabi"], []]),
        "market": rng.choice(["any", "any", "ready", "offplan"]),
    }
    optional = {
        "areas": ["Dubai Marina"],
        "must_have": rng.choice([["vacant"], ["vacant"], ["Example Developer"]]),
        "size_min_sqft": 700,
        "handover_by": "2028-Q4",
        "bedrooms_min": 1,
        "bedrooms_max": 2,
        "property_types": ["apartment"],
        "budget_includes_costs": True,
        "sale_type": rng.choice(["primary", "resale"]),
        "exclude": rng.choice([["tenanted"], ["Example Developer"], ["Tower"]]),
        "weights": rng.choice([{"terms": 0.3}, {"terms": 0}, {"yield": 0}, {"fit": 0.5}]),
    }
    data.update({name: value for name, value in optional.items() if rng.random() < 0.3})
    if "areas" in data:
        data["areas_strict"] = rng.random() < 0.3
    if "must_have" in data:
        data["must_have_strict"] = rng.random() < 0.5
    if "handover_by" in data:
        data["handover_strict"] = rng.random() < 0.6
    if rng.random() < 0.3:
        data["financing"] = "mortgage"
    return data


def generated_listing(rng, emirate, today):
    offplan = rng.random() < 0.5
    size = rng.choice([600, 750, 900])
    price = rng.choice([2_100_000, 2_400_000, 3_000_000])
    benchmark = price / size * rng.choice([0.75, 0.9, 0.95, 1.0, 1.05, 1.1, 1.3, 1.6])
    data = {
        "url": f"https://x.example/{rng.randrange(10 ** 9)}",
        "price_aed": price,
        "evidence": rng.choice(["page", "page", "page", "card", "lead"]),
        "emirate": emirate,
        "community": rng.choice(["Dubai Marina", "Business Bay"]),
        "building": "Tower",
        "developer": "Example Developer",
        "property_type": "apartment",
        "bedrooms": 1,
        "bathrooms": 1,
        "size_sqft": size,
        "completion": "offplan" if offplan else "ready",
        "sale_type": rng.choice(["primary", "primary", "resale"]),
        "observed_on": (today - timedelta(days=rng.choice([0, 2, 10, 40]))).isoformat(),
        "benchmark_psf": round(benchmark),
        "benchmark_count": rng.choice([2, 6, 12]),
        "annual_rent_aed": price * rng.choice([0.04, 0.06, 0.06, 0.08, 0.08, 0.2]),
        "rent_count": rng.choice([1, 6]),
        "service_charge_psf": rng.choice([10, 18, 45]),
        "verified": rng.choice([True, False]),
        "permit_number": rng.choice(["7100000001", None]),
        "listed_days_ago": rng.choice([3, 120]),
        "building_sales_12m": rng.choice([2, 15]),
        "tags": rng.choice([[], ["vacant"], ["tenanted"]]),
        "from_price": rng.random() < 0.15,
        "price_corroborated": rng.choice([True, True, False, None]),
    }
    if offplan or rng.random() < 0.3:
        data.update(payment_plan=dict(rng.choice(PLANS)), post_handover_months=rng.choice([0, 24, 48]))
        if data["payment_plan"].get("during_construction") and rng.random() < 0.5:
            data["instalments"] = [{"pct": 10, "after_months": 1}, {"pct": 10, "due": "2027-06"}]
    if offplan:
        data.update(
            handover=rng.choice(["2026-06", "2028-Q2", "2029-Q4"]),
            developer_tier=rng.choice([1, 1, 2, 3]),
            registration_verified=rng.choice([True, True, True, False, None]),
            project_number="2927",
            register_started=rng.choice(["2024-01", "2026-06"]),
            register_completion=rng.choice(["2026-03", "2028-Q4", "2029-Q2"]),
            register_progress_pct=rng.choice([5, 40, 80]),
            register_inspected_on=rng.choice(["2026-11-01", "2026-05-01"]),
            ready_benchmark_psf=round(benchmark * rng.choice([0.6, 0.9])),
            transfer_fee_waived=rng.random() < 0.3,
        )
    return {name: value for name, value in data.items() if value is not None}


def assessed(brief, listing, today):
    try:
        record = Listing.from_dict(listing)
    except ListingError:
        # Instalments left without the plan they detail: the record is refused, which shortlists nothing.
        return None
    ranked = assess(Brief.from_dict(brief), [record], today).ranked
    return ranked[0] if ranked else None


def verdict(brief, listing, today):
    found = assessed(brief, listing, today)
    return found.verdict if found else "rejected"


def just_short(brief, listing, today):
    """The same record repriced to score as close under the shortlist line as it can: where a small lift shows."""
    best = None
    for step in range(-10, 16):
        repriced = {**listing, "price_aed": round(listing["price_aed"] * (1 + step * 0.02))}
        found = assessed(brief, repriced, today)
        if found and found.verdict != "shortlist" and found.score < SHORTLIST_SCORE and (best is None or found.score > best[0]):
            best = (found.score, repriced)
    return best[1] if best else listing


@pytest.fixture(scope="module")
def cases(request):
    from tests.property_scout.conftest import TODAY

    rng = random.Random(20261120)
    built = []
    for index in range(RECORDS):
        brief = generated_brief(rng)
        listing = generated_listing(rng, rng.choice(brief["emirates"] or ["dubai", "ajman"]), TODAY)
        # Every other record is left as generated, so that offers held above the line are tested too.
        built.append((brief, just_short(brief, listing, TODAY) if index % 2 else listing))
    return built, TODAY


def test_the_generated_records_crowd_the_shortlist_line_and_cover_every_verdict(cases):
    built, today = cases
    found = [assessed(brief, listing, today) for brief, listing in built]
    verdicts = {a.verdict for a in found if a}
    assert verdicts >= {"consider", "pass", "verify_first"} and None in found
    close = [a for a in found if a and SHORTLIST_SCORE - 2 <= a.score < SHORTLIST_SCORE]
    held = [a for a in found if a and a.held]
    assert len(close) >= 20 and len(held) >= 10


def test_a_record_just_short_reaches_the_shortlist_when_its_price_falls(cases):
    """The line is within reach: the drops below are tested against offers a small change would shortlist."""
    built, today = cases
    reached = 0
    for brief, listing in built:
        cheaper = {**listing, "price_aed": round(listing["price_aed"] * 0.9)}
        reached += verdict(brief, listing, today) != "shortlist" and verdict(brief, cheaper, today) == "shortlist"
    assert reached >= 10


def test_dropping_a_field_never_puts_an_offer_on_the_shortlist(cases):
    built, today = cases
    lifted = []
    for brief, listing in built:
        if verdict(brief, listing, today) == "shortlist":
            continue
        for name in listing:
            if name in REQUIRED or name in STATEMENTS:
                continue
            without = {key: value for key, value in listing.items() if key != name}
            if verdict(brief, without, today) == "shortlist":
                lifted.append((name, brief, listing))
    assert [name for name, _, _ in lifted] == []


def test_dropping_two_fields_together_never_puts_an_offer_on_the_shortlist(cases):
    """One gap can hide behind another: a date the register gives, say, behind the advert's."""
    built, today = cases
    lifted = []
    for brief, listing in built[:PAIRED_RECORDS]:
        if verdict(brief, listing, today) == "shortlist":
            continue
        names = [name for name in listing if name not in REQUIRED and name not in STATEMENTS]
        for pair in combinations(names, 2):
            without = {key: value for key, value in listing.items() if key not in pair}
            if verdict(brief, without, today) == "shortlist":
                lifted.append(pair)
    assert lifted == []


def test_dropping_a_field_never_frees_an_offer_from_a_limit_untested(cases):
    """An offer the brief rejects may come back when the deciding field is dropped, but only held or worse."""
    built, today = cases
    for brief, listing in built:
        if verdict(brief, listing, today) != "rejected":
            continue
        for name in listing:
            if name in REQUIRED:
                continue
            without = {key: value for key, value in listing.items() if key != name}
            assert verdict(brief, without, today) != "shortlist", name
