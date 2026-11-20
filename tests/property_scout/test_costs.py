import pytest

from property_scout.brief import EMIRATES, NATIONALITIES
from property_scout.costs import (
    LTV_CAP_HOME,
    LTV_CAP_HOME_ABOVE_THRESHOLD,
    LTV_CAP_INVESTMENT,
    LTV_CAP_OFFPLAN,
    LTV_HOME_THRESHOLD_AED,
    LTV_NATIONAL_UPLIFT,
    REDUCED_RATE_NATIONALITIES,
    SCHEDULES,
    SELLER_PAYS_TRANSFER,
    VAT,
    Buyer,
    Purchase,
    acquisition_costs,
    ltv_cap,
)
from property_scout.scoring import cost_flags

PRICE = 2_000_000


def cost(emirate="dubai", price=PRICE, completion="ready", sale_type="resale", community=None, waived=False, **buyer):
    return acquisition_costs(Purchase(price, emirate, community, completion, sale_type, waived), Buyer(**buyer))


def amounts(costs):
    return {item.note.code: item.amount for item in costs.items}


def flags(costs, emirate="dubai"):
    return {flag.code: flag.severity for flag in cost_flags(costs, emirate)}


class TestSchedules:
    def test_only_known_emirates_have_schedules(self):
        assert set(SCHEDULES) <= set(EMIRATES)
        assert set(SELLER_PAYS_TRANSFER) <= set(SCHEDULES)
        assert set(REDUCED_RATE_NATIONALITIES) < set(NATIONALITIES)

    @pytest.mark.parametrize("emirate", sorted(SCHEDULES))
    def test_rates_are_fractions(self, emirate):
        schedule = SCHEDULES[emirate]
        assert 0 < schedule.transfer_rate < 0.1
        for rate in (schedule.transfer_rate_reduced, schedule.agency_rate, schedule.mortgage_rate):
            assert rate is None or 0 < rate < 0.1

    @pytest.mark.parametrize("emirate", sorted(set(EMIRATES) - set(SCHEDULES)) + [None])
    def test_emirate_without_a_schedule_reports_the_price_only(self, emirate):
        costs = cost(emirate)
        assert not costs.rates_known and not costs.complete
        assert costs.items == [] and costs.total_outlay == PRICE

    @pytest.mark.parametrize("emirate", sorted(SCHEDULES))
    def test_part_published_schedules_are_marked(self, emirate):
        costs = cost(emirate)
        assert costs.rates_known and costs.complete is SCHEDULES[emirate].complete
        assert ("cost_rates_partial" in flags(costs, emirate)) is not SCHEDULES[emirate].complete

    def test_the_two_full_schedules_are_dubai_and_abu_dhabi(self):
        assert {name for name, schedule in SCHEDULES.items() if schedule.complete} == {"dubai", "abu_dhabi"}


