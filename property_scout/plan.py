"""Turn a brief into the exact pages and queries to open first.

The URL shapes are Property Finder's, the one UAE-wide portal a page reader can
filter by URL. They were confirmed live on 2026-11-19 and can change without
notice: a page whose title lacks the requested community, beds or price band has
silently ignored the filter.
"""

from typing import Any, Dict, List, Optional

from .brief import Brief
from .costs import GOLDEN_VISA_MIN_AED
from .text import place

PF = "https://www.propertyfinder.ae/en"
REGISTER_COPY = "https://offplan.tv/dubai/area"
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
# Dubai districts whose registered sales and new leases put a studio's gross yield between 7.6% and 10.2%
# on 21 November 2026 (Property Finder's transaction pages), highest first. A yield brief that names no
# area starts here, not in the prime districts, where the same sum earns 6% to 7%.
YIELD_DISTRICTS = (
    "international-city",
    "dubai-silicon-oasis",
    "discovery-gardens",
    "dubai-sports-city",
    "dubai-production-city-impz",
    "motor-city",
    "jumeirah-village-circle",
)
FRESH = "the reader may serve a copy up to two weeks old: add cb= with any unused value to force a fresh read"
EMPTY = (
    "a page titled for the whole emirate under a slug you know is valid means nothing matched: "
    "raise pt once to see the nearest stock before suspecting the slug; 'not found' means the slug is wrong: "
    "use the community's full name as the portal prints it"
)


def _area_slugs(brief: Brief) -> List[str]:
    """The portal's address for each area, short forms expanded and repeats folded."""
    return list(dict.fromkeys(place(area).replace(" ", "-") for area in brief.areas if place(area)))


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
    return [f"-{slug}" for slug in _area_slugs(brief)] or [""]


def _dubai_only(brief: Brief) -> bool:
    return (brief.emirates or ["dubai"]) == ["dubai"]


def _yield_first(brief: Brief) -> bool:
    """Income is the aim, the area is open, and registered rents can be read: only Dubai's finished homes qualify."""
    return brief.purpose == "yield" and not brief.areas and brief.market != "offplan" and _dubai_only(brief)


def notes(brief: Brief) -> List[Dict[str, Any]]:
    """What the plan could not express, so the gap is seen rather than assumed away."""
    remarks: List[str] = []
    if not brief.emirates:
        remarks.append("the brief names no emirate: Dubai is assumed")
    if brief.areas and len(brief.emirates) > 1:
        remarks.append("areas are searched only when the brief names one emirate: write one brief per emirate")
    unsearchable = [kind for kind in brief.property_types if kind not in TYPE_SLUG]
    if unsearchable:
        remarks.append(f"the portal has no address for {', '.join(unsearchable)}: all property types are searched instead")
    beds = _bed_options(brief)
    if beds != [None] and (brief.bedrooms_max is None or brief.bedrooms_max > beds[-1]):
        remarks.append(f"only {beds[0]} to {beds[-1]} bedrooms are searched: add larger homes by hand")
    if brief.market != "ready":
        if brief.size_min_sqft:
            remarks.append("the new-projects pages cannot filter by size: read sizes on each project page")
        if brief.handover_by:
            remarks.append(f"no page filters by handover date: drop projects due after {brief.handover_by} as you read them")
    if brief.sale_type:
        remarks.append(f"no page filters by sale type: keep only '{brief.sale_type}' adverts (cards are tagged First Sale or Re-Sale)")
    if brief.must_have or brief.exclude:
        remarks.append("must-haves and exclusions are not in any address: read them from each advert and record them as tags")
    if _yield_first(brief):
        remarks.append(
            "a yield brief with no area is searched by yield, not by district: read the yield_scan pages first "
            "and take the listings from the segments that lead them"
        )
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
        for place_slug in _places(brief):
            for type_slug in types:
                for beds in _bed_options(brief):
                    path = f"{EMIRATE_SLUG[emirate]}/{_bed_prefix(beds)}{type_slug}-for-sale{place_slug}.html"
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
    base: List[str] = [f"bdr[]={beds}" for beds in _bed_options(brief) if beds is not None]
    if _floor(brief):
        base.append(f"pf={_floor(brief):.0f}")
    base.append(f"pt={brief.budget_max:.0f}")
    # One page per type the index can filter; a type it cannot filter means the unfiltered page.
    type_ids: List[Optional[int]] = [NEW_PROJECT_TYPE_ID.get(kind) for kind in brief.property_types] or [None]
    if None in type_ids:
        type_ids = [None]
    steps: List[Dict[str, Any]] = []
    for emirate in brief.emirates or ["dubai"]:
        for place_slug in _places(brief):
            for type_id in type_ids:
                params = base + ([f"t={type_id}"] if type_id else []) + ["cs=off_plan"]
                steps.append(
                    {
                        "step": "new_projects",
                        "channel": "propertyfinder",
                        "url": f"{PF}/new-projects/lp/{EMIRATE_SLUG[emirate]}{place_slug.replace('-', '/', 1)}?{'&'.join(params)}",
                        "check": "the heading must name the place and give a count; the price on a project card is "
                        "the project's lowest launch price whatever bedroom filter is set, and is historic; drop cards "
                        "marked Sold out or Ready and those whose delivery date is past the brief's limit; open the "
                        "project page for the current price and ask the reader for 12,000 to 15,000 characters, "
                        f"because unit prices follow the gallery; {FRESH}",
                    }
                )
    return steps


