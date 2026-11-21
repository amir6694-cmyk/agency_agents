"""The UAE Property Scout must be routable, parseable, and in step with the engine it cites."""

import os
import re
import shlex

import pytest

from agent_router.config import PROJECT_ROOT, AgentConfig
from agent_router.personality import AgentPersonality
from agent_router.router import AgentRouter
from property_scout.brief import CRITERIA, NATIONALITIES, PROPERTY_TYPES, PURPOSES, Brief
from property_scout.cli import build_parser
from property_scout.comps import SIZE_BAND
from property_scout.costs import (
    GOLDEN_VISA_MIN_AED,
    LTV_CAP_HOME,
    LTV_CAP_HOME_ABOVE_THRESHOLD,
    LTV_CAP_INVESTMENT,
    LTV_CAP_OFFPLAN,
    SCHEDULES,
)
from property_scout.dedupe import CONFLICTING_TAGS, CONTRADICTING_FACTS, PRICE_TOLERANCE, SIZE_TOLERANCE
from property_scout.fields import LONG_TEXT, MAX_TEXT
from property_scout.listing import ANALYST_CAPS, EVIDENCE, INSTALMENT_KEYS, PLAN_STAGES, Listing
from property_scout.messages import UI
from property_scout.metrics import FIRST_YEAR_MONTHS
from property_scout.scoring import (
    ASSUMED_YIELD_LOSS,
    BEHIND_SCHEDULE_GAP,
    CONSIDER_SCORE,
    DEFAULT_DISCOUNT_RATE,
    HELD_AT_CONSIDER,
    DEVELOPER_TIER_POINTS,
    EVIDENCE_POINTS,
    FRESH_WITHIN_DAYS,
    IMPLAUSIBLE_GAP,
    IMPLAUSIBLE_GROSS_YIELD,
    NET_YIELD_RANGE,
    OFFPLAN_PREMIUM_LIMIT,
    PROFILES,
    RATED_CONFIDENCE,
    RECENT_WITHIN_DAYS,
    RUNNING_COST_RATIO,
    SHORTLIST_SCORE,
    TERMS_BEST_BENEFIT,
    VALUE_BEST_GAP,
    VALUE_WORST_GAP,
    VISA_MARGIN,
)

