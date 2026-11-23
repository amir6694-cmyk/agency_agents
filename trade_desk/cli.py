"""Command-line interface for the trade desk engine.

Usage examples:
    python -m trade_desk template symbol > symbol.json
    python -m trade_desk check --symbol symbol.json --account account.json --trade trade.json --format md
    python -m trade_desk size --symbol symbol.json --equity 10000 --risk 0.5 --side buy --entry 4452.30 --stop 4440.30
    python -m trade_desk atr --candles candles.json --period 14 --multiple 1.5 --side buy --entry 4452.30 --tick-size 0.01
    python -m trade_desk journal --trades closed.json --start-balance 10000 --format md
"""

import argparse
import json
import sys
from dataclasses import asdict
from typing import Any, List, Optional

from property_scout.cli import _emit, _read_json
from property_scout.fields import InputError

from .account import Account
from .atr import DEFAULT_PERIOD, METHODS, CandleError, atr, atr_stop, candles_from
from .guard import assess
from .journal import ClosedTrade, JournalError, review, trades_from
from .report import journal_data, journal_markdown, to_data, to_markdown
from .sizing import size
from .spec import Symbol
from .trade import SIDES, Trade

SYMBOL_TEMPLATE = asdict(
    Symbol(
        name="XAUUSD",
        digits=2,
        contract_size=100,
        tick_size=0.01,
        tick_value=1.0,
        volume_min=0.01,
        volume_step=0.01,
        volume_max=100,
        profit_currency="USD",
        commission_per_lot=7.0,
        swap_long=-50.0,
        swap_short=25.0,
        margin_per_lot=None,
    )
)

ACCOUNT_TEMPLATE = asdict(
    Account(
        currency="USD",
        balance=10_000,
        equity=10_000,
        risk_pct=0.5,
        open_positions=[],
        leverage=100,
        margin_used=0,
        conversion_rate=None,
        daily_loss_pct=5,
        daily_loss_of="initial",
        day_start_balance=10_000,
        max_loss_pct=10,
        max_loss_mode="static",
        initial_balance=10_000,
        high_water=None,
    )
)

TRADE_TEMPLATE = asdict(
    Trade(
        symbol="XAUUSD",
        side="buy",
        entry=4452.30,
        stop=4440.30,
        target=4476.30,
        spread=0.25,
        slippage=0.0,
        rollovers=0,
        note="Example: retest of the London high, stop below the 1-hour swing low",
    )
)

JOURNAL_TEMPLATE = [
    asdict(ClosedTrade(closed="2026-11-17T09:42:00+00:00", side="buy", profit=96.4, volume=0.04, risk=48.3, symbol="XAUUSD", opened="2026-11-17T08:15:00+00:00")),
    asdict(ClosedTrade(closed="2026-11-17T15:05:00+00:00", side="sell", profit=-48.3, volume=0.04, risk=48.3, symbol="XAUUSD", opened="2026-11-17T14:31:00+00:00")),
    asdict(ClosedTrade(closed="2026-11-18T10:20:00+00:00", side="buy", profit=-49.1, volume=0.05, risk=49.1, symbol="XAUUSD", opened="2026-11-18T09:02:00+00:00")),
    asdict(ClosedTrade(closed="2026-11-18T16:44:00+00:00", side="buy", profit=121.0, volume=0.05, risk=49.1, symbol="XAUUSD", opened="2026-11-18T14:30:00+00:00")),
    asdict(ClosedTrade(closed="2026-11-19T13:58:00+00:00", side="sell", profit=-7.0, volume=0.04, risk=48.3, symbol="XAUUSD", opened="2026-11-19T13:30:00+00:00")),
    asdict(ClosedTrade(closed="2026-11-20T11:12:00+00:00", side="buy", profit=72.5, volume=0.04, risk=48.3, symbol="XAUUSD", opened="2026-11-20T08:47:00+00:00")),
]

