from datetime import date

import pytest

from property_scout.metrics import benchmark_gap, gross_yield, net_yield, plan_cashflows, plan_value


class TestBenchmarkGap:
    def test_negative_when_below_benchmark(self, make_listing):
        listing = make_listing(price_aed=1_500_000, size_sqft=750, benchmark_psf=2500)
        assert benchmark_gap(listing) == pytest.approx(-0.20)

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

    def test_net_yield_unknown_without_service_charge(self, make_listing):
        assert net_yield(make_listing(annual_rent_aed=100_000), 2_000_000, 0.10) is None


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
        assert max(month for month, _ in flows) == 25 + 36

    def test_paying_everything_today_is_worth_full_price(self, make_listing, today):
        listing = make_listing(payment_plan={"on_booking": 100})
        value = plan_value(listing, today, 0.07)
        assert value.present_value_ratio == pytest.approx(1.0)
        assert value.deferral_benefit == pytest.approx(0.0)

    def test_single_payment_at_handover_discounts_exactly(self, make_listing):
        listing = make_listing(completion="offplan", handover="2027-11", payment_plan={"on_handover": 100})
        value = plan_value(listing, date(2026, 11, 19), 0.08)
        assert value.months_to_handover == 12
        assert value.present_value_ratio == pytest.approx(1 / 1.08)

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

    def test_reports_share_due_before_handover(self, make_listing, today):
        listing = make_listing(completion="offplan", handover="2028-Q4", payment_plan={"on_booking": 20, "during_construction": 40, "on_handover": 40})
        assert plan_value(listing, today, 0.07).paid_before_handover_pct == 60

    @pytest.mark.parametrize("rate, published", [(0.04, 0.026), (0.06, 0.037)])
    def test_matches_a_published_worked_example(self, make_listing, today, rate, published):
        """Deferring 40% of the price over 40 monthly instalments, as worked through in the trade press."""
        listing = make_listing(payment_plan={"on_booking": 60, "post_handover": 40}, post_handover_months=40)
        assert plan_value(listing, today, rate).deferral_benefit == pytest.approx(published, abs=0.0005)
