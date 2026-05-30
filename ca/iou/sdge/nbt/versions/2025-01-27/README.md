# SDG&E NBT — effective 2025-01-27

SDG&E Schedule NBT (Net Billing Tariff) for Customer-Sited Renewable Distributed Generation — residential modifier overlaying the EV-TOU-5 base RatePlan. Per CPUC Decision D.22-12-056 (adopted Dec 2022), NBT is the export-compensation regime for residential DER customers with interconnection applications submitted on or after April 15, 2023. Customer-facing name: "Solar Billing Plan" (SBP).

## Files

- `sdge_nbt_2025-01-27.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, modeling deferrals, validation status
- `rate-plan-modifier_sdge_nbt_2025-01-27.jsonld` — URPX RatePlanModifier serialization

## Schedule designation

Filed SDG&E tariff designation is **Schedule NBT** (same as PG&E and SCE). Tariff portal entry: `tariffsprd.sdge.com/view/tariff/?utilId=SDGE&bookId=ELEC&tarfKey=1064`. The customer-facing "Solar Billing Plan" name refers to this schedule.

## Sibling of PG&E NBT + SCE NBT — third export-direction modifier in the corpus

Modeling pattern derived from `ca/iou/pge/nbt/versions/2025-10-17/` (URPXT-7kr.1) and `ca/iou/sce/nbt/versions/2025-04-23/` (URPXT-7kr.2). All three NBT filings use `urpx:flowDirection urpx:reverse` on the MetricSpecification — the export-direction vocabulary the PG&E NBT work surfaced. All three bind to a single mandatory residential base RatePlan.

## Single-base binding to EV-TOU-5

Per Sheet 3: "Separately metered, residential customers including Aggregation customers taking service on the NBT tariff must take service on Schedule EV-TOU-5 as their OAS." Modeled as `urpx:applicableToRatePlan sdge:ev-tou-5` — single-base modifier overlay, same pattern as PG&E NBT's E-ELEC mandate and SCE NBT's TOU-D-PRIME mandate.

EV-TOU-5 is SDG&E's residential EV-friendly TOU rate; mandating it for NBT customers reflects the assumption that solar customers are also EV-adopting / electrification-leaning households.

## Structural surface vs PG&E NBT + SCE NBT

| Element | SDG&E NBT | SCE NBT | PG&E NBT |
|---|---|---|---|
| Base RatePlan binding | `sdge:ev-tou-5` | `sce:tou-d-prime` | `pge:e-elec` |
| MetricSpecification flowDirection | `urpx:reverse` | `urpx:reverse` | `urpx:reverse` |
| NBC count | **5** (PPP, ND, CTC, DWR-BC, WF-NBC) | 4 (PPPC, NDC, CTC, WFC) | 4 (PPPC, NDC, CTC, WFC) |
| ACC Plus tier names | Residential / Low Income Customer | Non-Equity / Equity Customer | Residential / Low Income |
| ACC Plus values in tariff | **NOT in this PDF** (referenced on Sheet 8 but values absent) | In tariff Sheet 7 | In tariff Sheet 11 |
| 2025-vintage ACC Plus values | pending discovery | $0.024 / $0.056 | $0.01320 / $0.05400 |

The **DWR-BC (Department of Water Resources Bond Charge)** is the SDG&E-specific NBC — reflects San Diego's particular exposure to DWR's California Water Project. PG&E and SCE don't have DWR-BC.

## SDG&E Low Income Customer definition (Sheet 5 §1.c)

Equivalent to PG&E's Low-Income and SCE's Equity Customer classifications. A Low Income Customer is:

1. A residential customer enrolled in CARE or FERA;
2. A resident-owner of a single-family home in a disadvantaged community per D.18-06-027; OR
3. A residential customer who lives in California Indian Country per D.20-12-003.

Same eligibility basis across all three CA IOUs; only the terminology differs (Low Income / Equity / Low-Income).

## What's modeled

- 4 `urpx:Ledger` + 4 `urpx:PriceDefinition` declaring the structural surface (same as PG&E and SCE NBT):
  - Export Compensation Rate — Generation Component (system-wide ACC: energy, cap-and-trade, generation capacity)
  - Export Compensation Rate — Delivery Component (ACC: transmission, distribution, greenhouse adder, methane leakage)
  - ACC Plus Residential adder
  - ACC Plus Low Income Customer adder
- 2 `urpx:EligibilityRule`s — REGF requirement (Sheet 5 §1.b) + post-2023-04-15 interconnection-application date (Sheet 1)
- **0 `urpx:Price` instances** in initial shell

## What's deferred

| Deferral | Why |
|---|---|
| **Per-cell Export Compensation Rate Prices** (4 published vintages × 576 cells × 2 components = ~4,608 Prices) | Loaded by URPXT-7kr.3.1; SDG&E publishes the URL directly on Sheet 4: `https://www.sdge.com/solar/solar-billing-plan/export-pricing` |
| **ACC Plus Adder values** | Sheet 8 references "ACC Plus credit" semantics but the values table is not in this composite PDF (Sheets 21-22 are absent from this PDF — could be where the values live or were canceled). Discovery needed. |
| Annual true-up / Net Surplus Compensation (NSC) | Year-long-window settlement doesn't fit per-bill modifier shape |
| NSC Renewable Attribute Adder (RAA) | WREGIS-transfer-contingent year-end concern |
| Discontinuance of NSC Double Compensation (Sheet 14 §6.c) | Consumer-side true-up reconciliation |
| Sub-schedule variants (NBT Aggregation SC 12, NBT Paired Storage SC 8, Multiple Tariff Facilities SC 5) | Sibling filings |
| **Schedule NBT-V** (Virtual NBT, separately filed at SDG&E tarfKey 1130) | Sibling tariff for multi-tenant properties; separate filing |
| PEV Submetering exclusion (Sheet 33 §13, per D.22-08-024) | Customer-class exclusion noted in prose |
| Legacy NEM/NEM-ST transition mechanics | Process state, not billing-time |
| Prevailing Wage (Special Condition 11) | Pre-PTO project eligibility, not a rate concept |
| Natural / Human-Made Disasters (Special Condition 10) | Interconnection-process concern |
| DWR-BC NBC modeling | Lives on the base EV-TOU-5 RatePlan, not on this modifier |

