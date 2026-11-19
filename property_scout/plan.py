"""Turn a brief into the exact pages and queries to open first.

The URL shapes are Property Finder's, the one UAE-wide portal a page reader can
filter by URL. They were confirmed live on 2026-11-19 and can change without
notice: a page whose title lacks the requested community, beds or price band has
silently ignored the filter.
"""

from typing import Any, Dict, List, Optional

from .brief import Brief
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
NEW_PROJECT_LOCATION_ID = {
    "dubai": 1,
    "umm_al_quwain": 2,
    "ras_al_khaimah": 3,
    "sharjah": 4,
    "ajman": 5,
    "abu_dhabi": 6,
    "fujairah": 7,
}
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


def _hyphen(value: str) -> str:
    return norm(value).replace(" ", "-")


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


def _query(brief: Brief, completion: Optional[str]) -> str:
    params: List[str] = []
    if brief.budget_min:
        params.append(f"pf={brief.budget_min:.0f}")
    params.append(f"pt={brief.budget_max:.0f}")
    if completion:
        params.append(f"cs={completion}")
    if brief.size_min_sqft:
        params.append(f"af={brief.size_min_sqft:.0f}")
    return "&".join(params)


def listing_search_urls(brief: Brief) -> List[Dict[str, Any]]:
    emirates = brief.emirates or ["dubai"]
    types = [TYPE_SLUG.get(t) for t in brief.property_types if TYPE_SLUG.get(t)] or ["properties"]
    completion = COMPLETION_PARAM.get(brief.market)
    steps: List[Dict[str, Any]] = []
    for emirate in emirates:
        places = [f"-{_hyphen(area)}" for area in brief.areas] or [""]
        for place in places:
            for type_slug in types:
                for beds in _bed_options(brief):
                    path = f"{EMIRATE_SLUG[emirate]}/{_bed_prefix(beds)}{type_slug}-for-sale{place}.html"
                    steps.append(
                        {
                            "step": "listings",
                            "channel": "propertyfinder",
                            "url": f"{PF}/buy/{path}?{_query(brief, completion)}",
                            "check": "page title must name the community, bedroom count and type; "
                            "order is newest-first, add &page=2 for more or narrow pf/pt to hunt the cheapest",
                        }
                    )
    return steps


def new_project_urls(brief: Brief) -> List[Dict[str, Any]]:
    if brief.market == "ready":
        return []
    steps: List[Dict[str, Any]] = []
    for emirate in brief.emirates or ["dubai"]:
        params = [f"l={NEW_PROJECT_LOCATION_ID[emirate]}"]
        if brief.budget_min:
            params.append(f"pf={brief.budget_min:.0f}")
        params.append(f"pt={brief.budget_max:.0f}")
        params += [f"bdr[]={beds}" for beds in _bed_options(brief) if beds is not None]
        steps.append(
            {
                "step": "new_projects",
                "channel": "propertyfinder",
                "url": f"{PF}/new-projects?{'&'.join(params)}",
                "check": "heading count must be lower than the unfiltered UAE total; "
                "drop cards marked Sold out or Ready and those outside the handover window",
            }
        )
    return steps


def benchmark_urls(brief: Brief) -> List[Dict[str, Any]]:
    """Registered sale and rent rows. Property Finder publishes them for Dubai only."""
    if "dubai" not in (brief.emirates or ["dubai"]):
        return []
    steps: List[Dict[str, Any]] = []
    for area in brief.areas:
        slug = _hyphen(area)
        steps.append(
            {
                "step": "sold_benchmark",
                "channel": "propertyfinder",
                "url": f"{PF}/transactions/sold/dubai/{slug}",
                "check": "use the rows, not the headline average: take the median per sqft of comparable "
                "rows from the last six months; append -{building} or prefix {n}-bedroom-apartments- to narrow",
            }
        )
        steps.append(
            {
                "step": "rent_benchmark",
                "channel": "propertyfinder",
                "url": f"{PF}/transactions/rented/dubai/{slug}",
                "check": "use new 12-month contracts only; renewals are capped and understate market rent",
            }
        )
    return steps


def lead_queries(brief: Brief) -> List[Dict[str, Any]]:
    where = ", ".join(brief.areas) or ", ".join(EMIRATE_SLUG[e].replace("-", " ") for e in brief.emirates) or "Dubai"
    beds = _bed_options(brief)[0]
    unit = "property" if beds is None else "studio" if beds == 0 else f"{beds} bedroom"
    market = {"offplan": "off-plan", "ready": "ready", "any": ""}[brief.market]
    base = f"{unit} {market} for sale {where} under AED {brief.budget_max:,.0f}".replace("  ", " ")
    steps = [
        {
            "step": "leads",
            "channel": "web_search",
            "query": base,
            "domains": ["bayut.com", "dubizzle.com"],
            "check": "these portals block page readers: report hits as unverified leads with their link, "
            "prefer dubizzle URLs dated within 30 days",
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
    return listing_search_urls(brief) + new_project_urls(brief) + benchmark_urls(brief) + lead_queries(brief)
