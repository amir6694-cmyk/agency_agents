#!/bin/bash

#
# Bash Validation Script for the trade_desk engine
#
# Following Rule 4: Bash Test Validation for Math/Logic
# Recomputes lot sizes, risk, reward multiples, loss-limit floors, ATR and journal
# statistics with awk, then compares them with what the engine prints.
#
# Run from the project root: bash tests/validation/test_trade_desk_math.sh
#

set -e

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

PASS_COUNT=0
FAIL_COUNT=0

check() {
    local name="$1" expected="$2" actual="$3" tolerance="${4:-0.005}"
    if awk -v e="$expected" -v a="$actual" -v t="$tolerance" 'BEGIN { d = e - a; if (d < 0) d = -d; exit !(d <= t) }'; then
        echo "PASS  $name: $actual"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "FAIL  $name: expected $expected, engine says $actual"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

field() {
    python3 -c "import json,sys; data = json.load(open('$1')); print(eval('data' + sys.argv[1]))" "$2"
}

# Lots: floor(budget / loss per lot / step) * step, with loss per lot = (stop distance + slippage) * contract * rate + commission + swap charges
lots() {
    awk -v budget="$1" -v loss="$2" -v step="$3" 'BEGIN { n = int(budget / loss / step + 1e-9); printf "%.2f", n * step }'
}

cat > "$WORK/symbol.json" <<'JSON'
{"name": "XAUUSD", "digits": 2, "contract_size": 100, "tick_size": 0.01, "tick_value": 1.0,
 "volume_min": 0.01, "volume_step": 0.01, "volume_max": 100, "profit_currency": "USD",
 "commission_per_lot": 7.0, "swap_long": -50.0, "swap_short": 25.0}
JSON

account() {
    python3 - "$@" > "$WORK/account.json" <<'PY'
import json, sys
data = {"currency": "USD", "balance": 10000, "equity": 10000, "risk_pct": 0.5, "leverage": 100, "margin_used": 0,
        "open_positions": [], "daily_loss_pct": 5, "daily_loss_of": "initial", "day_start_balance": 10000,
        "max_loss_pct": 10, "max_loss_mode": "static", "initial_balance": 10000}
for pair in sys.argv[1:]:
    key, value = pair.split("=", 1)
    data[key] = json.loads(value)
print(json.dumps(data))
PY
}

trade() {
    python3 - "$@" > "$WORK/trade.json" <<'PY'
import json, sys
data = {"symbol": "XAUUSD", "side": "buy", "entry": 4452.30, "stop": 4440.30, "target": 4476.30,
        "spread": 0.25, "slippage": 0.0, "rollovers": 0}
for pair in sys.argv[1:]:
    key, value = pair.split("=", 1)
    data[key] = json.loads(value)
print(json.dumps(data))
PY
}

run_check() {
    python3 -m trade_desk check --symbol "$WORK/symbol.json" --account "$WORK/account.json" --trade "$WORK/trade.json" > "$WORK/out.json"
}

echo "Position size"

# 10,000 at 0.5% is 50. One lot loses 12.00 * 100 + 7 = 1,207 at the stop.
account; trade; run_check
LOSS=$(awk 'BEGIN { print 12.00 * 100 + 7 }')
check "lots, the example" "$(lots 50 "$LOSS" 0.01)" "$(field "$WORK/out.json" "['lots']")" 0
check "risk, the example" "$(awk -v l="$(lots 50 "$LOSS" 0.01)" -v p="$LOSS" 'BEGIN { print l * p }')" "$(field "$WORK/out.json" "['risk']")"
check "reward multiple, the example" "$(awk 'BEGIN { print (24.00 * 100 - 7) / (12.00 * 100 + 7) }')" "$(field "$WORK/out.json" "['r_multiple']")" 0.0001
check "break-even win rate" "$(awk 'BEGIN { r = (24.00 * 100 - 7) / (12.00 * 100 + 7); print 1 / (1 + r) }')" "$(field "$WORK/out.json" "['breakeven_win_rate']")" 0.0001

# Slippage widens the loss; two rollovers at -50 a lot add 100
trade 'slippage=0.3' 'rollovers=2'; run_check
LOSS=$(awk 'BEGIN { print 12.30 * 100 + 7 + 2 * 50 }')
check "lots with slippage and two rollovers" "$(lots 50 "$LOSS" 0.01)" "$(field "$WORK/out.json" "['lots']")" 0
check "loss per lot with slippage and two rollovers" "$LOSS" "$(field "$WORK/out.json" "['loss_per_lot']")"
check "reward multiple counts swaps but not slippage" "$(awk -v l="$LOSS" 'BEGIN { print (24.00 * 100 - 7 - 100) / l }')" "$(field "$WORK/out.json" "['r_multiple']")" 0.0001

# Risk is a share of the lower of balance and equity
account 'equity=9000'; trade; run_check
check "lots on 9,000 of equity" "$(lots 45 1207 0.01)" "$(field "$WORK/out.json" "['lots']")" 0
account 'risk_pct=2'; run_check
check "lots at 2%" "$(lots 200 1207 0.01)" "$(field "$WORK/out.json" "['lots']")" 0

# A sell with a swap credit: the credit is not counted
account; trade 'side="sell"' 'stop=4464.30' 'target=4428.30' 'rollovers=3'; run_check
check "sell loss per lot ignores the swap credit" "1207" "$(field "$WORK/out.json" "['loss_per_lot']")"

# A euro account: tick value 0.86 euro, so a 1.00 move is 86 euro a lot
python3 -c "import json; d = json.load(open('$WORK/symbol.json')); d['tick_value'] = 0.86; json.dump(d, open('$WORK/symbol_eur.json', 'w'))"
cp "$WORK/symbol.json" "$WORK/symbol_usd.json"; cp "$WORK/symbol_eur.json" "$WORK/symbol.json"
account 'currency="EUR"' 'conversion_rate=0.86'; trade; run_check
LOSS=$(awk 'BEGIN { print 12.00 * 86 + 7 }')
check "euro account lots" "$(lots 50 "$LOSS" 0.01)" "$(field "$WORK/out.json" "['lots']")" 0
check "euro margin estimate, 1:100" "$(awk -v l="$(lots 50 "$LOSS" 0.01)" 'BEGIN { print l * 100 * 4452.30 * 0.86 / 100 }')" "$(field "$WORK/out.json" "['margin']")"
cp "$WORK/symbol_usd.json" "$WORK/symbol.json"

echo
echo "Loss-limit floors"

# Daily: 5% of the initial 10,000 is 500, anchored at the day start of 10,400
account 'balance=10400' 'equity=10400' 'day_start_balance=10400'; trade; run_check
check "daily floor on the initial balance" "$(awk 'BEGIN { print 10400 - 0.05 * 10000 }')" "$(field "$WORK/out.json" "['floors'][0]['level']")"
account 'balance=10400' 'equity=10400' 'day_start_balance=10400' 'daily_loss_of="day_start"'; run_check
check "daily floor on the day-start balance" "$(awk 'BEGIN { print 10400 * (1 - 0.05) }')" "$(field "$WORK/out.json" "['floors'][0]['level']")"

# Trailing: 10% of 10,000 below a high-water mark of 10,600
account 'max_loss_mode="trailing"' 'high_water=10600'; run_check
check "trailing floor" "$(awk 'BEGIN { print 10600 - 0.10 * 10000 }')" "$(field "$WORK/out.json" "['floors'][1]['level']")"

# Open risk: 0.2 lots long, 10.00 above its stop
account 'open_positions=[{"symbol": "XAUUSD", "side": "buy", "volume": 0.2, "price_current": 4460.0, "stop": 4450.0}]'; run_check
OPEN=$(awk 'BEGIN { print 0.2 * 10.00 * 100 }')
check "open risk" "$OPEN" "$(field "$WORK/out.json" "['open_risk']")"
check "worst-case equity" "$(awk -v o="$OPEN" -v r="$(field "$WORK/out.json" "['risk']")" 'BEGIN { print 10000 - o - r }')" "$(field "$WORK/out.json" "['worst_equity']")"
check "lots that fit the daily floor" "$(lots "$(awk -v o="$OPEN" 'BEGIN { print 10000 - o - 9500 }')" 1207 0.01)" "$(field "$WORK/out.json" "['lots_that_fit']")" 0

echo
echo "Average true range"

cat > "$WORK/candles.json" <<'JSON'
[{"time": "2026-11-20 10:00", "open": 10, "high": 12, "low": 9, "close": 11},
 {"time": "2026-11-20 11:00", "open": 11, "high": 13, "low": 10, "close": 12},
 {"time": "2026-11-20 12:00", "open": 12, "high": 12.5, "low": 8, "close": 9},
 {"time": "2026-11-20 13:00", "open": 9, "high": 10, "low": 7, "close": 9.5},
 {"time": "2026-11-20 14:00", "open": 9.5, "high": 15, "low": 9.5, "close": 14}]
JSON
python3 -m trade_desk atr --candles "$WORK/candles.json" --period 3 > "$WORK/atr.json"
TR=$(awk 'BEGIN { split("12 13 12.5 10 15", h); split("9 10 8 7 9.5", l); split("11 12 9 9.5 14", c);
    for (i = 2; i <= 5; i++) { hi = h[i] > c[i-1] ? h[i] : c[i-1]; lo = l[i] < c[i-1] ? l[i] : c[i-1]; printf "%s ", hi - lo } }')
check "ATR(3), simple average" "$(echo "$TR" | awk '{ print ($2 + $3 + $4) / 3 }')" "$(field "$WORK/atr.json" "['atr']")" 0.0001
python3 -m trade_desk atr --candles "$WORK/candles.json" --period 3 --method wilder > "$WORK/atr.json"
check "ATR(3), Wilder" "$(echo "$TR" | awk '{ a = ($1 + $2 + $3) / 3; print (a * 2 + $4) / 3 }')" "$(field "$WORK/atr.json" "['atr']")" 0.0001

echo
echo "Journal"

cat > "$WORK/journal.json" <<'JSON'
[{"closed": "2026-11-17T09:10:00Z", "side": "buy", "profit": 100, "risk": 50},
 {"closed": "2026-11-17T14:40:00Z", "side": "sell", "profit": -50, "risk": 50},
 {"closed": "2026-11-18T10:05:00Z", "side": "sell", "profit": -50, "risk": 50},
 {"closed": "2026-11-18T15:30:00Z", "side": "buy", "profit": 200, "risk": 50},
 {"closed": "2026-11-19T08:00:00Z", "side": "buy", "profit": 0},
 {"closed": "2026-11-19T16:45:00Z", "side": "sell", "profit": -30, "risk": 30}]
JSON
python3 -m trade_desk journal --trades "$WORK/journal.json" --start-balance 1000 > "$WORK/journal_out.json"
check "profit factor" "$(awk 'BEGIN { print 300 / 130 }')" "$(field "$WORK/journal_out.json" "['profit_factor']")" 0.0001
check "expectancy" "$(awk 'BEGIN { print 170 / 6 }')" "$(field "$WORK/journal_out.json" "['expectancy']")"
check "expectancy in R" "$(awk 'BEGIN { print (2 - 1 - 1 + 4 - 1) / 5 }')" "$(field "$WORK/journal_out.json" "['expectancy_r']")" 0.0001
check "largest drawdown" "100" "$(field "$WORK/journal_out.json" "['max_drawdown']")"
check "largest drawdown, share of the peak" "$(awk 'BEGIN { print 100 / 1100 * 100 }')" "$(field "$WORK/journal_out.json" "['max_drawdown_pct']")" 0.0001

echo
echo "passed: $PASS_COUNT, failed: $FAIL_COUNT"
[ "$FAIL_COUNT" -eq 0 ]
