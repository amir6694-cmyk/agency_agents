from datetime import date

import pytest

from property_scout.text import completion_slug, contains, months_until, norm, parse_period, slug


class TestNormalisation:
    def test_norm_collapses_case_and_punctuation(self):
        assert norm("  Marina-Gate  1, Dubai ") == "marina gate 1 dubai"

    def test_norm_of_nothing_is_empty(self):
        assert norm(None) == ""

    def test_slug_uses_underscores(self):
        assert slug("Abu Dhabi") == "abu_dhabi"

    @pytest.mark.parametrize("raw", ["Off-Plan", "off plan", "Under Construction", "offplan"])
    def test_offplan_aliases(self, raw):
        assert completion_slug(raw) == "offplan"

    @pytest.mark.parametrize("raw", ["Ready", "completed", "Secondary", "resale"])
    def test_ready_aliases(self, raw):
        assert completion_slug(raw) == "ready"


class TestContains:
    def test_matches_whole_words(self):
        assert contains("Dubai Marina, Marina Gate 1", "marina gate")

    def test_rejects_partial_words(self):
        assert not contains("Dubai Marina", "mari")

    def test_empty_needle_never_matches(self):
        assert not contains("Dubai Marina", " ")


class TestPeriods:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("2027-Q4", (2027, 12)),
            ("Q2 2028", (2028, 6)),
            ("2027-11", (2027, 11)),
            ("2029", (2029, 12)),
            ("2027 q1", (2027, 3)),
        ],
    )
    def test_parses_supported_forms(self, raw, expected):
        assert parse_period(raw) == expected

    @pytest.mark.parametrize("raw", ["soon", "2027-13", "Q5 2027", "27"])
    def test_rejects_unsupported_forms(self, raw):
        with pytest.raises(ValueError):
            parse_period(raw)

    def test_months_until_counts_to_period_end(self):
        assert months_until("2027-Q4", date(2026, 11, 19)) == 13

    def test_months_until_is_negative_for_the_past(self):
        assert months_until("2026-Q2", date(2026, 11, 19)) == -5
