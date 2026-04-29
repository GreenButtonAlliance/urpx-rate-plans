# CPAU E-1 — effective 2025-07-01

City of Palo Alto Utilities (CPAU) Schedule E-1, Residential Electric Service. Tiered non-TOU residential rate plan for single-family dwelling units served by a single meter.

## Files

- `cpau_e-1_2025-07-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_cpau_e-1_2025-07-01.jsonld` — URPX rate-plan serialization (`@graph` with the RatePlan)

## What's in the JSON-LD

The file holds a single top-level `urpx:RatePlan` (`cpau:e-1`) with a nested `urpx:RatePlanVersion` (`cpau:e-1-2025-07-01`).

### Structure

| Component | Tier 1 (≤ 15 kWh/day baseline) | Tier 2 (> 15 kWh/day) |
|---|---|---|
| Commodity (supply ledger) | $0.10373 | $0.13372 |
| Distribution (delivery ledger) | $0.09593 | $0.08968 |
| Public Benefits (bundled ledger) | $0.00604 | $0.00604 |
| **Marginal Tier 1 total** | **$0.20570/kWh** | $0.22944/kWh |
| Customer Charge (per-meter, monthly, on `mi-meter-count`) | $5.15/month | — |

The 15 kWh/day baseline is per-day, prorated by meter-reading days in the billing period.

### Eligibility

`urpx:EligibilityRule` requires three conjoined predicates (`urpx:BooleanOperationNode` with `urpx:andOperator`):

1. `urpx:hasCustomerKind = urpx:residentialKind`
2. `urpx:CustomOperandNode` `dwellingType = "Single-family dwelling"` (custom — no URPX-native dwelling-type vocabulary today)
3. `urpx:CustomOperandNode` `metering = "Separately metered"` (custom)

## Provenance

DCJ-authored. Original v0.1.x conversion contributed to `urpx-org/urpx` via [PR #7](https://github.com/urpx-org/urpx/pull/7) on 2026-03-03; brought home to `urpx-tariffs` and migrated to v0.2.0 on 2026-04-28 from PR head `e8ed4f0` (after Una's same-day SHACL-compliance push).

## Validation

```
# Run from the urpx-tariffs project root:
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
        -e ../urpx/ontology/urpx-ontology.ttl \
        -df json-ld \
        ca/pou/cpau/e-1/versions/2025-07-01/rate-plan_cpau_e-1_2025-07-01.jsonld
# Conforms: True
```

End-to-end via clj-urpx: `clojure -M:validate` (load + coerce + resolve, all clean).

## Modifiers (deferred)

CPAU has three rate-plan modifiers that apply to E-1 — `cpau:e-eec-1` (Export Electricity Compensation), `cpau:e-hra` (Habitat Restoration Act?), and `cpau:e-nse-1` (Net Surplus Energy?). They are not yet incorporated into this filing — the modifier-packaging architecture is pending decision (cross-RatePlan applicability for E-HRA / E-NSE-1 + the urpx-org/urpx#16 SHACL-stub problem for modifier-only filings). Tracked at [grid-coordination/urpx-tariffs#9](https://github.com/grid-coordination/urpx-tariffs/issues/9).
