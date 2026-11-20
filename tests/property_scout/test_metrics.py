from datetime import date

import pytest

from property_scout.metrics import (
    benchmark_gap,
    expected_handover,
    gross_yield,
    months_to_handover,
    net_yield,
    plan_cashflows,
    plan_value,
    schedule_shortfall,
)


class TestBenchmarkGap:
    def test_negative_when_below_benchmark(self, make_listing):
        listing = make_listing(price_aed=1_500_000, size_sqft=750, benchmark_psf=2500)
        assert benchmark_gap(listing) == pytest.approx(-0.20)

    def test_a_round_ratio_is_not_a_hair_under_itself(self, make_listing):
        assert benchmark_gap(make_listing(price_aed=2_400 * 750, size_sqft=750, benchmark_psf=2_000)) == 0.2
        assert benchmark_gap(make_listing(price_aed=1_400 * 750, size_sqft=750, benchmark_psf=2_000)) == -0.3

    def test_unknown_without_benchmark_or_size(self, make_listing):
        assert benchmark_gap(make_listing()) is None
        assert benchmark_gap(make_listing(size_sqft=None, benchmark_psf=2000)) is None


class TestYields:
    def test_gross_yield(self, make_listing):
        assert gross_yield(make_listing(price_aed=2_000_000, annual_rent_aed=130_000)) == pytest.approx(0.065)

    def test_gross_yield_unknown_without_rent(self, make_listing):
        assert gross_yield(make_listing()) is None

    def test_net_yield_deducts_service_charge_and_running_costs(self, make_listing):
        listing = make_listing(price_aed=2_000_000, size_sqft=1000, annual_rent_aed=130_000, service_charge_psf=18)
        net = net_yield(listing, total_cost=2_100_000, running_cost_ratio=0.10)
        assert net == pytest.approx((130_000 - 18_000 - 13_000) / 2_100_000)

    @pytest.mark.parametrize("missing", ["annual_rent_aed", "service_charge_psf", "size_sqft"])
    def test_net_yield_needs_rent_service_charge_and_size(self, make_listing, missing):
        facts = {"annual_rent_aed": 100_000, "service_charge_psf": 15, "size_sqft": 750}
        facts[missing] = None
        assert net_yield(make_listing(**facts), 2_000_000, 0.10) is None


class TestExpectedHandover:
    def test_the_register_date_is_used_while_it_is_ahead(self, make_listing, today):
        listing = make_listing(completion="offplan", handover="2027-Q2", register_completion="2028-Q3")
        assert expected_handover(listing, today) == "2028-Q3"

    def test_a_lapsed_register_date_gives_way_to_a_later_advertised_one(self, make_listing, today):
        listing = make_listing(completion="offplan", handover="2028-Q2", register_completion="2026-06")
        assert expected_handover(listing, today) == "2028-Q2"

    def test_nothing_is_expected_once_every_stated_date_has_passed(self, make_listing, today):
        assert expected_handover(make_listing(completion="offplan", handover="2026-Q1", register_completion="2026-06"), today) is None
        assert expected_handover(make_listing(completion="offplan"), today) is None

    def test_a_date_is_compared_to_the_day(self, make_listing, today):
        earlier_this_month = today.replace(day=1).isoformat()
        assert expected_handover(make_listing(completion="offplan", handover=earlier_this_month), today) is None
        assert expected_handover(make_listing(completion="offplan", handover=today.isoformat()), today) == today.isoformat()
        assert expected_handover(make_listing(completion="offplan", handover=today.strftime("%Y-%m")), today) is not None


