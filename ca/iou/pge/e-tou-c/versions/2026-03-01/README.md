# PG&E E-TOU-C — effective 2026-03-01

This filing is the worked example for the conventions in [`/LAYOUT.md`](../../../../../../LAYOUT.md).

## Files

- `pge_e-tou-c_2026-03-01.pdf` — source PDF (sha256 in `tariff.toml`; PG&E updated the canonical URL in place between our 2026-04-26 retrieval and 2026-04-28 — the committed copy is the original we extracted from)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_pge_e-tou-c_2026-03-01.jsonld` — URPX serialization of the base RatePlan + Vintage-PCIA modifier (single self-contained file with `@graph`)
- `rate-plan-modifier_pge_e-tou-c-baseline-tier_2026-03-01.jsonld` — sibling RatePlanModifier carrying the 40-cell baseline-credit + Conservation Incentive Adjustment matrix (10 territories × 2 codes × 2 seasons), wired via `urpx:applicableToRatePlan` to the base file's `pge:e-tou-c`

## What's in the JSON-LD

The `@graph` contains:

1. Five `urpx:ProgramEnrollment` instances (`pge:program-care`, `pge:program-fera`, `pge:program-cca`, `pge:program-da`, `pge:program-tbs`) referenced by the eligibility / applicability ConditionExpressions
2. `pge:al-7846-e` — `urpx:TariffPublication` for PG&E Advice Letter 7846-E
3. `pge:e-tou-c` — `urpx:RatePlan` (with nested `urpx:RatePlanVersion`) covering the unbundled energy rates, base services charge, and climate credit
4. `pge:e-tou-c-vintage-pcia` — `urpx:RatePlanModifier` (with nested `urpx:RatePlanModifierVersion`) carrying the 18 vintage-conditional PCIA prices for CCA/DA/TBS customers, linked to (3) via `urpx:applicableToRatePlan`

### Patterns applied (URPX v0.2.0)

- **Income-tier base services charge** — `pge:pa-income-tier` `urpx:ProfileAlternatives` with one dimension on `urpx:hasProgramEnrollment` (3 ProfileAlternative entries: CARE, FERA, Standard). The Standard alternative's `urpx:ConditionExpression` uses a `urpx:BooleanOperationNode` (AND of two `notEquals` ComparisonNodes). The 3 BSC `Price`s are wrapped in `pge:psa-bsc-by-income-tier` `urpx:PriceSetAlternatives`, each `PriceSetAlternative` referencing the matching ProfileAlternative.
- **Vintage-PCIA prices** — `pge:pa-departure-vintage` `urpx:ProfileAlternatives` (18 ProfileAlternative entries, one per vintage year 2009–2026). Each PA's `urpx:ConditionExpression` uses a `urpx:CustomOperandNode` with `urpx:customConditionProperty="departureVintage"` on the left and `urpx:gYearValue` on the right. The 18 vintage `Price`s are wrapped in `pge:psa-vpcia-by-vintage`. The synthetic `urpx:dimensionProperty` URI is a workaround pending [urpx-org/urpx#30](https://github.com/urpx-org/urpx/issues/30) (request for `customDimensionProperty` parallel to `customConditionProperty`).

### What's deferred

- **Sheet 4 base-charge unbundling** (Distribution / Public Purpose / Nuclear / NSGC components per income tier) — only the totals are modeled. The 4-component breakdown could be added if downstream consumers need it.
- **Tier 2's affordable-housing qualification path** — only the FERA branch is modeled; tracked upstream as [urpx-org/urpx#10](https://github.com/urpx-org/urpx/issues/10).

## Validation

```
# Run from the urpx-tariffs project root:
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
        -e ../urpx/ontology/urpx-ontology.ttl \
        -df json-ld \
        ca/iou/pge/e-tou-c/versions/2026-03-01/rate-plan_pge_e-tou-c_2026-03-01.jsonld
# Conforms: True
```

This rate plan is serialized against URPX **v0.2.0** and validates clean against pyshacl + [clj-urpx](https://github.com/grid-coordination/clj-urpx) end-to-end (load → coerce → resolve).
