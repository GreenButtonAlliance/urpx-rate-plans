# SCE NBT — effective 2025-04-23

SCE Schedule NBT (Net Billing Tariff) — residential modifier overlaying the TOU-D Option PRIME base RatePlan. Per CPUC Decision D.22-12-056 (adopted Dec 2022), NBT is the export-compensation regime for residential DER customers with interconnection applications submitted on or after April 15, 2023. Customer-facing names: "Solar Billing Plan" (SBP), with vintage labels NBT23 / NBT24 / NBT25 / NBT26 / NBT00.

## Files

- `sce_nbt_2025-04-23.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, modeling deferrals, validation status
- `rate-plan-modifier_sce_nbt_2025-04-23.jsonld` — URPX RatePlanModifier serialization

## Schedule designation

Filed SCE tariff designation is **Schedule NBT** (same as PG&E's). The colloquial "NEM 3" / "NEM 3.0" labels and the customer-facing "Solar Billing Plan" (SBP) name all refer to this schedule.

## Sibling of PG&E NBT — second export-direction modifier in the corpus

Modeling pattern derived directly from `ca/iou/pge/nbt/versions/2025-10-17/`. Both filings use `urpx:flowDirection urpx:reverse` on the MetricSpecification — confirmed admitted by the closed MetricSpecificationShape during PG&E NBT authoring. Both bind to a single mandatory residential base RatePlan via `urpx:applicableToRatePlan`. The PG&E NBT filing was the corpus's first export-direction modifier; this SCE NBT filing is the second.

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

Equivalent to PG&E's Low-Income classification. An Equity Customer is either:

1. A Residential Customer enrolled in CARE (California Alternate Rates for Energy) or FERA (Family Electric Rates Assistance);
2. A resident-owner of a single-family home in a disadvantaged community as defined in D.18-06-027; OR
3. A Residential Customer who lives in California Indian Country as defined in D.20-12-003.

Same eligibility basis as PG&E NBT's Low-Income. The Equity Customer predicate is consumer-side-evaluable; this filing's Price encodes the conjunction with vintage-2025 via a `urpx:BooleanOperationNode + urpx:andOperator`.

## What's modeled

- 4 `urpx:Ledger` + 4 `urpx:PriceDefinition` declaring the structural surface:
  - Export Compensation Rate — Generation Component (system-wide ACC: energy, cap-and-trade, generation capacity)
  - Export Compensation Rate — Delivery Component (ACC: transmission, distribution, greenhouse adder, methane leakage)
  - ACC Plus Non-Equity Customer adder
  - ACC Plus Equity Customer adder
- 2 `urpx:EligibilityRule`s — REGF requirement (Sheet 11 §1.b) + post-2023-04-15 interconnection-application date (Sheet 1 / Sheet 13)
- 2 `urpx:Price` instances (2025 interconnection vintage):
  - ACC Plus Non-Equity: `-$0.024/kWh` (Sheet 7 Table)
  - ACC Plus Equity: `-$0.056/kWh` (Sheet 7 Table)

## What's deferred

| Deferral | Why |
|---|---|
| **Per-cell Export Compensation Rate Prices** | Tracked at URPXT-7kr.2.1; SCE data-file URL was not surfaced during 2026-05-29 sourcing |
| **Additional ACC Plus vintages** (2023, 2024, 2026, 2027 rows) | Each requires sibling Price + vintage-gated ApplicabilityRule; follow-up |
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

## Per-cell data load — pending

The 4-vintage × 24-hour × 12-month × 2-day-type × 2-component grid (~4,608 Prices) is tracked at **URPXT-7kr.2.1**. PG&E NBT loaded these from `pge.com/energyexportcredit` (a single ZIP redirect to per-vintage PDFs); SCE's equivalent file location is not exposed on their customer-facing pages (the `Understanding Solar Export Pricing` page describes the file format including UTC time columns alongside PST, but doesn't surface the download URL). Follow-up will locate the SCE data file and run the equivalent of the PG&E extract+build pipeline.

## Cross-references

- **Parent epic**: URPXT-7kr (NBT export-compensation modeling for all three CA IOUs)
- **Sibling utility filings**: `ca/iou/pge/nbt/versions/2025-10-17/` (URPXT-7kr.1) — modeling-pattern source; URPXT-7kr.3 (SDG&E NBT) — next sibling
- **Base RatePlan**: SCE TOU-D Option PRIME — the mandatory residential OAS for NBT per Sheet 2 §1.a
- **Modifier overlay precedent**: `ca/iou/sce/tou-d-prime-cpp/versions/2026-03-20/` (CPP modifier over PRIME)
- **Foundational regulatory**: CPUC Decision D.22-12-056 (NBT adoption), D.23-11-068 (NBT-A Aggregation)
- **Most-recent reissue**: Advice 5533-E (Sheets 2 + 7, 2025-04-23); other sheets carry advice letters between 2023-03-01 and 2024-12-14

## Validation

SHACL passes via `dev/validate-with-base.py --utility sce`, which merges every SCE filing into one graph so the `applicableToRatePlan` reference to TOU-D-PRIME resolves. Validation passes on first attempt — the PG&E NBT modeling pattern transferred cleanly with utility-specific substitutions only.
