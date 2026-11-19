import pytest

from property_scout.brief import CRITERIA
from property_scout.comps import MIN_COMPS
from property_scout.costs import GOLDEN_VISA_MIN_AED
from property_scout.messages import TEXT, render
from property_scout.scoring import (
    CONSIDER_SCORE,
    DEVELOPER_TIER_POINTS,
    EVIDENCE_POINTS,
    IMPLAUSIBLE_GAP,
    NEUTRAL,
    OFFPLAN_PREMIUM_LIMIT,
    PROFILES,
    RATED_CONFIDENCE,
    SHORTLIST_SCORE,
    STALE_AFTER_DAYS,
    VALUE_BEST_GAP,
    VALUE_WORST_GAP,
    assess,
    weights_for,
)

BENCHMARK = 2400


def criterion(assessment, name):
    return next(c for c in assessment.criteria if c.name == name)


def flag_codes(assessment):
    return {flag.code for flag in assessment.flags}


def only(result):
    assert len(result.ranked) == 1
    return result.ranked[0]


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
        assert len(loose.ranked) == 1
        assert self.reasons(strict) == {"reject.over_budget_costs"}

    def test_under_minimum(self, make_brief, make_listing, today):
        result = assess(make_brief(budget_min=2_000_000), [make_listing()], today)
        assert self.reasons(result) == {"reject.under_budget"}

    def test_wrong_market(self, make_brief, make_listing, today):
        result = assess(make_brief(market="offplan"), [make_listing(completion="ready")], today)
        assert self.reasons(result) == {"reject.market"}

    def test_unknown_completion_is_kept_and_flagged(self, make_brief, make_listing, today):
        assessment = only(assess(make_brief(market="offplan"), [make_listing(completion=None)], today))
        assert "completion_unknown" in flag_codes(assessment)

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

    def test_exclusions_match_places_and_tags(self, make_brief, make_listing, today):
        by_place = assess(make_brief(exclude=["marina gate"]), [make_listing()], today)
        by_tag = assess(make_brief(exclude=["tenanted"]), [make_listing(tags=["Tenanted"])], today)
        assert self.reasons(by_place) == {"reject.excluded"}
        assert self.reasons(by_tag) == {"reject.excluded"}

    def test_golden_visa_needs_the_threshold(self, make_brief, make_listing, today):
        brief = make_brief(purpose="golden_visa", budget_max=3_000_000)
        below = assess(brief, [make_listing(price_aed=GOLDEN_VISA_MIN_AED - 1)], today)
        at = assess(brief, [make_listing(price_aed=GOLDEN_VISA_MIN_AED)], today)
        assert self.reasons(below) == {"reject.golden_visa"}
        assert len(at.ranked) == 1


class TestValue:
    def score_at(self, gap, make_brief, make_listing, today):
        listing = make_listing(price_aed=BENCHMARK * (1 + gap) * 750, size_sqft=750, benchmark_psf=BENCHMARK)
        return criterion(only(assess(make_brief(budget_max=10_000_000), [listing], today)), "value").score

    def test_scale_endpoints_and_level_price(self, make_brief, make_listing, today):
        level = 100 * VALUE_WORST_GAP / (VALUE_WORST_GAP - VALUE_BEST_GAP)
        assert self.score_at(VALUE_BEST_GAP, make_brief, make_listing, today) == pytest.approx(100)
        assert self.score_at(0, make_brief, make_listing, today) == pytest.approx(level, abs=0.1)
        assert self.score_at(VALUE_WORST_GAP, make_brief, make_listing, today) == pytest.approx(0)

    def test_a_price_level_with_sold_scores_above_neutral(self, make_brief, make_listing, today):
        assert self.score_at(0, make_brief, make_listing, today) > NEUTRAL

    def test_scale_is_clamped(self, make_brief, make_listing, today):
        assert self.score_at(VALUE_WORST_GAP * 2, make_brief, make_listing, today) == 0

    def test_unknown_without_benchmark(self, make_brief, make_listing, today):
        assessment = only(assess(make_brief(), [make_listing()], today))
        assert criterion(assessment, "value").score is None
        assert "no_benchmark" in flag_codes(assessment)

    def test_unknown_without_size(self, make_brief, make_listing, today):
        assessment = only(assess(make_brief(), [make_listing(size_sqft=None, benchmark_psf=BENCHMARK)], today))
        assert criterion(assessment, "value").score is None
        assert "size_missing" in flag_codes(assessment)

    def test_implausibly_cheap_is_critical_and_ranked_last(self, make_brief, make_listing, today):
        bait = make_listing(url="https://a.example/bait", price_aed=BENCHMARK * (1 + IMPLAUSIBLE_GAP) * 750 - 1, benchmark_psf=BENCHMARK)
        fair = make_listing(url="https://a.example/fair", building="Other Tower", price_aed=BENCHMARK * 750, benchmark_psf=BENCHMARK)
        result = assess(make_brief(), [bait, fair], today)
        assert [a.listing.url for a in result.ranked] == ["https://a.example/fair", "https://a.example/bait"]
        assert result.ranked[1].verdict == "verify_first"
        assert "implausible_price" in flag_codes(result.ranked[1])


