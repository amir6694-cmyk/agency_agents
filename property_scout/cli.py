"""Command-line interface for the property scout engine.

Usage examples:
    python -m property_scout template brief
    python -m property_scout plan --brief brief.json
    python -m property_scout costs --price 2000000 --emirate dubai --sale-type resale --financing mortgage --ltv 0.75
    python -m property_scout comps --rows sold_rows.json --size 760 --months 12 --completion ready
    python -m property_scout score --brief brief.json --listings listings.json --format html --lang ru --out shortlist.html
"""

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, List, Optional

from .brief import EMIRATES, FINANCING, NATIONALITIES, SALE_TYPES, Brief
from .comps import CONCENTRATION_LIMIT, MIN_COMPS, CompsError, summarise
from .costs import Buyer, Purchase, acquisition_costs
from .fields import MAX_NUMBER, InputError
from .listing import COMPLETION, Listing, ListingError
from .messages import LANGUAGES, UI, aed, render
from .plan import search_plan
from .report import to_data, to_html, to_markdown
from .scoring import assess, cost_flags

BRIEF_TEMPLATE = asdict(
    Brief(
        budget_max=2_500_000,
        emirates=["dubai"],
        areas=["Dubai Marina", "Dubai Creek Harbour"],
        property_types=["apartment"],
        bedrooms_min=1,
        bedrooms_max=2,
    )
)

READY_EXAMPLE = asdict(
    Listing(
        url="https://example.com/listing/123",
        price_aed=1_850_000,
        evidence="page",
        source="propertyfinder",
        title="Vacant | High floor | Marina view",
        agent="Example Realty",
        emirate="dubai",
        community="Dubai Marina",
        building="Example Tower 1",
        property_type="apartment",
        bedrooms=1,
        bathrooms=2,
        size_sqft=760,
        completion="ready",
        sale_type="resale",
        permit_number="7100000000",
        verified=True,
        listed_days_ago=4,
        observed_on="2026-11-20",
        annual_rent_aed=120_000,
        rent_basis="median of 7 new 12-month leases in the building, Aug-Nov 2026",
        rent_count=7,
        service_charge_psf=16.5,
        benchmark_psf=2_300,
        benchmark_basis="median of 9 registered 1-bed sales in the building, Dec 2025-Nov 2026",
        benchmark_count=9,
        building_sales_12m=9,
        tags=["vacant", "high_floor"],
        sources={"sold": "https://example.com/transactions/sold/example-tower-1"},
    )
)

OFFPLAN_EXAMPLE = asdict(
    Listing(
        url="https://example.com/projects/example-residences/1-bedroom",
        price_aed=1_450_000,
        evidence="page",
        source="developer",
        title="1 bedroom, type B",
        emirate="dubai",
        community="Dubai Creek Harbour",
        building="Example Residences",
        developer="Example Developer",
        property_type="apartment",
        bedrooms=1,
        bathrooms=1,
        size_sqft=720,
        completion="offplan",
        sale_type="primary",
        handover="2028-Q4",
        payment_plan={"on_booking": 20, "during_construction": 40, "on_handover": 40},
        instalments=[{"pct": 10, "after_months": 2}, {"pct": 10, "due": "2027-06"}],
        from_price=True,
        price_corroborated=True,
        observed_on="2026-11-20",
        annual_rent_aed=88_000,
        rent_basis="median of 8 new 12-month leases of 1-beds in a delivered building next door, Aug-Nov 2026; its service charge",
        rent_count=8,
        service_charge_psf=18,
        benchmark_psf=2_150,
        benchmark_basis="median of 12 registered off-plan 1-bed sales in the community, Sep-Nov 2026",
        benchmark_count=12,
        ready_benchmark_psf=1_900,
        ready_benchmark_basis="median of 14 registered ready 1-bed sales in the community, Sep-Nov 2026",
        developer_tier=1,
        registration_verified=True,
        project_number="1234",
        escrow_bank="Example Bank",
        register_started="2026-03",
        register_completion="2029-Q1",
        register_progress_pct=12,
        register_inspected_on="2026-10-05",
        sources={"register": "https://example.com/register/1234"},
    )
)


MAX_MONTHS = 600


