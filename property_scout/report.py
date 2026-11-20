"""Render a ranking as JSON-ready data, Markdown, or a self-contained HTML page."""

import re
from datetime import date
from html import escape
from typing import Any, Dict, List, Optional

from .costs import RATES_AS_OF
from .messages import UI, aed, grouped, long_date, pct, render
from .scoring import Assessment, Result

PALETTE = {"page": "#FFFFFF", "text": "#111111", "mute": "#6B6B6B", "line": "#E2E2E2", "bar": "#333333"}
SEVERITY_COLOUR = {"critical": "#B42318", "warning": "#111111", "info": "#6B6B6B"}
_MD_SPECIAL = re.compile(r"([\\`*_\[\]|])")


def _md(text: str) -> str:
    return _MD_SPECIAL.sub(r"\\\1", text).replace("<", "&lt;").replace(">", "&gt;")


def _web(link: str) -> bool:
    return link.lower().startswith(("http://", "https://"))


def _unit_line(a: Assessment, lang: str) -> str:
    t = UI[lang]
    listing = a.listing
    parts: List[str] = []
    if listing.property_type:
        parts.append(t.get(f"type.{listing.property_type}", listing.property_type.replace("_", " ")))
    if listing.bedrooms is not None:
        parts.append(t["studio"] if listing.bedrooms == 0 else f"{listing.bedrooms} {t['beds']}")
    if listing.size_sqft:
        parts.append(f"{grouped(listing.size_sqft, lang)} {t['sqft']}")
    if listing.completion:
        parts.append(t[f"market.{listing.completion}"])
    if listing.offplan and listing.scheduled_handover:
        parts.append(f"{t['handover']} {listing.scheduled_handover}")
    if listing.emirate:
        parts.append(t[f"emirate.{listing.emirate}"])
    if listing.developer:
        parts.append(f"{t['developer']}: {listing.developer}")
    return " · ".join(parts)


def _advert_line(a: Assessment, lang: str) -> str:
    t = UI[lang]
    listing = a.listing
    parts: List[str] = []
    if listing.agent:
        parts.append(f"{t['agent']}: {listing.agent}")
    if listing.observed_on:
        parts.append(f"{t['seen']} {long_date(date.fromisoformat(listing.observed_on), lang)}")
    if listing.permit_number:
        parts.append(f"{t['permit']} {listing.permit_number}")
    return " · ".join(parts)


def _register_line(a: Assessment, lang: str) -> str:
    t = UI[lang]
    listing = a.listing
    parts: List[str] = []
    if listing.project_number:
        parts.append(f"{t['register_no']} {listing.project_number}")
    if listing.register_progress_pct is not None:
        parts.append(f"{t['register_built']} {listing.register_progress_pct:g}%")
    if listing.register_inspected_on:
        parts.append(f"{t['register_inspected']} {long_date(date.fromisoformat(listing.register_inspected_on), lang)}")
    if listing.register_completion:
        parts.append(f"{t['register_due']} {listing.register_completion}")
    if listing.escrow_bank:
        parts.append(f"{t['escrow']}: {listing.escrow_bank}")
    return f"{t['register']}: " + " · ".join(parts) if parts else ""


def _other_adverts(a: Assessment) -> List[tuple]:
    """Address and price of each folded advert; cards on one search page at one price read as one line."""
    return list(dict.fromkeys((d.url, d.price_aed) for d in a.duplicates))


def _share(value: Optional[float], lang: str, signed: bool = False) -> str:
    return UI[lang]["unknown"] if value is None else pct(value, signed=signed, lang=lang)


def _figures(a: Assessment, lang: str) -> List[tuple]:
    t = UI[lang]
    listing = a.listing
    figures = [
        (t["price"], aed(listing.price_aed, lang)),
        (t["psf"], aed(listing.price_psf, lang) if listing.price_psf else t["unknown"]),
        (t["gap"], _share(a.benchmark_gap, lang, signed=True)),
        (t["gross_yield"], _share(a.gross_yield, lang)),
        (t["net_yield"], _share(a.net_yield, lang)),
        (t["outlay"], aed(a.costs.total_outlay, lang)),
    ]
    if a.costs.loan:
        figures.append((t["own_funds"], aed(a.costs.own_funds, lang)))
    if a.cash_at_booking is not None:
        figures.append((t["cash_at_booking"], aed(a.cash_at_booking, lang)))
    if listing.building_sales_12m is not None:
        figures.append((t["sales_12m"], str(listing.building_sales_12m)))
    return figures


