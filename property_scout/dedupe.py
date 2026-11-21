"""Fold adverts of the same unit into one offer without losing what each of them showed."""

from dataclasses import replace
from typing import List, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit

from .brief import HOUSE_TYPES
from .listing import ANALYST_CAPS, EVIDENCE, Listing
from .text import norm, place

SIZE_TOLERANCE = 0.02
PRICE_TOLERANCE = 0.05
TRACKING_PARAMETERS = ("cb", "gclid", "fbclid")
# Stated differently by two adverts, these make them two offers: a first sale and a resale are not one deal.
CONTRADICTING_FACTS = ("bedrooms", "bathrooms", "completion", "emirate", "sale_type")
# The developer's schedule: taken whole from one advert, never pieced together from two.
PLAN_FACTS = ("payment_plan", "instalments", "post_handover_months")
# Tags of which one unit can carry only one.
CONFLICTING_TAGS = (("tenanted", "vacant"), ("furnished", "unfurnished"), ("high_floor", "mid_floor", "low_floor"))
# What an advert says about the unit: taken from another advert only when that one was read at least as closely.
ADVERT_FACTS = (
    "emirate", "community", "sub_community", "building", "developer", "property_type", "bedrooms", "bathrooms",
    "size_sqft", "completion", "sale_type", "handover",
)
# What the analyst looked up about the building or the project, whichever advert's record carries it.
RESEARCHED_FACTS = (
    "annual_rent_aed", "rent_basis", "rent_count", "service_charge_psf", "benchmark_psf", "benchmark_basis",
    "benchmark_count", "ready_benchmark_psf", "ready_benchmark_basis", "building_sales_12m", "developer_tier",
    "registration_verified", "project_number", "escrow_bank", "register_started", "register_completion",
    "register_progress_pct", "register_inspected_on",
)
# Facts about the unit, which another advert of it may supply; the rest belong to one advert.
SHARED_FACTS = ADVERT_FACTS + RESEARCHED_FACTS


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


def _differ(a, b) -> bool:
    return a is not None and b is not None and a != b


def _contradict(a: Listing, b: Listing) -> bool:
    if any(_differ(getattr(a, name), getattr(b, name)) for name in CONTRADICTING_FACTS):
        return True
    if a.size_sqft and b.size_sqft and not _close(a.size_sqft, b.size_sqft, SIZE_TOLERANCE):
        return True
    if not _close(a.price_aed, b.price_aed, PRICE_TOLERANCE):
        return True
    return any(
        one != other and one in a.tags and other in b.tags
        for group in CONFLICTING_TAGS
        for one in group
        for other in group
    )


def _same_unit(a: Listing, b: Listing) -> bool:
    if _contradict(a, b):
        return False
    # A card's link is the search page it was seen on, which many different units share.
    if "card" not in (a.evidence, b.evidence) and canonical_url(a.url) == canonical_url(b.url):
        return True
    if a.permit_number and a.permit_number == b.permit_number:
        return True
    # Houses of one type in one community share size and price band, so they need the tests above.
    if a.property_type in HOUSE_TYPES or b.property_type in HOUSE_TYPES:
        return False
    if not (a.size_sqft and b.size_sqft and norm(a.building) and place(a.community)):
        return False
    if a.bedrooms is None or b.bedrooms is None:
        return False
    return norm(a.building) == norm(b.building) and place(a.community) == place(b.community)


def _strength(listing: Listing) -> Tuple:
    """Best evidence first, the cheapest among equals; the rest only makes the order the same for any input order."""
    return (EVIDENCE.index(listing.evidence), listing.price_aed, 0 if listing.verified else 1, listing.url, repr(listing))


def _as_strong(donor: Listing, anchor: Listing) -> bool:
    return EVIDENCE.index(donor.evidence) <= EVIDENCE.index(anchor.evidence)


def proven_tags(group: List[Listing], index: int = 0) -> List[str]:
    """Tags that may count in the unit's favour: the advert's own and those of adverts read at least as closely."""
    anchor = group[index]
    return list(dict.fromkeys(tag for member in group if _as_strong(member, anchor) for tag in member.tags))


def represent(group: List[Listing], index: int = 0) -> Listing:
    """One advert of the group, carrying what the others showed about the unit and the strictest analyst cap.

    What an advert says about the unit is taken only from an advert read at least as closely: a search
    result cannot supply what an opened page left out. Tags, notes and caps of every advert are kept,
    because a warning counts whoever gave it.
    """
    anchor = group[index]
    others = group[:index] + group[index + 1:]
    filled = {}
    for name in SHARED_FACTS:
        if getattr(anchor, name) in (None, ""):
            donors = (getattr(o, name) for o in others if name in RESEARCHED_FACTS or _as_strong(o, anchor))
            donor = next((value for value in donors if value not in (None, "")), None)
            if donor is not None:
                filled[name] = donor
    if not anchor.payment_plan:
        planned = next((o for o in others if o.payment_plan and _as_strong(o, anchor)), None)
        if planned is not None:
            filled.update({name: getattr(planned, name) for name in PLAN_FACTS})
    capped = max((member for member in group if member.analyst_cap), key=lambda m: ANALYST_CAPS.index(m.analyst_cap), default=None)
    if capped is not None:
        filled.update(analyst_cap=capped.analyst_cap, analyst_note=capped.analyst_note)
    return replace(
        anchor,
        tags=list(dict.fromkeys(tag for member in [anchor] + others for tag in member.tags)),
        notes=" | ".join(dict.fromkeys(member.notes for member in [anchor] + others if member.notes)),
        sources={name: link for member in reversed([anchor] + others) for name, link in member.sources.items()},
        **filled,
    )


def fold(listings: List[Listing]) -> List[List[Listing]]:
    """Adverts grouped by unit, the best-evidenced first and the cheapest among equals.

    An advert joins a group when it matches the group's first advert, so a chain of near-matches
    cannot grow wider than the tolerances. An advert that matches two adverts which contradict each
    other could be either unit: it is kept apart from both and nothing joins it, which also keeps
    every group free of contradictions. The result does not depend on the order of the input.
    """
    ordered = sorted(listings, key=_strength)
    groups: List[List[Listing]] = []
    open_groups: List[List[Listing]] = []
    for listing in ordered:
        partners = [other for other in ordered if other is not listing and _same_unit(listing, other)]
        torn = any(_contradict(one, other) for i, one in enumerate(partners) for other in partners[i + 1:])
        home = None if torn else next((g for g in open_groups if any(g[0] is p for p in partners)), None)
        if home is not None:
            home.append(listing)
            continue
        groups.append([listing])
        if not torn:
            open_groups.append(groups[-1])
    return groups


def dedupe(listings: List[Listing]) -> List[Tuple[Listing, List[Listing]]]:
    """One offer per unit, each with the adverts folded into it."""
    return [(represent(group), group[1:]) for group in fold(listings)]
