import re
from datetime import timedelta
from pathlib import Path

import pytest

import property_scout
from property_scout.brief import CRITERIA
from property_scout.comps import MIN_COMPS
from property_scout.costs import GOLDEN_VISA_MIN_AED, LTV_CAP_INVESTMENT
from property_scout.listing import EVIDENCE
from property_scout.messages import TEXT, render
from property_scout.scoring import (
    ASSUMED_YIELD_LOSS,
    CONSIDER_SCORE,
    DEVELOPER_TIER_POINTS,
    EVIDENCE_POINTS,
    FRESH_WITHIN_DAYS,
    IMPLAUSIBLE_GAP,
    IMPLAUSIBLE_GROSS_YIELD,
    INSPECTION_STALE_DAYS,
    LATE_HANDOVER_PENALTY_PER_MONTH,
    LOW_TURNOVER_SALES,
    NET_YIELD_RANGE,
    NEUTRAL,
    OFFPLAN_PREMIUM_LIMIT,
    PARTIAL,
    PROFILES,
    RATED_CONFIDENCE,
    RECENT_WITHIN_DAYS,
    SEVERITIES,
    SHORTLIST_SCORE,
    STALE_AFTER_DAYS,
    TERMS_BEST_BENEFIT,
    UNKNOWN_TIER_POINTS,
    VALUE_BEST_GAP,
    VALUE_WORST_GAP,
    VERDICTS,
    VISA_MARGIN,
    assess,
    weights_for,
)

BENCHMARK = 2400
SIZE = 750
OFFPLAN = {"completion": "offplan", "sale_type": "primary"}


def criterion(assessment, name):
    return next(c for c in assessment.criteria if c.name == name)


def flag_codes(assessment):
    return {flag.code for flag in assessment.flags}


def only(result):
    assert len(result.ranked) == 1
    return result.ranked[0]


def priced(gap):
    return {"price_aed": BENCHMARK * (1 + gap) * SIZE, "size_sqft": SIZE, "benchmark_psf": BENCHMARK, "benchmark_count": MIN_COMPS}


@pytest.fixture
def strong(today):
    """A fully documented, well priced flat: shortlisted unless something holds it back."""
    return {
        **priced(-0.12),
        "annual_rent_aed": 140_000,
        "rent_count": MIN_COMPS,
        "service_charge_psf": 15,
        "permit_number": "7100000001",
        "observed_on": today.isoformat(),
    }


@pytest.fixture
def run(make_brief, make_listing, today):
    def assessed(brief=None, **listing):
        return only(assess(make_brief(**(brief or {})), [make_listing(**listing)], today))

    return assessed


class TestWeights:
    @pytest.mark.parametrize("purpose", sorted(PROFILES))
    def test_every_profile_covers_every_criterion_and_sums_to_one(self, make_brief, purpose):
        weights = weights_for(make_brief(purpose=purpose))
        assert set(weights) == set(CRITERIA)
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_brief_overrides_are_renormalised(self, make_brief):
        weights = weights_for(make_brief(weights={"value": 0, "yield": 0, "fit": 1, "trust": 0, "terms": 0}))
        assert weights["fit"] == pytest.approx(1.0)

    def test_all_zero_weights_are_refused(self, make_brief):
        with pytest.raises(ValueError):
            weights_for(make_brief(weights={name: 0 for name in CRITERIA}))


