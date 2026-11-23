"""A gap in a record must never be what lets a trade through.

Every optional field is dropped in turn from a few hundred generated records, and every pair of fields
from a smaller sample, including the fields of open positions. A drop may stop the record from parsing,
or leave the verdict where it was, or lower it; it must never turn a review or a block into a go.

One assumption is stated rather than tested: where the record gives the terminal's margin per lot, it is
drawn from half to MARGIN_ESTIMATE_FACTOR times the leverage estimate. The engine trusts an estimate only
when that multiple of it still clears, so a broker margin further above the estimate than that is outside
what dropping `margin_per_lot` is promised to survive.
"""

import random
from itertools import combinations

import pytest

from property_scout.fields import InputError
from trade_desk.account import REQUIRED as ACCOUNT_REQUIRED
from trade_desk.account import Account
from trade_desk.guard import MARGIN_ESTIMATE_FACTOR, MARGIN_LEVEL_WARN, TIGHT_HEADROOM, assess
from trade_desk.spec import REQUIRED as SYMBOL_REQUIRED
from trade_desk.spec import Symbol
from trade_desk.trade import REQUIRED as TRADE_REQUIRED
from trade_desk.trade import Trade

RECORDS = 300
PAIRED_RECORDS = 60
POSITION_OPTIONAL = ("price_current", "stop", "risk_to_stop")


def generated(rng):
    in_euros = rng.random() < 0.25
    rate = round(rng.uniform(0.84, 0.95), 4) if in_euros else 1.0
    contract, tick = 100, 0.01
    step = rng.choice([0.01, 0.01, 0.01, 0.1])
    symbol = {
        "name": "XAUUSD",
        "digits": 2,
        "contract_size": contract,
        "tick_size": tick,
        "tick_value": round(contract * tick * rate * rng.uniform(0.995, 1.005), 6),
        "volume_min": step,
        "volume_step": step,
        "volume_max": rng.choice([round(step * 5, 2), 1, 100]),
        "profit_currency": "USD",
        "commission_per_lot": rng.choice([0, 3.5, 7, 12]),
        "swap_long": round(rng.uniform(-90, 10), 2),
        "swap_short": round(rng.uniform(-30, 40), 2),
    }
    balance = round(rng.choice([2_000, 10_000, 25_000, 50_000, 100_000]) * rng.uniform(0.9, 1.1), 2)
    initial = round(balance * rng.uniform(0.92, 1.08), 2)
    day_start = round(balance * rng.uniform(0.98, 1.03), 2)
    daily_pct = rng.choice([2, 3, 4, 5])
    near_the_line = rng.random() < 0.3
    if near_the_line:
        equity = round(day_start * (1 - daily_pct / 100 * rng.uniform(0.75, 1.02)), 2)
    else:
        equity = round(day_start * rng.uniform(0.995, 1.04), 2)
    entry = round(rng.uniform(4_000, 4_800), 2)
    side = rng.choice(["buy", "sell"])
    distance = round(rng.uniform(2, 40), 2)
    sign = 1 if side == "buy" else -1
    leverage = rng.choice([10, 30, 100, 100, 500])
    positions = []
    for _ in range(rng.choice([0, 0, 1, 2])):
        if rng.random() < 0.6:
            price = round(entry + rng.uniform(-15, 15), 2)
            held = rng.choice(["buy", "sell"])
            gap = round(rng.uniform(1, 25), 2)
            positions.append({
                "symbol": "XAUUSD", "side": held, "volume": rng.choice([0.01, 0.05, 0.2, 1]),
                "price_current": price, "stop": round(price - gap if held == "buy" else price + gap, 2),
            })
        else:
            positions.append({"symbol": "EURUSD", "side": "sell", "volume": 0.5, "risk_to_stop": round(rng.uniform(5, 300), 2)})
    account = {
        "currency": "EUR" if in_euros else "USD",
        "balance": balance,
        "equity": equity,
        "risk_pct": rng.choice([0.25, 0.5, 0.5, 1, 1, 1.5, 2, 2.5, 4]),
        "leverage": leverage,
        "margin_used": round(rng.uniform(0, 0.3) * equity, 2) if positions else 0,
        "open_positions": positions,
        "daily_loss_pct": daily_pct,
        "daily_loss_of": rng.choice(["initial", "day_start"]),
        "day_start_balance": day_start,
        "max_loss_pct": rng.choice([6, 8, 10, 12]),
        "max_loss_mode": rng.choice(["static", "trailing"]),
        "initial_balance": initial,
        "high_water": round(max(initial, balance) * rng.uniform(1, 1.04), 2),
    }
    if in_euros:
        account["conversion_rate"] = rate
    if rng.random() < 0.5:
        estimate = contract * entry * rate / leverage
        symbol["margin_per_lot"] = round(estimate * rng.uniform(0.5, MARGIN_ESTIMATE_FACTOR), 2)
    trade = {
        "symbol": "XAUUSD",
        "side": side,
        "entry": entry,
        "stop": round(entry - sign * distance, 2),
        "target": round(entry + sign * distance * rng.choice([0.5, 0.9, 1.5, 2, 2.5, 3]), 2),
        "spread": round(rng.choice([rng.uniform(0.1, 0.6), rng.uniform(0.1, 0.6), rng.uniform(0.5, 4)]), 2),
        "slippage": rng.choice([0, 0.2, 0.5]),
        "rollovers": rng.choice([0, 0, 1, 3]),
        "note": "generated",
    }
    return symbol, account, trade


