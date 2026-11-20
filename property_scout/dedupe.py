"""Fold adverts of the same unit into one offer without losing what each of them showed."""

from dataclasses import replace
from typing import List, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit

from .brief import HOUSE_TYPES
from .listing import EVIDENCE, Listing
from .text import norm

SIZE_TOLERANCE = 0.02
PRICE_TOLERANCE = 0.05
TRACKING_PARAMETERS = ("cb", "ref", "source", "gclid", "fbclid")
CONFLICTING_TAGS = (("tenanted", "vacant"), ("furnished", "unfurnished"))
# Facts about the unit, which any advert of it may supply; the rest belong to one advert.
SHARED_FACTS = (
    "emirate", "community", "sub_community", "developer", "property_type", "bathrooms", "handover",
    "annual_rent_aed", "rent_basis", "rent_count", "service_charge_psf", "benchmark_psf", "benchmark_basis",
    "benchmark_count", "ready_benchmark_psf", "building_sales_12m", "developer_tier", "registration_verified",
    "project_number", "escrow_bank", "register_completion", "register_progress_pct", "register_inspected_on",
)


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in TRACKING_PARAMETERS and not key.startswith("utm_")
    )
    route = f"#{parts.fragment}" if parts.fragment.startswith(("/", "!")) else ""
    return f"{host}{parts.path.rstrip('/')}{'?' + urlencode(query) if query else ''}{route}"


def _close(a: float, b: float, tolerance: float) -> bool:
    return abs(a - b) <= tolerance * max(a, b)


def _contradict(a: Listing, b: Listing) -> bool:
    if a.bedrooms is not None and b.bedrooms is not None and a.bedrooms != b.bedrooms:
        return True
    if a.bathrooms is not None and b.bathrooms is not None and a.bathrooms != b.bathrooms:
        return True
    if a.size_sqft and b.size_sqft and not _close(a.size_sqft, b.size_sqft, SIZE_TOLERANCE):
        return True
    if not _close(a.price_aed, b.price_aed, PRICE_TOLERANCE):
        return True
    return any(
        (one in a.tags and other in b.tags) or (other in a.tags and one in b.tags) for one, other in CONFLICTING_TAGS
    )


def _same_unit(a: Listing, b: Listing) -> bool:
    if _contradict(a, b) or a.completion != b.completion:
        return False
    # A card's link is the search page it was seen on, which many different units share.
    if a.evidence == b.evidence == "page" and canonical_url(a.url) == canonical_url(b.url):
        return True
    if a.permit_number and a.permit_number == b.permit_number:
        return True
    # Houses of one type in one community share size and price band, so they need the tests above.
    if a.property_type in HOUSE_TYPES or b.property_type in HOUSE_TYPES:
        return False
    if not (a.size_sqft and b.size_sqft and norm(a.building)) or a.bedrooms is None or b.bedrooms is None:
        return False
    return norm(a.building) == norm(b.building) and norm(a.community) == norm(b.community)


def _strength(listing: Listing) -> Tuple[int, float, int, str]:
    return (EVIDENCE.index(listing.evidence), listing.price_aed, 0 if listing.verified else 1, listing.url)


def _merged(anchor: Listing, others: List[Listing]) -> Listing:
    filled = {}
    for name in SHARED_FACTS:
        if getattr(anchor, name) in (None, ""):
            donor = next((getattr(o, name) for o in others if getattr(o, name) not in (None, "")), None)
            if donor is not None:
                filled[name] = donor
    tags = list(dict.fromkeys(anchor.tags + [tag for other in others for tag in other.tags]))
    return replace(anchor, tags=tags, **filled)


def dedupe(listings: List[Listing]) -> List[Tuple[Listing, List[Listing]]]:
    """One offer per unit, each with the adverts folded into it.

    The best-evidenced advert represents the unit, the cheapest among equals; every
    other advert is compared with that one alone, so a chain of near-matches cannot
    grow into a group wider than the tolerances.
    """
    groups: List[List[Listing]] = []
    for listing in sorted(listings, key=_strength):
        for group in groups:
            if _same_unit(group[0], listing):
                group.append(listing)
                break
        else:
            groups.append([listing])
    return [(_merged(group[0], group[1:]), group[1:]) for group in groups]
