# SCE NBT — effective 2025-04-23

SCE Schedule NBT (Net Billing Tariff) — residential modifier overlaying the TOU-D Option PRIME base RatePlan. Per CPUC Decision D.22-12-056 (adopted Dec 2022), NBT is the export-compensation regime for residential DER customers with interconnection applications submitted on or after April 15, 2023. Customer-facing names: "Solar Billing Plan" (SBP), with vintage labels NBT23 / NBT24 / NBT25 / NBT26 / NBT00.

## Files

- `sce_nbt_2025-04-23.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, modeling deferrals, validation status
- `rate-plan-modifier_sce_nbt_2025-04-23.jsonld` — URPX RatePlanModifier serialization

## Schedule designation

Filed SCE tariff designation is **Schedule NBT** (same as PG&E's). The colloquial "NEM 3" / "NEM 3.0" labels and the customer-facing "Solar Billing Plan" (SBP) name all refer to this schedule.

## Sibling of PG&E NBT — second export-direction modifier in the corpus

Modeling pattern derived directly from `us/ca/pge/electricity/nbt/versions/2025-10-17/`. Both filings use `urpx:flowDirection urpx:reverse` on the MetricSpecification — confirmed admitted by the closed MetricSpecificationShape during PG&E NBT authoring. Both bind to a single mandatory residential base RatePlan via `urpx:applicableToRatePlan`. The PG&E NBT filing was the corpus's first export-direction modifier; this SCE NBT filing is the second.

## Single-base binding

Per Sheet 2 §1.a: "Residential Customers taking service under this Schedule must be on the Prime Option of Schedule TOU-D." Modeled as `urpx:applicableToRatePlan sce:tou-d-prime` — single-base modifier overlay, mirrors PG&E NBT's E-ELEC mandate and the SCE TOU-D-PRIME-CPP precedent.

Non-Residential NBT customers may take any TOU schedule (Sheet 2 §1.b) — non-residential modeling deferred.

## Structural surface vs PG&E NBT

| Element | SCE NBT | PG&E NBT |
|---|---|---|
| Base RatePlan binding | `sce:tou-d-prime` | `pge:e-elec` |
| MetricSpecification flowDirection | `urpx:reverse` | `urpx:reverse` |
| ACC Plus tier names | Non-Equity Customer / Equity Customer | Residential / Low-Income |
| 2025-vintage ACC Plus values | `-$0.024` / `-$0.056` | `-$0.01320` / `-$0.05400` |
| Lock-in horizon | 9 years (2023-04-15 to 2027-12-31 PTO) | Same |
| NBC list | PPPC, NDC, CTC, WFC | Same |
| Vintage label scheme | NBT23 / NBT24 / NBT25 / NBT26 / NBT00 | calendar-year |
| Sub-schedules | NBT-A, NBT-PS, NBT-MT | NBT-S, NBT-EXP, NBT-EXP-OTR, NBT-MT, NBT-PS, NBTA |

SCE Non-Equity values are roughly **2x PG&E Residential** values across all vintages (e.g. 2023: SCE $0.040 vs PG&E $0.022). Equity values are very close (2023: SCE $0.093 vs PG&E $0.090) — the equity tier appears to converge across IOUs while the standard tier differs.

## SCE Equity Customer definition (Sheet 17)

Sheet 17 (Cal. P.U.C. Sheet No. 87511-E, effective 2024-07-01) defines an Equity Customer as either:

1. A Residential Customer enrolled in CARE (California Alternate Rates for Energy) or FERA (Family Electric Rates Assistance);
2. A resident of a single-family home in a disadvantaged community as defined in D.18-06-027 whose account only has one meter; OR
3. A Residential Customer who lives in California Indian Country as defined in D.20-12-003 whose account has only one meter.

The committed PDF carries the superseded 87687-E, which says resident-owner and has no one-meter condition. The Equity Customer predicate is consumer-side-evaluable. The NBT25 vintage is two `urpx:ProfileAlternative` cells, one per customer segment of the Sheet 7 table (Residential Non-Equity Customer, Residential Equity Customer), stated by a second `urpx:AlternativeDimension`, `NBT Customer Segment`, in the vintage container. Each cell's `urpx:PriceSetAlternative` holds the NBT25 export Prices and that segment's ACC Plus Price, so a consumer selecting a cell gets one ACC Plus Price. No Price carries a `urpx:ApplicabilityRule`.

## What's modeled

- 4 `urpx:Ledger` + 4 `urpx:PriceDefinition` declaring the structural surface:
 - Export Compensation Rate — Generation Component (system-wide ACC: energy, cap-and-trade, generation capacity)
 - Export Compensation Rate — Delivery Component (ACC: transmission, distribution, greenhouse adder, methane leakage)
 - ACC Plus Non-Equity Customer adder
 - ACC Plus Equity Customer adder
- 2 `urpx:EligibilityRule`s — REGF requirement (Sheet 11 §1.b) + post-2023-04-15 interconnection-application date (Sheet 1 / Sheet 13)
- 5,088 Export Compensation Rate `urpx:Price`s from CEC MIDAS, one `urpx:PriceSetAlternative` per vintage, two for NBT25 (see below)
- 2 ACC Plus `urpx:Price` instances (2025 interconnection vintage):
 - ACC Plus Non-Equity: `-$0.024/kWh` (Sheet 7 Table)
 - ACC Plus Equity: `-$0.056/kWh` (Sheet 7 Table)

## What's deferred

| Deferral | Why |
|---|---|
| **Additional ACC Plus vintages** (2023, 2024, 2026, 2027 rows) | Each is a Price in each customer-segment cell of its vintage, split as NBT25 is; follow-up |
| Annual true-up / Net Surplus Compensation (NSC) | Year-long-window settlement doesn't fit per-bill modifier shape |
| NSC Renewable Attribute Adder (RAA) | WREGIS-transfer-contingent year-end concern |
| Sub-schedule variants (NBT-A, NBT-PS, NBT-MT) | Sibling filings |
| California Climate Credit cash-out provision (Sheet 26) | Consumer-side residential semi-annual credit handling |
| Legacy NEM/NEM-ST transition mechanics | Process state, not billing-time |
| Prevailing Wage (Special Condition 9) | Pre-PTO project eligibility, not a rate concept |
| Natural Disaster provisions (Special Condition 8) | Interconnection-process concern |
| Energy Export Credit Adjustment Pricing | Separate concern at sce.com/EEC-adjustment-pricing — addresses duplicate-EEC corrections at Relevant Period close |
| NBT-A Billing Service Charges (Sheet 10) | Multi-account-aggregation overlay, out of scope here |

Full list with reasoning in `tariff.toml` under `[modeling]`.

## Per-cell export compensation data

Loaded. The filing carries 5,088 RIN-tagged export compensation Prices covering all
twelve months, the hour-by-month-by-day-type grid the tariff prices exports on.
Generation is not published directly by SCE and is derived per cell by subtracting
the delivery-only SCXX rate from the bundled SCSC rate in MIDAS.

Vintage is a `urpx:ProfileAlternatives` (`sce:nbt-2025-04-23-pa-vintage`) with one `urpx:ProfileAlternative` per label, NBT23, NBT24, NBT25, NBT26 and non-vintaged, each stating `NBT Vintage Label`, except that NBT25 is two alternatives, one per `NBT Customer Segment`. The Prices sit in one `urpx:PriceSetAlternative` per alternative, on the pattern of `us/ca/sce/electricity/cca-crs/versions/2026-03-20/`, so a consumer selects the vintage, and for NBT25 the segment, with `:profile-alternatives` and one export Price applies per ledger at any instant. Month, hour and day type are time of use: a single `urpx:TOUSchedule` on the export MetricInput and 576 TOUPeriods, every period bracketed within a single-month `urpx:Season`. The export Prices name their period by `urpx:touPeriodNumber`, which is (month - 1) × 48 + 24 for a weekend + hour + 1. A weekday holiday prices at that hour's weekend value, as Sheet 5's weekday versus weekend/holiday split directs: every weekday bracket carries `urpx:includeHolidays` false, and every weekend period carries a second bracket, day type `urpx:weekdayDays` with `urpx:includeNonHolidays` false, so a weekday holiday lands on it. The modifier declares no `urpx:HolidayCalendar`; which days are holidays comes from the calendar on `sce:tou-d-prime`. `dev/remodel_nbt.py` added these brackets and flags and aborts unless every Price, value and period number is unchanged. NBT26 prices January through May only, so for June through December that vintage resolves no export Price; `dev/check_nbt_export.clj` expects exactly that and names the reason. `dev/remodel_nbt.py` produced this structure from the earlier per-Price periods and rules.

SCE does not expose the export rate file on its customer-facing pages the way PG&E
does at `pge.com/energyexportcredit`, so these came through MIDAS rather than a
published file. The `Understanding Solar Export Pricing` page documents the format,
including UTC time columns alongside PST, without surfacing a download URL.

## Reconciliation with the live tariff book

The committed PDF does not carry every sheet in force during this filing's window. Against the live tariff book retrieved 2026-10-11 (sha256 `f99d3800…`, held at `data/documents/sce/ELECTRIC_SCHEDULES_NBT.pdf`), its Sheets 2 and 7 carry the right sheet numbers (89744-E, 89745-E) but a text with (P) markers, and Sheet 7 conditions ACC Plus eligibility on Original PTO Date where 89745-E conditions it on Interconnection Request date. Its Sheets 5, 8, 14, 17, 23 and 24 are the revisions that AL 5209-E, 5209-E-A and 5209-E-B replaced effective 2024-07-01. Sheets 6 and 34 were replaced effective 2025-06-02 under AL 5497-E (89868-E, 89869-E), which begins the next version. The 2025 ACC Plus values and this filing's effective date are unchanged. The per-sheet table is in `tariff.toml` `[extraction]`.

## Cross-references

- **Parent epic**: (NBT export-compensation modeling for all three CA IOUs)
- **Sibling utility filings**: `us/ca/pge/electricity/nbt/versions/2025-10-17/` — modeling-pattern source; (SDG&E NBT) — next sibling
- **Base RatePlan**: SCE TOU-D Option PRIME — the mandatory residential OAS for NBT per Sheet 2 §1.a
- **Modifier overlay precedent**: `us/ca/sce/electricity/tou-d-prime-cpp/versions/2026-03-20/` (CPP modifier over PRIME)
- **Foundational regulatory**: CPUC Decision D.22-12-056 (NBT adoption), D.23-11-068 (NBT-A Aggregation)
- **Most-recent reissue**: Advice 5533-E (Sheets 2 + 7, 2025-04-23); in the committed PDF, other sheets carry advice letters effective between 2023-03-01 and 2024-03-06

## Validation

SHACL passes via `dev/shacl.sh --utility sce`, which merges every SCE filing into one graph so the `applicableToRatePlan` reference to TOU-D-PRIME resolves. Validation passes on first attempt — the PG&E NBT modeling pattern transferred cleanly with utility-specific substitutions only.
