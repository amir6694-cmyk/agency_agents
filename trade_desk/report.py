"""Reports: JSON for the agent, Markdown for the trader. Both carry every figure the verdict rests on."""

import html
from dataclasses import asdict
from typing import Any, Dict, Optional

from .guard import Assessment
from .journal import MIN_SAMPLE, Stats
from .messages import render

PREFIX = {"block": "BLOCK", "hold": "REVIEW", "info": "NOTE"}


def _round(value: Optional[float], places: int) -> Optional[float]:
    return None if value is None else round(value, places)


def _money(value: Optional[float]) -> Optional[float]:
    return _round(value, 2)


def to_data(assessment: Assessment) -> Dict[str, Any]:
    sizing, trade = assessment.sizing, assessment.trade
    return {
        "verdict": assessment.verdict,
        "symbol": trade.symbol,
        "side": trade.side,
        "entry": trade.entry,
        "stop": trade.stop,
        "target": trade.target,
        "currency": assessment.account.currency,
        "lots": sizing.lots,
        "risk": _money(sizing.risk),
        "risk_pct": _round(sizing.risk_pct, 4),
        "budget": _money(sizing.budget),
        "loss_per_lot": _money(sizing.loss_per_lot),
        "costs_per_lot": _money(sizing.costs_per_lot),
        "reward": _money(sizing.reward),
        "r_multiple": _round(sizing.r_multiple, 4),
        "breakeven_win_rate": _round(sizing.breakeven_win_rate, 4),
        "min_lot_risk_pct": _round(sizing.min_lot_risk_pct, 4),
        "margin": _money(sizing.margin),
        "margin_estimated": sizing.margin_estimated,
        "margin_level": _round(assessment.margin_level, 1),
        "open_risk": _money(assessment.open_risk),
        "worst_equity": _money(assessment.worst_equity),
        "floors": [
            {"name": item.name, "level": _money(item.level), "limit": _money(item.limit), "room": _money(item.room)}
            for item in assessment.floors
        ],
        "lots_that_fit": assessment.lots_that_fit,
        "note": trade.note,
        "flags": [{"code": flag.code, "level": flag.level, "text": render(flag)} for flag in assessment.flags],
    }


def _escape(text: str) -> str:
    return html.escape(text, quote=False).replace("|", "\\|")


def to_markdown(assessment: Assessment) -> str:
    sizing, trade, account = assessment.sizing, assessment.trade, assessment.account
    digits = assessment.symbol.digits
    currency = account.currency

    def price(value: float) -> str:
        return f"{value:.{digits}f}" if digits is not None else f"{value:g}"

    def money(value: float) -> str:
        return f"{value:,.2f} {currency}"

    target = "none"
    if trade.target is not None:
        target = f"{price(trade.target)} ({sizing.r_multiple:.2f}R after costs)"
    margin = "unknown"
    if sizing.margin is not None:
        margin = money(sizing.margin) + (" (estimated)" if sizing.margin_estimated else "")
        if assessment.margin_level is not None:
            margin += f", margin level {assessment.margin_level:,.0f}% after the trade"
    rows = [
        ("Entry", price(trade.entry)),
        ("Stop", f"{price(trade.stop)} ({price(sizing.distance)} away)"),
        ("Target", target),
        ("Size", f"{sizing.lots:g} lots"),
        ("Risk", f"{money(sizing.risk)} ({sizing.risk_pct:.2f}% of {sizing.base:,.2f}; budget {money(sizing.budget)})"),
        ("Loss per lot at the stop", f"{money(sizing.loss_per_lot)}, costs {money(sizing.costs_per_lot)} included"),
    ]
    if sizing.reward is not None:
        rows.append(("Reward at the target", money(sizing.reward)))
    if sizing.breakeven_win_rate is not None:
        rows.append(("Break-even win rate", f"{sizing.breakeven_win_rate:.1%}"))
    rows += [
        ("Margin", margin),
        ("Open risk", money(assessment.open_risk)),
        ("Equity if every stop is hit", money(assessment.worst_equity)),
    ]
    for item in assessment.floors:
        rows.append((f"{item.name.capitalize()} loss floor", f"{item.level:,.2f} (limit {item.limit:,.2f}, room {item.room:,.2f})"))
    if assessment.lots_that_fit is not None:
        rows.append(("Most lots the floors allow", f"{assessment.lots_that_fit:g}"))
    if trade.note:
        rows.append(("Note", _escape(trade.note)))
    lines = [f"# {trade.symbol} {trade.side}: **{assessment.verdict.upper()}**", "", "| | |", "|---|---|"]
    lines += [f"| {label} | {value} |" for label, value in rows]
    if assessment.flags:
        lines += ["", "## Flags", ""]
        lines += [f"- {PREFIX[flag.level]}: {render(flag)}" for flag in assessment.flags]
    return "\n".join(lines) + "\n"


def journal_data(stats: Stats) -> Dict[str, Any]:
    data = asdict(stats)
    for name in ("net", "gross_profit", "gross_loss", "average_win", "average_loss", "expectancy", "max_drawdown"):
        data[name] = _money(data[name])
    for name in ("win_rate", "payoff", "profit_factor", "expectancy_r", "r_coverage", "max_drawdown_pct"):
        data[name] = _round(data[name], 4)
    for side in data["by_side"].values():
        side["win_rate"] = round(side["win_rate"], 4)
        side["net"] = round(side["net"], 2)
    return data


def journal_markdown(stats: Stats) -> str:
    def ratio(value: Optional[float]) -> str:
        return "n/a" if value is None else f"{value:.2f}"

    rows = [
        ("Trades", f"{stats.trades} ({stats.wins} won, {stats.losses} lost, {stats.flat} flat), {stats.first} to {stats.last}"),
        ("Win rate", f"{stats.win_rate:.1%}"),
        ("Net", f"{stats.net:,.2f}"),
        ("Average win / loss", f"{ratio(stats.average_win)} / {ratio(stats.average_loss)}"),
        ("Payoff ratio", ratio(stats.payoff)),
        ("Profit factor", ratio(stats.profit_factor)),
        ("Expectancy per trade", f"{stats.expectancy:,.2f}"),
        ("Expectancy in R", "n/a" if stats.expectancy_r is None else f"{stats.expectancy_r:.2f}R over {stats.r_coverage:.0%} of trades"),
        ("Largest drawdown", f"{stats.max_drawdown:,.2f}" + ("" if stats.max_drawdown_pct is None else f" ({stats.max_drawdown_pct:.1f}% of the peak)")),
        ("Longest losing / winning streak", f"{stats.longest_losing_streak} / {stats.longest_winning_streak}"),
    ]
    for side, figures in stats.by_side.items():
        rows.append((f"{side.capitalize()}s", f"{figures['trades']} trades, {figures['win_rate']:.1%} won, net {figures['net']:,.2f}"))
    lines = ["# Journal review", "", "| | |", "|---|---|"] + [f"| {label} | {value} |" for label, value in rows]
    if stats.small_sample:
        lines += ["", f"Small sample: fewer than {MIN_SAMPLE} trades, so these figures describe this run more than the strategy."]
    return "\n".join(lines) + "\n"