def register_urls(brief: Brief) -> List[Dict[str, Any]]:
    """A copy of Dubai's project register by area: registration is a gate for every off-plan offer."""
    if brief.market == "ready" or not _dubai_only(brief):
        return []
    return [
        {
            "step": "register",
            "channel": "offplan.tv",
            "url": f"{REGISTER_COPY}/{slug}",
            "check": "a third-party copy of the Land Department's register, not the register: note the date it says it "
            "was read; projects are filed under their register names; the table may be cut short, so ask for a long "
            "read; a project's own page is offplan.tv/dubai/{project-name}",
        }
        for slug in _area_slugs(brief)
    ]


def yield_scan_urls(brief: Brief) -> List[Dict[str, Any]]:
    """Where registered rents are highest against registered prices, for a yield brief that leaves the area open."""
    if not _yield_first(brief):
        return []
    beds = [b for b in _bed_options(brief) if b is not None][:2] or [0, 1]
    return [
        {
            "step": "yield_scan",
            "channel": "propertyfinder",
            "url": f"{PF}/transactions/sold/dubai/{_bed_prefix(count)}apartments-{slug}",
            "check": "rank before searching: the header prints the average price and, at district level, the average yield, "
            "and lists the clusters or buildings with their sales counts; the same address under /rented/ gives the "
            "average new rent; go one level down (add the cluster or building to the address) where sales are frequent, "
            "take the median new 12-month rent over the median sold price, and open adverts only in the two or three "
            "best segments, cheapest first",
        }
        for slug in YIELD_DISTRICTS
        for count in beds
    ]


def benchmark_urls(brief: Brief) -> List[Dict[str, Any]]:
    """Registered sale and rent rows. Property Finder publishes them for Dubai only."""
    if not _dubai_only(brief):
        return []
    apartments = bool(brief.property_types) and set(brief.property_types) <= {"apartment"}
    prefixes = [_bed_prefix(beds) + "apartments-" for beds in _bed_options(brief) if beds is not None] if apartments else []
    steps: List[Dict[str, Any]] = []
    for slug in _area_slugs(brief):
        for prefix in prefixes or [""]:
            steps.append(
                {
                    "step": "sold_benchmark",
                    "channel": "propertyfinder",
                    "url": f"{PF}/transactions/sold/dubai/{prefix}{slug}",
                    "check": "use the rows, not the headline average: the page shows ten rows and ?page=2 the next ten; "
                    "for a candidate read its building's page, whose address is the card's location line in order "
                    "(community, cluster or district, complex, building); a title naming the cluster or complex "
                    "instead of the building means a segment is missing; take the median of comparable rows with their date span",
                }
            )
            steps.append(
                {
                    "step": "rent_benchmark",
                    "channel": "propertyfinder",
                    "url": f"{PF}/transactions/rented/dubai/{prefix}{slug}",
                    "check": "use new 12-month contracts only: renewals are capped and do not show today's market rent; "
                    "stop once five new leases in the size band are in hand",
                }
            )
    return steps


def lead_queries(brief: Brief) -> List[Dict[str, Any]]:
    where = ", ".join(brief.areas) or ", ".join(EMIRATE_SLUG[e].replace("-", " ") for e in brief.emirates) or "Dubai"
    beds = _bed_options(brief)[0]
    kind = brief.property_types[0] if len(brief.property_types) == 1 else "property"
    unit = kind if beds is None else "studio" if beds == 0 else f"{beds} bedroom {kind}"
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
    return (
        notes(brief)
        + yield_scan_urls(brief)
        + listing_search_urls(brief)
        + new_project_urls(brief)
        + register_urls(brief)
        + benchmark_urls(brief)
        + lead_queries(brief)
    )