class TestScheduleShortfall:
    register = dict(completion="offplan", register_started="2024-11", register_completion="2028-11", register_inspected_on="2026-11-01")

    def test_compares_time_elapsed_with_the_share_built(self, make_listing):
        elapsed, built = schedule_shortfall(make_listing(register_progress_pct=10, **self.register))
        assert elapsed == pytest.approx(0.49, abs=0.01) and built == 0.10

    @pytest.mark.parametrize("missing", ["register_started", "register_completion", "register_inspected_on", "register_progress_pct"])
    def test_needs_both_ends_the_progress_and_its_date(self, make_listing, missing):
        facts = {**self.register, "register_progress_pct": 10, missing: None}
        assert schedule_shortfall(make_listing(**facts)) is None

    def test_the_advertised_date_stands_in_for_a_missing_register_date(self, make_listing):
        facts = {**self.register, "register_completion": None, "handover": "2028-11", "register_progress_pct": 10}
        assert schedule_shortfall(make_listing(**facts))[0] == pytest.approx(0.49, abs=0.01)

    def test_a_completion_date_before_the_start_gives_no_comparison(self, make_listing):
        facts = {**self.register, "register_started": "2029-01", "register_progress_pct": 10}
        assert schedule_shortfall(make_listing(**facts)) is None

    def test_elapsed_time_is_kept_between_nothing_and_everything(self, make_listing):
        late = {**self.register, "register_inspected_on": "2030-01-01", "register_progress_pct": 90}
        early = {**self.register, "register_inspected_on": "2024-01-01", "register_progress_pct": 0}
        assert schedule_shortfall(make_listing(**late))[0] == 1 and schedule_shortfall(make_listing(**early))[0] == 0


class TestMonthsToHandover:
    def test_counts_to_the_start_of_the_period(self, make_listing, today):
        listing = make_listing(completion="offplan", handover="2028-Q4")
        assert months_to_handover(listing, today) == 23

    def test_the_register_date_is_used_over_the_advert(self, make_listing, today):
        listing = make_listing(completion="offplan", handover="2027-11", register_completion="2028-05")
        assert months_to_handover(listing, today) == 18

    def test_a_past_date_is_now(self, make_listing, today):
        assert months_to_handover(make_listing(completion="offplan", handover="2026-Q1"), today) == 0

    def test_a_lapsed_register_date_does_not_bring_the_handover_forward(self, make_listing, today):
        listing = make_listing(completion="offplan", handover="2028-Q4", register_completion="2026-06")
        assert months_to_handover(listing, today) == 23

    def test_a_finished_unit_is_handed_over_now(self, make_listing, today):
        listing = make_listing(payment_plan={"on_booking": 60, "post_handover": 40}, post_handover_months=24)
        assert months_to_handover(listing, today) == 0

    @pytest.mark.parametrize("completion", ["offplan", None])
    def test_unknown_when_money_is_deferred_to_an_undated_handover(self, make_listing, today, completion):
        listing = make_listing(completion=completion, payment_plan={"on_booking": 20, "on_handover": 80})
        assert months_to_handover(listing, today) is None


