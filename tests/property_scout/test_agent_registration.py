"""The UAE Property Scout must be routable, parseable, and in step with the engine it cites."""

import os

import pytest

from agent_router.config import PROJECT_ROOT, AgentConfig
from agent_router.personality import AgentPersonality
from agent_router.router import AgentRouter
from property_scout.brief import CRITERIA
from property_scout.scoring import (
    GROSS_YIELD_RANGE,
    IMPLAUSIBLE_GAP,
    NET_YIELD_RANGE,
    PROFILES,
    RATED_CONFIDENCE,
    SHORTLIST_SCORE,
    VALUE_BEST_GAP,
    VALUE_WORST_GAP,
)

AGENT = "UAE Property Scout"
SOURCE = os.path.join(PROJECT_ROOT, "agents", "real-estate", "real-estate-uae-property-scout.md")
INSTALLED = os.path.join(PROJECT_ROOT, ".claude", "agents", "uae-property-scout.md")


@pytest.fixture
def definition():
    with open(SOURCE, encoding="utf-8") as handle:
        return handle.read()


class TestRegistration:
    def test_registered_with_an_existing_file(self):
        agent = AgentConfig().get_agent_by_name(AGENT)
        assert agent is not None
        assert agent["category"] == "real-estate"
        assert agent["file_path"] == SOURCE
        assert agent["is_default"] is False

    def test_definition_parses_into_a_full_personality(self):
        personality = AgentPersonality().load_agent(AGENT)
        assert personality["name"] == "uae-property-scout"
        for section in ("core_mission", "workflow_process", "success_metrics"):
            assert len(personality[section]) >= 4, section
        assert personality["communication_style"]["tone"]
        assert len(personality["deliverables"]) >= 2

    def test_claude_code_copy_is_identical_to_the_source(self, definition):
        with open(INSTALLED, encoding="utf-8") as handle:
            assert handle.read() == definition


class TestRouting:
    @pytest.mark.parametrize(
        "task",
        [
            "Find a 2 bedroom apartment in Dubai Marina under AED 3,000,000 for investment",
            "Compare off-plan projects in Abu Dhabi with a post-handover payment plan",
            "Shortlist ready villas in Ras Al Khaimah for a Golden Visa purchase",
            "Which real estate offers in Sharjah give the best rental yield?",
            "Подбери квартиру в Дубае до 2 млн дирхам, офф-план, сдача в 2027",
            "Нужна вилла в Абу-Даби на вторичке для семьи, бюджет 6 млн",
            "Найди лучшие предложения недвижимости в ОАЭ с рассрочкой от застройщика",
        ],
    )
    def test_property_briefs_reach_the_scout(self, task):
        assert AgentRouter().select_agent(task)["name"] == AGENT

    @pytest.mark.parametrize(
        "task, expected",
        [
            ("Create a React component for the toggle button", "Frontend Developer"),
            ("Design a PostgreSQL database schema with indexes", "Backend Architect"),
            ("Build a landing page for a Dubai real estate agency", None),
            ("Сделай лендинг для агентства недвижимости в Дубае", None),
            ("Format prices in AED on the checkout screen", None),
            ("Напиши unit-тесты для модуля авторизации", None),
        ],
    )
    def test_unrelated_work_does_not(self, task, expected):
        selected = AgentRouter().select_agent(task)["name"]
        assert selected != AGENT
        if expected:
            assert selected == expected

    def test_a_brief_is_not_split_across_agents(self):
        analysis = AgentRouter().analyze_task("Find a 1 bedroom apartment for sale in Business Bay with a payment plan")
        assert [agent["name"] for agent in analysis["required_agents"]] == [AGENT]


class TestDefinitionMatchesEngine:
    def test_states_the_value_scale(self, definition):
        assert f"{abs(VALUE_BEST_GAP):.0%} below" in definition
        assert f"{VALUE_WORST_GAP:.0%} above" in definition
        assert f"{abs(IMPLAUSIBLE_GAP):.0%}" in definition

    def test_states_the_yield_scales(self, definition):
        for low, high in (NET_YIELD_RANGE, GROSS_YIELD_RANGE):
            assert f"{low * 100:g}%" in definition and f"{high * 100:g}%" in definition

    def test_states_the_shortlist_bar(self, definition):
        assert f"{SHORTLIST_SCORE:.0f}" in definition and f"{RATED_CONFIDENCE:.0%}" in definition

    @pytest.mark.parametrize("purpose", sorted(PROFILES))
    def test_weight_table_row_matches_the_profile(self, definition, purpose):
        cells = " | ".join(f"{PROFILES[purpose][name]:.0%}" for name in CRITERIA)
        assert f"| `{purpose}` | {cells} |" in definition
