"""Turn a brief into the exact pages and queries to open first.

The URL shapes are Property Finder's, the one UAE-wide portal a page reader can
filter by URL. They were confirmed live on 2026-11-19 and can change without
notice: a page whose title lacks the requested community, beds or price band has
silently ignored the filter.
"""

from typing import Any, Dict, List, Optional

from .brief import Brief
from .costs import GOLDEN_VISA_MIN_AED
from .text import norm

PF = "https://www.propertyfinder.ae/en"
EMIRATE_SLUG = {
    "dubai": "dubai",
    "abu_dhabi": "abu-dhabi",
    "sharjah": "sharjah",
    "ras_al_khaimah": "ras-al-khaimah",
    "ajman": "ajman",
    "umm_al_quwain": "umm-al-quwain",
    "fujairah": "fujairah",
}
NEW_PROJECT_TYPE_ID = {"apartment": 1, "penthouse": 20, "townhouse": 22, "villa": 35}
TYPE_SLUG = {
    "apartment": "apartments",
    "villa": "villas",
    "townhouse": "townhouses",
    "penthouse": "penthouses",
}
COMPLETION_PARAM = {"ready": "completed", "offplan": "off_plan"}
MAX_BED_VARIANTS = 4
NEWS_DOMAINS = [
    "khaleejtimes.com",
    "gulfnews.com",
    "thenationalnews.com",
    "arabianbusiness.com",
    "zawya.com",
]
FRESH = "the reader may serve a copy up to two weeks old: add cb= with any unused value to force a fresh read"
EMPTY = (
    "a page titled for the whole emirate under a slug you know is valid means nothing matched: "
    "raise pt once to see the nearest stock before suspecting the slug"
)


def _hyphen(value: str) -> str:
    slug = norm(value).replace(" ", "-")
    return slug if slug.isascii() else ""


def _bed_prefix(beds: Optional[int]) -> str:
    if beds is None:
        return ""
    return "studio-" if beds == 0 else f"{beds}-bedroom-"


def _bed_options(brief: Brief) -> List[Optional[int]]:
    if brief.bedrooms_min is None and brief.bedrooms_max is None:
        return [None]
    low = brief.bedrooms_min if brief.bedrooms_min is not None else 0
    high = brief.bedrooms_max if brief.bedrooms_max is not None else low + MAX_BED_VARIANTS - 1
    return list(range(low, high + 1))[:MAX_BED_VARIANTS]


def _floor(brief: Brief) -> float:
    return max(brief.budget_min, GOLDEN_VISA_MIN_AED) if brief.purpose == "golden_visa" else brief.budget_min


def _places(brief: Brief) -> List[str]:
    """Area slugs, or one empty slug for an emirate-wide search. Areas need a single emirate to belong to."""
    if len(brief.emirates) > 1:
        return [""]
    return [f"-{_hyphen(area)}" for area in brief.areas if _hyphen(area)] or [""]


def notes(brief: Brief) -> List[Dict[str, Any]]:
    """What the plan could not express, so the gap is seen rather than assumed away."""
    remarks: List[str] = []
    if not brief.emirates:
        remarks.append("the brief names no emirate: Dubai is assumed")
    if brief.areas and len(brief.emirates) > 1:
        remarks.append("areas are searched only when the brief names one emirate: write one brief per emirate")
    if any(not _hyphen(area) for area in brief.areas):
        remarks.append("an area written in a non-Latin script has no portal address: give its English name")
    unsearchable = [kind for kind in brief.property_types if kind not in TYPE_SLUG]
    if unsearchable:
        remarks.append(f"the portal has no address for {', '.join(unsearchable)}: all property types are searched instead")
    beds = _bed_options(brief)
    if beds != [None] and (brief.bedrooms_max is None or brief.bedrooms_max > beds[-1]):
        remarks.append(f"only {beds[0]} to {beds[-1]} bedrooms are searched: add larger homes by hand")
    return [{"step": "note", "check": remark} for remark in remarks]


