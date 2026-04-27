# PG&E EV2 — effective 2026-03-27

## Files

- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_pge_ev2_2026-03-27.jsonld` — URPX serialization (single self-contained file with `@graph`)

The source PDF is **not** committed. Retrieve from the URL in `tariff.toml` and verify against the recorded sha256.

## What's in the JSON-LD

The `@graph` contains four top-level resources:

1. `pge:program-care` — `urpx:ProgramEnrollment` for CARE
2. `pge:program-fera` — `urpx:ProgramEnrollment` for FERA
3. `pge:ev2` — `urpx:RatePlan` (with nested `urpx:RatePlanVersion`) covering the unbundled energy rates and base services charge
4. `pge:ev2-vintage-pcia` — `urpx:RatePlanModifier` (with nested `urpx:RatePlanModifierVersion`) carrying the 18 vintage-conditional PCIA prices for CCA/DA/TBS customers, linked to (3) via `urpx:applicableToRatePlan`

### Structure

EV2 is a residential TOU schedule for plug-in EV / battery-storage / electric-heat-pump customers:

| TOU Period | Hours (every day, including weekends and holidays) |
|---|---|
| **Peak** | 16:00–21:00 |
| **Part-Peak** | 15:00–16:00 and 21:00–24:00 |
| **Off-Peak** | 00:00–15:00 |

| | Peak | Part-Peak | Off-Peak |
|---|---:|---:|---:|
| Summer | $0.53809 | $0.42760 | $0.22558 |
| Winter | $0.41099 | $0.39428 | $0.22558 |

Customer-facing name is **EV2-A** (per Sheet 1: "Bills issued under Schedule EV2 will be identified as EV2A").

### Notable simplifications vs. other PG&E residential schedules

EV2 is structurally the simplest of the PG&E residential conversions in this repo:

- **No baseline credit, no Conservation Incentive Adjustment, no baseline territory matrix** — therefore no upstream URPX-#11 deferral.
- **No California Climate Credit** on the rate sheet.
- **All-days TOU** — no weekday-vs-weekend distinction needed; the peak window applies every day including weekends and holidays.
- **Income-tier base services charge** — same three-tier pattern as E-1 / E-TOU-C / E-TOU-D, same values.

## Annual usage cap

Sheet 1 specifies an annual usage cap: customers cannot exceed 800% of their annual baseline allowance over the rolling 12-month window. Violators are defaulted to E-TOU-D and barred from any EV rate schedule for 12 months.

This is modeled as a second `urpx:EligibilityRule` (`pge:er-annual-usage-cap`) on the RatePlanVersion (multiple rules imply AND), with a single `urpx:Condition` carrying:

- `conditionType: "annualUsageCapAsPercentOfBaseline"` (informal)
- `operator: urpx:lessThanOrEqualOperator`
- `conditionValue: "800"`
- `hasMetricSpecification: pge:ms-energy` (kWh)

The `conditionType` string is informal because URPX does not yet provide first-class vocabulary for rolling-window aggregation or percent-of-baseline as a unit of measure. Tracked upstream as `../urpx` **URPX-d9e**; locally as **URPXT-g2y** for the follow-up that tightens this filing once the upstream vocabulary lands. SHACL conforms today; a downstream consumer (e.g. clj-price-server) can read the conditionType + operator + value + description and surface the constraint to a VEN-client over OpenADR 3, which can then act on it given its cumulative usage state.

## Validation

```
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
        -e ../urpx/ontology/urpx-ontology.ttl \
        -df json-ld \
        rate-plan_pge_ev2_2026-03-27.jsonld
# Conforms: True
```

clj-urpx (`../clj-urpx` ≥ 0.3.0) loads, coerces, and resolves prices correctly across all three TOU periods × both seasons. Timezone (`America/Los_Angeles`) is read from `urpx:timezoneIdentifier` on the RatePlan.
