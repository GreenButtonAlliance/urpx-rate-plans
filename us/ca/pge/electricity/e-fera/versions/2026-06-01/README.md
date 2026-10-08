# PG&E E-FERA, effective 2026-06-01

PG&E Schedule E-FERA, Family Electric Rate Assistance, as a `urpx:RatePlanModifier` applicable to the residential bases E-1, E-TOU-C, E-TOU-D, EV2 and E-ELEC.

## Files

- `pge_e-fera_2026-06-01.pdf`: source PDF (sha256 in `tariff.toml`)
- `tariff.toml`: provenance, modeling deferrals, validation status
- `rate-plan-modifier_pge_e-fera_2026-06-01.jsonld`: URPX RatePlanModifier serialization

## What the schedule prices

Sheet 1: "an 18 percent discount on their total bundled volumetric charges on their otherwise applicable rate schedule", "a discount amount equal to 18 percent of the associated generation charges", and "Discounts will be applied as a residual reduction to distribution charges, after FERA customers are exempted from the Wildfire Hardening Charge, Recovery Bond Charge, and the Recovery Bond Credit." FERA customers pay the Wildfire Fund Charge.

## What's modeled

| Price | Value | Basis |
|---|---|---|
| `pge:e-fera-2026-06-01-price-wildfire-hardening-exemption` | multiplier -1 | the base's Wildfire Hardening Charge |
| `pge:e-fera-2026-06-01-price-recovery-bond-exemption` | multiplier -1 | the base's Recovery Bond Charge |
| `pge:e-fera-2026-06-01-price-recovery-bond-credit-exemption` | multiplier -1 | the base's Recovery Bond Credit |
| `pge:e-fera-2026-06-01-price-bill-discount` | multiplier -0.18 | the base's `-summary-fera-discountable` |

Each Price names its candidate in each current base version, read as alternatives (LAYOUT.md section 6b). Each base's FERA-discountable `urpx:PriceSummary` names every volumetric Price of the base version except the three exempt charges, generation included; the base services charge is excluded as not volumetric. The generation sentence is read as placing generation inside the discount, not as a second discount on it.

The base services charge stays in each base's income-tier `urpx:ProfileAlternative` layer: Sheet 1 assigns a FERA customer to Income Tier 2.

A subtotal names only its own base's Prices, so the Schedule NBT rule that the FERA discount is not applied to the Export Compensation Rate holds by construction.

## Checked

Summer weekday peak (2026-07-15 17:00), composed with each base:

| Base | Base marginal | Exempt | Discount | FERA marginal |
|---|---:|---:|---:|---:|
| E-1 | 0.32561 | -0.00391 | -0.0579060 | 0.2637940 |
| E-ELEC | 0.55214 | -0.00391 | -0.0986814 | 0.4495486 |
| E-TOU-C | 0.46886 | -0.00391 | -0.0836910 | 0.3812590 |
| E-TOU-D | 0.47708 | -0.00391 | -0.0851706 | 0.3879994 |
| EV2 | 0.53809 | -0.00391 | -0.0961524 | 0.4380276 |

Each FERA marginal is 0.82 times (base marginal less 0.00391). PG&E publishes no effective FERA rate for these schedules, so there is no published figure to reproduce.

What is not modeled is in `tariff.toml` under `[modeling].deferrals`.
