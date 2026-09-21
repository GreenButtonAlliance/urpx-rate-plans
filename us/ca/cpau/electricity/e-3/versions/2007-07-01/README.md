# CPAU E-3 — effective 2007-07-01

City of Palo Alto Utilities **Schedule E-3: Customer-Owned Generation Retail Rate**.

## Files

- `cpau_e-3_2007-07-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_cpau_e-3_2007-07-01.jsonld` — URPX rate-plan serialization

## Notes

Buyback rates the utility **pays** to customers operating their own (non-NEM-eligible) generation facilities. **Effective 2007-07-01** — the oldest filing in this corpus, never reissued.

**V1 scope: Section C.1 WITHOUT-interval-meter case only.** 4 PriceDefinitions:
- Energy buyback Summer ($0.07902/kWh) — applies to both Firm and Non-Firm power
- Energy buyback Winter ($0.07831/kWh) — applies to both Firm and Non-Firm power
- Firm capacity credit Summer ($4.32/kW/month) — Firm-only via inline ApplicabilityGroup
- Firm capacity credit Winter ($4.32/kW/month) — Firm-only via inline ApplicabilityGroup

**New URPX modeling territory**: first **reverse-flow filing** in this corpus. `urpx:flowDirection: urpx:reverse` on both energy and capacity MetricInputs. The buyback pattern reuses the shape established by the CPAU E-EEC-1 and E-NSE-1 modifiers (in the multi-source CPAU E-1 2025-09-01 filing): `chargeType: urpx:creditEnergy`, `chargeCategory: urpx:discount`, `billPortion: urpx:bundledPortion`. For the capacity credit, `chargeType: urpx:creditGeneration` — the inverse direction of E-4 / E-4 TOU / E-7 / E-7 TOU's customer-facing `urpx:demandDirect` charges.

**Deferred to follow-up bd issues**:
- **Section C.2 WITH-interval-meter TOU buyback**: 3 TOU periods Summer (Off-Peak / Mid-Peak / Peak) + 2 TOU periods Winter (Off-Peak / Peak). The TOU windows **differ from CPAU E-4 TOU / E-7 TOU** — Summer Peak is 12 noon to 6 PM (not 4–9 PM); Winter Peak is 8 AM to 9 PM weekday non-holiday. Holidays excluded.
- **Section C.3 market-based buyback** for facilities with rated capacity > 1 MW: range pricing ($2–10/kW capacity, $0.03–0.20/kWh energy). URPX modeling for *range* pricing (rather than fixed values) is its own modeling question; defer.
- **Section E.5** customer charge for facilities served-as-load (operator's discretion; "specified in the service contract" rather than the rate schedule).

## Provenance

DCJ-authored, generated from scratch by `shadow-repo/scripts/build-cpau-e-3-2007-07-01.py` on 2026-04-30. Source PDF retrieved from paloalto.gov via curl_cffi.

## Validation

```
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
 -e ../urpx/ontology/urpx-ontology.ttl \
 -df json-ld \
 us/ca/cpau/electricity/e-3/versions/2007-07-01/rate-plan_cpau_e-3_2007-07-01.jsonld
# Conforms: True
```

End-to-end via clj-urpx: `clojure -M:validate` reports load+coerce+validate clean.
