# CPAU E-1 TOU — effective 2026-01-01

City of Palo Alto Utilities (CPAU) Schedule E-1 TOU, Residential Time-Of-Use Electric Service. Voluntary residential TOU rate plan with three periods (peak / off-peak / super-off-peak) × two seasons (summer / winter). Eligibility requires AMI (advanced metering infrastructure) supporting time-of-use measurement.

## Files

- `cpau_e-1-tou_2026-01-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_cpau_e-1-tou_2026-01-01.jsonld` — URPX rate-plan serialization

## What's in the JSON-LD

The file is an `@graph` bundle holding three top-level entities:

1. `cpau:e-1-tou` — the `urpx:RatePlan` (with nested `urpx:RatePlanVersion` `cpau:e-1-tou-2026-01-01`)
2. `cpau:e-hra` — `urpx:RatePlanModifier` (Electric Hydro Rate Adjuster); effective 2023-01-01
3. `cpau:e-nse-1` — `urpx:RatePlanModifier` (Net Surplus Energy); effective 2025-09-01

Single self-contained `@graph` per the price-server consumption pattern. Modifier RPMVs in this @graph are byte-equivalent to those in the E-1 filing's @graph for E-HRA — RDF graph merge across the two filings unifies cleanly.

### Structure

Only the **commodity** rate varies by TOU period; distribution ($0.09351) and public benefits ($0.00604) are flat across all hours.

| Period | Hours (every day) | Summer Commodity | Winter Commodity |
|---|---|---|---|
| Peak | 4–9 pm | $0.23354 | $0.16705 |
| Off-Peak | 7am–4pm + 9–11pm | (other rates) | (other rates) |
| Super Off-Peak | 11pm–7am | (lowest) | (lowest) |

Marginal at summer 5 pm peak (probe in `dev/validate_v020.clj`) = $0.33309/kWh.

### Eligibility

`urpx:EligibilityRule` requires four conjoined predicates: residential customer kind + single-family dwelling + separately metered + AMI meter installed.

## Provenance

DCJ-authored. Original v0.1.x conversion contributed to `urpx-org/urpx` via [PR #7](https://github.com/urpx-org/urpx/pull/7) on 2026-03-03; brought home to `urpx-rate-plans` and migrated to v0.2.0 on 2026-04-28.

## Validation

```
# Run from the urpx-rate-plans project root:
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
        -e ../urpx/ontology/urpx-ontology.ttl \
        -df json-ld \
        us/ca/cpau/electricity/e-1-tou/versions/2026-01-01/rate-plan_cpau_e-1-tou_2026-01-01.jsonld
# Conforms: True
```

End-to-end via clj-urpx: `clojure -M:validate` (load + coerce + resolve, all clean).

## Modifiers status

- **E-HRA** and **E-NSE-1** — both **incorporated** into the `@graph` of this filing (both effective by 2026-01-01).
- **E-EEC-1** — does NOT apply to E-1 TOU per its `applicableToRatePlan` (E-1 only).
