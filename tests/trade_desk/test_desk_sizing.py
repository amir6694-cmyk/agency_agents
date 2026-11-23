"""Lot size: the most volume whose loss at the stop, costs included, stays inside the risk budget."""

import pytest

from trade_desk.sizing import conversion, round_down, size, value_per_unit
from trade_desk.trade import TradeError

from desk_examples import DROP


def sized(records, symbol=None, account=None, trade=None):
    return size(*records(symbol, account, trade))


class TestTheExample:
    def test_lot_size_risk_and_reward(self, records):
        s = sized(records)
        assert s.base == 10_000 and s.budget == pytest.approx(50)
        assert s.distance == pytest.approx(12.0)
        assert s.value_per_unit == pytest.approx(100)
        assert s.costs_per_lot == pytest.approx(7)
        assert s.loss_per_lot == pytest.approx(1207)
        assert s.lots_raw == pytest.approx(50 / 1207)
        assert s.lots == 0.04
        assert s.risk == pytest.approx(48.28)
        assert s.risk_pct == pytest.approx(0.4828)
        assert s.reward_per_lot == pytest.approx(2393)
        assert s.reward == pytest.approx(95.72)
        assert s.r_multiple == pytest.approx(2393 / 1207)
        assert s.breakeven_win_rate == pytest.approx(1207 / 3600)
        assert s.min_lot_risk_pct == pytest.approx(0.1207)
        assert s.below_min is False and s.capped is False

    def test_a_sell_mirrors_a_buy(self, records):
        s = sized(records, trade={"side": "sell", "stop": 4464.30, "target": 4428.30})
        assert s.lots == 0.04 and s.risk == pytest.approx(48.28) and s.r_multiple == pytest.approx(2393 / 1207)

    def test_a_larger_budget(self, records):
        s = sized(records, account={"risk_pct": 2})
        assert s.budget == pytest.approx(200) and s.lots == 0.16 and s.risk == pytest.approx(193.12)


class TestTheBudget:
    @pytest.mark.parametrize("balance, equity", [(10_000, 9_000), (9_000, 10_000)])
    def test_risk_is_a_share_of_the_lower_of_balance_and_equity(self, records, balance, equity):
        s = sized(records, account={"balance": balance, "equity": equity})
        assert s.base == 9_000 and s.budget == pytest.approx(45) and s.lots == 0.03

    @pytest.mark.parametrize("risk_pct", [0.1, 0.25, 0.33, 0.5, 0.75, 1, 1.5, 2, 3.7, 5])
    @pytest.mark.parametrize("stop", [4451.80, 4447.30, 4440.30, 4421.05, 4352.30])
    def test_never_more_than_the_budget_and_never_a_step_less_than_it_allows(self, records, risk_pct, stop):
        s = sized(records, account={"risk_pct": risk_pct}, trade={"stop": stop})
        if s.below_min:
            assert s.lots == 0 and s.risk == 0
            return
        assert s.risk <= s.budget * (1 + 1e-9)
        assert (s.lots + 0.01) * s.loss_per_lot > s.budget

    def test_a_budget_that_lands_on_a_step_buys_that_step(self, records):
        assert sized(records, account={"risk_pct": 0.6035}).lots == 0.05

    def test_too_far_a_stop_for_the_smallest_volume(self, records):
        s = sized(records, trade={"stop": 3452.30, "target": DROP})
        assert s.below_min is True and s.lots == 0 and s.risk == 0
        assert s.min_lot_risk_pct == pytest.approx(0.01 * 100_007 / 10_000 * 100)

    def test_a_coarse_volume_step(self, records):
        s = sized(records, symbol={"volume_min": 0.1, "volume_step": 0.1})
        assert s.below_min is True and s.lots == 0
        assert s.min_lot_risk_pct == pytest.approx(1.207)

    def test_the_largest_volume_the_broker_takes(self, records):
        s = sized(records, symbol={"volume_max": 0.02})
        assert s.capped is True and s.lots == 0.02 and s.risk == pytest.approx(24.14)


