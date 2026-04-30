# CPAU E-7 — effective 2025-07-01

City of Palo Alto Utilities **Schedule E-7: Large Non-Residential Electric Service**. Demand-metered service for large-commercial customers with maximum demand ≥ 1000 kW per site, sustained 3+ consecutive months. **Large-commercial sibling** of [CPAU E-4](../../e-4/versions/2025-07-01/) (medium non-residential, < 1000 kW); **non-TOU sibling** of [CPAU E-7 TOU](../../e-7-tou/versions/2025-07-01/).

## Files

- `cpau_e-7_2025-07-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_cpau_e-7_2025-07-01.jsonld` — URPX rate-plan serialization

## Rate structure (Section C of the PDF)

| Charge | Summer | Winter |
|---|---:|---:|
| **Demand** ($/kW) | $43.61 (= $12.07 + $31.54) | $30.57 (= $2.82 + $27.75) |
| **Energy** ($/kWh) | $0.13792 (= $0.12786 + $0.00402 + $0.00604) | $0.08970 (= $0.07973 + $0.00393 + $0.00604) |
| **Customer Charge** | — | $578.08/month |

Each $/kWh rate is unbundled into `commodity / distribution / public-benefits`; each $/kW rate into `commodity / distribution`. Note that **distribution per kWh is much lower than E-4** ($0.00402 vs $0.02797) — large-commercial pays less per-kWh distribution because of higher volumes and lower per-unit cost-to-serve. The opposite applies to the customer charge ($578.08 vs $126.24): bigger customers pay a higher fixed monthly fee.

## Eligibility (Section A)

A 3-way `urpx:andOperator`:

1. `metering = "Demand metered"`
2. `monthlyMaxDemand_kW >= 1000`
3. `demandSustainedConsecutiveMonths = 3`

Customers below the 1000-kW threshold take CPAU E-4; customers in the 500–1000 kW band who want TOU may opt into E-4 TOU; large customers (≥ 1000 kW) who want TOU may opt into E-7 TOU.

## Demand-charge calculation

Same shape as E-4: each demand `urpx:PriceDefinition` carries a `urpx:CalculationMethod` with `aggregationMethod = urpx:maximum`, `intervalDuration = P1M`, `intervalType = monthlyInterval`. 15-minute granularity on the demand `MetricInput`.

## Site-aggregation feature (D.3) — noted, not modeled

> *"Qualifying Customers may request Service under this schedule for more than one Account or one Meter if the Accounts are on one site. A site, for the purposes of this Rate Schedule, consists of one or more Accounts which cover contiguous parcels of land with no intervening public right-of-ways (e.g. streets) and which have a common billing address."*

URPX has no native vocabulary for **site-level account aggregation** (multiple billing accounts treated as one for the purposes of demand-tier eligibility). This is noted in the JSON-LD's `RatePlanVersion.description` but not structurally encoded. Possible upstream URPX vocabulary issue if downstream consumers need it.

## Patterns reused

- **Non-TOU seasonal pattern** — `urpx:appliesInSeason` on each `PriceDefinition`. Same as [CPAU E-2](../../e-2/versions/2025-07-01/) and [CPAU E-4](../../e-4/versions/2025-07-01/).
- **Demand-charge layer** — `urpx:demand` measurementKind, `urpx:kW` unit, max-aggregation `CalculationMethod` on demand PDs. Same as [CPAU E-4](../../e-4/versions/2025-07-01/) and [CPAU E-4 TOU](../../e-4-tou/versions/2025-07-01/).

No new URPX modeling territory.

## Deferred to follow-up issues

- **Section D.6 Primary Voltage Discount** (2.8%) — URPXT-34j. *Note: rate is 2.8% here vs 2.5% on E-4 / E-4 TOU; modeling work needs to handle per-schedule rate variance.*
- **Section D.7 Standby Charge** ($40.79/kW summer, $27.75/kW winter) — URPXT-hii. *Note: rates differ from E-4 ($46.58 / $23.49); schedule-specific.*
- **Section D.4 TES carve-out** (Thermal Energy Storage customers' billing demand uses noon–6 PM weekday window) — same as E-4's existing TES follow-up.
- **Section D.4 5-minute interval option** for fluctuating loads — City discretion, default 15-minute is modeled.

## Provenance

DCJ-authored, generated from scratch by `shadow-repo/scripts/build-cpau-e-7-2025-07-01.py` on 2026-04-30 (templatized from the E-4 build script). Source PDF retrieved from paloalto.gov via curl_cffi.

## Validation

```
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
        -e ../urpx/ontology/urpx-ontology.ttl \
        -df json-ld \
        ca/pou/cpau/e-7/versions/2025-07-01/rate-plan_cpau_e-7_2025-07-01.jsonld
# Conforms: True
```

End-to-end via clj-urpx: `clojure -M:validate` resolves the energy marginal at the Tue 2026-07-15 17:00 PDT probe instant to **0.13792** ($/kWh) — Summer energy total exactly. Demand ledgers and service ledger correctly excluded from per-kWh marginal.