def listing_search_urls(brief: Brief) -> List[Dict[str, Any]]:
    types = [TYPE_SLUG[kind] for kind in brief.property_types if kind in TYPE_SLUG]
    if not types or len(types) < len(brief.property_types):
        types = ["properties"]
    params = []
    if _floor(brief):
        params.append(f"pf={_floor(brief):.0f}")
    params.append(f"pt={brief.budget_max:.0f}")
    if brief.market in COMPLETION_PARAM:
        params.append(f"cs={COMPLETION_PARAM[brief.market]}")
    if brief.size_min_sqft:
        params.append(f"af={brief.size_min_sqft:.0f}")
    steps: List[Dict[str, Any]] = []
    for emirate in brief.emirates or ["dubai"]:
        for place in _places(brief):
            for type_slug in types:
                for beds in _bed_options(brief):
                    path = f"{EMIRATE_SLUG[emirate]}/{_bed_prefix(beds)}{type_slug}-for-sale{place}.html"
                    steps.append(
                        {
                            "step": "listings",
                            "channel": "propertyfinder",
                            "url": f"{PF}/buy/{path}?{'&'.join(params)}",
                            "check": "page title must name the community, bedroom count and type; order is "
                            "newest-first with 25 cards, so split pf/pt into narrower bands to see more or to "
                            f"hunt the cheapest; {EMPTY}; {FRESH}",
                        }
                    )
    return steps


def new_project_urls(brief: Brief) -> List[Dict[str, Any]]:
    if brief.market == "ready":
        return []
    params: List[str] = [f"bdr[]={beds}" for beds in _bed_options(brief) if beds is not None]
    if _floor(brief):
        params.append(f"pf={_floor(brief):.0f}")
    params.append(f"pt={brief.budget_max:.0f}")
    if len(brief.property_types) == 1 and brief.property_types[0] in NEW_PROJECT_TYPE_ID:
        params.append(f"t={NEW_PROJECT_TYPE_ID[brief.property_types[0]]}")
    params.append("cs=off_plan")
    steps: List[Dict[str, Any]] = []
    for emirate in brief.emirates or ["dubai"]:
        for place in _places(brief):
            steps.append(
                {
                    "step": "new_projects",
                    "channel": "propertyfinder",
                    "url": f"{PF}/new-projects/lp/{EMIRATE_SLUG[emirate]}{place.replace('-', '/', 1)}?{'&'.join(params)}",
                    "check": "the heading must name the place and give a count; drop cards marked Sold out "
                    "or Ready and those whose delivery date is past the brief's limit; a launch price is "
                    "historic, open the project page for the current one and ask the reader for 12,000 to "
                    f"15,000 characters, because unit prices follow the gallery; {FRESH}",
                }
            )
    return steps


def benchmark_urls(brief: Brief) -> List[Dict[str, Any]]:
    """Registered sale and rent rows. Property Finder publishes them for Dubai only."""
    if (brief.emirates or ["dubai"]) != ["dubai"]:
        return []
    steps: List[Dict[str, Any]] = []
    for area in brief.areas:
        slug = _hyphen(area)
        if not slug:
            continue
        steps.append(
            {
                "step": "sold_benchmark",
                "channel": "propertyfinder",
                "url": f"{PF}/transactions/sold/dubai/{slug}",
                "check": "use the rows, not the headline average: the page shows ten rows, so read the building "
                "page for each candidate (append -{building}, prefix {n}-bedroom-apartments-) and take the "
                "median of comparable rows with their date span",
            }
        )
        steps.append(
            {
                "step": "rent_benchmark",
                "channel": "propertyfinder",
                "url": f"{PF}/transactions/rented/dubai/{slug}",
                "check": "use new 12-month contracts only: renewals are capped and do not show today's market rent",
            }
        )
    return steps


def lead_queries(brief: Brief) -> List[Dict[str, Any]]:
    where = ", ".join(brief.areas) or ", ".join(EMIRATE_SLUG[e].replace("-", " ") for e in brief.emirates) or "Dubai"
    beds = _bed_options(brief)[0]
    unit = "property" if beds is None else "studio" if beds == 0 else f"{beds} bedroom"
    market = {"offplan": "off-plan", "ready": "ready", "any": ""}[brief.market]
    base = " ".join(f"{unit} {market} for sale {where} under AED {brief.budget_max:,.0f}".split())
    steps = [
        {
            "step": "leads",
            "channel": "web_search",
            "query": base,
            "domains": ["bayut.com", "dubizzle.com"],
            "check": "these portals block page readers: whatever a search result quotes is a lead, never a "
            "reading; report hits as unverified with their link and prefer dubizzle URLs dated within 30 days",
        }
    ]
    if brief.market != "ready":
        steps.append(
            {
                "step": "launch_news",
                "channel": "web_search",
                "query": f"new launch {where} payment plan starting price {unit}",
                "domains": NEWS_DOMAINS,
                "check": "read each article's date and currency; results mix years",
            }
        )
    return steps


def search_plan(brief: Brief) -> List[Dict[str, Any]]:
    return notes(brief) + listing_search_urls(brief) + new_project_urls(brief) + benchmark_urls(brief) + lead_queries(brief)
