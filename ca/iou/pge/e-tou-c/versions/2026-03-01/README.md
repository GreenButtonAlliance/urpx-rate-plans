# PG&E E-TOU-C — effective 2026-03-01

This filing is the worked example for the conventions in [`/LAYOUT.md`](../../../../../../LAYOUT.md).

## Files

- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_pge_e-tou-c_2026-03-01.jsonld` — URPX serialization (single self-contained file with `@graph`)

The source PDF is **not** committed. Retrieve from the URL in `tariff.toml` and verify against the recorded sha256.

## What's in the JSON-LD

The `@graph` contains four top-level resources:

1. `pge:program-care` — `urpx:ProgramEnrollment` for CARE
2. `pge:program-fera` — `urpx:ProgramEnrollment` for FERA
3. `pge:e-tou-c` — `urpx:RatePlan` (with nested `urpx:RatePlanVersion`) covering the unbundled energy rates, base services charge, and climate credit
4. `pge:e-tou-c-vintage-pcia` — `urpx:RatePlanModifier` (with nested `urpx:RatePlanModifierVersion`) carrying the 18 vintage-conditional PCIA prices for CCA/DA/TBS customers, linked to (3) via `urpx:applicableToRatePlan`

### Patterns applied

- **Income-tier conditional Price** (pattern-001 in `../urpx/proposals/`) — base services charge expressed as 3 conditional Prices keyed on `urpx:hasProgramEnrollment` (CARE, FERA, neither). Pattern decided in URPX-y5c.
- **Vintage conditional Price** (pattern-001 at scale) — 18 conditional Prices keyed on the utility-namespaced `pge:departureVintage` (`xsd:gYear`). Pattern decided in URPX-lb6.

### What's deferred

- **Baseline credit + Conservation Incentive Adjustment** matrix (10 territories × 2 codes × 2 seasons) — tracked in beads issue **URPXT-o1i**, blocked on upstream [urpx-org/urpx#11](https://github.com/urpx-org/urpx/issues/11) (parameterized matrix-valued tier bounds). One-cell pattern is demonstrated in `../urpx/test-cases/pge-e-tou-c-baseline-tier-2026-03-01/`.
- **Sheet 4 base-charge unbundling** (Distribution / Public Purpose / Nuclear / NSGC components per income tier) — only the totals are modeled. The 4-component breakdown could be added if downstream consumers need it.
- **Tier 2's affordable-housing qualification path** — only the FERA branch is modeled; tracked upstream as [urpx-org/urpx#10](https://github.com/urpx-org/urpx/issues/10).

## Validation

```
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
        -e ../urpx/ontology/urpx-ontology.ttl \
        -df json-ld \
        rate-plan_pge_e-tou-c_2026-03-01.jsonld
# Conforms: True
```

The file also loads, coerces, and resolves prices via `../clj-urpx` (`urpx.core/load-rate-plan` + `urpx.coerce/coerce-rate-plan` + `urpx.price/resolve-prices`).
