"""Journal review: what a run of closed trades says, and how far a sample that size can be trusted."""

from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any, Dict, List, Optional

from property_scout.fields import InputError

from .records import Reader, one_clock
from .trade import SIDES

MIN_SAMPLE = 30
REQUIRED = ("closed", "side", "profit")


class JournalError(InputError):
    pass


@dataclass
class ClosedTrade:
    closed: str
    side: str
    profit: float
    volume: Optional[float] = None
    risk: Optional[float] = None
    symbol: str = ""
    opened: Optional[str] = None


@dataclass
class Stats:
    trades: int
    wins: int
    losses: int
    flat: int
    win_rate: float
    net: float
    gross_profit: float
    gross_loss: float
    average_win: Optional[float]
    average_loss: Optional[float]
    payoff: Optional[float]
    profit_factor: Optional[float]
    expectancy: float
    expectancy_r: Optional[float]
    r_coverage: float
    max_drawdown: float
    max_drawdown_pct: Optional[float]
    longest_losing_streak: int
    longest_winning_streak: int
    by_side: Dict[str, Dict[str, float]]
    small_sample: bool
    first: str
    last: str


def trades_from(rows: Any) -> List[ClosedTrade]:
    if not isinstance(rows, list):
        raise JournalError("closed trades must be a JSON array of {closed, side, profit, risk, ...}")
    trades, moments = [], []
    for index, row in enumerate(rows, start=1):
        read = Reader(row, [f.name for f in fields(ClosedTrade)], REQUIRED, JournalError, f"trade {index}")
        closed, opened = read.instant("closed"), read.instant("opened")
        trades.append(ClosedTrade(
            closed=closed.isoformat(),
            side=read.choice("side", SIDES),
            profit=read.signed("profit"),
            volume=read.number("volume"),
            risk=read.number("risk"),
            symbol=read.text("symbol"),
            opened=None if opened is None else opened.isoformat(),
        ))
        moments.append(closed)
    one_clock(moments, JournalError, "closed trades")
    return trades


def _streaks(results: List[float]) -> tuple:
    longest = {1: 0, -1: 0}
    run, sign = 0, 0
    for profit in results:
        current = (profit > 0) - (profit < 0)
        run = run + 1 if current == sign and current else (1 if current else 0)
        sign = current
        if current:
            longest[current] = max(longest[current], run)
    return longest[-1], longest[1]


def _drawdown(results: List[float], start: Optional[float]) -> tuple:
    value = peak = start or 0.0
    deepest, deepest_share = 0.0, 0.0
    for profit in results:
        value += profit
        peak = max(peak, value)
        deepest = max(deepest, peak - value)
        if start is not None and peak > 0:
            deepest_share = max(deepest_share, (peak - value) / peak * 100)
    return deepest, deepest_share if start is not None else None


def review(trades: List[ClosedTrade], start_balance: Optional[float] = None) -> Stats:
    if not trades:
        raise JournalError("no closed trades to review")
    ordered = sorted(trades, key=lambda trade: datetime.fromisoformat(trade.closed))
    results = [trade.profit for trade in ordered]
    wins = [profit for profit in results if profit > 0]
    losses = [profit for profit in results if profit < 0]
    gross_profit, gross_loss = sum(wins), sum(losses)
    average_win = gross_profit / len(wins) if wins else None
    average_loss = gross_loss / len(losses) if losses else None
    multiples = [trade.profit / trade.risk for trade in ordered if trade.risk]
    losing, winning = _streaks(results)
    deepest, deepest_share = _drawdown(results, start_balance)
    by_side = {}
    for side in SIDES:
        mine = [trade.profit for trade in ordered if trade.side == side]
        if mine:
            won = sum(1 for profit in mine if profit > 0)
            by_side[side] = {"trades": len(mine), "wins": won, "win_rate": won / len(mine), "net": sum(mine)}
    return Stats(
        trades=len(results),
        wins=len(wins),
        losses=len(losses),
        flat=len(results) - len(wins) - len(losses),
        win_rate=len(wins) / len(results),
        net=sum(results),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        average_win=average_win,
        average_loss=average_loss,
        payoff=average_win / -average_loss if average_win is not None and average_loss else None,
        profit_factor=gross_profit / -gross_loss if losses else None,
        expectancy=sum(results) / len(results),
        expectancy_r=sum(multiples) / len(multiples) if multiples else None,
        r_coverage=len(multiples) / len(results),
        max_drawdown=deepest,
        max_drawdown_pct=deepest_share,
        longest_losing_streak=losing,
        longest_winning_streak=winning,
        by_side=by_side,
        small_sample=len(results) < MIN_SAMPLE,
        first=ordered[0].closed,
        last=ordered[-1].closed,
    )
