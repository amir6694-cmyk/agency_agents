"""The verdict: go, review or blocked, and every flag that can lead to one."""

import pytest

from trade_desk.guard import (
    HIGH_RISK_PCT,
    LEVELS,
    MARGIN_ESTIMATE_FACTOR,
    MARGIN_LEVEL_WARN,
    MIN_REWARD_RISK,
    SPEC_TOLERANCE,
    SPREAD_SHARE_LIMIT,
    TIGHT_HEADROOM,
    VERDICTS,
    assess,
)
from trade_desk.messages import TEXT, render

from desk_examples import DROP

GOLD_LONG = {"symbol": "XAUUSD", "side": "buy", "volume": 0.2, "price_current": 4460.0, "stop": 4450.0}


def judged(records, symbol=None, account=None, trade=None):
    return assess(*records(symbol, account, trade))


def codes(assessment, level=None):
    return {flag.code for flag in assessment.flags if level is None or flag.level == level}


def floor(assessment, name):
    return next(item for item in assessment.floors if item.name == name)


# One record per flag that raises it. Overrides apply to the symbol, the account and the trade in turn.
SCENARIOS = {
    "below_min_volume": ({}, {}, {"stop": 3452.30, "target": 6452.30}),
    "spec_inconsistent": ({"tick_value": 0.1}, {}, {}),
    "limit_breached": ({}, {"equity": 9_500}, {}),
    "limit_would_breach": ({}, {"equity": 9_520}, {}),
    "margin_insufficient": ({"margin_per_lot": 300_000}, {}, {}),
    "open_without_stop": ({}, {"open_positions": [{**GOLD_LONG, "stop": None}]}, {}),
    "spec_unchecked": ({"profit_currency": DROP}, {}, {}),
    "commission_unknown": ({"commission_per_lot": DROP}, {}, {}),
    "hold_unknown": ({}, {}, {"rollovers": DROP}),
    "swap_unknown": ({"swap_long": DROP}, {}, {"rollovers": 1}),
    "slippage_unknown": ({}, {}, {"slippage": DROP}),
    "spread_unknown": ({}, {}, {"spread": DROP}),
    "spread_wide": ({}, {}, {"spread": 3.0}),
    "no_target": ({}, {}, {"target": DROP}),
    "reward_low": ({}, {}, {"target": 4458.30}),
    "risk_high": ({}, {"risk_pct": 2.5}, {}),
    "margin_unknown": ({}, {"leverage": DROP}, {}),
    "margin_level_low": ({"margin_per_lot": 100_000}, {}, {}),
    "margin_estimate_thin": ({}, {"leverage": 20}, {}),
    "open_risk_unknown": ({}, {"open_positions": [{"symbol": "EURUSD", "side": "buy", "volume": 1, "price_current": 1.08, "stop": 1.07}]}, {}),
    "daily_limit_unset": ({}, {"daily_loss_pct": DROP}, {}),
    "daily_limit_untested": ({}, {"day_start_balance": DROP}, {}),
    "daily_basis_unknown": ({}, {"daily_loss_of": DROP}, {}),
    "max_loss_unset": ({}, {"max_loss_pct": DROP}, {}),
    "max_loss_untested": ({}, {"max_loss_mode": "trailing"}, {}),
    "max_loss_mode_unknown": ({}, {"max_loss_mode": DROP}, {}),
    "headroom_tight": ({}, {"equity": 9_600}, {}),
    "volume_capped": ({"volume_max": 0.02}, {}, {}),
    "margin_estimated": ({}, {}, {}),
}


class TestTheExample:
    def test_a_clean_trade_is_go(self, records):
        result = judged(records)
        assert result.verdict == "go"
        assert codes(result) == {"margin_estimated"}
        assert codes(result, "info") == {"margin_estimated"}

    def test_worst_case_and_floors(self, records):
        result = judged(records)
        assert result.open_risk == 0
        assert result.worst_equity == pytest.approx(10_000 - 48.28)
        daily, overall = floor(result, "daily"), floor(result, "overall")
        assert (daily.level, daily.limit) == (pytest.approx(9_500), pytest.approx(500))
        assert daily.room == pytest.approx(451.72)
        assert (overall.level, overall.limit) == (pytest.approx(9_000), pytest.approx(1_000))
        assert overall.room == pytest.approx(951.72)
        assert result.lots_that_fit == 0.41

    def test_margin_level_after_the_trade(self, records):
        assert judged(records).margin_level == pytest.approx(10_000 / (0.04 * 4452.30) * 100)
        used = judged(records, account={"margin_used": 200}).margin_level
        assert used == pytest.approx(10_000 / (200 + 0.04 * 4452.30) * 100)


