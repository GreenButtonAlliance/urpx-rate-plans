# urpx-tariffs

A corpus of utility electric **tariff documents** (the regulatory PDFs) and **URPX rate-plan serializations** (the structured JSON-LD extracted from them).

The serializations use the [URPX ontology](https://github.com/urpx-org/urpx) — a machine-readable, validatable representation of each rate plan. Each filing directory holds the source PDF, a `tariff.toml` provenance manifest, and one `urpx:RatePlan` (or `urpx:RatePlanModifier`) JSON-LD file.

> **Terminology (per [URPX](https://github.com/urpx-org/urpx/blob/main/CONTRIBUTING.md#terminology-and-language-use))**: a *tariff* is the regulatory document (e.g. a tariff book); a *rate plan* is the parameter package (prices, TOU schedules, tiers, eligibility); a *rate* is a single price value. The repo name is shorthand — the structured artifact under each filing is a rate plan.

**This repo is a work in progress.** It is driven by an expanding set of [Big Hairy Audacious Goals (BHAGs)](https://www.jimcollins.com/concepts/bhag.html). The first BHAG is **model all California residential tariffs**. We are working incrementally toward that goal in priority order — the rate plans serving the most customers first, niche schedules later.

The initial motivation is to enable the [Grid Coordination Price Server](https://github.com/grid-coordination/price-server-user-guide) to ingest these URPX rate plans and publish [OpenADR 3](https://www.openadr.org/) programs and *computed* prices derived from the tariff structures. The price server is the consumer; this corpus is the source of truth for what the underlying tariffs say.

**Current scope: California** — coverage of California utilities across all classes (investor-owned, publicly-owned, cooperative, community choice aggregator). The directory hierarchy is jurisdiction-first (`ca/...`) so additional states can be added without restructuring.

## Disclaimer

We are URPX **newbies** — definitely not URPX experts. Despite reading the [URPX ontology](https://github.com/urpx-org/urpx), the [SHACL shapes](https://github.com/urpx-org/urpx/tree/main/shacl), and the published [test cases](https://github.com/urpx-org/urpx/tree/main/test-cases) carefully, our modeling of these tariffs as URPX rate plans is a **best-effort interpretation** that has not been reviewed or deemed reasonable/accurate by the URPX authors. Some rate plans will be wrong in non-obvious ways. If you spot a modeling error — a misused class, a rate component placed in the wrong ledger, an `urpx:chargeType` that should be something else — please tell us (see [Contributing](#contributing)).

Each filing directory's `tariff.toml` documents what's modeled, what's deferred, and any known gaps. The [Status](#status) table below summarizes corpus-wide fidelity.

## Layout

See [LAYOUT.md](./LAYOUT.md) for the full conventions. In short:

```
ca/<class>/<utility>/<schedule>/versions/<effective-date>/
  <utility>_<schedule>_<date>.pdf                             # source tariff document
  tariff.toml                                                 # per-filing provenance manifest
  rate-plan_<utility>_<schedule>_<date>.jsonld                # URPX rate-plan serialization, OR
  rate-plan-modifier_<utility>_<schedule>_<date>.jsonld       # for standalone rider/overlay rate plans
```

`<class>` is one of `iou`, `pou`, `coop`, `cca`. Source tariff PDFs are committed alongside each rate plan — see [LAYOUT.md §7](./LAYOUT.md#7-source-pdf-referencing) for the rationale (canonical URLs alone are not durable provenance; PG&E updated `ELEC_SCHEDS_E-TOU-C.pdf` in place between two retrievals two days apart).

Each `<class>/<utility>/` directory also carries a `utility.toml` discovery manifest listing the URLs where the utility publishes its tariffs ([LAYOUT.md §5](./LAYOUT.md#5-per-utility-discovery-manifest-utilitytoml)).

## Status

45 rate plans landed (32 `urpx:RatePlan` + 13 `urpx:RatePlanModifier`), all serialized against URPX v0.2.0 and validating clean via both `pyshacl` against the [URPX SHACL shapes](https://github.com/urpx-org/urpx/blob/v0.2.0/shacl/urpx-shacl.ttl) and [clj-urpx](https://github.com/grid-coordination/clj-urpx) (load → coerce → resolve a representative price for a known instant; see `dev/validate_v020.clj`).

**Statewide residential coverage**: ~90% of the 15M California residential customers tracked in `dev/coverage-estimates.toml` are served by a base RatePlan that is structurally modeled. Run `python dev/coverage.py` for the live breakdown.

**SHACL-validating ≠ bill-calculation-complete.** All 45 rate plans pass pyshacl + [clj-urpx](https://github.com/grid-coordination/clj-urpx), but most carry at least one documented modeling deferral tied to an open URPX vocabulary question. Each rate plan's `tariff.toml [extraction.notes]` lists what's deferred and why; the [Open URPX vocabulary questions](#open-urpx-vocabulary-questions) section below cross-references them.

### Fidelity by rate plan

| Fidelity | Rate plans | Notes |
|---|---:|---|
| **Models the published rate-of-record** | 41 | Validates clean against pyshacl + [clj-urpx](https://github.com/grid-coordination/clj-urpx); the bill calculation for the typical residential case is correct. About half carry one or more minor deferrals (PCIA composition for CCA-served customers, Franchise Fee Differentials; PG&E baseline-allocation matrix is fully modeled for E-TOU-C 2026-03-01 — pending for E-1) — all tied to one of the open URPX vocabulary questions listed below. |
| **Substantial economic effect deferred to prose** | 2 | SCE CARE and SCE FERA — line-item exemptions (WFC, FRC, BSC adjustments) modeled with concrete unit prices, but the headline 32.5% (CARE) / 18% (FERA) percentage-of-bill discount is captured in description prose only. Tracked at [urpx-org/urpx#24](https://github.com/urpx-org/urpx/issues/24). |
| **Placeholder Price (key value not expressible)** | 2 | LADWP NEM and SMUD NEM1 — both compensate exported energy at the customer's *applicable base-rate energy charge*, a "computed at upstream context" semantic that has no URPX v0.2.0 primitive. The modifiers carry a placeholder `Price` (`unitPrice="0"`) for SHACL conformance, with the actual compensation rule documented in the description prose. Same upstream issue: [urpx-org/urpx#24](https://github.com/urpx-org/urpx/issues/24). |

**Customer reach by fidelity bucket** (estimates per `dev/coverage-estimates.toml`; modifier counts overlap with their already-modeled base RatePlans):

| Bucket | Estimated customer reach |
|---|---|
| Models the published rate-of-record (base rates) | ~13.5M of ~15M tracked CA residential customers (~90%) |
| Substantial economic effect deferred to prose (modifier overlay) | ~1.5M SCE CARE + ~250K SCE FERA (~12% of CA residential, all on top of structurally-modeled base rates; line-item exemptions correct, headline percentage discount missing) |
| Placeholder Price (modifier overlay) | ~140K LADWP NEM solar + tens of K SMUD NEM1 grandfathered solar (~1% of CA residential, all on top of structurally-modeled base rates) |

### Open URPX vocabulary questions

Modeling work on this corpus surfaced a set of upstream issues + discussions awaiting resolution. Each rate plan's `tariff.toml` cites the ones that affect it; this is the corpus-wide index.

- [**urpx#18**](https://github.com/urpx-org/urpx/issues/18) — percent-of-baseline / ratio-of-reference modeling for usage-cap conditions.
- [**urpx#21**](https://github.com/urpx-org/urpx/issues/21) — rate-plan eligibility aggregation across accounts at one site. Una proposed `aggregationMethod=urpx:sum` on a derived `MetricInput`; trying to apply that pattern surfaced an inconsistency in three SHACL shapes — see discussion #29 below.
- [**urpx#24**](https://github.com/urpx-org/urpx/issues/24) — percentage-of-bill discount + computed-from-upstream-context semantics. Affects SCE CARE/FERA (percentage discount) and LADWP NEM / SMUD NEM1 (compute at customer's base rate).
- [**urpx#25**](https://github.com/urpx-org/urpx/issues/25) — on-site-generation exemptions and conditional demand credits in a Standby Charge. Affects SMUD NEM1/SSR standby-charge waivers.
- [**urpx#26**](https://github.com/urpx-org/urpx/issues/26) — packaging standalone `@graph` siblings (e.g. ProgramEnrollment defs) in a `URPXDocument`-wrapped filing.
- [**urpx-org/urpx discussion #28**](https://github.com/urpx-org/urpx/discussions/28) — `TariffPublication` ↔ `URPXDocument` shape conflict under `-i rdfs`. Affects 6 PG&E rate plans (E-1, E-TOU-C ×2, E-TOU-D, EV2, E-ELEC 2026-03-27 ─ those with an Advice Letter `TariffPublication` carrying `urpx:hasRatePlan`). For now we run `pyshacl` without `-i rdfs`; will re-enable when the discussion lands and we restructure the affected rate plans accordingly.
- [**urpx-org/urpx discussion #29**](https://github.com/urpx-org/urpx/discussions/29) — three SHACL shapes (`MetricInputShape`'s inline `calculationRule` constraint, `CalculationMethodShape`, `MetricSpecificationShape`) appear inconsistent on where `aggregationMethod` can attach. Blocks the concrete CPAU E-7 / E-7 TOU site-aggregation refactor proposed on #21.
- [**urpx#30**](https://github.com/urpx-org/urpx/issues/30) — request for `customDimensionProperty` (string) on `AlternativeDimension`, parallel to `CustomOperandNode.customConditionProperty`. PG&E vintage-PCIA + baseline-tier modifiers currently mint synthetic URIs as a workaround.
- [**urpx-org/urpx discussion #31**](https://github.com/urpx-org/urpx/discussions/31) — `PlanElementsShape.hasProfileAlternatives` is `sh:maxCount 1`, but PG&E E-1 needs two independent dimension groups (income tier × baseline territory-code). Blocks the in-place E-1 baseline-matrix expansion.
- [**urpx-org/urpx discussion #32**](https://github.com/urpx-org/urpx/discussions/32) — *additive baseline allowance* semantics: PG&E's medical baseline raises the Tier 1 cap by +16.438 kWh/day uniformly for eligible customers. Three modeling paths considered (matrix expansion to 4 codes; separate overlay modifier; placeholder Price); none expresses the additive-bound shift cleanly with v0.2.0 vocabulary. Blocks Code M / Code S medical-baseline modeling across all 5 PG&E baseline-having residential schedules.

### Utilities covered

| Utility | Class | Path | Base RatePlans | RatePlanModifiers |
|---|---|---|---|---|
| Pacific Gas & Electric (PG&E) | IOU | `ca/iou/pge/` | E-1, E-TOU-C (×2 reissue), E-TOU-D, EV2, E-ELEC (×2 reissue) | E-TOU-C Baseline-Tier |
| Southern California Edison (SCE) | IOU | `ca/iou/sce/` | TOU-D-4-9PM, TOU-D-5-8PM, TOU-D-PRIME, Schedule D | CARE, FERA |
| San Diego Gas & Electric (SDG&E) | IOU | `ca/iou/sdge/` | TOU-DR1, DR, TOU-DR2, EV-TOU-5, TOU-ELEC, DR-SES | — |
| Los Angeles Department of Water and Power (LADWP) | POU | `ca/pou/ladwp/` | R-1A, R-1B | NEM |
| Sacramento Municipal Utility District (SMUD) | POU | `ca/pou/smud/` | TOD-5-8pm, Fixed | SSR, NEM1, PEV Credit |
| City of Palo Alto Utilities (CPAU) | POU | `ca/pou/cpau/` | E-1 (×2 multi-source), E-1-TOU, E-2, E-3, E-4, E-4-TOU, E-7, E-7-TOU, E-14, E-16 | E-2-G, E-4-G, E-7-G, E-HRA, E-EEC-1, E-NSE-1 |

### Outstanding work

Tracked in [Issues](https://github.com/grid-coordination/urpx-tariffs/issues) and the local `bd` (beads) issue tracker. Highlights:

- SCE TOU-D HPWH (Heat Pump Water Heater) baseline-allocation modifier — blocked on [urpx-org/urpx#24](https://github.com/urpx-org/urpx/issues/24) (the gap there spans both percentage-of-bill discounts and quantity-threshold extensions)
- PG&E and SDG&E CARE/FERA modifiers — same shape as SCE's, deferred until the urpx#24 vocabulary lands
- Smaller-utility coverage (Imperial Irrigation District, City of Anaheim, Modesto Irrigation District, Riverside, Glendale, etc.) — each adds ~50K–150K residential customers and broadens statewide coverage

## Contributing

Issues, Discussions, and pull requests are welcome — see [CONTRIBUTING.md](./CONTRIBUTING.md) for the workflow. In short:

- **Modeling questions, ideas, suggestions** → [Discussions](https://github.com/grid-coordination/urpx-tariffs/discussions)
- **Confirmed modeling errors, missing tariffs, manifest schema bugs** → [Issues](https://github.com/grid-coordination/urpx-tariffs/issues)
- **Patches** → pull requests; please open a Discussion or Issue first for non-trivial changes (new utilities, new modifier shapes, manifest-schema changes)

If you have URPX modeling expertise and would like to review what we have, please get in touch — the [Disclaimer](#disclaimer) above is not aspirational, we genuinely could use the help.

## License

This repository is REUSE-compliant. See [`LICENSE`](./LICENSE), [`LICENSES/`](./LICENSES/), and [`REUSE.toml`](./REUSE.toml) for the authoritative declarations.

In summary:

- **Rate-plan JSON-LD serializations, manifests (`tariff.toml`, `utility.toml`), JSON Schemas, prose documentation (`README.md`, `LAYOUT.md`, `CONTRIBUTING.md`), and code (`dev/*.clj`, `dev/*.py`)** — [Community Data License Agreement — Permissive — Version 2.0](https://cdla.dev/permissive-2-0/) (`CDLA-Permissive-2.0`), Copyright (c) 2026 Clark Communications Corporation.
- **Committed source tariff PDFs** — `LicenseRef-PublicRecord`. Public regulatory documents (CPUC tariff filings, municipal-utility rate schedules adopted by city ordinance) are factual records of governmental processes and not subject to copyright. Copyright text attributes the issuing utility for provenance only, not as an assertion of ownership.
- **`ca/iou/pge/e-elec/versions/2026-01-01/rate-plan_pge_e-elec_2026-01-01.jsonld`** — same `CDLA-Permissive-2.0`, with copyright held jointly by `Flux Tailor LLC` (originator of the upstream v0.1.x test-case fixture in `urpx-org/urpx`) and Clark Communications Corporation (the v0.2.0 migration in this repo).

CDLA-Permissive-2.0 is the same license URPX uses for its test-case dataset content (`urpx-org/urpx/test-cases/`) — so files can flow between the two repos without license conversion.
