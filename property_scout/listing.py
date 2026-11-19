"""A normalised listing: one offer as collected from a portal, broker or developer."""

from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional

from .brief import EMIRATES
from .text import completion_slug, parse_period, slug

COMPLETION = ("ready", "offplan")
SALE_TYPES = ("resale", "primary")
EVIDENCE = ("page", "card", "lead")
PLAN_STAGES = ("on_booking", "during_construction", "on_handover", "post_handover")


class ListingError(ValueError):
    pass


@dataclass
class Listing:
    url: str
    price_aed: float
    evidence: str
    source: str = ""
    title: str = ""
    emirate: Optional[str] = None
    community: Optional[str] = None
    sub_community: Optional[str] = None
    building: Optional[str] = None
    developer: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    size_sqft: Optional[float] = None
    completion: Optional[str] = None
    sale_type: Optional[str] = None
    handover: Optional[str] = None
    payment_plan: Dict[str, float] = field(default_factory=dict)
    post_handover_months: int = 0
    permit_number: Optional[str] = None
    verified: Optional[bool] = None
    listed_days_ago: Optional[int] = None
    observed_on: Optional[str] = None
    annual_rent_aed: Optional[float] = None
    rent_basis: str = ""
    service_charge_psf: Optional[float] = None
    benchmark_psf: Optional[float] = None
    benchmark_basis: str = ""
    ready_benchmark_psf: Optional[float] = None
    transfer_fee_waived: bool = False
    developer_tier: Optional[int] = None
    registration_verified: Optional[bool] = None
    tags: List[str] = field(default_factory=list)
    sources: Dict[str, str] = field(default_factory=dict)
    notes: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Listing":
        if not isinstance(data, dict):
            raise ListingError("each listing must be a JSON object")
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ListingError(f"unknown listing fields {unknown}; valid fields: {sorted(known)}")
        for required in ("url", "price_aed", "evidence"):
            if not data.get(required):
                raise ListingError(f"listing needs {required}: {data.get('url') or data.get('title') or data}")
        listing = cls(**data)
        listing._normalise()
        listing._validate()
        return listing

    def _normalise(self) -> None:
        for name in ("emirate", "property_type", "sale_type"):
            value = getattr(self, name)
            setattr(self, name, slug(value) if value else None)
        self.evidence = slug(str(self.evidence))
        self.completion = completion_slug(self.completion) if self.completion else None
        self.tags = [slug(t) for t in self.tags]

    def _validate(self) -> None:
        where = self.url
        if not str(self.url).lower().startswith(("http://", "https://")):
            raise ListingError(f"{where}: url must be an http(s) link to the page the offer was read from")
        if not isinstance(self.price_aed, (int, float)) or self.price_aed <= 0:
            raise ListingError(f"{where}: price_aed must be a positive number")
        if self.evidence not in EVIDENCE:
            raise ListingError(
                f"{where}: evidence must be 'page' (its own page was opened), 'card' (seen on a search page) "
                f"or 'lead' (from a search engine or a portal that could not be read)"
            )
        if self.emirate is not None and self.emirate not in EMIRATES:
            raise ListingError(f"{where}: unknown emirate {self.emirate!r}; valid: {EMIRATES}")
        if self.completion is not None and self.completion not in COMPLETION:
            raise ListingError(f"{where}: completion must be one of {COMPLETION}")
        if self.sale_type is not None and self.sale_type not in SALE_TYPES:
            raise ListingError(f"{where}: sale_type must be one of {SALE_TYPES}")
        for name in ("size_sqft", "annual_rent_aed", "service_charge_psf", "benchmark_psf", "ready_benchmark_psf"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ListingError(f"{where}: {name} must be positive when given")
        if self.developer_tier is not None and self.developer_tier not in (1, 2, 3):
            raise ListingError(f"{where}: developer_tier must be 1, 2 or 3")
        if self.handover is not None:
            try:
                parse_period(self.handover)
            except ValueError as exc:
                raise ListingError(f"{where}: handover: {exc}") from exc
        if self.payment_plan:
            bad = sorted(set(self.payment_plan) - set(PLAN_STAGES))
            if bad:
                raise ListingError(f"{where}: payment_plan stages {bad} not in {PLAN_STAGES}")
            total = sum(self.payment_plan.values())
            if abs(total - 100) > 0.5:
                raise ListingError(f"{where}: payment_plan percentages sum to {total}, not 100")
            if self.payment_plan.get("post_handover") and self.post_handover_months <= 0:
                raise ListingError(f"{where}: post_handover share needs post_handover_months")

    @property
    def price_psf(self) -> Optional[float]:
        if not self.size_sqft:
            return None
        return self.price_aed / self.size_sqft

    @property
    def label(self) -> str:
        parts = [p for p in (self.building, self.sub_community, self.community) if p]
        return ", ".join(parts) or self.title or self.url
