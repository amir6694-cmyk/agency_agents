#!/bin/bash

#
# Bash Validation Script for the property_scout engine
#
# Following Rule 4: Bash Test Validation for Math/Logic
# Recomputes costs, payment-plan value, yields and scores with awk from the
# published fee schedules and the rubric, then compares with what the engine prints.
#
# Run from the project root: bash tests/validation/test_property_scout_math.sh
#

set -e

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

PASS_COUNT=0
FAIL_COUNT=0

check() {
    local name="$1" expected="$2" actual="$3" tolerance="${4:-0.5}"
    if awk -v e="$expected" -v a="$actual" -v t="$tolerance" 'BEGIN { d = e - a; if (d < 0) d = -d; exit !(d <= t) }'; then
        echo "PASS  $name: $actual"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "FAIL  $name: expected $expected, engine says $actual"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

costs_field() {
    local field="$1"; shift
    python3 -m property_scout costs --json "$@" | python3 -c "import json,sys; print(json.load(sys.stdin)['$field'])"
}

echo "Acquisition costs"

# Dubai: 4% + 520 fixed + trustee 4,000 plus 5% VAT + agency 2% plus 5% VAT
check "Dubai cash resale, AED 2,000,000" \
    "$(awk 'BEGIN { p = 2000000; print p * 0.04 + 520 + 4000 * 1.05 + p * 0.02 * 1.05 }')" \
    "$(costs_field total_costs_aed --price 2000000 --emirate dubai --sale-type resale)"

# Below AED 500,000 the trustee fee is 2,000 plus VAT
check "Dubai cash resale, AED 450,000" \
    "$(awk 'BEGIN { p = 450000; print p * 0.04 + 520 + 2000 * 1.05 + p * 0.02 * 1.05 }')" \
    "$(costs_field total_costs_aed --price 450000 --emirate dubai --sale-type resale)"

# First home: 75% is inside the 80% ceiling. Mortgage registration 0.25% of the loan + 270; fees are not financed
check "Dubai first home at 75%, costs" \
    "$(awk 'BEGIN { p = 2000000; print p * 0.04 + 520 + 4200 + p * 0.021 + p * 0.75 * 0.0025 + 270 }')" \
    "$(costs_field total_costs_aed --price 2000000 --emirate dubai --sale-type resale --financing mortgage --ltv 0.75 --first-home)"
check "Dubai first home at 75%, own funds" \
    "$(awk 'BEGIN { p = 2000000; print p * 0.25 + p * 0.04 + 520 + 4200 + p * 0.021 + p * 0.75 * 0.0025 + 270 }')" \
    "$(costs_field own_funds_aed --price 2000000 --emirate dubai --sale-type resale --financing mortgage --ltv 0.75 --first-home)"

# An investment purchase is capped at 60% whatever is asked for
check "Dubai investor asking 75%, own funds at the 60% ceiling" \
    "$(awk 'BEGIN { p = 2000000; print p * 0.40 + p * 0.04 + 520 + 4200 + p * 0.021 + p * 0.60 * 0.0025 + 270 }')" \
    "$(costs_field own_funds_aed --price 2000000 --emirate dubai --sale-type resale --financing mortgage --ltv 0.75)"

# A first home above AED 5,000,000 is capped at 70%
check "Dubai first home at AED 30,000,000 asking 75%, own funds at the 70% ceiling" \
    "$(awk 'BEGIN { p = 30000000; print p * 0.30 + p * 0.04 + 520 + 4200 + p * 0.021 + p * 0.70 * 0.0025 + 270 }')" \
    "$(costs_field own_funds_aed --price 30000000 --emirate dubai --sale-type resale --financing mortgage --ltv 0.75 --first-home)"

# UAE nationals get five points more on completed property
check "Dubai investor, UAE national, loan share" \
    "0.65" \
    "$(costs_field loan_to_value_used --price 2000000 --emirate dubai --sale-type resale --financing mortgage --ltv 0.9 --nationality uae)" 0.000001

# Bought from the developer: 4% + 20, no trustee, no agency fee, and no loan before handover
check "Dubai off-plan from developer" \
    "$(awk 'BEGIN { print 2000000 * 0.04 + 20 }')" \
    "$(costs_field total_costs_aed --price 2000000 --emirate dubai --completion offplan --sale-type primary --financing mortgage --ltv 0.5)"
check "Dubai off-plan from developer, fee waived" \
    "20" \
    "$(costs_field total_costs_aed --price 2000000 --emirate dubai --completion offplan --sale-type primary --waived)"

# Abu Dhabi: 2% + 875; commission 2% capped at 500,000, plus VAT
check "Abu Dhabi resale, AED 30,000,000 (commission cap)" \
    "$(awk 'BEGIN { p = 30000000; c = p * 0.02; if (c > 500000) c = 500000; print p * 0.02 + 875 + c * 1.05 }')" \
    "$(costs_field total_costs_aed --price 30000000 --emirate abu_dhabi --sale-type resale)"
check "Abu Dhabi off-plan from developer" \
    "$(awk 'BEGIN { print 2000000 * 0.02 + 450 }')" \
    "$(costs_field total_costs_aed --price 2000000 --emirate abu_dhabi --completion offplan --sale-type primary)"
# On the ADGM islands the seller pays the 2%
check "Abu Dhabi, Al Reem Island resale" \
    "$(awk 'BEGIN { p = 2400000; print p + 875 + p * 0.02 * 1.05 }')" \
    "$(costs_field total_outlay_aed --price 2400000 --emirate abu_dhabi --community 'Al Reem Island' --sale-type resale)"
# Mortgage registration 0.1% of the loan + 450 plus VAT
check "Abu Dhabi mortgaged resale" \
    "$(awk 'BEGIN { p = 2000000; print p * 0.02 + 875 + p * 0.021 + p * 0.5 * 0.001 + 450 * 1.05 }')" \
    "$(costs_field total_costs_aed --price 2000000 --emirate abu_dhabi --sale-type resale --financing mortgage --ltv 0.5)"

check "Ras Al Khaimah resale" \
    "$(awk 'BEGIN { print 2000000 * 0.02 + 400 }')" \
    "$(costs_field total_costs_aed --price 2000000 --emirate ras_al_khaimah --sale-type resale)"
check "Sharjah, other nationalities" \
    "$(awk 'BEGIN { print 2000000 * 0.04 + 500 }')" \
    "$(costs_field total_costs_aed --price 2000000 --emirate sharjah --sale-type resale)"
check "Sharjah, GCC national" \
    "$(awk 'BEGIN { print 2000000 * 0.02 + 500 }')" \
    "$(costs_field total_costs_aed --price 2000000 --emirate sharjah --sale-type resale --nationality gcc)"
check "Ajman minimum fee on AED 50,000" \
    "$(awk 'BEGIN { f = 50000 * 0.03; if (f < 3000) f = 3000; print f + 350 }')" \
    "$(costs_field total_costs_aed --price 50000 --emirate ajman --sale-type resale)"
check "Ajman minimum fee on AED 50,000, UAE national" \
    "$(awk 'BEGIN { f = 50000 * 0.02; if (f < 2500) f = 2500; print f + 350 }')" \
    "$(costs_field total_costs_aed --price 50000 --emirate ajman --sale-type resale --nationality uae)"

echo ""
echo "Payment plans, yields and scores"

cat > "$WORK/brief.json" <<'JSON'
{"budget_max": 5000000, "purpose": "yield", "emirates": ["dubai"], "discount_rate": 0.06}
JSON
cat > "$WORK/listings.json" <<'JSON'
[
  {"url": "https://example.com/a", "evidence": "page", "price_aed": 2000000, "emirate": "dubai",
   "community": "Test", "building": "Tower A", "bedrooms": 2, "size_sqft": 1000, "completion": "ready",
   "sale_type": "resale", "annual_rent_aed": 130000, "rent_count": 6, "service_charge_psf": 18,
   "benchmark_psf": 2000, "benchmark_count": 6, "permit_number": "71", "observed_on": "2026-11-19"},
  {"url": "https://example.com/b", "evidence": "page", "price_aed": 1500000, "emirate": "dubai",
   "community": "Test", "building": "Tower B", "bedrooms": 1, "size_sqft": 750, "completion": "offplan",
   "sale_type": "primary", "handover": "2028-11",
   "payment_plan": {"on_booking": 20, "during_construction": 40, "on_handover": 40}},
  {"url": "https://example.com/c", "evidence": "page", "price_aed": 2000000, "emirate": "dubai",
   "community": "Test", "building": "Tower C", "bedrooms": 2, "size_sqft": 1000, "completion": "ready",
   "sale_type": "primary", "payment_plan": {"on_booking": 60, "post_handover": 40}, "post_handover_months": 40},
  {"url": "https://example.com/d", "evidence": "card", "price_aed": 1800000, "emirate": "dubai",
   "community": "Test", "building": "Tower D", "bedrooms": 2, "size_sqft": 1000, "completion": "ready",
   "sale_type": "resale", "annual_rent_aed": 117000, "benchmark_psf": 2000, "benchmark_count": 3,
   "observed_on": "2026-11-12"}
]
JSON
python3 -m property_scout score --brief "$WORK/brief.json" --listings "$WORK/listings.json" --today 2026-11-19 > "$WORK/out.json"

field() {
    python3 -c "
import json, sys
rows = {r['url']: r for r in json.load(open('$WORK/out.json'))['ranked']}
row = rows['https://example.com/$1']
value = row
for key in '$2'.split('.'):
    value = next(c for c in value if c['name'] == key[1:]) if key.startswith('@') else value[key]
print(value)
"
}

# 60% today, 40% in 40 equal monthly instalments, discounted at 6% a year compounded monthly
check "present value of a 60/40 post-handover plan" \
    "$(awk 'BEGIN { r = exp(log(1.06) / 12) - 1; pv = 0.6; for (m = 1; m <= 40; m++) pv += 0.01 / (1 + r) ^ m; print pv }')" \
    "$(field c plan_present_value_ratio)" 0.000001

# 20% today, 40% in 24 equal monthly instalments, 40% at handover in 24 months
check "present value of a 20/40/40 construction plan" \
    "$(awk 'BEGIN { r = exp(log(1.06) / 12) - 1; pv = 0.2; for (m = 1; m <= 24; m++) pv += (0.4 / 24) / (1 + r) ^ m; pv += 0.4 / (1 + r) ^ 24; print pv }')" \
    "$(field b plan_present_value_ratio)" 0.000001

# Due at booking: the first instalment plus the registration fees
check "cash due at booking, off-plan" "$(awk 'BEGIN { p = 1500000; print p * 0.20 + p * 0.04 + 20 }')" "$(field b cash_at_booking_aed)"

check "gross yield" "$(awk 'BEGIN { print 130000 / 2000000 }')" "$(field a gross_yield)" 0.000001

# Net: rent less service charge and 13% of rent, over price plus acquisition costs
check "net yield" \
    "$(awk 'BEGIN { p = 2000000; costs = p * 0.04 + 520 + 4200 + p * 0.021; print (130000 - 18 * 1000 - 0.13 * 130000) / (p + costs) }')" \
    "$(field a net_yield)" 0.000001

# Value: 20% above the benchmark scores 0, 10% below scores 100; level with it is two thirds of the way
check "value score at the benchmark" "$(awk 'BEGIN { print 100 * (0 - 0.20) / (-0.10 - 0.20) }')" "$(field a criteria.@value.score)" 0.06

# On fewer than five sales the score is held halfway to the neutral 50
check "value score 10% below a thin benchmark" "$(awk 'BEGIN { print 50 + (100 - 50) * 0.5 }')" "$(field d criteria.@value.score)" 0.06

# Yield: net yield from 2% (0) to 7.5% (100)
check "yield score" \
    "$(awk 'BEGIN { p = 2000000; costs = p * 0.04 + 520 + 4200 + p * 0.021; n = (130000 - 18000 - 16900) / (p + costs); print 100 * (n - 0.02) / (0.075 - 0.02) }')" \
    "$(field a criteria.@yield.score)" 0.06

# Without a service charge the gross yield less 2.5 points stands in for the net figure
check "yield score from a gross figure" \
    "$(awk 'BEGIN { n = 117000 / 1800000 - 0.025; print 100 * (n - 0.02) / (0.075 - 0.02) }')" \
    "$(field d criteria.@yield.score)" 0.06

# Trust: the share of checks made and passed
check "trust, opened page seen today with a permit" "100" "$(field a criteria.@trust.score)" 0.06
check "trust, card seen a week ago, nothing verified" "$(awk 'BEGIN { print 100 * (0.5 + 0.5 + 0) / 3 }')" "$(field d criteria.@trust.score)" 0.06
check "trust, off-plan page with nothing else checked" "$(awk 'BEGIN { print 100 * (1 + 0 + 0 + 0.2 + 0) / 5 }')" "$(field b criteria.@trust.score)" 0.06

# Terms: a deferral worth 10% of the price scores 100
check "terms score" \
    "$(awk 'BEGIN { r = exp(log(1.06) / 12) - 1; pv = 0.6; for (m = 1; m <= 40; m++) pv += 0.01 / (1 + r) ^ m; print 100 * (1 - pv) / 0.10 }')" \
    "$(field c criteria.@terms.score)" 0.06

# Total for a yield buyer: value 25%, yield 40%, trust 20%; fit and terms do not apply to this resale
check "total score" \
    "$(awk 'BEGIN { p = 2000000; costs = p * 0.04 + 520 + 4200 + p * 0.021; n = (130000 - 18000 - 16900) / (p + costs);
        v = 100 * 0.20 / 0.30; y = 100 * (n - 0.02) / 0.055; print (0.25 * v + 0.40 * y + 0.20 * 100) / 0.85 }')" \
    "$(field a score)" 0.06

# Completeness: value and yield count for half on thin or estimated evidence, trust in full
check "data completeness on thin evidence" "$(awk 'BEGIN { print (0.25 * 0.5 + 0.40 * 0.5 + 0.20) / 0.85 }')" "$(field d completeness)" 0.006

echo ""
echo "passed: $PASS_COUNT, failed: $FAIL_COUNT"
[ "$FAIL_COUNT" -eq 0 ]
