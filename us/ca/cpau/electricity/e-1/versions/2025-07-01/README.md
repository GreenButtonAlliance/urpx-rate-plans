# CPAU E-1 — effective 2025-07-01

City of Palo Alto Utilities (CPAU) Schedule E-1, Residential Electric Service. Tiered non-TOU residential rate plan for single-family dwelling units served by a single meter.

## Files

- `cpau_e-1_2025-07-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_cpau_e-1_2025-07-01.jsonld` — URPX rate-plan serialization (`@graph` with the RatePlan)

## What's in the JSON-LD

The file is an `@graph` bundle holding two top-level entities:

1. `cpau:e-1` — the `urpx:RatePlan` (with nested `urpx:RatePlanVersion` `cpau:e-1-2025-07-01`)
2. `cpau:e-hra` — `urpx:RatePlanModifier` (Electric Hydro Rate Adjuster) — applicable to E-1; effective 2023-01-01 (already in effect at E-1's filing date)

Single self-contained `@graph` per the price-server consumption pattern — each filing is a complete program for downstream resolution.

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

DCJ-authored. Original v0.1.x conversion contributed to `urpx-org/urpx` via [PR #7](https://github.com/urpx-org/urpx/pull/7) on 2026-03-03; brought home to `urpx-rate-plans` and migrated to v0.2.0 on 2026-04-28 from PR head `e8ed4f0` (after Una's same-day SHACL-compliance push).

## Validation

```
# Run from the urpx-rate-plans project root:
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
        -e ../urpx/ontology/urpx-ontology.ttl \
        -df json-ld \
        us/ca/cpau/electricity/e-1/versions/2025-07-01/rate-plan_cpau_e-1_2025-07-01.jsonld
# Conforms: True
```

End-to-end via clj-urpx: `clojure -M:validate` (load + coerce + resolve, all clean).

## Modifiers status

- **E-HRA (Electric Hydro Rate Adjuster)** — incorporated into the `@graph` of this filing (effective 2023-01-01, applicable at E-1's filing date).
- **E-EEC-1 (Export Electricity Compensation)** — *not* incorporated in this 2025-07-01 rate plan. E-EEC-1 became effective 2025-09-01, AFTER E-1's 2025-07-01 filing date. The sibling rate plan at [`../2025-09-01/`](../2025-09-01/) incorporates both E-EEC-1 and E-NSE-1 in its `@graph`.
- **E-NSE-1** — same as above; incorporated in the [`../2025-09-01/`](../2025-09-01/) sibling.