class TestEveryFlag:
    def test_every_flag_has_a_level_a_text_and_a_scenario(self):
        assert set(LEVELS.values()) == {"block", "hold", "info"}
        assert set(TEXT) == set(LEVELS)
        assert set(SCENARIOS) == set(LEVELS)

    @pytest.mark.parametrize("code", sorted(SCENARIOS))
    def test_the_scenario_raises_the_flag(self, records, code):
        result = judged(records, *SCENARIOS[code])
        assert code in codes(result)
        assert next(flag.level for flag in result.flags if flag.code == code) == LEVELS[code]

    @pytest.mark.parametrize("code", sorted(SCENARIOS))
    def test_the_verdict_follows_the_most_severe_flag(self, records, code):
        result = judged(records, *SCENARIOS[code])
        levels = {flag.level for flag in result.flags}
        expected = "blocked" if "block" in levels else "review" if "hold" in levels else "go"
        assert result.verdict == expected

    @pytest.mark.parametrize("code", sorted(SCENARIOS))
    def test_every_flag_renders_as_a_sentence(self, records, code):
        result = judged(records, *SCENARIOS[code])
        for flag in result.flags:
            text = render(flag)
            assert text and "{" not in text and "}" not in text
            assert text[0].isupper() and text.endswith(".")

    def test_verdict_order(self):
        assert VERDICTS == ("blocked", "review", "go")


class TestBlocks:
    def test_a_stop_too_far_for_the_smallest_volume(self, records):
        result = judged(records, *SCENARIOS["below_min_volume"])
        assert result.verdict == "blocked" and result.sizing.lots == 0
        assert "10.00%" in render(next(f for f in result.flags if f.code == "below_min_volume"))

    def test_a_tick_value_that_does_not_fit_the_contract(self, records):
        assert judged(records, symbol={"tick_value": 1.0 * (1 + SPEC_TOLERANCE * 2)}).verdict == "blocked"
        assert judged(records, symbol={"tick_value": 1.0 * (1 + SPEC_TOLERANCE / 2)}).verdict == "go"

    def test_a_tick_value_checked_against_a_stated_conversion_rate(self, records):
        fits = judged(records, symbol={"tick_value": 0.86}, account={"currency": "EUR", "conversion_rate": 0.86})
        assert fits.verdict == "go"
        wrong = judged(records, symbol={"tick_value": 0.86}, account={"currency": "EUR", "conversion_rate": 1.17})
        assert "spec_inconsistent" in codes(wrong)

    def test_another_account_currency_without_a_rate_cannot_be_checked(self, records):
        result = judged(records, symbol={"tick_value": 0.86}, account={"currency": "EUR"})
        assert "spec_unchecked" in codes(result) and result.verdict == "review"

    def test_a_loss_limit_already_reached(self, records):
        result = judged(records, account={"equity": 9_400})
        assert result.verdict == "blocked" and "limit_breached" in codes(result)

    def test_a_trade_that_would_cross_a_floor_says_what_would_fit(self, records):
        result = judged(records, *SCENARIOS["limit_would_breach"])
        assert result.verdict == "blocked"
        assert result.worst_equity < floor(result, "daily").level
        assert result.lots_that_fit == 0.01
        text = render(next(f for f in result.flags if f.code == "limit_would_breach"))
        assert "9,500.00" in text and "0.01" in text

    def test_open_risk_counts_against_the_floors(self, records):
        result = judged(records, account={"open_positions": [GOLD_LONG]})
        assert result.open_risk == pytest.approx(0.2 * 10 * 100)
        assert result.worst_equity == pytest.approx(10_000 - 200 - 48.28)
        assert result.lots_that_fit == 0.24

    def test_a_position_given_as_money_at_risk(self, records):
        other = {"symbol": "EURUSD", "side": "sell", "volume": 1, "risk_to_stop": 35.0}
        result = judged(records, account={"open_positions": [GOLD_LONG, other]})
        assert result.open_risk == pytest.approx(235)
        assert "open_risk_unknown" not in codes(result)

    def test_enough_open_risk_blocks_the_next_trade(self, records):
        heavy = {**GOLD_LONG, "volume": 0.46}
        result = judged(records, account={"open_positions": [heavy]})
        assert result.open_risk == pytest.approx(460)
        assert result.verdict == "blocked" and "limit_would_breach" in codes(result)

    def test_an_open_position_without_a_stop_blocks_whatever_else_is_known(self, records):
        result = judged(records, *SCENARIOS["open_without_stop"])
        assert result.verdict == "blocked"

    def test_margin_beyond_free_margin(self, records):
        result = judged(records, symbol={"margin_per_lot": 200_000}, account={"margin_used": 3_000})
        assert "margin_insufficient" in codes(result)
        fits = judged(records, symbol={"margin_per_lot": 100_000}, account={"margin_used": 0})
        assert "margin_insufficient" not in codes(fits)