class TestYield:
    def test_net_yield_is_used_when_service_charge_is_known(self, make_brief, make_listing, today):
        listing = make_listing(annual_rent_aed=130_000, service_charge_psf=18)
        assessment = only(assess(make_brief(), [listing], today))
        assert assessment.net_yield is not None
        assert criterion(assessment, "yield").notes[0].code == "yield.net"

    def test_gross_yield_is_the_fallback(self, make_brief, make_listing, today):
        assessment = only(assess(make_brief(), [make_listing(annual_rent_aed=130_000)], today))
        assert assessment.net_yield is None
        assert criterion(assessment, "yield").notes[0].code == "yield.gross"

    def test_higher_rent_scores_higher(self, make_brief, make_listing, today):
        low = only(assess(make_brief(), [make_listing(annual_rent_aed=90_000)], today))
        high = only(assess(make_brief(), [make_listing(annual_rent_aed=140_000)], today))
        assert criterion(high, "yield").score > criterion(low, "yield").score

    def test_projected_rent_on_off_plan_is_flagged(self, make_brief, make_listing, today):
        listing = make_listing(completion="offplan", sale_type="primary", annual_rent_aed=120_000)
        assert "projected_rent" in flag_codes(only(assess(make_brief(), [listing], today)))


class TestFit:
    def test_not_applicable_without_preferences(self, make_brief, make_listing, today):
        fit = criterion(only(assess(make_brief(), [make_listing()], today)), "fit")
        assert fit.applicable is False

    def test_preferred_area_and_must_haves(self, make_brief, make_listing, today):
        brief = make_brief(areas=["Dubai Marina"], must_have=["sea view", "balcony"])
        fit = criterion(only(assess(brief, [make_listing(tags=["Sea View"])], today)), "fit")
        assert fit.score == pytest.approx((100 + 50) / 2)

    def test_small_units_lose_fit_gradually(self, make_brief, make_listing, today):
        brief = make_brief(size_min_sqft=1000)
        exact = criterion(only(assess(brief, [make_listing(size_sqft=1000)], today)), "fit").score
        short = criterion(only(assess(brief, [make_listing(size_sqft=900)], today)), "fit").score
        tiny = criterion(only(assess(brief, [make_listing(size_sqft=700)], today)), "fit").score
        assert exact == 100 and 0 < short < 100 and tiny == 0

    def test_late_handover_costs_fit_and_raises_a_flag(self, make_brief, make_listing, today):
        brief = make_brief(handover_by="2027-Q4")
        on_time = make_listing(completion="offplan", sale_type="primary", handover="2027-Q2")
        late = make_listing(completion="offplan", sale_type="primary", handover="2028-Q2")
        good = only(assess(brief, [on_time], today))
        bad = only(assess(brief, [late], today))
        assert criterion(good, "fit").score == 100
        assert criterion(bad, "fit").score < 100
        assert "late_handover" in flag_codes(bad) and "late_handover" not in flag_codes(good)


