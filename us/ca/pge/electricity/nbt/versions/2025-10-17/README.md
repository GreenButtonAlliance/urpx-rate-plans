# PG&E NBT — effective 2025-10-17

PG&E Schedule NBT (Net Billing Tariff) Service — residential modifier overlaying the E-ELEC base RatePlan. Per CPUC Decision D.22-12-056 (adopted Dec 2022), NBT is the export-compensation regime for residential DER customers with interconnection applications submitted on or after April 15, 2023. Customer-facing name: "Solar Billing Plan".

## Files

- `pge_nbt_2025-10-17.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, modeling deferrals, validation status
- `rate-plan-modifier_pge_nbt_2025-10-17.jsonld` — URPX RatePlanModifier serialization

## Schedule designation

Filed PG&E tariff designation is **Schedule NBT**, not NEM-NBT or NEM-3. The colloquial "NEM-3" and the customer-facing "Solar Billing Plan" both refer to this schedule.

## Modeling approach

NBT is modeled as a `urpx:RatePlanModifier` overlaying `pge:e-elec` via `urpx:applicableToRatePlan`. This mirrors the SCE TOU-D-PRIME-CPP precedent at `us/ca/sce/electricity/tou-d-prime-cpp/versions/2026-03-20/` exactly. Per Sheet 9 §A of the source PDF, residential customers taking NBT MUST take E-ELEC as their Otherwise Applicable Schedule — single-base binding.

Import-side charges remain governed by the base E-ELEC RatePlan; this modifier handles only the export-side compensation. Import and export kWh are independently recorded on separate meter channels and are NOT netted (Sheet 7).

## Export-direction vocabulary

The export side uses `urpx:flowDirection urpx:reverse` on the MetricSpecification — defined in URPX v0.2.0 as "Reverse energy flow - generation/export to grid". This is the first use of `urpx:flowDirection` in this corpus.

SCE TOU-D-PRIME-CPP previously deferred direction-of-flow distinction because its Non-Event Credit applied to consumption-side energy. NBT pays for exported energy, so it needs the vocabulary — and the vocabulary has been in URPX v0.2.0 since the initial release. `MetricSpecificationShape` is `sh:closed=true` but explicitly lists `urpx:flowDirection` in its `sh:path` — closed shape admits the property. SPARQL-confirmed during sourcing.

## What's modeled

- 4 `urpx:Ledger` + 4 `urpx:PriceDefinition` declaring the structural surface:
 - Export Compensation Rate — Generation Component (system-wide ACC values; bundled-customer-only per published price-sheet footnote)
 - Export Compensation Rate — Delivery Component (system-averaged across PG&E climate zones per tariff Sheet 10 step 2; applies to all NBT customers)
 - ACC Plus Residential adder ("Energy Export Bonus Credit")
 - ACC Plus Low-Income Residential adder (CARE/FERA / disadvantaged-community-resident-owner / California-Indian-Country)
- 2 `urpx:EligibilityRule`s — REGF requirement + post-2023-04-15 interconnection-application date
- 2 `urpx:Price` instances (2025 interconnection vintage):
 - ACC Plus Residential: `$-0.01320/kWh` (Sheet 11 Table)
 - ACC Plus Low-Income: `$-0.05400/kWh` (Sheet 11 Table)

The low-income Price uses a `urpx:BooleanOperationNode` with `urpx:andOperator` conjoining (vintage = 2025) AND (low-income-eligible = true). First use of boolean-composition vocabulary in this corpus.

## What's deferred

| Deferral | Why |
|---|---|
| **Additional ACC Plus vintages** (2023, 2024, 2026, 2027 rows) | Each requires a sibling Price + vintage-gated ApplicabilityRule; follow-up |
| Annual true-up / Net Surplus Compensation (NSC) | Year-long-window settlement doesn't fit per-bill modifier shape — same deferral as PRIME-CPP Bill Protection |
| NSC Renewable Attribute Adder (RAA) | WREGIS-transfer-contingent year-end concern |
| Sub-schedule variants (NBT-EXP, NBT-EXP-OTR, NBT-MT, NBT-PS, NBTA) | Sibling filings |
| Multiple Tariff Facilities (SC 4) | Non-residential |
| Load Aggregation NBTA (SC 6) | Multi-parcel arrangements; non-residential focus |
| Legacy NEM/NEM2 transition mechanics | Process state, not billing-time |
| Prevailing Wage (SC 10) | Pre-PTO project eligibility, not a rate concept |
| Natural/Human-Made Disasters provisions (SC 9) | Interconnection-process concern |

Full list with reasoning in `tariff.toml` under `[modeling]`.

## Per-cell data load — TOUPeriod chain

The per-cell Export Compensation Rate Prices use a `urpx:TOUPeriod` chain: `Price → TOUPeriod → TimeBracket`. `urpx:hasTimeBracket` attaches to TOUPeriod, not directly to ApplicabilityRule. The data load emits 48 shared TOUPeriods (24 hours × 2 day-types — `urpx:weekdayDays` / `urpx:weekendDays`), 48 shared ApplicabilityRules (12 months × 4 vintages, each carrying month + vintage-gating ConditionExpression), and 4,608 per-cell Prices (576 cells per vintage × 2 components × 4 published vintages 2023-2026). Combined with the 2 ACC Plus prices, total 4,610 Prices on the modifier.

Per the tariff Sheet 10 methodology step 2, the published Delivery component is system-averaged across PG&E climate zones (no per-zone variability in the published data), so the cell count is per-vintage not per-zone-vintage.

Source: `pge.com/energyexportcredit` redirects to a ZIP containing per-vintage PDFs. Extraction + emission scripts at `scripts/extract-nbt-eec-values.py` and `build-pge-nbt-prices-2025-10-17.py`. The extractor handles per-vintage PDF styling quirks (2026 has bold-overstrike text breaking pdfplumber; 2025 has whitespace collapsing breaking pypdf) by trying both libraries and using whichever yields a clean 48-row parse. The build script is idempotent — preserves the ACC Plus Prices and replaces the per-cell layer on each run.

## Cross-references

- **Parent epic**: (NBT export-compensation modeling for all three CA IOUs)
- **Sibling utility filings**: (SCE NBT) and (SDG&E NBT) — both follow the modeling pattern established here
- **Modeling-pattern source**: `us/ca/sce/electricity/tou-d-prime-cpp/versions/2026-03-20/` (RatePlanModifier-overlay precedent)
- **Base RatePlan**: `us/ca/pge/electricity/e-elec/versions/2026-03-27/` (the mandatory residential OAS per Sheet 9 §A)
- **Foundational regulatory**: CPUC Decision D.22-12-056

## Validation

SHACL passes via `dev/validate-with-base.py --utility pge`, which merges every PG&E filing into one graph so the `applicableToRatePlan` reference to E-ELEC resolves.
