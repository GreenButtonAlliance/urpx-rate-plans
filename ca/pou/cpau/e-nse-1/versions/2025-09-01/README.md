# CPAU E-NSE-1 — effective 2025-09-01

City of Palo Alto Utilities **Schedule E-NSE-1**: Solar NEM 1 Net Surplus Electricity Compensation — annual-settlement compensation rate for NEM 1 customers who are net surplus generators at year-end and elect monetary payment. Does NOT apply to NEM 2 (Successor) customers. Net surplus electricity × compensation rate = annual monetary compensation.

A standalone `urpx:RatePlanModifier` filing applicable to eligible residential and small commercial NEM 1 Customers who, at end of an annual settlement period (per Rule 29), are net surplus customer-generators of electricity and elect monetary compensation.

## Files

- `cpau_e-nse-1_2025-09-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan-modifier_cpau_e-nse-1_2025-09-01.jsonld` — URPX rate-plan-modifier serialization (top-level `urpx:RatePlanModifier`)

## Provenance

Originally DCJ-authored, contributed to `urpx-org/urpx/test-cases/` via PR #7 (cpau-rate-plans branch). Brought into urpx-tariffs as part of the corpus expansion (URPXT-tdk). Carved out of the existing CPAU E-1 2025-09-01 multi-source filing's `@graph` into a standalone modifier filing on 2026-04-30 by `shadow-repo/scripts/extract-cpau-modifiers-tdk.py`.

The extracted modifier subtree:
- Has `urpx:applicableToRatePlan` and `urpx:applicableToRatePlanVersion` **stripped** — same standalone-modifier cross-graph identity workaround as the green-power filings (E-2-G / E-4-G / E-7-G), pending [`urpx-org/urpx#23`](https://github.com/urpx-org/urpx/issues/23).
- Has its `DataSourceReference` updated to point at the canonical paloalto.gov URL (rather than the placeholder `file://` URI inherited from the URPX-team-authored source).
- Carries the same modifier pricing, eligibility-rule (where present), and modeling shape as in the source multi-source filing.

## Standalone modifier filing

This is part of the second set of standalone modifier filings in the corpus (alongside CPAU E-2-G / E-4-G / E-7-G filed earlier today). Top-level entity is `urpx:RatePlanModifier`; JSON-LD filename uses the `rate-plan-modifier_*` convention.

The modifier's relationship to its base RatePlan(s) is captured in the `RatePlanModifierVersion.description` text only — the structural link via `urpx:applicableToRatePlan` / `urpx:applicableToRatePlanVersion` is omitted pending [`urpx-org/urpx#23`](https://github.com/urpx-org/urpx/issues/23). Once that resolves, retrofit via `shadow-repo/scripts/retrofit-modifier-options-9qp.py` (or its successor).

## Validation

```
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
        -e ../urpx/ontology/urpx-ontology.ttl \
        -df json-ld \
        ca/pou/cpau/e-nse-1/versions/2025-09-01/rate-plan-modifier_cpau_e-nse-1_2025-09-01.jsonld
# Conforms: True
```

End-to-end via clj-urpx: `clojure -M:validate` reports `load+coerce ✓  (resolve N/A — modifier requires base composition)`. Resolve-prices is correctly skipped pending the base+modifier composer (separate clj-urpx work; awaits `urpx-org/urpx#23` resolution).