CANDLES_TEMPLATE = [
    {"time": "2026-11-23 00:00", "open": 4438.2, "high": 4440.41, "low": 4431.45, "close": 4433.69},
    {"time": "2026-11-23 01:00", "open": 4433.69, "high": 4439.21, "low": 4432.49, "close": 4438.44},
    {"time": "2026-11-23 02:00", "open": 4438.44, "high": 4442.35, "low": 4435.22, "close": 4439.95},
    {"time": "2026-11-23 03:00", "open": 4439.95, "high": 4443.83, "low": 4436.78, "close": 4440.8},
    {"time": "2026-11-23 04:00", "open": 4440.8, "high": 4446.7, "low": 4439.54, "close": 4444.19},
    {"time": "2026-11-23 05:00", "open": 4444.19, "high": 4446.67, "low": 4440.85, "close": 4445.87},
    {"time": "2026-11-23 06:00", "open": 4445.87, "high": 4449.2, "low": 4442.62, "close": 4445.49},
    {"time": "2026-11-23 07:00", "open": 4445.49, "high": 4449.14, "low": 4444.18, "close": 4447.98},
    {"time": "2026-11-23 08:00", "open": 4447.98, "high": 4457.98, "low": 4444.68, "close": 4454.23},
    {"time": "2026-11-23 09:00", "open": 4454.23, "high": 4462.98, "low": 4453.56, "close": 4460.73},
    {"time": "2026-11-23 10:00", "open": 4460.73, "high": 4463.14, "low": 4457.53, "close": 4458.98},
    {"time": "2026-11-23 11:00", "open": 4458.98, "high": 4462.54, "low": 4455.77, "close": 4458.7},
    {"time": "2026-11-23 12:00", "open": 4458.7, "high": 4460.41, "low": 4455.74, "close": 4459.92},
    {"time": "2026-11-23 13:00", "open": 4459.92, "high": 4461.84, "low": 4456.62, "close": 4458.46},
    {"time": "2026-11-23 14:00", "open": 4458.46, "high": 4461.97, "low": 4457.64, "close": 4459.78},
    {"time": "2026-11-23 15:00", "open": 4459.78, "high": 4463.21, "low": 4457.22, "close": 4460.11},
    {"time": "2026-11-23 16:00", "open": 4460.11, "high": 4463.95, "low": 4458.78, "close": 4460.25},
    {"time": "2026-11-23 17:00", "open": 4460.25, "high": 4463.98, "low": 4457.37, "close": 4459.5},
    {"time": "2026-11-23 18:00", "open": 4459.5, "high": 4460.46, "low": 4458.29, "close": 4459.97},
    {"time": "2026-11-23 19:00", "open": 4459.97, "high": 4460.55, "low": 4452.64, "close": 4455.58},
]

TEMPLATES = {
    "symbol": SYMBOL_TEMPLATE,
    "account": ACCOUNT_TEMPLATE,
    "trade": TRADE_TEMPLATE,
    "journal": JOURNAL_TEMPLATE,
    "candles": CANDLES_TEMPLATE,
}


def _rows(path: str, key: str, error) -> Any:
    rows = _read_json(path)
    if isinstance(rows, dict) and set(rows) == {key}:
        rows = rows[key]
    if not isinstance(rows, list):
        raise error(f"{path} must be a JSON array, or an object with a '{key}' array")
    return rows


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))


def cmd_template(args) -> int:
    _print(TEMPLATES[args.kind])
    return 0


def cmd_check(args) -> int:
    result = assess(
        Symbol.from_dict(_read_json(args.symbol)),
        Account.from_dict(_read_json(args.account)),
        Trade.from_dict(_read_json(args.trade)),
    )
    if args.format == "md":
        text = to_markdown(result)
    else:
        text = json.dumps(to_data(result), indent=2, ensure_ascii=False, allow_nan=False)
    _emit(text, args.out)
    return 0


def cmd_size(args) -> int:
    symbol = Symbol.from_dict(_read_json(args.symbol))
    currency = args.currency or symbol.profit_currency
    if not currency:
        raise InputError("give --currency: the symbol does not state its profit currency")
    account = Account.from_dict({
        "currency": currency,
        "balance": args.balance if args.balance is not None else args.equity,
        "equity": args.equity,
        "risk_pct": args.risk,
        "open_positions": [],
    })
    trade = Trade.from_dict({
        "symbol": symbol.name,
        "side": args.side,
        "entry": args.entry,
        "stop": args.stop,
        "target": args.target,
        "slippage": args.slippage,
        "rollovers": args.rollovers,
    })
    sizing = size(symbol, account, trade)
    if args.json:
        _print({
            "lots": sizing.lots,
            "risk": round(sizing.risk, 2),
            "risk_pct": round(sizing.risk_pct, 4),
            "budget": round(sizing.budget, 2),
            "loss_per_lot": round(sizing.loss_per_lot, 2),
            "costs_per_lot": round(sizing.costs_per_lot, 2),
            "reward": None if sizing.reward is None else round(sizing.reward, 2),
            "r_multiple": None if sizing.r_multiple is None else round(sizing.r_multiple, 4),
            "breakeven_win_rate": None if sizing.breakeven_win_rate is None else round(sizing.breakeven_win_rate, 4),
            "min_lot_risk_pct": round(sizing.min_lot_risk_pct, 4),
            "below_min": sizing.below_min,
            "capped": sizing.capped,
            "currency": currency,
        })
        return 0
    if sizing.below_min:
        print(f"No volume fits: the smallest, {symbol.volume_min:g} lots, would risk {sizing.min_lot_risk_pct:.2f}% of {sizing.base:,.2f} {currency}.")
        return 0
    line = f"{sizing.lots:g} lots risks {sizing.risk:,.2f} {currency} ({sizing.risk_pct:.2f}% of {sizing.base:,.2f})"
    if sizing.r_multiple is not None:
        line += f"; the target pays {sizing.r_multiple:.2f}R after costs"
    print(line + ".")
    if symbol.commission_per_lot is None:
        print("! commission is not stated in the symbol file, so the risk leaves it out")
    print("Run `check` with the account's loss limits and open positions for a verdict.")
    return 0