class TestDubai:
    schedule = SCHEDULES["dubai"]

    def test_cash_resale_stack(self):
        costs = cost()
        top_tier = self.schedule.trustee_tiers[-1][1]
        assert amounts(costs) == {
            "cost.transfer_fee": pytest.approx(PRICE * self.schedule.transfer_rate),
            "cost.registration_fee": self.schedule.fixed_ready,
            "cost.trustee_fee": pytest.approx(top_tier * (1 + VAT)),
            "cost.agency_fee": pytest.approx(PRICE * self.schedule.agency_rate * (1 + VAT)),
        }
        assert costs.total_outlay == pytest.approx(PRICE + sum(amounts(costs).values()))
        assert costs.own_funds == costs.total_outlay and costs.ltv_used is None
        assert flags(costs) == {}

    def test_trustee_fee_steps_up_at_the_threshold(self):
        threshold, low_fee = self.schedule.trustee_tiers[0]
        below = amounts(cost(price=threshold - 1))
        at = amounts(cost(price=threshold))
        assert below["cost.trustee_fee"] == pytest.approx(low_fee * (1 + VAT))
        assert at["cost.trustee_fee"] == pytest.approx(self.schedule.trustee_tiers[1][1] * (1 + VAT))

    def test_buying_from_the_developer_has_no_trustee_or_agency_fee(self):
        got = amounts(cost(completion="offplan", sale_type="primary"))
        assert set(got) == {"cost.transfer_fee", "cost.registration_fee"}
        assert got["cost.registration_fee"] == self.schedule.fixed_offplan

    def test_off_plan_resale_pays_trustee_and_agency_on_the_off_plan_fixed_fee(self):
        got = amounts(cost(completion="offplan", sale_type="resale"))
        assert set(got) == {"cost.transfer_fee", "cost.registration_fee", "cost.trustee_fee", "cost.agency_fee"}
        assert got["cost.registration_fee"] == self.schedule.fixed_offplan

    def test_unknown_sale_type_is_costed_as_a_resale(self):
        assert amounts(cost(sale_type=None)) == amounts(cost(sale_type="resale"))

    @pytest.mark.parametrize("nationality", NATIONALITIES)
    def test_nationality_changes_nothing_where_there_is_one_rate(self, nationality):
        assert amounts(cost(nationality=nationality)) == amounts(cost())


class TestWaiver:
    rate = SCHEDULES["dubai"].transfer_rate

    def test_a_developer_waiver_is_listed_at_zero_and_its_worth_recorded(self):
        full = cost(completion="offplan", sale_type="primary")
        waived = cost(completion="offplan", sale_type="primary", waived=True)
        assert amounts(waived)["cost.transfer_fee_waived"] == 0
        assert "cost.transfer_fee" not in amounts(waived)
        assert full.total_costs - waived.total_costs == pytest.approx(PRICE * self.rate)
        assert waived.waived_rate == self.rate and full.waived_rate == 0
        assert not waived.waiver_ignored

    @pytest.mark.parametrize("sale_type", ["resale", None])
    def test_a_waiver_on_anything_but_a_primary_sale_is_ignored_and_flagged(self, sale_type):
        costs = cost(sale_type=sale_type, waived=True)
        assert amounts(costs)["cost.transfer_fee"] == pytest.approx(PRICE * self.rate)
        assert costs.waiver_ignored and costs.waived_rate == 0
        assert flags(costs)["waiver_ignored"] == "warning"