AGENT = "UAE Property Scout"
SOURCE = os.path.join(PROJECT_ROOT, "agents", "real-estate", "real-estate-uae-property-scout.md")
INSTALLED = os.path.join(PROJECT_ROOT, ".claude", "agents", "uae-property-scout.md")


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
        assert agent["category"] == "real-estate"
        assert agent["file_path"] == SOURCE
        assert agent["is_default"] is False

    def test_definition_parses_into_a_full_personality(self):
        personality = AgentPersonality().load_agent(AGENT)
        assert personality["name"] == "uae-property-scout"
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
        rubric = section(definition, "### Rubric")
        level = 100 * VALUE_WORST_GAP / (VALUE_WORST_GAP - VALUE_BEST_GAP)
        assert f"{abs(VALUE_BEST_GAP):.0%} below scores 100" in rubric
        assert f"level scores {level:.0f}" in rubric
        assert f"{VALUE_WORST_GAP:.0%} above scores 0" in rubric
        assert f"A price {abs(IMPLAUSIBLE_GAP):.0%} or more below its benchmark is a critical flag" in rubric
        assert f"An ask {VALUE_WORST_GAP:.0%} or more above" in rubric

    def test_states_the_yield_scale_and_how_a_gross_figure_is_treated(self, definition):
        rubric = section(definition, "### Rubric")
        low, high = NET_YIELD_RANGE
        assert f"Net yield from {low * 100:g}% (0) to {high * 100:g}% (100)" in rubric
        assert f"the gross yield less {ASSUMED_YIELD_LOSS * 100:g} points" in rubric
        assert f"a gross yield above {IMPLAUSIBLE_GROSS_YIELD:.0%}" in rubric
        assert f"plus {RUNNING_COST_RATIO:.0%} of rent" in section(definition, "### Yield")

    def test_states_how_trust_is_built(self, definition):
        rubric = section(definition, "### Rubric")
        levels = ", ".join(f"{level} {EVIDENCE_POINTS[level]:g}" for level in EVIDENCE)
        tiers = ", ".join(f"{DEVELOPER_TIER_POINTS[tier]:g}" for tier in sorted(DEVELOPER_TIER_POINTS))
        assert f"evidence level ({levels})" in rubric
        assert f"seen within {FRESH_WITHIN_DAYS} days (1) or {RECENT_WITHIN_DAYS} days (0.5)" in rubric
        assert f"the developer's tier ({tiers})" in rubric

    def test_states_the_terms_scale_and_the_discount_rate(self, definition):
        assert f"a benefit worth {TERMS_BEST_BENEFIT:.0%} of the price scores 100" in section(definition, "### Rubric")
        assert f"discounts at {DEFAULT_DISCOUNT_RATE:.0%} a year by default" in definition
        assert f"flags one over {OFFPLAN_PREMIUM_LIMIT:.0%}" in definition

    def test_states_the_verdict_thresholds(self, definition):
        rubric = section(definition, "### Rubric")
        assert f"**shortlist** at a score of {SHORTLIST_SCORE:.0f} or more" in rubric
        assert f"**consider** from {CONSIDER_SCORE:.0f}" in rubric
        assert f"data completeness is under {RATED_CONFIDENCE:.0%}" in rubric

    def test_states_what_holds_an_offer_back(self, definition):
        rubric = section(definition, "### Rubric")
        assert f"an uncorroborated first sale {abs(VALUE_BEST_GAP):.0%} or more below registered sales" in rubric
        assert f"an ask {VALUE_WORST_GAP:.0%} or more above a benchmark of fewer than five sales" in rubric
        assert f"more than {BEHIND_SCHEDULE_GAP * 100:.0f} points ahead of the share built" in definition
        for gap in (
            "rent with no service charge to cost it",
            "an off-plan first sale with no payment plan recorded",
            "with no completion date still ahead read from the register",
        ):
            assert gap in rubric, gap
        assert {"service_charge_unknown", "no_plan", "plan_date_unconfirmed"} <= set(HELD_AT_CONSIDER)

    def test_states_the_limits_that_hold_an_offer_when_untested(self, definition):
        rubric = section(definition, "### Rubric")
        for phrase in (
            "(emirate, completion status, bedroom count or property type not stated",
            "an exclusion the record gives nothing to test on",
            "a home recorded as ready whose handover or registered completion date is still ahead",
            "where the brief weighs income",
            "Equal scores are ordered by the fuller data, then by the lower total outlay",
        ):
            assert phrase in rubric, phrase
        assert {"emirate_missing", "exclusion_untested", "completion_contradicted"} <= set(HELD_AT_CONSIDER)
        assert [fact for fact in CONTRADICTING_FACTS if fact.replace("_", " ") not in rubric] == []
        assert "it needs both `building` and `developer`" in definition

    def test_quotes_the_headings_a_held_offer_is_given(self, definition):
        rubric = section(definition, "### Rubric")
        assert f'"{UI["en"]["verdict.held"]}"' in rubric
        assert UI["en"]["verdict.held_analyst"].endswith("held back by the analyst") and '"held back by the analyst"' in rubric

    def test_describes_dated_instalments_and_the_first_year(self, definition):
        record = section(definition, "### The listing record")
        assert [key for key in INSTALMENT_KEYS if f'"{key}"' not in record] == []
        assert FIRST_YEAR_MONTHS == 12 and "what falls due in the first twelve months" in definition
        assert "counts only when it raises the score" in section(definition, "### Rubric")

    def test_describes_how_rows_are_left_out_of_a_benchmark(self, definition):
        args = build_parser().parse_args(["comps", "--rows", "rows.json", "--exclude-project", "Tower A"])
        assert args.exclude_project == ["Tower A"]
        assert '`--exclude-project "Name"`' in definition and '`"excluded": "bulk transaction"`' in definition

    def test_states_the_folding_tolerances(self, definition):
        rubric = section(definition, "### Rubric")
        assert f"size within {SIZE_TOLERANCE:.0%}" in rubric and f"price within {PRICE_TOLERANCE:.0%}" in rubric
        assert f"Drop sizes more than {SIZE_BAND:.0%} from the subject" in definition

    @pytest.mark.parametrize("purpose", sorted(PROFILES))
    def test_weight_table_row_matches_the_profile(self, definition, purpose):
        cells = " | ".join(f"{PROFILES[purpose][name]:.0%}" for name in CRITERIA)
        assert f"| `{purpose}` | {cells} |" in definition

    def test_states_the_lending_caps_and_the_visa_threshold(self, definition):
        costs = section(definition, "## Costs, Finance and Residency")
        caps = (
            f"{LTV_CAP_HOME:.0%} of value up to AED 5 million for a first home, {LTV_CAP_HOME_ABOVE_THRESHOLD:.0%} above; "
            f"{LTV_CAP_INVESTMENT:.0%} for a second or investment property; {LTV_CAP_OFFPLAN:.0%} off-plan for every borrower"
        )
        assert caps in costs
        assert f"AED {GOLDEN_VISA_MIN_AED / 1e6:g} million or more" in costs
        assert f"within {VISA_MARGIN:.0%} of the threshold" in costs

    @pytest.mark.parametrize("emirate, label", [("dubai", "Dubai"), ("abu_dhabi", "Abu Dhabi"), ("sharjah", "Sharjah"), ("ras_al_khaimah", "Ras Al Khaimah"), ("ajman", "Ajman")])
    def test_fee_table_row_states_the_schedule(self, definition, emirate, label):
        schedule = SCHEDULES[emirate]
        row = next(line for line in section(definition, "## Costs, Finance and Residency").splitlines() if line.startswith(f"| {label} |"))
        figures = [f"{schedule.transfer_rate * 100:g}%", f"AED {schedule.fixed_ready:,.0f}"]
        if schedule.fixed_offplan != schedule.fixed_ready:
            figures.append(f"AED {schedule.fixed_offplan:,.0f}")
        if schedule.transfer_rate_reduced:
            figures.append(f"{schedule.transfer_rate_reduced * 100:g}% for UAE and GCC nationals")
        if schedule.transfer_minimum:
            figures += [f"minimum AED {schedule.transfer_minimum:,.0f}", f"minimum AED {schedule.transfer_minimum_reduced:,.0f}"]
        if schedule.agency_rate:
            figures.append(f"{'agency' if emirate == 'dubai' else 'Agency'} {schedule.agency_rate * 100:g}%")
        if schedule.agency_cap:
            figures.append(f"capped at AED {schedule.agency_cap:,.0f}")
        if schedule.mortgage_rate:
            figures.append(f"{'Mortgage' if emirate == 'dubai' else 'mortgage'} {schedule.mortgage_rate * 100:g}% of loan")
        for figure in figures:
            assert figure in row, figure


