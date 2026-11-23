"""Example records shared by the trade_desk tests.

One clean gold trade on a 10,000 USD account with prop-style limits, which the engine should pass.
Buy XAUUSD at 4452.30, stop 4440.30 (12.00 away), target 4476.30 (24.00 away). A 1.00 move on one
lot of 100 oz is worth 100 USD, so one lot loses 1,200 USD plus 7 USD commission at the stop. Half a
percent of 10,000 is 50 USD, which buys 0.04 lots (0.0414 rounded down to the 0.01 step).
"""

SYMBOL = {
    "name": "XAUUSD",
    "digits": 2,
    "contract_size": 100,
    "tick_size": 0.01,
    "tick_value": 1.0,
    "volume_min": 0.01,
    "volume_step": 0.01,
    "volume_max": 100,
    "profit_currency": "USD",
    "commission_per_lot": 7.0,
    "swap_long": -50.0,
    "swap_short": 25.0,
}

ACCOUNT = {
    "currency": "USD",
    "balance": 10_000,
    "equity": 10_000,
    "risk_pct": 0.5,
    "leverage": 100,
    "margin_used": 0,
    "open_positions": [],
    "daily_loss_pct": 5,
    "daily_loss_of": "initial",
    "day_start_balance": 10_000,
    "max_loss_pct": 10,
    "max_loss_mode": "static",
    "initial_balance": 10_000,
}

TRADE = {
    "symbol": "XAUUSD",
    "side": "buy",
    "entry": 4452.30,
    "stop": 4440.30,
    "target": 4476.30,
    "spread": 0.25,
    "slippage": 0.0,
    "rollovers": 0,
}


DROP = object()


def merged(base, overrides):
    data = dict(base)
    for key, value in overrides.items():
        if value is DROP:
            data.pop(key, None)
        else:
            data[key] = value
    return data