class TestHardFilters:
    def reasons(self, result):
        assert not result.ranked and len(result.rejected) == 1
        return {note.code for note in result.rejected[0].reasons}

    def test_over_budget(self, make_brief, make_listing, today):
        result = assess(make_brief(budget_max=1_500_000), [make_listing(price_aed=1_800_000)], today)
        assert self.reasons(result) == {"reject.over_budget"}

    def test_budget_can_include_acquisition_costs(self, make_brief, make_listing, today):
        listing = make_listing(price_aed=1_800_000)
        loose = assess(make_brief(budget_max=1_850_000), [listing], today)
        strict = assess(make_brief(budget_max=1_850_000, budget_includes_costs=True), [listing], today)
        assert "costs_exceed_budget" in flag_codes(only(loose))
        assert self.reasons(strict) == {"reject.over_budget_costs"}

    def test_a_price_exactly_on_a_budget_limit_is_inside_it(self, make_brief, make_listing, today):
        listing = make_listing(price_aed=1_800_000)
        assert len(assess(make_brief(budget_max=1_800_000), [listing], today).ranked) == 1
        assert len(assess(make_brief(budget_min=1_800_000), [listing], today).ranked) == 1

    def test_under_minimum(self, make_brief, make_listing, today):
        result = assess(make_brief(budget_min=2_000_000), [make_listing()], today)
        assert self.reasons(result) == {"reject.under_budget"}

    def test_wrong_market(self, make_brief, make_listing, today):
        result = assess(make_brief(market="offplan"), [make_listing(completion="ready")], today)
        assert self.reasons(result) == {"reject.market"}

    def test_unknown_completion_is_kept_and_flagged(self, run):
        assert "completion_unknown" in flag_codes(run({"market": "offplan"}, completion=None))

    def test_wrong_emirate_type_and_bedrooms(self, make_brief, make_listing, today):
        brief = make_brief(emirates=["abu_dhabi"], property_types=["villa"], bedrooms_min=2, bedrooms_max=3)
        result = assess(brief, [make_listing(bedrooms=1)], today)
        assert self.reasons(result) == {"reject.emirate", "reject.type", "reject.beds_low"}

    def test_too_many_bedrooms(self, make_brief, make_listing, today):
        result = assess(make_brief(bedrooms_max=1), [make_listing(bedrooms=3)], today)
        assert self.reasons(result) == {"reject.beds_high"}

    def test_strict_areas_reject_outsiders_but_soft_areas_do_not(self, make_brief, make_listing, today):
        listing = make_listing(community="Business Bay", building="Executive Towers")
        strict = assess(make_brief(areas=["Dubai Marina"], areas_strict=True), [listing], today)
        soft = assess(make_brief(areas=["Dubai Marina"]), [listing], today)
        assert self.reasons(strict) == {"reject.area"}
        assert criterion(only(soft), "fit").score == 0

    def test_an_area_may_be_written_the_short_way(self, make_brief, make_listing, today):
        listing = make_listing(community="Jumeirah Village Circle", building="Bloom Towers")
        assert len(assess(make_brief(areas=["JVC"], areas_strict=True), [listing], today).ranked) == 1

    @pytest.mark.parametrize("area", ["Park Heights", "Acacia B"])
    def test_an_area_may_name_a_sub_community_or_a_building(self, make_brief, make_listing, today, area):
        listing = make_listing(community="Dubai Hills Estate", sub_community="Park Heights", building="Acacia B")
        assert len(assess(make_brief(areas=[area], areas_strict=True), [listing], today).ranked) == 1

    def test_an_area_is_not_matched_on_a_shared_word(self, make_brief, make_listing, today):
        listing = make_listing(community="Dubai Hills Estate", building="Park Heights")
        result = assess(make_brief(areas=["Dubai Marina"], areas_strict=True), [listing], today)
        assert self.reasons(result) == {"reject.area"}

    @pytest.mark.parametrize(
        "term, listing",
        [
            ("marina gate", {}),
            ("Dubai Marina", {}),
            ("tenanted", {"tags": ["Tenanted"]}),
            ("Acme", {"developer": "Acme Properties"}),
            ("JVC", {"community": "Jumeirah Village Circle"}),
        ],
    )
    def test_exclusions_match_places_tags_and_developers(self, make_brief, make_listing, today, term, listing):
        assert self.reasons(assess(make_brief(exclude=[term]), [make_listing(**listing)], today)) == {"reject.excluded"}

    def test_an_exclusion_needs_whole_words(self, make_brief, make_listing, today):
        assert len(assess(make_brief(exclude=["mar"]), [make_listing()], today).ranked) == 1

    def test_golden_visa_needs_the_threshold(self, make_brief, make_listing, today):
        brief = make_brief(purpose="golden_visa", budget_max=3_000_000)
        below = assess(brief, [make_listing(price_aed=GOLDEN_VISA_MIN_AED - 1)], today)
        at = assess(brief, [make_listing(price_aed=GOLDEN_VISA_MIN_AED)], today)
        assert self.reasons(below) == {"reject.golden_visa"}
        assert len(at.ranked) == 1

    def test_a_late_handover_is_rejected_unless_the_deadline_is_soft(self, make_brief, make_listing, today):
        late = make_listing(handover="2028-Q2", **OFFPLAN)
        hard = assess(make_brief(handover_by="2027-Q4"), [late], today)
        soft = assess(make_brief(handover_by="2027-Q4", handover_strict=False), [late], today)
        assert self.reasons(hard) == {"reject.handover"}
        assert "late_handover" in flag_codes(only(soft))

    def test_the_deadline_is_tested_against_the_register_date(self, make_brief, make_listing, today):
        listing = make_listing(handover="2027-Q2", register_completion="2028-Q3", **OFFPLAN)
        assert self.reasons(assess(make_brief(handover_by="2027-Q4"), [listing], today)) == {"reject.handover"}

    def test_a_deadline_does_not_touch_ready_homes(self, make_brief, make_listing, today):
        assert len(assess(make_brief(handover_by="2027-Q4"), [make_listing()], today).ranked) == 1


class TestValue:
    def score_at(self, run, gap, **extra):
        return criterion(run({"budget_max": 10_000_000}, **{**priced(gap), **extra}), "value")

    def test_scale_endpoints_and_level_price(self, run):
        level = 100 * VALUE_WORST_GAP / (VALUE_WORST_GAP - VALUE_BEST_GAP)
        assert self.score_at(run, VALUE_BEST_GAP).score == pytest.approx(100)
        assert self.score_at(run, 0).score == pytest.approx(level)
        assert self.score_at(run, VALUE_WORST_GAP).score == pytest.approx(0)

    def test_a_price_level_with_sold_scores_above_neutral(self, run):
        assert self.score_at(run, 0).score > NEUTRAL

    def test_scale_is_clamped(self, run):
        assert self.score_at(run, VALUE_WORST_GAP * 2).score == 0
        assert self.score_at(run, VALUE_BEST_GAP * 2).score == 100

    @pytest.mark.parametrize("count", [None, 0, MIN_COMPS - 1])
    def test_a_thin_benchmark_counts_for_half_and_is_held_towards_neutral(self, run, count):
        full = self.score_at(run, VALUE_BEST_GAP)
        thin = self.score_at(run, VALUE_BEST_GAP, benchmark_count=count)
        assert full.score == pytest.approx(100) and full.evidence == 1.0
        assert thin.score == pytest.approx(NEUTRAL + (100 - NEUTRAL) * PARTIAL) and thin.evidence == PARTIAL
        assert [note.code for note in thin.notes] == ["value.scored", "value.thin"]

    def test_thin_benchmark_is_flagged(self, run):
        assert "thin_benchmark" in flag_codes(run(**{**priced(0), "benchmark_count": MIN_COMPS - 1}))
        assert "thin_benchmark" in flag_codes(run(**{**priced(0), "benchmark_count": None}))
        assert "thin_benchmark" not in flag_codes(run(**priced(0)))

    def test_unknown_without_benchmark(self, run):
        assessment = run()
        value = criterion(assessment, "value")
        assert value.score is None and value.evidence == 0
        assert "no_benchmark" in flag_codes(assessment)

    def test_unknown_without_size(self, run):
        assessment = run(size_sqft=None, benchmark_psf=BENCHMARK)
        assert criterion(assessment, "value").score is None
        assert "size_missing" in flag_codes(assessment) and "no_benchmark" not in flag_codes(assessment)

    def test_implausibly_cheap_is_critical_and_ranked_last(self, make_brief, make_listing, today):
        bait = make_listing(url="https://a.example/bait", **priced(IMPLAUSIBLE_GAP - 0.01))
        fair = make_listing(url="https://a.example/fair", building="Other Tower", **priced(0))
        result = assess(make_brief(), [bait, fair], today)
        assert [a.listing.url for a in result.ranked] == ["https://a.example/fair", "https://a.example/bait"]
        assert result.ranked[1].verdict == "verify_first"
        assert "implausible_price" in flag_codes(result.ranked[1])
        assert "implausible_price" not in flag_codes(result.ranked[0])


