"""A normalised listing: one offer as collected from a portal, broker or developer."""

from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional

from .brief import EMIRATES, MAX_BEDROOMS, property_type_slug
from .fields import Check, InputError
from .text import completion_slug, parse_period, slug

COMPLETION = ("ready", "offplan")
SALE_TYPES = ("resale", "primary")
EVIDENCE = ("page", "card", "lead")
PLAN_STAGES = ("on_booking", "during_construction", "on_handover", "post_handover")
ANALYST_CAPS = ("consider", "pass", "verify_first")
MAX_POST_HANDOVER_MONTHS = 240
REQUIRED = ("url", "price_aed", "evidence")


class ListingError(InputError):
    pass


@dataclass
class Listing:
    url: str
    price_aed: float
    evidence: str
    source: str = ""
    title: str = ""
    agent: str = ""
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
    from_price: bool = False
    transfer_fee_waived: bool = False
    permit_number: Optional[str] = None
    verified: Optional[bool] = None
    listed_days_ago: Optional[int] = None
    observed_on: Optional[str] = None
    annual_rent_aed: Optional[float] = None
    rent_basis: str = ""
    rent_count: Optional[int] = None
    service_charge_psf: Optional[float] = None
    benchmark_psf: Optional[float] = None
    benchmark_basis: str = ""
    benchmark_count: Optional[int] = None
    ready_benchmark_psf: Optional[float] = None
    building_sales_12m: Optional[int] = None
    developer_tier: Optional[int] = None
    registration_verified: Optional[bool] = None
    project_number: Optional[str] = None
    escrow_bank: Optional[str] = None
    register_completion: Optional[str] = None
    register_progress_pct: Optional[float] = None
    register_inspected_on: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    sources: Dict[str, str] = field(default_factory=dict)
    notes: str = ""
    analyst_cap: Optional[str] = None
    analyst_note: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Listing":
        if not isinstance(data, dict):
            raise ListingError("each listing must be a JSON object")
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ListingError(f"unknown listing fields {unknown}; valid fields: {sorted(known)}")
        label = data.get("url") or data.get("title") or "listing"
        for required in REQUIRED:
            if data.get(required) in (None, ""):
                raise ListingError(f"{label}: listing needs {required}")
        check = Check(ListingError, str(label))
        get = data.get

        def optional_text(name: str) -> Optional[str]:
            return check.text(name, get(name)) or None

        listing = cls(
            url=check.text("url", get("url")),
            price_aed=check.number("price_aed", get("price_aed")),
            evidence=slug(check.text("evidence", get("evidence"))),
            source=check.text("source", get("source")),
            title=check.text("title", get("title")),
            agent=check.text("agent", get("agent")),
            emirate=slug(check.text("emirate", get("emirate"))) or None,
            community=optional_text("community"),
            sub_community=optional_text("sub_community"),
            building=optional_text("building"),
            developer=optional_text("developer"),
            property_type=property_type_slug(check.text("property_type", get("property_type"))) or None,
            bedrooms=check.integer("bedrooms", get("bedrooms"), 0, MAX_BEDROOMS),
            bathrooms=check.integer("bathrooms", get("bathrooms"), 0, MAX_BEDROOMS),
            size_sqft=check.number("size_sqft", get("size_sqft")),
            completion=completion_slug(check.text("completion", get("completion"))) or None,
            sale_type=slug(check.text("sale_type", get("sale_type"))) or None,
            handover=optional_text("handover"),
            payment_plan={
                stage: check.number(f"payment_plan.{stage}", share, high=100, open_low=False)
                for stage, share in check.mapping("payment_plan", get("payment_plan")).items()
                if share is not None
            },
            post_handover_months=check.integer("post_handover_months", get("post_handover_months"), 0, MAX_POST_HANDOVER_MONTHS) or 0,
            from_price=bool(check.boolean("from_price", get("from_price"))),
            transfer_fee_waived=bool(check.boolean("transfer_fee_waived", get("transfer_fee_waived"))),
            permit_number=optional_text("permit_number"),
            verified=check.boolean("verified", get("verified")),
            listed_days_ago=check.integer("listed_days_ago", get("listed_days_ago"), 0, 100_000),
            observed_on=check.day("observed_on", get("observed_on")),
            annual_rent_aed=check.number("annual_rent_aed", get("annual_rent_aed")),
            rent_basis=check.text("rent_basis", get("rent_basis")),
            rent_count=check.integer("rent_count", get("rent_count"), 0, 1_000_000),
            service_charge_psf=check.number("service_charge_psf", get("service_charge_psf")),
            benchmark_psf=check.number("benchmark_psf", get("benchmark_psf")),
            benchmark_basis=check.text("benchmark_basis", get("benchmark_basis")),
            benchmark_count=check.integer("benchmark_count", get("benchmark_count"), 0, 1_000_000),
            ready_benchmark_psf=check.number("ready_benchmark_psf", get("ready_benchmark_psf")),
            building_sales_12m=check.integer("building_sales_12m", get("building_sales_12m"), 0, 1_000_000),
            developer_tier=check.integer("developer_tier", get("developer_tier"), 1, 3),
            registration_verified=check.boolean("registration_verified", get("registration_verified")),
            project_number=optional_text("project_number"),
            escrow_bank=optional_text("escrow_bank"),
            register_completion=optional_text("register_completion"),
            register_progress_pct=check.number("register_progress_pct", get("register_progress_pct"), high=100, open_low=False),
            register_inspected_on=check.day("register_inspected_on", get("register_inspected_on")),
            tags=[slug(tag) for tag in check.strings("tags", get("tags")) if slug(tag)],
            sources={name: check.text(f"sources.{name}", link) for name, link in check.mapping("sources", get("sources")).items()},
            notes=check.text("notes", get("notes")),
            analyst_cap=slug(check.text("analyst_cap", get("analyst_cap"))) or None,
            analyst_note=check.text("analyst_note", get("analyst_note")),
        )
        listing._validate(check)
        return listing

    def _validate(self, check: Check) -> None:
        if not self.url.lower().startswith(("http://", "https://")):
            raise check.fail("url", "must be an http(s) link to the page the offer was read from", self.url)
        if self.evidence not in EVIDENCE:
            raise check.fail(
                "evidence",
                "must be 'page' (its own page was opened), 'card' (seen on a search page) or 'lead' (search engine or unreadable portal)",
                self.evidence,
            )
        if self.emirate is not None:
            check.choice("emirate", self.emirate, EMIRATES)
        if self.completion is not None:
            check.choice("completion", self.completion, COMPLETION)
        if self.sale_type is not None:
            check.choice("sale_type", self.sale_type, SALE_TYPES)
        if self.analyst_cap is not None:
            check.choice("analyst_cap", self.analyst_cap, ANALYST_CAPS)
            if not self.analyst_note:
                raise check.fail("analyst_note", "must give the reason whenever analyst_cap is set", self.analyst_note)
        for name in ("handover", "register_completion"):
            value = getattr(self, name)
            if value is not None:
                try:
                    parse_period(value)
                except ValueError as exc:
                    raise ListingError(f"{check.where}: {name}: {exc}") from exc
        if self.payment_plan:
            for stage in self.payment_plan:
                check.choice("payment_plan stage", stage, PLAN_STAGES)
            total = sum(self.payment_plan.values())
            if abs(total - 100) > 0.5:
                raise check.fail("payment_plan", "percentages must sum to 100", total)
            if self.payment_plan.get("post_handover") and not self.post_handover_months:
                raise check.fail("post_handover_months", "is needed when the plan has a post_handover share", self.post_handover_months)

    @property
    def price_psf(self) -> Optional[float]:
        if not self.size_sqft:
            return None
        return self.price_aed / self.size_sqft

    @property
    def offplan(self) -> bool:
        return self.completion == "offplan"

    @property
    def scheduled_handover(self) -> Optional[str]:
        """The land register's date when it was read, otherwise the advert's."""
        return self.register_completion or self.handover

    @property
    def label(self) -> str:
        parts = [p for p in (self.building, self.sub_community, self.community) if p]
        return ", ".join(parts) or self.title or self.url
