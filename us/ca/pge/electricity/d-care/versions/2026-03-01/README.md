# PG&E D-CARE, effective 2026-03-01

PG&E Schedule D-CARE, the line-item discount for California Alternate Rates for Energy (CARE) customers, as a `urpx:RatePlanModifier` applicable to the residential bases E-1, E-TOU-C, E-TOU-D, EV2 and E-ELEC.

## Files

- `pge_d-care_2026-03-01.pdf`: source PDF (sha256 in `tariff.toml`)
- `tariff.toml`: provenance, modeling deferrals, validation status
- `rate-plan-modifier_pge_d-care_2026-03-01.jsonld`: URPX RatePlanModifier serialization

## What the schedule prices

Sheet 1: a CARE percentage discount "on their total bundled volumetric charges less charges from which they are exempt (Wildfire Fund Charge, Wildfire Hardening Charge, Recovery Bond Charge, Recovery Bond Credit, and the CARE surcharge portion of the public purpose program charge used to fund the CARE discount) on their otherwise applicable rate schedule (except for the California Climate Credit, which will not be discounted)". Sheet 2: D-CARE Discount 35.000 percent.

## What's modeled

| Price | Value | Basis |
|---|---|---|
| `pge:d-care-2026-03-01-price-wildfire-fund-exemption` | multiplier -1 | the base's Wildfire Fund Charge |
| `pge:d-care-2026-03-01-price-wildfire-hardening-exemption` | multiplier -1 | the base's Wildfire Hardening Charge |
| `pge:d-care-2026-03-01-price-recovery-bond-exemption` | multiplier -1 | the base's Recovery Bond Charge |
| `pge:d-care-2026-03-01-price-recovery-bond-credit-exemption` | multiplier -1 | the base's Recovery Bond Credit |
| `pge:d-care-2026-03-01-price-bill-discount` | multiplier -0.35 | the base's `-summary-care-discountable` |

Each Price names its candidate in all five current base versions, read as alternatives (LAYOUT.md section 6b). Each base's CARE-discountable `urpx:PriceSummary` names every volumetric Price of the base version except the four exempt charges; the base services charge is excluded as not volumetric, and the Public Purpose Programs charge is included whole because no document on disk publishes its CARE surcharge portion. `dev/lint_discount_summaries.py` re-derives the member lists.

The base services charge stays in each base's income-tier `urpx:ProfileAlternative` layer: Sheet 1 assigns a CARE customer to Income Tier 1 "and will not receive further discounts on the base service charge".

A subtotal names only its own base's Prices, so the Schedule NBT rule that the CARE discount is not applied to the Export Compensation Rate holds by construction.

## Checked

Summer weekday peak (2026-07-15 17:00), composed with each base:

| Base | Base marginal | Exempt | Discount | CARE marginal |
|---|---:|---:|---:|---:|
| E-1 | 0.32561 | -0.00982 | -0.1105265 | 0.2052635 |
| E-ELEC | 0.55214 | -0.00982 | -0.1898120 | 0.3525080 |
| E-TOU-C | 0.46886 | -0.00982 | -0.1606640 | 0.2983760 |
| E-TOU-D | 0.47708 | -0.00982 | -0.1635410 | 0.3037190 |
| EV2 | 0.53809 | -0.00982 | -0.1848945 | 0.3433755 |

Each CARE marginal is 0.65 times (base marginal less 0.00982). PG&E publishes no effective CARE rate for these schedules, so there is no published figure to reproduce.

What is not modeled, with measured effects, is in `tariff.toml` under `[modeling].deferrals`.
