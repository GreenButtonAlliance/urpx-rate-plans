# urpx-tariffs

A corpus of utility electric **tariff documents** (the regulatory PDFs) and **URPX rate-plan serializations** (the structured JSON-LD extracted from them).

This repo is a sibling of the [URPX ontology repo](https://github.com/urpx-org/urpx) and uses URPX to express each tariff's rate plan in a machine-readable, validatable form. Each filing directory holds the source tariff PDF, a `tariff.toml` provenance manifest, and one `urpx:RatePlan` JSON-LD file.

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

`<class>` is one of `iou`, `pou`, `coop`, `cca`. Source tariff PDFs are committed alongside each rate plan — see [LAYOUT.md §6](./LAYOUT.md#6-source-pdf-referencing) for the rationale (canonical URLs alone are not durable provenance; PG&E updated `ELEC_SCHEDS_E-TOU-C.pdf` in place between two retrievals two days apart).

## Status

Initial corpus: PG&E residential schedules — E-1, E-TOU-C (2026-03-01 + 2026-03-27 versions), E-TOU-D, EV2 — all migrated to URPX v0.2.0-candidate and validating clean via both `pyshacl` and `clj-urpx`. Migration tracked at [#1](https://github.com/grid-coordination/urpx-tariffs/issues/1); follow-up work at [#2](https://github.com/grid-coordination/urpx-tariffs/issues/2)–[#7](https://github.com/grid-coordination/urpx-tariffs/issues/7).

## License

Each tariff is a public regulatory document. The URPX serializations and manifests in this repo are released under CC0.
