# Repository Layout

This document defines the conventions for organizing **tariff documents** (the regulatory PDFs) and the **URPX rate-plan serializations** extracted from them. It is the source of truth for directory structure, file naming, manifest schema, and the temporal model.

> **Terminology** (per [URPX CONTRIBUTING.md](https://github.com/urpx-org/urpx/blob/main/CONTRIBUTING.md#terminology-and-language-use)): a *tariff* is the regulatory document containing one or more rate plans; a *rate plan* is the complete set of parameters needed to calculate what a customer is charged; a *rate* is a single price value. This corpus curates rate plans from tariff documents and keeps both. A modeled filing holds its tariff document beside the rate plan read from it (§7); tariff documents for schedules not yet modeled are held separately (§10d).

## 1. The temporal model: RatePlan vs RatePlanVersion

URPX models a rate plan using two related concepts:

- **`urpx:RatePlan`** — the stable, conceptual schedule. Holds a persistent identifier (e.g. "E-TOU-C"), the schedule's display name, the date it was first introduced, and the timezone its hours are read in. This resource rarely changes. The publishing utility is not on it: every filing here carries `urpx:offeredBy` on the version instead.
- **`urpx:RatePlanVersion`** — an immutable snapshot of one regulatory filing. Holds the rate values, time-of-use windows, riders, eligibility rules, and effective date. A new filing creates a new RatePlanVersion.

The two are linked via `urpx:hasRatePlanVersion` and declared `owl:disjointWith`. URPX v0.5.1 defines the RatePlan as *"Stable identity of a utility rate plan, independent of time"*, with the note *"The stable identifier. No pricing content."*

This hybrid pattern was chosen over the alternatives because:

| Pattern | Stable identity | Immutable snapshots | Match to CPUC/utility filing model |
| --- | --- | --- | --- |
| One resource per revision (linked by `prov:wasRevisionOf`) | ✗ — no canonical ID for "the schedule" | ✓ | partial |
| One resource mutated over time | ✓ | ✗ — same IRI yields different content over time | ✗ |
| **Hybrid (RatePlan + RatePlanVersion)** | ✓ | ✓ | ✓ |

## 1b. Service arrangements: what a customer actually takes service under

A **service arrangement** is a fully-determined selection over the plan space: one `urpx:RatePlanVersion`, plus zero or more `urpx:RatePlanModifierVersion`s applicable to it, plus one `urpx:ProfileAlternative` per dimension either of them leaves open. *Determined* means nothing remains to choose: it resolves to prices for any instant in its window with no further input. It is the thing a customer takes service under, and it is the unit an OpenADR 3 price server publishes as a program for an EMS to subscribe to.

**URPX names every part of an arrangement and no whole of it.** Every `owl:ObjectProperty` whose range includes one of the four plan classes was enumerated: there are sixteen and none has a composition domain. `urpx:hasModifierOptions` states availability, `urpx:applicableToRatePlan` states compatibility, and `urpx:AccountServiceAgreement` is a stub whose own `skos:note` pushes account data out of scope. So the term is ours, and the enumeration is derived rather than serialized: nothing in `us/` carries a service arrangement as a node.

**A `urpx:RatePlanVersion` is the base plan's snapshot, not the arrangement.** PG&E E-TOU-D has one `urpx:RatePlan`, one current version of it, and eighteen MIDAS rate identifiers, one per overlay combination. Reading a version as the composition loses that entire dimension.

**Identity is intrinsic.** An arrangement is identified by its own components: the base version IRI, the sorted modifier version IRIs, and the sorted alternative selections. A MIDAS RIN is an *optional external attestation*, attached only where it is confidently derivable, and it is never the identity. RIN mapping is straightforward in some cases and may be intractable in others, and MIDAS itself is incomplete.

**Only a current version is a service arrangement**, because nobody takes service under a superseded one. Supersession is derived from the data: a plan identity (the `urpx:forRatePlan` or `urpx:forRatePlanModifier` target) holding more than one distinct version `@id`, with all but the latest `urpx:effectiveDateTime` superseded. It is *not* derived from directory names. A directory count is not a version count: a snapshot bundle can restate a version node whose rates did not change, so two directories can carry one version node, because the base rates did not change and only the modifiers operative at the snapshot did. See also the lineage note in §10: nothing in the JSON-LD links a version to the one it replaces, so succession is read off `urpx:effectiveDateTime` and the `urpx:expirationDateTime` bounds that touch.

**A version node can occur in more than one filing, and the copies are not always identical.** A base filing bundles the modifiers operative at its snapshot date, scoped to that base. The authoritative occurrence is the one in the version's own filing, the file named `<stem>_<utility>_<slug>_<date>.jsonld`, and `dev/arrangements.py` refuses rather than choosing when a bundled copy claims a base the authority does not.

The enumeration lives in `dev/arrangements.py`; `dev/test_arrangements.py` fires its guards against deliberately broken input.

## 2. File packaging: one self-contained file per filing

Each filing is serialized as a single JSON-LD file containing both:

- the (stable) `urpx:RatePlan` declaration, and
- the (filing-specific) `urpx:RatePlanVersion`, which points back with `urpx:forRatePlan` and is also still nested via `urpx:hasRatePlanVersion` (re-admitted at `sh:minCount 0` in v0.5.x, so both links are carried).

This mirrors the convention used by the URPX test cases (e.g. `test-cases/cpau-e-1-2025-07-01/data/urpx-rate-plan_cpau_e-1_2025-07-01.jsonld`).

Rationale:

- **A base rate plan filing is self-contained unless it inlines another schedule's subtree.** Most can be cited or distributed in isolation. A **modifier** filing never can: it names the base plans it applies to via `urpx:applicableToRatePlan`, and those live in their own filings. A base filing that inlines a modifier, as CPAU's `e-1` and `e-1-tou` do with `cpau:e-hra`, inherits the same cross-file references. `dev/validate-with-base.py --per-file` reported 35 of 72 conforming on 2026-09-23; the 37 that did not are all 33 modifiers plus those 4 base filings. That mode is a diagnostic, not a gate; the gate unit is the merged graph, where the references resolve.
- RDF graph merge handles the overlap cleanly, but only because every node that two filings both carry is named. Blank nodes never merge, so before the naming pass in section 6 the merged graph held one blank child per filing under each shared parent and violated every `sh:maxCount 1` edge into it. `dev/name_blank_nodes.py --check` is what keeps this bullet true.
- The duplicated RatePlan-level boilerplate is a handful of lines and is lint-checkable.

The cross-filing consistency linter at [`dev/lint_consistency.py`](./dev/lint_consistency.py) verifies that `urpx:initialEffectiveDate`, `urpx:ratePlanUniqueIdentifier`, `urpx:name`, `urpx:timezoneIdentifier`, and the RatePlan `@id` are byte-identical across all filings of a given schedule. Run from the repo root: `python3 dev/lint_consistency.py` (or `--json` for machine-readable output). It refuses, rather than passing, when it finds no RatePlan to compare: it spent the period after the v0.5.1 migration locating none in 41 of 73 filings, reporting "Schedules checked: 0", and exiting 0 with "corpus is consistent", which is the failure mode this sentence previously described as a guarantee.

## 3. Directory hierarchy

```
<country>/<subdivision>/<utility>/<carrier>/<schedule>/versions/<effective-date>/
```

| Segment | Values | Notes |
| --- | --- | --- |
| `<country>` | `us` | ISO 3166-1 alpha-2. Explicit because a bare `ca` reads as either California or Canada. |
| `<subdivision>` | `ca` | ISO 3166-2 subdivision code, here the state. Future: `or`, `wa`, etc. |
| `<utility>` | e.g. `pge`, `sce`, `sdge`, `cpau`, `smud`, `sdcp`, `3ce` | Lowercase short name, the organization's own abbreviation where it has one. Sits above the carrier because PG&E and SDG&E supply both gas and electricity. Where an organization has renamed, the slug keeps the abbreviation its filings and customers still use: `pce` for WestLight Energy, `ebce` for Ava Community Energy. Slugs for the parties MIDAS knows about are listed in [reports/california-parties.md](reports/california-parties.md); one that does not publish to MIDAS, as CPAU does not, appears only here and in its own directory. |
| `<carrier>` | `electricity` | The commodity, mirroring `urpx:commodity` on the filing itself. Present so gas or water can be added later without moving anything. |
| `<schedule>` | e.g. `e-tou-c`, `e-1`, `ev2`, `care` | Lowercase, hyphenated form of the schedule code. |
| `versions/<effective-date>` | ISO 8601 date, e.g. `2026-03-01` | The date this filing becomes effective, as published. |

Example:

```
us/ca/pge/utility.toml                                        # per-utility discovery manifest (§5)
us/ca/pge/electricity/e-tou-c/versions/2026-03-01/            # per-filing directory (§4, §6, §7)
us/ca/pge/electricity/e-tou-c/versions/2026-03-27/
us/ca/cpau/utility.toml
us/ca/cpau/electricity/e-1/versions/2025-07-01/
us/ca/sdcp/utility.toml                                       # manifest only, no filing yet
```

A `urpx:RatePlanModifier` is packaged exactly like a rate plan, under its own
pseudo-schedule directory: `us/ca/sce/electricity/care/versions/2026-03-20/`.
Thirty-three are filed that way. It names the base plans it applies to by IRI,
which is why the corpus is read as one graph (§2).

### Why this nesting

- **Jurisdiction first** — anticipates expansion beyond California.
- **Jurisdiction second** — the regulatory regime differs by state, and a jurisdiction is the unit a consumer filters by.
- **Schedule before date** — a schedule is the long-lived thing; its versions are children. Listing a schedule's directory shows its full revision history.
- **`versions/` literal directory** — leaves room for future sibling directories at the schedule level (e.g. `metadata.toml`, `lineage.md`, `rate-plan.jsonld` if we ever split the file, per §10).

## 4. Per-filing manifest: `tariff.toml`

Each `versions/<date>/` directory contains a `tariff.toml` capturing provenance and processing metadata that does not belong inside the URPX JSON-LD. The schema is at `schema/tariff-manifest.schema.json`.

### 4.1. Single-source filing (the common case)

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

### 4.2. Multi-source filing

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

Sub-table names are free-form (`base`, `modifier_e_nse_1`, etc.); they're for human readability — the schema constrains their spelling but not their meaning. Each sub-table carries the same fields as a single-source `[source]` block. See `us/ca/cpau/electricity/e-1-tou/versions/2026-01-01/tariff.toml` for a working example; it declares three sources, because the filing inlines two modifiers and each traces to its own PDF.

Inlining a modifier is a property of how the *publisher* wrote the schedule, not a packaging choice open to this corpus. Where a modifier is published as its own schedule it gets its own filing directory, and the modifier points back at the base with `urpx:applicableToRatePlan`. Assembling a pre-composed bundle that no single PDF corresponds to gives one version `@id` two definitions in the corpus, and a reader that loads both files then has to pick one.

### 4.3. Per-document regulator metadata in multi-source filings

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

Use this only when the per-document regulatory metadata genuinely differs across the source documents. If they all share one `authority + docket`, the flat single-`[regulator]` form is sufficient. The `authority` enum values (`puc`, `ferc`, `city-council`, `board`, `none`, `unknown`) are deliberately generic — the state context is already in the directory path (`us/ca/...`), and the regulator's full name (e.g. "California Public Utilities Commission") can live in description prose if needed.

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
| `applicable_modifiers` | Corpus-coverage — which RatePlanModifiers legally attach to this schedule | Base RatePlan filings only (omit on modifier filings; two SCE CRS modifiers still carry an empty list, and no lint enforces this) |

**Why two axes.** A base RatePlan being modeling-complete is independent of whether every applicable modifier has its own filing in the corpus. A price server billing a non-CARE customer on E-TOU-C only needs the base RatePlan; one billing a CARE customer needs base + CARE modifier. Conflating them would make `complete = true` mean different things to different consumers.

**Replaces prose deferrals.** Filings predating this convention express deferred work via `(modeling deferred — …)` parentheticals inside `urpx:description` strings. New filings should use the structured `deferrals` array instead; the prose form will be migrated incrementally as filings are revisited.

#### Modifier-coverage tracking: options considered

Two shapes were considered for tracking which modifiers a base RatePlan accepts:

- **Option A — self-declared on the base.** Each base RatePlan filing carries `applicable_modifiers` listing the universe of legally-applicable modifiers per the source PDF, *including modifiers not yet modeled in the corpus*. A lint walks the corpus and reports, per base, which applicable modifiers (i) have a filing under the same utility, and (ii) of those, which have `complete = true`.
- **Option B — derived from the modifier side.** Skip the per-base list entirely. Each RatePlanModifier filing already names its applicable bases via IRI. A corpus walk could collect those references and emit a coverage report without per-base annotation.

**Option A is the chosen approach.** Option B is lighter weight but only sees modifiers that already have filings — it cannot surface the case "we know SCE has a Medical Baseline modifier but no one has modeled it yet", which is the gap signal that matters most. The information *what modifiers legally attach to this schedule* isn't recoverable from the JSON-LD or any other file we keep, so the base manifest is the right home for it.

The lint that consumes `applicable_modifiers` lives at `dev/lint_modifier_coverage.py` and emits `reports/modifier-coverage.md`.

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

`dev/lint_utility_manifests.py` runs in `check_all.py` and validates every manifest against the schema. It then checks three things the schema cannot state, because a schema never sees where a file sits or which files are absent: that `utility` equals the directory it sits in, that no two directories claim the same utility, and that a directory holding filings also holds a manifest.

Three kinds of URL matter most in `tariff_index_urls`, and they answer different questions. A **tariff library or book** is where a schedule's current document is fetched from. An **advice-letter listing** is what says a change happened. A **schedule inventory**, where the utility publishes one, is what says which schedules exist at all and which are grandfathered or closed; SCE's annual "Summary of Available Residential and Nonresidential Rates" is one. The third is the one that bounds a modeling backlog, because it is what distinguishes a schedule this corpus has not modeled from one no longer offered. It is also the easiest to overlook, because it need not look like an index: PG&E's is an HTML page, SDG&E's a JSON endpoint, and SCE's a PDF that reads like a single document.

The schema is intentionally minimal. Richer fields (per-schedule URL templates, AL-listing endpoints, structured scrape recipes) can be added once a real scraper is built and tells us what it needs.

**A `utility.toml` with no filing beside it is a normal shape, not an incomplete one.** It records that an organization sells electricity here, what it is called, and where its tariffs are published, which is what a modeler needs before any filing exists. Most directories are in that state, community choice aggregators and one municipal utility; `dev/lint_utility_manifests.py` prints the current split on every run. Nothing requires a filing: the generators and lints that walk filings find none here, and `coverage.py` counts customers only from modeled rate plans, so such a directory contributes zero rather than distorting a figure.

## 6. IRI naming conventions

Subjects are minted in per-utility CURIE prefixes bound in each filing's `@context`, never in `urpx:`. The `urpx:` prefix names URPX vocabulary terms and enumeration members only. Every prefix resolves under the identity base `https://rate-plans.grid-coordination.energy/`.

| Resource | IRI shape | Example |
| --- | --- | --- |
| Utility (`urpx:Organization`) | `org:utility-<utility>` | `org:utility-pge` |
| RatePlan | `<utility>:<schedule>` | `pge:e-tou-c` |
| RatePlanVersion | `<utility>:<schedule>-<date>` | `pge:e-tou-c-2026-03-01` |
| CoverageClaim | `<utility>:cc-<schedule>-<date>` | `pge:cc-e-tou-c-2026-03-01` |
| Subordinate resources (eligibility rules, ledgers, prices, etc.) | `<utility>:<short>-<descriptor>` | `pge:e-1-2026-03-01-ledger-energy-supply` |

These mirror the convention used in the URPX test cases (e.g. `pge:e-tou-c`). Lowercase, hyphenated, no spaces.

### Scoping subordinate IRIs

URI identity says **one IRI denotes one resource**. Every filing of a utility is loaded into one merged graph at validation time (`dev/validate-with-base.py --utility <slug>`, the gate unit), so a subordinate resource that two filings both mint becomes a single node carrying both filings' values.

**Every subordinate resource takes the IRI of the version that owns it, followed by its descriptor:**

```
<utility>:<owning-version-local-part>-<descriptor>
```

The owning version is the nearest enclosing `urpx:RatePlanVersion` or `urpx:RatePlanModifierVersion`, and its own local part is already `<schedule>-<date>`, so the result reads `pge:e-elec-2026-03-27-price-public-purpose`.

Take the scope from the **owning version, not the directory**. They differ wherever a filing inlines another schedule's subtree: CPAU's `e-1` and `e-1-tou` both inline the whole `cpau:e-hra` modifier, and PG&E inlines a per-plan PCIA modifier into five base filings. Scoping by directory would rename `cpau:e-hra-2023-01-01-price-25-75-gen-480-642` three different ways and mint three copies of one real modifier. Scoping by owner gives it the same IRI in all three files, which is correct, because it is one resource.

Apply it to every subordinate resource, not only to ones observed to collide. An earlier revision of this section said to apply it "only to the IRIs that actually collide on content", and the result was 509 subordinate IRIs minted by more than one schedule, with `sce:price-gen-summer-on-peak-2026-03-20` carrying three different unit prices at once. Content that happens to agree today is not a reason to share an IRI; the next rate case moves one value and the collision appears with nothing to announce it.

**Kept shared, deliberately.** The identity layer names entities that genuinely span a utility's schedules, and scoping those would mint duplicates of one real thing: `urpx:Organization` and its identity/name/identifier nodes, `urpx:RateCase`, `urpx:RatePlan`, `urpx:RatePlanModifier`, `urpx:SourcePublication`, `urpx:ProgramEnrollment`. Version nodes carry `<schedule>-<date>` already. Two subordinate types also stay shared: `urpx:MetricSpecification`, and `urpx:CoverageClaim`, which has its own form `<utility>:cc-<schedule>-<date>`.

Whether a type may stay shared is decided by **closure, not by how utility-level the concept feels**: a shared IRI is safe only if every `sh:maxCount 1` value it carries is a literal, or an IRI that is itself kept shared. A parent that passes a one-level check still breaks once its children are scoped, because it then holds one child per schedule. `urpx:Season` is the instructive case for the other direction. All 72 in the corpus agree within each utility today, but `SeasonShape` sets no `sh:maxCount` on `urpx:month` and all 72 corpus Seasons are month-based, so a future divergence would silently union the months and leave the gate green. CPAU is the one utility whose schedules disagree on season boundaries, and the one that already mints per-schedule Seasons.

`dev/lint_iri_scope.py` enforces this and runs in the gate, so the convention no longer depends on someone noticing. `dev/rescope_iris.py` applies it.

### Blank nodes carry `@id`s too

A node with no `@id` is a fresh blank node on every parse, so it never merges with its counterpart in another filing. Where two filings serialize the same subtree, which section 2 both permits and relies on, the merged graph then holds one blank child per filing under a single named parent, and every `sh:maxCount 1` edge into it is violated. This accounted for 90 of the corpus's remaining violations: 1,468 blank nodes sat under `sh:maxCount 1` edges, and not one of the corpus's 1,184 operand nodes had an `@id`.

**Every node reachable by a `sh:maxCount 1` edge carries an `@id`, named after the node that points at it:**

```
<parent @id>-<property name, minus a leading "has", kebab-cased>
```

So `pge:e-tou-c-2026-03-01-plan-elements`, and below it `...-plan-elements-billing-model`. Because the parent is already scoped to its owning version, the scoping is inherited rather than re-derived, which is what makes an inlined modifier's operands come out identically named in every filing that inlines them.

A child is identified by its parent and its property alone, with no ordinal. An ordinal would depend on array order, and array order is not guaranteed to agree between two serializations of one subtree, so it would defeat the merge it is meant to enable. That is safe only because no parent holds more than one such blank child under a single property; `dev/name_blank_nodes.py --audit` checks that property, along with parent reachability and name collisions, before writing anything.

`dev/name_blank_nodes.py --check` runs in both gate modes and fails on a blank node in scope. This covers `urpx:PlanElements`, `urpx:Prices`, `urpx:PriceSet`, `urpx:BillingModel`, `urpx:CalculationMethod`, `urpx:AlternativeDimensions` and the three operand node types. `urpx:BillingModel` is in scope purely by closure: nothing points at one twice, but `PlanElementsShape` puts `sh:maxCount 1` on `urpx:hasBillingModel`, so naming `PlanElements` without it would trade one class of violation for another.

## 6b. Percentage-of-bill discounts

CARE and FERA discount a percentage of the bill rather than a per-unit rate, so they are modeled as a subtotal plus a multiplier rather than as a price.

**The subtotal lives in the base plan filing**, as a `urpx:PriceSummary` hung off the `PriceSet` holding most of that plan's line items, with `urpx:includesPrice` naming the discountable ones. It belongs there because it sums that plan's own prices. **The discount lives in the modifier**, as a `urpx:Price` carrying `urpx:multiplier` (the negative discount rate) and `urpx:basedOnPrice` pointing at the subtotal. It belongs there because the discount is a property of the program, and the base plan also serves customers not enrolled in it.

**Multiple `urpx:basedOnPrice` values are candidates, read disjunctively.** A modifier applying to every base plan of a utility names all their subtotals on one discount Price; composing it with any one plan leaves the other eight absent, and the one present is used. This is what avoids either reusing an `@id` across plans or minting a discount per plan. Zero resolvable candidates is still an error, so a typo stays loud. URPX itself says nothing about multiplicity; this reading is clj-urpx's, and the case for it is that disjunctive fails loudly when nothing resolves while conjunctive would fail quietly when everything does, silently summing nine unrelated subtotals.

**One subtotal per plan, not per TOU period.** Summary members are gated to the instant being resolved by the same season, month and TOU predicates that gate a tier, so a subtotal naming every discountable line item is correct in every period. Authoring per period would mean roughly eight times as many summaries; `dev/lint_discount_summaries.py` prints the current count.

**Whether the two programs share a subtotal depends on the tariff, not on convenience.** SCE excludes the same two items from both (the PUCRF, and the Climate Credit, which Special Condition 12 applies after the taxes the discount precedes), so CARE and FERA share one subtotal and differ only in rate. SDG&E carves the fixed charge out of both and CARE additionally excludes the charges it is exempt from, so FERA pays the DWR Bond Charge and the Wildfire Fund NBC that CARE does not, and the same plan needs two subtotals with different members.

`dev/lint_discount_summaries.py` re-derives each subtotal from the tariff rule and runs in the gate, because a price added to a plan but not to its subtotal makes the discount too small while every other check stays green.

**One property that is optional in the shapes but load-bearing here**, and not visible to SHACL. A `urpx:Ledger` with no `urpx:referencesMetricInput` keeps its tiers but falls out of the marginal-rate aggregate, which the pinned clj-urpx now refuses rather than answering with a legal-looking zero.

## 7. Source PDF referencing

Each filing's source PDF is **committed alongside the JSON-LD** at:

```
<country>/<subdivision>/<utility>/<carrier>/<schedule>/versions/<date>/<utility>_<schedule>_<date>.pdf
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

### Why the bytes are committed, not just the URL

The earlier convention was *"PDFs are not committed; future consumers can re-fetch and verify byte-identity"*. That convention was reversed on 2026-04-28 after a real demonstration of why URLs alone are not durable provenance: PG&E updated `ELEC_SCHEDS_E-TOU-C.pdf` in place at the canonical URL between our 2026-04-26 retrieval and a 2026-04-28 re-fetch — same URL, different bytes. The original was recoverable only because dcj had a private archive copy. URDB and similar tariff databases are full of broken links and silently-mutated documents for the same reason; URPX's *raison d'être* is auditable provenance, which requires the actual bytes the data was extracted from to live alongside the structured representation.

### Edge case: corrections to the same effective date

If a regulator issues a correction with a new sheet number for the same effective date, extend the filename to include the CPUC leaf identifier (e.g. `pge_e-tou-d_2026-03-27_61254-E.pdf`). Not a problem we have today.

Utility-specific source-document quirks (publication cadence, per-sheet vs whole-document effective dates, opaque vs stable URLs) are documented in each utility's `utility.toml` `scrape_notes` rather than aggregated here.

## 8. Extraction intermediates

Per-filing extraction byproducts (MinerU markdown, OCR layouts, intermediate JSON) live at `versions/<date>/extracted/` and are excluded from git via the top-level `.gitignore`. They are useful locally for debugging the conversion but bloat the repo and are reproducible from the source PDF.

If a particular extraction needs to be preserved (e.g. as evidence of how a tricky table was parsed), commit a single `extracted/notes.md` describing the issue, not the raw output; `**/extracted/` is gitignored, so that needs `git add -f`.

## 9. Workflow: adding a new filing

1. Identify a new tariff PDF (utility website, CPUC e-filing, regulator portal).
2. Create the directory: `<country>/<subdivision>/<utility>/<carrier>/<schedule>/versions/<effective-date>/`, today `us/ca/...`.
3. Write `tariff.toml` with `utility`, `schedule` and `effective_date` at the top level, and a `[source]` table carrying `url`, `sha256` (compute locally) and `retrieved_on`. `schema/tariff-manifest.schema.json` is the authority on what is required.
4. Run extraction (e.g. `mineru -p source.pdf -o extracted/ -b pipeline`).
5. Convert to URPX JSON-LD as `rate-plan_<utility>_<schedule>_<date>.jsonld`.
6. Validate with `clj-urpx` (SHACL) — record outcome in `[validation]`.
7. Record modeling-completeness state in `[modeling]` (§4.4): set `complete = true` and `deferrals = []` if the source PDF is fully captured; otherwise list the deferred parts. On base RatePlan filings, also populate `applicable_modifiers` with every RatePlanModifier the source tariff names — *including modifiers not yet modeled in the corpus*, since this list is what drives the modifier-coverage gap report.
8. Lint cross-filing consistency (RatePlan-level fields match prior filings of this schedule).
9. **Bound the filing this one supersedes.** A tariff sheet never states its own end date; it states which sheet it cancels. So the end of the previous filing is recorded in THIS document, and nowhere else. Read the `Cancelling Revised Cal. P.U.C. Sheet No.` line against the live sheets of the filing you hold, find the sheet that cancels its RATE sheet, and write that sheet's effective date as `urpx:expirationDateTime` on the superseded version node.

   Use the CANCELLING SHEET's effective date, not this filing's. A utility PDF bundles sheets at different revisions, and this corpus dates a filing by its newest sheet, which is often a special-condition sheet rather than a rate sheet. SCE's 2026-03-20 filings carry rates that took effect 2026-01-01 under AL 5725-E; dating the predecessor's end at 2026-03-20 would assert the old rates applied for another 78 days.

   If that leaves a gap before this filing's own effective date, the gap is real: a rate change happened that this corpus never captured. Leave it visible. `reports/version-continuity.md` lists gaps as backlog to backfill from the utility's historical archive, and fails only on overlaps.
10. Commit. Optionally open a PR if review is required.

## 10. Future considerations

- **Non-residential schedules** follow the same layout under their own schedule directories (e.g. `us/ca/pge/electricity/a-1/`). Nothing in the hierarchy splits by customer class.
- **Lineage tracking**: the *interval* is expressed and the link is not. A superseded version carries `urpx:expirationDateTime`, so its span is `[effective, expiration)` and succession can be read off intervals that touch. What cannot be recorded is the link itself, which is the one thing the source actually states. A CPUC sheet says `Cancelling Revised Cal. P.U.C. Sheet No. 90634-E`; there is nowhere on a version to put that. URPX v0.5.1 permits `urpx:supersedes` on `urpx:PricingModel` and `urpx:TariffFiling` only, and `RatePlanVersionShape` and `RatePlanModifierVersionShape` are both `sh:closed`, so neither can carry it even as an extension. `urpx:supersedes` skos:note states the reasoning directly: "Version classes carry no lifecycle of their own: a version's place in the timeline derives from the filing chain." This corpus models no `TariffFiling`, so restoring the lineage it once recorded needs a decision about whether to.
- **Splitting the file** (separating RatePlan from each RatePlanVersion) remains an option if the duplicated boilerplate ever becomes painful. It would not require renaming any existing files — only adding a `rate-plan.jsonld` alongside `versions/`.

## 10b. Mined third-party metadata: `data/midas/`

MIDAS is California's price server, not a tariff source, and none of its price
series is stored here. What is mined by `dev/mine_midas.py` is the metadata
around a Rate Identification Number, because it maps an identifier to a named
party, to a composition, and sometimes to that party's own tariff document.

| Path | Tracked | Holds |
| --- | --- | --- |
| `data/midas/midas.sqlite` | no | the working store, one row per identifier, written in its own transaction as it arrives so an interrupted run loses at most the record in flight. |
| `data/midas/rins.jsonl` | no | the full export, one JSON object per identifier, sorted by identifier with sorted keys. 31MB, and rebuildable from the store with `--export-only`, so it is not carried in git. |
| `data/midas/lookups/*.json` | yes | the ten MIDAS reference tables. `distribution` and `energy` decode the two halves of a party segment into a named organization with a URL, which is how `XXSA` resolves to San Diego Community Power; `location` decodes the fourth field, where `0000` is All Areas. |
| `data/midas/census.json` | yes | the shape of the whole feed without storing it: identifier count, per-segment counts, sub-identifier counts, signal types, and how many rate codes are non-numeric. |

The two tracked entries are what lets a reader see what the feed contains, and
`reports/midas-catalog.md` and `reports/california-parties.md` are generated
from the untracked store. Regenerating either needs a mine first.

### The `rate` table

One table, one row per rate identifier, every column `TEXT` because MIDAS sends
every value as a string and coercing on the way in would lose the distinction
between absent and empty. The database is gitignored and rebuilt from the API,
which is exactly why its schema is written down here.

```sql
CREATE TABLE rate (
  rid               TEXT,   -- RateID.       The identifier. Primary key.
  rate_name         TEXT,   -- RateName
  alt_rate_name_1   TEXT,   -- AltRateName1
  alt_rate_name_2   TEXT,   -- AltRateName2
  rate_type         TEXT,   -- RateType.     TOU, RTP, T-D, ... (lookups/ratetype.json)
  sector            TEXT,   -- Sector.       Res, Com, Ind    (lookups/sector.json)
  end_use           TEXT,   -- EndUse                          (lookups/enduse.json)
  rate_plan_url     TEXT,   -- RatePlan_Url. The utility's own document, where given
  api_url           TEXT,   -- API_Url
  signup_close_date TEXT,   -- SignupCloseDate
  signal_type       TEXT,   -- SignalType
  description       TEXT,   -- Description
  last_updated      TEXT,   -- LastUpdated, FROM THE LISTING, not the detail response
  fetched_at        TEXT,   -- ours: when this row was written, UTC
  PRIMARY KEY (rid)
);
```

`last_updated` is the change key and has to come from the listing: the detail
response carries the field but leaves it null, so taking it from there would
record every row as never updated and re-fetch the whole feed forever.
`fetched_at` is ours and is not exported, because a timestamp that moves every
run would destroy the export's idempotence.

**`rid` is structured, and the structure is the reason a RIN is not a plan
identifier.** It is four hyphen-separated fields: country and state (`USCA`), the
party segment (`PGPG`), the rate code, and a location code. So
`substr(rid,6,4)` is the party, which is how every report groups, and the same
rate code recurs under several locations.

The location field decodes through `lookups/location.json`: 70,214 rows are
`0000` "All Areas", 1,864 are `TEST` "Used for upload testing" (three more are
spelled `Test` and decode to nothing), and the rest name
a grid operator, and 248 name a specific circuit (`012041131` decodes to
`PG&E OAKLAND D 1131`). The test rows are live in the feed
and are not rate plans, so a count that includes them overstates by about 2.5%.

**The store is idempotent and resumable, and both are testable.** Every row
carries the `LastUpdated` MIDAS reported when it was fetched, and a run fetches
only identifiers the store has never seen or whose `LastUpdated` has moved, so a
run that finds nothing new exports byte-identical bytes. `--limit` bounds a run,
so the store can converge over several rather than attempting the whole feed at
once.

Idempotence rests on the payload's `LastUpdated` because nothing else is
offered. Responses carry no `Last-Modified`, no `ETag` and no `Cache-Control`,
and conditional requests are ignored: `If-Modified-Since` and `If-None-Match`
are both answered `200` rather than `304`.

**MIDAS is not only a rate feed.** It carries three signal types: `Electricity
Rates`, `Greenhouse Gas Emissions` (12 identifiers) and `California Independent
System Operator Flex Alert` (1). Only the first has a seller, so
`dev/list_california_parties.py` selects on signal type rather than on party
name, which was a proxy for it that kept missing cases. Several party segments
are separately test and research feeds rather than organizations, and the report
lists whatever it excludes on either ground.

`USCA-FLEX-ALRT-0000` is worth knowing about: it is the CAISO Flex Alert status,
a voluntary conservation call and a production signal, not a test fixture. The
lookup table naming its party segment "MIDAS FlexAlert Test Signal" is
misleading. The signal's own API is documented in the sibling `caiso-flex-alert`
repository.

That one found a bug worth recording, because the symptom was a shortfall small
enough to read as rounding: the mine held 74,096 of the feed's 74,097. Exactly
one listing row omits `LastUpdated`, and the fetch list was built as
`have.get(rid) != lu`. For a row never stored both sides are `None`, so it could
never enter the list and no run would ever have picked it up. An identifier the
store has not seen is now always fetched whatever the listing says about it, and
the store holds all 74,097.

Scope is deliberately not limited to the utilities this corpus models. As of the
same mine the feed carried 74,097 identifiers over 33 party segments, most of
them community choice aggregators, and mining them is how this corpus learns
what exists before modeling it.

**Every count drawn from this feed is point-in-time and has to say so.** MIDAS
is live: parties appear, rename and withdraw, and identifier counts move daily.
Both generated reports carry their as-of in the second paragraph, read from the
store's own fetch stamps rather than from the clock, so regenerating without
re-mining does not silently restate the date. Figures quoted in prose, here and
in a `utility.toml`, carry the mine date beside them for the same reason.

## 10c. Schedule inventories: `data/inventories/`

A filing says what a tariff charges. An inventory says which tariffs exist, which
is the other half of knowing where the corpus stands, and it needs a different
kind of source. `dev/build_inventory.py` writes one file per utility recording
every schedule a source names, which source named it, and when it was first seen.

**Sources are of two kinds, and the distinction is load-bearing.** An *inventory*
source is authoritative about which schedules exist: PG&E's tariff book index
lists its electric schedules, and that list is the answer. An *observed*
source names things it happened to see, at whatever granularity it uses. Only an
inventory source creates a schedule; an observed name attaches to one it matches,
and the match rule is recorded so the attachment can be checked.

Three inventory sources exist, one per investor-owned utility, and they are of
very different quality. The counts below are as of 2026-09-23. A utility adds and
withdraws schedules, and neither `data/inventories/*.json` nor
`reports/rate-plans-to-model.md` stamps an as-of of its own yet, so this date is
the only one and it has to be maintained by hand. SDG&E's is a JSON service with a stable contract that
states which schedules are closed. PG&E's is a regex over the href attributes of
an index page. SCE publishes no enumerable page at all, so its schedules are read
out of the SharePoint folders its hub page links, which is the fragile one: that
listing is virtualized and pages at 30 rows, so scraping the rendered page
returned 30 of Other Rates' 72 files and looked complete. Every SCE count is
checked against the folder's own `ItemCount` for that reason, and the adapter
refuses on a mismatch rather than writing a short inventory.

**An inventory names documents; the corpus models rate plans, and they are not
the same grain.** One SCE PDF is the source for six directories here:
`ELECTRIC_SCHEDULES_TOU-D.pdf` backs `tou-d-4-9pm`, `tou-d-5-8pm`, `tou-d-prime`,
`tou-d-prime-cpp`, `deed-restricted` and `fera`. Matching a directory name
against a schedule code would report all six as unmodeled and `tou-d` as missing.
`dev/list_rate_plans_to_model.py` instead matches each filing's recorded
`[source] url` against the document the inventory names, which settles the
attribution from what the corpus already records rather than from guessing at
names.

Distinct schedule codes can also reduce to one directory name: SDG&E publishes
both `20/20` and `20-20`. The builder records the collision and keeps the loser
under `also_named` rather than silently overwriting it.

Unioning the two over-counts badly, and the first draft did. PG&E's tariff book
named 104 schedules and the MIDAS feed named 118 things (2026-09-23), but only 12 were the same
schedule spelled differently (`A1` for `A-1`); 96 are rate options *within* a
schedule (`A10P` is Primary under A-10); and 10 match nothing. Added together
that is 210 schedules for a utility publishing 104, and an `--offline` run that
lost the real inventory actually wrote 216. Observed names that match
nothing are kept in `unmatched` rather than dropped, because each is either a gap
in the inventory or a name not yet understood.

A utility with no inventory source still gets a file, and that file says
`has_inventory_source: false`. Its schedules are observed names only, so the set
is neither complete nor necessarily at schedule granularity, and no coverage
percentage is computed from it.

`first_seen` is never restamped, so a run that finds nothing new writes
byte-identical files. A schedule that a source stops naming is retained and gains
`last_absent`, because a withdrawn tariff is a fact and its filings stay valid for
the window they covered. `--rebuild` drops retained rows instead, which is what
undoes a run that wrote bad ones; only a person can tell those two cases apart.

## 10d. Fetched documents: `data/documents/`

`dev/fetch_tariff_documents.py` fetches the documents those sources link to and
records provenance in the shape a filing's `tariff.toml` uses: `url`, `sha256`,
`retrieved_on`, `media_type`. `data/documents.json` is that record.

**The documents themselves are committed, and this is settled policy rather than a
size tradeoff to revisit.** Source PDFs disappear from utility websites; this
project has learned that the hard way, so keeping our own copies is not optional
and git is the tool for it. PG&E compounds the problem by reissuing a schedule in
place at the same URL, so even a document still reachable may no longer be the one
we read. Keeping only the `sha256` would preserve the evidence that a document
existed while losing the document itself.

The cost is real and accepted: every in-place reissue adds a full copy that git
keeps forever. When one of these is modeled, its PDF moves into the filing
directory with its own `tariff.toml`, which is where a source document belongs.

Files are laid out `data/documents/<utility>/<filename>`. A publisher that puts
the document's name in the URL keeps it (`ELEC_SCHEDS_E-TOU-C.pdf`); SDG&E puts
nothing there, serving every one of them from `/tariff/` or `/historical/` with the
identity in the query string, so those are named for the schedule and, where the
URL names a year, the year. **No two documents may resolve to one path**, and
that is checked rather than assumed: both naming defects here were this
invariant breaking silently, the manifest recording 159 documents while the
directory held one, with every printed count still looking right. The three publishers
seen so far happen not to collide, each using a prefix of its own (`ELEC_SCHEDS_`
for PG&E, `ELEC_ELEC-SCHEDS_` for SDG&E, `ELECTRIC_SCHEDULES_` for SCE), so this
is not a collision already observed. It is that the prefix convention is an IOU
habit and nothing more: SMUD's documents are named `1-GS-TOU1.ashx`, and a
municipal utility or a community choice aggregator publishing
`residential-rates.pdf` is the obvious next case. Namespacing by utility costs
nothing and does not need the collision to arrive first.

**SDG&E serves its two kinds of schedule from different endpoints.** `/tariff/`
serves only what is in force, so every closed schedule 404s there; `/historical/`
serves them, keyed by `tarfKey` and a year. A closed schedule is recorded at the
last year it was published, which is the version that was in force when it
closed, so the store holds one document per schedule exactly as it does for every
other publisher. The full archive is larger and none of it is fetched: 2026-09-23, 404 schedule-year
pairs for the closed schedules and 1,128 for the current ones.

`TARF_YEARS` is a lower bound rather than the whole range. DR-TOU lists 2000
onward and 1999 returns a real tariff sheet; years genuinely outside the range
404 honestly.

**SDG&E's PDF bytes are not stable, so `sha256` cannot be its change key.**
Fetching one URL three times gives three different hashes: four bytes differ,
deep inside a compressed stream, and the length moves by one. The document is
regenerated per request. The extracted text is identical every time, so
`content_sha256`, the hash of the text, is the change key and `sha256` records
the copy actually held.

This is computed on a document's first fetch, and after that only when the bytes
differ from what is stored, so PG&E (which
answers `304`) and SCE (whose bytes are stable once unwrapped) never pay for it.
Without it every run would rewrite every SDG&E document and report each as
changed, and git would gain a full set of blobs each time. Extraction falls back
to comparing bytes when `pdftotext` is absent or the text cannot be read, which
over-reports change rather than silently under-reporting it.

**Every URL gets a row whatever happens to it.** Most of what the MIDAS feed
links cannot be fetched at all, and that is a finding about the feed rather than
an error to skip past: SMUD's three links redirect to a 404 page while still
returning `200`, so content type decides rather than status or file extension,
and SDG&E's `regarchive` host resolves but never accepts a connection. A prior
successful copy is retained when a later fetch fails, so one bad day does not
erase a document already in hand.

Only one of the three publishers supports a conditional request. PG&E serves both
`Last-Modified` and a strong `ETag` and answers `304`. SDG&E's document service
sends neither, and SharePoint's download endpoint has no usable validator either,
so for those two a run re-downloads the bytes and compares the `sha256`. That is
the cost of knowing whether a document changed: about 150MB of transfer per full
run, against PG&E's cheap `304`s.

`retrieved_on` means when these bytes were first seen rather than when the URL
was last checked, for the same reason given in section 10b.

**SCE's documents need two extra steps, and both are easy to get silently wrong.**
Fetching the rendered file path returns 403 even holding the share cookie; the
`_layouts/15/download.aspx` endpoint is what answers. What it answers with is the
PDF inside a `multipart/form-data` envelope, so the bytes begin with a boundary
marker rather than `%PDF-`. Hashing them unstripped would be worse than useless:
the boundary is regenerated per response, so an unchanged document would hash
differently on every fetch and every run would report a change. The envelope is
stripped before hashing, and the fetcher refuses a payload that is still not a
PDF afterwards.

## 11. Reports: what each one measures

Everything under `reports/` is generated. `dev/check_all.py` runs every generator whose inputs are all tracked, then fails if a tracked file drifted, so those reports are a build failure rather than a stale file. The three that read the untracked MIDAS store are run on demand instead.

The two questions these reports keep apart are **servability** (can a price server resolve this to a price?) and **completeness** (does this JSON-LD fully capture its source PDF?). §4.4 argues the general case: collapsing them into a single ready flag forces the modeler to pick one axis and lie about the other. They are also empirically independent in both directions: a filing can be incomplete over a demand-meter threshold that changes nobody's bill, and a filing can be `complete = true` while understating a marginal rate.

| Report | Generator | Measures |
| --- | --- | --- |
| `service-arrangements.md` / `.edn` | `dev/list_service_arrangements.py` | Every service arrangement the corpus can express, over current versions, at the grain of one base version plus at most one modifier version, with servability read from `dev/baseline/marginal-rates.edn`. Three outcomes, plus one for what was not measured. |
| `ready-for-use.md` / `.edn` | `dev/list_ready_for_use.py` | The same servability, rolled up to one row per `tariff.toml` directory, with `[modeling].complete` alongside it as a separate, separately labeled column. |
| `coverage.md` | `dev/coverage.py` | How much of the statewide residential customer base the corpus reaches, from the estimates in `dev/coverage-estimates.toml`. |
| `modifier-coverage.md` | `dev/lint_modifier_coverage.py` | Which modifiers a base RatePlan declares in `[modeling].applicable_modifiers` have a filing of their own (§4.4, Option A). A corpus-coverage gap report, not a servability one. |
| `modifier-base-pairings.json` / `.edn` | `dev/list_modifier_base_pairings.py` | The compatibility graph, from `urpx:applicableToRatePlan`, at plan-identity grain. |
| `version-continuity.md` / `.edn` | `dev/list_version_continuity.py` | What periods the corpus can price, per plan identity, from `[effective, expiration)` spans laid end to end. Gaps are backlog (a rate change we never captured, recoverable from the utility's archive) and do not fail; overlaps are modeling errors and do. Carries how long since each filing's source was last checked, which is the number that predicts the next gap. |
| `midas-catalog.md` / `.edn` | `dev/list_midas_catalog.py` | What the mined MIDAS feed contains: parties, rate types, sectors, and which rate-plan links point at a tariff document rather than a landing page. Reads the untracked MIDAS store under `data/midas/` (§10b), so it is not in `check_all.py`'s step list and refuses rather than writing an empty report when the store is absent. |
| `california-parties.md` | `dev/list_california_parties.py` | Every organization selling electricity in the MIDAS feed, with its party segment, the `<utility>` slug this corpus assigns it, whether it is investor-owned, publicly owned or a community choice aggregator, and whether it has filings yet. Same untracked dependency and the same refusal. The investor-owned / publicly owned / community choice classification is asserted in the generator, because MIDAS carries none. |
| `rate-plans-to-model.md` | `dev/list_rate_plans_to_model.py` | The backlog: every schedule an inventory names, and whether this corpus models it. Keeps utilities with a real inventory apart from those known only through an observed feed, and computes a coverage percentage only for the former. Carries the document link and, where one has been fetched, says so. |
| `midas-coverage.md` / `.json` | `scripts/build-midas-coverage-report.py` | Which CPUC MIDAS rate identifiers this corpus or the price server covers. Networked, credentialed and slow, so it is deliberately NOT in `check_all.py`'s step list; its age is printed on every full run instead. |

Servability figures are always *as of the recorded baseline*. `dev/baseline/marginal-rates.edn` is not auto-generated: re-record it deliberately with `clojure -M:validate --record-baseline` and review the diff.
