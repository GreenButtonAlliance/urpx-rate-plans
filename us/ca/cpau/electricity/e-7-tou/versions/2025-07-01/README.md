# CPAU E-7 TOU — effective 2025-07-01

City of Palo Alto Utilities **Schedule E-7 TOU: Large Non-Residential Electric Time of Use Service**. Voluntary opt-in TOU rate for demand-metered customers with maximum demand ≥ 1000 kW per site, sustained 3+ consecutive months. **Large-commercial sibling** of [CPAU E-4 TOU](../../e-4-tou/versions/2025-07-01/); **TOU sibling** of [CPAU E-7](../../e-7/versions/2025-07-01/).

## Files

- `cpau_e-7-tou_2025-07-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_cpau_e-7-tou_2025-07-01.jsonld` — URPX rate-plan serialization

27 PriceDefinitions: 18 energy + 8 demand + 1 customer charge.

## Rate structure (Section C of the PDF)

| Charge | Window | Summer ($/unit) | Winter ($/unit) |
|---|---|---:|---:|
| **Demand Peak** ($/kW) | 4–9 PM weekday non-holiday | $27.72 | $15.88 |
| **Max Demand** ($/kW) | All hours, every day | $17.79 | $15.88 |
| **Energy Peak** ($/kWh) | 4–9 PM weekday non-holiday | $0.19205 | $0.13222 |
| **Energy Mid-Peak** ($/kWh) | Summer: 2–4 PM + 9–11 PM weekday non-holiday<br>Winter: 9 AM–2 PM weekday non-holiday | $0.16005 | $0.10645 |
| **Energy Off-Peak** ($/kWh) | All other hours; weekends; holidays | $0.12282 | $0.07657 |
| **Customer Charge** | per month | — | $578.08 |

TOU windows are **identical to CPAU E-4 TOU** (and the PG&E pattern); only the rate values differ.

## Eligibility (Section A)

A 3-way `urpx:andOperator`:

1. `metering = "Demand metered"`
2. `monthlyMaxDemand_kW >= 1000`
3. `demandSustainedConsecutiveMonths = 3`

Same eligibility shape as the [CPAU E-7 base](../../e-7/versions/2025-07-01/), but voluntary opt-in (E-7 is mandatory; E-7 TOU is the voluntary TOU alternative for the same customer segment).

## Patterns reused

- **Two TOUSchedules per BillingModel** (energy + demand) — same as E-4 TOU
- **Holiday-aware TOU** (HolidayCalendar + includeHolidays/includeNonHolidays on TimeBracket) — same as E-4 TOU and PG&E E-TOU-D
- **Demand-charge layer** (`urpx:demand` measurementKind, max-aggregation `CalculationMethod`) — same as E-4 TOU
- **Commercial TOU windows that differ between Summer and Winter** (Mid-Peak shape changes seasonally) — same as E-4 TOU

No new URPX modeling territory; entirely mechanical adaptation of E-4 TOU with different rate values and the 1000+ kW eligibility threshold.

## Site-aggregation feature (D.3) — noted, not modeled

> *"Qualifying Customers may request Service under this schedule for more than one Account or one Meter if the Accounts are on one site..."*

Same site-aggregation feature as E-7. URPX has no native vocabulary; noted but not structurally encoded. Possible upstream URPX vocabulary issue.

## Deferred to follow-up issues

- **Section D.6 Primary Voltage Discount** (2.8%) — urpx-org/urpx#24. *Rate is 2.8% here vs 2.5% on E-4 / E-4 TOU; per-schedule variance to handle.*
- **Section D.7 Standby Charge** ($40.79/kW summer, $27.75/kW winter) — urpx-org/urpx#25. *Rates differ from E-4 TOU ($46.58 / $23.49); schedule-specific.*
- **Section D.5 12-month minimum commitment** — urpx-org/urpx#22 (upstream URPX vocabulary issue: URPX has no native vocabulary for minimum-term commitments).

(No TES carve-out: TES exception is on the non-TOU schedules only — E-4 and E-7.)

## Provenance

DCJ-authored, generated from scratch by `scripts/build-cpau-e-7-tou-2025-07-01.py` on 2026-04-30 (templatized from the E-4 TOU build script). Source PDF retrieved from paloalto.gov via curl_cffi.

## Validation

```
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
 -e ../urpx/ontology/urpx-ontology.ttl \
 -df json-ld \
 us/ca/cpau/electricity/e-7-tou/versions/2025-07-01/rate-plan_cpau_e-7-tou_2025-07-01.jsonld
# Conforms: True
```

End-to-end via clj-urpx: `clojure -M:validate` resolves the energy marginal at the Tue 2026-07-15 17:00 PDT probe instant to **0.19205** ($/kWh) — Summer Peak energy total exactly. Demand and service ledgers correctly excluded from per-kWh marginal.