class TestCosts:
    def test_slippage_widens_the_loss_but_not_the_reward(self, records):
        s = sized(records, trade={"slippage": 0.30})
        assert s.loss_per_lot == pytest.approx(1237)
        assert s.lots == 0.04 and s.risk == pytest.approx(49.48)
        assert s.reward_per_lot == pytest.approx(2393) and s.r_multiple == pytest.approx(2393 / 1237)

    def test_an_unknown_commission_counts_nothing(self, records):
        s = sized(records, symbol={"commission_per_lot": DROP})
        assert s.costs_per_lot == 0 and s.loss_per_lot == pytest.approx(1200) and s.risk == pytest.approx(48)

    def test_a_swap_charge_is_paid_for_every_rollover(self, records):
        s = sized(records, trade={"rollovers": 2})
        assert s.costs_per_lot == pytest.approx(107)
        assert s.loss_per_lot == pytest.approx(1307)
        assert s.reward_per_lot == pytest.approx(2293)
        assert s.lots == 0.03

    def test_a_swap_credit_is_not_counted_on_either_side(self, records):
        s = sized(records, trade={"side": "sell", "stop": 4464.30, "target": 4428.30, "rollovers": 3})
        assert s.costs_per_lot == pytest.approx(7) and s.reward_per_lot == pytest.approx(2393)

    def test_an_unknown_swap_counts_nothing(self, records):
        s = sized(records, symbol={"swap_long": DROP}, trade={"rollovers": 2})
        assert s.costs_per_lot == pytest.approx(7)

    def test_a_target_that_costs_eat(self, records):
        thin = sized(records, trade={"target": 4452.40})
        assert thin.reward_per_lot == pytest.approx(3) and thin.r_multiple == pytest.approx(3 / 1207)
        negative = sized(records, trade={"target": 4452.35})
        assert negative.reward_per_lot == pytest.approx(-2) and negative.r_multiple < 0
        assert negative.breakeven_win_rate is None

    def test_no_target_no_reward(self, records):
        s = sized(records, trade={"target": DROP})
        assert s.reward_per_lot is None and s.reward is None and s.r_multiple is None and s.breakeven_win_rate is None


class TestCurrency:
    def test_money_per_price_unit(self, make_symbol):
        assert value_per_unit(make_symbol()) == pytest.approx(100)
        assert value_per_unit(make_symbol(contract_size=10, tick_value=0.1)) == pytest.approx(10)

    def test_tick_value_implies_the_rate_from_profit_to_account_currency(self, make_symbol):
        assert conversion(make_symbol()) == pytest.approx(1)
        assert conversion(make_symbol(tick_value=0.86)) == pytest.approx(0.86)

    def test_an_account_in_another_currency_uses_the_tick_value_it_reports(self, records):
        s = sized(records, symbol={"tick_value": 0.86}, account={"currency": "EUR", "conversion_rate": 0.86})
        assert s.value_per_unit == pytest.approx(86) and s.loss_per_lot == pytest.approx(1039)
        assert s.lots == 0.04 and s.risk == pytest.approx(41.56)


class TestMargin:
    def test_estimated_from_leverage(self, records):
        s = sized(records)
        assert s.margin_estimated is True
        assert s.margin_per_lot == pytest.approx(4452.30)
        assert s.margin == pytest.approx(0.04 * 4452.30)

    def test_estimated_in_the_account_currency(self, records):
        s = sized(records, symbol={"tick_value": 0.86}, account={"currency": "EUR", "conversion_rate": 0.86})
        assert s.margin_per_lot == pytest.approx(100 * 4452.30 * 0.86 / 100)

    def test_the_terminal_figure_wins(self, records):
        s = sized(records, symbol={"margin_per_lot": 900})
        assert s.margin_estimated is False and s.margin_per_lot == 900 and s.margin == pytest.approx(36)

    def test_unknown_without_leverage_or_a_terminal_figure(self, records):
        s = sized(records, account={"leverage": DROP})
        assert s.margin is None and s.margin_per_lot is None


class TestRoundDown:
    @pytest.mark.parametrize(
        "volume, step, expected",
        [
            (0.3, 0.01, 0.3),
            (0.29, 0.01, 0.29),
            (0.299, 0.01, 0.29),
            (0.7, 0.1, 0.7),
            (1.0, 0.1, 1.0),
            (5, 1, 5),
            (5.99, 1, 5),
            (0.0099, 0.01, 0),
            (1.2345, 0.001, 1.234),
        ],
    )
    def test_rounds_to_the_step_below_without_float_noise(self, volume, step, expected):
        assert round_down(volume, step) == expected


def test_the_specification_must_be_for_the_symbol_traded(make_symbol, make_account, make_trade):
    with pytest.raises(TradeError, match="XAUUSD.m"):
        size(make_symbol(name="XAUUSD.m"), make_account(), make_trade())
