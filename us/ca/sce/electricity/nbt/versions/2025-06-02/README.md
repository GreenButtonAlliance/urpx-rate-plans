# SCE NBT: effective 2025-06-02

SCE Schedule NBT (Net Billing Tariff), the residential export-compensation modifier overlaying the TOU-D Option PRIME base RatePlan (`sce:tou-d-prime`), as it stands from Advice 5497-E, effective 2025-06-02. The modeling is that of the 2025-04-23 version (`../2025-04-23/README.md`); this version differs from it in the two sheets below and in no price.

## Files

- `sce_nbt_2025-06-02.pdf`: the live SCE tariff book for Schedule NBT, retrieved 2026-10-11 (sha256 in `tariff.toml`), the same bytes as `data/documents/sce/ELECTRIC_SCHEDULES_NBT.pdf`
- `tariff.toml`: provenance, the sheets the document carries, modeling deferrals, validation status
- `rate-plan-modifier_sce_nbt_2025-06-02.jsonld`: URPX RatePlanModifierVersion `sce:nbt-2025-06-02`, written by `dev/author_sce_nbt_2025_06_02.py`

## What Advice 5497-E changed

| Sheet | Cal. P.U.C. Sheet No. | Cancels | Change |
|---|---|---|---|
| 6 | 89868-E | 87507-E | Rates 3.a.ii: the EEC Vintage Year lock-in applies to an Interconnection Request date between 2023-04-15 and 2027-12-31. A Customer with an Original PTO Date on or before 2024-06-30 takes the EEC Vintage Year of that date; one with an Interconnection Request submitted from 2024-07-01 through 2027-12-31, or submitted before 2024-06-30 with an Original PTO Date after it, takes the EEC Vintage Year of the Interconnection Request date. |
| 34 | 89869-E | 87704-E | Special Condition 7.b: a NEM or NEM-ST Customer moved to NBT whose modifications or repairs increase system size by more than 10 percent or 1 kW begins a new 9-year legacy period from the PTO date of the modification. |

Both rules decide which vintage applies to a customer and for how long. The model takes the vintage as a selection the consumer supplies (`NBT Vintage Label`), so both are deferrals in `tariff.toml` `[modeling]`.

## Prices

Identical to the 2025-04-23 version: the Export Compensation Rate Prices from CEC MIDAS, carrying their MIDAS RIN citations, and the 2025 ACC Plus row of Sheet 7 (89745-E), -0.024 per kWh Residential Non-Equity Customer and -0.056 per kWh Residential Equity Customer. `dev/author_sce_nbt_2025_06_02.py` refuses unless every Price equals its 2025-04-23 counterpart.

## Supersession

The 2025-04-23 version ends 2025-06-02, the effective date of Sheets 6 and 34 here, which cancel revisions in force under it (LAYOUT.md §9, step 9).
