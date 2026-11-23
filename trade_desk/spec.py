"""A symbol's contract specification, as MetaTrader 5 reports it for the account that trades it."""

from dataclasses import dataclass, fields
from typing import Any, Optional

from property_scout.fields import InputError

from .records import Reader

REQUIRED = ("name", "contract_size", "tick_size", "tick_value", "volume_min", "volume_step", "volume_max")
MAX_DIGITS = 8


class SpecError(InputError):
    pass


@dataclass
class Symbol:
    name: str
    contract_size: float
    tick_size: float
    tick_value: float
    volume_min: float
    volume_step: float
    volume_max: float
    digits: Optional[int] = None
    profit_currency: Optional[str] = None
    commission_per_lot: Optional[float] = None
    swap_long: Optional[float] = None
    swap_short: Optional[float] = None
    margin_per_lot: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Any) -> "Symbol":
        read = Reader(data, [f.name for f in fields(cls)], REQUIRED, SpecError, "symbol")
        symbol = cls(
            name=read.name("name"),
            contract_size=read.number("contract_size"),
            tick_size=read.number("tick_size"),
            tick_value=read.number("tick_value"),
            volume_min=read.number("volume_min"),
            volume_step=read.number("volume_step"),
            volume_max=read.number("volume_max"),
            digits=read.integer("digits", 0, MAX_DIGITS),
            profit_currency=read.currency("profit_currency"),
            commission_per_lot=read.number("commission_per_lot", open_low=False),
            swap_long=read.signed("swap_long"),
            swap_short=read.signed("swap_short"),
            margin_per_lot=read.number("margin_per_lot"),
        )
        if symbol.volume_max < symbol.volume_min:
            raise read.check.fail("volume_max", f"must be at least volume_min ({symbol.volume_min:g})", symbol.volume_max)
        return symbol