def _brief_line(result: Result, lang: str) -> str:
    t = UI[lang]
    brief = result.brief
    budget = aed(brief.budget_max, lang)
    if brief.budget_min:
        budget = f"{aed(brief.budget_min, lang)} – {budget}"
    if brief.budget_includes_costs:
        budget += f" ({t['budget_with_costs']})"
    where = ", ".join(brief.areas) or ", ".join(t[f"emirate.{e}"] for e in brief.emirates) or t["anywhere"]
    return (
        f"{t['budget']}: {budget} · {t['market']}: {t['market.' + brief.market]} · "
        f"{t['purpose']}: {t['purpose.' + brief.purpose]} · {t['where']}: {where}"
    )


def _counts(result: Result) -> Dict[str, int]:
    return {
        "received": result.received,
        "unique": len(result.ranked) + len(result.rejected),
        "ranked": len(result.ranked),
        "shortlisted": sum(1 for a in result.ranked if a.verdict == "shortlist"),
        "rejected": len(result.rejected),
    }


def _shown_weights(result: Result) -> Dict[str, float]:
    """Weights of the criteria that applied to at least one ranked offer."""
    used = {c.name for a in result.ranked for c in a.criteria if c.applicable}
    return {name: share for name, share in result.weights.items() if share and (name in used or not result.ranked)}


def to_data(result: Result, lang: str = "en", top: Optional[int] = None) -> Dict[str, Any]:
    ranked = result.ranked[:top] if top else result.ranked
    return {
        "as_of": result.as_of.isoformat(),
        "cost_rates_as_of": RATES_AS_OF,
        "weights": result.weights,
        "counts": _counts(result),
        "ranked": [
            {
                "rank": index,
                "url": a.listing.url,
                "evidence": a.listing.evidence,
                "label": a.listing.label,
                "title": a.listing.title,
                "agent": a.listing.agent,
                "observed_on": a.listing.observed_on,
                "permit_number": a.listing.permit_number,
                "verdict": a.verdict,
                "score": a.score,
                "completeness": a.confidence,
                "price_aed": a.listing.price_aed,
                "price_psf": a.listing.price_psf,
                "benchmark_gap": a.benchmark_gap,
                "gross_yield": a.gross_yield,
                "net_yield": a.net_yield,
                "total_outlay_aed": a.costs.total_outlay,
                "own_funds_aed": a.costs.own_funds if a.costs.loan else None,
                "loan_to_value_used": a.costs.ltv_used,
                "cash_at_booking_aed": a.cash_at_booking,
                "plan_present_value_ratio": a.plan.present_value_ratio if a.plan else None,
                "criteria": [
                    {
                        "name": c.name,
                        "score": None if c.score is None else round(c.score, 1),
                        "applicable": c.applicable,
                        "evidence": c.evidence,
                        "weight": result.weights[c.name],
                        "basis": "; ".join(render(n, lang) for n in c.notes),
                    }
                    for c in a.criteria
                ],
                "flags": [
                    {"severity": f.severity, "code": f.code, "message": render(f.note, lang)} for f in a.flags
                ],
                "costs": [{"item": render(i.note, lang), "amount_aed": i.amount} for i in a.costs.items],
                "duplicates": [
                    {"url": d.url, "price_aed": d.price_aed, "evidence": d.evidence, "agent": d.agent} for d in a.duplicates
                ],
                "notes": a.listing.notes,
                "sources": a.listing.sources,
            }
            for index, a in enumerate(ranked, start=1)
        ],
        "rejected": [
            {
                "url": r.listing.url,
                "label": r.listing.label,
                "title": r.listing.title,
                "price_aed": r.listing.price_aed,
                "reasons": [render(n, lang) for n in r.reasons],
            }
            for r in result.rejected
        ],
    }