class TestYield:
    def test_net_yield_is_used_when_service_charge_is_known(self, run):
        assessment = run(annual_rent_aed=130_000, service_charge_psf=18, rent_count=MIN_COMPS)
        result = criterion(assessment, "yield")
        low, high = NET_YIELD_RANGE
        assert [note.code for note in result.notes] == ["yield.net"] and result.evidence == 1.0
        assert result.score == pytest.approx(100 * (assessment.net_yield - low) / (high - low))

    @pytest.mark.parametrize("count", [None, MIN_COMPS - 1])
    def test_rent_resting_on_few_contracts_counts_for_half(self, run, count):
        result = criterion(run(annual_rent_aed=130_000, service_charge_psf=18, rent_count=count), "yield")
        assert [note.code for note in result.notes] == ["yield.net", "yield.thin"] and result.evidence == PARTIAL

    def test_a_gross_figure_is_scored_as_an_estimated_net_and_counts_for_half(self, run):
        assessment = run(annual_rent_aed=130_000, rent_count=MIN_COMPS)
        result = criterion(assessment, "yield")
        low, high = NET_YIELD_RANGE
        assert assessment.net_yield is None
        assert result.notes[0].code == "yield.gross" and result.evidence == PARTIAL
        assert result.score == pytest.approx(100 * (assessment.gross_yield - ASSUMED_YIELD_LOSS - low) / (high - low))

    def test_a_gross_figure_never_beats_the_same_rent_properly_costed(self, run):
        costed = criterion(run(annual_rent_aed=130_000, service_charge_psf=5, rent_count=MIN_COMPS), "yield")
        gross = criterion(run(annual_rent_aed=130_000, rent_count=MIN_COMPS), "yield")
        assert gross.score < costed.score

    def test_no_rent_no_score(self, run):
        result = criterion(run(), "yield")
        assert result.score is None and result.evidence == 0

    def test_higher_rent_scores_higher(self, run):
        assert criterion(run(annual_rent_aed=140_000), "yield").score > criterion(run(annual_rent_aed=90_000), "yield").score

    def test_projected_rent_on_off_plan_is_flagged(self, run):
        assert "projected_rent" in flag_codes(run(annual_rent_aed=120_000, **OFFPLAN))
        assert "projected_rent" not in flag_codes(run(annual_rent_aed=120_000))

    def test_an_incredible_yield_is_critical(self, run):
        price = 1_800_000
        over = run(price_aed=price, annual_rent_aed=price * IMPLAUSIBLE_GROSS_YIELD + 1_000)
        under = run(price_aed=price, annual_rent_aed=price * IMPLAUSIBLE_GROSS_YIELD - 1_000)
        assert "implausible_yield" in flag_codes(over) and over.verdict == "verify_first"
        assert "implausible_yield" not in flag_codes(under)


class TestFit:
    def test_not_applicable_without_preferences(self, run):
        fit = criterion(run(), "fit")
        assert fit.applicable is False and fit.score is None

    def test_preferred_area_and_must_haves(self, run):
        fit = criterion(run({"areas": ["Dubai Marina"], "must_have": ["sea view", "balcony"]}, tags=["Sea View"]), "fit")
        assert fit.score == pytest.approx((100 + 50) / 2)

    def test_a_strict_area_is_a_filter_and_earns_no_points(self, run):
        fit = criterion(run({"areas": ["Dubai Marina"], "areas_strict": True}), "fit")
        assert fit.applicable is False
        mixed = criterion(run({"areas": ["Dubai Marina"], "areas_strict": True, "must_have": ["balcony"]}), "fit")
        assert mixed.score == 0

    def test_small_units_lose_fit_gradually(self, run):
        brief = {"size_min_sqft": 1000}
        exact = criterion(run(brief, size_sqft=1000), "fit").score
        short = criterion(run(brief, size_sqft=900), "fit").score
        tiny = criterion(run(brief, size_sqft=700), "fit").score
        assert exact == 100 and short == pytest.approx(50) and tiny == 0

    def test_a_soft_deadline_costs_fit_by_the_month(self, run):
        brief = {"handover_by": "2027-Q4", "handover_strict": False}
        on_time = run(brief, handover="2027-Q2", **OFFPLAN)
        late = run(brief, handover="2028-Q2", **OFFPLAN)
        assert criterion(on_time, "fit").score == 100
        assert criterion(late, "fit").score == pytest.approx(100 - 6 * LATE_HANDOVER_PENALTY_PER_MONTH)
        assert "late_handover" in flag_codes(late) and "late_handover" not in flag_codes(on_time)

    def test_an_undated_handover_is_neutral_and_flagged(self, run):
        assessment = run({"handover_by": "2027-Q4"}, **OFFPLAN)
        fit = criterion(assessment, "fit")
        assert fit.score == NEUTRAL and fit.notes[0].code == "fit.handover_unknown"
        assert "handover_unknown" in flag_codes(assessment)