class TestTrust:
    @pytest.mark.parametrize("level", sorted(EVIDENCE_POINTS))
    def test_evidence_level_sets_the_starting_point(self, make_brief, make_listing, today, level):
        assessment = only(assess(make_brief(), [make_listing(evidence=level)], today))
        assert criterion(assessment, "trust").score == pytest.approx(100 * EVIDENCE_POINTS[level])

    def test_a_lead_is_never_shortlisted_and_ranks_below_opened_pages(self, make_brief, make_listing, today):
        strong = dict(price_aed=BENCHMARK * 0.88 * 750, benchmark_psf=BENCHMARK, annual_rent_aed=140_000, service_charge_psf=15)
        lead = make_listing(url="https://a.example/lead", building="Lead Tower", evidence="lead", **strong)
        page = make_listing(url="https://a.example/page", building="Page Tower")
        result = assess(make_brief(), [lead, page], today)
        assert [a.listing.url for a in result.ranked] == ["https://a.example/page", "https://a.example/lead"]
        assert result.ranked[1].verdict == "verify_first"
        assert "unverified_lead" in flag_codes(result.ranked[1])

    def test_a_card_is_noted_as_such(self, make_brief, make_listing, today):
        card = only(assess(make_brief(), [make_listing(evidence="card")], today))
        page = only(assess(make_brief(), [make_listing()], today))
        assert "card_only" in flag_codes(card) and "card_only" not in flag_codes(page)

    def test_missing_permit_is_a_note_not_a_penalty(self, make_brief, make_listing, today):
        assessment = only(assess(make_brief(), [make_listing(verified=True)], today))
        assert criterion(assessment, "trust").score == 100
        assert "no_permit" in flag_codes(assessment)

    def test_permit_verification_and_recency_add_up(self, make_brief, make_listing, today):
        listing = make_listing(permit_number="7122473800", verified=True, observed_on=today.isoformat())
        assessment = only(assess(make_brief(), [listing], today))
        assert criterion(assessment, "trust").score == 100
        assert "no_permit" not in flag_codes(assessment)

    def test_old_sightings_and_unverified_adverts_lose_trust(self, make_brief, make_listing, today):
        listing = make_listing(evidence="lead", verified=False, observed_on="2026-09-01")
        assert criterion(only(assess(make_brief(), [listing], today)), "trust").score == 0

    @pytest.mark.parametrize("tier", sorted(DEVELOPER_TIER_POINTS))
    def test_developer_tier_drives_off_plan_trust(self, make_brief, make_listing, today, tier):
        listing = make_listing(completion="offplan", sale_type="primary", developer_tier=tier)
        score = criterion(only(assess(make_brief(), [listing], today)), "trust").score
        assert score == pytest.approx(100 * (EVIDENCE_POINTS["page"] + DEVELOPER_TIER_POINTS[tier]) / 2)

    def test_registration_states(self, make_brief, make_listing, today):
        def run(state):
            listing = make_listing(completion="offplan", sale_type="primary", registration_verified=state)
            return only(assess(make_brief(), [listing], today))

        assert "registration_unchecked" in flag_codes(run(None))
        assert not {"registration_unchecked", "registration_not_found"} & flag_codes(run(True))
        missing = run(False)
        assert "registration_not_found" in flag_codes(missing)
        assert missing.verdict == "verify_first"


class TestTerms:
    def test_not_applicable_to_a_plain_resale(self, make_brief, make_listing, today):
        assert criterion(only(assess(make_brief(), [make_listing()], today)), "terms").applicable is False

    def test_unknown_for_primary_off_plan_without_a_plan(self, make_brief, make_listing, today):
        listing = make_listing(completion="offplan", sale_type="primary")
        terms = criterion(only(assess(make_brief(), [listing], today)), "terms")
        assert terms.applicable and terms.score is None

    def test_back_loaded_plan_scores_higher(self, make_brief, make_listing, today):
        def run(plan):
            listing = make_listing(completion="offplan", sale_type="primary", handover="2029-Q4", payment_plan=plan)
            return criterion(only(assess(make_brief(), [listing], today)), "terms").score

        assert run({"on_booking": 20, "on_handover": 80}) > run({"on_booking": 80, "on_handover": 20})

    def test_brief_discount_rate_changes_the_value_of_the_plan(self, make_brief, make_listing, today):
        listing = make_listing(completion="offplan", sale_type="primary", handover="2029-Q4", payment_plan={"on_booking": 20, "on_handover": 80})
        low = only(assess(make_brief(discount_rate=0.02), [listing], today)).plan.deferral_benefit
        high = only(assess(make_brief(discount_rate=0.10), [listing], today)).plan.deferral_benefit
        assert high > low


