# CPAU E-2 — effective 2025-07-01

City of Palo Alto Utilities **Schedule E-2: Residential Master-Metered and Small Non-Residential Electric Service**. First commercial rate plan in this corpus, opening the CPAU business / non-residential schedules.

## Files

- `cpau_e-2_2025-07-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_cpau_e-2_2025-07-01.jsonld` — URPX rate-plan serialization

## What's in the JSON-LD

The file is an `@graph` bundle with a single top-level `urpx:RatePlan` (`cpau:e-2`) and its nested `urpx:RatePlanVersion` (`cpau:e-2-2025-07-01`).

### Structure

Two-period seasonal rate, **no TOU within periods, no tiers**:

| Period | Months | Commodity | Distribution | Public Benefits | **Total** |
|---|---|---:|---:|---:|---:|
| Summer | May 1 – Oct 31 | $0.15075 | $0.10806 | $0.00604 | **$0.26485** |
| Winter | Nov 1 – Apr 30 | $0.09334 | $0.07352 | $0.00604 | **$0.17290** |

Plus:
- **Customer charge**: $6.22 per meter per **month** (flat — most filings in this corpus use $/day for the equivalent, but CPAU E-2's published charge is monthly)

### Eligibility

A 2-way `urpx:orOperator` over two `urpx:BooleanOperationNode` AND-branches:

1. **Non-residential branch**: `urpx:hasCustomerKind = urpx:nonResidentialKind` AND custom `metering = "Non-Demand metered"`
2. **Master-metered multi-family residential branch**: `urpx:hasCustomerKind = urpx:residentialKind` AND custom `dwellingType = "Master-metered multi-family"` AND custom `metering = "Non-Demand metered"`

Section A of the published Schedule E-2 (Sheet E-2-1) defines these two eligibility paths; a customer qualifies if either holds.

### Special note

Sheet E-2-2's "Maximum Demand Meter" clause (a customer exceeding 8,000 kWh for three consecutive months gets a demand meter installed) is an operational metering rule, not a rate, and is not modeled.

## NEW URPX modeling territory

Several patterns are exercised here for the first time in the urpx-rate-plans corpus. The vocabulary supports all of them — the work was just verifying via SPARQL against the URPX SHACL shapes:

1. **`urpx:nonResidentialKind` eligibility** — first commercial filing in the corpus.
2. **`urpx:appliesInSeason` on `PriceDefinition`** — non-TOU seasonal applicability. PG&E filings use TOU + `ApplicabilityRule.month`; CPAU E-1-TOU uses TOU + Season via the TOUPeriod chain. CPAU E-2 is the simplest case: just Season, no TOU. Each PD points at the right `urpx:Season` (declared under `PlanElements.hasSeasons`) with its `month` list.
3. **`urpx:hasSeasons` on `PlanElements`** — declares the Summer/Winter `urpx:Season` instances with `xsd:gMonth` lists, referenced by `appliesInSeason` from each unbundled PriceDefinition.
4. **Monthly `intervalDuration` (`P1M`) on the customer-charge calculation method** — residential CPAU and all PG&E filings in this corpus use `P1D` for their daily customer charges. CPAU E-2 publishes a per-month charge ($6.22/month).

The `appliesInSeason → Season.month` resolver path was added to clj-urpx in [](https://github.com/grid-coordination/clj-urpx/issues) (clj-urpx@86d109e) to support this pattern.

## Modifiers (not yet integrated)

CPAU E-2 customers are eligible for several rate-plan modifiers that are **not currently modeled in this filing's `@graph`**:

- **E-EEC-1** (Solar NEM 2 Export Compensation) — applies to small commercial customers
- **E-NSE-1** (Solar NEM 1 Net Surplus Compensation) — applies to small commercial NEM 1 customers
- **E-HRA** (Electric Hydro Rate Adjuster) — applies to all CPAU electric customers (currently zero-valued; "Inactive as of 7/1/2023")

Two of these (E-EEC-1, E-NSE-1) became effective 2025-09-01, after the base E-2 effective date. A future multi-source snapshot filing at `versions/2025-09-01/` could embed all three modifier `RatePlanModifierVersion`s into the `@graph` (the same pattern used for [CPAU E-1 2025-09-01](../../e-1/versions/2025-09-01/)).

## Provenance

DCJ-authored, generated from scratch (not migrated from any prior fixture) by `shadow-repo/scripts/build-cpau-e-2-2025-07-01.py` on 2026-04-29. Source PDF retrieved from paloalto.gov via curl_cffi (Chrome120 TLS impersonation; paloalto.gov rejects standard urllib/requests with 403).

## Validation

```
# Run from the urpx-rate-plans project root:
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
 -e ../urpx/ontology/urpx-ontology.ttl \
 -df json-ld \
 us/ca/cpau/electricity/e-2/versions/2025-07-01/rate-plan_cpau_e-2_2025-07-01.jsonld
# Conforms: True
```

End-to-end via clj-urpx: `clojure -M:validate` resolves the summer marginal at the Tue 2026-07-15 17:00 PDT probe instant to **0.26485** ($/kWh), matching the Section C published Summer total exactly.