class TestTrust:
    @pytest.mark.parametrize("level", EVIDENCE)
    def test_evidence_level_is_one_of_three_checks_on_a_ready_home(self, run, level):
        trust = criterion(run(evidence=level), "trust")
        assert trust.score == pytest.approx(100 * EVIDENCE_POINTS[level] / 3)
        assert trust.evidence == 1.0

    def test_checks_that_were_skipped_score_nothing(self, run):
        notes = [note.code for note in criterion(run(), "trust").notes]
        assert notes == ["trust.evidence_page", "trust.not_dated", "trust.unchecked"]

    def test_a_dated_permitted_page_is_fully_trusted(self, run, today):
        assessment = run(permit_number="7122473800", observed_on=today.isoformat())
        assert criterion(assessment, "trust").score == 100
        assert "no_permit" not in flag_codes(assessment)

    def test_portal_verification_stands_in_for_the_permit_and_its_absence_is_noted(self, run, today):
        assessment = run(verified=True, observed_on=today.isoformat())
        assert criterion(assessment, "trust").score == 100
        assert "no_permit" in flag_codes(assessment)

    def test_an_advert_the_portal_did_not_verify_says_so(self, run):
        assert "trust.unverified" in [note.code for note in criterion(run(verified=False), "trust").notes]

    def test_the_permit_reminder_is_for_emirates_that_issue_one(self, make_brief, make_listing, today):
        sharjah = only(assess(make_brief(emirates=["sharjah"]), [make_listing(emirate="sharjah")], today))
        assert "no_permit" not in flag_codes(sharjah)

    @pytest.mark.parametrize(
        "days, points",
        [(0, 1.0), (FRESH_WITHIN_DAYS, 1.0), (FRESH_WITHIN_DAYS + 1, 0.5), (RECENT_WITHIN_DAYS, 0.5), (RECENT_WITHIN_DAYS + 1, 0.0)],
    )
    def test_trust_fades_as_the_sighting_ages(self, run, today, days, points):
        seen = (today - timedelta(days=days)).isoformat()
        assert criterion(run(observed_on=seen), "trust").score == pytest.approx(100 * (EVIDENCE_POINTS["page"] + points) / 3)

    def test_a_sighting_dated_tomorrow_is_a_time_zone_not_an_error(self, run, today):
        assessment = run(observed_on=(today + timedelta(days=1)).isoformat())
        assert "trust.seen_today" in [note.code for note in criterion(assessment, "trust").notes]
        assert "seen_in_future" not in flag_codes(assessment)

    def test_a_sighting_dated_later_than_that_earns_nothing_and_is_flagged(self, run, today):
        assessment = run(observed_on=(today + timedelta(days=2)).isoformat())
        assert criterion(assessment, "trust").score == pytest.approx(100 * EVIDENCE_POINTS["page"] / 3)
        assert "seen_in_future" in flag_codes(assessment)

    @pytest.mark.parametrize("tier", sorted(DEVELOPER_TIER_POINTS))
    def test_developer_tier_is_one_of_five_checks_on_off_plan(self, run, tier):
        score = criterion(run(developer_tier=tier, **OFFPLAN), "trust").score
        assert score == pytest.approx(100 * (EVIDENCE_POINTS["page"] + DEVELOPER_TIER_POINTS[tier]) / 5)

    def test_an_unassessed_developer_scores_like_an_unproven_one(self, run):
        score = criterion(run(**OFFPLAN), "trust").score
        assert score == pytest.approx(100 * (EVIDENCE_POINTS["page"] + UNKNOWN_TIER_POINTS) / 5)
        assert UNKNOWN_TIER_POINTS == min(DEVELOPER_TIER_POINTS.values())

    def test_a_fully_checked_off_plan_offer_is_fully_trusted(self, run, today):
        facts = dict(developer_tier=1, registration_verified=True, verified=True, observed_on=today.isoformat())
        assert criterion(run(**facts, **OFFPLAN), "trust").score == 100

    def test_registration_states(self, run):
        unchecked, found, missing = (run(registration_verified=state, **OFFPLAN) for state in (None, True, False))
        assert "registration_unchecked" in flag_codes(unchecked)
        assert not {"registration_unchecked", "registration_not_found"} & flag_codes(found)
        assert "registration_not_found" in flag_codes(missing) and missing.verdict == "verify_first"
        assert criterion(found, "trust").score > criterion(unchecked, "trust").score == criterion(missing, "trust").score


class TestTerms:
    def test_not_applicable_to_a_resale_even_with_the_developers_plan_attached(self, run):
        plain = criterion(run(), "terms")
        with_plan = criterion(run(completion="offplan", sale_type="resale", handover="2028-Q4", payment_plan={"on_booking": 20, "on_handover": 80}), "terms")
        assert plain.applicable is False and with_plan.applicable is False
        assert with_plan.notes[0].code == "terms.resale"

    def test_not_applicable_to_a_finished_home_sold_without_a_plan(self, run):
        terms = criterion(run(sale_type="primary"), "terms")
        assert terms.applicable is False and terms.notes[0].code == "terms.na"

    def test_a_finished_home_sold_by_the_developer_on_a_plan_is_scored(self, run):
        terms = criterion(run(sale_type="primary", payment_plan={"on_booking": 60, "post_handover": 40}, post_handover_months=40), "terms")
        assert terms.applicable and 0 < terms.score < 100

    def test_unknown_for_primary_off_plan_without_a_plan(self, run):
        terms = criterion(run(**OFFPLAN), "terms")
        assert terms.applicable and terms.score is None and terms.evidence == 0

    def test_back_loaded_plan_scores_higher(self, run):
        def score(plan):
            return criterion(run(handover="2029-Q4", payment_plan=plan, **OFFPLAN), "terms").score

        assert score({"on_booking": 20, "on_handover": 80}) > score({"on_booking": 80, "on_handover": 20})

    def test_score_is_the_deferral_benefit_on_the_scale(self, run):
        assessment = run(handover="2028-Q4", payment_plan={"on_booking": 20, "during_construction": 40, "on_handover": 40}, **OFFPLAN)
        expected = 100 * min(assessment.plan.deferral_benefit / TERMS_BEST_BENEFIT, 1)
        assert 0 < expected < 100
        assert criterion(assessment, "terms").score == pytest.approx(expected)

    def test_a_waived_transfer_fee_counts_as_part_of_the_terms(self, run):
        plan = dict(handover="2027-Q2", payment_plan={"on_booking": 50, "on_handover": 50}, **OFFPLAN)
        plain = criterion(run(**plan), "terms")
        waived = criterion(run(transfer_fee_waived=True, **plan), "terms")
        assert waived.score > plain.score
        assert [note.code for note in waived.notes] == ["terms.scored", "terms.waiver"]

    def test_brief_discount_rate_changes_the_value_of_the_plan(self, run):
        plan = dict(handover="2029-Q4", payment_plan={"on_booking": 20, "on_handover": 80}, **OFFPLAN)
        low = run({"discount_rate": 0.02}, **plan).plan.deferral_benefit
        high = run({"discount_rate": 0.10}, **plan).plan.deferral_benefit
        assert high > low


