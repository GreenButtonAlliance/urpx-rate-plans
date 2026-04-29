# urpx-tariffs

A corpus of utility electric **tariff documents** (the regulatory PDFs) and **URPX rate-plan serializations** (the structured JSON-LD extracted from them).

The serializations use the [URPX ontology](https://github.com/urpx-org/urpx) — a machine-readable, validatable representation of each rate plan. Each filing directory holds the source PDF, a `tariff.toml` provenance manifest, and one `urpx:RatePlan` JSON-LD file.

> **Terminology (per [URPX](https://github.com/urpx-org/urpx/blob/main/CONTRIBUTING.md#terminology-and-language-use))**: a *tariff* is the regulatory document (e.g. a tariff book); a *rate plan* is the parameter package (prices, TOU schedules, tiers, eligibility); a *rate* is a single price value. The repo name is shorthand — the structured artifact under each filing is a rate plan.

**Current scope: California** — coverage of California utilities across all classes (investor-owned, publicly-owned, cooperative, community choice aggregator). The directory hierarchy is jurisdiction-first (`ca/...`) so additional states can be added without restructuring.

## Layout

See [LAYOUT.md](./LAYOUT.md) for the full conventions. In short:

```
ca/<class>/<utility>/<schedule>/versions/<effective-date>/
  <utility>_<schedule>_<date>.pdf                # source tariff document
  tariff.toml                                    # per-filing provenance manifest
  rate-plan_<utility>_<schedule>_<date>.jsonld   # URPX rate-plan serialization
```

`<class>` is one of `iou`, `pou`, `coop`, `cca`. Source tariff PDFs are committed alongside each rate plan — see [LAYOUT.md §7](./LAYOUT.md#7-source-pdf-referencing) for the rationale (canonical URLs alone are not durable provenance; PG&E updated `ELEC_SCHEDS_E-TOU-C.pdf` in place between two retrievals two days apart).

Each `<class>/<utility>/` directory also carries a `utility.toml` discovery manifest listing the URLs where the utility publishes its tariffs ([LAYOUT.md §5](./LAYOUT.md#5-per-utility-discovery-manifest-utilitytoml)).

## Status

Ten filings shipped, all serialized against URPX v0.2.0-candidate and validating clean via both `pyshacl` (SHACL conformance) and `clj-urpx` (load → coerce → resolve a representative price for a known instant; see `dev/validate_v020.clj`):

| Utility | Class | Schedules covered |
|---|---|---|
| PG&E   | `ca/iou/pge/`  | E-1, E-TOU-C (2026-03-01 + 2026-03-27 reissue), E-TOU-D, EV2, E-ELEC (2026-01-01 + 2026-03-27 reissue) |
| CPAU   | `ca/pou/cpau/` | E-1 (2025-07-01 + 2025-09-01 multi-source snapshot), E-1-TOU |

Manifest infrastructure: per-filing `tariff.toml` (with both single-source and multi-source variants — the latter for self-contained `@graph`s referencing multiple source PDFs), and per-utility `utility.toml` capturing tariff-discovery URLs. Schemas live under [`schema/`](./schema/).

Outstanding work — including 3 CPAU modifier-only filings, the full-baseline-matrix expansion of E-1, `urpx:supersedes` lineage adoption, and a cross-filing consistency linter — is tracked in the [issues list](https://github.com/grid-coordination/urpx-tariffs/issues).

## License

This repository is REUSE-compliant. See [`LICENSE`](./LICENSE), [`LICENSES/`](./LICENSES/), and [`REUSE.toml`](./REUSE.toml) for the authoritative declarations.

In summary:

- **Rate-plan JSON-LD serializations, manifests (`tariff.toml`, `utility.toml`), JSON Schemas, prose documentation (`README.md`, `LAYOUT.md`), and code (`dev/*.clj`)** — [Community Data License Agreement — Permissive — Version 2.0](https://cdla.dev/permissive-2-0/) (`CDLA-Permissive-2.0`), Copyright (c) 2026 Clark Communications Corporation.
- **Committed source tariff PDFs** — `LicenseRef-PublicRecord`. Public regulatory documents (CPUC tariff filings, municipal-utility rate schedules adopted by city ordinance) are factual records of governmental processes and not subject to copyright. Copyright text attributes the issuing utility for provenance only, not as an assertion of ownership.
- **`ca/iou/pge/e-elec/versions/2026-01-01/rate-plan_pge_e-elec_2026-01-01.jsonld`** — same `CDLA-Permissive-2.0`, with copyright held jointly by `Flux Tailor LLC` (originator of the upstream v0.1.x test-case fixture in `urpx-org/urpx`) and Clark Communications Corporation (the v0.2.0 migration in this repo).

The CDLA-Permissive-2.0 choice harmonizes with the license of the upstream `urpx-org/urpx` datasets.
