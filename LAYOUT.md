# Repository Layout

This document defines the conventions for organizing **tariff documents** (the regulatory PDFs) and the **URPX rate-plan serializations** extracted from them. It is the source of truth for directory structure, file naming, manifest schema, and the temporal model.

> **Terminology** (per [URPX CONTRIBUTING.md](https://github.com/urpx-org/urpx/blob/main/CONTRIBUTING.md#terminology-and-language-use)): a *tariff* is the regulatory document; a *rate plan* is the parameter package; a *rate* is a single price value. This repo holds both — a tariff PDF and the URPX rate-plan JSON-LD extracted from it — under each filing directory.

## 1. The temporal model: RatePlan vs RatePlanVersion

URPX models a rate plan using two related concepts:

- **`urpx:RatePlan`** — the stable, conceptual schedule. Holds a persistent identifier (e.g. "E-TOU-C"), the schedule's display name, the publishing utility, and the date it was first introduced. This resource rarely changes.
- **`urpx:RatePlanVersion`** — an immutable snapshot of one regulatory filing. Holds the rate values, time-of-use windows, riders, eligibility rules, and effective date. A new filing creates a new RatePlanVersion.

The two are linked via `urpx:hasRatePlanVersion`, declared `owl:disjointWith` in the ontology, and documented as: *"Master template … contains the stable identifier and houses all temporal versions of the rate."*

This hybrid pattern was chosen over the alternatives because:

| Pattern | Stable identity | Immutable snapshots | Match to CPUC/utility filing model |
| --- | --- | --- | --- |
| One resource per revision (linked by `prov:wasRevisionOf`) | ✗ — no canonical ID for "the schedule" | ✓ | partial |
| One resource mutated over time | ✓ | ✗ — same IRI yields different content over time | ✗ |
| **Hybrid (RatePlan + RatePlanVersion)** | ✓ | ✓ | ✓ |

## 2. File packaging: one self-contained file per filing

Each filing is serialized as a single JSON-LD file containing both:

- the (stable) `urpx:RatePlan` declaration, and
- the (filing-specific) `urpx:RatePlanVersion`, which points back with `urpx:forRatePlan` and is also still nested via `urpx:hasRatePlanVersion` (re-admitted at `sh:minCount 0` in v0.5.x, so both links are carried).

This mirrors the convention used by the URPX test cases (e.g. `test-cases/cpau-e-1-2025-07-01/data/urpx-rate-plan_cpau_e-1_2025-07-01.jsonld`).

Rationale:

- Each filing artifact is self-contained, portable, and can be cited or distributed in isolation.
- RDF graph merge handles the overlap cleanly: every file describes the same `urpx:RatePlan` IRI with consistent properties — merging multiple files yields a single RatePlan with all its versions linked.
- The duplicated RatePlan-level boilerplate (~15 lines) is small and lint-checkable.

The cross-filing consistency linter at [`dev/lint_consistency.py`](./dev/lint_consistency.py) verifies that `urpx:initialEffectiveDate`, `urpx:ratePlanUniqueIdentifier`, `urpx:name`, `urpx:timezoneIdentifier`, and the RatePlan `@id` are byte-identical across all filings of a given schedule. Run from the repo root: `python3 dev/lint_consistency.py` (or `--json` for machine-readable output).

## 3. Directory hierarchy

```
<country>/<subdivision>/<utility>/<carrier>/<schedule>/versions/<effective-date>/
```

| Segment | Values | Notes |
| --- | --- | --- |
| `<country>` | `us` | ISO 3166-1 alpha-2. Explicit because a bare `ca` reads as either California or Canada. |
| `<subdivision>` | `ca` | ISO 3166-2 subdivision code, here the state. Future: `or`, `wa`, etc. |
| `<utility>` | e.g. `pge` | See below. A utility sits above the carrier because PG&E and SDG&E supply both gas and electricity. |
| `<carrier>` | `electricity` | The commodity, mirroring `urpx:commodity` on the filing itself. Present so gas or water can be added later without moving anything. |
| `<utility>` | e.g. `pge`, `sce`, `sdge`, `cpau`, `smud`, `ladwp` | Lowercase short name. Match the EIA short name where one exists. |
| `<schedule>` | e.g. `e-tou-c`, `e-1`, `ev2`, `e-care` | Lowercase, hyphenated form of the schedule code. |
| `versions/<effective-date>` | ISO 8601 date, e.g. `2026-03-01` | The date this filing becomes effective, as published. |

Example:

```
us/ca/pge/electricity/utility.toml                            # per-utility discovery manifest (§5)
us/ca/pge/electricity/e-tou-c/versions/2026-03-01/            # per-filing directory (§4, §6, §7)
us/ca/pge/electricity/e-tou-c/versions/2025-09-01/
us/ca/cpau/electricity/utility.toml
us/ca/cpau/electricity/e-1/versions/2025-07-01/
```

### Why this nesting

- **Jurisdiction first** — anticipates expansion beyond California.
- **Class second** — the regulatory regime differs by class (CPUC vs municipal council vs CARE-only IOU schedules), and many tools will want to filter by class.
- **Schedule before date** — a schedule is the long-lived thing; its versions are children. Listing a schedule's directory shows its full revision history.
- **`versions/` literal directory** — leaves room for future sibling directories at the schedule level (e.g. `metadata.toml`, `lineage.md`, `schedule.jsonld` if we ever split the file).

## 4. Per-filing manifest: `tariff.toml`

Each `versions/<date>/` directory contains a `tariff.toml` capturing provenance and processing metadata that does not belong inside the URPX JSON-LD. The schema is at `schema/tariff-manifest.schema.json`.

### Single-source filing (the common case)

When a filing's `@graph` is extracted from a single source PDF:

```toml
# Identity --------------------------------------------------------------------
utility        = "pge"
schedule       = "e-tou-c"
effective_date = "2026-03-01"

# Source ----------------------------------------------------------------------
[source]
url           = "https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_SCHEDS_E-TOU-C.pdf"
sha256        = "9c2f6b3e..."
retrieved_on  = "2026-04-26"
media_type    = "application/pdf"
# filing_type values: advice-letter | application | resolution | ordinance |
#                     rate-case-decision | tariff-schedule | unknown
filing_type   = "advice-letter"
filing_id     = "PGE-AL-7234-E"          # if known
landing_page  = "..."                    # optional; the utility's discovery
                                         # surface where this PDF is published

# Regulatory ------------------------------------------------------------------
[regulator]
authority     = "puc"                    # puc | ferc | city-council | board | none | unknown
docket        = "A.24-12-345"            # if known

# Extraction ------------------------------------------------------------------
[extraction]
tool          = "mineru"
tool_version  = "1.4.2"
extracted_on  = "2026-04-26"

# Validation ------------------------------------------------------------------
[validation]
shacl_passed   = true
validator      = "clj-urpx"
validator_ver  = "0.3.1"
validated_on   = "2026-04-26"

# Modeling --------------------------------------------------------------------
[modeling]
complete             = true                # source PDF fully captured in this JSON-LD
deferrals            = []                  # MUST be [] when complete = true
applicable_modifiers = ["care", "fera"]    # ONLY on base RatePlan filings (see §4.4)

# Review ----------------------------------------------------------------------
[review]
status        = "draft"                  # draft | reviewed | published | superseded
reviewer      = ""                       # email or handle
reviewed_on   = ""
notes         = ""                       # short free text
```

`source.url`, `source.sha256`, and `source.retrieved_on` are required so the original PDF is always retrievable and verifiable. Optional fields may be omitted (TOML elides them).

### Multi-source filing

Some filings package a base RatePlan and one or more `RatePlanModifier`s into a single self-contained `@graph` — each modifier traces back to its own published PDF with its own URL, sha256, and retrieval date. In that case `[source]` is a parent table with an optional `landing_page` plus one named sub-table per source document:

```toml
[source]
landing_page  = "https://www.paloalto.gov/.../Residential-Rates"

  [source.base]
  url          = "https://www.paloalto.gov/.../e-1-effective-2025-07-01.pdf"
  sha256       = "9c8ad3bd..."
  retrieved_on = "2026-04-28"
  media_type   = "application/pdf"
  filing_type  = "tariff-schedule"

  [source.modifier_e_eec_1]
  url          = "https://www.paloalto.gov/.../e-eec-1-effective-2025-09-01.pdf"
  sha256       = "b2876440..."
  retrieved_on = "2026-04-28"
  media_type   = "application/pdf"
  filing_type  = "tariff-schedule"

  # ... one [source.<name>] block per source document
```

Sub-table names are free-form (`base`, `modifier_e_eec_1`, etc.); they're for human readability — the schema validates structure, not naming. Each sub-table carries the same fields as a single-source `[source]` block. See `us/ca/cpau/electricity/e-1/versions/2025-09-01/tariff.toml` for a working example.

### Per-document regulator metadata in multi-source filings

When a multi-source filing's source documents were *each filed separately* with the regulator under their own dockets/ordinances, `[regulator]` accepts named sub-tables paralleling `[source.<name>]`:

```toml
[regulator]
  [regulator.base]
  authority = "city-council"
  docket    = "Ordinance No. 5378"

  [regulator.modifier_e_eec_1]
  authority = "city-council"
  docket    = "Resolution 9.876"
```

Use this only when the per-document regulatory metadata genuinely differs across the source documents. If they all share one `authority + docket`, the flat single-`[regulator]` form is sufficient. The `authority` enum values (`puc`, `ferc`, `city-council`, `board`, `none`, `unknown`) are deliberately generic — the state context is already in the directory path (`ca/iou/...`), and the regulator's full name (e.g. "California Public Utilities Commission") can live in description prose if needed.

### 4.4. Modeling-completeness metadata (`[modeling]`)

The `[modeling]` block answers two distinct questions about how much of the source tariff has been captured. Keeping them separate is deliberate — collapsing them into a single "ready" flag forces the modeler to pick one axis and lie about the other.

```toml
[modeling]
complete             = true
deferrals            = []
applicable_modifiers = ["care", "fera", "medical-baseline", "ev-credit"]   # base RatePlan filings only
```

| Field | Axis | Applies to |
| --- | --- | --- |
| `complete` | Within-filing — does this JSON-LD fully capture its source PDF(s)? | All filings (base RatePlans + RatePlanModifiers) |
| `deferrals` | Within-filing — structured list of source-document parts intentionally not modeled | All filings; MUST be `[]` when `complete = true` |
| `applicable_modifiers` | Corpus-coverage — which RatePlanModifiers legally attach to this schedule | Base RatePlan filings only (omit on modifier filings) |

**Why two axes.** A base RatePlan being modeling-complete is independent of whether every applicable modifier has its own filing in the corpus. A price server billing a non-CARE customer on E-TOU-C only needs the base RatePlan; one billing a CARE customer needs base + CARE modifier. Conflating them would make `complete = true` mean different things to different consumers.

**Replaces prose deferrals.** Filings predating this convention express deferred work via `(modeling deferred — …)` parentheticals inside `rdfs:comment` strings. New filings should use the structured `deferrals` array instead; the prose form will be migrated incrementally as filings are revisited.

#### Modifier-coverage tracking: options considered

Two shapes were considered for tracking which modifiers a base RatePlan accepts:

- **Option A — self-declared on the base.** Each base RatePlan filing carries `applicable_modifiers` listing the universe of legally-applicable modifiers per the source PDF, *including modifiers not yet modeled in the corpus*. A lint walks the corpus and reports, per base, which applicable modifiers (i) have a filing under the same utility, and (ii) of those, which have `complete = true`.
- **Option B — derived from the modifier side.** Skip the per-base list entirely. Each RatePlanModifier filing already names its applicable bases via IRI. A corpus walk could collect those references and emit a coverage report without per-base annotation.

**Option A is the chosen approach.** Option B is lighter weight but only sees modifiers that already have filings — it cannot surface the case "we know SCE has a Medical Baseline modifier but no one has modeled it yet", which is the gap signal that matters most. The information *what modifiers legally attach to this schedule* isn't recoverable from the JSON-LD or any other file we keep, so the base manifest is the right home for it.

The lint that consumes `applicable_modifiers` lives at `dev/lint_modifier_coverage.py` (when implemented) and emits `reports/modifier-coverage.md`.

## 5. Per-utility discovery manifest: `utility.toml`

Each `us/<subdivision>/<utility>/` directory contains a `utility.toml` pointing at where the utility publishes its tariffs. Distinct from the per-filing `tariff.toml` (§4): `tariff.toml` pins a specific snapshot, `utility.toml` points at the discovery surface where future snapshots can be found. The schema is at `schema/utility-manifest.schema.json`.

```toml
utility           = "pge"

tariff_index_urls = [
  "https://www.pge.com/en/account/rate-plans/rate-plans/learn-about-rate-plans.html",
  "https://www.pge.com/tariffs/assets/pdf/tariffbook/",
]

scrape_notes = """
Free text. Document scrape strategy hints: known TLS-fingerprint blocks
(curl_cffi required), URL patterns per schedule, AL-listing locations,
paywalls, etc.
"""
```

Required fields are `utility` and `tariff_index_urls` (one or more discovery URLs). `scrape_notes` is optional but recommended — capture what a future scraper will need to know that isn't obvious from the URLs alone.

The schema is intentionally minimal. Richer fields (per-schedule URL templates, AL-listing endpoints, structured scrape recipes) can be added once a real scraper is built and tells us what it needs.

## 6. IRI naming conventions

Subjects are minted in per-utility CURIE prefixes bound in each filing's `@context`, never in `urpx:`. The `urpx:` prefix names URPX vocabulary terms and enumeration members only. Every prefix resolves under the identity base `https://rate-plans.grid-coordination.energy/`.

| Resource | IRI shape | Example |
| --- | --- | --- |
| Utility (`urpx:Organization`) | `org:utility-<utility>` | `org:utility-pge` |
| RatePlan | `<utility>:<schedule>` | `pge:e-tou-c` |
| RatePlanVersion | `<utility>:<schedule>-<date>` | `pge:e-tou-c-2026-03-01` |
| CoverageClaim | `<utility>:cc-<schedule>-<date>` | `pge:cc-e-tou-c-2026-03-01` |
| Subordinate resources (eligibility rules, ledgers, prices, etc.) | `<utility>:<short>-<descriptor>` | `pge:er-residential`, `urpx:pge-ledger-commodity` |

These mirror the convention used in the existing URPX test cases (e.g. `urpx:cpau-e-1`, `urpx:cpau-e-1-2025-07-01`). Lowercase, hyphenated, no spaces.

### Scoping subordinate IRIs

URI identity says **one IRI denotes one resource**. Every filing of a utility is loaded into one merged graph at validation time (`dev/validate-with-base.py --utility <slug>`, the gate unit), so a subordinate resource that two filings both mint becomes a single node carrying both filings' values.

**Every subordinate resource takes the IRI of the version that owns it, followed by its descriptor:**

```
<utility>:<owning-version-local-part>-<descriptor>
```

The owning version is the nearest enclosing `urpx:RatePlanVersion` or `urpx:RatePlanModifierVersion`, and its own local part is already `<schedule>-<date>`, so the result reads `pge:e-elec-2026-03-27-price-public-purpose`.

Take the scope from the **owning version, not the directory**. They differ wherever a filing inlines another schedule's subtree: CPAU's `e-1` inlines the whole `cpau:e-hra` modifier, and PG&E inlines a per-plan PCIA modifier into five base filings. Scoping by directory would rename `cpau:e-hra-2023-01-01-price-25-75-gen-480-642` three different ways and mint three copies of one real modifier. Scoping by owner gives it the same IRI in all three files, which is correct, because it is one resource.

Apply it to every subordinate resource, not only to ones observed to collide. An earlier revision of this section said to apply it "only to the IRIs that actually collide on content", and the result was 509 subordinate IRIs minted by more than one schedule, with `sce:price-gen-summer-on-peak-2026-03-20` carrying three different unit prices at once. Content that happens to agree today is not a reason to share an IRI; the next rate case moves one value and the collision appears with nothing to announce it.

**Kept shared, deliberately.** The identity layer names entities that genuinely span a utility's schedules, and scoping those would mint duplicates of one real thing: `urpx:Organization` and its identity/name/identifier nodes, `urpx:RateCase`, `urpx:RatePlan`, `urpx:RatePlanModifier`, `urpx:SourcePublication`, `urpx:TariffPublication`, `urpx:ProgramEnrollment`. Version nodes carry `<schedule>-<date>` already. Two subordinate types also stay shared: `urpx:MetricSpecification`, and `urpx:CoverageClaim`, which has its own form `<utility>:cc-<schedule>-<date>`.

Whether a type may stay shared is decided by **closure, not by how utility-level the concept feels**: a shared IRI is safe only if every `sh:maxCount 1` value it carries is a literal, or an IRI that is itself kept shared. A parent that passes a one-level check still breaks once its children are scoped, because it then holds one child per schedule. `urpx:Season` is the instructive case for the other direction. All 24 in the corpus agree today, but `SeasonShape` sets no `sh:maxCount` on `urpx:month` and all 72 corpus Seasons are month-based, so a future divergence would silently union the months and leave the gate green. CPAU is the one utility whose schedules disagree on season boundaries, and the one that already mints per-schedule Seasons.

`dev/lint_iri_scope.py` enforces this and runs in the gate, so the convention no longer depends on someone noticing. `dev/rescope_iris.py` applies it.

## 7. Source PDF referencing

Each filing's source PDF is **committed alongside the JSON-LD** at:

```
us/<country>/<subdivision>/<utility>/<carrier>/<schedule>/versions/<date>/<utility>_<schedule>_<date>.pdf
```

Examples:

```
us/ca/pge/electricity/e-tou-c/versions/2026-03-01/pge_e-tou-c_2026-03-01.pdf
us/ca/pge/electricity/e-tou-d/versions/2026-03-27/pge_e-tou-d_2026-03-27.pdf
```

The URPX `urpx:hasDataSourceReference` block in each JSON-LD retains the canonical published URL via `urpx:accessURL` and the publisher's filename via `urpx:fileName`:

```json
"urpx:hasDataSourceReference": {
  "@type": "urpx:DataSourceReference",
  "urpx:fileName": "ELEC_SCHEDS_E-TOU-C.pdf",
  "urpx:accessURL": "https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_SCHEDS_E-TOU-C.pdf",
  ...
}
```

`tariff.toml` carries the sha256 of the bytes-as-extracted, allowing the committed local PDF to be self-checked.

### Why PDFs ARE committed (reversal of an earlier decision)

The earlier convention was *"PDFs are not committed; future consumers can re-fetch and verify byte-identity"*. That convention was reversed on 2026-04-28 after a real demonstration of why URLs alone are not durable provenance: PG&E updated `ELEC_SCHEDS_E-TOU-C.pdf` in place at the canonical URL between our 2026-04-26 retrieval and a 2026-04-28 re-fetch — same URL, different bytes. The original was recoverable only because dcj had a private archive copy. URDB and similar tariff databases are full of broken links and silently-mutated documents for the same reason; URPX's *raison d'être* is auditable provenance, which requires the actual bytes the data was extracted from to live alongside the structured representation.

### Edge case: corrections to the same effective date

If a regulator issues a correction with a new sheet number for the same effective date, extend the filename to include the CPUC leaf identifier (e.g. `pge_e-tou-d_2026-03-27_61254-E.pdf`). Not a problem we have today.

Utility-specific source-document quirks (publication cadence, per-sheet vs whole-document effective dates, opaque vs stable URLs) are documented in each utility's `utility.toml` `scrape_notes` rather than aggregated here.

## 8. Extraction intermediates

Per-filing extraction byproducts (MinerU markdown, OCR layouts, intermediate JSON) live at `versions/<date>/extracted/` and are excluded from git via the top-level `.gitignore`. They are useful locally for debugging the conversion but bloat the repo and are reproducible from the source PDF.

If a particular extraction needs to be preserved (e.g. as evidence of how a tricky table was parsed), commit a single `extracted/notes.md` describing the issue, not the raw output.

## 9. Workflow: adding a new filing

1. Identify a new tariff PDF (utility website, CPUC e-filing, regulator portal).
2. Create the directory: `us/<country>/<subdivision>/<utility>/<carrier>/<schedule>/versions/<effective-date>/`.
3. Write `tariff.toml` with `source.url`, `source.sha256` (compute locally), `retrieved_on`, and `extraction.tool`.
4. Run extraction (e.g. `mineru -p source.pdf -o extracted/ -b pipeline`).
5. Convert to URPX JSON-LD as `rate-plan_<utility>_<schedule>_<date>.jsonld`.
6. Validate with `clj-urpx` (SHACL) — record outcome in `[validation]`.
7. Record modeling-completeness state in `[modeling]` (§4.4): set `complete = true` and `deferrals = []` if the source PDF is fully captured; otherwise list the deferred parts. On base RatePlan filings, also populate `applicable_modifiers` with every RatePlanModifier the source tariff names — *including modifiers not yet modeled in the corpus*, since this list is what drives the modifier-coverage gap report.
8. Lint cross-filing consistency (RatePlan-level fields match prior filings of this schedule).
9. Commit. Optionally open a PR if review is required.

## 10. Future considerations

- **Tariff modifiers** (`urpx:RatePlanModifier`, e.g. CARE discount, NEM credit) can stand alone at `versions/` paths under their own pseudo-schedule directory, e.g. `us/ca/pge/electricity/e-care/versions/...` — they share the same packaging. Cross-references to the base RatePlan use IRIs.
- **Non-residential schedules** follow the same layout under their own schedule directories (e.g. `us/ca/pge/electricity/a-1/`). The class-level split is by utility class, not by customer class.
- **Lineage tracking** (this version supersedes that one) is captured by `urpx:supersedes` inside the JSON-LD, not by directory layout. Per [urpx-org/urpx#16](https://github.com/urpx-org/urpx/issues/16), the value must point to an existing `RatePlanVersion` IRI; cross-file resolution is verified by `dev/validate-with-base.py --utility <slug>`, which merges a whole utility so the referent is in the same graph. Adopted in [#3](https://github.com/grid-coordination/urpx-rate-plans/issues/3) starting with PG&E E-TOU-C 2026-03-27 → 2026-03-01.
- **Splitting the file** (separating RatePlan from each RatePlanVersion) remains an option if the duplicated boilerplate ever becomes painful. It would not require renaming any existing files — only adding a `rate-plan.jsonld` alongside `versions/`.
