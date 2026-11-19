"""Render a ranking as JSON-ready data, Markdown, or a self-contained HTML page."""

from html import escape
from typing import Any, Dict, List, Optional

from .costs import RATES_AS_OF
from .messages import UI, aed, long_date, pct, render
from .scoring import Assessment, Result

PALETTE = {"navy": "#071522", "panel": "#0E2233", "line": "#1E3A52", "gold": "#C9A45D", "ivory": "#F2EBDD", "mute": "#8FA0AD"}
SEVERITY_COLOUR = {"critical": "#D9654F", "warning": "#C9A45D", "info": "#8FA0AD"}


def _unit_line(a: Assessment, t: Dict[str, str]) -> str:
    listing = a.listing
    parts: List[str] = []
    if listing.property_type:
        parts.append(t.get(f"type.{listing.property_type}", listing.property_type.replace("_", " ")))
    if listing.bedrooms is not None:
        parts.append(t["studio"] if listing.bedrooms == 0 else f"{listing.bedrooms} {t['beds']}")
    if listing.size_sqft:
        parts.append(f"{listing.size_sqft:,.0f} {t['sqft']}")
    if listing.completion:
        parts.append(t[f"market.{listing.completion}"])
    if listing.handover and listing.completion == "offplan":
        parts.append(f"{t['handover']} {listing.handover}")
    if listing.emirate:
        parts.append(t[f"emirate.{listing.emirate}"])
    return " · ".join(parts)


def _share(value: Optional[float], lang: str, signed: bool = False) -> str:
    return UI[lang]["unknown"] if value is None else pct(value, signed=signed, lang=lang)


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


def to_data(result: Result, lang: str = "en", top: Optional[int] = None) -> Dict[str, Any]:
    ranked = result.ranked[:top] if top else result.ranked
    return {
        "as_of": result.as_of.isoformat(),
        "cost_rates_as_of": RATES_AS_OF,
        "weights": result.weights,
        "counts": {
            "received": result.received,
            "unique": len(result.ranked) + len(result.rejected),
            "ranked": len(result.ranked),
            "shortlisted": sum(1 for a in result.ranked if a.verdict == "shortlist"),
            "rejected": len(result.rejected),
        },
        "ranked": [
            {
                "rank": index,
                "url": a.listing.url,
                "evidence": a.listing.evidence,
                "label": a.listing.label,
                "verdict": a.verdict,
                "score": a.score,
                "confidence": a.confidence,
                "price_aed": a.listing.price_aed,
                "price_psf": a.listing.price_psf,
                "benchmark_gap": a.benchmark_gap,
                "gross_yield": a.gross_yield,
                "net_yield": a.net_yield,
                "total_outlay_aed": a.costs.total_outlay,
                "upfront_cash_aed": a.costs.upfront_cash,
                "plan_present_value_ratio": a.plan.present_value_ratio if a.plan else None,
                "criteria": [
                    {
                        "name": c.name,
                        "score": c.score,
                        "applicable": c.applicable,
                        "weight": result.weights[c.name],
                        "basis": "; ".join(render(n, lang) for n in c.notes),
                    }
                    for c in a.criteria
                ],
                "flags": [
                    {"severity": f.severity, "code": f.code, "message": render(f.note, lang)} for f in a.flags
                ],
                "costs": [{"item": render(i.note, lang), "amount_aed": i.amount} for i in a.costs.items],
                "duplicate_urls": a.duplicate_urls,
            }
            for index, a in enumerate(ranked, start=1)
        ],
        "rejected": [
            {"url": r.listing.url, "label": r.listing.label, "reasons": [render(n, lang) for n in r.reasons]}
            for r in result.rejected
        ],
    }


