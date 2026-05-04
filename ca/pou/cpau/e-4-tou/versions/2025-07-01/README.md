# CPAU E-4 TOU — effective 2025-07-01

City of Palo Alto Utilities **Schedule E-4 TOU: Medium Non-Residential Electric Time of Use Service**. Voluntary opt-in rate for demand-metered Secondary Electric Service customers with sustained demand 500–1000 kW.

This is the **first commercial TOU and first demand-charge filing** in this corpus — a substantial stress-test for URPX's vocabulary across multiple new dimensions.

## Files

- `cpau_e-4-tou_2025-07-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_cpau_e-4-tou_2025-07-01.jsonld` — URPX rate-plan serialization

## What's in the JSON-LD

The `@graph` bundle has a single top-level `urpx:RatePlan` (`cpau:e-4-tou`) with its `urpx:RatePlanVersion` (`cpau:e-4-tou-2025-07-01`). 27 `urpx:PriceDefinition`s in total: 18 energy + 8 demand + 1 customer charge.

### Rate structure (Section C of the PDF)

| Charge | Window | Summer ($/unit) | Winter ($/unit) |
|---|---|---:|---:|
| **Demand Peak** ($/kW) | 4–9 PM weekday non-holiday | $28.89 | $13.22 |
| **Max Demand** ($/kW) | All hours, every day | $20.37 | $13.22 |
| **Energy Peak** ($/kWh) | 4–9 PM weekday non-holiday | $0.20629 | $0.15475 |
| **Energy Mid-Peak** ($/kWh) | Summer: 2–4 PM + 9–11 PM weekday non-holiday<br>Winter: 9 AM–2 PM weekday non-holiday | $0.17602 | $0.12926 |
| **Energy Off-Peak** ($/kWh) | All other hours; all weekend; all holidays | $0.14083 | $0.09969 |
| **Customer Charge** | per month | — | $126.24 |

