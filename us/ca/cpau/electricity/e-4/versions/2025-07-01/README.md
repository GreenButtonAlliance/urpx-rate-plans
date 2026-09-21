# CPAU E-4 — effective 2025-07-01

City of Palo Alto Utilities **Schedule E-4: Medium Non-Residential Electric Service**. Demand-metered Secondary service for customers with maximum demand below 1000 kW. **Non-TOU sibling** of [CPAU E-4 TOU](../../e-4-tou/versions/2025-07-01/) — same demand-charge structure, same customer base, but no TOU windowing within seasons.

## Files

- `cpau_e-4_2025-07-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_cpau_e-4_2025-07-01.jsonld` — URPX rate-plan serialization

## What's in the JSON-LD

The `@graph` bundle has a single top-level `urpx:RatePlan` (`cpau:e-4`) with its `urpx:RatePlanVersion` (`cpau:e-4-2025-07-01`). 11 `urpx:PriceDefinition`s.

### Rate structure (Section C of the PDF)

| Charge | Summer | Winter |
|---|---:|---:|
| **Demand** ($/kW) | $49.17 (= $11.09 commodity + $38.08 distribution) | $26.09 (= $2.60 + $23.49) |
| **Energy** ($/kWh) | $0.15842 (= $0.12441 + $0.02797 + $0.00604) | $0.11429 (= $0.08028 + $0.02797 + $0.00604) |
| **Customer Charge** | — | $126.24/month |

Each $/kWh rate is unbundled into `commodity / distribution / public-benefits` (3 components); each $/kW rate is unbundled into `commodity / distribution` (2 components — public-benefits doesn't apply to demand).

### Eligibility (Section A)

A 2-way `urpx:andOperator` over `urpx:ComparisonNode`s:

1. `metering = "Demand metered Secondary"`
2. `monthlyMaxDemand_kW < 1000`

(Customers with sustained demand 500–1000 kW for 3+ months may opt into [CPAU E-4 TOU](../../e-4-tou/versions/2025-07-01/) for a TOU-based alternative; E-4 is the non-TOU default for the demand-metered Secondary <1000 kW segment.)

### Demand-charge calculation

Each demand `urpx:PriceDefinition` carries a `urpx:CalculationMethod` with `aggregationMethod = urpx:maximum`, `intervalDuration = P1M`, `intervalType = monthlyInterval`:

> Maximum demand (kW) measured in any 15-minute interval at any time during the monthly billing period.

The 15-minute granularity is on the demand `MetricInput`'s `MetricSpecification` (`intervalDuration: PT15M`, `intervalType: fifteenMinuteInterval`). Per Section D.3, the City may exercise discretion to use a 5-minute interval for customers with intermittent or fluctuating loads — the default 15-minute interval is what's modeled here.

### Patterns reused from prior filings

- **Non-TOU seasonal pattern** — `urpx:appliesInSeason` on each `PriceDefinition` referencing one of two `urpx:Season` instances declared under `PlanElements.hasSeasons`. Same shape as [CPAU E-2](../../e-2/versions/2025-07-01/).
- **Demand-charge layer** — `urpx:demand` measurementKind, `urpx:kW` unit-of-measure, 15-minute interval on the demand MetricInput, `urpx:CalculationMethod` with max-aggregation on each demand PD. Same shape as [CPAU E-4 TOU](../../e-4-tou/versions/2025-07-01/) but without the demand TOUSchedule (since E-4 has no TOU windowing).

No genuinely new URPX modeling territory in this filing — it's the orthogonal combination of two patterns we already established.

## Deferred to follow-up issues

The following sections of the published Schedule E-4 are **not modeled in this filing**:

- **Section D.5 Primary Voltage Discount** — 2.5% discount for customers taking service at the supply line voltage when above 2 kV. Same clause as E-4 TOU's D.5; tracked under urpx-org/urpx#24 (broaden scope to all CPAU commercial schedules with this clause).
- **Section D.6 Standby Charge** — per-kW summer/winter charges for customers with non-utility on-site generation, with NEM-eligibility exemptions. Same shape as E-4 TOU's D.7; tracked under urpx-org/urpx#25 (broaden scope).
- **Section D.3 TES (Thermal Energy Storage) carve-out** — for TES customers, the billing demand is computed only from the noon–6 PM weekday window rather than all hours. Customer-attribute-conditional `CalculationMethod` — file as a new bd issue scoped to CPAU E-4. Most customers don't have TES; the default all-hours calculation is what's modeled.

(Section D.3 demand-meter installation rule — install demand meter when monthly use > 8000 kWh for 3 consecutive months — is a metering operations rule, not a rate, and is intentionally not modeled. Section D.3 5-minute-interval option for fluctuating loads is a City-discretion provision; default 15-minute is modeled.)

## Provenance

DCJ-authored, generated from scratch by `shadow-repo/scripts/build-cpau-e-4-2025-07-01.py` on 2026-04-30. Source PDF retrieved from paloalto.gov via curl_cffi (Chrome120 TLS impersonation; paloalto.gov rejects standard urllib/requests with 403).

## Validation

```
# Run from the urpx-rate-plans project root:
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
        -e ../urpx/ontology/urpx-ontology.ttl \
        -df json-ld \
        us/ca/cpau/electricity/e-4/versions/2025-07-01/rate-plan_cpau_e-4_2025-07-01.jsonld
# Conforms: True
```

End-to-end via clj-urpx: `clojure -M:validate` resolves the energy marginal at the Tue 2026-07-15 17:00 PDT probe instant to **0.15842** ($/kWh) — the Summer energy total ($0.12441 + $0.02797 + $0.00604), matching Section C of the PDF exactly. Demand ledgers (per-kW) and the service ledger (per-month customer charge) are correctly excluded from the per-kWh marginal sum.