class TestFloors:
    def test_a_daily_limit_on_the_day_start_balance(self, records):
        result = judged(records, account={"daily_loss_of": "day_start", "day_start_balance": 10_400, "equity": 10_400, "balance": 10_400})
        daily = floor(result, "daily")
        assert daily.limit == pytest.approx(520) and daily.level == pytest.approx(9_880)

    def test_a_daily_limit_on_the_initial_balance_is_anchored_at_the_day_start(self, records):
        result = judged(records, account={"daily_loss_of": "initial", "day_start_balance": 10_400, "equity": 10_400, "balance": 10_400})
        daily = floor(result, "daily")
        assert daily.limit == pytest.approx(500) and daily.level == pytest.approx(9_900)

    def test_an_unknown_basis_takes_the_stricter_floor(self, records):
        result = judged(records, account={"daily_loss_of": DROP, "day_start_balance": 10_400, "equity": 10_400, "balance": 10_400})
        assert floor(result, "daily").level == pytest.approx(9_900)
        assert "daily_basis_unknown" in codes(result) and result.verdict == "review"

    def test_a_trailing_limit_follows_the_high_water_mark(self, records):
        result = judged(records, account={"max_loss_mode": "trailing", "high_water": 10_600})
        overall = floor(result, "overall")
        assert overall.limit == pytest.approx(1_000) and overall.level == pytest.approx(9_600)

    def test_an_unknown_mode_takes_the_stricter_floor(self, records):
        result = judged(records, account={"max_loss_mode": DROP, "high_water": 10_600})
        assert floor(result, "overall").level == pytest.approx(9_600)
        assert "max_loss_mode_unknown" in codes(result)

    def test_without_limits_there_is_nothing_to_fit_inside(self, records):
        result = judged(records, account={"daily_loss_pct": DROP, "max_loss_pct": DROP})
        assert result.floors == [] and result.lots_that_fit is None
        assert {"daily_limit_unset", "max_loss_unset"} <= codes(result) and result.verdict == "review"

    def test_headroom_is_measured_against_the_limit(self, records):
        result = judged(records, *SCENARIOS["headroom_tight"])
        daily = floor(result, "daily")
        assert 0 <= daily.room < TIGHT_HEADROOM * daily.limit
        assert result.verdict == "review"


class TestHolds:
    def test_risk_above_the_ceiling(self, records):
        assert "risk_high" in codes(judged(records, account={"risk_pct": HIGH_RISK_PCT + 0.5}))
        assert "risk_high" not in codes(judged(records, account={"risk_pct": HIGH_RISK_PCT}))

    def test_reward_below_the_floor_after_costs(self, records):
        result = judged(records, *SCENARIOS["reward_low"])
        assert result.sizing.r_multiple < MIN_REWARD_RISK
        assert "reward_low" in codes(result)

    def test_spread_against_the_stop(self, records):
        assert "spread_wide" in codes(judged(records, trade={"spread": 12.0 * SPREAD_SHARE_LIMIT * 1.05}))
        assert "spread_wide" not in codes(judged(records, trade={"spread": 12.0 * SPREAD_SHARE_LIMIT * 0.95}))

    def test_margin_level_under_the_warning_line(self, records):
        result = judged(records, *SCENARIOS["margin_level_low"])
        assert result.margin_level < MARGIN_LEVEL_WARN and result.verdict == "review"

    def test_an_estimate_is_trusted_only_when_a_multiple_of_it_still_clears(self, records):
        thin = judged(records, account={"leverage": 20})
        assert "margin_estimate_thin" in codes(thin) and "margin_estimated" not in codes(thin)
        estimate = thin.sizing.margin
        assert 10_000 / (estimate * MARGIN_ESTIMATE_FACTOR) * 100 < MARGIN_LEVEL_WARN
        roomy = judged(records, account={"leverage": 30})
        assert "margin_estimate_thin" not in codes(roomy) and roomy.verdict == "go"

    def test_open_positions_need_the_margin_they_use(self, records):
        result = judged(records, account={"open_positions": [GOLD_LONG], "margin_used": DROP})
        assert "margin_unknown" in codes(result)

    def test_a_swap_is_needed_only_when_held_overnight_on_that_side(self, records):
        assert "swap_unknown" not in codes(judged(records, symbol={"swap_long": DROP}, trade={"rollovers": 0}))
        assert "swap_unknown" not in codes(judged(records, symbol={"swap_long": DROP}, trade={"side": "sell", "stop": 4464.30, "target": 4428.30, "rollovers": 2}))


def test_flags_carry_no_duplicates(records):
    result = judged(records, account={"open_positions": [{**GOLD_LONG, "stop": None}, {**GOLD_LONG, "stop": None}]})
    assert [flag.code for flag in result.flags].count("open_without_stop") == 1
