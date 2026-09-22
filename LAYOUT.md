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

## 1b. Service arrangements: what a customer actually takes service under

A **service arrangement** is a fully-determined selection over the plan space: one `urpx:RatePlanVersion`, plus zero or more `urpx:RatePlanModifierVersion`s applicable to it, plus one `urpx:ProfileAlternative` per dimension either of them leaves open. *Determined* means nothing remains to choose: it resolves to prices for any instant in its window with no further input. It is the thing a customer takes service under, and it is the unit an OpenADR 3 price server publishes as a program for an EMS to subscribe to.

**URPX v0.5.1 has no term for it.** Every `owl:ObjectProperty` whose range is one of the four plan classes was enumerated: there are fifteen and none has a composition domain. `urpx:hasModifierOptions` states availability, `urpx:applicableToRatePlan` states compatibility, and `urpx:AccountServiceAgreement` is a stub whose own `skos:note` pushes account data out of scope. So the term is ours, and the enumeration is derived rather than serialized: nothing in `us/` carries a service arrangement as a node.

**A `urpx:RatePlanVersion` is not a service arrangement.** It is the base plan's snapshot. PG&E E-TOU-D has one `urpx:RatePlan`, one current version of it, and eighteen MIDAS rate identifiers, one per overlay combination. Reading a version as the composition loses that entire dimension.

**Identity is intrinsic.** An arrangement is identified by its own components: the base version IRI, the sorted modifier version IRIs, and the sorted alternative selections. A MIDAS RIN is an *optional external attestation*, attached only where it is confidently derivable, and it is never the identity. RIN mapping is straightforward in some cases and may be intractable in others, and MIDAS itself is incomplete.

**A superseded version is not a service arrangement**, because nobody takes service under it. Supersession is derived from the data: a plan identity (the `urpx:forRatePlan` or `urpx:forRatePlanModifier` target) holding more than one distinct version `@id`, with all but the latest `urpx:effectiveDateTime` superseded. It is *not* derived from directory names. A directory count is not a version count: CPAU E-1 is filed at `versions/2025-07-01/` and again at `versions/2025-09-01/`, and both carry the one version node `cpau:e-1-2025-07-01`, because the base rates did not change and only the modifiers operative at the snapshot did. See also the lineage note in §10: nothing in the JSON-LD links a version to the one it replaces, so this ordering is all there is.

**A version node can occur in more than one filing, and the copies are not always identical.** A base filing bundles the modifiers operative at its snapshot date, scoped to that base. The authoritative occurrence is the one in the version's own filing, the file named `<stem>_<utility>_<slug>_<date>.jsonld`, and `dev/arrangements.py` refuses rather than choosing when a bundled copy claims a base the authority does not.

The enumeration lives in `dev/arrangements.py`; `dev/test_arrangements.py` fires each of its guards against a deliberately broken input.

## 2. File packaging: one self-contained file per filing

Each filing is serialized as a single JSON-LD file containing both:

- the (stable) `urpx:RatePlan` declaration, and
- the (filing-specific) `urpx:RatePlanVersion`, which points back with `urpx:forRatePlan` and is also still nested via `urpx:hasRatePlanVersion` (re-admitted at `sh:minCount 0` in v0.5.x, so both links are carried).

This mirrors the convention used by the URPX test cases (e.g. `test-cases/cpau-e-1-2025-07-01/data/urpx-rate-plan_cpau_e-1_2025-07-01.jsonld`).

Rationale:

- Every **base rate plan** filing is self-contained, portable, and can be cited or distributed in isolation: all 40 of them validate standalone. A **modifier** filing cannot be, and is not: it names the base plans it applies to via `urpx:applicableToRatePlan`, and those live in their own filings. `dev/validate-with-base.py --per-file` reports 40 of 73 conforming for exactly this reason, and the 33 that do not are the 33 modifier filings. That mode is a diagnostic, not a gate; the gate unit is the merged graph, where those references resolve.
- RDF graph merge handles the overlap cleanly, but only because every node that two filings both carry is named. Blank nodes never merge, so before the naming pass in section 6 the merged graph held one blank child per filing under each shared parent and violated every `sh:maxCount 1` edge into it. `dev/name_blank_nodes.py --check` is what keeps this bullet true.
- The duplicated RatePlan-level boilerplate (~15 lines) is small and lint-checkable.

