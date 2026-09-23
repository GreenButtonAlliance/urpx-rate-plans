# urpx-rate-plans

A corpus of **URPX rate plans**, curated from electric utility tariff filings and kept with the tariff documents they were read from.

Each rate plan is expressed in the [URPX ontology](https://github.com/urpx-org/urpx): a machine-readable, validatable statement of everything needed to calculate what a customer is charged. A filing directory holds the tariff document, a `tariff.toml` provenance manifest, and the rate plan itself, serialized as JSON-LD.

> **Terminology (per [URPX](https://github.com/urpx-org/urpx/blob/main/CONTRIBUTING.md#terminology-and-language-use))**: a *tariff* is the regulatory document, such as a tariff book, containing one or more rate plans; a *rate plan* is the complete set of parameters needed to calculate what a customer is charged, including prices, TOU schedules, service tiers, seasonal variation and eligibility rules; a *rate* is a single price value, incomplete without the rate plan around it. What this corpus curates is rate plans. It keeps the tariff documents they were read from because those are the evidence, and because utilities remove them.

**This repo is a work in progress.** It is driven by an expanding set of [Big Hairy Audacious Goals (BHAGs)](https://www.jimcollins.com/concepts/bhag.html). The first BHAG is **model every California residential rate plan**. We are working incrementally toward that goal in priority order — the rate plans serving the most customers first, niche schedules later.

The initial motivation is to enable the [Grid Coordination Price Server](https://github.com/grid-coordination/price-server-user-guide) to ingest these URPX rate plans and publish [OpenADR 3](https://www.openadr.org/) programs and *computed* prices derived from the tariff structures. The price server is the consumer; this corpus is the source of truth for what the underlying tariffs say.

**Current scope: California electricity.** Twenty organizations are catalogued: three investor-owned utilities, three publicly owned, and fourteen community choice aggregators. The directory hierarchy is jurisdiction-first (`us/ca/...`), so other states and other countries can be added without restructuring. The country segment is spelled out because a bare `ca` reads as either California or Canada.

## Disclaimer

We are URPX **newbies** — definitely not URPX experts. Despite reading the [URPX ontology](https://github.com/urpx-org/urpx), the [SHACL shapes](https://github.com/urpx-org/urpx/tree/main/shacl), and the published [test cases](https://github.com/urpx-org/urpx/tree/main/test-cases) carefully, our modeling of these tariffs as URPX rate plans is a **best-effort interpretation** that has not been reviewed or deemed reasonable/accurate by the URPX authors. Some rate plans will be wrong in non-obvious ways. If you spot a modeling error — a misused class, a rate component placed in the wrong ledger, an `urpx:chargeType` that should be something else — please tell us (see [Contributing](#contributing)).

Each filing directory's `tariff.toml` documents what's modeled, what's deferred, and any known gaps. The [Status](#status) table below summarizes corpus-wide fidelity.

## Layout

See [LAYOUT.md](./LAYOUT.md) for the full conventions. In short:

```
<country>/<subdivision>/<utility>/<carrier>/<schedule>/versions/<effective-date>/
  e.g.  us/ca/pge/electricity/e-tou-c/versions/2026-03-01/
  <utility>_<schedule>_<date>.pdf                             # source tariff document
  tariff.toml                                                 # per-filing provenance manifest
  rate-plan_<utility>_<schedule>_<date>.jsonld                # URPX rate-plan serialization, OR
  rate-plan-modifier_<utility>_<schedule>_<date>.jsonld       # for standalone rider/overlay rate plans
```

`<carrier>` is the commodity, currently always `electricity`; it sits below `<utility>` because PG&E and SDG&E supply both gas and electricity, and a utility's offerings should stay adjacent. It mirrors `urpx:commodity`, which each filing also carries. Source tariff PDFs are committed alongside each rate plan — see [LAYOUT.md §7](./LAYOUT.md#7-source-pdf-referencing) for the rationale (canonical URLs alone are not durable provenance; PG&E updated `ELEC_SCHEDS_E-TOU-C.pdf` in place between two retrievals two days apart).

Each `<country>/<subdivision>/<utility>/` directory also carries a `utility.toml` discovery manifest listing the URLs where the utility publishes its tariffs ([LAYOUT.md §5](./LAYOUT.md#5-per-utility-discovery-manifest-utilitytoml)).

### Service arrangements

A **service arrangement** is a fully determined selection over the plan space: one `urpx:RatePlanVersion`, plus every `urpx:RatePlanModifierVersion` that applies to it and that the customer has, plus one `urpx:ProfileAlternative` for each dimension any of them leaves open. *Fully determined* means nothing remains to choose: given an instant inside its window it resolves to prices with no further input. If a choice is still outstanding it is not one arrangement but several.

A rate plan is what a utility publishes. An arrangement is what a particular customer is billed under, and a plan generally admits many. It is the unit a price server publishes and an energy-management system subscribes to.

***Service arrangement* is this corpus's term, not URPX vocabulary.** URPX names every part of an arrangement and no whole of it, so the term stays local: it is never written into a filing and never carries a `urpx:` prefix. [doc/service-arrangements.md](./doc/service-arrangements.md) gives the full definition: what determines an arrangement, what makes two distinct, and what makes one current.

[`reports/service-arrangements.{md,edn}`](./reports/) enumerates the arrangements the corpus expresses and reports, for each, whether a price server asking for a price gets a number back. [`reports/ready-for-use.md`](./reports/ready-for-use.md) rolls that up per filing.

### Reading more than one filing at a time

A modifier filing names the base rate plans it applies to, and those live in their own filings. So the corpus is read as one graph rather than a file at a time: validating a modifier on its own reports unresolved references, which is the modifier doing its job, not a defect. [`reports/modifier-base-pairings.{json,edn}`](./reports/) gives those pairings as a flat map for anyone who wants the answer without walking the graph.

Version order is carried by each filing's `versions/<date>/` and by `urpx:effectiveDateTime`. There is no link from a version to the one it replaced; [LAYOUT.md §10](./LAYOUT.md#10-future-considerations) explains why URPX v0.5.1 cannot carry one.

## Status

73 filings landed (40 `urpx:RatePlan` + 33 standalone `urpx:RatePlanModifier`; one filing — PG&E E-TOU-C 2026-03-01 — packages a base alongside a sibling modifier in the same directory, plus 4 PG&E vintage-PCIA modifiers are bundled inline inside their bases' `@graph`). All filings serialize against URPX v0.5.1 and validate clean via both `pyshacl` against the [URPX SHACL shapes](https://github.com/urpx-org/urpx/blob/main/shacl/urpx-shacl.ttl) and [clj-urpx](https://github.com/grid-coordination/clj-urpx) (load → coerce → resolve a representative price for a known instant; see `dev/validate_v020.clj`).

**Statewide residential coverage**: ~91% (90.8%) of the 15M California residential customers tracked in `dev/coverage-estimates.toml` are served by a base RatePlan that is structurally modeled. Run `python dev/coverage.py` for the live breakdown.

**Cross-corpus utility identification**: every filing's `publishedBy` Organization carries `urpx:eiaId` (PG&E 14328, SCE 17609, SDG&E 16609, LADWP 11208, SMUD 16534, CPAU 3203) — usable as a stable join key against the EIA-861 utility dataset without parsing legalName variants.

**SHACL-validating ≠ bill-calculation-complete.** All filings pass pyshacl + [clj-urpx](https://github.com/grid-coordination/clj-urpx), but most carry at least one documented modeling deferral tied to an open URPX vocabulary question. Each rate plan's `tariff.toml [extraction.notes]` lists what's deferred and why; the [MODELING-GAPS.md](./MODELING-GAPS.md) section below cross-references them.

### How well each rate plan is modeled

Three levels, and the distinction is about whether a bill comes out right, not about whether the JSON-LD validates. Every filing validates.

- **Models the published rate-of-record.** The bill calculation for the typical residential case is correct. Most of these carry a minor deferral of their own, recorded in that filing's `tariff.toml [extraction.notes]`.
- **Substantial economic effect deferred to prose.** Something a customer would notice on the bill is described in the filing's prose rather than computed: SMUD EAPR's income-tier usage discount, and event-day evaluation on the two CPP filings, which needs caller-supplied event state.
- **Placeholder price.** LADWP NEM and SMUD NEM1 compensate exported energy at the customer's own applicable base-rate energy charge, which we have not found a way to express. Both carry a `Price` of `0` for SHACL conformance and a coverage claim saying that zero must not be read as a zero-value export. Asked upstream at [urpx-org/urpx discussion #63](https://github.com/urpx-org/urpx/discussions/63).

The corpus holds 72 rate plans across 71 filings: 39 base plans and 33 modifiers.

Rather than restate any of it here, where it goes stale:

| Question | Where it is answered |
|---|---|
| Can a price server get a price out of this filing? | [`reports/ready-for-use.md`](./reports/ready-for-use.md), generated |
| Which service arrangements resolve, and at what instants? | [`reports/service-arrangements.md`](./reports/service-arrangements.md), generated |
| How many customers do the modeled plans reach? | [`reports/coverage.md`](./reports/coverage.md), generated |
| What can URPX not express, and what have we not converted? | [MODELING-GAPS.md](./MODELING-GAPS.md) |
| What has this filing deferred? | that filing's `tariff.toml [extraction.notes]` |

### Modeling gaps

What this corpus cannot express in URPX v0.5.1, and what it has not yet converted, are tracked in [MODELING-GAPS.md](./MODELING-GAPS.md).

### Utilities covered

Six utilities have filings: PG&E, SCE and SDG&E, the three investor-owned; and LADWP, SMUD and CPAU, publicly owned. Together they cover 63 schedules across 71 filings. Fifteen more organizations have a discovery manifest and no filing yet, fourteen community choice aggregators and one municipal utility; that is a normal state, not an incomplete one.

[`reports/rate-plans-to-model.md`](./reports/rate-plans-to-model.md) has the per-schedule detail, including which of each utility's published schedules are still unmodeled. [`reports/california-parties.md`](./reports/california-parties.md) lists every organization selling electricity in California.

## Contributing

Issues, Discussions, and pull requests are welcome — see [CONTRIBUTING.md](./CONTRIBUTING.md) for the workflow. In short:

- **Modeling questions, ideas, suggestions** → [Discussions](https://github.com/grid-coordination/urpx-rate-plans/discussions)
- **Confirmed modeling errors, missing tariffs, manifest schema bugs** → [Issues](https://github.com/grid-coordination/urpx-rate-plans/issues)
- **Patches** → pull requests; please open a Discussion or Issue first for non-trivial changes (new utilities, new modifier shapes, manifest-schema changes)

If you have URPX modeling expertise and would like to review what we have, please get in touch — the [Disclaimer](#disclaimer) above is not aspirational, we genuinely could use the help.

## License

This repository is REUSE-compliant. See [`LICENSE`](./LICENSE), [`LICENSES/`](./LICENSES/), and [`REUSE.toml`](./REUSE.toml) for the authoritative declarations.

In summary:

- **Rate-plan JSON-LD serializations, manifests (`tariff.toml`, `utility.toml`), JSON Schemas, prose documentation (`README.md`, `LAYOUT.md`, `CONTRIBUTING.md`), and code (`dev/*.clj`, `dev/*.py`)** — [Community Data License Agreement — Permissive — Version 2.0](https://cdla.dev/permissive-2-0/) (`CDLA-Permissive-2.0`), Copyright (c) 2026 Clark Communications Corporation.
- **Committed source tariff PDFs** — `LicenseRef-PublicRecord`. These are utility tariff filings and published rate schedules, filed with a public regulator or adopted by city ordinance (CPUC advice letters, municipal-utility rate schedules). They are vendored here as source documents for the serializations extracted from them. **This repository claims no copyright in them.** The `SPDX-FileCopyrightText` names the issuing utility for provenance only. Where copyright subsists, if it does, it rests with the filer; this repository makes no determination either way. The identifier and its text follow [`urpx-org/urpx`](https://github.com/urpx-org/urpx/blob/main/LICENSES/LicenseRef-PublicRecord.txt), which uses the same one for the same class of document, so scanners classify mixed checkouts consistently.
- **`us/ca/pge/electricity/e-elec/versions/2026-01-01/rate-plan_pge_e-elec_2026-01-01.jsonld`** — same `CDLA-Permissive-2.0`, with copyright held jointly by `Flux Tailor LLC`, which originated the upstream fixture in `urpx-org/urpx`, and Clark Communications Corporation, which built on it here.

CDLA-Permissive-2.0 is the same license URPX uses for its test-case dataset content (`urpx-org/urpx/test-cases/`) — so files can flow between the two repos without license conversion.
