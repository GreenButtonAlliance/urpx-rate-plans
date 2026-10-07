# PG&E E-TOU-C — effective 2026-03-01

This filing is the worked example for the conventions in [`/LAYOUT.md`](../../../../../../LAYOUT.md).

## Files

- `pge_e-tou-c_2026-03-01.pdf` — source PDF (sha256 in `tariff.toml`; PG&E updated the canonical URL in place between our 2026-04-26 retrieval and 2026-04-28 — the committed copy is the original we extracted from)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_pge_e-tou-c_2026-03-01.jsonld` — URPX serialization of the base RatePlan + Vintage-PCIA modifier (single self-contained file with `@graph`)

## What's in the JSON-LD

The `@graph` contains:

1. Five `urpx:ProgramEnrollment` instances (`pge:program-care`, `pge:program-fera`, `pge:program-cca`, `pge:program-da`, `pge:program-tbs`) referenced by the eligibility / applicability ConditionExpressions
2. `pge:al-7846-e` — `urpx:TariffPublication` for PG&E Advice Letter 7846-E
3. `pge:e-tou-c` — `urpx:RatePlan` (with nested `urpx:RatePlanVersion`) covering the unbundled energy rates, the Conservation Incentive Adjustment on the baseline tiers, base services charge, and climate credit
4. `pge:e-tou-c-vintage-pcia` — `urpx:RatePlanModifier` (with nested `urpx:RatePlanModifierVersion`) carrying the 18 vintage-conditional PCIA prices for CCA/DA/TBS customers, linked to (3) via `urpx:applicableToRatePlan`

### Patterns applied

- **Income tier, baseline territory and baseline code**: one `urpx:ProfileAlternatives`, `pge:e-tou-c-2026-03-01-pa-income-territory-code`, over three dimensions: `urpx:hasProgramEnrollment` (CARE, FERA, neither), `baselineTerritory` (P through Z) and `baselineCode` (B, H). Its 60 members are the cells of the cross product, because a version carries one container and clj-urpx selects one member per container. Each cell's condition is an AND of its income-tier comparison (two `notEquals` for the standard tier), its territory and its code. The Base Services Charge is `pge:e-tou-c-2026-03-01-psa-bsc-by-income-tier`, one `PriceSetAlternative` per cell at its income tier's published amount.
- **Baseline tiers**: `pge:e-tou-c-2026-03-01-tiers-baseline` over a kWh MetricInput: Tier 1 to the Special Condition 1 quantity, Tier 2 to four times it, Tier 2 Continued above. Each of the 360 `urpx:ServiceBracket`s names one cell and one season. The Conservation Incentive Adjustment is priced on the three tiers.
- **Vintage-PCIA prices** — `pge:pa-departure-vintage` `urpx:ProfileAlternatives` (18 ProfileAlternative entries, one per vintage year 2009–2026). Each PA's `urpx:ConditionExpression` uses a `urpx:CustomOperandNode` with `urpx:customConditionProperty="departureVintage"` on the left and `urpx:gYearValue` on the right. The 18 vintage `Price`s are wrapped in `pge:psa-vpcia-by-vintage`. The synthetic `urpx:dimensionProperty` URI is a workaround pending [urpx-org/urpx#30](https://github.com/urpx-org/urpx/issues/30) (request for `customDimensionProperty` parallel to `customConditionProperty`).

### What's deferred

- **Sheet 4 base-charge unbundling** (Distribution / Public Purpose / Nuclear / NSGC components per income tier) — only the totals are modeled. The 4-component breakdown could be added if downstream consumers need it.
- **Tier 2's affordable-housing qualification path** — only the FERA branch is modeled; tracked upstream as [urpx-org/urpx#10](https://github.com/urpx-org/urpx/issues/10).

## Validation

```
# Run from the urpx-rate-plans project root:
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
 -e ../urpx/ontology/urpx-ontology.ttl \
 -df json-ld \
 us/ca/pge/electricity/e-tou-c/versions/2026-03-01/rate-plan_pge_e-tou-c_2026-03-01.jsonld
# Conforms: True
```

This rate plan is serialized against URPX **v0.5.1** and validates clean against pyshacl + [clj-urpx](https://github.com/grid-coordination/clj-urpx) end-to-end (load → coerce → resolve).