The cross-filing consistency linter at [`dev/lint_consistency.py`](./dev/lint_consistency.py) verifies that `urpx:initialEffectiveDate`, `urpx:ratePlanUniqueIdentifier`, `urpx:name`, `urpx:timezoneIdentifier`, and the RatePlan `@id` are byte-identical across all filings of a given schedule. Run from the repo root: `python3 dev/lint_consistency.py` (or `--json` for machine-readable output). It refuses, rather than passing, when it finds no RatePlan to compare: it spent the period after the v0.5.1 migration locating none in 41 of 73 filings, reporting "Schedules checked: 0", and exiting 0 with "corpus is consistent", which is the failure mode this sentence previously described as a guarantee.

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
landing_page = "https://www.paloalto.gov/.../Residential-Rates"

  [source.base]
  url          = "https://www.paloalto.gov/.../e-1-tou-effective-2026-01-01.pdf"
  sha256       = "e1253904..."
  retrieved_on = "2026-03-03"
  media_type   = "application/pdf"
  filing_type  = "tariff-schedule"

  [source.modifier_e_nse_1]
  url          = "https://www.paloalto.gov/.../e-nse-1-effective-2025-09-01.pdf"
  sha256       = "c07362c5..."
  retrieved_on = "2026-04-30"
  media_type   = "application/pdf"
  filing_type  = "tariff-schedule"

  # ... one [source.<name>] block per source document
