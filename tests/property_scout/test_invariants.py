"""A gap in a record must never be what puts an offer on the shortlist.

Every optional field is dropped in turn from a few hundred generated records, under generated briefs.
Three fields are left alone because their absence is a statement, not a gap: without `from_price` the
price is that of a specific unit, without `transfer_fee_waived` the fee is due, and `tags` are evidence
that is either recorded or not.
"""

import random
from datetime import timedelta

import pytest

from property_scout.brief import Brief
from property_scout.listing import REQUIRED, Listing
from property_scout.scoring import assess

STATEMENTS = ("from_price", "transfer_fee_waived", "tags")
RECORDS = 250


def generated_brief(rng):
    data = {
        "budget_max": 6_000_000,
        "purpose": rng.choice(["yield", "growth", "end_use", "balanced", "golden_visa"]),
        "emirates": [rng.choice(["dubai", "abu_dhabi", "sharjah", "fujairah"])],
        "market": rng.choice(["any", "any", "ready", "offplan"]),
    }
    optional = {
        "areas": ["Dubai Marina"],
        "must_have": ["vacant"],
        "size_min_sqft": 700,
        "handover_by": "2028-Q4",
        "bedrooms_min": 1,
        "property_types": ["apartment"],
        "budget_includes_costs": True,
        "sale_type": rng.choice(["primary", "resale"]),
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
    benchmark = price / size * rng.choice([0.75, 0.9, 1.0, 1.1, 1.3, 1.6])
    data = {
        "url": f"https://x.example/{rng.randrange(10 ** 9)}",
        "price_aed": price,
        "evidence": rng.choice(["page", "page", "page", "card", "lead"]),
        "emirate": emirate,
        "community": rng.choice(["Dubai Marina", "Business Bay"]),
        "building": "Tower",
        "property_type": "apartment",
        "bedrooms": 1,
        "bathrooms": 1,
        "size_sqft": size,
        "completion": "offplan" if offplan else "ready",
        "sale_type": rng.choice(["primary", "resale"]),
        "observed_on": (today - timedelta(days=rng.choice([0, 2, 10, 40]))).isoformat(),
        "benchmark_psf": round(benchmark),
        "benchmark_count": rng.choice([2, 6, 12]),
        "annual_rent_aed": price * rng.choice([0.04, 0.06, 0.08]),
        "rent_count": rng.choice([1, 6]),
        "service_charge_psf": rng.choice([10, 18, 45]),
        "verified": rng.choice([True, False]),
        "permit_number": rng.choice(["7100000001", None]),
        "listed_days_ago": rng.choice([3, 120]),
        "building_sales_12m": rng.choice([2, 15]),
        "tags": rng.choice([[], ["vacant"], ["tenanted"]]),
        "from_price": rng.random() < 0.15,
        "price_corroborated": rng.choice([True, False, None]),
    }
    if offplan:
        data.update(
            handover=rng.choice(["2026-06", "2028-Q2", "2029-Q4"]),
            payment_plan=rng.choice([{"on_booking": 20, "on_handover": 80}, {"on_booking": 40, "post_handover": 60}]),
            post_handover_months=rng.choice([0, 24]),
            developer_tier=rng.choice([1, 2, 3]),
            registration_verified=rng.choice([True, True, False, None]),
            project_number="2927",
            register_started=rng.choice(["2024-01", "2026-06"]),
            register_completion=rng.choice(["2026-03", "2028-Q4", "2029-Q2"]),
            register_progress_pct=rng.choice([5, 40, 80]),
            register_inspected_on=rng.choice(["2026-11-01", "2026-05-01"]),
            ready_benchmark_psf=round(benchmark * rng.choice([0.6, 0.9])),
            transfer_fee_waived=rng.random() < 0.3,
        )
    return {name: value for name, value in data.items() if value is not None}


def verdict(brief, listing, today):
    result = assess(Brief.from_dict(brief), [Listing.from_dict(listing)], today)
    return result.ranked[0].verdict if result.ranked else "rejected"


@pytest.fixture(scope="module")
def cases(request):
    from tests.property_scout.conftest import TODAY

    rng = random.Random(20261120)
    built = []
    for _ in range(RECORDS):
        brief = generated_brief(rng)
        built.append((brief, generated_listing(rng, brief["emirates"][0], TODAY)))
    return built, TODAY


def test_the_generated_records_do_reach_the_shortlist(cases):
    built, today = cases
    verdicts = [verdict(brief, listing, today) for brief, listing in built]
    assert verdicts.count("shortlist") >= 5 and len(set(verdicts)) >= 5


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
