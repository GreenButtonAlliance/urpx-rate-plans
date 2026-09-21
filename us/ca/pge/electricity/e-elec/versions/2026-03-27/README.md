# PG&E E-ELEC — effective 2026-03-27

PG&E Schedule E-ELEC (Residential Time-Of-Use, Electric Home), reissued under PG&E Advice Letter 7869-E / CPUC Decision D.26-03-013.

## Files

- `pge_e-elec_2026-03-27.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_pge_e-elec_2026-03-27.jsonld` — URPX rate-plan serialization

## Relationship to the 2026-01-01 sibling

This is the same E-ELEC schedule, reissued ~3 months later under D.26-03-013 — the same advice letter that produced the 2026-03-27 reissues of E-TOU-C, E-TOU-D, and EV2. The 2026-01-01 filing is preserved alongside this one because price-server consumers may need to resolve historical prices (e.g. for billing reconciliation) for instants prior to 2026-03-27.

## Substantive changes from 2026-01-01

| What | 2026-01-01 | 2026-03-27 |
|---|---|---|
| Base Services Charge | flat $0.49281/meter/day | income-tiered: CARE $0.19713, FERA $0.39688, Tier-3 $0.79343 (per meter per day) |
| California Climate Credit | $-36.18 per household, April + October bill cycles | **removed** |
| Energy rates (per kWh) | (per Sheet 3 of the 2026-01-01 PDF) | updated per Sheet 3 of the new PDF (see `UNBUNDLED_RATES` in the derive script) |
| Eligibility (residential + qualifying-tech / NBT) | unchanged | unchanged |
| TOU window structure (4–9pm peak, 3–4pm + 9pm–12am part-peak, 12am–3pm off-peak; same every day) | unchanged | unchanged |

The income-tier base-charge values match the E-TOU-C / E-TOU-D / EV2 / E-1 sibling filings under the same advice letter — D.26-03-013 standardized this charge across PG&E's residential schedules.

## Composite tariff PDF — mixed sheet revisions

As with PG&E's other 2026-03-27 reissues, the composite ELEC_SCHEDS_E-ELEC.pdf mixes sheets at different revisions:

- **Sheet 2** advances to AL 7869-E / 2026-03-27 (the new rate version)
- **Sheet 1 + Sheets 3-onward** stay at AL 7846-E / 2026-03-01

Both `urpx:TariffPublication` entities (`pge:al-7869-e` and `pge:al-7846-e`) are declared in `@graph` so consumers can attribute every clause to the right advice letter.

## Derivation

This filing was derived from the 2026-01-01 sibling by `shadow-repo/scripts/derive-e-elec-2026-03-27.py` rather than re-extracted from scratch — same pattern as the E-TOU-C 2026-03-01 → 2026-03-27 derivation. The script:

1. Adds 5 `urpx:ProgramEnrollment` instances (CARE, FERA, CCA, DA, TBS) referenced by the income-tier `ProfileAlternative` ConditionExpressions
2. Adds the new `urpx:RateCase` `pge:rc-d-26-03-013` and the two `urpx:TariffPublication`s
3. Updates 25 unbundled per-kWh `Price.unitPrice` values per Sheet 3
4. Drops the California Climate Credit (Ledger, PriceDefinition, Price, household-count MetricInput)
5. Replaces the flat $0.49281 base-charge `Price` with the income-tier base services charge structure: `pge:pa-income-tier` `urpx:ProfileAlternatives` (3 ProfileAlternatives: CARE, FERA, Standard — Standard's ConditionExpression uses a `BooleanOperationNode` of two `notEquals`) and 3 BSC `Price`s wrapped in `pge:psa-bsc-by-income-tier` `urpx:PriceSetAlternatives`, each `PriceSetAlternative` referencing the matching ProfileAlternative

## Vintage PCIA — still not modeled

The 2026-01-01 sibling didn't model the Sheet 4 vintage-PCIA table (carried over from the URPX-team-authored v0.1.x fixture); that omission persists here. Adding a vintage-PCIA `RatePlanModifier` to both E-ELEC versions is tracked at [#12](https://github.com/grid-coordination/urpx-rate-plans/issues/12).

## Validation

```
# Run from the urpx-rate-plans project root:
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
 -e ../urpx/ontology/urpx-ontology.ttl \
 -df json-ld \
 us/ca/pge/electricity/e-elec/versions/2026-03-27/rate-plan_pge_e-elec_2026-03-27.jsonld
# Conforms: True
```

End-to-end via clj-urpx: `clojure -M:validate` (load + coerce + resolve, all clean).
