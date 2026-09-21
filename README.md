# urpx-rate-plans

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
us/<country>/<subdivision>/<utility>/<carrier>/<schedule>/versions/<effective-date>/
  <utility>_<schedule>_<date>.pdf                             # source tariff document
  tariff.toml                                                 # per-filing provenance manifest
  rate-plan_<utility>_<schedule>_<date>.jsonld                # URPX rate-plan serialization, OR
  rate-plan-modifier_<utility>_<schedule>_<date>.jsonld       # for standalone rider/overlay rate plans
```

`<carrier>` is the commodity, currently always `electricity`; it sits below `<utility>` because PG&E and SDG&E supply both gas and electricity, and a utility's offerings should stay adjacent. It mirrors `urpx:commodity`, which each filing also carries. Source tariff PDFs are committed alongside each rate plan — see [LAYOUT.md §7](./LAYOUT.md#7-source-pdf-referencing) for the rationale (canonical URLs alone are not durable provenance; PG&E updated `ELEC_SCHEDS_E-TOU-C.pdf` in place between two retrievals two days apart).

Each `<country>/<subdivision>/<utility>/` directory also carries a `utility.toml` discovery manifest listing the URLs where the utility publishes its tariffs ([LAYOUT.md §5](./LAYOUT.md#5-per-utility-discovery-manifest-utilitytoml)).

### Reading the JSON-LD: cross-resource relationships

Two relationships span resources within (and across) filings — both are nested, not at the top level, so consumers reading only the top-level resource will miss them:

| Relationship | JSON-LD path | Notes |
|---|---|---|
| Modifier → base RatePlan(s) it applies to | `urpx:RatePlanModifier` → `urpx:hasRatePlanModifierVersion` → `urpx:applicableToRatePlan` | List of `@id` references to base RatePlan IRIs (e.g. `sce:d`). Cross-version: a modifier filed once applies to every version of the named base. |
| RatePlanVersion → the version it supersedes | `urpx:RatePlanVersion` → `urpx:supersedes` | Single `@id` reference to the prior version's IRI. See [LAYOUT.md §10](./LAYOUT.md#10-future-considerations) and [urpx-org/urpx#16](https://github.com/urpx-org/urpx/issues/16). |

Consumers that need the modifier ↔ base pairings as a flat map can read [`reports/modifier-base-pairings.{edn,json}`](./reports/) instead of walking the JSON-LD — auto-generated by `dev/list_modifier_base_pairings.py` from the corpus. Each base's `[modeling].applicable_modifiers` in `tariff.toml` carries the same data viewed from the base side, including modifiers known to attach to the schedule but not yet modeled (see [LAYOUT.md §4.4](./LAYOUT.md#44-modeling-completeness-metadata-modeling)).

## Status

73 filings landed (40 `urpx:RatePlan` + 33 standalone `urpx:RatePlanModifier`; one filing — PG&E E-TOU-C 2026-03-01 — packages a base alongside a sibling modifier in the same directory, plus 4 PG&E vintage-PCIA modifiers are bundled inline inside their bases' `@graph`). All filings serialize against URPX v0.2.0 and validate clean via both `pyshacl` against the [URPX SHACL shapes](https://github.com/urpx-org/urpx/blob/main/shacl/urpx-shacl.ttl) and [clj-urpx](https://github.com/grid-coordination/clj-urpx) (load → coerce → resolve a representative price for a known instant; see `dev/validate_v020.clj`).

**Statewide residential coverage**: ~91% (90.8%) of the 15M California residential customers tracked in `dev/coverage-estimates.toml` are served by a base RatePlan that is structurally modeled. Run `python dev/coverage.py` for the live breakdown.

**Cross-corpus utility identification**: every filing's `publishedBy` Organization carries `urpx:eiaId` (PG&E 14328, SCE 17609, SDG&E 16609, LADWP 11208, SMUD 16534, CPAU 3203) — usable as a stable join key against the EIA-861 utility dataset without parsing legalName variants.

**SHACL-validating ≠ bill-calculation-complete.** All filings pass pyshacl + [clj-urpx](https://github.com/grid-coordination/clj-urpx), but most carry at least one documented modeling deferral tied to an open URPX vocabulary question. Each rate plan's `tariff.toml [extraction.notes]` lists what's deferred and why; the [MODELING-GAPS.md](./MODELING-GAPS.md) section below cross-references them.

### Fidelity by rate plan

| Fidelity | Rate plans | Notes |
|---|---:|---|
| **Models the published rate-of-record** | 62 | Validates clean against pyshacl + [clj-urpx](https://github.com/grid-coordination/clj-urpx); the bill calculation for the typical residential case is correct. About half carry one or more minor deferrals (PCIA composition for CCA-served customers, Franchise Fee Differentials; PG&E baseline-allocation matrix is fully modeled for E-TOU-C 2026-03-01 — pending for E-1) — all tied to one of the open URPX vocabulary questions listed below. CPAU E-HRA (Hydroelectric Recovery Adjustment) tags all 16 matrix-cell Prices with `urpx:hasDynamicPricing` (`dynamicPricingType=urpx:indexBasedPricing` + `priceSource=urpx:renewableForecastSource`) marking them as externally-indexed by CPAU's annual hydro forecast — same canonical-vocabulary uplift as the CPP modifiers. PG&E NBT 2025-10-17 introduces the first export-direction modifier in the corpus (`urpx:flowDirection urpx:reverse` on a `urpx:MetricSpecification` — confirmed admitted by the closed MetricSpecificationShape); 4,608 per-cell Export Compensation Rate Prices loaded from `pge.com/energyexportcredit` covering the 2023-2026 vintage cohort. PG&E E-RSMART 2025-10-31 (residential SmartRate CPP overlay) is the first multi-base `urpx:RatePlanModifier` in the corpus, binding to 5 base RatePlans (E-1, E-ELEC, E-TOU-C, E-TOU-D, EV2). **MIDAS RIN cross-reference is established across the corpus.** All three CA IOU NBT filings carry CEC MIDAS Rate Identification Numbers in Price names for round-trip verification against the MIDAS source. Concretely: **SDG&E NBT 2025-01-27** ships with 5,760 RIN-tagged Prices (5 vintages × 576 cells × Generation + Delivery; SDG&E publishes both components as separate RIN families: `USCA-SDXX` Delivery + `USCA-XXSD` Generation); **PG&E NBT 2025-10-17** has 4,608 Prices with 2,304 Delivery tagged (`USCA-PGXX-3500-0000` = E-ELEC + NBT23) — Generation Prices are loaded from `pge.com/energyexportcredit` but untagged (PG&E doesn't publish Generation via MIDAS as a separate RIN); **SCE NBT 2025-04-23** has 5,088 Prices RIN-tagged — Delivery from `USCA-SCXX-0605-0000` (TOU-D-PRIME-NBT 2025) and Generation **derived from MIDAS via subtraction**: `USCA-SCSC` (bundled-service combined EEC) minus `USCA-SCXX` (CCA-service Delivery-only EEC) = Generation Component. SCE doesn't publish a separate Generation RIN, but the bundled-vs-CCA arithmetic recovers it cleanly (verified constant within lock-in periods). The cross-reference enables a downstream consumer (e.g. the price server) to validate URPX-resolved prices against MIDAS by `(RIN, instant)` lookup. |
| **Substantial economic effect deferred to prose** | 8 | SCE CARE/FERA + SDG&E CARE/FERA + SMUD EAPR — line-item exemptions (WFC, FRC, BSC adjustments) modeled with concrete unit prices, but the headline percentage-of-bill discounts (32.5%/18% SCE CARE/FERA, 35%/18% SDG&E CARE/FERA, $60-$0/mo income-tier usage caps SMUD EAPR) are captured in description prose only. SCE PRIME-CPP, SMUD CPP, and SCE DA-CRS / CCA-CRS modifiers also carry deferrals on dynamic event-day / vintage-year evaluation: the SMUD CPP and SCE PRIME-CPP Event Charge Prices use the canonical `urpx:hasDynamicPricing` + `urpx:PriceUpdateRule` vocabulary (`dynamicPricingType=urpx:criticalPeakPricing` + `updateFrequency=urpx:eventTriggeredUpdates`); the SCE PRIME-CPP Non-Event Credit and Maximum Available Credit retain `ApplicabilityRule` + `CustomOperandNode` gating (inverse-event-polarity and customer-grandfathered-attribute respectively, neither of which fits DynamicPricing). [clj-urpx 0.7.0](https://github.com/grid-coordination/clj-urpx) surfaces `:urpx.resolved/dynamic-pricing` on each resolved tier carrying `hasDynamicPricing` — consumers building bills can now filter event-driven tiers out of the non-event marginal without re-parsing the source JSON-LD. The remaining gaps (`marginal-unit-rate` semantics decision and caller-supplied event-state evaluation) are tracked at [grid-coordination/clj-urpx#5](https://github.com/grid-coordination/clj-urpx/issues/5) parts (2) and (3); the percentage-of-bill / cap-on-credit semantics still need [urpx-org/urpx#24](https://github.com/urpx-org/urpx/issues/24). |
| **Placeholder Price (key value not expressible)** | 2 | LADWP NEM and SMUD NEM1 — both compensate exported energy at the customer's *applicable base-rate energy charge*, a "computed at upstream context" semantic that has no URPX v0.2.0 primitive. The modifiers carry a placeholder `Price` (`unitPrice="0"`) for SHACL conformance, with the actual compensation rule documented in the description prose. Same upstream issue: [urpx-org/urpx#24](https://github.com/urpx-org/urpx/issues/24). |

**Customer reach by fidelity bucket** (estimates per `dev/coverage-estimates.toml`; modifier counts overlap with their already-modeled base RatePlans):

| Bucket | Estimated customer reach |
|---|---|
| Models the published rate-of-record (base rates) | ~13.6M of ~15M tracked CA residential customers (~91%) |
| Substantial economic effect deferred to prose (modifier overlay) | ~1.5M SCE CARE + ~250K SCE FERA + ~420K SDG&E CARE + ~70K SDG&E FERA + ~30K SMUD EAPR + ~10K SMUD CPP (~15% of CA residential, all on top of structurally-modeled base rates; line-item exemptions and BSC adjustments correct, headline percentage / cap-on-credit discount missing; CPP Event Charges use `hasDynamicPricing` for canonical event-driven semantics — clj-urpx 0.7.0 surfaces these on resolved tiers, but consumer-side billing-time evaluation of event status remains pending [clj-urpx#5](https://github.com/grid-coordination/clj-urpx/issues/5) parts (2) and (3) and the URPX vocabulary for caller-supplied event state) |
| Placeholder Price (modifier overlay) | ~140K LADWP NEM solar + tens of K SMUD NEM1 grandfathered solar (~1% of CA residential, all on top of structurally-modeled base rates) |

### Modeling gaps

What this corpus cannot express in URPX v0.5.1, and what it has not yet converted, are tracked in [MODELING-GAPS.md](./MODELING-GAPS.md).

### Utilities covered

| Utility | Class | Path | Base RatePlans | RatePlanModifiers |
|---|---|---|---|---|
| Pacific Gas & Electric (PG&E) | IOU | `us/ca/pge/` | E-1, E-TOU-C (×2 reissue), E-TOU-D, EV2, E-ELEC (×2 reissue) | E-TOU-C Baseline-Tier, NBT (Net Billing Tariff), E-RSMART (SmartRate) |
| Southern California Edison (SCE) | IOU | `us/ca/sce/` | TOU-D-4-9PM (×2 reissue), TOU-D-5-8PM (×2 reissue), TOU-D-PRIME (×2 reissue), Schedule D (×2 reissue) | CARE (×2 reissue), FERA (×2 reissue), Deed-Restricted (×2 reissue), DA-CRS, CCA-CRS, PRIME-CPP, Medical Baseline, NBT (Net Billing Tariff: 5,088 RIN-tagged Prices, Generation derived from MIDAS SCSC−SCXX) |
| San Diego Gas & Electric (SDG&E) | IOU | `us/ca/sdge/` | TOU-DR1, TOU-DR, TOU-DR2, DR, DR-SES, EV-TOU, EV-TOU-2, EV-TOU-5, TOU-ELEC | CARE, FERA, DRAH, NBT (Net Billing Tariff: 5,760 RIN-tagged Prices) |
| Los Angeles Department of Water and Power (LADWP) | POU | `us/ca/ladwp/` | R-1A, R-1B | NEM, EZ-Save, Lifeline |
| Sacramento Municipal Utility District (SMUD) | POU | `us/ca/smud/` | TOD-5-8pm, TOD-Low-Use, Fixed | SSR, NEM1, PEV Credit, MED, EAPR, CPP |
| City of Palo Alto Utilities (CPAU) | POU | `us/ca/cpau/` | E-1 (×2 multi-source), E-1-TOU, E-2, E-3, E-4, E-4-TOU, E-7, E-7-TOU, E-14, E-16 | E-2-G, E-4-G, E-7-G, E-HRA, E-EEC-1, E-NSE-1 |

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
- **`us/ca/pge/electricity/e-elec/versions/2026-01-01/rate-plan_pge_e-elec_2026-01-01.jsonld`** — same `CDLA-Permissive-2.0`, with copyright held jointly by `Flux Tailor LLC` (originator of the upstream v0.1.x test-case fixture in `urpx-org/urpx`) and Clark Communications Corporation (the v0.2.0 migration in this repo).

CDLA-Permissive-2.0 is the same license URPX uses for its test-case dataset content (`urpx-org/urpx/test-cases/`) — so files can flow between the two repos without license conversion.
