import pytest

from property_scout.brief import EMIRATES
from property_scout.costs import (
    LTV_CAP_HOME,
    LTV_CAP_HOME_ABOVE_THRESHOLD,
    LTV_CAP_INVESTMENT,
    LTV_CAP_OFFPLAN,
    LTV_HOME_THRESHOLD_AED,
    SCHEDULES,
    VAT,
    acquisition_costs,
    ltv_cap,
)
from property_scout.scoring import assess

PRICE = 2_000_000


def amounts(costs):
    return {item.note.code: item.amount for item in costs.items}


class TestSchedules:
    def test_only_known_emirates_have_schedules(self):
        assert set(SCHEDULES) <= set(EMIRATES)

    @pytest.mark.parametrize("emirate", sorted(SCHEDULES))
    def test_rates_are_fractions(self, emirate):
        schedule = SCHEDULES[emirate]
        assert 0 < schedule.transfer_rate < 0.1
        for rate in (schedule.transfer_rate_gcc, schedule.agency_rate, schedule.mortgage_rate):
            assert rate is None or 0 < rate < 0.1

    @pytest.mark.parametrize("emirate", sorted(set(EMIRATES) - set(SCHEDULES)))
    def test_emirate_without_a_schedule_reports_the_price_only(self, emirate):
        costs = acquisition_costs(PRICE, emirate, "ready", "resale")
        assert not costs.rates_known and costs.items == [] and costs.total_outlay == PRICE


class TestDubai:
    schedule = SCHEDULES["dubai"]

    def test_cash_resale_stack(self):
        got = amounts(acquisition_costs(PRICE, "dubai", "ready", "resale"))
        top_tier = self.schedule.trustee_tiers[-1][1]
        assert got == {
            "cost.transfer_fee": pytest.approx(PRICE * self.schedule.transfer_rate),
            "cost.registration_fee": self.schedule.fixed_ready,
            "cost.trustee_fee": pytest.approx(top_tier * (1 + VAT)),
            "cost.agency_fee": pytest.approx(PRICE * self.schedule.agency_rate * (1 + VAT)),
        }

    def test_trustee_fee_steps_down_below_the_threshold(self):
        threshold, low_fee = self.schedule.trustee_tiers[0]
        below = amounts(acquisition_costs(threshold - 1, "dubai", "ready", "resale"))
        at = amounts(acquisition_costs(threshold, "dubai", "ready", "resale"))
        assert below["cost.trustee_fee"] == pytest.approx(low_fee * (1 + VAT))
        assert at["cost.trustee_fee"] > below["cost.trustee_fee"]

    def test_buying_from_the_developer_has_no_trustee_or_agency_fee(self):
        got = amounts(acquisition_costs(PRICE, "dubai", "offplan", "primary"))
        assert set(got) == {"cost.transfer_fee", "cost.registration_fee"}
        assert got["cost.registration_fee"] == self.schedule.fixed_offplan

    def test_off_plan_resale_uses_the_oqood_trustee_fee(self):
        got = amounts(acquisition_costs(PRICE, "dubai", "offplan", "resale"))
        assert got["cost.trustee_fee"] == pytest.approx(self.schedule.trustee_offplan_resale * (1 + VAT))

    def test_mortgage_adds_registration_on_the_loan_and_fees_stay_in_cash(self):
        cash = acquisition_costs(PRICE, "dubai", "ready", "resale")
        financed = acquisition_costs(PRICE, "dubai", "ready", "resale", "mortgage", 0.75)
        expected = PRICE * 0.75 * self.schedule.mortgage_rate + self.schedule.mortgage_fixed
        assert amounts(financed)["cost.mortgage_registration"] == pytest.approx(expected)
        assert financed.loan == pytest.approx(PRICE * 0.75)
        assert financed.upfront_cash == pytest.approx(PRICE * 0.25 + financed.total_costs)
        assert cash.upfront_cash == cash.total_outlay

    def test_off_plan_is_costed_without_a_loan(self):
        costs = acquisition_costs(PRICE, "dubai", "offplan", "primary", "mortgage", 0.5)
        assert costs.loan == 0 and "cost.mortgage_registration" not in amounts(costs)

    def test_waived_transfer_fee_is_listed_at_zero(self):
        full = acquisition_costs(PRICE, "dubai", "offplan", "primary")
        waived = acquisition_costs(PRICE, "dubai", "offplan", "primary", transfer_fee_waived=True)
        assert amounts(waived)["cost.transfer_fee_waived"] == 0
        assert full.total_costs - waived.total_costs == pytest.approx(PRICE * self.schedule.transfer_rate)

    def test_unknown_sale_type_is_costed_as_a_resale(self):
        assert amounts(acquisition_costs(PRICE, "dubai", "ready", None)) == amounts(
            acquisition_costs(PRICE, "dubai", "ready", "resale")
        )


