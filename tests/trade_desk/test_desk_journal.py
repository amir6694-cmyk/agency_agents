"""Journal review: what a run of closed trades says, and how far it can be trusted."""

import pytest

from property_scout.fields import InputError
from trade_desk.journal import MIN_SAMPLE, JournalError, review, trades_from

# W L L W flat L, buys and sells interleaved, one trade with no recorded risk.
ROWS = [
    {"closed": "2026-11-17T09:10:00Z", "side": "buy", "profit": 100, "risk": 50, "volume": 0.05, "symbol": "XAUUSD"},
    {"closed": "2026-11-17T14:40:00Z", "side": "sell", "profit": -50, "risk": 50, "volume": 0.05, "symbol": "XAUUSD"},
    {"closed": "2026-11-18T10:05:00Z", "side": "sell", "profit": -50, "risk": 50},
    {"closed": "2026-11-18T15:30:00Z", "side": "buy", "profit": 200, "risk": 50},
    {"closed": "2026-11-19T08:00:00Z", "side": "buy", "profit": 0},
    {"closed": "2026-11-19T16:45:00Z", "side": "sell", "profit": -30, "risk": 30},
]


@pytest.fixture
def stats():
    return review(trades_from(ROWS))


def test_errors_are_input_errors():
    assert issubclass(JournalError, InputError)
    assert MIN_SAMPLE == 30


class TestCounts:
    def test_wins_losses_and_flat_trades(self, stats):
        assert (stats.trades, stats.wins, stats.losses, stats.flat) == (6, 2, 3, 1)
        assert stats.win_rate == pytest.approx(2 / 6)

    def test_money(self, stats):
        assert stats.net == pytest.approx(170)
        assert stats.gross_profit == pytest.approx(300) and stats.gross_loss == pytest.approx(-130)
        assert stats.average_win == pytest.approx(150) and stats.average_loss == pytest.approx(-130 / 3)
        assert stats.payoff == pytest.approx(150 / (130 / 3))
        assert stats.profit_factor == pytest.approx(300 / 130)
        assert stats.expectancy == pytest.approx(170 / 6)

    def test_expectancy_in_r_over_the_trades_that_recorded_their_risk(self, stats):
        assert stats.expectancy_r == pytest.approx((2 - 1 - 1 + 4 - 1) / 5)
        assert stats.r_coverage == pytest.approx(5 / 6)

    def test_streaks(self, stats):
        assert stats.longest_losing_streak == 2 and stats.longest_winning_streak == 1

    def test_by_side(self, stats):
        assert stats.by_side["buy"] == {"trades": 3, "wins": 2, "win_rate": pytest.approx(2 / 3), "net": pytest.approx(300)}
        assert stats.by_side["sell"] == {"trades": 3, "wins": 0, "win_rate": 0, "net": pytest.approx(-130)}

    def test_dates_and_sample(self, stats):
        assert stats.first == "2026-11-17T09:10:00+00:00" and stats.last == "2026-11-19T16:45:00+00:00"
        assert stats.small_sample is True


class TestDrawdown:
    def test_peak_to_trough_in_money(self, stats):
        assert stats.max_drawdown == pytest.approx(100)
        assert stats.max_drawdown_pct is None

    def test_as_a_share_of_the_peak_when_the_starting_balance_is_known(self):
        stats = review(trades_from(ROWS), start_balance=1_000)
        assert stats.max_drawdown == pytest.approx(100)
        assert stats.max_drawdown_pct == pytest.approx(100 / 1_100 * 100)

    def test_trades_are_taken_in_the_order_they_closed(self):
        shuffled = [ROWS[3], ROWS[0], ROWS[5], ROWS[1], ROWS[4], ROWS[2]]
        stats = review(trades_from(shuffled))
        assert stats.max_drawdown == pytest.approx(100) and stats.longest_losing_streak == 2

    def test_a_losing_start_is_a_drawdown_from_the_start(self):
        stats = review(trades_from([dict(ROWS[1]), dict(ROWS[2], closed="2026-11-18T10:05:00Z")]), start_balance=500)
        assert stats.max_drawdown == pytest.approx(100) and stats.max_drawdown_pct == pytest.approx(20)


class TestEdges:
    def test_no_losses_means_no_profit_factor(self):
        stats = review(trades_from([ROWS[0], ROWS[3]]))
        assert stats.profit_factor is None and stats.average_loss is None and stats.payoff is None

    def test_no_risk_recorded_means_no_r(self):
        stats = review(trades_from([{k: v for k, v in row.items() if k != "risk"} for row in ROWS]))
        assert stats.expectancy_r is None and stats.r_coverage == 0

    def test_a_large_sample_is_not_small(self):
        rows = [dict(ROWS[0], closed=f"2026-10-{1 + i // 2:02d}T{10 + i % 2}:00:00Z") for i in range(MIN_SAMPLE)]
        assert review(trades_from(rows)).small_sample is False

    def test_an_empty_journal(self):
        with pytest.raises(JournalError, match="no closed trades"):
            review(trades_from([]))

    @pytest.mark.parametrize(
        "change, named",
        [
            ({"profit": "100"}, "profit"),
            ({"side": "long"}, "side"),
            ({"closed": "yesterday"}, "closed"),
            ({"risk": 0}, "risk"),
            ({"pnl": 100}, "pnl"),
        ],
    )
    def test_a_bad_row_is_named_by_its_position(self, change, named):
        rows = [dict(row) for row in ROWS]
        rows[2].update(change)
        with pytest.raises(JournalError, match=rf"trade 3.*{named}|{named}.*trade 3"):
            trades_from(rows)

    def test_times_with_and_without_an_offset_cannot_be_mixed(self):
        rows = [dict(row) for row in ROWS]
        rows[4]["closed"] = "2026-11-19 08:00"
        with pytest.raises(JournalError, match="offset"):
            trades_from(rows)

    def test_metatrader_export_times_are_read(self):
        rows = [dict(row, closed=row["closed"].replace("-", ".").replace("T", " ").replace("Z", "")) for row in ROWS]
        assert review(trades_from(rows)).trades == 6
