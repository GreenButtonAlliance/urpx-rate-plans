# Repository Layout

This document defines the conventions for organizing tariff data in this repo. It is the source of truth for directory structure, file naming, manifest schema, and the temporal model.

## 1. The temporal model: RatePlan vs RatePlanVersion

URPX models a tariff using two related concepts:

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
- the (filing-specific) `urpx:RatePlanVersion` nested via `urpx:hasRatePlanVersion`.

This mirrors the convention used by the URPX test cases (e.g. `test-cases/cpau-e-1-2025-07-01/data/urpx-rate-plan_cpau_e-1_2025-07-01.jsonld`).

Rationale:
- Each filing artifact is self-contained, portable, and can be cited or distributed in isolation.
- RDF graph merge handles the overlap cleanly: every file describes the same `urpx:RatePlan` IRI with consistent properties — merging multiple files yields a single RatePlan with all its versions linked.
- The duplicated RatePlan-level boilerplate (~15 lines) is small and lint-checkable.

A linter (TBD) will verify that `urpx:initialEffectiveDate`, `urpx:ratePlanUniqueIdentifier`, `urpx:name`, and the RatePlan `@id` are identical across all filings of a given schedule.

## 3. Directory hierarchy

```
<jurisdiction>/<class>/<utility>/<schedule>/versions/<effective-date>/
```

| Segment | Values | Notes |
| --- | --- | --- |
| `<jurisdiction>` | `ca` | Two-letter state code. Future: `or`, `wa`, etc. |
| `<class>` | `iou`, `pou`, `coop`, `cca` | Investor-owned utility, publicly-owned utility, cooperative, community choice aggregator. Filing rules and regulators differ by class. |
| `<utility>` | e.g. `pge`, `sce`, `sdge`, `cpau`, `smud`, `ladwp` | Lowercase short name. Match the EIA short name where one exists. |
| `<schedule>` | e.g. `e-tou-c`, `e-1`, `ev2`, `e-care` | Lowercase, hyphenated form of the schedule code. |
| `versions/<effective-date>` | ISO 8601 date, e.g. `2026-03-01` | The date this filing becomes effective, as published. |

Example:

```
ca/iou/pge/e-tou-c/versions/2026-03-01/
ca/iou/pge/e-tou-c/versions/2025-09-01/
ca/pou/cpau/e-1/versions/2025-07-01/
```

### Why this nesting

- **Jurisdiction first** — anticipates expansion beyond California.
- **Class second** — the regulatory regime differs by class (CPUC vs municipal council vs CARE-only IOU schedules), and many tools will want to filter by class.
- **Schedule before date** — a schedule is the long-lived thing; its versions are children. Listing a schedule's directory shows its full revision history.
- **`versions/` literal directory** — leaves room for future sibling directories at the schedule level (e.g. `metadata.toml`, `lineage.md`, `schedule.jsonld` if we ever split the file).

## 4. Per-filing manifest: `tariff.toml`

Each `versions/<date>/` directory contains a `tariff.toml` capturing provenance and processing metadata that does not belong inside the URPX JSON-LD.

```toml
# Identity --------------------------------------------------------------------
utility       = "pge"
schedule      = "e-tou-c"
effective_date = "2026-03-01"

# Source ----------------------------------------------------------------------
[source]
url           = "https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_SCHEDS_E-TOU-C.pdf"
sha256        = "9c2f6b3e..."
retrieved_on  = "2026-04-26"
media_type    = "application/pdf"
filing_type   = "advice-letter"          # advice-letter | application | resolution | unknown
filing_id     = "PGE-AL-7234-E"          # if known

# Regulatory ------------------------------------------------------------------
[regulator]
authority     = "cpuc"                   # cpuc | city-council | board | none
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

# Review ----------------------------------------------------------------------
[review]
status        = "draft"                  # draft | reviewed | published | superseded
reviewer      = ""                       # email or handle
reviewed_on   = ""
notes         = ""                       # short free text
```

