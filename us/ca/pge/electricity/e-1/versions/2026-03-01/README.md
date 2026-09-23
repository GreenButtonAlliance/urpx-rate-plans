# PG&E E-1 — effective 2026-03-01

## Files

- `pge_e-1_2026-03-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_pge_e-1_2026-03-01.jsonld` — URPX serialization (single self-contained file with `@graph`)

## What's in the JSON-LD

The `@graph` contains:

1. Five `urpx:ProgramEnrollment` instances (`pge:program-care`, `pge:program-fera`, `pge:program-cca`, `pge:program-da`, `pge:program-tbs`) referenced by the eligibility / applicability ConditionExpressions
2. `pge:al-7846-e` — `urpx:TariffPublication` for PG&E Advice Letter 7846-E
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

Full-matrix expansion is tracked under [#18](https://github.com/grid-coordination/urpx-rate-plans/issues/18) and **is blocked**, on the consumer rather than on the vocabulary.

The vocabulary is not the obstacle, and the data is not either. `sh:maxCount 1` caps `urpx:ProfileAlternatives` containers per `PlanElements`, not dimensions within one, and a container's alternatives are the cross-product of its dimensions; the corpus ships that shape twice, in the E-TOU-C baseline-tier modifier and CPAU E-HRA. All 40 kWh/day values were checked against Sheet 4 of this filing's own PDF on 2026-09-23, against the E-TOU-C overlay's 120 brackets: no disagreements.

What blocks it is that clj-urpx resolves bounds from the first `urpx:ServiceBracket` on a tier and filters by neither season nor `urpx:ProfileAlternative`. This filing carries six tiers holding one bracket each, so winter's correct 11.0 kWh/day is present today as tier 4. Under a three-tier, forty-bracket overlay it would be absent entirely, so completing the data would cost a correct number. Losing a correct number is worse than leaving nineteen cells unmodeled, so this stays as it is until the consumer can select a bracket, tracked by the clj-urpx session as URPX-rng. `tariff.toml` carries the full reasoning and the measurements.

### Code H (all-electric), Code M / S (medical) — not modeled

The tariff publishes additional baseline allowances for all-electric heating customers (Code H) and adds medical allowances (Code M / S) on top of the basic quantities. Only Code B (basic) is modeled here.

### Initial effective date

`urpx:initialEffectiveDate` is set to 2001-01-01 as a placeholder for the post-restructuring modern PG&E E-1 era. The schedule predates this; the exact original effective date should be researched and corrected if available.

## Validation

```
# Run from the urpx-rate-plans project root:
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
 -e ../urpx/ontology/urpx-ontology.ttl \
 -df json-ld \
 us/ca/pge/electricity/e-1/versions/2026-03-01/rate-plan_pge_e-1_2026-03-01.jsonld
# Conforms: True
```

This rate plan is serialized against URPX **v0.5.1** and validates clean against pyshacl + [clj-urpx](https://github.com/grid-coordination/clj-urpx) end-to-end (load → coerce → resolve).