class TestScoreAndCompleteness:
    def test_no_data_scores_neutral_with_zero_completeness(self, run):
        assessment = run({"weights": {"value": 1, "yield": 1, "fit": 0, "trust": 0, "terms": 0}})
        assert (assessment.score, assessment.confidence, assessment.verdict) == (NEUTRAL, 0, "needs_data")

    def test_score_is_the_weighted_mean_of_the_criteria_that_apply(self, run, strong):
        assessment = run({"areas": ["Dubai Marina"]}, **strong)
        weights = PROFILES["balanced"]
        live = [c for c in assessment.criteria if c.applicable]
        assert {c.name for c in live} == {"value", "yield", "fit", "trust"}
        total = sum(weights[c.name] for c in live)
        expected = sum(weights[c.name] * c.score for c in live) / total
        assert assessment.score == pytest.approx(expected, abs=0.05)
        assert assessment.confidence == 1.0

    def test_completeness_is_the_weighted_share_of_evidence(self, run):
        assessment = run(**{**priced(0), "benchmark_count": None})
        weights = PROFILES["balanced"]
        total = weights["value"] + weights["yield"] + weights["trust"]
        assert assessment.confidence == pytest.approx((weights["value"] * PARTIAL + weights["trust"]) / total, abs=0.005)

    def test_zero_weight_criteria_do_not_dilute_completeness(self, run):
        assessment = run({"purpose": "end_use", "areas": ["Dubai Marina"]}, **priced(0))
        assert PROFILES["end_use"]["yield"] == 0
        assert assessment.confidence == 1.0

    def test_weight_on_criteria_that_do_not_apply_leaves_nothing_to_rate(self, run):
        assessment = run({"weights": {"value": 0, "yield": 0, "fit": 1, "trust": 0, "terms": 1}})
        assert (assessment.score, assessment.confidence, assessment.verdict) == (NEUTRAL, 0, "needs_data")

    def test_rated_boundary(self, run):
        def at(trust_weight):
            return run({"weights": {"value": 1 - trust_weight, "yield": 0, "fit": 0, "trust": trust_weight, "terms": 0}})

        assert at(RATED_CONFIDENCE).rated and at(RATED_CONFIDENCE).verdict != "needs_data"
        assert not at(RATED_CONFIDENCE - 0.05).rated and at(RATED_CONFIDENCE - 0.05).verdict == "needs_data"


class TestVerdict:
    def test_a_documented_well_priced_page_is_shortlisted(self, run, strong):
        assessment = run(**strong)
        assert assessment.score >= SHORTLIST_SCORE and assessment.confidence == 1.0
        assert assessment.verdict == "shortlist" and not assessment.has_critical_flag

    @pytest.mark.parametrize(
        "score, verdict",
        [(SHORTLIST_SCORE, "shortlist"), (SHORTLIST_SCORE - 0.5, "consider"), (CONSIDER_SCORE, "consider"), (CONSIDER_SCORE - 1, "pass")],
    )
    def test_verdict_boundaries(self, run, score, verdict):
        gap = VALUE_WORST_GAP + (VALUE_BEST_GAP - VALUE_WORST_GAP) * score / 100
        assessment = run({"budget_max": 5_000_000, "weights": {"value": 1, "yield": 0, "fit": 0, "trust": 0, "terms": 0}}, **priced(gap))
        assert assessment.score == pytest.approx(score, abs=0.05)
        assert assessment.verdict == verdict

    def test_only_an_opened_page_can_be_shortlisted(self, run, strong):
        card = run(evidence="card", **strong)
        assert card.score >= SHORTLIST_SCORE and card.verdict == "consider"
        assert "card_only" in flag_codes(card)
        lead = run(evidence="lead", **strong)
        assert lead.verdict == "verify_first" and "unverified_lead" in flag_codes(lead)

    def test_off_plan_is_not_shortlisted_until_its_registration_is_confirmed(self, run, strong):
        facts = {**strong, **OFFPLAN, "handover": "2028-Q4", "developer_tier": 1, "payment_plan": {"on_booking": 20, "on_handover": 80}}
        unchecked = run(**facts)
        confirmed = run(registration_verified=True, **facts)
        assert unchecked.score >= SHORTLIST_SCORE and unchecked.verdict == "consider"
        assert confirmed.verdict == "shortlist"

    def test_a_tenanted_home_is_not_shortlisted_for_own_use(self, run, strong):
        brief = {"purpose": "end_use", "areas": ["Dubai Marina"]}
        tenanted = run(brief, tags=["tenanted"], **strong)
        vacant = run(brief, tags=["vacant"], **strong)
        investor = run({"purpose": "yield"}, tags=["tenanted"], **strong)
        assert tenanted.verdict == "consider" and "tenanted" in flag_codes(tenanted)
        assert vacant.verdict == "shortlist"
        assert investor.verdict == "shortlist" and "tenanted" not in flag_codes(investor)

    @pytest.mark.parametrize("cap, verdict, severity", [("consider", "consider", "warning"), ("pass", "pass", "warning"), ("verify_first", "verify_first", "critical")])
    def test_the_analyst_can_hold_an_offer_back_with_a_reason(self, run, strong, cap, verdict, severity):
        assessment = run(analyst_cap=cap, analyst_note="floor plan shows a studio, not one bedroom", **strong)
        flag = next(flag for flag in assessment.flags if flag.code == "analyst")
        assert assessment.verdict == verdict and flag.severity == severity
        assert "floor plan shows a studio" in render(flag.note)

    def test_an_analyst_cap_never_lifts_a_verdict(self, run):
        assert run(analyst_cap="consider", analyst_note="checked").verdict == "needs_data"

    def test_a_price_far_above_registered_sales_is_a_pass_whatever_else_is_good(self, run, strong):
        dear = {**strong, **priced(VALUE_WORST_GAP + 0.05)}
        assessment = run({"budget_max": 5_000_000, "weights": {"value": 0.1, "yield": 0, "fit": 0, "trust": 0.9, "terms": 0}}, **dear)
        assert assessment.score >= SHORTLIST_SCORE
        assert assessment.verdict == "pass" and "overpriced" in flag_codes(assessment)

    def test_a_thin_benchmark_cannot_force_a_pass(self, run, strong):
        dear = {**strong, **priced(VALUE_WORST_GAP + 0.05), "benchmark_count": MIN_COMPS - 1}
        assessment = run({"budget_max": 5_000_000, "weights": {"value": 0.1, "yield": 0, "fit": 0, "trust": 0.9, "terms": 0}}, **dear)
        assert "overpriced" in flag_codes(assessment) and assessment.verdict == "shortlist"

    def test_overpriced_low_yield_unit_is_a_pass(self, run):
        weak = run(price_aed=2_400_000, benchmark_psf=BENCHMARK, benchmark_count=MIN_COMPS, annual_rent_aed=70_000, rent_count=MIN_COMPS, service_charge_psf=30, verified=False)
        assert weak.score < CONSIDER_SCORE and weak.verdict == "pass"


