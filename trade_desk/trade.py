"""One planned trade: side, entry, stop, target, and what it costs to get in and to hold."""

from dataclasses import dataclass, fields
from typing import Any, Optional

from property_scout.fields import InputError

from .records import Reader

SIDES = ("buy", "sell")
REQUIRED = ("symbol", "side", "entry", "stop")
MAX_ROLLOVERS = 366


class TradeError(InputError):
    pass


def direction(side: str) -> int:
    return 1 if side == "buy" else -1


@dataclass
class Trade:
    symbol: str
    side: str
    entry: float
    stop: float
    target: Optional[float] = None
    spread: Optional[float] = None
    slippage: Optional[float] = None
    rollovers: Optional[int] = None
    note: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "Trade":
        read = Reader(data, [f.name for f in fields(cls)], REQUIRED, TradeError, "trade")
        trade = cls(
            symbol=read.name("symbol"),
            side=read.choice("side", SIDES),
            entry=read.number("entry"),
            stop=read.number("stop"),
            target=read.number("target"),
            spread=read.number("spread", open_low=False),
            slippage=read.number("slippage", open_low=False),
            rollovers=read.integer("rollovers", 0, MAX_ROLLOVERS),
            note=read.text("note"),
        )
        sign = direction(trade.side)
        if (trade.entry - trade.stop) * sign <= 0:
            where = "below" if sign > 0 else "above"
            raise read.check.fail("stop", f"must be {where} the entry of {trade.entry:g} for a {trade.side}", trade.stop)
        if trade.target is not None and (trade.target - trade.entry) * sign <= 0:
            where = "above" if sign > 0 else "below"
            raise read.check.fail("target", f"must be {where} the entry of {trade.entry:g} for a {trade.side}", trade.target)
        return trade
