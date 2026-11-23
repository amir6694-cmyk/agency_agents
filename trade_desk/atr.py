"""Average true range from candles, and a stop placed a multiple of it away from the entry.

The default `sma` is what MetaTrader 5's built-in ATR draws: true range against the previous close,
averaged over the last `period` bars. `wilder` is the smoothing Wilder published.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional

from property_scout.fields import InputError

from .records import Reader, one_clock
from .sizing import STEP_EPSILON
from .trade import SIDES

DEFAULT_PERIOD = 14
METHODS = ("sma", "wilder")
PRICES = ("open", "high", "low", "close")
# Columns a MetaTrader export carries that the range does not use.
EXPORT_COLUMNS = ("tick_volume", "volume", "real_volume", "spread")


class CandleError(InputError):
    pass


@dataclass
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float


def candles_from(rows: Any) -> List[Candle]:
    if not isinstance(rows, list):
        raise CandleError("candles must be a JSON array of {time, open, high, low, close}")
    candles = []
    for index, row in enumerate(rows, start=1):
        where = f"candle {index}"
        read = Reader(row, ("time",) + PRICES + EXPORT_COLUMNS, ("time",) + PRICES, CandleError, where)
        candle = Candle(read.instant("time"), *(read.number(name) for name in PRICES))
        if candle.high < max(candle.open, candle.close, candle.low):
            raise read.check.fail("high", "must be at least the open, the close and the low", candle.high)
        if candle.low > min(candle.open, candle.close):
            raise read.check.fail("low", "must be at most the open and the close", candle.low)
        if candles:
            one_clock((candles[-1].time, candle.time), CandleError, where)
            if candle.time <= candles[-1].time:
                raise read.check.fail("time", f"must be later than candle {index - 1}", row["time"])
        candles.append(candle)
    return candles


def true_ranges(candles: List[Candle]) -> List[float]:
    return [
        max(bar.high, before.close) - min(bar.low, before.close)
        for before, bar in zip(candles, candles[1:])
    ]


def atr(candles: List[Candle], period: int = DEFAULT_PERIOD, method: str = "sma") -> float:
    if method not in METHODS:
        raise CandleError(f"method must be one of {METHODS}, got {method!r}")
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise CandleError(f"period must be a whole number of at least 1, got {period!r}")
    if len(candles) < period + 1:
        raise CandleError(f"ATR({period}) needs {period + 1} candles, got {len(candles)}")
    ranges = true_ranges(candles)
    if method == "sma":
        return sum(ranges[-period:]) / period
    value = sum(ranges[:period]) / period
    for item in ranges[period:]:
        value = (value * (period - 1) + item) / period
    return value


def atr_stop(entry: float, side: str, value: float, multiple: float, tick_size: Optional[float] = None) -> float:
    """A stop `multiple` ATRs from the entry, moved outward onto the tick grid."""
    if side not in SIDES:
        raise InputError(f"side must be one of {SIDES}, got {side!r}")
    if not multiple > 0:
        raise InputError(f"the ATR multiple must be above 0, got {multiple!r}")
    stop = entry - multiple * value if side == "buy" else entry + multiple * value
    if tick_size:
        ticks = stop / tick_size
        stop = (math.floor(ticks + STEP_EPSILON) if side == "buy" else math.ceil(ticks - STEP_EPSILON)) * tick_size
        stop = round(stop, 8)
    if stop <= 0:
        raise InputError(f"a stop {multiple:g} ATRs below {entry:g} would be at or below zero")
    return stop
