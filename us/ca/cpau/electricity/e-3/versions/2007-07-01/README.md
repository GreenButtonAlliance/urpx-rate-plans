# CPAU E-3 — effective 2007-07-01

City of Palo Alto Utilities **Schedule E-3: Customer-Owned Generation Retail Rate**.

## Files

- `cpau_e-3_2007-07-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_cpau_e-3_2007-07-01.jsonld` — URPX rate-plan serialization

## Notes

Buyback rates the utility **pays** to customers operating their own (non-NEM-eligible) generation facilities. **Effective 2007-07-01**, never reissued.

**Both buyback tables are modeled.** Section C.1 (without an interval meter): energy buyback Summer $0.07902/kWh and Winter $0.07831/kWh for Firm and Non-Firm power, plus a Firm capacity credit of $4.32/kW-month in each season. Section C.2 (with an interval meter): five TOU energy cells, plus a peak-period Firm capacity credit of $4.32/kW-month in each season.

**Selection.** Which table applies (interval meter or not) and the type of power (Firm or Non-Firm, Special Note 1) are one `urpx:ProfileAlternatives`, `cpau:e3-pa-buyback-configuration`, with two dimensions and four cells. Each cell's `urpx:PriceSetAlternative` holds the energy buyback Prices of its table, and the two Firm cells also hold the capacity credits.

**New URPX modeling territory**: first **reverse-flow filing** in this corpus. `urpx:flowDirection: urpx:reverse` on both energy and capacity MetricInputs. The buyback pattern reuses the shape established by the CPAU E-EEC-1 and E-NSE-1 modifiers (in the multi-source CPAU E-1 2025-09-01 filing): `chargeType: urpx:creditEnergy`, `chargeCategory: urpx:discount`, `billPortion: urpx:bundledPortion`. For the capacity credit, `chargeType: urpx:creditGeneration` — the inverse direction of E-4 / E-4 TOU / E-7 / E-7 TOU's customer-facing `urpx:demandDirect` charges.

**Deferred to follow-up bd issues**:
- **Section C.3 market-based buyback** for facilities with rated capacity > 1 MW: range pricing ($2–10/kW capacity, $0.03–0.20/kWh energy). URPX modeling for *range* pricing (rather than fixed values) is its own modeling question; defer.
- **Section E.5** customer charge for facilities served-as-load (operator's discretion; "specified in the service contract" rather than the rate schedule).

## Provenance

DCJ-authored, generated from scratch by `scripts/build-cpau-e-3-2007-07-01.py` on 2026-04-30. Source PDF retrieved from paloalto.gov via curl_cffi.

## Validation

```
dev/shacl.sh --utility cpau
```

End-to-end via clj-urpx: `clojure -M:validate` reports load+coerce+validate clean.
