"""Lot size: the most volume whose loss at the stop, costs included, stays inside the risk budget."""

import math
from dataclasses import dataclass
from typing import Optional

from .account import Account
from .spec import Symbol
from .trade import Trade, TradeError

# Absorbs float noise such as 0.7 / 0.1 = 6.999999999999999 without rounding a real shortfall up.
STEP_EPSILON = 1e-9


@dataclass
class Sizing:
    base: float
    budget: float
    distance: float
    value_per_unit: float
    costs_per_lot: float
    loss_per_lot: float
    reward_per_lot: Optional[float]
    lots_raw: float
    lots: float
    risk: float
    risk_pct: float
    reward: Optional[float]
    r_multiple: Optional[float]
    breakeven_win_rate: Optional[float]
    min_lot_risk_pct: float
    below_min: bool
    capped: bool
    margin_per_lot: Optional[float]
    margin: Optional[float]
    margin_estimated: bool


def round_down(volume: float, step: float) -> float:
    return round(max(math.floor(volume / step + STEP_EPSILON), 0) * step, 8)


def value_per_unit(symbol: Symbol) -> float:
    """Account money gained or lost per lot when the price moves by 1.0."""
    return symbol.tick_value / symbol.tick_size


def conversion(symbol: Symbol) -> float:
    """The rate from profit currency to account currency that the reported tick value implies."""
    return symbol.tick_value / (symbol.contract_size * symbol.tick_size)


def swap_charge(symbol: Symbol, trade: Trade) -> float:
    """What holding one lot costs in swaps. A credit is not counted: it can change before the trade closes."""
    if not trade.rollovers:
        return 0.0
    swap = symbol.swap_long if trade.side == "buy" else symbol.swap_short
    if swap is None or swap >= 0:
        return 0.0
    return trade.rollovers * -swap


def margin_for_one_lot(symbol: Symbol, account: Account, price: float) -> Optional[float]:
    if symbol.margin_per_lot is not None:
        return symbol.margin_per_lot
    if account.leverage is None:
        return None
    return symbol.contract_size * price * conversion(symbol) / account.leverage


def size(symbol: Symbol, account: Account, trade: Trade) -> Sizing:
    if trade.symbol != symbol.name:
        raise TradeError(f"trade: symbol is {trade.symbol!r} but the specification is for {symbol.name!r}")
    base = min(account.balance, account.equity)
    budget = base * account.risk_pct / 100
    distance = abs(trade.entry - trade.stop)
    per_unit = value_per_unit(symbol)
    costs = (symbol.commission_per_lot or 0.0) + swap_charge(symbol, trade)
    loss_per_lot = (distance + (trade.slippage or 0.0)) * per_unit + costs
    lots_raw = budget / loss_per_lot
    lots = round_down(lots_raw, symbol.volume_step)
    capped = lots > symbol.volume_max
    if capped:
        lots = symbol.volume_max
    below_min = lots < symbol.volume_min
    if below_min:
        lots = 0.0
    reward_per_lot = None if trade.target is None else abs(trade.target - trade.entry) * per_unit - costs
    r_multiple = None if reward_per_lot is None else reward_per_lot / loss_per_lot
    per_lot_margin = margin_for_one_lot(symbol, account, trade.entry)
    return Sizing(
        base=base,
        budget=budget,
        distance=distance,
        value_per_unit=per_unit,
        costs_per_lot=costs,
        loss_per_lot=loss_per_lot,
        reward_per_lot=reward_per_lot,
        lots_raw=lots_raw,
        lots=lots,
        risk=lots * loss_per_lot,
        risk_pct=lots * loss_per_lot / base * 100,
        reward=None if reward_per_lot is None else lots * reward_per_lot,
        r_multiple=r_multiple,
        breakeven_win_rate=1 / (1 + r_multiple) if r_multiple is not None and r_multiple > 0 else None,
        min_lot_risk_pct=symbol.volume_min * loss_per_lot / base * 100,
        below_min=below_min,
        capped=capped,
        margin_per_lot=per_lot_margin,
        margin=None if per_lot_margin is None else lots * per_lot_margin,
        margin_estimated=symbol.margin_per_lot is None and per_lot_margin is not None,
    )
