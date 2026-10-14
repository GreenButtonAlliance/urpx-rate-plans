# Contributing to urpx-rate-plans

Thanks for your interest in contributing! This repo is a corpus of [URPX](https://github.com/urpx-org/urpx) rate-plan serializations of US utility tariffs, plus the source PDFs they were extracted from. The first BHAG (see [README.md](./README.md)) is to model all California residential tariffs in customer-count priority order.

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
- Match the existing tone and structure. Rate plans in this repo are scaffolded from existing patterns (see the `tariff.toml` notes for pattern references), validated by both [clj-shacl](https://github.com/dcj/clj-shacl) (SHACL, on Apache Jena) and [clj-urpx](https://github.com/grid-coordination/clj-urpx), and kept structurally consistent across utilities so a price-server consuming the corpus doesn't have to special-case different utilities.
- One commit per logical change is fine; we don't require squash or any particular branch naming.

## Setup

You need Java 21 or later, the [Clojure CLI](https://clojure.org/guides/install_clojure), Python 3.10 or later, and git.

1. Clone this repository and [urpx-org/urpx](https://github.com/urpx-org/urpx) side by side:

   ```bash
   git clone https://github.com/grid-coordination/urpx-rate-plans.git
   git clone https://github.com/urpx-org/urpx.git
   ```

   The SHACL step reads the URPX shapes and ontology from that clone at pinned revisions, so it needs a full clone, not a shallow one. To keep the clone elsewhere, set `URPX_CHECKOUT` to its path. When the pins move to a new tag, run `git -C ../urpx fetch --all --tags`.

2. Install the Python packages into a virtualenv, and set `URPX_RATE_PLANS_VENV` to it so the gate activates it:

   ```bash
   python3 -m venv ~/.venvs/urpx-rate-plans
   ~/.venvs/urpx-rate-plans/bin/pip install -r dev/requirements.txt
   export URPX_RATE_PLANS_VENV=~/.venvs/urpx-rate-plans
   ```

3. Install the pre-commit hook, which regenerates `reports/` and `catalog/` and runs `dev/gate.sh --fast`:

   ```bash
   git config core.hooksPath dev/git-hooks
   ```

4. Check the setup with `dev/gate.sh --full`. The gate runs [clj-kondo](https://github.com/clj-kondo/clj-kondo) and [reuse](https://reuse.software/) when they are on `PATH`, and skips them otherwise.

The Clojure libraries, [clj-urpx](https://github.com/grid-coordination/clj-urpx) and [clj-shacl](https://github.com/dcj/clj-shacl), come from Clojars through `deps.edn`. To work against a local checkout of either, override it for one run:

```bash
clojure -Sdeps '{:deps {energy.grid-coordination/clj-urpx {:local/root "../clj-urpx"}}}' -M:nrepl
```

Optionally, keep an nREPL running from the repository root with `clojure -M:nrepl`. `dev/shacl.sh` runs inside it when it answers on the port in `.nrepl-port`, which saves a JVM start on every SHACL run; `URPX_NREPL_PORT=none` turns that off.

## LLM coding assistants

[`AGENTS.md`](./AGENTS.md) holds the shared instructions for LLM coding assistants (Codex, Cursor, GitHub Copilot and others read it; [`CLAUDE.md`](./CLAUDE.md) imports it for Claude Code). Change it by pull request when the project's conventions change.

Keep your personal configuration out of the repo: `CLAUDE.local.md` (which Claude Code loads alongside `CLAUDE.md`), `.claude/`, `.cursor/` and the like are gitignored. To version them anyway, keep them in a separate private "shadow" repository and symlink them into your working tree; for a file you don't need to version, `.git/info/exclude` works too.

## Adding a new rate plan

The end-to-end workflow for adding a single new rate plan is documented in [LAYOUT.md §9](./LAYOUT.md#9-workflow-adding-a-new-filing). In short:

1. Pick a pattern reference — an existing rate plan whose structure most closely matches the new one (e.g. another utility's residential TOU rate, another modifier with the same compensation mechanism).
2. Create the filing directory: `<country>/<subdivision>/<utility>/<carrier>/<schedule>/versions/<effective-date>/`, for example `us/ca/pge/electricity/e-tou-c/versions/2026-03-01/`.
3. Commit the source tariff PDF alongside the JSON-LD; record its `sha256` and the canonical retrieval URL in `tariff.toml`.
4. Author the JSON-LD (using the URPX ontology), making the rate plan self-contained. Wrap it in a `urpx:URPXPackage` carrying `urpx:targetURPXVersion`. (`urpx:URPXDocument` was retired at URPX v0.3.0.) A filing that also carries standalone `@graph` siblings such as `urpx:ProgramEnrollment` or `urpx:RateCase` keeps them beside the package rather than inside it, since `URPXPackageShape` is closed and does not admit them.

   Seattle City Light's JSON-LD is generated from Clojure source in `src/rate_plans/us/wa/scl/`: edit the source, not the JSON-LD, and write the documents with `python3 dev/check_generated.py --write`. The gate fails when a committed document differs from the source ([doc/dsl-source.md](./doc/dsl-source.md)).
5. Run `dev/shacl.sh --utility <slug>` to SHACL-validate. The gate unit is a MERGED graph per utility, not a single file: cross-file references (`urpx:applicableToRatePlan`, `urpx:supersedes`) only resolve when the referent is in the same graph. Shapes are read from the URPX clone described in [Setup](#setup) and are deliberately not vendored here. Single-file mode exists but is a labelled diagnostic, not a gate.
6. Run `clojure -M:validate` for end-to-end load, coerce, resolve verification through the clj-urpx consumer. Filings are discovered automatically; there is no list to add to.
7. Update `dev/coverage-estimates.toml` if this is a new utility or significantly shifts a utility's per-tariff residential share.
8. Document what's modeled, what's deferred, and any URPX vocabulary gaps in `tariff.toml [extraction.notes]`.

## Modeling judgment calls

A few patterns we've found helpful:

- **Pattern reference first.** Before authoring a new rate plan, identify the closest existing rate plan in the corpus and scaffold from it. This keeps cross-utility shape consistent.
- **Pause when URPX vocabulary doesn't fit.** If you can't express a regulatory rule in URPX cleanly, don't invent a custom shape — file an issue against [urpx-org/urpx](https://github.com/urpx-org/urpx) describing the gap with a concrete example, as [urpx-org/urpx discussion #34](https://github.com/urpx-org/urpx/discussions/34) does for percentage-of-bill discounts.
- **[clj-urpx](https://github.com/grid-coordination/clj-urpx) is also WIP.** Its load-coerce-resolve pipeline is the validator we lean on for end-to-end checks beyond SHACL, but it is in no way definitive — in the course of modeling tariffs in this repo we have repeatedly hit missing capabilities or bugs in it. If you encounter one, please file a Discussion or Issue at [grid-coordination/clj-urpx](https://github.com/grid-coordination/clj-urpx) so the validator improves alongside the corpus.
- **Description prose is part of the contract.** When a regulatory rule can't be expressed structurally, document it clearly in `urpx:description` on the relevant `RatePlanVersion` / `RatePlanModifierVersion`. A consumer reading the JSON-LD should be able to understand exactly what's modeled and what isn't.
- **Provenance over prediction.** Every rate plan's `tariff.toml [source]` block records the canonical URL, retrieval date, and `sha256` of the source PDF. If a utility republishes a different PDF at the same URL (this happens — PG&E updated `ELEC_SCHEDS_E-TOU-C.pdf` in place between two retrievals two days apart), the committed PDF + `sha256` are the durable record.

## Code of conduct

Be respectful and constructive. We're a small project and appreciate everyone who takes the time to file an issue or send a PR.

## Important notice

This corpus is provided on an "as-is" basis. Updates and maintenance, including responses to issues filed on GitHub, will take place on an "as time and resources permit" basis. As the [README disclaimer](./README.md#disclaimer) notes, our modeling is best-effort and has not been reviewed by URPX experts — independent verification against the committed source PDF is recommended for any consumer using these files for billing-correctness purposes.