def to_markdown(result: Result, lang: str = "en", top: Optional[int] = None) -> str:
    t = UI[lang]
    data = to_data(result, lang, top)
    counts = data["counts"]
    ranked = result.ranked[:top] if top else result.ranked
    lines = [
        f"# {t['title']}",
        "",
        f"{t['as_of']} {long_date(result.as_of, lang)}. {_brief_line(result, lang)}",
        "",
        f"{t['received']}: {counts['received']} · {t['unique']}: {counts['unique']} · "
        f"{t['ranked']}: {counts['ranked']} · {t['shortlisted']}: {counts['shortlisted']} · "
        f"{t['rejected']}: {counts['rejected']}",
        "",
    ]
    if not ranked:
        lines += [t["none_ranked"], ""]
    for index, a in enumerate(ranked, start=1):
        listing = a.listing
        psf = aed(listing.price_psf, lang) if listing.price_psf else t["unknown"]
        lines += [
            f"## {index}. {listing.label} — {t['verdict.' + a.verdict]} ({a.score:.0f}/100, {t['confidence'].lower()} {a.confidence:.0%})",
            "",
            _unit_line(a, t),
            "",
            f"- {t['price']}: {aed(listing.price_aed, lang)} ({psf} {t['psf']}; {_share(a.benchmark_gap, lang, signed=True)} {t['gap']})",
            f"- {t['gross_yield']}: {_share(a.gross_yield, lang)} · {t['net_yield']}: {_share(a.net_yield, lang)}",
            f"- {t['outlay']}: {aed(a.costs.total_outlay, lang)}",
        ]
        if a.costs.loan:
            lines.append(f"- {t['upfront_cash']}: {aed(a.costs.upfront_cash, lang)}")
        for c in a.criteria:
            if c.applicable:
                shown = t["unknown"] if c.score is None else f"{c.score:.0f}"
                lines.append(f"- {t['criterion.' + c.name]} {shown}: {'; '.join(render(n, lang) for n in c.notes)}")
        for f in a.flags:
            lines.append(f"- **{t['severity.' + f.severity]}** — {render(f.note, lang)}")
        lines.append(f"- {listing.url}")
        for url in a.duplicate_urls:
            lines.append(f"- {t['also_listed']}: {url}")
        lines.append("")
    if result.rejected:
        lines += [f"## {t['rejected_title']}", ""]
        for r in result.rejected:
            lines.append(f"- {r.listing.label}: {'; '.join(render(n, lang) for n in r.reasons)} — {r.listing.url}")
        lines.append("")
    lines += [f"## {t['method']}", "", t["method_text"].format(rates_as_of=RATES_AS_OF), ""]
    return "\n".join(lines)


_CSS = """
*{box-sizing:border-box}
body{margin:0;background:%(navy)s;color:%(ivory)s;font-family:'Manrope','Helvetica Neue',Arial,sans-serif;font-size:15px;line-height:1.55}
main{max-width:980px;margin:0 auto;padding:56px 24px 72px}
h1,h2,h3{font-family:'Cormorant Garamond','Fraunces',Georgia,serif;font-weight:500;letter-spacing:.02em;margin:0}
h1{font-size:44px;color:%(gold)s}
h2{font-size:26px;margin-top:56px;padding-bottom:10px;border-bottom:1px solid %(line)s}
h3{font-size:25px}
a{color:%(gold)s;text-decoration:none;border-bottom:1px solid transparent}a:hover{border-bottom-color:%(gold)s}
.eyebrow{font-size:11px;letter-spacing:.28em;text-transform:uppercase;color:%(mute)s}
.rule{width:72px;height:1px;background:%(gold)s;margin:22px 0}
.brief{color:%(mute)s;max-width:760px}
.stats{display:flex;flex-wrap:wrap;gap:12px;margin-top:28px}
.stat{flex:1 1 150px;border:1px solid %(line)s;padding:14px 16px}
.stat b{display:block;font-family:'Cormorant Garamond','Fraunces',Georgia,serif;font-size:30px;font-weight:500;color:%(gold)s}
.card{background:%(panel)s;border:1px solid %(line)s;margin-top:22px;padding:26px 28px}
.head{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}
.rank{font-family:'Cormorant Garamond','Fraunces',Georgia,serif;font-size:20px;color:%(gold)s;margin-right:10px}
.unit{color:%(mute)s;margin-top:4px}
.score{text-align:right;white-space:nowrap}
.score b{font-family:'Cormorant Garamond','Fraunces',Georgia,serif;font-size:40px;font-weight:500;color:%(gold)s;line-height:1}
.badge{display:inline-block;margin-top:6px;padding:3px 10px;border:1px solid %(gold)s;font-size:11px;letter-spacing:.16em;text-transform:uppercase}
.figures{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:22px 0 4px}
.figures span{display:block;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:%(mute)s}
.figures b{font-size:17px;font-weight:500}
h4{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:%(mute)s;font-weight:500;margin:22px 0 8px}
table{width:100%%;border-collapse:collapse}
td{padding:6px 0;border-top:1px solid %(line)s;vertical-align:top}
td.n{text-align:right;white-space:nowrap;padding-left:16px}
td.k{white-space:nowrap;padding-right:16px;width:1%%}
.bar{height:3px;background:%(line)s;margin-top:5px}.bar i{display:block;height:3px;background:%(gold)s}
ul{margin:0;padding:0;list-style:none}li{padding:6px 0;border-top:1px solid %(line)s}
.sev{font-size:10px;letter-spacing:.16em;text-transform:uppercase;margin-right:8px}
.small{color:%(mute)s;font-size:13px}
footer{margin-top:56px;color:%(mute)s;font-size:13px;max-width:820px}
@media print{body{background:#fff;color:#111}.card{background:#fff}h1,.stat b,.score b,.rank,a{color:#7a5c1e}}
""" % PALETTE