class TestOtherEmirates:
    def test_abu_dhabi_commission_is_capped(self):
        schedule = SCHEDULES["abu_dhabi"]
        price = 2 * schedule.agency_cap / schedule.agency_rate
        got = amounts(acquisition_costs(price, "abu_dhabi", "ready", "resale"))
        assert got["cost.agency_fee"] == pytest.approx(schedule.agency_cap * (1 + VAT))
        assert got["cost.transfer_fee"] == pytest.approx(price * schedule.transfer_rate)

    @pytest.mark.parametrize("emirate", ["sharjah", "ajman"])
    def test_gcc_nationals_pay_the_lower_rate(self, emirate):
        schedule = SCHEDULES[emirate]
        foreign = amounts(acquisition_costs(PRICE, emirate, "ready", "resale"))
        gcc = amounts(acquisition_costs(PRICE, emirate, "ready", "resale", gcc_national=True))
        assert foreign["cost.transfer_fee"] == pytest.approx(PRICE * schedule.transfer_rate)
        assert gcc["cost.transfer_fee"] == pytest.approx(PRICE * schedule.transfer_rate_gcc)

    def test_gcc_flag_changes_nothing_where_there_is_one_rate(self):
        assert amounts(acquisition_costs(PRICE, "dubai", "ready", "resale", gcc_national=True)) == amounts(
            acquisition_costs(PRICE, "dubai", "ready", "resale")
        )

    def test_ajman_minimum_fee_applies_to_small_purchases(self):
        schedule = SCHEDULES["ajman"]
        price = schedule.transfer_minimum / schedule.transfer_rate / 2
        assert amounts(acquisition_costs(price, "ajman", "ready", "resale"))["cost.transfer_fee"] == schedule.transfer_minimum

    def test_ajman_gcc_nationals_have_their_own_lower_minimum(self):
        schedule = SCHEDULES["ajman"]
        price = schedule.transfer_minimum_gcc / schedule.transfer_rate_gcc / 2
        fee = amounts(acquisition_costs(price, "ajman", "ready", "resale", gcc_national=True))["cost.transfer_fee"]
        assert fee == schedule.transfer_minimum_gcc
        assert 0 < schedule.transfer_minimum_gcc < schedule.transfer_minimum

    @pytest.mark.parametrize("emirate", sorted(SCHEDULES))
    def test_part_published_schedules_are_marked(self, emirate):
        assert acquisition_costs(PRICE, emirate, "ready", "resale").official is SCHEDULES[emirate].official


class TestLendingCaps:
    def test_caps_by_case(self):
        assert ltv_cap(PRICE, "offplan", investment=False) == LTV_CAP_OFFPLAN
        assert ltv_cap(PRICE, "ready", investment=True) == LTV_CAP_INVESTMENT
        assert ltv_cap(LTV_HOME_THRESHOLD_AED, "ready", investment=False) == LTV_CAP_HOME
        assert ltv_cap(LTV_HOME_THRESHOLD_AED + 1, "ready", investment=False) == LTV_CAP_HOME_ABOVE_THRESHOLD

    def test_loan_above_the_cap_is_flagged(self, make_brief, make_listing, today):
        def codes(purpose, ltv, **listing):
            brief = make_brief(purpose=purpose, financing="mortgage", loan_to_value=ltv)
            return {f.code for f in assess(brief, [make_listing(**listing)], today).ranked[0].flags}

        assert "ltv_over_cap" in codes("yield", LTV_CAP_INVESTMENT + 0.05)
        assert "ltv_over_cap" not in codes("end_use", LTV_CAP_HOME)
        assert "offplan_finance" in codes("end_use", 0.5, completion="offplan", sale_type="primary")

    def test_indicative_schedule_is_flagged(self, make_brief, make_listing, today):
        brief = make_brief(emirates=["sharjah"])
        flags = {f.code for f in assess(brief, [make_listing(emirate="sharjah")], today).ranked[0].flags}
        assert "cost_rates_indicative" in flags and "cost_rates_unknown" not in flags

    def test_golden_visa_conditions_are_noted_for_financed_or_off_plan_purchases(self, make_brief, make_listing, today):
        def codes(brief_extra, **listing):
            brief = make_brief(purpose="golden_visa", budget_max=5_000_000, **brief_extra)
            return {f.code for f in assess(brief, [make_listing(price_aed=2_500_000, **listing)], today).ranked[0].flags}

        assert "golden_visa_conditions" not in codes({})
        assert "golden_visa_conditions" in codes({"financing": "mortgage", "loan_to_value": 0.5})
        assert "golden_visa_conditions" in codes({}, completion="offplan", sale_type="primary")
