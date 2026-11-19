import pytest

from property_scout.brief import CRITERIA, EMIRATES, Brief, BriefError


class TestBriefParsing:
    def test_minimal_brief_gets_defaults(self):
        brief = Brief.from_dict({"budget_max": 1_000_000})
        assert brief.market == "any"
        assert brief.purpose == "balanced"
        assert brief.financing == "cash"
        assert brief.emirates == []

    def test_normalises_free_text_choices(self):
        brief = Brief.from_dict(
            {"budget_max": 1_000_000, "market": "Off-Plan", "emirates": ["Abu Dhabi"], "property_types": ["Villa"]}
        )
        assert brief.market == "offplan"
        assert brief.emirates == ["abu_dhabi"]
        assert brief.property_types == ["villa"]

    def test_secondary_means_ready(self):
        assert Brief.from_dict({"budget_max": 1, "market": "secondary"}).market == "ready"

    def test_every_emirate_is_accepted(self):
        brief = Brief.from_dict({"budget_max": 1, "emirates": list(EMIRATES)})
        assert brief.emirates == list(EMIRATES)


class TestBriefValidation:
    def test_requires_budget(self):
        with pytest.raises(BriefError, match="budget_max"):
            Brief.from_dict({"market": "ready"})

    def test_rejects_non_object(self):
        with pytest.raises(BriefError):
            Brief.from_dict(["budget_max", 1])

    def test_names_unknown_fields(self):
        with pytest.raises(BriefError, match="budget"):
            Brief.from_dict({"budget_max": 1, "budget": 2})

    @pytest.mark.parametrize(
        "field, value",
        [
            ("budget_max", 0),
            ("budget_max", "2m"),
            ("budget_min", 5_000_000),
            ("market", "rental"),
            ("purpose", "flip"),
            ("financing", "crypto"),
            ("emirates", ["qatar"]),
            ("loan_to_value", 75),
            ("discount_rate", 7),
            ("handover_by", "next year"),
            ("weights", {"vibes": 1}),
            ("weights", {"value": -1}),
        ],
    )
    def test_rejects_bad_values(self, field, value):
        data = {"budget_max": 2_000_000}
        data[field] = value
        with pytest.raises(BriefError):
            Brief.from_dict(data)

    def test_rejects_inverted_bedroom_range(self):
        with pytest.raises(BriefError):
            Brief.from_dict({"budget_max": 1, "bedrooms_min": 3, "bedrooms_max": 1})

    def test_accepts_every_criterion_as_a_weight(self):
        brief = Brief.from_dict({"budget_max": 1, "weights": {name: 1 for name in CRITERIA}})
        assert set(brief.weights) == set(CRITERIA)
