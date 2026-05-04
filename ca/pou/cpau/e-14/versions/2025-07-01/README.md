# CPAU E-14 — effective 2025-07-01

City of Palo Alto Utilities **Schedule E-14: Street Lights**.

## Files

- `cpau_e-14_2025-07-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_cpau_e-14_2025-07-01.jsonld` — URPX rate-plan serialization

## Notes

Flat per-fixture-per-month rates for street and highway lighting installations and traffic signals owned by **governmental agencies other than the City of Palo Alto** (Section A). CPAU supplies electricity, performs switching, and maintains the lamps and glassware.

**18 PriceDefinitions** modeled: 17 fixture types from the published rate sheet (Mercury-Vapor 400W; HPSV 70/100/150/250W; LED 70/100/150/175/250W-equivalent; traffic signals 12" Head, 8" Head, 12" Arrow, 12" Beacon; pedestrian head; controller; speed signs) plus a $2.50/month switching surcharge for separately-switched circuits below 10 kW lamp load (Section D.2). Each fixture type has its own `urpx:MetricInput` (count of fixtures of that type at the customer's installation) and its own `urpx:PriceDefinition` referencing it.

**New URPX modeling territory**: per-fixture-type pricing with a separate MetricInput per type. Previous corpus filings have shared a single energy MetricInput across many PriceDefinitions; E-14's discrete-fixture-enumeration is a different shape. `chargeType: urpx:serviceNonMetered`; `intervalDuration: P1M`.

**Deferred (description-only)**:
- Section D.5 interim-rate provision for lamps not on the schedule (operator's discretion; not a published rate).
- Section D.3 annual burning schedule (4100 hours/year operational rule).

## Provenance

DCJ-authored, generated from scratch by `shadow-repo/scripts/build-cpau-e-14-2025-07-01.py` on 2026-04-30. Source PDF retrieved from paloalto.gov via curl_cffi.

## Validation

```
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
        -e ../urpx/ontology/urpx-ontology.ttl \
        -df json-ld \
        ca/pou/cpau/e-14/versions/2025-07-01/rate-plan_cpau_e-14_2025-07-01.jsonld
# Conforms: True
```

End-to-end via clj-urpx: `clojure -M:validate` reports load+coerce+validate clean.