def to_markdown(result: Result, lang: str = "en", top: Optional[int] = None) -> str:
    t = UI[lang]
    counts = _counts(result)
    ranked = result.ranked[:top] if top else result.ranked
    lines = [
        f"# {t['title']}",
        "",
        f"{t['as_of']} {long_date(result.as_of, lang)}. {_md(_brief_line(result, lang))}",
        "",
        " · ".join(f"{t[key]}: {counts[key]}" for key in ("received", "unique", "ranked", "shortlisted", "rejected")),
        "",
    ]
    if not ranked:
        lines += [t["none_ranked"], ""]
    for index, a in enumerate(ranked, start=1):
        listing = a.listing
        lines += [
            f"## {index}. {_md(listing.label)} — {t['verdict.' + a.verdict]} "
            f"({a.score:.1f}/100, {t['completeness'].lower()} {a.confidence:.0%})",
            "",
        ]
        if listing.title:
            lines.append(f"«{_md(listing.title)}»")
        lines += [_md(line) for line in (_unit_line(a, lang), _advert_line(a, lang), _register_line(a, lang)) if line]
        lines.append("")
        lines += [f"- {name}: {value}" for name, value in _figures(a, lang)]
        for c in a.criteria:
            if c.applicable:
                shown = t["unknown"] if c.score is None else f"{c.score:.0f}"
                lines.append(f"- {t['criterion.' + c.name]} {shown}: {_md('; '.join(render(n, lang) for n in c.notes))}")
        for f in a.flags:
            lines.append(f"- **{t['severity.' + f.severity]}** — {_md(render(f.note, lang))}")
        if listing.notes:
            lines.append(f"- {t['notes']}: {_md(listing.notes)}")
        lines.append(f"- {t['open_' + listing.evidence]}: <{listing.url}>")
        for url, price in _other_adverts(a):
            lines.append(f"- {t['also_listed']}: <{url}> ({aed(price, lang)})")
        for name, link in listing.sources.items():
            lines.append(f"- {t['sources']}, {_md(name)}: {'<' + link + '>' if _web(link) else _md(link)}")
        lines.append("")
    if result.rejected:
        lines += [f"## {t['rejected_title']}", ""]
        for r in result.rejected:
            reasons = "; ".join(render(n, lang) for n in r.reasons)
            lines.append(f"- {_md(r.listing.label)}, {aed(r.listing.price_aed, lang)}: {_md(reasons)} — <{r.listing.url}>")
        lines.append("")
    weights = " · ".join(f"{t['criterion.' + name]} {share:.0%}" for name, share in _shown_weights(result).items())
    lines += [f"## {t['method']}", "", t["method_text"].format(rates_as_of=RATES_AS_OF), "", f"{t['weights']}: {weights}", ""]
    return "\n".join(lines)


_CSS = """
*{box-sizing:border-box}
body{margin:0;background:%(page)s;color:%(text)s;font-family:system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;font-size:15px;line-height:1.55}
main{max-width:980px;margin:0 auto;padding:48px 24px 72px}
h1,h2,h3{font-weight:600;margin:0}
h1{font-size:34px}
h2{font-size:22px;margin-top:48px;padding-bottom:10px;border-bottom:1px solid %(line)s}
h3{font-size:20px}
a{color:%(text)s;text-decoration:underline;overflow-wrap:anywhere}
.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:%(mute)s}
.rule{height:1px;background:%(line)s;margin:18px 0}
.brief{color:%(mute)s;max-width:760px}
.stats{display:flex;flex-wrap:wrap;gap:12px;margin-top:24px}
.stat{flex:1 1 150px;border:1px solid %(line)s;padding:14px 16px;color:%(mute)s}
.stat b{display:block;font-size:26px;font-weight:600;color:%(text)s}
.card{border:1px solid %(line)s;margin-top:20px;padding:24px 26px}
.head{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}
.rank{color:%(mute)s;margin-right:10px;font-weight:400}
.unit{color:%(mute)s;margin-top:4px}
.score{text-align:right;white-space:nowrap}
.score b{font-size:34px;font-weight:600;line-height:1}
.badge{display:inline-block;margin-top:6px;padding:3px 10px;border:1px solid %(text)s;font-size:11px;letter-spacing:.08em;text-transform:uppercase}
.figures{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:20px 0 4px}
.figures span{display:block;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:%(mute)s}
.figures b{font-size:17px;font-weight:600}
h4{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:%(mute)s;font-weight:600;margin:22px 0 8px}
table{width:100%%;border-collapse:collapse}
td{padding:6px 0;border-top:1px solid %(line)s;vertical-align:top}
td.n{text-align:right;white-space:nowrap;padding-left:16px}
td.k{white-space:nowrap;padding-right:16px;width:1%%}
.bar{height:3px;background:%(line)s;margin-top:5px}.bar i{display:block;height:3px;background:%(bar)s}
ul{margin:0;padding:0;list-style:none}li{padding:6px 0;border-top:1px solid %(line)s}
.sev{font-size:10px;letter-spacing:.08em;text-transform:uppercase;font-weight:600;margin-right:8px}
.small{color:%(mute)s;font-size:13px}
footer{margin-top:48px;color:%(mute)s;font-size:13px;max-width:820px}
""" % PALETTE


def _link(url: str, text: str) -> str:
    return f"<a href='{escape(url, quote=True)}'>{escape(text)}</a>"