Full list with reasoning in `tariff.toml` under `[modeling]`.

## EEC data URL — exposed directly in the tariff

Sheet 4 cites `https://www.sdge.com/solar/solar-billing-plan/export-pricing` as the location of current EEC Rates. **Cleaner entry point than the SCE case**, where the equivalent URL was not exposed in the tariff or customer-facing pages. The per-cell load follow-up (URPXT-7kr.3.1) starts from this URL — likely a clean fetch unlike the SCE URL-discovery archaeology.

## Cross-references

- **Parent epic**: URPXT-7kr (NBT export-compensation modeling for all three CA IOUs)
- **Sibling utility filings**: `ca/iou/pge/nbt/versions/2025-10-17/` (URPXT-7kr.1) and `ca/iou/sce/nbt/versions/2025-04-23/` (URPXT-7kr.2)
- **Base RatePlan**: SDG&E Schedule EV-TOU-5 — the mandatory residential OAS for NBT per Sheet 3
- **Foundational regulatory**: CPUC Decision D.22-12-056 (NBT adoption), D.23-11-068 (NBT Aggregation SC 12)
- **Most-recent reissue**: Advice 4596-E (Sheets 23, 24, 25 — Prevailing Wage updates; effective 2025-01-27); most rate-bearing sheets carry 2023-2024 advice letters

## Validation

SHACL passes via `dev/validate-with-base.py` with the SDG&E EV-TOU-5 base RatePlan loaded as data context. The modifier validates with an empty `hasPrice` array — `urpx:Prices` does not require a minimum `hasPrice` count.