class TestRanking:
    def test_rated_offers_come_before_undocumented_ones_whatever_the_score(self, make_brief, make_listing, today):
        documented = make_listing(url="https://a.example/known", building="Known Tower", annual_rent_aed=110_000, rent_count=MIN_COMPS, **priced(0.10))
        blank = make_listing(url="https://a.example/blank", building="Blank Tower")
        result = assess(make_brief(purpose="yield", budget_max=3_000_000), [blank, documented], today)
        known, unknown = result.ranked
        assert known.listing.url == "https://a.example/known"
        assert unknown.score > known.score
        assert (known.verdict, unknown.verdict) == ("pass", "needs_data")

    def test_thin_evidence_cannot_outrank_full_evidence(self, make_brief, make_listing, today, strong):
        thin = make_listing(url="https://a.example/thin", building="Thin Tower", **priced(-0.14))
        full = make_listing(url="https://a.example/full", building="Full Tower", **strong)
        result = assess(make_brief(), [thin, full], today)
        assert result.ranked[0].listing.url == "https://a.example/full"
        assert result.ranked[0].confidence > result.ranked[1].confidence

    def test_verdicts_are_listed_in_order_with_unverified_offers_last(self, make_brief, make_listing, today, strong):
        listings = [
            make_listing(url="https://a.example/lead", building="A", evidence="lead", **{**strong, "permit_number": "71"}),
            make_listing(url="https://a.example/blank", building="B"),
            make_listing(url="https://a.example/card", building="C", evidence="card", **{**strong, "permit_number": "72"}),
            make_listing(url="https://a.example/page", building="D", **{**strong, "permit_number": "73"}),
        ]
        ranked = assess(make_brief(), listings, today).ranked
        assert [a.verdict for a in ranked] == ["shortlist", "consider", "needs_data", "verify_first"]
        assert [VERDICTS.index(a.verdict) for a in ranked] == sorted(VERDICTS.index(a.verdict) for a in ranked)

    def test_ties_go_to_the_cheaper_then_to_the_address(self, make_brief, make_listing, today):
        a = make_listing(url="https://a.example/1", building="A", price_aed=1_900_000)
        b = make_listing(url="https://a.example/2", building="B", price_aed=1_700_000)
        c = make_listing(url="https://a.example/0", building="C", price_aed=1_900_000)
        result = assess(make_brief(), [a, b, c], today)
        assert [x.listing.url for x in result.ranked] == ["https://a.example/2", "https://a.example/0", "https://a.example/1"]


class TestEmirateAndCosts:
    def test_a_listing_without_an_emirate_takes_the_briefs_only_emirate(self, run):
        assessment = run(emirate=None)
        assert assessment.listing.emirate == "dubai"
        assert assessment.costs.rates_known and "emirate_missing" not in flag_codes(assessment)

    @pytest.mark.parametrize("emirates", [[], ["dubai", "abu_dhabi"]])
    def test_it_is_not_guessed_when_the_brief_does_not_settle_it(self, run, emirates):
        assessment = run({"emirates": emirates}, emirate=None)
        assert "emirate_missing" in flag_codes(assessment)
        assert assessment.costs.total_outlay == assessment.listing.price_aed

    def test_part_published_and_unpublished_schedules_are_flagged_differently(self, run):
        assert "cost_rates_partial" in flag_codes(run({"emirates": ["sharjah"]}, emirate="sharjah"))
        assert "cost_rates_unknown" in flag_codes(run({"emirates": ["fujairah"]}, emirate="fujairah"))

    def test_a_loan_above_the_ceiling_is_flagged_and_costed_at_the_ceiling(self, run):
        assessment = run({"purpose": "yield", "financing": "mortgage", "loan_to_value": LTV_CAP_INVESTMENT + 0.15})
        assert "ltv_capped" in flag_codes(assessment)
        assert assessment.costs.ltv_used == pytest.approx(LTV_CAP_INVESTMENT)

    def test_own_use_is_lent_against_as_a_first_home_unless_stated_otherwise(self, run):
        ask = {"financing": "mortgage", "loan_to_value": LTV_CAP_INVESTMENT + 0.15}
        assert "ltv_capped" not in flag_codes(run({"purpose": "end_use", **ask}))
        assert "ltv_capped" in flag_codes(run({"purpose": "end_use", "first_home": False, **ask}))

    def test_off_plan_and_non_resident_finance_are_flagged(self, run):
        assert "offplan_finance" in flag_codes(run({"financing": "mortgage"}, **OFFPLAN))
        assert "non_resident_finance" in flag_codes(run({"financing": "mortgage", "resident": False}))
        assert "non_resident_finance" not in flag_codes(run({"resident": False}))

    def test_an_ignored_waiver_and_the_abu_dhabi_fee_rules_are_flagged(self, run):
        assert "waiver_ignored" in flag_codes(run(transfer_fee_waived=True))
        abu_dhabi = {"emirates": ["abu_dhabi"]}
        assert "transfer_split" in flag_codes(run(abu_dhabi, emirate="abu_dhabi", community="Yas Island"))
        assert "transfer_seller_pays" in flag_codes(run(abu_dhabi, emirate="abu_dhabi", community="Al Reem Island"))

    def test_cash_due_at_booking_is_the_first_instalment_plus_fees(self, run):
        assessment = run(handover="2028-Q4", payment_plan={"on_booking": 20, "on_handover": 80}, **OFFPLAN)
        assert assessment.cash_at_booking == pytest.approx(assessment.listing.price_aed * 0.20 + assessment.costs.total_costs)
        assert run().cash_at_booking is None


