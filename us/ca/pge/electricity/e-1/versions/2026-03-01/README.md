# PG&E E-1 — effective 2026-03-01

## Files

- `pge_e-1_2026-03-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_pge_e-1_2026-03-01.jsonld` — URPX serialization of the rate plan and the vintaged-PCIA modifier
- `rate-plan-modifier_pge_e-1-income-tier_2026-03-01.jsonld` — the Base Services Charge, at its three income tiers

## What's in the JSON-LD

`rate-plan_pge_e-1_2026-03-01.jsonld`, in its `@graph`:

1. Five `urpx:ProgramEnrollment` instances (`pge:program-care`, `pge:program-fera`, `pge:program-cca`, `pge:program-da`, `pge:program-tbs`) referenced by the eligibility / applicability ConditionExpressions
2. `pge:al-7846-e` — `urpx:TariffPublication` for PG&E Advice Letter 7846-E
3. `pge:e-1` — `urpx:RatePlan` (with nested `urpx:RatePlanVersion`) covering the unbundled energy rates, the conservation incentive adjustment by tier, and the baseline allowance matrix
4. `pge:e-1-vintage-pcia` — `urpx:RatePlanModifier` (with nested `urpx:RatePlanModifierVersion`) for the 18 vintage-conditional PCIA prices for CCA/DA/TBS customers, linked via `urpx:applicableToRatePlan`

`rate-plan-modifier_pge_e-1-income-tier_2026-03-01.jsonld` carries `pge:e-1-income-tier`, a second `urpx:RatePlanModifier`: the daily Base Services Charge at Income Tier 1 (CARE, $0.19713), Tier 2 (FERA, $0.39688) and Tier 3 ($0.79343). It is a separate document because `urpx:PlanElements` allows one `urpx:hasProfileAlternatives` container per version and the base plan spends its container on the baseline matrix below, and because `urpx.core/load-rate-plan-modifier` takes one `urpx:RatePlanModifier` per document.

### Structure

E-1 is **non-TOU**: a single per-kWh Generation rate ($0.12855) and Distribution rate ($0.18042), with the energy rate stratified into three baseline-percentage tiers via a tier-varying Conservation Incentive Adjustment:

| Tier | % of baseline | CIA $/kWh |
|---|---|---:|
| Tier 1 | 0–100% | −$0.04052 |
| Tier 2 | 101–400% | +$0.04089 |
| Tier 2 Continued | over 400% | +$0.04089 |

All other "all usage" components (transmission, public-purpose, wildfire-fund, etc.) match the values used across PG&E residential schedules.

### Baseline allowance matrix

Where those percentages fall in absolute kWh/day comes from Special Condition 2, Sheet 4 (Cal. P.U.C. Sheet 61099-E): 10 baseline territories × 2 baseline codes (B basic, H all-electric) × 2 seasons, 40 quantities, each the Tier 1 boundary with Tier 2 ending at four times it. All 40 are carried, as 20 `urpx:ProfileAlternative` cells over two `urpx:AlternativeDimension` nodes (`baselineTerritory`, `baselineCode`) and 20 cell-scoped `urpx:ServiceBracket` nodes on each of the six `urpx:ServiceTier` nodes, 120 brackets in total. All 40 values were checked against Sheet 4 of this filing's own PDF on 2026-09-23, and against the E-TOU-C overlay's brackets for the same table: no disagreements.

Which cell applies is the caller's to name, through `resolve-prices`'s `:profile-alternatives`, keyed by the container `pge:e-1-2026-03-01-pa-baseline-territory-code`. Naming none is not an error and not a default: clj-urpx 0.32.0 surfaces every tier with its number and unit price, withholds the bounds, and marks them `:alternative-unselected` with the twenty candidates it could not choose between. Measured 2026-09-23 at that pin: Territory R Code B resolves tiers 1 to 3 at 0-17.7, 17.7-70.8 and above 70.8 and tiers 4 to 6 at 0-10.4, 10.4-41.6 and above 41.6; Territory P Code B resolves to the same six bounds this filing carried before the matrix was written.

## Known limitations

### Season is not in the data

Sheet 4 gives separate summer and winter quantities and Special Condition 6 defines summer as June 1 through September 30. Season is carried by the identity of the six tiers, three summer rungs and three winter rungs, and by no `urpx:appliesInSeason`: the two `urpx:Season` nodes in the file are referenced by nothing. So the six tiers overlap over one kWh metric, and resolving at a summer instant and a winter instant returns the same six bounds. Writing the qualifier on all 120 brackets is possible now that the consumer selects on it, and would not depend on any other plan's season definitions, but it is a change of its own.

### The Base Services Charge is in a modifier, and modifiers are optional

Every E-1 customer pays a Base Services Charge; only the amount varies. `urpx:hasModifierOptions` is the only link from a plan to a modifier and it says the modifier is available, not that composing it is required, so a consumer resolving the base plan alone gets the energy charges and no daily charge. `tariff.toml` records the three shapes that would have kept the charge in the base plan and why each was not taken.

### Code M / S (medical) — not modeled

The tariff adds medical allowances (Code M / S) on top of the basic and all-electric quantities, and the additional amounts are "as provided in Rule 19", which is not in this corpus. Code B and Code H are both modeled.

### Initial effective date

`urpx:initialEffectiveDate` is set to 2001-01-01 as a placeholder for the post-restructuring modern PG&E E-1 era. The schedule predates this; the exact original effective date should be researched and corrected if available.

## Validation

```
# Run from the urpx-rate-plans project root, both documents in one graph:
python3 dev/validate-with-base.py --utility pge
```

This rate plan is serialized against URPX **v0.5.1** and validates clean against pyshacl + [clj-urpx](https://github.com/grid-coordination/clj-urpx) end-to-end (load → coerce → resolve).
