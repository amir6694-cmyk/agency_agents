"""The buyer brief: what the client wants, as hard limits and soft preferences."""

from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional

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
CRITERIA = ("value", "yield", "fit", "trust", "terms")


class BriefError(ValueError):
    pass


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
    financing: str = "cash"
    loan_to_value: Optional[float] = None
    gcc_national: bool = False
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
        if "budget_max" not in data:
            raise BriefError("brief needs budget_max (AED)")
        brief = cls(**data)
        brief._normalise()
        brief._validate()
        return brief

    def _normalise(self) -> None:
        self.market = completion_slug(self.market)
        self.purpose = slug(self.purpose)
        self.financing = slug(self.financing)
        self.emirates = [slug(e) for e in self.emirates]
        self.property_types = [slug(t) for t in self.property_types]

    def _validate(self) -> None:
        if not isinstance(self.budget_max, (int, float)) or self.budget_max <= 0:
            raise BriefError("budget_max must be a positive number of AED")
        if self.budget_min < 0 or self.budget_min > self.budget_max:
            raise BriefError("budget_min must be between 0 and budget_max")
        if self.market not in MARKETS:
            raise BriefError(f"market must be one of {MARKETS}")
        if self.purpose not in PURPOSES:
            raise BriefError(f"purpose must be one of {PURPOSES}")
        if self.financing not in FINANCING:
            raise BriefError(f"financing must be one of {FINANCING}")
        bad = [e for e in self.emirates if e not in EMIRATES]
        if bad:
            raise BriefError(f"unknown emirates {bad}; valid: {EMIRATES}")
        if (
            self.bedrooms_min is not None
            and self.bedrooms_max is not None
            and self.bedrooms_min > self.bedrooms_max
        ):
            raise BriefError("bedrooms_min must not exceed bedrooms_max")
        if self.loan_to_value is not None and not 0 < self.loan_to_value < 1:
            raise BriefError("loan_to_value must be a fraction between 0 and 1, e.g. 0.75")
        if self.discount_rate is not None and not 0 <= self.discount_rate < 1:
            raise BriefError("discount_rate must be a fraction, e.g. 0.07")
        if self.handover_by is not None:
            try:
                parse_period(self.handover_by)
            except ValueError as exc:
                raise BriefError(f"handover_by: {exc}") from exc
        bad = sorted(set(self.weights) - set(CRITERIA))
        if bad:
            raise BriefError(f"unknown weight names {bad}; valid: {CRITERIA}")
        if any(w < 0 for w in self.weights.values()):
            raise BriefError("weights must not be negative")
