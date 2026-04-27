# PG&E E-1 — effective 2026-03-01

## Files

- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_pge_e-1_2026-03-01.jsonld` — URPX serialization (single self-contained file with `@graph`)

The source PDF is **not** committed. Retrieve from the URL in `tariff.toml` and verify against the recorded sha256.

## What's in the JSON-LD

The `@graph` contains four top-level resources:

1. `pge:program-care` — `urpx:ProgramEnrollment` for CARE
2. `pge:program-fera` — `urpx:ProgramEnrollment` for FERA
3. `pge:e-1` — `urpx:RatePlan` (with nested `urpx:RatePlanVersion`) covering the unbundled energy rates, conservation incentive adjustment by tier, and base services charge
4. `pge:e-1-vintage-pcia` — `urpx:RatePlanModifier` (with nested `urpx:RatePlanModifierVersion`) for the 18 vintage-conditional PCIA prices for CCA/DA/TBS customers, linked via `urpx:applicableToRatePlan`

### Structure

E-1 is **non-TOU**: a single per-kWh Generation rate ($0.12855) and Distribution rate ($0.18042), with the energy rate stratified into three baseline-percentage tiers via a tier-varying Conservation Incentive Adjustment:

| Tier | % of baseline | CIA $/kWh |
|---|---|---:|
| Tier 1 | 0–100% | −$0.04052 |
| Tier 2 | 101–400% | +$0.04089 |
| Tier 2 Continued | over 400% | +$0.04089 |

All other "all usage" components (transmission, public-purpose, wildfire-fund, etc.) match the values used across PG&E residential schedules.

## Known limitations

### Baseline matrix — one cell modeled (Territory P, Code B)

The tier *boundaries* (in absolute kWh/day) come from a 10-territory × 2-code × 2-season matrix. This file models **one cell** — Territory P, Code B residential, summer 13.5 kWh/day / winter 11.0 kWh/day. The file is correct for Territory-P/Code-B customers and incorrect (wrong tier boundaries) for everyone else.

Full-matrix expansion is blocked on upstream [urpx-org/urpx#11](https://github.com/urpx-org/urpx/issues/11) (parameterized matrix-valued tier bounds). Tracked locally in **URPXT-xqu**, under umbrella **URPXT-cww**.

### Code H (all-electric), Code M / S (medical) — not modeled

The tariff publishes additional baseline allowances for all-electric heating customers (Code H) and adds medical allowances (Code M / S) on top of the basic quantities. Only Code B (basic) is modeled here.

### Initial effective date

`urpx:initialEffectiveDate` is set to 2001-01-01 as a placeholder for the post-restructuring modern PG&E E-1 era. The schedule predates this; the exact original effective date should be researched and corrected if available.

## Validation

```
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
        -e ../urpx/ontology/urpx-ontology.ttl \
        -df json-ld \
        rate-plan_pge_e-1_2026-03-01.jsonld
# Conforms: True
```

clj-urpx (`../clj-urpx` ≥ 0.3.0) loads, coerces, and resolves prices correctly. The 6 CIA tier-Prices are all surfaced under the `Conservation Incentive Adjustment` ledger so the caller can pick the active one based on cumulative billing-period usage.