class TestLending:
    schedule = SCHEDULES["dubai"]

    @pytest.mark.parametrize(
        "price, completion, first_home, national, cap",
        [
            (PRICE, "offplan", True, False, LTV_CAP_OFFPLAN),
            (PRICE, "offplan", True, True, LTV_CAP_OFFPLAN),
            (PRICE, "ready", False, False, LTV_CAP_INVESTMENT),
            (PRICE, "ready", False, True, LTV_CAP_INVESTMENT + LTV_NATIONAL_UPLIFT),
            (LTV_HOME_THRESHOLD_AED, "ready", True, False, LTV_CAP_HOME),
            (LTV_HOME_THRESHOLD_AED, "ready", True, True, LTV_CAP_HOME + LTV_NATIONAL_UPLIFT),
            (LTV_HOME_THRESHOLD_AED + 1, "ready", True, False, LTV_CAP_HOME_ABOVE_THRESHOLD),
            (LTV_HOME_THRESHOLD_AED + 1, "ready", True, True, LTV_CAP_HOME_ABOVE_THRESHOLD + LTV_NATIONAL_UPLIFT),
            (PRICE, None, True, False, LTV_CAP_HOME),
        ],
    )
    def test_ceiling_by_case(self, price, completion, first_home, national, cap):
        assert ltv_cap(price, completion, first_home, national) == pytest.approx(cap)

    def test_a_loan_within_the_ceiling_is_used_as_asked(self):
        asked = LTV_CAP_HOME - 0.05
        costs = cost(financing="mortgage", loan_to_value=asked, first_home=True)
        assert costs.loan == pytest.approx(PRICE * asked) and costs.ltv_used == pytest.approx(asked)
        assert not costs.loan_capped and "ltv_capped" not in flags(costs)
        expected = PRICE * asked * self.schedule.mortgage_rate + self.schedule.mortgage_fixed
        assert amounts(costs)["cost.mortgage_registration"] == pytest.approx(expected)

    def test_a_loan_above_the_ceiling_is_cut_to_it_and_flagged(self):
        costs = cost(financing="mortgage", loan_to_value=LTV_CAP_INVESTMENT + 0.15)
        assert costs.loan == pytest.approx(PRICE * LTV_CAP_INVESTMENT)
        assert costs.loan_capped and costs.ltv_cap == LTV_CAP_INVESTMENT
        assert flags(costs)["ltv_capped"] == "warning"

    def test_a_loan_exactly_at_the_ceiling_is_not_flagged(self):
        assert not cost(financing="mortgage", loan_to_value=LTV_CAP_INVESTMENT).loan_capped

    def test_no_stated_loan_means_the_ceiling(self):
        costs = cost(financing="mortgage", first_home=True)
        assert costs.ltv_used == pytest.approx(LTV_CAP_HOME) and not costs.loan_capped

    def test_only_uae_nationals_get_the_uplift(self):
        ask = dict(financing="mortgage", loan_to_value=0.99)
        assert cost(nationality="uae", **ask).ltv_used == pytest.approx(LTV_CAP_INVESTMENT + LTV_NATIONAL_UPLIFT)
        assert cost(nationality="gcc", **ask).ltv_used == pytest.approx(LTV_CAP_INVESTMENT)

    def test_fees_are_paid_from_own_funds_on_top_of_the_down_payment(self):
        costs = cost(financing="mortgage", loan_to_value=0.5)
        assert costs.own_funds == pytest.approx(PRICE * 0.5 + costs.total_costs)
        assert costs.own_funds + costs.loan == pytest.approx(costs.total_outlay)

    def test_off_plan_is_costed_without_a_loan(self):
        costs = cost(completion="offplan", sale_type="primary", financing="mortgage", loan_to_value=0.5)
        assert costs.loan == 0 and costs.loan_ignored and costs.ltv_cap == LTV_CAP_OFFPLAN
        assert "cost.mortgage_registration" not in amounts(costs)
        assert costs.own_funds == costs.total_outlay
        assert flags(costs) == {"offplan_finance": "warning"}

    def test_a_cash_buyer_has_no_loan_whatever_ratio_is_given(self):
        costs = cost(financing="cash", loan_to_value=0.5)
        assert costs.loan == 0 and not costs.loan_capped and not costs.loan_ignored

    def test_a_large_first_home_worked_through(self):
        price = 6 * LTV_HOME_THRESHOLD_AED
        costs = cost(price=price, financing="mortgage", loan_to_value=0.75, first_home=True)
        loan = price * LTV_CAP_HOME_ABOVE_THRESHOLD
        fees = (
            price * self.schedule.transfer_rate
            + self.schedule.fixed_ready
            + self.schedule.trustee_tiers[-1][1] * (1 + VAT)
            + price * self.schedule.agency_rate * (1 + VAT)
            + loan * self.schedule.mortgage_rate
            + self.schedule.mortgage_fixed
        )
        assert costs.own_funds == pytest.approx(price - loan + fees)


