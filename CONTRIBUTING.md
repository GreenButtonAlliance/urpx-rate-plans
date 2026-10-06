# Contributing to urpx-rate-plans

Thanks for your interest in contributing! This repo is a corpus of [URPX](https://github.com/urpx-org/urpx) rate-plan serializations of US utility tariffs, all of them Californian so far, plus the source PDFs they were extracted from. The first BHAG (see [README.md](./README.md)) is to model all California residential tariffs in customer-count priority order.

We are URPX newbies (see the [Disclaimer](./README.md#disclaimer) in the README) — outside review of our modeling is genuinely welcome.

## How to contribute

### Discussions

Use [Discussions](https://github.com/grid-coordination/urpx-rate-plans/discussions) for:

- Questions about how a particular rate plan or modifier was modeled (and why)
- Modeling judgment calls — "is this the right URPX shape?" / "is this `chargeType` correct?"
- Proposing a new utility or rate plan to add to the corpus
- Sharing what you're doing with the data downstream
- Asking for advice when extracting a tariff that has an unusual structure

Discussions are open-ended — a good place to think out loud or scope something before it becomes a concrete change. Aligned outcomes from a Discussion often turn into one or more Issues.

### Issues

Use [Issues](https://github.com/grid-coordination/urpx-rate-plans/issues) for actionable changes:

- Confirmed modeling errors (wrong unit price, misused class, eligibility predicate that doesn't match the source PDF)
- Missing rate plans for utilities the corpus is supposed to cover
- Provenance bugs (`tariff.toml` sha256 mismatch, broken `[source.url]`, wrong effective date)
- Schema changes (`schema/tariff-manifest.schema.json`, `schema/utility-manifest.schema.json`)
- Stale or incorrect prose in `README.md`, `LAYOUT.md`, or any rate plan's `tariff.toml`

If you're not sure whether something is an Issue or a Discussion, start with a Discussion — we can convert it later.

### Pull requests

Pull requests are welcome.

- For small fixes (typos, broken links, dead code, single-rate-value corrections backed by the committed source PDF), open a PR directly.
- For substantive changes (new utilities, new modifier shapes, manifest-schema changes, restructuring the directory hierarchy), open a Discussion or Issue first so we can align on scope before you invest the effort.
- Match the existing tone and structure. Rate plans in this repo are scaffolded from existing patterns (see the `tariff.toml` notes for pattern references), validated by both [pyshacl](https://github.com/RDFLib/pySHACL) and [clj-urpx](https://github.com/grid-coordination/clj-urpx), and kept structurally consistent across utilities so a price-server consuming the corpus doesn't have to special-case different utilities.
- One commit per logical change is fine; we don't require squash or any particular branch naming.

## Adding a new rate plan

The end-to-end workflow for adding a single new rate plan is documented in [LAYOUT.md §11](./LAYOUT.md#11-adding-a-new-filing). In short:

1. Pick a pattern reference — an existing rate plan whose structure most closely matches the new one (e.g. another utility's residential TOU rate, another modifier with the same compensation mechanism).
2. Create the filing directory: `us/<country>/<subdivision>/<utility>/<carrier>/<schedule>/versions/<effective-date>/`, for example `us/ca/pge/electricity/e-tou-c/versions/2026-03-01/`.
3. Commit the source tariff PDF alongside the JSON-LD; record its `sha256` and the canonical retrieval URL in `tariff.toml`.
4. Author the JSON-LD (using the URPX ontology), making the rate plan self-contained. Wrap it in a `urpx:URPXPackage` carrying `urpx:targetURPXVersion`. (`urpx:URPXDocument` was retired at URPX v0.3.0.) A filing that also carries standalone `@graph` siblings such as `urpx:ProgramEnrollment` or `urpx:RateCase` keeps them beside the package rather than inside it, since `URPXPackageShape` is closed and does not admit them.
5. Run `python3 dev/validate-with-base.py --utility <slug>` to SHACL-validate. The gate unit is a MERGED graph per utility, not a single file: cross-file references (`urpx:applicableToRatePlan`, `urpx:supersedes`) only resolve when the referent is in the same graph. Shapes are read from an adjacent `../urpx` checkout at a pinned revision and are deliberately not vendored here; the script tells you what to do if that checkout is missing. Single-file mode exists but is a labelled diagnostic, not a gate.
6. Run `clojure -M:validate` for end-to-end load, coerce, resolve verification through the clj-urpx consumer. Filings are discovered automatically; there is no list to add to.
7. Update `dev/coverage-estimates.toml` if this is a new utility or significantly shifts a utility's per-tariff residential share.
8. Document what's modeled, what's deferred, and any URPX vocabulary gaps in `tariff.toml [extraction.notes]`.

## Modeling judgment calls

A few patterns we've found helpful:

- **Pattern reference first.** Before authoring a new rate plan, identify the closest existing rate plan in the corpus and scaffold from it. This keeps cross-utility shape consistent.
- **Pause when URPX vocabulary doesn't fit.** If you can't express a regulatory rule in URPX cleanly, don't invent a custom shape — file an issue against [urpx-org/urpx](https://github.com/urpx-org/urpx) describing the gap with a concrete example. The current vocabulary-gap discussion is at [urpx-org/urpx#24](https://github.com/urpx-org/urpx/issues/24).
- **[clj-urpx](https://github.com/grid-coordination/clj-urpx) is also WIP.** Its load-coerce-resolve pipeline is the validator we lean on for end-to-end checks beyond pyshacl, but it is in no way definitive — in the course of modeling tariffs in this repo we have repeatedly hit missing capabilities or bugs in it. If you encounter one, please file a Discussion or Issue at [grid-coordination/clj-urpx](https://github.com/grid-coordination/clj-urpx) so the validator improves alongside the corpus.
- **Description prose is part of the contract.** When a regulatory rule can't be expressed structurally, document it clearly in `urpx:description` on the relevant `RatePlanVersion` / `RatePlanModifierVersion`. A consumer reading the JSON-LD should be able to understand exactly what's modeled and what isn't.
- **Provenance over prediction.** Every rate plan's `tariff.toml [source]` block records the canonical URL, retrieval date, and `sha256` of the source PDF. If a utility republishes a different PDF at the same URL (this happens — PG&E updated `ELEC_SCHEDS_E-TOU-C.pdf` in place between two retrievals two days apart), the committed PDF + `sha256` are the durable record.

## Code of conduct

Be respectful and constructive. We're a small project and appreciate everyone who takes the time to file an issue or send a PR.

## Important notice

This corpus is provided on an "as-is" basis. Updates and maintenance, including responses to issues filed on GitHub, will take place on an "as time and resources permit" basis. As the [README disclaimer](./README.md#disclaimer) notes, our modeling is best-effort and has not been reviewed by URPX experts — independent verification against the committed source PDF is recommended for any consumer using these files for billing-correctness purposes.
