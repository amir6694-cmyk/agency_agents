"""Records are checked at the boundary: a wrong value is named, never coerced or guessed."""

import pytest

from property_scout.fields import InputError
from trade_desk.account import DAILY_BASES, MAX_LOSS_MODES, Account, AccountError, OpenPosition
from trade_desk.spec import Symbol, SpecError
from trade_desk.spec import REQUIRED as SYMBOL_REQUIRED
from trade_desk.account import REQUIRED as ACCOUNT_REQUIRED
from trade_desk.trade import REQUIRED as TRADE_REQUIRED
from trade_desk.trade import SIDES, Trade, TradeError

from desk_examples import ACCOUNT, DROP, SYMBOL, TRADE, merged


class TestSymbol:
    def test_reads_a_full_specification(self, make_symbol):
        symbol = make_symbol()
        assert symbol.name == "XAUUSD"
        assert symbol.contract_size == 100 and symbol.tick_size == 0.01 and symbol.tick_value == 1.0
        assert (symbol.volume_min, symbol.volume_step, symbol.volume_max) == (0.01, 0.01, 100)
        assert symbol.commission_per_lot == 7.0 and symbol.swap_long == -50.0 and symbol.swap_short == 25.0
        assert symbol.margin_per_lot is None

    def test_errors_are_input_errors(self):
        assert issubclass(SpecError, InputError)

    @pytest.mark.parametrize("field", SYMBOL_REQUIRED)
    def test_every_required_field_is_required(self, field):
        with pytest.raises(SpecError, match=field):
            Symbol.from_dict(merged(SYMBOL, {field: DROP}))

    def test_unknown_fields_are_named(self):
        with pytest.raises(SpecError, match="lot_size"):
            Symbol.from_dict(merged(SYMBOL, {"lot_size": 100}))

    @pytest.mark.parametrize(
        "field, value",
        [
            ("contract_size", 0),
            ("contract_size", "100"),
            ("tick_size", -0.01),
            ("tick_value", 0),
            ("tick_value", True),
            ("volume_min", 0),
            ("volume_step", 0),
            ("commission_per_lot", -7),
            ("margin_per_lot", 0),
            ("digits", 2.5),
            ("digits", 9),
            ("profit_currency", "US Dollar"),
            ("profit_currency", 840),
            ("name", ""),
            ("name", "XAU\nUSD"),
        ],
    )
    def test_wrong_values_are_named(self, field, value):
        with pytest.raises(SpecError, match=field):
            Symbol.from_dict(merged(SYMBOL, {field: value}))

    def test_volume_max_below_volume_min_is_refused(self):
        with pytest.raises(SpecError, match="volume_max"):
            Symbol.from_dict(merged(SYMBOL, {"volume_min": 1, "volume_max": 0.5}))

    def test_swaps_may_be_charges_or_credits(self, make_symbol):
        symbol = make_symbol(swap_long=-61.2, swap_short=0)
        assert symbol.swap_long == -61.2 and symbol.swap_short == 0

    def test_commission_may_be_zero(self, make_symbol):
        assert make_symbol(commission_per_lot=0).commission_per_lot == 0

    def test_currency_is_upper_case(self, make_symbol):
        assert make_symbol(profit_currency="usd").profit_currency == "USD"

    def test_not_an_object(self):
        with pytest.raises(SpecError):
            Symbol.from_dict(["XAUUSD"])


class TestAccount:
    def test_reads_a_full_account(self, make_account):
        account = make_account()
        assert account.currency == "USD" and account.balance == 10_000 and account.equity == 10_000
        assert account.risk_pct == 0.5 and account.leverage == 100 and account.margin_used == 0
        assert account.open_positions == []
        assert account.daily_loss_pct == 5 and account.daily_loss_of == "initial"
        assert account.max_loss_pct == 10 and account.max_loss_mode == "static"
        assert account.high_water is None

    def test_choices(self):
        assert DAILY_BASES == ("initial", "day_start")
        assert MAX_LOSS_MODES == ("static", "trailing")

    @pytest.mark.parametrize("field", ACCOUNT_REQUIRED)
    def test_every_required_field_is_required(self, field):
        with pytest.raises(AccountError, match=field):
            Account.from_dict(merged(ACCOUNT, {field: DROP}))

    def test_open_positions_must_be_stated_even_when_there_are_none(self):
        assert "open_positions" in ACCOUNT_REQUIRED
        with pytest.raises(AccountError, match="open_positions"):
            Account.from_dict(merged(ACCOUNT, {"open_positions": None}))

    @pytest.mark.parametrize(
        "field, value",
        [
            ("risk_pct", 0),
            ("risk_pct", 101),
            ("risk_pct", "1%"),
            ("equity", 0),
            ("balance", -5),
            ("leverage", 0),
            ("margin_used", -1),
            ("daily_loss_pct", 0),
            ("daily_loss_pct", 150),
            ("daily_loss_of", "yesterday"),
            ("max_loss_mode", "relative"),
            ("initial_balance", 0),
            ("high_water", "10000"),
            ("conversion_rate", 0),
            ("currency", "dollars"),
            ("open_positions", {"symbol": "XAUUSD"}),
        ],
    )
    def test_wrong_values_are_named(self, field, value):
        with pytest.raises(AccountError, match=field):
            Account.from_dict(merged(ACCOUNT, {field: value}))

    def test_unknown_fields_are_named(self):
        with pytest.raises(AccountError, match="daily_drawdown"):
            Account.from_dict(merged(ACCOUNT, {"daily_drawdown": 5}))


