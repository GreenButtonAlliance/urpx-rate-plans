# PG&E E-ELEC — effective 2026-01-01

PG&E Schedule E-ELEC (Residential Time-Of-Use, Electric Home) — opt-in residential TOU schedule for customers with at least one qualifying electric technology (battery EV, plug-in hybrid, energy storage, electric heat pump) OR enrollment on the Net Billing Tariff.

## Files

- `pge_e-elec_2026-01-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_pge_e-elec_2026-01-01.jsonld` — URPX rate-plan serialization

## What's in the JSON-LD

The file is an `@graph` bundle with a single top-level `urpx:RatePlan` (`pge:e-elec`) and its nested `urpx:RatePlanVersion` (`pge:e-elec-2026-01-01`).

### Structure

3-period × 2-season TOU schedule (same window pattern as EV2):

| Period | Hours (every day) | Summer | Winter |
|---|---|---:|---:|
| Peak | 4–9 p.m. | $0.57908 | $0.34756 |
| Part-Peak | 3–4 p.m. + 9 p.m.–12 a.m. | $0.41720 | $0.32547 |
| Off-Peak | 12 a.m.–3 p.m. | $0.36052 | $0.31161 |

Plus:
- Base Services Charge: **$0.49281 per meter per day** (flat — no income-tier structure unlike E-TOU-C / E-TOU-D / E-1 / EV2)
- California Climate Credit: **−$36.18 per household per semi-annual payment** (April + October bill cycles)
- 13-line unbundling: Generation, Distribution, Transmission, Public Purpose, Wildfire, Recovery Bond, etc.

### Eligibility

Two `urpx:EligibilityRule`s (both must hold for service under E-ELEC):

1. **`pge:er-residential`** — `urpx:hasCustomerKind = urpx:residentialKind`
2. **`pge:er-qualifying-technology`** — at least ONE of:
   - `urpx:derType = urpx:storageDER` (energy storage; per Special Condition interconnection requirements)
   - `urpx:derType = urpx:evChargingDER` (BEV or PHEV — URPX's DERTypeValue enum doesn't distinguish them)
   - `urpx:hasHVAC = urpx:airSourceHeatPump` (electric heat pump as primary water-heating or climate-control source)
   - `urpx:CustomOperandNode` "Program Enrollment" = "Net Billing Tariff (NBT)" (NBT customers must take service under E-ELEC and aren't required to have any of the qualifying technologies above; CustomOperandNode used because URPX has no NBT-specific vocabulary)

The four qualifying-technology predicates are joined by `urpx:orOperator` in a `urpx:BooleanOperationNode`.

### Vintage PCIA — not modeled

The Sheet 4 vintage-PCIA table (2009–2026) from the source PDF is NOT yet in this filing. The URPX-team-authored fixture didn't include a vintage-PCIA `RatePlanModifier`; we carry that omission for now. Follow-up to add a vintage PCIA modifier (matching the pattern in our other PG&E filings) is tracked at grid-coordination/urpx-tariffs#9.

## Provenance

Authored by the URPX team (Flux Tailor — Una Smith-Simon et al.) and present in the `urpx-org/urpx` repo since the initial v0.1.1 pre-draft commit (`12eaa7f`, 2026-01); subsequent updates by Una and Klaartje De Schepper carried it through the v0.2.0-candidate branch. The `urpx-org/urpx` v0.2.0-candidate fixture (test-cases/pge-e-elec-2026-01-01/) uses an intermediate v0.2.0 vocabulary that has since been superseded (ConditionLogic / ObjectTerminalNode / CustomTerminalNode → ConditionExpression / ObjectOperandNode / CustomOperandNode per Decisions #097/098). Brought into `urpx-tariffs` and migrated to the current v0.2.0 form on 2026-04-29 via `shadow-repo/scripts/migrate-pge-e-elec-v020.py`.

## URL-mutation note

The canonical PG&E URL `https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_SCHEDS_E-ELEC.pdf` now serves a different PDF (sha256 `09b55962...`, 577 KB) than the one committed here (sha256 `56f39462...`, 431 KB; retrieved 2026-01-05). The committed PDF is the original the URPX team extracted from when they authored the v0.1.x fixture. PG&E reissued E-ELEC under AL 7869-E / D.26-03-013 effective 2026-03-27 (the same advice letter that did E-TOU-C / E-TOU-D / EV2). The 2026-03-27 reissue is now modeled as a sibling filing at `../2026-03-27/`; this 2026-01-01 filing is preserved for historical price resolution (e.g. for instants prior to 2026-03-27).

## Validation

```
# Run from the urpx-tariffs project root:
pyshacl -s ../urpx/shacl/urpx-shacl.ttl \
        -e ../urpx/ontology/urpx-ontology.ttl \
        -df json-ld \
        ca/iou/pge/e-elec/versions/2026-01-01/rate-plan_pge_e-elec_2026-01-01.jsonld
# Conforms: True
```

End-to-end via clj-urpx: `clojure -M:validate` (load + coerce + resolve, all clean).

## Note on the "dynamic / hourly pricing" question

The published E-ELEC tariff is **TOU**, not dynamic pricing. Sheet 5 Special Condition 6 mentions a hypothetical "real-time pricing program" under PU Code 353.3 but explicitly says it isn't yet available; customers must take service on a TOU schedule. So the URPX modeling is straight TOU, mirroring our E-TOU-C / E-TOU-D / EV2 patterns.