def _card(index: int, a: Assessment, result: Result, lang: str) -> str:
    t = UI[lang]
    listing = a.listing
    psf = aed(listing.price_psf, lang) if listing.price_psf else t["unknown"]
    figures = [
        (t["price"], aed(listing.price_aed, lang)),
        (t["psf"], psf),
        (t["gap"], _share(a.benchmark_gap, lang, signed=True)),
        (t["gross_yield"], _share(a.gross_yield, lang)),
        (t["net_yield"], _share(a.net_yield, lang)),
        (t["outlay"], aed(a.costs.total_outlay, lang)),
    ]
    if a.costs.loan:
        figures.append((t["upfront_cash"], aed(a.costs.upfront_cash, lang)))
    rows = []
    for c in a.criteria:
        if not c.applicable:
            continue
        shown = t["unknown"] if c.score is None else f"{c.score:.0f}"
        width = 0 if c.score is None else c.score
        basis = escape("; ".join(render(n, lang) for n in c.notes))
        rows.append(
            f"<tr><td class='k'>{t['criterion.' + c.name]}<div class='small'>{result.weights[c.name]:.0%}</div></td>"
            f"<td>{basis}<div class='bar'><i style='width:{width}%'></i></div></td><td class='n'>{shown}</td></tr>"
        )
    costs = "".join(
        f"<tr><td>{escape(render(i.note, lang))}</td><td class='n'>{aed(i.amount, lang)}</td></tr>" for i in a.costs.items
    )
    flags = "".join(
        f"<li><span class='sev' style='color:{SEVERITY_COLOUR[f.severity]}'>{t['severity.' + f.severity]}</span>"
        f"{escape(render(f.note, lang))}</li>"
        for f in a.flags
    )
    extra = "".join(
        f"<div class='small'>{t['also_listed']}: <a href='{escape(u, quote=True)}'>{escape(u)}</a></div>"
        for u in a.duplicate_urls
    )
    developer = f" · {t['developer']}: {escape(listing.developer)}" if listing.developer else ""
    return (
        "<section class='card'><div class='head'><div>"
        f"<h3><span class='rank'>{index:02d}</span>{escape(listing.label)}</h3>"
        f"<div class='unit'>{escape(_unit_line(a, t))}{developer}</div></div>"
        f"<div class='score'><b>{a.score:.0f}</b><div class='small'>{t['confidence']} {a.confidence:.0%}</div>"
        f"<span class='badge'>{t['verdict.' + a.verdict]}</span></div></div>"
        "<div class='figures'>" + "".join(f"<div><span>{k}</span><b>{v}</b></div>" for k, v in figures) + "</div>"
        f"<h4>{t['criteria']}</h4><table>{''.join(rows)}</table>"
        + (f"<h4>{t['flags']}</h4><ul>{flags}</ul>" if flags else "")
        + (f"<h4>{t['costs']}</h4><table>{costs}</table>" if costs else "")
        + f"<h4>&nbsp;</h4><a href='{escape(listing.url, quote=True)}'>{t['open_' + listing.evidence]} →</a>{extra}</section>"
    )


def to_html(result: Result, lang: str = "en", top: Optional[int] = None) -> str:
    t = UI[lang]
    data = to_data(result, lang, top)
    counts = data["counts"]
    ranked = result.ranked[:top] if top else result.ranked
    stats = "".join(
        f"<div class='stat'><b>{counts[key]}</b>{t[key]}</div>"
        for key in ("received", "unique", "ranked", "shortlisted", "rejected")
    )
    cards = "".join(_card(i, a, result, lang) for i, a in enumerate(ranked, start=1)) or f"<p>{t['none_ranked']}</p>"
    rejected = ""
    if result.rejected:
        items = "".join(
            f"<li><a href='{escape(r.listing.url, quote=True)}'>{escape(r.listing.label)}</a>"
            f"<div class='small'>{escape('; '.join(render(n, lang) for n in r.reasons))}</div></li>"
            for r in result.rejected
        )
        rejected = f"<h2>{t['rejected_title']}</h2><ul>{items}</ul>"
    client = f"<div class='eyebrow'>{t['prepared_for']} {escape(result.brief.client)}</div>" if result.brief.client else ""
    weights = " · ".join(f"{t['criterion.' + name]} {share:.0%}" for name, share in result.weights.items() if share)
    return (
        f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{t['title']} — {long_date(result.as_of, lang)}</title>"
        "<link rel='preconnect' href='https://fonts.googleapis.com'>"
        "<link href='https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=Manrope:wght@400;500;600&display=swap' rel='stylesheet'>"
        f"<style>{_CSS}</style></head><body><main>"
        f"<div class='eyebrow'>{t['subtitle']} · {t['as_of']} {long_date(result.as_of, lang)}</div>"
        f"<h1>{t['title']}</h1><div class='rule'></div>{client}"
        f"<p class='brief'>{escape(_brief_line(result, lang))}</p><div class='stats'>{stats}</div>"
        f"{cards}{rejected}"
        f"<footer><h2>{t['method']}</h2><p>{t['method_text'].format(rates_as_of=RATES_AS_OF)}</p>"
        f"<p>{t['weights']}: {weights}</p></footer></main></body></html>"
    )
