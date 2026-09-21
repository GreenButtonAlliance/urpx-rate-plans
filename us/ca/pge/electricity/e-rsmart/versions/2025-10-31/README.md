# PG&E E-RSMART — effective 2025-10-31

PG&E Schedule E-RSMART (Residential SmartRate Program) — voluntary Critical Peak Pricing overlay for single-family residential customers. Pays a small per-kWh credit on non-event-window kWh in exchange for accepting a +$0.60/kWh adder on the 4-9pm window during 9-15 SmartDay event days per calendar year. PG&E's residential analog of SCE TOU-D-PRIME-CPP. Customer-facing name: "SmartRate".

## Files

- `pge_e-rsmart_2025-10-31.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, modeling deferrals, validation status
- `rate-plan-modifier_pge_e-rsmart_2025-10-31.jsonld` — URPX RatePlanModifier serialization

## Schedule designation

Filed PG&E tariff designation is **Schedule E-RSMART**. URPXT-zvd's original title carried "E-CPP" which is incorrect — corrected to E-RSMART when claiming.

## Multi-base modifier — first in corpus

E-RSMART overlays **five** base RatePlans simultaneously (Sheet 1 APPLICABILITY):

- `pge:e-1` — tiered (no TOU)
- `pge:e-elec` — TOU with 4-9pm peak
- `pge:e-tou-c` — TOU with 4-9pm peak
- `pge:e-tou-d` — TOU with 5-8pm peak (note: different from SmartRate's 4-9pm window)
- `pge:ev2` — TOU with 4-9pm peak

This is the **first multi-base `urpx:RatePlanModifier` in the corpus**. SHACL-confirmed during sourcing that `urpx:applicableToRatePlan` has `maxCount=None` — multi-base binding is fully supported. SCE TOU-D-PRIME-CPP and PG&E NBT (URPXT-7kr.1) both bind to a single base; SmartRate exercises the multi-base case.

NBT compatibility is explicit (Sheet 1): NBT customers ARE eligible for SmartRate. SmartRate + NBT + E-ELEC stack for solar+battery+EMS customers — three overlapping pieces of pricing logic.

## Modeling pattern (PRIME-CPP precedent)

Follows the SCE TOU-D-PRIME-CPP modeling pattern at `us/ca/sce/electricity/tou-d-prime-cpp/versions/2026-03-20/` closely. Three PriceDefinitions on three separate Ledgers (Sheet 2 rate table):

| PriceDefinition | unitPrice | Gating |
|---|---|---|
| SmartDay High-Price Period Charge | `+$0.60000/kWh` | `hasDynamicPricing` + `criticalPeakPricing` + `eventTriggeredUpdates` + `PriceUpdateRule` with temperature-trigger semantics |
| SmartRate Non-High-Price Period Credit | `-$0.00636/kWh` (per-event rate) | ApplicabilityRule + `CustomOperandNode("SmartRate Credit Applicable") = "true"` |
| SmartRate Participation Credit | `-$0.00167/kWh` (per-event rate) | Same applicability as Non-High-Price Credit |

The SmartDay High-Price Period Charge uses the canonical URPX v0.2.0 event-driven pricing pattern (`hasDynamicPricing` + `criticalPeakPricing` + `eventTriggeredUpdates` + `PriceUpdateRule` prose) — same shape SCE PRIME-CPP refactored to.

## N_SmartDays bill-period multiplier — deferred to consumer

Per Sheet 2, both Credits' effective per-kWh value at billing time is `unitPrice × (number of SmartDays in bill period)`. This bill-period-aggregation semantic doesn't fit per-hour resolution. The modifier-level `unitPrice` carries the **per-event rate** (`$-0.00636`, `$-0.00167`); the consumer-side billing engine multiplies by the actual SmartDay count for the bill period.

For an EMS optimizing marginal price within a day, the per-event rate is small enough that it doesn't materially shift hour-by-hour scheduling decisions — the SmartDay High-Price Charge (`+$0.60000`) is the EMS-relevant signal.

## 4-9pm window encoding

The 4-9pm High-Price window is descriptive in the `PriceUpdateRule.description` on the SmartDay Charge, NOT structurally encoded as a `TOUPeriod`. Same approach SCE PRIME-CPP took. Reasoning:

- The `urpx:hasDynamicPricing + criticalPeakPricing + eventTriggeredUpdates` pattern is the canonical event-driven shape
- The 4-9pm window only matters on event days; SmartRate's window applies to ALL five base RatePlans regardless of their underlying TOU structure (and base structures differ — E-1 is tiered, E-TOU-D peaks at 5-8pm, others at 4-9pm)
- Consumer-side resolver evaluates "is the current instant in the 4-9pm window during a called SmartDay event?" using an external event calendar

If a downstream consumer needs structural encoding for the 4-9pm window, a follow-up filing can add a `TOUPeriod` carrying a `TimeBracket` referenced from the SmartDay Charge Price.

## Eligibility

One `EligibilityRule` with a single `CustomOperandNode("SmartRate Election") = "true"` — mirrors PRIME-CPP's `"CPP Election" = "PRIME-CPP"` simplicity. The other constraints — Bundled Service only, single-family residential, SmartMeter installed, NOT master-metered, NOT NEM-1/NEM-2, NOT standby, NOT DA/CCA, NOT Rule-22.1 TBS, NOT dual-enrolled in another DR program per D.18-11-029 — are baked into PG&E's enrollment-side validation. The customer-side state of "SmartRate Election = true" implies all of these gates passed at enrollment time.

NBT-compatibility: NBT is explicitly preserved as eligible per Sheet 1 — no additional gating needed.

## What's deferred

| Deferral | Why |
|---|---|
| Bill Protection (Sheet 5) | First-full-Summer-Season comparison vs OAS; year-long calculation doesn't fit per-bill modifier shape — same deferral pattern as SCE PRIME-CPP Bill Protection |
| N_SmartDays bill-period multiplier on the two Credits | Consumer-side billing-engine evaluates the count |
| Daily SmartDay activation trigger | Temperature-forecast / CAISO-Flex-Alert logic in PriceUpdateRule prose, not structurally evaluable |
| Grandfathered SmartAC dual-enrollment exception | Edge-case customer state pre-2018-10-26 |
| Customer-onboarding mechanics | Enrollment process, not billing-time |
| 4-9pm window as structural TOUPeriod | Optional refinement; current encoding via PriceUpdateRule prose follows PRIME-CPP precedent |

## Cross-references

- **Issue**: URPXT-zvd
- **Modeling-pattern source**: `us/ca/sce/electricity/tou-d-prime-cpp/versions/2026-03-20/` (CPP-modifier-overlay precedent)
- **Sibling overlay**: `us/ca/pge/electricity/nbt/versions/2025-10-17/` (PG&E NBT, separate epic URPXT-7kr) — NBT + SmartRate are both available on E-ELEC and can stack
- **Foundational regulatory**: D.19-07-004 (SmartRate authorization), D.21-03-056 (CPP framework — shared with SCE PRIME-CPP), D.18-11-029 (DR dual-enrollment prohibition)
- **Most-recent reissue**: Advice 7747-E (Sheet 1, 2025-10-31); Sheets 2-5 unchanged since Advice 6560-E (2022-05-01)

## Validation

SHACL passes via `dev/validate-with-base.py --utility pge`, which merges every PG&E filing into one graph so all five `applicableToRatePlan` references resolve. The overlapping ProgramEnrollment and TariffPublication declarations across those base files do produce cross-filing violations. An earlier version of the script suppressed them as base-file concerns; that hid the fact that they are real `@id` reuse, so they are now counted in the PG&E merged profile and held against a recorded baseline instead.
