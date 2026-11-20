import math

import pytest

from property_scout.fields import MAX_TEXT, Check, InputError


class Refused(InputError):
    pass


@pytest.fixture
def check():
    return Check(Refused, "row 3")


class TestText:
    def test_strips_and_accepts_nothing_as_empty(self, check):
        assert check.text("title", "  Sea view  ") == "Sea view"
        assert check.text("title", None) == ""

    @pytest.mark.parametrize("value", [5, True, ["a"], {"a": 1}])
    def test_refuses_anything_but_text(self, check, value):
        with pytest.raises(Refused, match="row 3: title must be text"):
            check.text("title", value)

    @pytest.mark.parametrize("value", ["two\nlines", "tab\there", "nul\x00", "line separator"])
    def test_refuses_control_characters(self, check, value):
        with pytest.raises(Refused, match="one line"):
            check.text("title", value)

    def test_refuses_overlong_text(self, check):
        assert check.text("notes", "x" * MAX_TEXT)
        with pytest.raises(Refused, match="longer"):
            check.text("notes", "x" * (MAX_TEXT + 1))


class TestNumber:
    def test_accepts_whole_and_fractional_numbers(self, check):
        assert check.number("price", 5) == 5
        assert check.number("price", 2.5) == 2.5
        assert check.number("price", None) is None

    @pytest.mark.parametrize("value", ["5", "1,800,000", True, False, [5]])
    def test_refuses_text_and_booleans(self, check, value):
        with pytest.raises(Refused, match="must be a number"):
            check.number("price", value)

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_refuses_values_that_are_not_finite(self, check, value):
        with pytest.raises(Refused):
            check.number("price", value)

    def test_lower_bound_is_exclusive_unless_opened(self, check):
        with pytest.raises(Refused, match="> 0"):
            check.number("price", 0)
        assert check.number("share", 0, open_low=False) == 0
        with pytest.raises(Refused, match=">= 0"):
            check.number("share", -1, open_low=False)

    def test_upper_bound_is_inclusive(self, check):
        assert check.number("share", 100, high=100) == 100
        with pytest.raises(Refused, match="<= 100"):
            check.number("share", 100.5, high=100)


class TestInteger:
    def test_accepts_whole_numbers_in_range(self, check):
        assert check.integer("beds", 0, 0, 20) == 0
        assert check.integer("beds", 20, 0, 20) == 20
        assert check.integer("beds", None, 0, 20) is None

    @pytest.mark.parametrize("value", [1.5, 2.0, "2", True])
    def test_refuses_fractions_text_and_booleans(self, check, value):
        with pytest.raises(Refused, match="whole number"):
            check.integer("beds", value, 0, 20)

    @pytest.mark.parametrize("value", [-1, 21])
    def test_refuses_values_out_of_range(self, check, value):
        with pytest.raises(Refused, match="between 0 and 20"):
            check.integer("beds", value, 0, 20)


class TestBoolean:
    @pytest.mark.parametrize("value", [True, False, None])
    def test_three_states_pass_through(self, check, value):
        assert check.boolean("verified", value) is value

    @pytest.mark.parametrize("value", ["true", "yes", 1, 0])
    def test_refuses_lookalikes(self, check, value):
        with pytest.raises(Refused, match="true, false or null"):
            check.boolean("verified", value)


class TestCollections:
    def test_strings_drops_blanks(self, check):
        assert check.strings("tags", [" a ", "", "b"]) == ["a", "b"]
        assert check.strings("tags", None) == []

    @pytest.mark.parametrize("value", ["dubai", {"a": 1}, 5])
    def test_strings_must_be_a_list(self, check, value):
        with pytest.raises(Refused, match="list"):
            check.strings("tags", value)

    def test_strings_checks_each_item(self, check):
        with pytest.raises(Refused, match="must be text"):
            check.strings("tags", ["a", 5])

    def test_mapping(self, check):
        assert check.mapping("weights", {"a": 1}) == {"a": 1}
        assert check.mapping("weights", None) == {}
        with pytest.raises(Refused, match="object"):
            check.mapping("weights", [("a", 1)])

    def test_choice_names_the_allowed_values(self, check):
        assert check.choice("market", "ready", ("ready", "offplan")) == "ready"
        with pytest.raises(Refused, match="offplan"):
            check.choice("market", "rental", ("ready", "offplan"))


class TestDay:
    def test_accepts_a_date_and_the_date_part_of_a_timestamp(self, check):
        assert check.day("seen", "2026-11-19") == "2026-11-19"
        assert check.day("seen", "2026-11-19T08:30:00Z") == "2026-11-19"
        assert check.day("seen", None) is None and check.day("seen", "") is None

    @pytest.mark.parametrize("value", ["19/11/2026", "2026-02-30", "2026-11", "yesterday", 20261119, "2026-11-19x"])
    def test_refuses_anything_else(self, check, value):
        with pytest.raises(Refused, match="YYYY-MM-DD"):
            check.day("seen", value)