```

Sub-table names are free-form (`base`, `modifier_e_nse_1`, etc.); they're for human readability — the schema validates structure, not naming. Each sub-table carries the same fields as a single-source `[source]` block. See `us/ca/cpau/electricity/e-1-tou/versions/2026-01-01/tariff.toml` for a working example; it declares three sources, because the filing inlines two modifiers and each traces to its own PDF.

Inlining a modifier is a property of how the *publisher* wrote the schedule, not a packaging choice open to this corpus. Where a modifier is published as its own schedule it gets its own filing directory, and a base version that merely permits it says so with `urpx:applicableToRatePlan`. Assembling a pre-composed bundle that no single PDF corresponds to gives one version `@id` two definitions in the corpus, and a reader that loads both files then has to pick one.

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

### Blank nodes carry `@id`s too

A node with no `@id` is a fresh blank node on every parse, so it never merges with its counterpart in another filing. Where two filings serialize the same subtree, which section 2 both permits and relies on, the merged graph then holds one blank child per filing under a single named parent, and every `sh:maxCount 1` edge into it is violated. This accounted for 90 of the corpus's remaining violations: 1,468 blank nodes sat under `sh:maxCount 1` edges, and not one of the corpus's 1,184 operand nodes had an `@id`.

**Every node reachable by a `sh:maxCount 1` edge carries an `@id`, named after the node that points at it:**

```
<parent @id>-<property name, minus a leading "has", kebab-cased>
```

So `pge:e-tou-c-2026-03-01-plan-elements`, and below it `...-plan-elements-billing-model`. Because the parent is already scoped to its owning version, the scoping is inherited rather than re-derived, which is what makes an inlined modifier's operands come out identically named in every filing that inlines them.

There is deliberately no ordinal in the scheme. An ordinal would depend on array order, and array order is not guaranteed to agree between two serializations of one subtree, so it would defeat the merge it is meant to enable. That is safe only because no parent holds more than one such blank child under a single property; `dev/name_blank_nodes.py --audit` checks that property, along with parent reachability and name collisions, before writing anything.

`dev/name_blank_nodes.py --check` runs in both gate modes and fails on a blank node in scope. This covers `urpx:PlanElements`, `urpx:Prices`, `urpx:BillingModel`, `urpx:CalculationMethod`, `urpx:AlternativeDimensions` and the three operand node types. `urpx:BillingModel` is in scope purely by closure: nothing points at one twice, but `PlanElementsShape` puts `sh:maxCount 1` on `urpx:hasBillingModel`, so naming `PlanElements` without it would trade five violations for five others.

## 6b. Percentage-of-bill discounts

CARE and FERA discount a percentage of the bill rather than a per-unit rate, so they are modeled as a subtotal plus a multiplier rather than as a price.

**The subtotal lives in the base plan filing**, as a `urpx:PriceSummary` hung off the `PriceSet` holding most of that plan's line items, with `urpx:includesPrice` naming the discountable ones. It belongs there because it sums that plan's own prices. **The discount lives in the modifier**, as a `urpx:Price` carrying `urpx:multiplier` (the negative discount rate) and `urpx:basedOnPrice` pointing at the subtotal. It belongs there because the discount is a property of the program, and the base plan also serves customers not enrolled in it.

**Multiple `urpx:basedOnPrice` values are candidates, read disjunctively.** A modifier applying to nine base plans names all nine subtotals on one discount Price; composing it with any one plan leaves the other eight absent, and the one present is used. This is what avoids either reusing an `@id` across plans or minting a discount per plan. Zero resolvable candidates is still an error, so a typo stays loud. URPX itself says nothing about multiplicity; this reading is clj-urpx's, and the case for it is that disjunctive fails loudly when nothing resolves while conjunctive would fail quietly when everything does, silently summing nine unrelated subtotals.

**One subtotal per plan, not per TOU period.** Summary members are gated to the instant being resolved by the same season, month and TOU predicates that gate a tier, so a subtotal naming every discountable line item is correct in every period. Authoring per period would mean roughly 200 summaries instead of 26.

**Whether the two programs share a subtotal depends on the tariff, not on convenience.** SCE excludes the same two items from both (the PUCRF, and the Climate Credit, which Special Condition 12 applies after the taxes the discount precedes), so CARE and FERA share one subtotal and differ only in rate. SDG&E carves the fixed charge out of both and CARE additionally excludes the charges it is exempt from, so FERA pays the DWR Bond Charge and the Wildfire Fund NBC that CARE does not, and the same plan needs two subtotals with different members.

`dev/lint_discount_summaries.py` re-derives each subtotal from the tariff rule and runs in the gate, because a price added to a plan but not to its subtotal makes the discount too small while every other check stays green.

**Two properties that are optional in the shapes but load-bearing here**, neither visible to SHACL. A `urpx:Price` with no `urpx:startDate` is dropped from resolution silently, though one inside a `PriceSet` inherits the set's date, so the omission only bites in a loose `hasPrice` list. And a `urpx:Ledger` with no `urpx:referencesMetricInput` keeps its tiers but falls out of the marginal-rate aggregate, which then returns `0` rather than erroring: a legal price, so nothing signals it.

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
- **Lineage tracking** (this version supersedes that one) is currently NOT expressed in the JSON-LD. Version ordering is readable from the `versions/<date>/` directory name and from `urpx:effectiveDateTime`; nothing links one version to the one it replaced. URPX v0.5.1 permits `urpx:supersedes` on `urpx:PricingModel` and `urpx:TariffFiling` only, and `RatePlanVersionShape` and `RatePlanModifierVersionShape` are both `sh:closed`, so neither can carry it even as an extension. `urpx:supersedes` skos:note states the reasoning directly: "Version classes carry no lifecycle of their own: a version's place in the timeline derives from the filing chain." This corpus models no `TariffFiling`, so restoring the lineage it once recorded needs a decision about whether to.
- **Splitting the file** (separating RatePlan from each RatePlanVersion) remains an option if the duplicated boilerplate ever becomes painful. It would not require renaming any existing files — only adding a `rate-plan.jsonld` alongside `versions/`.

## 11. Reports: what each one measures

Everything under `reports/` is generated. `dev/check_all.py` runs every generator and then fails if a tracked file drifted, so a report that disagrees with the corpus is a build failure rather than a stale file.

The two questions these reports keep apart are **servability** (can a price server resolve this to a price?) and **completeness** (does this JSON-LD fully capture its source PDF?). §4.4 argues the general case: collapsing them into a single ready flag forces the modeler to pick one axis and lie about the other. They are also empirically independent in both directions: a filing can be incomplete over a demand-meter threshold that changes nobody's bill, and a filing can be `complete = true` while understating a marginal rate.

| Report | Generator | Measures |
| --- | --- | --- |
| `service-arrangements.md` / `.edn` | `dev/list_service_arrangements.py` | Every service arrangement the corpus can express, over current versions, at the grain of one base version plus at most one modifier version, with servability read from `dev/baseline/marginal-rates.edn`. Three outcomes, plus one for what was not measured. |
| `ready-for-use.md` / `.edn` | `dev/list_ready_for_use.py` | The same servability, rolled up to one row per `tariff.toml` directory, with `[modeling].complete` alongside it as a separate, separately labeled column. |
| `coverage.md` | `dev/coverage.py` | How much of the statewide residential customer base the corpus reaches, from the estimates in `dev/coverage-estimates.toml`. |
| `modifier-coverage.md` | `dev/lint_modifier_coverage.py` | Which modifiers a base RatePlan declares in `[modeling].applicable_modifiers` have a filing of their own (§4.4, Option A). A corpus-coverage gap report, not a servability one. |
| `modifier-base-pairings.json` / `.edn` | `dev/list_modifier_base_pairings.py` | The compatibility graph, from `urpx:applicableToRatePlan`, at plan-identity grain. |
| `midas-coverage.md` / `.json` | `scripts/build-midas-coverage-report.py` | Which CPUC MIDAS rate identifiers this corpus or the price server covers. Networked, credentialed and slow, so it is deliberately NOT in `check_all.py`'s step list; its age is printed on every full run instead. |

Servability figures are always *as of the recorded baseline*. `dev/baseline/marginal-rates.edn` is not auto-generated: re-record it deliberately with `clojure -M:validate --record-baseline` and review the diff.
