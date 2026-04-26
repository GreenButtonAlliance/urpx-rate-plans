# PG&E E-TOU-D — effective 2026-03-27

## Files

- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_pge_e-tou-d_2026-03-27.jsonld` — URPX serialization (single self-contained file with `@graph`)

The source PDF is **not** committed. Retrieve from the URL in `tariff.toml` and verify against the recorded sha256.

## What's in the JSON-LD

The `@graph` contains four top-level resources:

1. `pge:program-care` — `urpx:ProgramEnrollment` for CARE
2. `pge:program-fera` — `urpx:ProgramEnrollment` for FERA
3. `pge:e-tou-d` — `urpx:RatePlan` (with nested `urpx:RatePlanVersion`) covering the unbundled energy rates and base services charge
4. `pge:e-tou-d-vintage-pcia` — `urpx:RatePlanModifier` (with nested `urpx:RatePlanModifierVersion`) carrying the 18 vintage-conditional PCIA prices for CCA/DA/TBS customers, linked to (3) via `urpx:applicableToRatePlan`

### How E-TOU-D differs from E-TOU-C

| Feature | E-TOU-C (2026-03-01) | E-TOU-D (2026-03-27) |
|---|---|---|
| Peak window | 4–9 p.m. **all days** | **5–8 p.m. weekdays non-holiday** |
| Peak duration | 5 hours / day, 7 days/week | 3 hours / day, ~5 days/week |
| Baseline credit | yes (territory matrix) | **no** |
| Conservation Incentive Adjustment | yes (within/over baseline) | **no** |
| California Climate Credit | yes (April / October) | **no** |
| Income-tier base charge | yes (CARE / FERA / std) | yes (same values) |
| Vintage PCIA modifier | yes | yes (same values) |
| Bundled energy rates | season + period | same shape, different values |

Holidays defined per the tariff: New Year's Day, Presidents Day, Memorial Day, Independence Day, Labor Day, Veterans Day, Thanksgiving Day, Christmas Day.

### Holiday-on-weekday handling

The "5-8 p.m. peak applies on weekdays except holidays" requirement is expressed via the optional booleans `urpx:includeHolidays` and `urpx:includeNonHolidays` on `urpx:TimeBracket`:

- **Peak** bracket: `dayType: urpx:weekdayDays`, `includeHolidays: false`, `includeNonHolidays: true`
- **Off-peak weekday holiday peak-hours** bracket: `dayType: urpx:weekdayDays`, `includeHolidays: true`, `includeNonHolidays: false` (covers e.g. Independence Day Monday 5–8 p.m.)
- Other off-peak brackets (weekday non-peak hours, weekend) — `dayType` alone suffices.

A consuming application must supply a holiday-date predicate to evaluate these correctly. The data is fidelity-correct against the published tariff.

## Validation

```
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
        -e ../urpx/ontology/urpx-ontology.ttl \
        -df json-ld \
        rate-plan_pge_e-tou-d_2026-03-27.jsonld
# Conforms: True
```

### End-to-end resolution check

clj-urpx (`../clj-urpx`) loads, coerces, and resolves prices correctly when supplied with a PG&E 2026 holiday predicate. Spot-checked: weekday-non-holiday peak hours → Peak; weekend → Off-Peak; holiday-on-weekday peak hours (Memorial Day Mon, Christmas Fri) → Off-Peak.
