"""The trading account: what it holds, what it may risk, and the loss limits it must stay inside."""

from dataclasses import dataclass, fields
from typing import Any, List, Optional

from property_scout.fields import InputError

from .records import Reader
from .trade import SIDES, direction

DAILY_BASES = ("initial", "day_start")
MAX_LOSS_MODES = ("static", "trailing")
REQUIRED = ("currency", "balance", "equity", "risk_pct", "open_positions")
POSITION_REQUIRED = ("symbol", "side", "volume")
MAX_LEVERAGE = 100_000


class AccountError(InputError):
    pass


@dataclass
class OpenPosition:
    symbol: str
    side: str
    volume: float
    price_current: Optional[float] = None
    stop: Optional[float] = None
    risk_to_stop: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Any, where: str) -> "OpenPosition":
        read = Reader(data, [f.name for f in fields(cls)], POSITION_REQUIRED, AccountError, where)
        position = cls(
            symbol=read.name("symbol"),
            side=read.choice("side", SIDES),
            volume=read.number("volume"),
            price_current=read.number("price_current"),
            stop=read.number("stop"),
            risk_to_stop=read.number("risk_to_stop", open_low=False),
        )
        if position.risk_to_stop is not None and (position.price_current is not None or position.stop is not None):
            raise read.check.fail("risk_to_stop", "replaces price_current and stop; give one or the other", position.risk_to_stop)
        if position.price_current is not None and position.stop is not None:
            if (position.price_current - position.stop) * direction(position.side) <= 0:
                where = "below" if position.side == "buy" else "above"
                raise read.check.fail("stop", f"must be {where} the current price of {position.price_current:g}; a stop past it has been hit", position.stop)
        return position


@dataclass
class Account:
    currency: str
    balance: float
    equity: float
    risk_pct: float
    open_positions: List[OpenPosition]
    leverage: Optional[float] = None
    margin_used: Optional[float] = None
    conversion_rate: Optional[float] = None
    daily_loss_pct: Optional[float] = None
    daily_loss_of: Optional[str] = None
    day_start_balance: Optional[float] = None
    max_loss_pct: Optional[float] = None
    max_loss_mode: Optional[str] = None
    initial_balance: Optional[float] = None
    high_water: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Any) -> "Account":
        read = Reader(data, [f.name for f in fields(cls)], REQUIRED, AccountError, "account")
        positions = read.get("open_positions")
        if not isinstance(positions, list):
            raise read.check.fail("open_positions", "must be a list, empty when nothing is open", positions)
        return cls(
            currency=read.currency("currency"),
            balance=read.number("balance"),
            equity=read.number("equity"),
            risk_pct=read.number("risk_pct", high=100),
            open_positions=[OpenPosition.from_dict(item, f"account: open_positions[{index}]") for index, item in enumerate(positions)],
            leverage=read.number("leverage", high=MAX_LEVERAGE),
            margin_used=read.number("margin_used", open_low=False),
            conversion_rate=read.number("conversion_rate"),
            daily_loss_pct=read.number("daily_loss_pct", high=100),
            daily_loss_of=read.choice("daily_loss_of", DAILY_BASES),
            day_start_balance=read.number("day_start_balance"),
            max_loss_pct=read.number("max_loss_pct", high=100),
            max_loss_mode=read.choice("max_loss_mode", MAX_LOSS_MODES),
            initial_balance=read.number("initial_balance"),
            high_water=read.number("high_water"),
        )