class TestGoldenVisa:
    brief = {"purpose": "golden_visa", "budget_max": 5_000_000}

    def test_a_price_just_over_the_threshold_is_flagged(self, run):
        near = run(self.brief, price_aed=GOLDEN_VISA_MIN_AED * (1 + VISA_MARGIN) - 1)
        clear = run(self.brief, price_aed=GOLDEN_VISA_MIN_AED * (1 + VISA_MARGIN))
        assert "visa_margin" in flag_codes(near) and "visa_margin" not in flag_codes(clear)

    def test_a_benchmark_implying_less_than_the_threshold_is_flagged(self, run):
        size = 1_000
        low = run(self.brief, price_aed=2_300_000, size_sqft=size, benchmark_psf=GOLDEN_VISA_MIN_AED / size - 100, benchmark_count=MIN_COMPS)
        fine = run(self.brief, price_aed=2_300_000, size_sqft=size, benchmark_psf=GOLDEN_VISA_MIN_AED / size + 100, benchmark_count=MIN_COMPS)
        assert "visa_benchmark_below" in flag_codes(low) and "visa_benchmark_below" not in flag_codes(fine)

    def test_conditions_are_noted_for_financed_or_off_plan_purchases(self, run):
        assert "visa_conditions" not in flag_codes(run(self.brief, price_aed=2_500_000))
        assert "visa_conditions" in flag_codes(run({**self.brief, "financing": "mortgage"}, price_aed=2_500_000))
        assert "visa_conditions" in flag_codes(run(self.brief, price_aed=2_500_000, **OFFPLAN))

    def test_none_of_it_concerns_other_buyers(self, run):
        assert not {"visa_margin", "visa_conditions"} & flag_codes(run({"budget_max": 5_000_000}, price_aed=2_050_000, **OFFPLAN))


class TestOtherFlags:
    def test_stale_listing(self, run):
        assert "stale" in flag_codes(run(listed_days_ago=STALE_AFTER_DAYS + 1))
        assert "stale" not in flag_codes(run(listed_days_ago=STALE_AFTER_DAYS))

    def test_a_from_price_is_flagged(self, run):
        assert "from_price" in flag_codes(run(from_price=True)) and "from_price" not in flag_codes(run())

    def test_unproven_developer(self, run):
        assert "developer_unproven" in flag_codes(run(developer_tier=3, **OFFPLAN))
        assert "developer_unproven" not in flag_codes(run(developer_tier=2, **OFFPLAN))

    def test_large_premium_over_ready_stock_is_flagged_for_off_plan_only(self, run):
        ready_psf = 1_500
        dear = ready_psf * (1 + OFFPLAN_PREMIUM_LIMIT + 0.05) * SIZE
        usual = ready_psf * (1 + OFFPLAN_PREMIUM_LIMIT - 0.05) * SIZE
        assert "offplan_premium" in flag_codes(run(price_aed=dear, ready_benchmark_psf=ready_psf, **OFFPLAN))
        assert "offplan_premium" not in flag_codes(run(price_aed=usual, ready_benchmark_psf=ready_psf, **OFFPLAN))
        assert "offplan_premium" not in flag_codes(run(price_aed=dear, ready_benchmark_psf=ready_psf))

    def test_a_register_date_that_has_passed_is_flagged(self, run):
        assert "register_overdue" in flag_codes(run(register_completion="2026-Q2", **OFFPLAN))
        assert "register_overdue" not in flag_codes(run(register_completion="2026-11", **OFFPLAN))

    def test_an_advertised_handover_that_has_passed_is_flagged_when_the_register_is_silent(self, run):
        assert "handover_passed" in flag_codes(run(handover="2026-Q2", **OFFPLAN))
        both = flag_codes(run(handover="2026-Q2", register_completion="2027-Q2", **OFFPLAN))
        assert "handover_passed" not in both and "handover_mismatch" in both

    def test_a_register_date_later_than_the_advert_is_flagged(self, run):
        assert "handover_mismatch" in flag_codes(run(handover="2028-Q2", register_completion="2028-Q4", **OFFPLAN))
        assert "handover_mismatch" not in flag_codes(run(handover="2028-Q4", register_completion="2028-Q2", **OFFPLAN))

    def test_an_old_site_inspection_is_noted(self, run, today):
        old = (today - timedelta(days=INSPECTION_STALE_DAYS + 1)).isoformat()
        recent = (today - timedelta(days=INSPECTION_STALE_DAYS)).isoformat()
        assert "inspection_stale" in flag_codes(run(register_inspected_on=old, **OFFPLAN))
        assert "inspection_stale" not in flag_codes(run(register_inspected_on=recent, **OFFPLAN))

    def test_a_building_that_rarely_trades_is_noted(self, run):
        assert "low_turnover" in flag_codes(run(building_sales_12m=LOW_TURNOVER_SALES - 1))
        assert "low_turnover" not in flag_codes(run(building_sales_12m=LOW_TURNOVER_SALES))
        assert "low_turnover" not in flag_codes(run())

    def test_flags_are_listed_most_severe_first(self, run):
        assessment = run({"financing": "mortgage"}, evidence="lead", registration_verified=False, developer_tier=3, **OFFPLAN)
        order = [SEVERITIES.index(flag.severity) for flag in assessment.flags]
        assert order == sorted(order) and len(set(order)) == len(SEVERITIES)

    def test_a_note_about_costs_does_not_come_before_a_later_warning(self, run):
        brief = {"emirates": ["abu_dhabi"], "financing": "mortgage", "resident": False}
        codes = [flag.code for flag in run(brief, emirate="abu_dhabi", community="Yas Island").flags]
        assert codes.index("non_resident_finance") < codes.index("transfer_split")


