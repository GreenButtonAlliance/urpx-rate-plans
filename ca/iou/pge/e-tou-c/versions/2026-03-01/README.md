# PG&E E-TOU-C — effective 2026-03-01

This filing is the worked example for the conventions in [`/LAYOUT.md`](../../../../../../LAYOUT.md).

## Files

- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_pge_e-tou-c_2026-03-01.jsonld` — URPX serialization (single self-contained file with `@graph`)

The source PDF is **not** committed. Retrieve from the URL in `tariff.toml` and verify against the recorded sha256.

## What's in the JSON-LD

The `@graph` contains:

1. Five `urpx:ProgramEnrollment` instances (`pge:program-care`, `pge:program-fera`, `pge:program-cca`, `pge:program-da`, `pge:program-tbs`) referenced by the eligibility / applicability ConditionExpressions
2. `pge:al-7846-e` — `urpx:TariffPublication` for PG&E Advice Letter 7846-E
3. `pge:e-tou-c` — `urpx:RatePlan` (with nested `urpx:RatePlanVersion`) covering the unbundled energy rates, base services charge, and climate credit
4. `pge:e-tou-c-vintage-pcia` — `urpx:RatePlanModifier` (with nested `urpx:RatePlanModifierVersion`) carrying the 18 vintage-conditional PCIA prices for CCA/DA/TBS customers, linked to (3) via `urpx:applicableToRatePlan`

### Patterns applied (URPX v0.2.0)

- **Income-tier conditional Price** — base services charge expressed as 3 conditional Prices keyed on `urpx:hasProgramEnrollment` (CARE, FERA, neither). Each ApplicabilityGroup carries a `urpx:ConditionExpression`: tiers 1 and 2 use a single `urpx:ComparisonNode` (`urpx:equalsOperator` against `pge:program-care` / `pge:program-fera`); the default tier uses a `urpx:BooleanOperationNode` with `urpx:andOperator` over two `urpx:notEqualsOperator` ComparisonNodes (safe-fallback pattern pending [urpx-org/urpx#9](https://github.com/urpx-org/urpx/issues/9)).
- **Vintage conditional Price** — 18 conditional Prices keyed on `https://example.com/pge/departureVintage`. Each ApplicabilityGroup uses a `urpx:DatatypeOperandNode` with `urpx:integerValue` for the vintage year; native `xsd:gYear` typing pending [urpx-org/urpx#17](https://github.com/urpx-org/urpx/issues/17).

### What's deferred

- **Baseline credit + Conservation Incentive Adjustment** matrix (10 territories × 2 codes × 2 seasons) — tracked in [#2](https://github.com/grid-coordination/urpx-tariffs/issues/2), blocked on upstream [urpx-org/urpx#11](https://github.com/urpx-org/urpx/issues/11) (parameterized matrix-valued tier bounds). One-cell pattern is demonstrated in `../urpx/test-cases/pge-e-tou-c-baseline-tier-2026-03-01/`.
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

This filing is migrated to URPX **v0.2.0-candidate** (`../urpx` on branch `v0.2.0-candidate`). See [#1](https://github.com/grid-coordination/urpx-tariffs/issues/1) for the full migration record. clj-urpx end-to-end resolution previously passed against URPX v0.1.x; re-validation against v0.2.0 is pending clj-urpx v0.2.0 support.
