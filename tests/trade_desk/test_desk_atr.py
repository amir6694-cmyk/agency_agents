"""Average true range from candles, computed the way MetaTrader 5's built-in ATR computes it."""

import pytest

from property_scout.fields import InputError
from trade_desk.atr import DEFAULT_PERIOD, METHODS, CandleError, atr, atr_stop, candles_from, true_ranges

ROWS = [
    {"time": "2026-11-20 10:00", "open": 10, "high": 12, "low": 9, "close": 11},
    {"time": "2026-11-20 11:00", "open": 11, "high": 13, "low": 10, "close": 12},
    {"time": "2026-11-20 12:00", "open": 12, "high": 12.5, "low": 8, "close": 9},
    {"time": "2026-11-20 13:00", "open": 9, "high": 10, "low": 7, "close": 9.5},
    {"time": "2026-11-20 14:00", "open": 9.5, "high": 15, "low": 9.5, "close": 14},
]


def test_defaults():
    assert DEFAULT_PERIOD == 14
    assert METHODS == ("sma", "wilder")
    assert issubclass(CandleError, InputError)


class TestTrueRange:
    def test_each_bar_against_the_close_before_it(self):
        assert true_ranges(candles_from(ROWS)) == pytest.approx([3, 4.5, 3, 5.5])

    def test_a_gap_counts_from_the_previous_close(self):
        rows = [
            {"time": "2026-11-20T10:00:00Z", "open": 10, "high": 11, "low": 9, "close": 11},
            {"time": "2026-11-20T11:00:00Z", "open": 13.5, "high": 14, "low": 13, "close": 13.5},
        ]
        assert true_ranges(candles_from(rows)) == pytest.approx([3])


class TestAverage:
    def test_simple_average_of_the_last_period_ranges(self):
        assert atr(candles_from(ROWS), 3) == pytest.approx(13 / 3)
        assert atr(candles_from(ROWS), 3, "sma") == pytest.approx(13 / 3)

    def test_wilder_smoothing(self):
        assert atr(candles_from(ROWS), 3, "wilder") == pytest.approx((3.5 * 2 + 5.5) / 3)

    def test_needs_one_more_candle_than_the_period(self):
        assert atr(candles_from(ROWS), 4) == pytest.approx((3 + 4.5 + 3 + 5.5) / 4)
        with pytest.raises(CandleError, match="6"):
            atr(candles_from(ROWS), 5)

    def test_unknown_method(self):
        with pytest.raises(CandleError, match="method"):
            atr(candles_from(ROWS), 3, "ema")


class TestCandles:
    def test_metatrader_export_times_are_read(self):
        rows = [dict(row, time=row["time"].replace("-", ".")) for row in ROWS]
        assert len(candles_from(rows)) == 5

    @pytest.mark.parametrize(
        "index, change, named",
        [
            (2, {"high": 8.5}, "high"),
            (3, {"low": 9.6}, "low"),
            (1, {"close": "12"}, "close"),
            (4, {"time": "2026-11-20 13:00"}, "time"),
            (4, {"time": "2026-11-20 12:30"}, "time"),
            (0, {"time": "20/11/2026 10:00"}, "time"),
            (0, {"colour": "red"}, "colour"),
        ],
    )
    def test_a_bad_candle_is_named_by_its_position(self, index, change, named):
        rows = [dict(row) for row in ROWS]
        rows[index].update(change)
        with pytest.raises(CandleError, match=rf"candle {index + 1}.*{named}|{named}.*candle {index + 1}"):
            candles_from(rows)

    def test_the_other_columns_of_a_metatrader_export_are_accepted_and_ignored(self):
        rows = [dict(row, tick_volume=1200, volume=0, real_volume=0, spread=25) for row in ROWS]
        assert atr(candles_from(rows), 3) == pytest.approx(13 / 3)

    def test_not_a_list(self):
        with pytest.raises(CandleError):
            candles_from({"candles": ROWS})


class TestStop:
    def test_a_buy_stop_below_rounded_away_from_the_entry(self):
        assert atr_stop(100.0, "buy", 4.33333, 1.5, 0.01) == pytest.approx(93.50)

    def test_a_sell_stop_above_rounded_away_from_the_entry(self):
        assert atr_stop(100.0, "sell", 4.33333, 1.5, 0.01) == pytest.approx(106.50)

    def test_without_a_tick_size_nothing_is_rounded(self):
        assert atr_stop(100.0, "buy", 4.0, 1.5) == pytest.approx(94.0)

    def test_a_stop_already_on_a_tick_stays_there(self):
        assert atr_stop(4452.30, "buy", 6.0, 2.0, 0.01) == pytest.approx(4440.30)

    @pytest.mark.parametrize("multiple", [0, -1])
    def test_the_multiple_must_be_positive(self, multiple):
        with pytest.raises(InputError):
            atr_stop(100.0, "buy", 4.0, multiple)

    def test_a_stop_at_or_below_zero_is_refused(self):
        with pytest.raises(InputError):
            atr_stop(5.0, "buy", 4.0, 2.0)
