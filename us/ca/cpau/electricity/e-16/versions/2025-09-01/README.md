# CPAU E-16 — effective 2025-09-01

City of Palo Alto Utilities **Schedule E-16: Unmetered Electric Service**.

## Files

- `cpau_e-16_2025-09-01.pdf` — source PDF (sha256 in `tariff.toml`)
- `tariff.toml` — provenance, source URL + sha256, regulator, validation status
- `rate-plan_cpau_e-16_2025-09-01.jsonld` — URPX rate-plan serialization

## Notes

For customers contracting with CPAU for **unmetered** electric service: billboards, telephone services, railroad signals, cathodic protection, traffic cameras, wireless antennas, cable TV power supplies, irrigation systems, and miscellaneous unmetered services (Section A).

**Partial modeling — customer charge only.** Modeled structurally:
- Customer charge: $10.96/month (Section C.1, also serves as Section C.3 minimum charge).

**Not modeled structurally — see prose**:
- **Section C.2 energy charge** is published as *"using Electric Rate Schedule E-2 plus all applicable riders"* — a cross-schedule reference for which we couldn't figure out a structural URPX pattern. The energy charge is described in prose only. Consumers needing a full E-16 bill must combine this filing with [`cpau:e-2`](../../../e-2/versions/2025-07-01/) and the applicable riders (E-HRA, E-EEC-1, E-NSE-1 as relevant to the customer).
- **Section D estimation method** for unmetered customers (kWh estimated from Total Wattage × annual operating hours / 1000 / 12). Documented in prose; the calculation is performed by the operator on a per-customer basis from the customer-supplied equipment inventory.
- **Section E miscellaneous fees** (license fees for conduit usage, utility pole attachments, communication equipment mounting; CPI-indexed per Section F). Annual rather than monthly, applies to physical infrastructure rather than energy service. Deferred to a follow-up bd issue.

The cross-schedule reference question parallels [`urpx-org/urpx#23`](https://github.com/urpx-org/urpx/issues/23) (modifier-to-base linkage) — both involve cross-file structural references in URPX. Filing a separate upstream URPX issue for the cross-RatePlan energy-charge reference is deferred until #23 resolves to see whether the URPX-team's pattern for #23 also covers this case.

## Provenance

DCJ-authored, generated from scratch by `scripts/build-cpau-e-16-2025-09-01.py` on 2026-04-30. Source PDF retrieved from paloalto.gov via curl_cffi.

## Validation

```
dev/shacl.sh --utility cpau
```

End-to-end via clj-urpx: `clojure -M:validate` reports load+coerce+validate clean.
