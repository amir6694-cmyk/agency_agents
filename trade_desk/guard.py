"""The verdict on one trade: go, review or blocked, with every flag that decided it.

A flag at level `block` stops the trade, `hold` sends it to review, `info` only informs. Anything the
risk depends on that the records leave out is a hold, so a gap can never be what lets a trade through.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .account import DAILY_BASES, Account
from .sizing import Sizing, conversion, round_down, size, value_per_unit
from .spec import Symbol
from .trade import Trade

HIGH_RISK_PCT = 2.0
MIN_REWARD_RISK = 1.0
TIGHT_HEADROOM = 0.25
SPREAD_SHARE_LIMIT = 0.2
MARGIN_LEVEL_WARN = 300.0
SPEC_TOLERANCE = 0.02
MARGIN_ESTIMATE_FACTOR = 5.0

VERDICTS = ("blocked", "review", "go")

LEVELS = {
    "below_min_volume": "block",
    "spec_inconsistent": "block",
    "limit_breached": "block",
    "limit_would_breach": "block",
    "margin_insufficient": "block",
    "open_without_stop": "block",
    "spec_unchecked": "hold",
    "commission_unknown": "hold",
    "slippage_unknown": "hold",
    "hold_unknown": "hold",
    "swap_unknown": "hold",
    "spread_unknown": "hold",
    "spread_wide": "hold",
    "no_target": "hold",
    "reward_low": "hold",
    "risk_high": "hold",
    "margin_unknown": "hold",
    "margin_level_low": "hold",
    "margin_estimate_thin": "hold",
    "open_risk_unknown": "hold",
    "daily_limit_unset": "hold",
    "daily_limit_untested": "hold",
    "daily_basis_unknown": "hold",
    "max_loss_unset": "hold",
    "max_loss_untested": "hold",
    "max_loss_mode_unknown": "hold",
    "headroom_tight": "hold",
    "volume_capped": "info",
    "margin_estimated": "info",
}


@dataclass
class Flag:
    code: str
    level: str
    params: Dict = field(default_factory=dict)


@dataclass
class Floor:
    name: str
    level: float
    limit: float
    room: float


@dataclass
class Assessment:
    symbol: Symbol
    account: Account
    trade: Trade
    verdict: str
    sizing: Sizing
    open_risk: float
    worst_equity: float
    floors: List[Floor]
    lots_that_fit: Optional[float]
    margin_level: Optional[float]
    flags: List[Flag]


class _Flags(list):
    def add(self, code: str, **params) -> None:
        if all(flag.code != code for flag in self):
            self.append(Flag(code, LEVELS[code], params))


def _spec(symbol: Symbol, account: Account, flags: _Flags) -> None:
    if symbol.profit_currency is None:
        flags.add("spec_unchecked")
        return
    if symbol.profit_currency == account.currency:
        expected = 1.0
    elif account.conversion_rate is not None:
        expected = account.conversion_rate
    else:
        flags.add("spec_unchecked")
        return
    implied = conversion(symbol)
    if abs(implied / expected - 1) > SPEC_TOLERANCE:
        flags.add("spec_inconsistent", implied=implied, expected=expected, currency=account.currency, profit=symbol.profit_currency)


def _costs(symbol: Symbol, account: Account, trade: Trade, sizing: Sizing, flags: _Flags) -> None:
    if symbol.commission_per_lot is None:
        flags.add("commission_unknown")
    if trade.slippage is None:
        flags.add("slippage_unknown")
    if trade.rollovers is None:
        flags.add("hold_unknown")
    elif trade.rollovers > 0 and (symbol.swap_long if trade.side == "buy" else symbol.swap_short) is None:
        flags.add("swap_unknown", side=trade.side)
    if trade.spread is None:
        flags.add("spread_unknown")
    elif trade.spread > SPREAD_SHARE_LIMIT * sizing.distance:
        flags.add("spread_wide", spread=trade.spread, share=trade.spread / sizing.distance)
    if trade.target is None:
        flags.add("no_target")
    elif sizing.r_multiple < MIN_REWARD_RISK:
        flags.add("reward_low", r=sizing.r_multiple, minimum=MIN_REWARD_RISK)
    if account.risk_pct > HIGH_RISK_PCT:
        flags.add("risk_high", risk_pct=account.risk_pct, ceiling=HIGH_RISK_PCT)
    if sizing.below_min:
        flags.add("below_min_volume", volume_min=symbol.volume_min, min_lot_risk_pct=sizing.min_lot_risk_pct, risk_pct=account.risk_pct)
    if sizing.capped:
        flags.add("volume_capped", volume_max=symbol.volume_max)


def _open_risk(symbol: Symbol, account: Account, flags: _Flags) -> float:
    total = 0.0
    for position in account.open_positions:
        if position.risk_to_stop is not None:
            total += position.risk_to_stop
        elif position.stop is None:
            flags.add("open_without_stop", symbol=position.symbol)
        elif position.symbol != symbol.name or position.price_current is None:
            flags.add("open_risk_unknown", symbol=position.symbol)
        else:
            total += position.volume * abs(position.price_current - position.stop) * value_per_unit(symbol)
    return total


def _daily(account: Account, flags: _Flags) -> Optional[tuple]:
    if account.daily_loss_pct is None:
        flags.add("daily_limit_unset")
        return None
    if account.day_start_balance is None:
        flags.add("daily_limit_untested")
        return None
    if account.daily_loss_of is None:
        flags.add("daily_basis_unknown")
    bases = (account.daily_loss_of,) if account.daily_loss_of else DAILY_BASES
    candidates = []
    for basis in bases:
        reference = account.initial_balance if basis == "initial" else account.day_start_balance
        if reference is not None:
            limit = account.daily_loss_pct / 100 * reference
            candidates.append((account.day_start_balance - limit, limit))
    if not candidates:
        flags.add("daily_limit_untested")
        return None
    return max(candidates)


def _overall(account: Account, flags: _Flags) -> Optional[tuple]:
    if account.max_loss_pct is None:
        flags.add("max_loss_unset")
        return None
    if account.initial_balance is None:
        flags.add("max_loss_untested")
        return None
    limit = account.max_loss_pct / 100 * account.initial_balance
    static = account.initial_balance - limit
    trailing = None if account.high_water is None else account.high_water - limit
    if account.max_loss_mode == "static":
        return static, limit
    if account.max_loss_mode == "trailing":
        if trailing is None:
            flags.add("max_loss_untested")
            return static, limit
        return trailing, limit
    flags.add("max_loss_mode_unknown")
    return max(static, trailing if trailing is not None else static), limit


def _margin(account: Account, sizing: Sizing, flags: _Flags) -> Optional[float]:
    used = account.margin_used
    if used is None:
        flags.add("margin_unknown")
        used = 0.0
    if sizing.margin is None:
        flags.add("margin_unknown")
        return None
    free = account.equity - used
    level = account.equity / (used + sizing.margin) * 100 if used + sizing.margin > 0 else None
    if sizing.margin > free:
        flags.add("margin_insufficient", margin=sizing.margin, free=free)
    elif level is not None and level < MARGIN_LEVEL_WARN:
        flags.add("margin_level_low", level=level, warn=MARGIN_LEVEL_WARN)
    if sizing.margin_estimated:
        stressed = sizing.margin * MARGIN_ESTIMATE_FACTOR
        stressed_level = account.equity / (used + stressed) * 100 if used + stressed > 0 else None
        if stressed > free or (stressed_level is not None and stressed_level < MARGIN_LEVEL_WARN):
            flags.add("margin_estimate_thin", factor=MARGIN_ESTIMATE_FACTOR)
        else:
            flags.add("margin_estimated")
    return level


def assess(symbol: Symbol, account: Account, trade: Trade) -> Assessment:
    sizing = size(symbol, account, trade)
    flags = _Flags()
    _spec(symbol, account, flags)
    open_risk = _open_risk(symbol, account, flags)
    _costs(symbol, account, trade, sizing, flags)
    worst = account.equity - open_risk - sizing.risk
    floors = []
    for name, found in (("daily", _daily(account, flags)), ("overall", _overall(account, flags))):
        if found is not None:
            level, limit = found
            floors.append(Floor(name, level, limit, worst - level))
    lots_that_fit = None
    if floors:
        room = min(account.equity - open_risk - item.level for item in floors)
        lots_that_fit = min(round_down(max(room, 0.0) / sizing.loss_per_lot, symbol.volume_step), symbol.volume_max)
        if lots_that_fit < symbol.volume_min:
            lots_that_fit = 0.0
    for item in floors:
        if account.equity <= item.level:
            flags.add("limit_breached", floor=item.name, level=item.level, equity=account.equity)
        elif worst < item.level:
            flags.add("limit_would_breach", floor=item.name, level=item.level, worst=worst, lots_that_fit=lots_that_fit)
        elif item.room < TIGHT_HEADROOM * item.limit:
            flags.add("headroom_tight", floor=item.name, room=item.room, limit=item.limit)
    margin_level = _margin(account, sizing, flags)
    levels = {flag.level for flag in flags}
    verdict = "blocked" if "block" in levels else "review" if "hold" in levels else "go"
    return Assessment(symbol, account, trade, verdict, sizing, open_risk, worst, floors, lots_that_fit, margin_level, list(flags))
