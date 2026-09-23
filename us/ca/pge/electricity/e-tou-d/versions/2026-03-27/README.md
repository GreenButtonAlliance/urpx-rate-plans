# PG&E E-TOU-D — effective 2026-03-27

## Files

- `pge_e-tou-d_2026-03-27.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_pge_e-tou-d_2026-03-27.jsonld` — URPX serialization (single self-contained file with `@graph`)

## What's in the JSON-LD

The `@graph` contains:

1. Five `urpx:ProgramEnrollment` instances (`pge:program-care`, `pge:program-fera`, `pge:program-cca`, `pge:program-da`, `pge:program-tbs`) referenced by the eligibility / applicability ConditionExpressions
2. `pge:rc-d-26-03-013` — `urpx:RateCase` for CPUC Decision D.26-03-013
3. `pge:al-7869-e` — `urpx:TariffPublication` for PG&E Advice Letter 7869-E
4. `pge:e-tou-d` — `urpx:RatePlan` (with nested `urpx:RatePlanVersion`) covering the unbundled energy rates and base services charge
5. `pge:e-tou-d-vintage-pcia` — `urpx:RatePlanModifier` (with nested `urpx:RatePlanModifierVersion`) carrying the 18 vintage-conditional PCIA prices for CCA/DA/TBS customers, linked to (4) via `urpx:applicableToRatePlan`

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

### Holiday-on-weekday handling

The "5-8 p.m. peak applies on weekdays except holidays" requirement is expressed via the optional booleans `urpx:includeHolidays` and `urpx:includeNonHolidays` on `urpx:TimeBracket`:

- **Peak** bracket: `dayType: urpx:weekdayDays`, `includeHolidays: false`, `includeNonHolidays: true`
- **Off-peak weekday holiday peak-hours** bracket: `dayType: urpx:weekdayDays`, `includeHolidays: true`, `includeNonHolidays: false` (covers e.g. Independence Day Monday 5–8 p.m.)
- Other off-peak brackets (weekday non-peak hours, weekend) — `dayType` alone suffices.

The eight named PG&E holidays are embedded in the data as a `urpx:HolidayCalendar` (`pge:holidays-e-tou-d`) under `PlanElements`, each `urpx:Holiday` carrying a `holidayName` and a human-readable `holidayRule` (e.g. "Third Monday in February"):

| Holiday | Rule |
|---|---|
| New Year's Day | January 1 (legally observed) |
| President's Day | Third Monday in February |
| Memorial Day | Last Monday in May |
| Independence Day | July 4 (legally observed) |
| Labor Day | First Monday in September |
| Veterans Day | November 11 (legally observed) |
| Thanksgiving Day | Fourth Thursday in November |
| Christmas Day | December 25 (legally observed) |

A consuming application that recognizes these rule strings (or maps them to dates) can evaluate the bracket-level `includeHolidays` / `includeNonHolidays` correctly without external configuration. clj-urpx ≤ 0.3.0 still requires a runtime `:holiday?` predicate (it doesn't yet read the embedded calendar) — surfacing this calendar from the data is a follow-up clj-urpx enhancement.

## Validation

```
# Run from the urpx-rate-plans project root:
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
 -e ../urpx/ontology/urpx-ontology.ttl \
 -df json-ld \
 us/ca/pge/electricity/e-tou-d/versions/2026-03-27/rate-plan_pge_e-tou-d_2026-03-27.jsonld
# Conforms: True
```

This rate plan is serialized against URPX **v0.5.1** and validates clean against pyshacl + [clj-urpx](https://github.com/grid-coordination/clj-urpx) end-to-end (load → coerce → resolve).