class TestOpenPosition:
    def position(self, **fields):
        data = {"symbol": "XAUUSD", "side": "buy", "volume": 0.2, "price_current": 4460.0, "stop": 4450.0}
        data.update(fields)
        return Account.from_dict(merged(ACCOUNT, {"open_positions": [{k: v for k, v in data.items() if v is not DROP}]}))

    def test_reads_a_position(self):
        position = self.position().open_positions[0]
        assert isinstance(position, OpenPosition)
        assert (position.symbol, position.side, position.volume) == ("XAUUSD", "buy", 0.2)
        assert position.price_current == 4460.0 and position.stop == 4450.0 and position.risk_to_stop is None

    def test_a_position_without_a_stop_is_a_valid_record(self):
        assert self.position(stop=DROP).open_positions[0].stop is None

    @pytest.mark.parametrize(
        "fields",
        [
            {"side": "buy", "price_current": 4450.0, "stop": 4460.0},
            {"side": "sell", "price_current": 4460.0, "stop": 4450.0},
            {"side": "buy", "price_current": 4450.0, "stop": 4450.0},
        ],
    )
    def test_a_stop_on_the_wrong_side_of_the_price_is_refused(self, fields):
        with pytest.raises(AccountError, match="stop"):
            self.position(**fields)

    def test_risk_to_stop_replaces_price_and_stop_and_cannot_sit_beside_them(self):
        position = self.position(symbol="EURUSD", price_current=DROP, stop=DROP, risk_to_stop=35.0).open_positions[0]
        assert position.risk_to_stop == 35.0
        with pytest.raises(AccountError, match="risk_to_stop"):
            self.position(risk_to_stop=35.0)

    @pytest.mark.parametrize("fields", [{"volume": 0}, {"side": "long"}, {"symbol": ""}, {"risk_to_stop": -1, "price_current": DROP, "stop": DROP}])
    def test_wrong_values_are_named(self, fields):
        with pytest.raises(AccountError):
            self.position(**fields)

    def test_the_position_is_named_in_the_error(self):
        with pytest.raises(AccountError, match="open_positions\\[1\\]"):
            Account.from_dict(merged(ACCOUNT, {"open_positions": [
                {"symbol": "XAUUSD", "side": "buy", "volume": 0.1, "price_current": 4460.0, "stop": 4450.0},
                {"symbol": "XAUUSD", "side": "sell", "volume": 0},
            ]}))


class TestTrade:
    def test_reads_a_full_trade(self, make_trade):
        trade = make_trade()
        assert (trade.symbol, trade.side, trade.entry, trade.stop, trade.target) == ("XAUUSD", "buy", 4452.30, 4440.30, 4476.30)
        assert trade.spread == 0.25 and trade.slippage == 0.0 and trade.rollovers == 0

    def test_sides(self):
        assert SIDES == ("buy", "sell")

    @pytest.mark.parametrize("field", TRADE_REQUIRED)
    def test_every_required_field_is_required(self, field):
        with pytest.raises(TradeError, match=field):
            Trade.from_dict(merged(TRADE, {field: DROP}))

    def test_a_sell_has_its_stop_above_and_its_target_below(self, make_trade):
        trade = make_trade(side="sell", entry=4452.30, stop=4464.30, target=4428.30)
        assert trade.side == "sell"

    @pytest.mark.parametrize(
        "fields, named",
        [
            ({"stop": 4460.0}, "stop"),
            ({"stop": 4452.30}, "stop"),
            ({"target": 4440.0}, "target"),
            ({"target": 4452.30}, "target"),
            ({"side": "sell"}, "stop"),
            ({"side": "sell", "stop": 4464.30}, "target"),
        ],
    )
    def test_a_stop_or_target_on_the_wrong_side_is_refused(self, fields, named):
        with pytest.raises(TradeError, match=named):
            Trade.from_dict(merged(TRADE, fields))

    @pytest.mark.parametrize(
        "field, value",
        [
            ("entry", "4452.30"),
            ("entry", 0),
            ("spread", -0.1),
            ("slippage", -0.5),
            ("rollovers", 1.5),
            ("rollovers", -1),
            ("side", "long"),
            ("note", "a‮b"),
        ],
    )
    def test_wrong_values_are_named(self, field, value):
        with pytest.raises(TradeError, match=field):
            Trade.from_dict(merged(TRADE, {field: value}))

    def test_zero_spread_slippage_and_rollovers_are_statements(self, make_trade):
        trade = make_trade(spread=0, slippage=0, rollovers=0)
        assert (trade.spread, trade.slippage, trade.rollovers) == (0, 0, 0)

    def test_unknown_fields_are_named(self):
        with pytest.raises(TradeError, match="take_profit"):
            Trade.from_dict(merged(TRADE, {"take_profit": 4476.30}))