class TestScoreAndVerdict:
    def test_no_data_scores_neutral_with_zero_confidence(self, make_brief, make_listing, today):
        brief = make_brief(weights={"value": 1, "yield": 1, "fit": 0, "trust": 0, "terms": 0})
        assessment = only(assess(brief, [make_listing()], today))
        assert assessment.score == NEUTRAL
        assert assessment.confidence == 0
        assert assessment.verdict == "needs_data"

    def test_a_documented_average_offer_ranks_above_an_undocumented_one(self, make_brief, make_listing, today):
        documented = make_listing(
            url="https://a.example/known",
            building="Known Tower",
            price_aed=BENCHMARK * 1.10 * 750,
            benchmark_psf=BENCHMARK,
            annual_rent_aed=110_000,
        )
        blank = make_listing(url="https://a.example/blank", building="Blank Tower")
        result = assess(make_brief(purpose="yield", budget_max=3_000_000), [blank, documented], today)
        known, unknown = result.ranked
        assert known.listing.url == "https://a.example/known"
        assert unknown.score > known.score
        assert known.verdict in ("consider", "pass") and unknown.verdict == "needs_data"

    def test_rated_boundary(self, make_brief, make_listing, today):
        def run(trust_weight):
            brief = make_brief(weights={"value": 1 - trust_weight, "yield": 0, "fit": 0, "trust": trust_weight, "terms": 0})
            return only(assess(brief, [make_listing()], today))

        assert run(RATED_CONFIDENCE).rated and run(RATED_CONFIDENCE).verdict != "needs_data"
        assert not run(RATED_CONFIDENCE - 0.05).rated

    def test_thin_evidence_cannot_outrank_full_evidence(self, make_brief, make_listing, today):
        thin = make_listing(url="https://a.example/thin", building="Thin Tower", price_aed=BENCHMARK * 0.86 * 750, benchmark_psf=BENCHMARK)
        full = make_listing(
            url="https://a.example/full",
            building="Full Tower",
            price_aed=BENCHMARK * 0.90 * 750,
            benchmark_psf=BENCHMARK,
            annual_rent_aed=140_000,
            service_charge_psf=15,
            verified=True,
            permit_number="71",
            observed_on=today.isoformat(),
        )
        result = assess(make_brief(), [thin, full], today)
        assert result.ranked[0].listing.url == "https://a.example/full"
        assert result.ranked[0].confidence > result.ranked[1].confidence

    def test_shortlist_needs_both_score_and_confidence(self, make_brief, make_listing, today):
        strong = make_listing(
            price_aed=BENCHMARK * 0.88 * 750,
            benchmark_psf=BENCHMARK,
            annual_rent_aed=140_000,
            service_charge_psf=15,
            verified=True,
            observed_on=today.isoformat(),
        )
        assessment = only(assess(make_brief(), [strong], today))
        assert assessment.score >= SHORTLIST_SCORE and assessment.confidence >= RATED_CONFIDENCE
        assert assessment.verdict == "shortlist"

    def test_overpriced_low_yield_unit_is_a_pass(self, make_brief, make_listing, today):
        weak = make_listing(price_aed=2_400_000, benchmark_psf=BENCHMARK, annual_rent_aed=70_000, service_charge_psf=30, verified=False)
        assessment = only(assess(make_brief(), [weak], today))
        assert assessment.score < CONSIDER_SCORE
        assert assessment.verdict == "pass"

    def test_zero_weight_criteria_do_not_dilute_confidence(self, make_brief, make_listing, today):
        brief = make_brief(purpose="end_use", areas=["Dubai Marina"])
        listing = make_listing(benchmark_psf=BENCHMARK, verified=True)
        assert only(assess(brief, [listing], today)).confidence == 1.0

    def test_ranking_is_by_score_then_price(self, make_brief, make_listing, today):
        a = make_listing(url="https://a.example/1", building="A", price_aed=1_900_000)
        b = make_listing(url="https://a.example/2", building="B", price_aed=1_700_000)
        result = assess(make_brief(), [a, b], today)
        assert [x.listing.url for x in result.ranked] == ["https://a.example/2", "https://a.example/1"]


