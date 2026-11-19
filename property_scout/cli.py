"""Command-line interface for the property scout engine.

Usage examples:
    python -m property_scout template brief
    python -m property_scout plan --brief brief.json
    python -m property_scout costs --price 2000000 --emirate dubai --completion ready --sale-type resale
    python -m property_scout comps --rows sold_rows.json --size 760 --months 3 --completion ready
    python -m property_scout score --brief brief.json --listings listings.json --format html --lang ru --out shortlist.html
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, List, Optional

from .brief import EMIRATES, FINANCING, Brief, BriefError
from .comps import MIN_COMPS, CompsError, summarise
from .costs import acquisition_costs
from .listing import COMPLETION, SALE_TYPES, Listing, ListingError
from .messages import LANGUAGES, UI, aed, render
from .plan import search_plan
from .report import to_data, to_html, to_markdown
from .scoring import assess

BRIEF_TEMPLATE = {
    "client": "",
    "budget_max": 2500000,
    "budget_min": 0,
    "budget_includes_costs": False,
    "market": "any",
    "purpose": "balanced",
    "emirates": ["dubai"],
    "areas": ["Dubai Marina"],
    "areas_strict": False,
    "property_types": ["apartment"],
    "bedrooms_min": 1,
    "bedrooms_max": 2,
    "size_min_sqft": None,
    "handover_by": None,
    "financing": "cash",
    "loan_to_value": None,
    "gcc_national": False,
    "must_have": [],
    "exclude": [],
    "weights": {},
    "discount_rate": None,
    "notes": "",
}

LISTING_TEMPLATE = {
    "url": "https://example.com/listing/123",
    "evidence": "page",
    "source": "propertyfinder",
    "title": "",
    "price_aed": 1850000,
    "emirate": "dubai",
    "community": "Dubai Marina",
    "sub_community": None,
    "building": "Marina Gate 1",
    "developer": None,
    "property_type": "apartment",
    "bedrooms": 1,
    "bathrooms": 2,
    "size_sqft": 760,
    "completion": "ready",
    "sale_type": "resale",
    "handover": None,
    "payment_plan": {},
    "post_handover_months": 0,
    "permit_number": None,
    "verified": None,
    "listed_days_ago": None,
    "observed_on": "2026-11-19",
    "annual_rent_aed": None,
    "rent_basis": "",
    "service_charge_psf": None,
    "benchmark_psf": None,
    "benchmark_basis": "",
    "benchmark_count": None,
    "ready_benchmark_psf": None,
    "transfer_fee_waived": False,
    "developer_tier": None,
    "registration_verified": None,
    "tags": [],
    "sources": {},
    "notes": "",
}


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _emit(text: str, out: Optional[str]) -> None:
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text)


def cmd_template(args) -> int:
    template = BRIEF_TEMPLATE if args.kind == "brief" else [LISTING_TEMPLATE]
    print(json.dumps(template, indent=2, ensure_ascii=False))
    return 0


def cmd_plan(args) -> int:
    brief = Brief.from_dict(_read_json(args.brief))
    print(json.dumps(search_plan(brief), indent=2, ensure_ascii=False))
    return 0


def cmd_costs(args) -> int:
    costs = acquisition_costs(
        args.price, args.emirate, args.completion, args.sale_type, args.financing, args.ltv, args.gcc_national
    )
    if args.json:
        payload = {
            "price_aed": costs.price,
            "items": [{"item": render(i.note, args.lang), "amount_aed": i.amount} for i in costs.items],
            "total_costs_aed": costs.total_costs,
            "total_outlay_aed": costs.total_outlay,
            "upfront_cash_aed": costs.upfront_cash,
            "official_schedule": costs.official,
            "rates_known": costs.rates_known,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    labels = UI[args.lang]
    for item in costs.items:
        print(f"{aed(item.amount, args.lang):>18}  {render(item.note, args.lang)}")
    print(f"{aed(costs.total_costs, args.lang):>18}  = {labels['costs_total']}")
    print(f"{aed(costs.total_outlay, args.lang):>18}  = {labels['outlay_total']}")
    if not costs.rates_known:
        print(labels["costs_incomplete"], file=sys.stderr)
    return 0


def cmd_comps(args) -> int:
    rows = _read_json(args.rows)
    if not isinstance(rows, list):
        raise CompsError("comparables file must be a JSON array of rows")
    today = date.fromisoformat(args.today) if args.today else date.today()
    summary = summarise(rows, today, args.size, args.months, args.completion)
    payload = {
        "used": summary.used,
        "dropped": summary.dropped,
        "median_psf": summary.median_psf,
        "low_psf": summary.low_psf,
        "high_psf": summary.high_psf,
        "median_price_aed": summary.median_price,
        "thin": summary.thin,
        "note": f"fewer than {MIN_COMPS} comparables: widen the search and say so" if summary.thin else "",
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_score(args) -> int:
    brief = Brief.from_dict(_read_json(args.brief))
    raw = _read_json(args.listings)
    if isinstance(raw, dict):
        raw = raw.get("listings")
    if not isinstance(raw, list):
        raise ListingError("listings file must be a JSON array, or an object with a 'listings' array")
    listings = [Listing.from_dict(item) for item in raw]
    today = date.fromisoformat(args.today) if args.today else date.today()
    result = assess(brief, listings, today)
    if args.format == "html":
        text = to_html(result, args.lang, args.top)
    elif args.format == "md":
        text = to_markdown(result, args.lang, args.top)
    else:
        text = json.dumps(to_data(result, args.lang, args.top), indent=2, ensure_ascii=False)
    _emit(text, args.out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="property-scout",
        description="Deterministic underwriting and ranking for UAE property listings",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("template", help="Print an example brief or listings file")
    p.add_argument("kind", choices=["brief", "listings"])
    p.set_defaults(handler=cmd_template)

    p = sub.add_parser("plan", help="Turn a brief into the search pages and queries to open")
    p.add_argument("--brief", required=True)
    p.set_defaults(handler=cmd_plan)

    p = sub.add_parser("costs", help="Itemise acquisition costs for one purchase")
    p.add_argument("--price", type=float, required=True)
    p.add_argument("--emirate", choices=EMIRATES, required=True)
    p.add_argument("--completion", choices=COMPLETION, default="ready")
    p.add_argument("--sale-type", dest="sale_type", choices=SALE_TYPES, default=None)
    p.add_argument("--financing", choices=FINANCING, default="cash")
    p.add_argument("--ltv", type=float, default=None, help="Loan-to-value as a fraction, e.g. 0.75")
    p.add_argument("--gcc-national", dest="gcc_national", action="store_true", help="Buyer is a UAE or GCC national")
    p.add_argument("--lang", choices=LANGUAGES, default="en")
    p.add_argument("--json", action="store_true")
    p.set_defaults(handler=cmd_costs)

    p = sub.add_parser("comps", help="Median price per sqft from raw sold or rent rows")
    p.add_argument("--rows", required=True, help="JSON array of {price_aed, size_sqft, date, completion}")
    p.add_argument("--size", type=float, default=None, help="Subject size in sqft; rows over 20%% away are dropped")
    p.add_argument("--months", type=int, default=3, help="Look-back window for dated rows")
    p.add_argument("--completion", choices=COMPLETION, default=None)
    p.add_argument("--today", default=None)
    p.set_defaults(handler=cmd_comps)

    p = sub.add_parser("score", help="Filter, de-duplicate, score and rank listings against a brief")
    p.add_argument("--brief", required=True)
    p.add_argument("--listings", required=True)
    p.add_argument("--format", choices=["json", "md", "html"], default="json")
    p.add_argument("--lang", choices=LANGUAGES, default="en")
    p.add_argument("--top", type=int, default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--today", default=None, help="Valuation date, YYYY-MM-DD (defaults to today)")
    p.set_defaults(handler=cmd_score)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (BriefError, ListingError, CompsError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