def _read_json(path: str) -> Any:
    def unique(pairs):
        keys = [key for key, _ in pairs]
        repeated = sorted({key for key in keys if keys.count(key) > 1})
        if repeated:
            raise InputError(f"{path}: a field appears twice in one object: {', '.join(repeated)}")
        return dict(pairs)

    with open(path, "r", encoding="utf-8") as handle:
        try:
            return json.load(handle, object_pairs_hook=unique)
        except json.JSONDecodeError as exc:
            raise InputError(f"{path} is not valid JSON: {exc}") from exc


def _emit(text: str, out: Optional[str]) -> None:
    if not out:
        print(text)
        return
    # Written beside the target and moved into place, so a failure cannot leave an earlier report truncated.
    partial = Path(f"{out}.tmp")
    partial.write_text(text, encoding="utf-8")
    os.replace(partial, out)
    print(f"wrote {out}")


def _day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a date written YYYY-MM-DD, got {value!r}") from None


def _positive(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        number = 0.0
    if not 1 <= number <= MAX_NUMBER:
        raise argparse.ArgumentTypeError(f"must be a number from 1 to {MAX_NUMBER:g}, got {value!r}")
    return number


def _count(value: str) -> int:
    if not (value.isascii() and value.isdigit()) or not 1 <= int(value) <= MAX_MONTHS:
        raise argparse.ArgumentTypeError(f"must be a whole number from 1 to {MAX_MONTHS}, got {value!r}")
    return int(value)


def _fraction(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        number = 0.0
    if not 0 < number < 1:
        raise argparse.ArgumentTypeError(f"must be a fraction between 0 and 1 such as 0.75, got {value!r}")
    return number


def cmd_template(args) -> int:
    template = BRIEF_TEMPLATE if args.kind == "brief" else [READY_EXAMPLE, OFFPLAN_EXAMPLE]
    print(json.dumps(template, indent=2, ensure_ascii=False))
    return 0


def cmd_plan(args) -> int:
    brief = Brief.from_dict(_read_json(args.brief))
    print(json.dumps(search_plan(brief), indent=2, ensure_ascii=False))
    return 0


def cmd_costs(args) -> int:
    if args.ltv is not None and args.financing != "mortgage":
        raise InputError("--ltv needs --financing mortgage")
    purchase = Purchase(args.price, args.emirate, args.community, args.completion, args.sale_type, args.waived)
    costs = acquisition_costs(purchase, Buyer(args.nationality, args.financing, args.ltv, args.first_home))
    remarks = [render(flag.note, args.lang) for flag in cost_flags(costs, args.emirate)]
    if args.json:
        payload = {
            "price_aed": costs.price,
            "items": [{"item": render(i.note, args.lang), "amount_aed": round(i.amount)} for i in costs.items],
            "total_costs_aed": round(costs.total_costs),
            "total_outlay_aed": round(costs.total_outlay),
            "loan_aed": round(costs.loan),
            "loan_to_value_used": costs.ltv_used,
            "loan_to_value_cap": costs.ltv_cap,
            "own_funds_aed": round(costs.own_funds),
            "rates_known": costs.rates_known,
            "schedule_complete": costs.complete,
            "notes": remarks,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    labels = UI[args.lang]
    for item in costs.items:
        print(f"{aed(item.amount, args.lang):>18}  {render(item.note, args.lang)}")
    print(f"{aed(costs.total_costs, args.lang):>18}  = {labels['costs_total']}")
    print(f"{aed(costs.total_outlay, args.lang):>18}  = {labels['outlay_total']}")
    if costs.loan:
        print(f"{aed(costs.own_funds, args.lang):>18}  = {labels['own_funds_total']}")
    for remark in remarks:
        print(f"! {remark}")
    return 0


def cmd_comps(args) -> int:
    rows = _read_json(args.rows)
    if not isinstance(rows, list):
        raise CompsError("comparables file must be a JSON array of rows")
    summary = summarise(
        rows, args.today or date.today(), args.size, args.months, args.completion, args.new_leases, args.exclude_project
    )
    notes = []
    if summary.thin:
        notes.append(f"fewer than {MIN_COMPS} comparable rows: widen the window or the area and say so")
    if summary.concentrated:
        notes.append(f"more than {CONCENTRATION_LIMIT:.0%} of the rows come from one project: the median describes that project")
    payload = {
        "used": summary.used,
        "dropped": summary.dropped,
        "median_psf": summary.median_psf,
        "low_psf": summary.low_psf,
        "high_psf": summary.high_psf,
        "median_price_aed": summary.median_price,
        "first_date": summary.first_date,
        "last_date": summary.last_date,
        "largest_project_share": summary.largest_project_share,
        "thin": summary.thin,
        "projects": summary.projects,
        "notes": notes,
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
    listings, refused = [], []
    for index, item in enumerate(raw, start=1):
        try:
            listings.append(Listing.from_dict(item))
        except ListingError as exc:
            refused.append(f"listing {index}: {exc}")
    if refused:
        raise ListingError("\nerror: ".join(refused))
    result = assess(brief, listings, args.today or date.today())
    if args.format == "html":
        text = to_html(result, args.lang, args.top)
    elif args.format == "md":
        text = to_markdown(result, args.lang, args.top)
    else:
        text = json.dumps(to_data(result, args.lang, args.top), indent=2, ensure_ascii=False, allow_nan=False)
    _emit(text, args.out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="property-scout",
        description="Deterministic underwriting and ranking for UAE property listings",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("template", help="Print an example brief, or a ready and an off-plan example listing")
    p.add_argument("kind", choices=["brief", "listings"])
    p.set_defaults(handler=cmd_template)

    p = sub.add_parser("plan", help="Turn a brief into the search pages and queries to open")
    p.add_argument("--brief", required=True)
    p.set_defaults(handler=cmd_plan)

    p = sub.add_parser("costs", help="Itemise acquisition costs for one purchase")
    p.add_argument("--price", type=_positive, required=True)
    p.add_argument("--emirate", choices=EMIRATES, required=True)
    p.add_argument("--community", default=None, help="Decides who pays the transfer fee on the ADGM islands")
    p.add_argument("--completion", choices=COMPLETION, default="ready")
    p.add_argument("--sale-type", dest="sale_type", choices=SALE_TYPES, default=None)
    p.add_argument("--waived", action="store_true", help="The developer has waived the transfer fee (primary sales only)")
    p.add_argument("--financing", choices=FINANCING, default="cash")
    p.add_argument("--ltv", type=_fraction, default=None, help="Loan-to-value asked for, e.g. 0.75; capped at the Central Bank ceiling")
    p.add_argument("--nationality", choices=NATIONALITIES, default="other")
    p.add_argument("--first-home", dest="first_home", action="store_true", help="The buyer's first home, for their own use")
    p.add_argument("--lang", choices=LANGUAGES, default="en")
    p.add_argument("--json", action="store_true")
    p.set_defaults(handler=cmd_costs)

    p = sub.add_parser("comps", help="Median price per sqft from raw sold or rent rows")
    p.add_argument(
        "--rows", required=True,
        help="JSON array of {price_aed, size_sqft, date, completion, project, contract, term_months, excluded}; "
        "a row whose 'excluded' gives a reason is counted and left out",
    )
    p.add_argument("--size", type=_positive, default=None, help="Subject size in sqft; rows over 20%% away are dropped")
    p.add_argument("--months", type=_count, default=12, help="Look-back window for dated rows (default 12)")
    p.add_argument("--completion", choices=COMPLETION, default=None)
    p.add_argument("--new-leases", dest="new_leases", action="store_true", help="Rent rows: keep new twelve-month contracts only")
    p.add_argument(
        "--exclude-project", dest="exclude_project", action="append", default=[], metavar="NAME",
        help="Leave out the rows of this project; repeat for several",
    )
    p.add_argument("--today", type=_day, default=None)
    p.set_defaults(handler=cmd_comps)

    p = sub.add_parser("score", help="Filter, de-duplicate, score and rank listings against a brief")
    p.add_argument("--brief", required=True)
    p.add_argument("--listings", required=True)
    p.add_argument("--format", choices=["json", "md", "html"], default="json")
    p.add_argument("--lang", choices=LANGUAGES, default="en")
    p.add_argument("--top", type=_count, default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--today", type=_day, default=None, help="Valuation date, YYYY-MM-DD (defaults to today)")
    p.set_defaults(handler=cmd_score)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (InputError, OSError, ValueError, ArithmeticError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RecursionError:
        # Whether the parser or a later step gives up on such a file depends on the interpreter.
        print("error: the input is nested too deeply to be a brief, a listings file or a rows file", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