def verdict(symbol, account, trade):
    try:
        return assess(Symbol.from_dict(symbol), Account.from_dict(account), Trade.from_dict(trade))
    except InputError:
        return None


def drops(symbol, account, trade):
    """Every optional field of a record, as (label, function that returns the three records without it)."""
    found = []
    for name, record, required in (("symbol", symbol, SYMBOL_REQUIRED), ("account", account, ACCOUNT_REQUIRED), ("trade", trade, TRADE_REQUIRED)):
        for field in record:
            if field not in required:
                found.append((f"{name}.{field}", (name, field, None)))
    for index, position in enumerate(account["open_positions"]):
        for field in POSITION_OPTIONAL:
            if field in position:
                found.append((f"account.open_positions[{index}].{field}", ("account", field, index)))
    return found


def without(records, cuts):
    symbol, account, trade = (dict(record) for record in records)
    account["open_positions"] = [dict(position) for position in account["open_positions"]]
    chosen = {"symbol": symbol, "account": account, "trade": trade}
    for name, field, index in cuts:
        if index is None:
            chosen[name].pop(field, None)
        else:
            chosen[name]["open_positions"][index].pop(field, None)
    return symbol, account, trade


def generated_records(count, seed):
    rng = random.Random(seed)
    return [generated(rng) for _ in range(count)]


def test_the_generator_reaches_every_verdict():
    seen = {}
    for records in generated_records(RECORDS, 7):
        result = verdict(*records)
        assert result is not None
        seen[result.verdict] = seen.get(result.verdict, 0) + 1
    assert set(seen) == {"go", "review", "blocked"}
    assert min(seen.values()) >= 20, seen


def test_dropping_one_field_never_lets_a_trade_through():
    lifted = []
    for number, records in enumerate(generated_records(RECORDS, 7)):
        before = verdict(*records).verdict
        if before == "go":
            continue
        for label, cut in drops(*records):
            after = verdict(*without(records, [cut]))
            if after is not None and after.verdict == "go":
                lifted.append(f"record {number}: dropping {label} turned {before} into go")
    assert lifted == []


def test_dropping_two_fields_never_lets_a_trade_through():
    lifted = []
    for number, records in enumerate(generated_records(PAIRED_RECORDS, 11)):
        before = verdict(*records).verdict
        if before == "go":
            continue
        for (first, a), (second, b) in combinations(drops(*records), 2):
            after = verdict(*without(records, [a, b]))
            if after is not None and after.verdict == "go":
                lifted.append(f"record {number}: dropping {first} and {second} turned {before} into go")
    assert lifted == []


def test_every_optional_field_is_dropped_somewhere():
    labels = {label.split(".")[-1] for records in generated_records(RECORDS, 7) for label, _ in drops(*records)}
    optional = (
        set(Symbol.__dataclass_fields__) - set(SYMBOL_REQUIRED)
        | set(Account.__dataclass_fields__) - set(ACCOUNT_REQUIRED)
        | set(Trade.__dataclass_fields__) - set(TRADE_REQUIRED)
        | set(POSITION_OPTIONAL)
    )
    assert optional <= labels


@pytest.mark.parametrize("seed", [7, 11, 13])
def test_a_go_keeps_every_promise(seed):
    for records in generated_records(RECORDS, seed):
        result = verdict(*records)
        sizing = result.sizing
        assert sizing.risk <= sizing.budget * (1 + 1e-9)
        if result.verdict != "go":
            continue
        assert sizing.lots >= records[0]["volume_min"]
        assert result.floors, "a go needs both loss limits computed"
        for item in result.floors:
            assert result.worst_equity >= item.level
            assert item.room >= TIGHT_HEADROOM * item.limit
        assert sizing.margin is not None and result.margin_level >= MARGIN_LEVEL_WARN
