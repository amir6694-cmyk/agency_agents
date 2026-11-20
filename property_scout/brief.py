"""The buyer brief: what the client wants, as hard limits and soft preferences."""

from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional

from .fields import Check, InputError
from .text import completion_slug, parse_period, slug

EMIRATES = (
    "dubai",
    "abu_dhabi",
    "sharjah",
    "ras_al_khaimah",
    "ajman",
    "umm_al_quwain",
    "fujairah",
)
MARKETS = ("offplan", "ready", "any")
PURPOSES = ("yield", "growth", "end_use", "golden_visa", "balanced")
FINANCING = ("cash", "mortgage")
NATIONALITIES = ("uae", "gcc", "other")
CRITERIA = ("value", "yield", "fit", "trust", "terms")
PROPERTY_TYPES = ("apartment", "villa", "townhouse", "penthouse", "duplex", "plot", "office")
HOUSE_TYPES = ("villa", "townhouse", "plot")
_TYPE_ALIASES = {
    "apartments": "apartment",
    "flat": "apartment",
    "flats": "apartment",
    "studio": "apartment",
    "hotel_apartment": "apartment",
    "hotel_apartments": "apartment",
    "villas": "villa",
    "townhouses": "townhouse",
    "town_house": "townhouse",
    "penthouses": "penthouse",
    "duplexes": "duplex",
    "land": "plot",
    "plots": "plot",
    "offices": "office",
}
MAX_BEDROOMS = 20


class BriefError(InputError):
    pass


def property_type_slug(value: str) -> str:
    key = slug(value)
    return _TYPE_ALIASES.get(key, key)


@dataclass
class Brief:
    budget_max: float
    budget_min: float = 0.0
    budget_includes_costs: bool = False
    market: str = "any"
    purpose: str = "balanced"
    emirates: List[str] = field(default_factory=list)
    areas: List[str] = field(default_factory=list)
    areas_strict: bool = False
    property_types: List[str] = field(default_factory=list)
    bedrooms_min: Optional[int] = None
    bedrooms_max: Optional[int] = None
    size_min_sqft: Optional[float] = None
    handover_by: Optional[str] = None
    handover_strict: bool = True
    financing: str = "cash"
    loan_to_value: Optional[float] = None
    buyer_nationality: str = "other"
    resident: bool = True
    first_home: Optional[bool] = None
    must_have: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    weights: Dict[str, float] = field(default_factory=dict)
    discount_rate: Optional[float] = None
    client: str = ""
    notes: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Brief":
        if not isinstance(data, dict):
            raise BriefError("brief must be a JSON object")
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise BriefError(f"unknown brief fields {unknown}; valid fields: {sorted(known)}")
        if data.get("budget_max") is None:
            raise BriefError("brief needs budget_max (AED)")
        check = Check(BriefError, "brief")
        get = data.get
        brief = cls(
            budget_max=check.number("budget_max", get("budget_max")),
            budget_min=check.number("budget_min", get("budget_min"), open_low=False) or 0.0,
            budget_includes_costs=bool(check.boolean("budget_includes_costs", get("budget_includes_costs"))),
            market=completion_slug(check.text("market", get("market")) or "any"),
            purpose=slug(check.text("purpose", get("purpose")) or "balanced"),
            emirates=list(dict.fromkeys(slug(e) for e in check.strings("emirates", get("emirates")))),
            areas=check.strings("areas", get("areas")),
            areas_strict=bool(check.boolean("areas_strict", get("areas_strict"))),
            property_types=list(
                dict.fromkeys(property_type_slug(t) for t in check.strings("property_types", get("property_types")))
            ),
            bedrooms_min=check.integer("bedrooms_min", get("bedrooms_min"), 0, MAX_BEDROOMS),
            bedrooms_max=check.integer("bedrooms_max", get("bedrooms_max"), 0, MAX_BEDROOMS),
            size_min_sqft=check.number("size_min_sqft", get("size_min_sqft")),
            handover_by=check.text("handover_by", get("handover_by")) or None,
            handover_strict=check.boolean("handover_strict", get("handover_strict")) is not False,
            financing=slug(check.text("financing", get("financing")) or "cash"),
            loan_to_value=check.number("loan_to_value", get("loan_to_value"), high=1.0),
            buyer_nationality=slug(check.text("buyer_nationality", get("buyer_nationality")) or "other"),
            resident=check.boolean("resident", get("resident")) is not False,
            first_home=check.boolean("first_home", get("first_home")),
            must_have=check.strings("must_have", get("must_have")),
            exclude=check.strings("exclude", get("exclude")),
            weights={
                name: check.number(f"weights.{name}", value, open_low=False)
                for name, value in check.mapping("weights", get("weights")).items()
            },
            discount_rate=check.number("discount_rate", get("discount_rate"), high=1.0, open_low=False),
            client=check.text("client", get("client")),
            notes=check.text("notes", get("notes")),
        )
        brief._validate(check)
        return brief

    def _validate(self, check: Check) -> None:
        if self.budget_min > self.budget_max:
            raise BriefError("brief: budget_min must not exceed budget_max")
        check.choice("market", self.market, MARKETS)
        check.choice("purpose", self.purpose, PURPOSES)
        check.choice("financing", self.financing, FINANCING)
        check.choice("buyer_nationality", self.buyer_nationality, NATIONALITIES)
        for emirate in self.emirates:
            check.choice("emirates", emirate, EMIRATES)
        for kind in self.property_types:
            check.choice("property_types", kind, PROPERTY_TYPES)
        if self.bedrooms_min is not None and self.bedrooms_max is not None and self.bedrooms_min > self.bedrooms_max:
            raise BriefError("brief: bedrooms_min must not exceed bedrooms_max")
        if self.loan_to_value == 1.0 or self.discount_rate == 1.0:
            raise BriefError("brief: loan_to_value and discount_rate are fractions below 1, e.g. 0.75 and 0.06")
        if self.handover_by is not None:
            try:
                parse_period(self.handover_by)
            except ValueError as exc:
                raise BriefError(f"brief: handover_by: {exc}") from exc
        for name, value in self.weights.items():
            check.choice("weights", name, CRITERIA)
            if value is None:
                raise BriefError(f"brief: weights.{name} must be a number")

    @property
    def is_first_home(self) -> bool:
        """Stated by the client, or else assumed only when the purchase is for own use."""
        return self.first_home if self.first_home is not None else self.purpose == "end_use"