Fields marked optional may be omitted (TOML simply elides them). `source.url` and `source.sha256` are required so the original PDF is always retrievable and verifiable. The schema is mirrored in `schema/tariff-manifest.schema.json` for tooling.

## 5. IRI naming conventions

| Resource | IRI shape | Example |
| --- | --- | --- |
| Utility (`urpx:Organization`) | `urpx:utility-<utility>` | `urpx:utility-pge` |
| RatePlan | `urpx:<utility>-<schedule>` | `urpx:pge-e-tou-c` |
| RatePlanVersion | `urpx:<utility>-<schedule>-<date>` | `urpx:pge-e-tou-c-2026-03-01` |
| Subordinate resources (eligibility rules, ledgers, prices, etc.) | `urpx:<utility>-<short>-<descriptor>` | `urpx:pge-er-residential`, `urpx:pge-ledger-commodity` |

These mirror the convention used in the existing URPX test cases (e.g. `urpx:cpau-e-1`, `urpx:cpau-e-1-2025-07-01`). Lowercase, hyphenated, no spaces.

## 6. Source PDF referencing

PDFs are **not committed**. The URPX `urpx:hasDataSourceReference` block in each JSON-LD points at the canonical published URL:

```json
"urpx:hasDataSourceReference": {
  "@type": "urpx:DataSourceReference",
  "urpx:url": "https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_SCHEDS_E-TOU-C.pdf",
  "urpx:fileName": "ELEC_SCHEDS_E-TOU-C.pdf",
  "urpx:mediaType": "application/pdf"
}
```

The `tariff.toml` carries the sha256 and the date the document was retrieved, so a future consumer can re-fetch and verify byte-identity.

## 7. Extraction intermediates

Per-filing extraction byproducts (MinerU markdown, OCR layouts, intermediate JSON) live at `versions/<date>/extracted/` and are excluded from git via the top-level `.gitignore`. They are useful locally for debugging the conversion but bloat the repo and are reproducible from the source PDF.

If a particular extraction needs to be preserved (e.g. as evidence of how a tricky table was parsed), commit a single `extracted/notes.md` describing the issue, not the raw output.

## 8. Workflow: adding a new filing

1. Identify a new tariff PDF (utility website, CPUC e-filing, regulator portal).
2. Create the directory: `ca/<class>/<utility>/<schedule>/versions/<effective-date>/`.
3. Write `tariff.toml` with `source.url`, `source.sha256` (compute locally), `retrieved_on`, and `extraction.tool`.
4. Run extraction (e.g. `mineru -p source.pdf -o extracted/ -b pipeline`).
5. Convert to URPX JSON-LD as `rate-plan_<utility>_<schedule>_<date>.jsonld`.
6. Validate with `clj-urpx` (SHACL) — record outcome in `[validation]`.
7. Lint cross-filing consistency (RatePlan-level fields match prior filings of this schedule).
8. Commit. Optionally open a PR if review is required.

## 9. Future considerations

- **Tariff modifiers** (`urpx:RatePlanModifier`, e.g. CARE discount, NEM credit) can stand alone at `versions/` paths under their own pseudo-schedule directory, e.g. `ca/iou/pge/e-care/versions/...` — they share the same packaging. Cross-references to the base RatePlan use IRIs.
- **Non-residential schedules** follow the same layout under their own schedule directories (e.g. `ca/iou/pge/a-1/`). The class-level split is by utility class, not by customer class.
- **Lineage tracking** (this version supersedes that one) is captured by `urpx:supersedes` inside the JSON-LD, not by directory layout. Adoption deferred per URPXT-4uf, blocked on urpx-org/urpx#16.
- **Splitting the file** (separating RatePlan from each RatePlanVersion) remains an option if the duplicated boilerplate ever becomes painful. It would not require renaming any existing files — only adding a `rate-plan.jsonld` alongside `versions/`.
