"""Every sentence the engine says about a trade. The guard emits a code and its figures, never prose."""

TEXT = {
    "below_min_volume": (
        "Even the smallest volume, {volume_min:g} lots, would risk {min_lot_risk_pct:.2f}% of the account against a "
        "budget of {risk_pct:g}%: the stop is too far for this budget, so no position fits."
    ),
    "spec_inconsistent": (
        "The tick value implies {implied:.4f} {currency} per {profit} where {expected:.4f} was expected: the "
        "specification does not fit the contract, so any size worked out from it is wrong."
    ),
    "limit_breached": "Equity of {equity:,.2f} is already at or below the {floor} loss floor of {level:,.2f}: no new trade.",
    "limit_would_breach": (
        "If every stop is hit, equity falls to {worst:,.2f}, below the {floor} loss floor of {level:,.2f}; {fit}."
    ),
    "margin_insufficient": "The position needs {margin:,.2f} of margin and only {free:,.2f} is free.",
    "open_without_stop": (
        "An open {symbol} position has no stop, so the account's risk has no ceiling: set its stop before adding a trade."
    ),
    "spec_unchecked": (
        "The tick value could not be checked against the contract: give `profit_currency`, and `conversion_rate` "
        "when the account is in another currency."
    ),
    "commission_unknown": "Commission is not stated, so the risk leaves it out; give 0 if the account pays none.",
    "slippage_unknown": "Slippage is not stated; give 0 for a limit order, or what market orders on this symbol have cost.",
    "hold_unknown": "The holding period is not stated; give `rollovers`, 0 for a trade closed before the daily rollover.",
    "swap_unknown": "The {side} swap is not stated for a trade held through rollover, so the risk leaves the charge out.",
    "spread_unknown": "The spread is not stated, so it cannot be checked against the stop.",
    "spread_wide": "The spread of {spread:g} is {share:.0%} of the stop distance: an ordinary flicker can take the stop out.",
    "no_target": "There is no target, so the reward and the break-even win rate are unknown.",
    "reward_low": "The target pays {r:.2f}R after costs, under {minimum:g}R.",
    "risk_high": "Risk of {risk_pct:g}% per trade is above {ceiling:g}%: a short losing streak takes a large share of the account.",
    "margin_unknown": (
        "Margin cannot be worked out: give the account's `margin_used` and `leverage`, or the terminal's `margin_per_lot`."
    ),
    "margin_level_low": "Margin level after the trade would be {level:,.0f}%, under {warn:g}%.",
    "margin_estimate_thin": (
        "Margin is estimated from the account's leverage, and {factor:g} times the estimate would not clear: read the "
        "margin for this symbol from the terminal."
    ),
    "open_risk_unknown": "The risk of the open {symbol} position cannot be worked out; give its `risk_to_stop`.",
    "daily_limit_unset": "No daily loss limit is set; give `daily_loss_pct`, the firm's or your own.",
    "daily_limit_untested": (
        "The daily loss floor cannot be placed; give `day_start_balance`, and `initial_balance` when the limit is a share of it."
    ),
    "daily_basis_unknown": (
        "It is not stated whether the daily limit is a share of the initial or the day-start balance, so the stricter floor is used."
    ),
    "max_loss_unset": "No overall loss limit is set; give `max_loss_pct`, the firm's or your own.",
    "max_loss_untested": "The overall loss floor cannot be placed; give `initial_balance`, and `high_water` for a trailing limit.",
    "max_loss_mode_unknown": "It is not stated whether the overall limit is static or trailing, so the stricter floor is used.",
    "headroom_tight": "Only {room:,.2f} of the {limit:,.2f} {floor} limit would be left if every stop is hit.",
    "volume_capped": "The size is cut to the broker's largest volume, {volume_max:g} lots.",
    "margin_estimated": "Margin is estimated from the account's leverage; the terminal's figure is more reliable.",
}


def _fit(lots: float) -> str:
    return "no volume fits until the floor resets" if not lots else f"at most {lots:g} lots fit"


def render(flag) -> str:
    params = dict(flag.params)
    if "lots_that_fit" in params:
        params["fit"] = _fit(params["lots_that_fit"])
    return TEXT[flag.code].format(**params)