class TestDefinitionMatchesTheInterface:
    def test_names_every_listing_field(self, definition):
        record = section(definition, "### The listing record")
        missing = [name for name in Listing.__dataclass_fields__ if f"`{name}`" not in record]
        assert missing == []

    def test_names_no_listing_field_that_does_not_exist(self, definition):
        table = [line for line in section(definition, "### The listing record").splitlines() if line.startswith("| ")][2:]
        named = set(re.findall(r"`([a-z_0-9]+)`", " ".join(table)))
        choices = set(EVIDENCE) | {"ready", "offplan", "resale", "primary"}
        assert named - choices <= set(Listing.__dataclass_fields__)

    def test_names_every_brief_field_and_choice(self, definition):
        intake = section(definition, "## Intake: the Brief")
        wanted = list(Brief.__dataclass_fields__) + list(PURPOSES) + list(PROPERTY_TYPES) + list(NATIONALITIES)
        assert [name for name in wanted if f"`{name}`" not in intake] == []

    def test_states_the_limits_of_a_record_and_the_tags_that_keep_adverts_apart(self, definition):
        record = section(definition, "### The listing record")
        assert f"Text fields hold {MAX_TEXT} characters" in record and f"hold {LONG_TEXT:,}" in record
        tags = [tag for group in CONFLICTING_TAGS for tag in group]
        assert [tag for tag in tags if f"`{tag}`" not in record] == []

    def test_states_the_default_window_of_the_comps_command(self, definition):
        assert build_parser().parse_args(["comps", "--rows", "rows.json"]).months == 12
        assert "It looks back twelve months unless `--months` says otherwise" in definition

    def test_names_the_plan_stages_and_analyst_caps(self, definition):
        record = section(definition, "### The listing record")
        assert [name for name in PLAN_STAGES + ANALYST_CAPS if f"`{name}`" not in record] == []

    def test_every_command_it_shows_is_one_the_engine_accepts(self, definition):
        commands = re.findall(r"python -m property_scout ([^`\n]+)", definition)
        assert len(commands) >= 10
        parser = build_parser()
        for command in commands:
            args = shlex.split(command.split(">")[0])
            assert parser.parse_args(args).command == args[0], command