class TestAbuDhabi:
    schedule = SCHEDULES["abu_dhabi"]

    def test_commission_is_capped(self):
        price = 2 * self.schedule.agency_cap / self.schedule.agency_rate
        got = amounts(cost("abu_dhabi", price=price))
        assert got["cost.agency_fee"] == pytest.approx(self.schedule.agency_cap * (1 + VAT))
        assert got["cost.transfer_fee"] == pytest.approx(price * self.schedule.transfer_rate)

    def test_fixed_fee_differs_between_ready_and_off_plan(self):
        ready = amounts(cost("abu_dhabi"))["cost.registration_fee"]
        offplan = amounts(cost("abu_dhabi", completion="offplan", sale_type="primary"))["cost.registration_fee"]
        assert (ready, offplan) == (self.schedule.fixed_ready, self.schedule.fixed_offplan)
        assert offplan < ready

    def test_the_fee_is_shown_in_full_and_the_default_split_is_noted(self):
        costs = cost("abu_dhabi", community="Yas Island")
        assert amounts(costs)["cost.transfer_fee"] == pytest.approx(PRICE * self.schedule.transfer_rate)
        assert costs.split_by_default and not costs.seller_pays_transfer
        assert flags(costs, "abu_dhabi") == {"transfer_split": "info"}

    @pytest.mark.parametrize("community", ["Al Reem Island", "al reem", "Reem Island", "Al Maryah Island"])
    def test_on_the_adgm_islands_the_seller_pays_the_transfer_fee(self, community):
        costs = cost("abu_dhabi", community=community)
        assert amounts(costs)["cost.transfer_fee_seller"] == 0 and "cost.transfer_fee" not in amounts(costs)
        assert costs.seller_pays_transfer and not costs.split_by_default
        assert flags(costs, "abu_dhabi") == {"transfer_seller_pays": "info"}
        assert costs.total_costs == pytest.approx(self.schedule.fixed_ready + PRICE * self.schedule.agency_rate * (1 + VAT))

    def test_a_dubai_community_of_the_same_name_changes_nothing(self):
        assert amounts(cost("dubai", community="Al Reem Island")) == amounts(cost("dubai"))

    def test_mortgage_registration(self):
        costs = cost("abu_dhabi", financing="mortgage", loan_to_value=0.5)
        expected = PRICE * 0.5 * self.schedule.mortgage_rate + self.schedule.mortgage_fixed
        assert amounts(costs)["cost.mortgage_registration"] == pytest.approx(expected)


class TestNorthernEmirates:
    @pytest.mark.parametrize("emirate", ["sharjah", "ajman"])
    @pytest.mark.parametrize("nationality", REDUCED_RATE_NATIONALITIES)
    def test_uae_and_gcc_nationals_pay_the_lower_rate(self, emirate, nationality):
        schedule = SCHEDULES[emirate]
        foreign = amounts(cost(emirate))
        national = amounts(cost(emirate, nationality=nationality))
        assert foreign["cost.transfer_fee"] == pytest.approx(PRICE * schedule.transfer_rate)
        assert national["cost.transfer_fee"] == pytest.approx(PRICE * schedule.transfer_rate_reduced)
        assert schedule.transfer_rate_reduced < schedule.transfer_rate

    def test_ajman_minimum_fee_applies_to_small_purchases(self):
        schedule = SCHEDULES["ajman"]
        price = schedule.transfer_minimum / schedule.transfer_rate / 2
        assert amounts(cost("ajman", price=price))["cost.transfer_fee"] == schedule.transfer_minimum

    def test_ajman_nationals_have_their_own_lower_minimum(self):
        schedule = SCHEDULES["ajman"]
        price = schedule.transfer_minimum_reduced / schedule.transfer_rate_reduced / 2
        fee = amounts(cost("ajman", price=price, nationality="gcc"))["cost.transfer_fee"]
        assert fee == schedule.transfer_minimum_reduced
        assert 0 < schedule.transfer_minimum_reduced < schedule.transfer_minimum

    @pytest.mark.parametrize("emirate", ["sharjah", "ras_al_khaimah", "ajman"])
    def test_only_the_registration_fees_are_costed(self, emirate):
        costs = cost(emirate, financing="mortgage", loan_to_value=0.5)
        assert set(amounts(costs)) == {"cost.transfer_fee", "cost.registration_fee"}
        assert costs.loan == pytest.approx(PRICE * 0.5)


class TestCostFlags:
    def test_a_missing_emirate_and_a_missing_schedule_are_told_apart(self):
        assert flags(cost(None), None) == {"emirate_missing": "warning"}
        assert flags(cost("fujairah"), "fujairah") == {"cost_rates_unknown": "warning"}
