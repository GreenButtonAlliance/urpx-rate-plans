# urpx-rate-plans

A corpus of **URPX rate plans** curated from electric utility tariff filings, including the tariff documents themselves.

Each rate plan is expressed in the [URPX ontology](https://github.com/urpx-org/urpx): a machine-readable, validatable statement of everything needed to calculate what a customer is charged. A filing directory holds the tariff document, a `tariff.toml` provenance manifest, and the rate plan itself, serialized as JSON-LD.

> **Terminology (per [URPX](https://github.com/urpx-org/urpx/blob/main/CONTRIBUTING.md#terminology-and-language-use))**: a *tariff* is the regulatory document, such as a tariff book, containing one or more rate plans; a *rate plan* is the complete set of parameters needed to calculate what a customer is charged, including prices, TOU schedules, service tiers, seasonal variation and eligibility rules; a *rate* is a single price value, incomplete without the rate plan around it. What this corpus curates is rate plans. It keeps the tariff documents they were read from because those are the evidence, and because utilities remove them.

**This repo is a work in progress.** It is driven by an expanding set of [Big Hairy Audacious Goals (BHAGs)](https://www.jimcollins.com/concepts/bhag.html). The first BHAG is **model every California residential rate plan**. We are working incrementally toward that goal in priority order — the rate plans serving the most customers first, niche schedules later.

The initial motivation is to enable the [Grid Coordination Price Server](https://github.com/grid-coordination/price-server-user-guide) to ingest these URPX rate plans and publish [OpenADR 3](https://www.openadr.org/) programs and *computed* prices derived from the rate-plan structures. The price server is the consumer; this corpus is the source of truth for what the underlying tariffs say.

**Current focus & priority: California electricity.** Every organization the CEC MIDAS feed carries as selling electricity in the state is catalogued in [`reports/california-parties.md`](./reports/california-parties.md), which carries its own as-of date. The directory hierarchy is jurisdiction-first (`us/ca/...`, `us/wa/...`), so other states and other countries can be added without restructuring. Washington has discovery manifests for Seattle City Light and Puget Sound Energy and no filing yet.

## Disclaimer

We are URPX **newbies** — definitely not URPX experts. Despite reading the [URPX ontology](https://github.com/urpx-org/urpx), the [SHACL shapes](https://github.com/urpx-org/urpx/tree/main/shacl), and the published [test cases](https://github.com/urpx-org/urpx/tree/main/test-cases) carefully, our modeling of these tariffs as URPX rate plans is a **best-effort interpretation** that has not been reviewed or deemed reasonable/accurate by the URPX authors. Some rate plans will be wrong in non-obvious ways. If you spot a modeling error — a misused class, a rate component placed in the wrong ledger, an `urpx:chargeType` that should be something else — please tell us (see [Contributing](#contributing)).

Each filing directory's `tariff.toml` documents what's modeled, what's deferred, and any known gaps. The [Status](#status) section below summarizes corpus-wide fidelity.

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

`<carrier>` is the commodity, currently always `electricity`, mirroring `urpx:commodity`, which every rate plan carries. The tariff document is committed beside the rate plan read from it ([LAYOUT.md §7](./LAYOUT.md#7-source-pdf-referencing)).

Each `<country>/<subdivision>/<utility>/` directory also carries a `utility.toml` discovery manifest listing the URLs where the utility publishes its tariffs ([LAYOUT.md §5](./LAYOUT.md#5-per-utility-discovery-manifest-utilitytoml)).

To enumerate the corpus from code, read [`corpus.json`](./corpus.json) or run one of the walkers it lists, in Python, Clojure, babashka or bash ([LAYOUT.md §3b](./LAYOUT.md#3b-walking-the-corpus-corpusjson)).

### Scenario cost models

A **scenario cost model** is URPX's `urpx:ScenarioCostModel`, read as a fully determined selection over the plan space: one `urpx:RatePlanVersion`, plus the `urpx:RatePlanModifierVersion`s applied to it, plus one `urpx:ProfileAlternative` for each dimension any of them leaves open. *Fully determined* means nothing remains to choose: given an instant inside its window it resolves to prices with no further input. If a choice is still outstanding it is not one scenario cost model but several.

A rate plan is what a utility publishes. A scenario cost model is what a particular customer is billed under, and a plan generally admits many. It is the unit a price server publishes as an OpenADR 3 program and an energy-management system subscribes to.

The properties that let a `urpx:ScenarioCostModel` name the modifier versions and alternatives it selects, `urpx:consumesModifierVersion` and `urpx:selectsProfileAlternative`, are proposed in [urpx-org/urpx#72](https://github.com/urpx-org/urpx/pull/72) and are not yet in a URPX release. [doc/scenario-cost-models.md](./doc/scenario-cost-models.md) gives the full definition: what determines one, what makes two distinct, what makes one current, and how its IRI is derived.

[`reports/scenario-cost-models.jsonld`](./reports/scenario-cost-models.jsonld) carries one `urpx:ScenarioCostModel` node per current scenario cost model the corpus can defend, at the grain of one base plan plus at most one modifier. [`reports/scenario-cost-models.{md,edn}`](./reports/) reports, for each composition they expand from, whether a price server asking for a price gets a number back, and names each model by IRI. [`reports/ready-for-use.md`](./reports/ready-for-use.md) rolls that up per filing. None of these is written into a filing.

### Reading more than one filing at a time

A modifier filing names the base rate plans it applies to, and those live in their own filings, so the corpus is read as one graph rather than a file at a time. Validating a modifier alone reports unresolved references; that is the modifier working, not a defect. [`reports/modifier-base-pairings.{json,edn}`](./reports/) indexes the pairings both ways, by modifier and by base.

Version order comes from each filing's `versions/<date>/` and `urpx:effectiveDateTime`, not from a link between versions ([LAYOUT.md §10](./LAYOUT.md#10-future-considerations)).

## Status

As of 2026-09-23, 71 filings hold 72 rate plans: 39 base plans and 33 standalone modifiers. One directory, PG&E E-TOU-C 2026-03-01, packages a base with a sibling modifier, and four PG&E vintage-PCIA modifiers are bundled inline in their bases' `@graph`.

Every filing serializes against URPX v0.5.1 and validates clean under both `pyshacl` against the [URPX SHACL shapes](https://github.com/urpx-org/urpx/blob/main/shacl/urpx-shacl.ttl) and [clj-urpx](https://github.com/grid-coordination/clj-urpx), which loads, coerces and resolves a price at a known instant.

Residential reach, per state and in total, is in [`reports/coverage.md`](./reports/coverage.md).

**Cross-corpus utility identification**: every rate plan's `urpx:offeredBy` `urpx:UtilityOperator` carries an `urpx:OrganizationIdentifier` whose `urpx:scheme` is `urpx:eiaScheme`; PG&E's `skos:notation` is 14328. All 72 carry one. It is a stable join key against the [EIA-861 detailed data files](https://www.eia.gov/electricity/data/eia861/), which avoids matching on `legalName` variants.

**SHACL-validating ≠ bill-calculation-complete.** All filings pass pyshacl + [clj-urpx](https://github.com/grid-coordination/clj-urpx), but most carry at least one documented modeling deferral tied to an open URPX vocabulary question. Each filing's `tariff.toml [modeling].deferrals` lists what's deferred and why; the [MODELING-GAPS.md](./MODELING-GAPS.md) section below cross-references them.

### How well each rate plan is modeled

Three levels, and the distinction is about whether a bill comes out right, not about whether the JSON-LD validates. Every filing validates.

- **Models the published rate-of-record.** The bill calculation for the typical residential case is correct. Most of these carry a minor deferral of their own, recorded in that filing's `tariff.toml [modeling].deferrals`.
- **Substantial economic effect deferred to prose.** Something a customer would notice on the bill is described in the filing's prose rather than computed: SMUD EAPR's income-tier usage discount, and event-day evaluation on the two CPP filings, which needs caller-supplied event state.
- **Unpriced export credit.** LADWP NEM compensates exported energy at "the applicable Rate Schedule energy pricing", a phrase its ordinance leaves undefined, and carries the credit's `PriceDefinition` with no `Price` until a source settles which base price that means. The shape is settled: one credit `Price` per base energy `Price`, each naming a single `urpx:basedOnPrice` with a `urpx:multiplier` of -1 and no `urpx:unitPrice`. SMUD NEM1 ships its twelve cells that way; LADWP's 18 are listed in [MODELING-GAPS.md](./MODELING-GAPS.md).

Where the rest is answered:

| Question | Where it is answered |
|---|---|
| Can a price server get a price out of this filing? | [`reports/ready-for-use.md`](./reports/ready-for-use.md), generated |
| Which scenario cost models resolve, and at what instants? | [`reports/scenario-cost-models.md`](./reports/scenario-cost-models.md), generated |
| How many customers do the modeled plans reach? | [`reports/coverage.md`](./reports/coverage.md), generated |
| What can URPX not express, and what have we not converted? | [MODELING-GAPS.md](./MODELING-GAPS.md) |
| What has this filing deferred? | that filing's `tariff.toml [modeling].deferrals` |

### Modeling gaps

What this corpus cannot express in URPX v0.5.1, and what it has not yet converted, are tracked in [MODELING-GAPS.md](./MODELING-GAPS.md).

### Utilities covered

As of 2026-09-23, six utilities have filings, all in California: PG&E, SCE and SDG&E, the three investor-owned; and LADWP, SMUD and CPAU, publicly owned. Others have a discovery manifest and no filing yet, which is a normal state and not an incomplete one.

[`reports/rate-plans-to-model.md`](./reports/rate-plans-to-model.md) has the per-schedule detail for the three utilities whose own schedule list has been read. CPAU and LADWP have no inventory source yet, so nothing there bounds their backlog. [`reports/california-parties.md`](./reports/california-parties.md) lists every organization the CEC MIDAS feed carries. CPAU sells here and MIDAS does not carry it, so a seller absent from that report is not necessarily absent from California.

## Contributing

Issues, Discussions, and pull requests are welcome — see [CONTRIBUTING.md](./CONTRIBUTING.md) for the workflow. In short:

- **Modeling questions, ideas, suggestions** → [Discussions](https://github.com/grid-coordination/urpx-rate-plans/discussions)
- **Confirmed modeling errors, unmodeled rate plans, manifest schema bugs** → [Issues](https://github.com/grid-coordination/urpx-rate-plans/issues)
- **Patches** → pull requests; please open a Discussion or Issue first for non-trivial changes (new utilities, new modifier shapes, manifest-schema changes)

If you have URPX modeling expertise and would like to review what we have, please get in touch — the [Disclaimer](#disclaimer) above is not aspirational, we genuinely could use the help.

## License

This repository is REUSE-compliant. See [`LICENSE`](./LICENSE), [`LICENSES/`](./LICENSES/), and [`REUSE.toml`](./REUSE.toml) for the authoritative declarations.

In summary:

- **Rate-plan JSON-LD serializations, manifests (`tariff.toml`, `utility.toml`), JSON Schemas, prose documentation (`README.md`, `LAYOUT.md`, `CONTRIBUTING.md`), and code (everything under `dev/` and `scripts/`)** — [Community Data License Agreement — Permissive — Version 2.0](https://cdla.dev/permissive-2-0/) (`CDLA-Permissive-2.0`), Copyright (c) 2026 Clark Communications Corporation.
- **Committed source tariff PDFs** — `LicenseRef-PublicRecord`. These are utility tariff filings and published rate schedules, filed with a public regulator, or adopted by a municipal utility's city council or governing board (CPUC advice letters, municipal-utility rate schedules). They are vendored here as source documents for the serializations extracted from them. **This repository claims no copyright in them.** The `SPDX-FileCopyrightText` names the issuing utility for provenance only. Where copyright subsists, if it does, it rests with the filer; this repository makes no determination either way. The identifier and its text follow [`urpx-org/urpx`](https://github.com/urpx-org/urpx/blob/main/LICENSES/LicenseRef-PublicRecord.txt), which uses the same one for the same class of document, so scanners classify mixed checkouts consistently.
- **`us/ca/pge/electricity/e-elec/versions/2026-01-01/rate-plan_pge_e-elec_2026-01-01.jsonld`** — same `CDLA-Permissive-2.0`, with copyright held jointly by `Flux Tailor LLC`, which originated the upstream fixture in `urpx-org/urpx`, and Clark Communications Corporation, which built on it here.

CDLA-Permissive-2.0 is the same license URPX uses for its test-case dataset content (`urpx-org/urpx/test-cases/`) — so files can flow between the two repos without license conversion.
