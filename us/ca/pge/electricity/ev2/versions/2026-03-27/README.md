# PG&E EV2 — effective 2026-03-27

## Files

- `pge_ev2_2026-03-27.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_pge_ev2_2026-03-27.jsonld` — URPX serialization (single self-contained file with `@graph`)

## What's in the JSON-LD

The `@graph` contains:

1. Five `urpx:ProgramEnrollment` instances (`pge:program-care`, `pge:program-fera`, `pge:program-cca`, `pge:program-da`, `pge:program-tbs`) referenced by the eligibility / applicability ConditionExpressions
2. `pge:rc-d-26-03-013` — `urpx:RateCase` for CPUC Decision D.26-03-013
3. `pge:al-7869-e` — `urpx:TariffPublication` for PG&E Advice Letter 7869-E
4. `pge:ev2` — `urpx:RatePlan` (with nested `urpx:RatePlanVersion`) covering the unbundled energy rates and base services charge
5. `pge:ev2-vintage-pcia` — `urpx:RatePlanModifier` (with nested `urpx:RatePlanModifierVersion`) carrying the 18 vintage-conditional PCIA prices for CCA/DA/TBS customers, linked to (4) via `urpx:applicableToRatePlan`

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

- **No baseline credit, no Conservation Incentive Adjustment, no baseline territory matrix** — therefore no upstream urpx-org/urpx#11 deferral.
- **No California Climate Credit** on the rate sheet.
- **All-days TOU** — no weekday-vs-weekend distinction needed; the peak window applies every day including weekends and holidays.
- **Income-tier base services charge** — same three-tier pattern as E-1 / E-TOU-C / E-TOU-D, same values.

## Annual usage cap

Sheet 1 specifies an annual usage cap: customers cannot exceed 800% of their annual baseline allowance over the rolling 12-month window. Violators are defaulted to E-TOU-D and barred from any EV rate schedule for 12 months.

Modeled as `pge:er-annual-usage-cap` (a third `urpx:EligibilityRule` on the RatePlanVersion alongside `pge:er-residential` and `pge:er-qualifying-equipment`; multiple rules imply AND). Its `urpx:ConditionExpression` is rooted at a `urpx:ComparisonNode` (`urpx:lessThanOrEqualOperator`):

- `urpx:leftOperand`: `urpx:ObjectOperandNode` referencing `pge:mi-energy-annual-rolling`, a `urpx:MetricInput` whose `urpx:MetricSpecification` carries `urpx:unitOfMeasure: urpx:percent`, `urpx:intervalDuration: P1Y` and `urpx:intervalAlignment: urpx:rollingAligned`.
- `urpx:rightOperand`: `urpx:DatatypeOperandNode` with `urpx:integerValue: 800`.

The right-side `800` is a percentage, and the metric says so: `urpx:percent` over a rolling `P1Y` window. What the model does not say is what the percentage is *of*. The denominator is the customer's annual baseline allowance, and URPX names no canonical metric for it, so the rule's `urpx:description` carries that half in prose. Asked upstream at [urpx-org/urpx discussion #38](https://github.com/urpx-org/urpx/discussions/38).

## Validation

```
# Run from the urpx-rate-plans project root:
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
 -e ../urpx/ontology/urpx-ontology.ttl \
 -df json-ld \
 us/ca/pge/electricity/ev2/versions/2026-03-27/rate-plan_pge_ev2_2026-03-27.jsonld
# Conforms: True
```

This rate plan is serialized against URPX **v0.5.1** and validates clean against pyshacl + [clj-urpx](https://github.com/grid-coordination/clj-urpx) end-to-end (load → coerce → resolve).