class TestOtherFlags:
    def test_stale_listing(self, make_brief, make_listing, today):
        stale = only(assess(make_brief(), [make_listing(listed_days_ago=STALE_AFTER_DAYS + 1)], today))
        fresh = only(assess(make_brief(), [make_listing(listed_days_ago=STALE_AFTER_DAYS)], today))
        assert "stale" in flag_codes(stale) and "stale" not in flag_codes(fresh)

    def test_tenanted_matters_only_to_an_end_user(self, make_brief, make_listing, today):
        listing = make_listing(tags=["tenanted"])
        assert "tenanted" in flag_codes(only(assess(make_brief(purpose="end_use"), [listing], today)))
        assert "tenanted" not in flag_codes(only(assess(make_brief(purpose="yield"), [listing], today)))

    def test_costs_pushing_past_budget_are_noted(self, make_brief, make_listing, today):
        assessment = only(assess(make_brief(budget_max=1_850_000), [make_listing(price_aed=1_800_000)], today))
        assert "costs_exceed_budget" in flag_codes(assessment)

    def test_unproven_developer(self, make_brief, make_listing, today):
        listing = make_listing(completion="offplan", sale_type="primary", developer_tier=3)
        assert "developer_unproven" in flag_codes(only(assess(make_brief(), [listing], today)))

    def test_large_premium_over_ready_stock_is_flagged_for_off_plan_only(self, make_brief, make_listing, today):
        ready_psf = 1_500
        dear = ready_psf * (1 + OFFPLAN_PREMIUM_LIMIT + 0.05) * 750
        usual = ready_psf * (1 + OFFPLAN_PREMIUM_LIMIT - 0.05) * 750

        def codes(price, completion, sale_type):
            listing = make_listing(price_aed=price, completion=completion, sale_type=sale_type, ready_benchmark_psf=ready_psf)
            return flag_codes(only(assess(make_brief(), [listing], today)))

        assert "offplan_premium" in codes(dear, "offplan", "primary")
        assert "offplan_premium" not in codes(usual, "offplan", "primary")
        assert "offplan_premium" not in codes(dear, "ready", "resale")

    def test_benchmark_on_few_sales_is_flagged(self, make_brief, make_listing, today):
        def codes(count):
            listing = make_listing(benchmark_psf=BENCHMARK, benchmark_count=count)
            return flag_codes(only(assess(make_brief(), [listing], today)))

        assert "thin_benchmark" in codes(MIN_COMPS - 1)
        assert "thin_benchmark" not in codes(MIN_COMPS)
        assert "thin_benchmark" not in codes(None)

    def test_emirate_without_a_cost_table_is_flagged(self, make_brief, make_listing, today):
        assessment = only(assess(make_brief(emirates=[]), [make_listing(emirate=None)], today))
        assert "cost_rates_unknown" in flag_codes(assessment)
        assert assessment.costs.total_outlay == assessment.listing.price_aed


class TestDuplicatesInAssessment:
    def test_duplicates_are_folded_and_reported(self, make_brief, make_listing, today):
        result = assess(make_brief(), [make_listing(), make_listing(url="https://b.example/9", price_aed=1_820_000)], today)
        assert result.received == 2
        assert only(result).duplicate_urls == ["https://b.example/9"]


class TestMessages:
    def test_every_note_renders_in_every_language(self, make_brief, make_listing, today):
        brief = make_brief(areas=["Dubai Marina"], must_have=["sea view"], size_min_sqft=800, handover_by="2027-Q1", purpose="end_use", budget_max=1_850_000)
        listings = [
            make_listing(url="https://a.example/1", benchmark_psf=BENCHMARK, benchmark_count=2, annual_rent_aed=120_000, service_charge_psf=16, verified=True, permit_number="7", observed_on="2026-11-10", listed_days_ago=200, tags=["tenanted"]),
            make_listing(url="https://a.example/2", building="B", completion="offplan", sale_type="primary", handover="2028-Q4", payment_plan={"on_booking": 20, "during_construction": 40, "on_handover": 40}, developer_tier=3, registration_verified=False, annual_rent_aed=100_000),
            make_listing(url="https://a.example/3", building="C", price_aed=900_000, benchmark_psf=BENCHMARK, completion=None, emirate=None),
            make_listing(url="https://a.example/4", building="D", price_aed=9_000_000, bedrooms=6, emirate="ajman", property_type="villa"),
        ]
        result = assess(brief, listings, today)
        notes = [n for a in result.ranked for c in a.criteria for n in c.notes]
        notes += [f.note for a in result.ranked for f in a.flags]
        notes += [i.note for a in result.ranked for i in a.costs.items]
        notes += [n for r in result.rejected for n in r.reasons]
        assert len({n.code for n in notes}) > 20
        for lang in TEXT:
            for note in notes:
                assert "{" not in render(note, lang)

    def test_languages_define_the_same_codes(self):
        assert set(TEXT["en"]) == set(TEXT["ru"])