class TestDuplicatesInAssessment:
    def test_duplicates_are_folded_and_reported(self, make_brief, make_listing, today):
        result = assess(make_brief(), [make_listing(), make_listing(url="https://b.example/9", price_aed=1_820_000)], today)
        assert result.received == 2
        assert [d.url for d in only(result).duplicates] == ["https://b.example/9"]
        assert "advertised_lower" not in flag_codes(only(result))

    def test_an_advert_at_the_same_price_is_not_called_cheaper(self, make_brief, make_listing, today):
        result = assess(make_brief(), [make_listing(), make_listing(url="https://b.example/9")], today)
        assert len(only(result).duplicates) == 1 and "advertised_lower" not in flag_codes(only(result))

    def test_a_cheaper_advert_of_weaker_evidence_is_pointed_out(self, make_brief, make_listing, today):
        page = make_listing(url="https://a.example/page")
        card = make_listing(url="https://a.example/search", evidence="card", price_aed=1_760_000)
        assessment = only(assess(make_brief(), [page, card], today))
        flag = next(flag for flag in assessment.flags if flag.code == "advertised_lower")
        assert assessment.listing.url == "https://a.example/page"
        assert flag.note.params == {"price": 1_760_000} and flag.severity == "info"

    def test_an_advert_outside_the_brief_is_rejected_before_folding(self, make_brief, make_listing, today):
        inside = make_listing(url="https://a.example/in", price_aed=1_800_000)
        outside = make_listing(url="https://a.example/out", price_aed=1_860_000)
        result = assess(make_brief(budget_max=1_820_000), [inside, outside], today)
        assert only(result).duplicates == []
        assert [r.listing.url for r in result.rejected] == ["https://a.example/out"]

    def test_the_merged_offer_is_scored_on_what_every_advert_showed(self, make_brief, make_listing, today):
        bare = make_listing(url="https://a.example/1")
        informed = make_listing(url="https://b.example/2", price_aed=1_820_000, **{k: v for k, v in priced(0).items() if k.startswith("benchmark")})
        assert criterion(only(assess(make_brief(), [bare, informed], today)), "value").score is not None


class TestMessages:
    def scenarios(self, make_brief, make_listing, today):
        plan = {"on_booking": 20, "during_construction": 40, "on_handover": 40}
        old = (today - timedelta(days=200)).isoformat()
        cases = [
            ({"areas": ["Dubai Marina"], "must_have": ["sea view"], "size_min_sqft": 800, "purpose": "end_use", "budget_max": 1_850_000, "financing": "mortgage", "loan_to_value": 0.95, "resident": False, "first_home": False},
             dict(benchmark_psf=BENCHMARK, benchmark_count=2, annual_rent_aed=120_000, service_charge_psf=16, verified=True, permit_number="7", observed_on="2026-11-10", listed_days_ago=200, tags=["tenanted"], building_sales_12m=2, transfer_fee_waived=True, analyst_cap="consider", analyst_note="view is of the car park")),
            ({"handover_by": "2027-Q4", "handover_strict": False, "financing": "mortgage"},
             dict(handover="2028-Q4", register_completion="2029-Q2", register_inspected_on=old, payment_plan=plan, developer_tier=3, registration_verified=False, annual_rent_aed=100_000, from_price=True, ready_benchmark_psf=1_000, transfer_fee_waived=True, **OFFPLAN)),
            ({"handover_by": "2027-Q4"}, dict(developer_tier=1, registration_verified=True, **OFFPLAN)),
            ({}, dict(handover="2026-Q1", **OFFPLAN)),
            ({}, dict(register_completion="2026-Q1", register_progress_pct=80, **OFFPLAN)),
            ({"emirates": []}, dict(emirate=None, completion=None, size_sqft=None, evidence="lead", observed_on="2027-01-01", verified=False)),
            ({}, dict(evidence="card", annual_rent_aed=900_000, **priced(-0.5))),
            ({}, dict(annual_rent_aed=120_000, rent_count=9, service_charge_psf=15, observed_on=today.isoformat(), sale_type="primary", **priced(0.3))),
            ({"emirates": ["sharjah"]}, dict(emirate="sharjah")),
            ({"emirates": ["fujairah"]}, dict(emirate="fujairah")),
            ({"emirates": ["abu_dhabi"]}, dict(emirate="abu_dhabi", community="Al Reem Island")),
            ({"emirates": ["abu_dhabi"]}, dict(emirate="abu_dhabi", community="Yas Island")),
            ({"purpose": "golden_visa", "budget_max": 5_000_000, "financing": "mortgage"}, dict(price_aed=2_050_000, size_sqft=1_000, benchmark_psf=1_800)),
            ({"budget_max": 1_000_000}, dict()),
            ({"budget_max": 1_850_000, "budget_includes_costs": True}, dict()),
            ({"budget_min": 2_000_000}, dict()),
            ({"market": "offplan", "emirates": ["ajman"], "property_types": ["villa"], "bedrooms_min": 3}, dict()),
            ({"bedrooms_max": 0, "areas": ["JVC"], "areas_strict": True, "exclude": ["marina"], "purpose": "golden_visa"}, dict()),
            ({"handover_by": "2027-Q1"}, dict(handover="2028-Q1", **OFFPLAN)),
            ({"handover_by": "2027-Q4", "areas": ["Business Bay"]}, dict(handover="2027-Q2", verified=True, **OFFPLAN)),
        ]
        results = [assess(make_brief(**brief), [make_listing(**listing)], today) for brief, listing in cases]
        results.append(assess(make_brief(), [make_listing(url="https://a.example/p"), make_listing(url="https://a.example/c", evidence="card", price_aed=1_750_000)], today))
        return results

    def notes(self, results):
        found = []
        for result in results:
            for a in result.ranked:
                found += [n for c in a.criteria for n in c.notes] + [f.note for f in a.flags] + [i.note for i in a.costs.items]
            found += [n for r in result.rejected for n in r.reasons]
        return found

    def test_every_sentence_in_the_catalogue_is_reachable_and_renders(self, make_brief, make_listing, today):
        notes = self.notes(self.scenarios(make_brief, make_listing, today))
        assert {note.code for note in notes} == set(TEXT["en"])
        for lang in TEXT:
            for note in notes:
                assert "{" not in render(note, lang), note.code

    def test_languages_define_the_same_codes(self):
        assert set(TEXT["en"]) == set(TEXT["ru"])

    def test_every_code_named_in_the_engine_is_in_the_catalogue(self):
        source = "".join(
            path.read_text(encoding="utf-8")
            for path in Path(property_scout.__file__).parent.glob("*.py")
            if path.name != "messages.py"
        )
        named = set(re.findall(r'"((?:value|yield|fit|trust|terms|flag|reject|cost)\.[a-z_]+)"', source))
        named |= {f"flag.{code}" for code in re.findall(r'add\("(?:critical|warning|info)", "([a-z_0-9]+)"', source)}
        assert named and named <= set(TEXT["en"])
