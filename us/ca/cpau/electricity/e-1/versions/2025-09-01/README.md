# CPAU E-1 — effective 2025-09-01 snapshot

Snapshot of CPAU's E-1 Residential Electric Service as of 2025-09-01, with all three applicable RatePlanModifiers (E-HRA, E-EEC-1, E-NSE-1) bundled into the single self-contained `@graph` per the price-server consumption pattern.

This is a **snapshot filing** — the base E-1 rates did NOT change between [`../2025-07-01/`](../2025-07-01/) and this directory. What's new at 2025-09-01: two modifiers (E-EEC-1 and E-NSE-1) became effective. The base `RatePlanVersion` IRI in this filing is still `cpau:e-1-2025-07-01` (same data); the directory date `2025-09-01` is the snapshot date when the modifier configuration became operative.

## Files

- `cpau_e-1_2025-07-01.pdf` — base E-1 source PDF (identical to `../2025-07-01/`)
- `cpau_e-hra_2023-01-01.pdf` — E-HRA modifier PDF
- `cpau_e-eec-1_2025-09-01.pdf` — E-EEC-1 (Solar NEM 2 Export Electricity Compensation) modifier PDF
- `cpau_e-nse-1_2025-09-01.pdf` — E-NSE-1 (Solar NEM 1 Net Surplus Electricity Compensation) modifier PDF
- `tariff.toml` — provenance manifest for all 4 source documents
- `rate-plan_cpau_e-1_2025-09-01.jsonld` — URPX rate-plan serialization

## What's in the JSON-LD

`@graph` with **four** top-level entities:

1. `cpau:e-1` — `urpx:RatePlan` (with nested `urpx:RatePlanVersion` `cpau:e-1-2025-07-01`)
2. `cpau:e-hra` — `urpx:RatePlanModifier` (Electric Hydro Rate Adjuster); effective 2023-01-01. Per the canonical landing page, annotated *"Inactive as of 7/1/2023"* — the schedule still applies but currently produces zero adjustment.
3. `cpau:e-eec-1` — `urpx:RatePlanModifier` (Solar – NEM 2 Export Electricity Compensation Rate); effective 2025-09-01; applies to E-1 only
4. `cpau:e-nse-1` — `urpx:RatePlanModifier` (Solar – NEM 1 Election A Net Surplus Electricity Compensation Rate); effective 2025-09-01; applies to E-1 and E-1-TOU

## Provenance

DCJ-authored. Original v0.1.x conversions of all four documents contributed to `urpx-org/urpx` via [PR #7](https://github.com/urpx-org/urpx/pull/7) on 2026-03-03; brought home to `urpx-rate-plans` and migrated to v0.2.0 on 2026-04-28.

## Validation

```
# Run from the urpx-rate-plans project root:
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
 -e ../urpx/ontology/urpx-ontology.ttl \
 -df json-ld \
 us/ca/cpau/electricity/e-1/versions/2025-09-01/rate-plan_cpau_e-1_2025-09-01.jsonld
# Conforms: True
```

End-to-end via clj-urpx: `clojure -M:validate` (load + coerce + resolve, all clean).

## Re-fetching the canonical PDFs

`paloalto.gov` rejects standard `urllib`/`requests` with HTTP 403 (TLS fingerprint check). Use `curl_cffi` with Chrome impersonation:

```python
from curl_cffi import requests
s = requests.Session(impersonate="chrome120")
s.get("https://www.paloalto.gov/Departments/Utilities/Customer-Service/Utilities-Rates/Residential-Rates") # populate session
r = s.get(canonical_pdf_url, headers={"Referer": landing_page_url}, timeout=30)
```

Verified 2026-04-28 — all four PDFs in this directory are byte-identical to current canonical sources.
