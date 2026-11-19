"""Collapse the same unit advertised several times into one listing."""

from typing import Dict, List, Tuple
from urllib.parse import urlsplit

from .listing import Listing
from .text import norm

SIZE_TOLERANCE = 0.02
PRICE_TOLERANCE = 0.05


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return f"{host}{parts.path.rstrip('/')}"


def _same_unit(a: Listing, b: Listing) -> bool:
    if canonical_url(a.url) == canonical_url(b.url):
        return True
    if not (a.building and b.building and a.size_sqft and b.size_sqft):
        return False
    if a.bedrooms is None or a.bedrooms != b.bedrooms:
        return False
    if norm(a.building) != norm(b.building) or norm(a.community) != norm(b.community):
        return False
    if a.completion != b.completion:
        return False
    size_close = abs(a.size_sqft - b.size_sqft) <= SIZE_TOLERANCE * max(a.size_sqft, b.size_sqft)
    price_close = abs(a.price_aed - b.price_aed) <= PRICE_TOLERANCE * max(a.price_aed, b.price_aed)
    return size_close and price_close


def _preference(listing: Listing) -> Tuple[float, int, int]:
    filled = sum(1 for value in vars(listing).values() if value not in (None, "", [], {}))
    return (listing.price_aed, 0 if listing.verified else 1, -filled)


def dedupe(listings: List[Listing]) -> Tuple[List[Listing], Dict[str, List[str]]]:
    """Return one listing per unit plus, per kept URL, the URLs folded into it.

    The cheapest advert of a unit wins; a verified one breaks a price tie.
    """
    parent = list(range(len(listings)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(listings)):
        for j in range(i + 1, len(listings)):
            if _same_unit(listings[i], listings[j]):
                parent[find(j)] = find(i)

    groups: Dict[int, List[Listing]] = {}
    for index, listing in enumerate(listings):
        groups.setdefault(find(index), []).append(listing)

    kept: List[Listing] = []
    folded: Dict[str, List[str]] = {}
    for group in groups.values():
        winner = min(group, key=_preference)
        kept.append(winner)
        others = [member.url for member in group if member is not winner]
        if others:
            folded[winner.url] = others
    return kept, folded
