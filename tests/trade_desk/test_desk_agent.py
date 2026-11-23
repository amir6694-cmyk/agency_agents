"""The MT5 Gold Trader must be routable, parseable, and in step with the engine it cites."""

import os
import re
import shlex

import pytest

from agent_router.config import PROJECT_ROOT, AgentConfig
from agent_router.personality import AgentPersonality
from agent_router.router import AgentRouter
from trade_desk.account import DAILY_BASES, MAX_LOSS_MODES, Account, OpenPosition
from trade_desk.atr import DEFAULT_PERIOD, METHODS
from trade_desk.cli import build_parser
from trade_desk.guard import (
    HIGH_RISK_PCT,
    LEVELS,
    MARGIN_ESTIMATE_FACTOR,
    MARGIN_LEVEL_WARN,
    MIN_REWARD_RISK,
    SPEC_TOLERANCE,
    SPREAD_SHARE_LIMIT,
    TIGHT_HEADROOM,
)
from trade_desk.journal import MIN_SAMPLE, ClosedTrade
from trade_desk.spec import Symbol
from trade_desk.trade import SIDES, Trade

AGENT = "MT5 Gold Trader"
SOURCE = os.path.join(PROJECT_ROOT, "agents", "trading", "trading-mt5-gold-trader.md")
INSTALLED = os.path.join(PROJECT_ROOT, ".claude", "agents", "mt5-gold-trader.md")


@pytest.fixture(scope="module")
def definition():
    with open(SOURCE, encoding="utf-8") as handle:
        return handle.read()


def section(definition, heading):
    start = definition.index(f"\n{heading}\n")
    level = heading.split(" ")[0]
    following = re.search(rf"\n#{{1,{len(level)}}} ", definition[start + 1:])
    return definition[start: start + 1 + following.start()] if following else definition[start:]


class TestRegistration:
    def test_registered_with_an_existing_file(self):
        agent = AgentConfig().get_agent_by_name(AGENT)
        assert agent is not None
        assert agent["category"] == "trading"
        assert agent["file_path"] == SOURCE
        assert agent["is_default"] is False

    def test_definition_parses_into_a_full_personality(self):
        personality = AgentPersonality().load_agent(AGENT)
        assert personality["name"] == "mt5-gold-trader"
        for part in ("core_mission", "workflow_process", "success_metrics"):
            assert len(personality[part]) >= 4, part
        assert personality["communication_style"]["tone"]
        assert len(personality["deliverables"]) >= 2

    def test_claude_code_copy_is_identical_to_the_source(self, definition):
        with open(INSTALLED, encoding="utf-8") as handle:
            assert handle.read() == definition


class TestRouting:
    @pytest.mark.parametrize(
        "task",
        [
            "Size a gold trade on MT5: buy XAUUSD at 4452 with a stop at 4440",
            "How many lots should I trade on XAU/USD with 1% risk per trade?",
            "Check my prop firm daily loss limit before I open another gold position",
            "Review my MetaTrader 5 trading journal for the last month",
            "Plan a short on gold with a stop loss and take profit for the New York session",
            "What is my position size for a 12 dollar stop on XAUUSD?",
            "Trader 5: is this gold setup worth taking?",
        ],
    )
    def test_gold_trading_reaches_the_trader(self, task):
        assert AgentRouter().select_agent(task)["name"] == AGENT

    @pytest.mark.parametrize(
        "task, expected",
        [
            ("Add margin and padding to the card component in CSS", None),
            ("Use the spread operator to merge two objects in JavaScript", None),
            ("Make the header position sticky on scroll", None),
            ("Shortlist ready villas in Ras Al Khaimah for a Golden Visa purchase", "UAE Property Scout"),
            ("Create a React component for the toggle button", "Frontend Developer"),
            ("Build a React dashboard that shows stock prices", None),
        ],
    )
    def test_unrelated_work_does_not(self, task, expected):
        selected = AgentRouter().select_agent(task)["name"]
        assert selected != AGENT
        if expected:
            assert selected == expected

    def test_a_trade_is_not_split_across_agents(self):
        analysis = AgentRouter().analyze_task("Work out the lot size for a gold buy on MT5 with a 0.5% risk")
        assert [agent["name"] for agent in analysis["required_agents"]] == [AGENT]


class TestDefinitionMatchesEngine:
    def test_states_every_threshold(self, definition):
        rubric = section(definition, "### Rubric")
        for phrase in (
            f"risk above {HIGH_RISK_PCT:g}% of the account per trade",
            f"under {MIN_REWARD_RISK:g}R after costs",
            f"less than {TIGHT_HEADROOM:.0%} of a loss limit",
            f"a spread wider than {SPREAD_SHARE_LIMIT:.0%} of the stop distance",
            f"a margin level under {MARGIN_LEVEL_WARN:g}% after the trade",
            f"more than {SPEC_TOLERANCE:.0%} from",
            f"{MARGIN_ESTIMATE_FACTOR:g} times the estimate",
        ):
            assert phrase in rubric, phrase

    def test_states_how_the_budget_and_the_size_are_set(self, definition):
        rubric = section(definition, "### Rubric")
        assert "the lower of balance and equity" in rubric
        assert "rounded down to the volume step" in rubric
        assert "A swap credit is never counted" in rubric

    def test_states_how_each_floor_is_built(self, definition):
        rubric = section(definition, "### Rubric")
        for phrase in ("anchored at `day_start_balance`", "`high_water` less the limit", "the stricter floor"):
            assert phrase in rubric, phrase

    def test_lists_every_flag_with_its_level(self, definition):
        flags = section(definition, "### Flags")
        missing = [code for code, level in LEVELS.items() if f"| `{code}` | {level} |" not in flags]
        assert missing == []

    def test_states_the_atr_it_matches(self, definition):
        how = section(definition, "## Volatility and Stops")
        assert f"period {DEFAULT_PERIOD}" in how
        assert [method for method in METHODS if f"`{method}`" not in how] == []
        assert "MetaTrader 5's built-in ATR" in how

    def test_states_the_journal_sample(self, definition):
        assert f"fewer than {MIN_SAMPLE} trades" in section(definition, "## Journal Review")


class TestDefinitionMatchesTheInterface:
    @pytest.mark.parametrize(
        "heading, record",
        [
            ("### The symbol record", Symbol),
            ("### The account record", Account),
            ("### Open positions", OpenPosition),
            ("### The trade record", Trade),
            ("## Journal Review", ClosedTrade),
        ],
    )
    def test_names_every_field(self, definition, heading, record):
        text = section(definition, heading)
        assert [name for name in record.__dataclass_fields__ if f"`{name}`" not in text] == []

    def test_names_every_choice(self, definition):
        account = section(definition, "### The account record")
        assert [choice for choice in DAILY_BASES + MAX_LOSS_MODES if f"`{choice}`" not in account] == []
        trade = section(definition, "### The trade record")
        assert [side for side in SIDES if f"`{side}`" not in trade] == []

    def test_every_command_it_shows_is_one_the_engine_accepts(self, definition):
        commands = re.findall(r"python -m trade_desk ([^`\n]+)", definition)
        assert len(commands) >= 8
        parser = build_parser()
        for command in commands:
            args = shlex.split(command.split(">")[0])
            assert parser.parse_args(args).command == args[0], command