class TestPaymentPlanValue:
    def test_no_plan_no_value(self, make_listing, today):
        assert plan_value(make_listing(), today, 0.07) is None

    def test_deferred_plan_without_handover_is_unknown(self, make_listing, today):
        listing = make_listing(completion="offplan", payment_plan={"on_booking": 20, "on_handover": 80})
        assert plan_value(listing, today, 0.07) is None

    def test_cashflows_sum_to_the_whole_price(self, make_listing, today):
        listing = make_listing(
            completion="offplan",
            handover="2028-Q4",
            payment_plan={"on_booking": 10, "during_construction": 40, "on_handover": 20, "post_handover": 30},
            post_handover_months=36,
        )
        flows = plan_cashflows(listing, today)
        assert sum(share for _, share in flows) == pytest.approx(1.0)
        assert max(month for month, _ in flows) == 23 + 36

    def test_a_post_handover_share_without_a_period_falls_due_on_handover(self, make_listing, today):
        listing = make_listing(completion="offplan", handover="2027-11", payment_plan={"on_booking": 40, "post_handover": 60})
        assert plan_cashflows(listing, today) == [(0, 0.4), (12, 0.6)]

    def test_paying_everything_today_is_worth_full_price(self, make_listing, today):
        value = plan_value(make_listing(payment_plan={"on_booking": 100}), today, 0.07)
        assert value.present_value_ratio == pytest.approx(1.0)
        assert value.deferral_benefit == pytest.approx(0.0)
        assert value.booking_pct == 100

    def test_single_payment_at_handover_discounts_exactly(self, make_listing):
        listing = make_listing(completion="offplan", handover="2027-11", payment_plan={"on_handover": 100})
        value = plan_value(listing, date(2026, 11, 19), 0.08)
        assert value.months_to_handover == 12
        assert value.present_value_ratio == pytest.approx(1 / 1.08)

    def test_construction_instalments_fall_at_the_end_of_each_month(self, make_listing):
        listing = make_listing(completion="offplan", handover="2027-01", payment_plan={"during_construction": 100})
        rate = 0.12
        monthly = (1 + rate) ** (1 / 12) - 1
        value = plan_value(listing, date(2026, 11, 19), rate)
        assert value.months_to_handover == 2
        assert value.present_value_ratio == pytest.approx(0.5 / (1 + monthly) + 0.5 / (1 + monthly) ** 2)

    def test_a_vague_date_cannot_flatter_the_plan(self, make_listing, today):
        plan = {"on_booking": 20, "on_handover": 80}
        quarter = make_listing(completion="offplan", handover="2028-Q4", payment_plan=plan)
        month = make_listing(completion="offplan", handover="2028-10", payment_plan=plan)
        year = make_listing(completion="offplan", handover="2028", payment_plan=plan)
        assert plan_value(quarter, today, 0.06).deferral_benefit == pytest.approx(plan_value(month, today, 0.06).deferral_benefit)
        assert plan_value(year, today, 0.06).deferral_benefit < plan_value(quarter, today, 0.06).deferral_benefit

    def test_zero_rate_means_no_benefit(self, make_listing, today):
        listing = make_listing(completion="offplan", handover="2029-Q4", payment_plan={"on_booking": 20, "on_handover": 80})
        assert plan_value(listing, today, 0.0).deferral_benefit == pytest.approx(0.0)

    def test_later_payments_are_worth_more_to_the_buyer(self, make_listing, today):
        front = make_listing(completion="offplan", handover="2028-Q4", payment_plan={"on_booking": 80, "on_handover": 20})
        back = make_listing(completion="offplan", handover="2028-Q4", payment_plan={"on_booking": 20, "on_handover": 80})
        assert plan_value(back, today, 0.07).deferral_benefit > plan_value(front, today, 0.07).deferral_benefit

    def test_past_handover_is_treated_as_due_now(self, make_listing, today):
        listing = make_listing(completion="offplan", handover="2026-Q1", payment_plan={"during_construction": 60, "on_handover": 40})
        value = plan_value(listing, today, 0.07)
        assert value.months_to_handover == 0
        assert value.present_value_ratio == pytest.approx(1.0)

    def test_reports_shares_due_at_booking_and_before_handover(self, make_listing, today):
        listing = make_listing(completion="offplan", handover="2028-Q4", payment_plan={"on_booking": 20, "during_construction": 40, "on_handover": 40})
        value = plan_value(listing, today, 0.07)
        assert (value.booking_pct, value.paid_before_handover_pct) == (20, 60)

    @pytest.mark.parametrize("rate, published", [(0.04, 0.026), (0.06, 0.037)])
    def test_matches_a_published_worked_example(self, make_listing, today, rate, published):
        """Deferring 40% of the price over 40 monthly instalments, as worked through in the trade press."""
        listing = make_listing(payment_plan={"on_booking": 60, "post_handover": 40}, post_handover_months=40)
        assert plan_value(listing, today, rate).deferral_benefit == pytest.approx(published, abs=0.0005)