Each $/kWh rate is unbundled into `commodity / distribution / public-benefits` (3 components); each $/kW rate is unbundled into `commodity / distribution` (2 components — public-benefits doesn't apply to demand).

### Eligibility (Section A)

A 4-way `urpx:andOperator` over `urpx:ComparisonNode`s:

1. `metering = "Demand metered Secondary"`
2. `monthlyMaxDemand_kW >= 500`
3. `monthlyMaxDemand_kW <= 1000`
4. `demandSustainedConsecutiveMonths = 3`

(Conditions 2 + 3 + 4 together encode "demand 500–1000 kW sustained ≥ 3 consecutive months in the most recent 12-month period.")

The `monthlyMaxDemand_kW` and `demandSustainedConsecutiveMonths` are `urpx:CustomOperandNode` properties — URPX has no built-in vocabulary for these customer attributes, so they ride as named custom predicates.

### TOU windows + holiday handling

Two `urpx:TOUSchedule`s — one per `MetricInput`:

- **Energy schedule** (`referencesMetricInput → mi-energy`): 6 TOUPeriods (Peak / Mid-Peak / Off-Peak × Summer / Winter)
- **Demand schedule** (`referencesMetricInput → mi-demand`): 4 TOUPeriods (Peak Demand / Max Demand × Summer / Winter)

Each has a `hasCalendar` reference to a shared `urpx:HolidayCalendar` (US federal holidays — same set as PG&E E-TOU-D). `urpx:TimeBracket.includeHolidays` / `includeNonHolidays` booleans gate weekday Peak / Mid-Peak windows to non-holidays only; off-peak brackets cover the holiday-shifted hours plus all weekends.

The Mid-Peak window is the most interesting case: Summer Mid-Peak has TWO TimeBrackets (afternoon 2–4 PM and evening 9–11 PM); Winter Mid-Peak has ONE (morning 9 AM–2 PM).

### Demand-charge calculation

Each demand `urpx:PriceDefinition` carries a `urpx:CalculationMethod` with `aggregationMethod = urpx:maximum`, `intervalDuration = P1M`, `intervalType = monthlyInterval`:

- **Peak Demand**: max kW measured in any 15-minute interval **within the peak window** during the billing month
- **Max Demand**: max kW measured in any 15-minute interval **at any time** during the billing month

The 15-minute granularity is on the demand `MetricInput`'s `MetricSpecification` (`intervalDuration: PT15M`, `intervalType: fifteenMinuteInterval`).

Both Demand charges apply concurrently in each billing period — the customer pays both, and the maximum-peak-demand and maximum-max-demand may occur at different times.

## NEW URPX modeling territory

Patterns exercised here for the first time in this corpus (vocabulary verified via SPARQL against `urpx-shacl.ttl` before drafting):

1. **`urpx:demand` measurementKind + `urpx:kW` unit-of-measure** — per-kW pricing.
2. **Two TOUSchedules in one BillingModel** — `BillingModel.hasTOUSchedule` is unbounded per SHACL; energy and demand schedules each scoped to their own MetricInput.
3. **Commercial TOU windows that differ between seasons** — Summer and Winter Mid-Peak shapes are distinct.
4. **`urpx:CalculationMethod.aggregationMethod = urpx:maximum`** — explicit max-over-billing-period semantics on demand PDs (energy uses implicit sum aggregation).
5. **15-minute demand interval** — `intervalDuration: PT15M` + `intervalType: fifteenMinuteInterval` on the demand MetricInput.
6. **Holiday-aware TOU** — same pattern as PG&E E-TOU-D (HolidayCalendar at PlanElements; includeHolidays/includeNonHolidays booleans on TimeBracket).
7. **Voluntary opt-in commercial schedule** — `customerChoice: voluntaryChoice`, `isDefault: false`.

clj-urpx required one resolver-side enhancement to consume this filing — vector cardinality on `BillingModel.hasTOUSchedule` (filed as URPX-qb5 in clj-urpx beads, fixed in clj-urpx@faebc1a). The filing's modeling itself is unchanged from initial draft.

## Deferred to follow-up issues

The following sections of the published Schedule E-4 TOU are **not modeled in this filing** and should be filed as follow-ups before this filing is considered complete:

- **Section D.5 Primary Voltage Discount** — 2.5% discount for customers taking service at the supply line voltage when above 2 kV. Modeling: a conditional discount `Price` gated by an `ApplicabilityGroup` whose `ConditionExpression` checks a custom `serviceVoltage_kV > 2` predicate.
- **Section D.7 Standby Charge** — separate per-kW summer/winter charges ($46.58/kW summer, $23.49/kW winter) for customers with non-utility on-site generation, with eligibility conditions (D.7.a) and several exemption clauses (D.7.e — backup-only generators, NEM-eligible customer-generators). Effectively a separate set of `PriceDefinition`s gated by an `EligibilityRule` on `Customer.hasGenerator` plus exemption logic.
- **Section D.4 12-month minimum commitment** — customers electing E-4 TOU must remain on the schedule for at least 12 months. URPX has no native vocabulary for minimum-term commitments; possible upstream issue against `urpx-org/urpx`.

(Section D.3 demand-meter installation rule — install demand meter when monthly use > 8000 kWh for 3 consecutive months, remove after 12 months < 6000 kWh — is a metering operations rule, not a rate, and is intentionally not modeled.)

## Provenance

DCJ-authored, generated from scratch by `shadow-repo/scripts/build-cpau-e-4-tou-2025-07-01.py` on 2026-04-29. Source PDF retrieved from paloalto.gov via curl_cffi (Chrome120 TLS impersonation; paloalto.gov rejects standard urllib/requests with 403).

## Validation

```
# Run from the urpx-tariffs project root:
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
        -e ../urpx/ontology/urpx-ontology.ttl \
        -df json-ld \
        ca/pou/cpau/e-4-tou/versions/2025-07-01/rate-plan_cpau_e-4-tou_2025-07-01.jsonld
# Conforms: True
```

End-to-end via clj-urpx: `clojure -M:validate` resolves the energy marginal at the Tue 2026-07-15 17:00 PDT probe instant to **0.20629** ($/kWh) — the Summer Peak energy total ($0.17208 + $0.02817 + $0.00604), matching Section C of the PDF exactly. Demand ledgers (per-kW) and the service ledger (per-month customer charge) are correctly excluded from the per-kWh marginal sum.
