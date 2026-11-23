"""Reports: JSON for the agent, Markdown for the trader. Both carry every number the verdict rests on."""

import json

import pytest

from trade_desk.guard import assess
from trade_desk.journal import MIN_SAMPLE, review, trades_from
from trade_desk.messages import render
from trade_desk.report import journal_data, journal_markdown, to_data, to_markdown

from desk_examples import DROP


@pytest.fixture
def judged(records):
    def build(symbol=None, account=None, trade=None):
        return assess(*records(symbol, account, trade))

    return build


class TestData:
    def test_carries_the_plan_the_size_and_the_limits(self, judged):
        data = to_data(judged())
        assert data["verdict"] == "go"
        assert (data["symbol"], data["side"], data["entry"], data["stop"], data["target"]) == ("XAUUSD", "buy", 4452.30, 4440.30, 4476.30)
        assert data["currency"] == "USD"
        assert data["lots"] == 0.04
        assert data["risk"] == 48.28 and data["budget"] == 50.0 and data["risk_pct"] == pytest.approx(0.4828)
        assert data["loss_per_lot"] == 1207.0 and data["costs_per_lot"] == 7.0
        assert data["reward"] == 95.72 and data["r_multiple"] == pytest.approx(1.98, abs=0.005)
        assert data["breakeven_win_rate"] == pytest.approx(0.3353, abs=0.0001)
        assert data["margin"] == pytest.approx(178.09) and data["margin_estimated"] is True
        assert data["open_risk"] == 0 and data["worst_equity"] == 9951.72
        assert data["lots_that_fit"] == 0.41
        assert data["floors"] == [
            {"name": "daily", "level": 9500.0, "limit": 500.0, "room": 451.72},
            {"name": "overall", "level": 9000.0, "limit": 1000.0, "room": 951.72},
        ]

    def test_flags_carry_their_code_level_and_sentence(self, judged):
        result = judged(trade={"target": DROP})
        flags = to_data(result)["flags"]
        no_target = next(flag for flag in flags if flag["code"] == "no_target")
        assert no_target["level"] == "hold"
        assert no_target["text"] == render(next(f for f in result.flags if f.code == "no_target"))

    def test_absent_figures_are_null_and_the_whole_is_strict_json(self, judged):
        data = to_data(judged(trade={"target": DROP}, account={"leverage": DROP, "daily_loss_pct": DROP, "max_loss_pct": DROP}))
        assert data["target"] is None and data["reward"] is None and data["r_multiple"] is None
        assert data["margin"] is None and data["margin_level"] is None
        assert data["lots_that_fit"] is None and data["floors"] == []
        json.dumps(data, allow_nan=False)


class TestMarkdown:
    def test_leads_with_the_verdict_and_the_size(self, judged):
        text = to_markdown(judged())
        assert text.splitlines()[0].startswith("# ")
        assert "**GO**" in text
        assert "0.04 lots" in text and "48.28 USD" in text and "0.48%" in text
        assert "9,500.00" in text and "9,000.00" in text

    @pytest.mark.parametrize(
        "overrides, word",
        [({"account": {"equity": 9_520}}, "**BLOCKED**"), ({"trade": {"target": DROP}}, "**REVIEW**")],
    )
    def test_names_the_other_verdicts_and_every_flag(self, judged, overrides, word):
        result = judged(**overrides)
        text = to_markdown(result)
        assert word in text
        for flag in result.flags:
            assert render(flag) in text

    def test_escapes_the_note(self, judged):
        text = to_markdown(judged(trade={"note": "<b>retest</b> | London open"}))
        assert "<b>" not in text and "&lt;b&gt;retest&lt;/b&gt; \\| London open" in text


class TestJournal:
    ROWS = [
        {"closed": "2026-11-17T09:10:00Z", "side": "buy", "profit": 100, "risk": 50},
        {"closed": "2026-11-17T14:40:00Z", "side": "sell", "profit": -50, "risk": 50},
        {"closed": "2026-11-18T10:05:00Z", "side": "buy", "profit": 80, "risk": 40},
    ]

    def test_data(self):
        data = journal_data(review(trades_from(self.ROWS), start_balance=5_000))
        assert data["trades"] == 3 and data["wins"] == 2 and data["net"] == 130.0
        assert data["profit_factor"] == pytest.approx(3.6) and data["expectancy_r"] == pytest.approx((2 - 1 + 2) / 3)
        assert data["by_side"]["buy"]["trades"] == 2
        json.dumps(data, allow_nan=False)

    def test_markdown_warns_about_a_small_sample(self):
        text = journal_markdown(review(trades_from(self.ROWS)))
        assert "66.7%" in text and "3.60" in text
        assert f"fewer than {MIN_SAMPLE} trades" in text