def cmd_atr(args) -> int:
    if args.multiple is not None and (args.side is None or args.entry is None):
        raise InputError("--multiple needs --side and --entry to place a stop")
    candles = candles_from(_rows(args.candles, "candles", CandleError))
    value = atr(candles, args.period, args.method)
    payload = {
        "atr": round(value, 6),
        "period": args.period,
        "method": args.method,
        "bars": len(candles),
        "last": candles[-1].time.isoformat(),
    }
    if args.multiple is not None:
        payload.update({
            "multiple": args.multiple,
            "side": args.side,
            "entry": args.entry,
            "stop": atr_stop(args.entry, args.side, value, args.multiple, args.tick_size),
        })
    _print(payload)
    return 0


def cmd_journal(args) -> int:
    stats = review(trades_from(_rows(args.trades, "trades", JournalError)), args.start_balance)
    if args.format == "md":
        print(journal_markdown(stats), end="")
    else:
        _print(journal_data(stats))
    return 0


def _period(value: str) -> int:
    if not (value.isascii() and value.isdigit()) or not 1 <= int(value) <= 1000:
        raise argparse.ArgumentTypeError(f"must be a whole number from 1 to 1000, got {value!r}")
    return int(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trade-desk",
        description="Deterministic position sizing, loss-limit checks and trade review for MetaTrader 5",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("template", help="Print an example symbol, account, trade, journal or candles file")
    p.add_argument("kind", choices=sorted(TEMPLATES))
    p.set_defaults(handler=cmd_template)

    p = sub.add_parser("check", help="Size one trade and judge it against the account's limits: go, review or blocked")
    p.add_argument("--symbol", required=True, help="The symbol's specification, as the terminal reports it")
    p.add_argument("--account", required=True, help="Balance, equity, risk per trade, open positions and loss limits")
    p.add_argument("--trade", required=True, help="Side, entry, stop, target, spread, slippage, rollovers")
    p.add_argument("--format", choices=["json", "md"], default="json")
    p.add_argument("--out", default=None)
    p.set_defaults(handler=cmd_check)

    p = sub.add_parser("size", help="Lot size for one trade from the equity and the risk, with no limits checked")
    p.add_argument("--symbol", required=True)
    p.add_argument("--equity", type=float, required=True)
    p.add_argument("--balance", type=float, default=None, help="Defaults to the equity; risk is a share of the lower")
    p.add_argument("--risk", type=float, required=True, help="Percent of the account to risk, e.g. 0.5")
    p.add_argument("--side", choices=SIDES, required=True)
    p.add_argument("--entry", type=float, required=True)
    p.add_argument("--stop", type=float, required=True)
    p.add_argument("--target", type=float, default=None)
    p.add_argument("--slippage", type=float, default=0.0)
    p.add_argument("--rollovers", type=int, default=0)
    p.add_argument("--currency", default=None, help="Account currency; defaults to the symbol's profit currency")
    p.add_argument("--json", action="store_true")
    p.set_defaults(handler=cmd_size)

    p = sub.add_parser("atr", help="Average true range from candles, and optionally a stop a multiple of it away")
    p.add_argument("--candles", required=True, help="JSON array of {time, open, high, low, close}, oldest first")
    p.add_argument("--period", type=_period, default=DEFAULT_PERIOD)
    p.add_argument("--method", choices=METHODS, default="sma", help="sma matches MetaTrader 5's built-in ATR")
    p.add_argument("--multiple", type=float, default=None)
    p.add_argument("--side", choices=SIDES, default=None)
    p.add_argument("--entry", type=float, default=None)
    p.add_argument("--tick-size", dest="tick_size", type=float, default=None)
    p.set_defaults(handler=cmd_atr)

    p = sub.add_parser("journal", help="Win rate, profit factor, expectancy, drawdown and streaks from closed trades")
    p.add_argument("--trades", required=True, help="JSON array of {closed, side, profit, risk, volume, symbol, opened}")
    p.add_argument("--start-balance", dest="start_balance", type=float, default=None)
    p.add_argument("--format", choices=["json", "md"], default="json")
    p.set_defaults(handler=cmd_journal)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (InputError, OSError, ValueError, ArithmeticError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RecursionError:
        print("error: the input is nested too deeply to be a trading record", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
