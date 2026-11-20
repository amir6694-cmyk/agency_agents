import math

import pytest

from property_scout.brief import CRITERIA, EMIRATES, NATIONALITIES, PROPERTY_TYPES, Brief, BriefError, property_type_slug


class TestBriefParsing:
    def test_minimal_brief_gets_defaults(self):
        brief = Brief.from_dict({"budget_max": 1_000_000})
        assert (brief.market, brief.purpose, brief.financing, brief.buyer_nationality) == ("any", "balanced", "cash", "other")
        assert brief.emirates == [] and brief.budget_min == 0
        assert brief.handover_strict is True and brief.resident is True and brief.first_home is None

    def test_normalises_free_text_choices(self):
        brief = Brief.from_dict(
            {"budget_max": 1_000_000, "market": "Off-Plan", "emirates": ["Abu Dhabi"], "property_types": ["Villas"], "buyer_nationality": "GCC"}
        )
        assert brief.market == "offplan"
        assert brief.emirates == ["abu_dhabi"]
        assert brief.property_types == ["villa"]
        assert brief.buyer_nationality == "gcc"

    def test_secondary_means_ready(self):
        assert Brief.from_dict({"budget_max": 1, "market": "secondary"}).market == "ready"

    def test_every_emirate_nationality_and_type_is_accepted(self):
        brief = Brief.from_dict({"budget_max": 1, "emirates": list(EMIRATES), "property_types": list(PROPERTY_TYPES)})
        assert brief.emirates == list(EMIRATES) and brief.property_types == list(PROPERTY_TYPES)
        for nationality in NATIONALITIES:
            assert Brief.from_dict({"budget_max": 1, "buyer_nationality": nationality}).buyer_nationality == nationality

    def test_repeats_are_folded(self):
        brief = Brief.from_dict({"budget_max": 1, "emirates": ["Dubai", "dubai"], "property_types": ["flat", "Apartments"]})
        assert brief.emirates == ["dubai"] and brief.property_types == ["apartment"]

    @pytest.mark.parametrize("raw, kind", [("Flat", "apartment"), ("Studio", "apartment"), ("Town House", "townhouse"), ("Land", "plot"), ("villa", "villa")])
    def test_property_type_aliases(self, raw, kind):
        assert property_type_slug(raw) == kind

    def test_switches_can_be_turned_off(self):
        brief = Brief.from_dict({"budget_max": 1, "handover_strict": False, "resident": False})
        assert brief.handover_strict is False and brief.resident is False

    @pytest.mark.parametrize("purpose, stated, expected", [("end_use", None, True), ("yield", None, False), ("yield", True, True), ("end_use", False, False)])
    def test_first_home_is_stated_or_assumed_from_the_purpose(self, purpose, stated, expected):
        assert Brief.from_dict({"budget_max": 1, "purpose": purpose, "first_home": stated}).is_first_home is expected


class TestBriefValidation:
    def test_requires_budget(self):
        with pytest.raises(BriefError, match="budget_max"):
            Brief.from_dict({"market": "ready"})

    def test_rejects_non_object(self):
        with pytest.raises(BriefError):
            Brief.from_dict(["budget_max", 1])

    def test_names_unknown_fields(self):
        with pytest.raises(BriefError, match="gcc_national"):
            Brief.from_dict({"budget_max": 1, "gcc_national": True})

    @pytest.mark.parametrize(
        "field, value",
        [
            ("budget_max", 0),
            ("budget_max", "2m"),
            ("budget_max", True),
            ("budget_max", math.nan),
            ("budget_min", 5_000_000),
            ("budget_min", -1),
            ("budget_includes_costs", "yes"),
            ("market", "rental"),
            ("purpose", "flip"),
            ("financing", "crypto"),
            ("buyer_nationality", "french"),
            ("emirates", ["qatar"]),
            ("emirates", "dubai"),
            ("property_types", ["castle"]),
            ("bedrooms_min", 1.5),
            ("bedrooms_min", "2"),
            ("bedrooms_max", 99),
            ("size_min_sqft", 0),
            ("loan_to_value", 75),
            ("loan_to_value", 1.0),
            ("discount_rate", 7),
            ("discount_rate", 1.0),
            ("handover_by", "next year"),
            ("handover_strict", "no"),
            ("weights", {"vibes": 1}),
            ("weights", {"value": -1}),
            ("weights", {"value": None}),
            ("weights", [1, 2]),
            ("client", "Two\nlines"),
            ("areas", [5]),
        ],
    )
    def test_rejects_bad_values(self, field, value):
        data = {"budget_max": 2_000_000}
        data[field] = value
        with pytest.raises(BriefError):
            Brief.from_dict(data)

    def test_the_error_names_the_field_and_the_value(self):
        with pytest.raises(BriefError, match=r"brief: budget_max must be a number, not text, got '2m'"):
            Brief.from_dict({"budget_max": "2m"})

    def test_rejects_inverted_bedroom_range(self):
        with pytest.raises(BriefError, match="bedrooms_min"):
            Brief.from_dict({"budget_max": 1, "bedrooms_min": 3, "bedrooms_max": 1})

    def test_accepts_every_criterion_as_a_weight(self):
        brief = Brief.from_dict({"budget_max": 1, "weights": {name: 1 for name in CRITERIA}})
        assert set(brief.weights) == set(CRITERIA)

    @pytest.mark.parametrize("period", ["2027-Q4", "Q4 2027", "Dec 2027", "2027-12-31", "2027"])
    def test_accepts_every_way_of_writing_a_deadline(self, period):
        assert Brief.from_dict({"budget_max": 1, "handover_by": period}).handover_by == period