def _card(index: int, a: Assessment, result: Result, lang: str) -> str:
    t = UI[lang]
    listing = a.listing
    rows = []
    for c in a.criteria:
        if not c.applicable:
            continue
        shown = t["unknown"] if c.score is None else f"{c.score:.0f}"
        basis = escape("; ".join(render(n, lang) for n in c.notes))
        rows.append(
            f"<tr><td class='k'>{t['criterion.' + c.name]}<div class='small'>{result.weights[c.name]:.0%}</div></td>"
            f"<td>{basis}<div class='bar'><i style='width:{c.score or 0:.0f}%'></i></div></td><td class='n'>{shown}</td></tr>"
        )
    costs = "".join(
        f"<tr><td>{escape(render(i.note, lang))}</td><td class='n'>{aed(i.amount, lang)}</td></tr>" for i in a.costs.items
    )
    flags = "".join(
        f"<li><span class='sev' style='color:{SEVERITY_COLOUR[f.severity]}'>{t['severity.' + f.severity]}</span>"
        f"{escape(render(f.note, lang))}</li>"
        for f in a.flags
    )
    lines = "".join(
        f"<div class='unit'>{escape(line)}</div>"
        for line in (f"«{listing.title}»" if listing.title else "", _unit_line(a, lang), _advert_line(a, lang), _register_line(a, lang))
        if line
    )
    links = [f"<li>{_link(listing.url, t['open_' + listing.evidence] + ' →')}</li>"]
    links += [f"<li class='small'>{t['also_listed']}: {_link(url, url)} ({aed(price, lang)})</li>" for url, price in _other_adverts(a)]
    links += [
        f"<li class='small'>{t['sources']}, {escape(name)}: {_link(link, link) if _web(link) else escape(link)}</li>"
        for name, link in listing.sources.items()
    ]
    return (
        "<section class='card'><div class='head'><div>"
        f"<h3><span class='rank'>{index:02d}</span>{escape(listing.label)}</h3>{lines}</div>"
        f"<div class='score'><b>{a.score:.1f}</b><div class='small'>{t['completeness']} {a.confidence:.0%}</div>"
        f"<span class='badge'>{t['verdict.' + a.verdict]}</span></div></div>"
        "<div class='figures'>" + "".join(f"<div><span>{k}</span><b>{v}</b></div>" for k, v in _figures(a, lang)) + "</div>"
        f"<h4>{t['criteria']}</h4><table>{''.join(rows)}</table>"
        + (f"<h4>{t['flags']}</h4><ul>{flags}</ul>" if flags else "")
        + (f"<h4>{t['notes']}</h4><p>{escape(listing.notes)}</p>" if listing.notes else "")
        + (f"<h4>{t['costs']}</h4><table>{costs}</table>" if costs else "")
        + f"<h4>&nbsp;</h4><ul>{''.join(links)}</ul></section>"
    )


def to_html(result: Result, lang: str = "en", top: Optional[int] = None) -> str:
    t = UI[lang]
    counts = _counts(result)
    ranked = result.ranked[:top] if top else result.ranked
    stats = "".join(
        f"<div class='stat'><b>{counts[key]}</b>{t[key]}</div>"
        for key in ("received", "unique", "ranked", "shortlisted", "rejected")
    )
    cards = "".join(_card(i, a, result, lang) for i, a in enumerate(ranked, start=1)) or f"<p>{t['none_ranked']}</p>"
    rejected = ""
    if result.rejected:
        items = "".join(
            f"<li>{_link(r.listing.url, r.listing.label)} · {aed(r.listing.price_aed, lang)}"
            f"<div class='small'>{escape('; '.join(render(n, lang) for n in r.reasons))}</div></li>"
            for r in result.rejected
        )
        rejected = f"<h2>{t['rejected_title']}</h2><ul>{items}</ul>"
    client = f"<div class='eyebrow'>{t['prepared_for']} {escape(result.brief.client)}</div>" if result.brief.client else ""
    weights = " · ".join(f"{t['criterion.' + name]} {share:.0%}" for name, share in _shown_weights(result).items())
    day = long_date(result.as_of, lang)
    return (
        f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{t['title']} — {day}</title><style>{_CSS}</style></head><body><main>"
        f"<div class='eyebrow'>{t['subtitle']} · {t['as_of']} {day}</div>"
        f"<h1>{t['title']}</h1><div class='rule'></div>{client}"
        f"<p class='brief'>{escape(_brief_line(result, lang))}</p><div class='stats'>{stats}</div>"
        f"{cards}{rejected}"
        f"<footer><h2>{t['method']}</h2><p>{t['method_text'].format(rates_as_of=RATES_AS_OF)}</p>"
        f"<p>{t['weights']}: {weights}</p></footer></main></body></html>"
    )
