# PG&E E-TOU-C — effective 2026-03-27

Successor to the 2026-03-01 filing under [`../2026-03-01/`](../2026-03-01/). Sheet 2 of the tariff was reissued under PG&E Advice Letter 7869-E (CPUC Decision D.26-03-013) effective 2026-03-27, cancelling sheet 61125-E. The other sheets are unchanged.

## Files

- `pge_e-tou-c_2026-03-27.pdf` — source PDF (sha256 in `tariff.toml`). The composite PG&E tariff PDF mixes sheets at different revisions: Sheet 1 stays at 7846-E / 2026-03-01 (61124-E), Sheet 2 advances to 7869-E / 2026-03-27 (61249-E), Sheets 3–10 stay at 7846-E.
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_pge_e-tou-c_2026-03-27.jsonld` — URPX serialization
- `rate-plan-modifier_pge_e-tou-c-medical-baseline_2026-03-27.jsonld`: the Standard Medical Baseline Quantity of Electric Rule 19 (Code M and Code S) as adjusting brackets on this version's tiers (urpx-org/urpx#80), and the Medical Baseline Wildfire Fund Charge exemption
- `pge_rule-19_2023-03-23.pdf`: PG&E Electric Rule 19, Medical Baseline Quantities (sha256 in `tariff.toml`)

## What changed vs. 2026-03-01

The substantive change is the **removal** of the California Climate Credit (`-$36.18` per household, semi-annual April / October). Sheet 2 in the new revision drops the credit line entirely. All other rates — TOU peak / off-peak energy, base services charge, vintage PCIA tables, line-item adjustments — are unchanged.

JSON-LD diff vs. 2026-03-01:

- Drop `pge:ledger-climate-credit` (Ledger), `pge:pd-climate-credit` (PriceDefinition), `pge:price-climate-credit` (Price), and the `pge:mi-household-count` MetricInput (only the Climate Credit referenced it).
- Bump base RatePlanVersion `@id`: `pge:e-tou-c-2026-03-01` → `pge:e-tou-c-2026-03-27`.
- Bump base-RPV Price `startDate` values: `2026-03-01` → `2026-03-27`.
- TariffPublication: now declares **two** ALs in `@graph` — `pge:al-7869-e` (issues the new base RPV) and `pge:al-7846-e` (still operative for the unchanged vintage-PCIA modifier). Each carries the link to the artifact it issued.
- Add `pge:rc-d-26-03-013` `urpx:RateCase`; the base RPV references it via `urpx:hasRateCase`.
- Vintage PCIA modifier (`pge:e-tou-c-vintage-pcia`) and its modifier-version (`pge:e-tou-c-vintage-pcia-2026-03-01`) carry over **unchanged** — AL 7869-E did not republish E-TOU-C's PCIA sheets, so the modifier's effective date stays at 2026-03-01.

## What's in the JSON-LD

The `@graph` contains:

1. Five `urpx:ProgramEnrollment` instances (`pge:program-care`, `pge:program-fera`, `pge:program-cca`, `pge:program-da`, `pge:program-tbs`) referenced by the eligibility / applicability ConditionExpressions
2. Two `urpx:TariffPublication` instances: `pge:al-7869-e` (base RPV) + `pge:al-7846-e` (vintage-PCIA modifier)
3. `pge:rc-d-26-03-013` — `urpx:RateCase` for CPUC Decision D.26-03-013
4. `pge:e-tou-c` — `urpx:RatePlan` (with nested `urpx:RatePlanVersion` `pge:e-tou-c-2026-03-27`), carrying the baseline tiers and the Conservation Incentive Adjustment over the same 60-cell income tier, territory and code container as the 2026-03-01 version (see its README)
5. `pge:e-tou-c-vintage-pcia` — `urpx:RatePlanModifier` (modifier version unchanged at `pge:e-tou-c-vintage-pcia-2026-03-01`)

## Validation

```
# Run from the urpx-rate-plans project root:
dev/shacl.sh --utility pge
```

End-to-end via clj-urpx (load + coerce + resolve): clean. See [`../../../../../../dev/validate_v020.clj`](../../../../../../dev/validate_v020.clj).

## Provenance note

This filing was discovered while implementing the PDF-commit policy reversal: re-fetching the canonical URL on 2026-04-28 returned a different sha256 from our 2026-04-26 retrieval, and the diff isolated to Sheet 2. See [grid-coordination/urpx-rate-plans#5](https://github.com/grid-coordination/urpx-rate-plans/issues/5) for the discovery context and LAYOUT.md §6 for the broader policy reversal.
