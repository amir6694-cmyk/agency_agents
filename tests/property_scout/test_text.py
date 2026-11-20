from datetime import date

import pytest

from property_scout.text import MAX_YEAR, MIN_YEAR, completion_slug, has_words, months_until, norm, parse_period, period_end, place, same_place, slug


class TestNormalisation:
    def test_norm_collapses_case_and_punctuation(self):
        assert norm("  Marina-Gate  1, Dubai ") == "marina gate 1 dubai"

    def test_norm_of_nothing_is_empty(self):
        assert norm(None) == "" and norm("") == ""

    def test_norm_strips_accents_and_keeps_other_scripts(self):
        assert norm("Résidence Élysée") == "residence elysee"
        assert norm("Дубай Марина") == norm("ДУБАЙ-МАРИНА") != ""
        assert norm("دبي مارينا") != ""

    def test_slug_uses_underscores(self):
        assert slug("Abu Dhabi") == "abu_dhabi"

    @pytest.mark.parametrize("raw", ["Off-Plan", "off plan", "Under Construction", "offplan"])
    def test_offplan_aliases(self, raw):
        assert completion_slug(raw) == "offplan"

    @pytest.mark.parametrize("raw", ["Ready", "completed"])
    def test_ready_aliases(self, raw):
        assert completion_slug(raw) == "ready"

    def test_a_sale_type_is_not_a_completion_status(self):
        assert completion_slug("resale") == "resale" and completion_slug("secondary") == "secondary"


class TestPlaces:
    @pytest.mark.parametrize(
        "short, full",
        [
            ("JVC", "Jumeirah Village Circle"),
            ("Marina", "Dubai Marina"),
            ("Downtown", "Downtown Dubai"),
            ("The Palm", "Palm Jumeirah"),
            ("Al Reem", "Al Reem Island"),
            ("Yas", "Yas Island"),
        ],
    )
    def test_short_forms_match_the_portal_name(self, short, full):
        assert same_place(short, full) and same_place(full, short)

    def test_an_unknown_place_is_itself(self):
        assert place("Business Bay") == "business bay"

    @pytest.mark.parametrize(
        "written, filed",
        [
            ("Jumeirah Village Circle (JVC)", "jumeirah village circle"),
            ("Jumeirah Village Circle, Dubai", "jumeirah village circle"),
            ("The Palm Jumeirah", "palm jumeirah"),
            ("Business Bay, Dubai, UAE", "business bay"),
            ("(JLT)", "jumeirah lake towers"),
            ("Al Reem Island (Abu Dhabi)", "al reem island"),
        ],
    )
    def test_a_decorated_name_is_read_as_the_place(self, written, filed):
        assert place(written) == filed

    def test_different_places_do_not_match(self):
        assert not same_place("Dubai Marina", "Dubai Marina Mall Hotel")
        assert not same_place("Business Bay", "Dubai Marina")

    def test_nothing_matches_nothing(self):
        assert not same_place(None, None) and not same_place("", "Dubai Marina")


class TestHasWords:
    def test_matches_whole_words(self):
        assert has_words("Dubai Marina, Marina Gate 1", "marina gate")

    def test_rejects_partial_words(self):
        assert not has_words("Dubai Marina", "mari")

    def test_empty_needle_never_matches(self):
        assert not has_words("Dubai Marina", " ") and not has_words(None, "marina")


class TestPeriods:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("2027-Q4", (2027, 10, 12)),
            ("Q2 2028", (2028, 4, 6)),
            ("Q4, 2027", (2027, 10, 12)),
            ("2027 q1", (2027, 1, 3)),
            ("2027-11", (2027, 11, 11)),
            ("2027-11-30", (2027, 11, 11)),
            ("Nov 2027", (2027, 11, 11)),
            ("December 2028", (2028, 12, 12)),
            ("2029", (2029, 1, 12)),
        ],
    )
    def test_parses_supported_forms(self, raw, expected):
        assert parse_period(raw) == expected

    @pytest.mark.parametrize("raw", ["soon", "2027-13", "Q5 2027", "27", "Foo 2027", "2027-00", ""])
    def test_rejects_unsupported_forms(self, raw):
        with pytest.raises(ValueError, match="unrecognised period"):
            parse_period(raw)

    @pytest.mark.parametrize("raw", [f"{MIN_YEAR - 1}-Q4", f"{MAX_YEAR + 1}", "3027-11", "0001-01-01"])
    def test_rejects_years_no_handover_could_fall_in(self, raw):
        with pytest.raises(ValueError, match="year outside"):
            parse_period(raw)

    @pytest.mark.parametrize(
        "raw, last_day",
        [
            ("2026-11-01", date(2026, 11, 1)),
            ("2026-11", date(2026, 11, 30)),
            ("Nov 2026", date(2026, 11, 30)),
            ("2026-Q4", date(2026, 12, 31)),
            ("2026", date(2026, 12, 31)),
            ("2028-02", date(2028, 2, 29)),
            ("2027-02-31", date(2027, 2, 28)),
        ],
    )
    def test_period_end_keeps_the_day_when_one_is_written(self, raw, last_day):
        assert period_end(raw) == last_day

    def test_months_until_counts_to_period_end(self):
        assert months_until("2027-Q4", date(2026, 11, 19)) == 13

    def test_months_until_can_count_to_the_period_start(self):
        assert months_until("2027-Q4", date(2026, 11, 19), start=True) == 11
        assert months_until("2029", date(2026, 11, 19), start=True) == 26

    def test_months_until_is_negative_for_the_past(self):
        assert months_until("2026-Q2", date(2026, 11, 19)) == -5
