# urpx-rate-plans

Instructions for LLM coding assistants working in this repository. Personal additions go in a gitignored local file (`CLAUDE.local.md` for Claude Code); see [CONTRIBUTING.md](./CONTRIBUTING.md#llm-coding-assistants).

A corpus of URPX rate plans, each a filing directory holding the tariff PDF, a `tariff.toml` manifest and the JSON-LD. Read [LAYOUT.md](./LAYOUT.md) before changing anything; walk the corpus with a walker from `corpus.json`, not hand-written globs. Setup is in [CONTRIBUTING.md](./CONTRIBUTING.md#setup).

## The session

Start an nREPL from the repository root and leave it running:

```bash
clojure -M:nrepl
```

It writes `.nrepl-port`. Run Claude Code from the same root with [clojure-mcp](https://github.com/bhauman/clojure-mcp) configured as an MCP server. Its `list_nrepl_ports` tool finds the server and `clojure_eval` evaluates in it. Use them to answer questions about clj-urpx and clj-shacl by introspection (`doc`, `source`, `dir`, `ns-publics`) before reading jars or grepping.

Before writing a helper in the DSL source, search the shared namespaces for one that already exists: `clojure -M:xref init`, then `who-calls`, `who-references` and `unused` ([clj-xref](https://github.com/danlentz/clj-xref)), and `apropos` and `ns-publics` in the nREPL.

`dev/shacl.sh`, and so the gate's SHACL step, runs inside that nREPL when one answers, and otherwise starts a JVM. Changing a dependency version in `deps.edn` needs a restart of the nREPL.

Stop an nREPL only by its own PID. Never `pkill` or `killall` by pattern: other sessions on the same machine run their own.

## Agents and worktrees

Parallel work runs in git worktrees, one branch each. In a worktree, set `URPX_NREPL_PORT=none` so `dev/shacl.sh` starts its own JVM rather than using an nREPL started in another checkout. An agent stops when its gate is green; merging to `main` is a maintainer's decision.

## Finding a tariff PDF

Each utility's `utility.toml` lists where it publishes its tariffs (`tariff_index_urls`, [LAYOUT.md §5](./LAYOUT.md#5-per-utility-discovery-manifest-utilitytoml)). Some of those pages render their links with JavaScript or need a browser session before a download works. [spel](https://github.com/Blockether/spel), a native Playwright CLI, drives a real browser from the shell; install the native binary from its GitHub releases, then `spel install` for the browsers.

```bash
spel open <tariff-index-url>
spel snapshot -i                     # interactive elements, numbered refs
spel get attr "ref=<N>" href         # a link's target
spel markdownify                     # the page as Markdown
spel cookies                         # the session's cookies, for curl
spel close
```

Download the PDF with `curl` once spel has its URL, passing a cookie when the host needs one. `us/ca/sce/utility.toml` records the recipe for SCE's SharePoint library, which needs both. Record the URL, sha256 and retrieval date in the filing's `tariff.toml`.

## Reading a tariff PDF

Extract the PDF to Markdown with [MinerU](https://github.com/opendatalab/MinerU) before modeling it. Its layout analysis keeps rate tables as tables, which a plain text dump does not.

```bash
mineru-kit parse <schedule>.pdf -o extracted/<schedule>.md --tier standard
```

The `standard` tier reads each page with MinerU's vision-language model, which places rate-table cells in the right rows where the `basic` tier and MinerU 3.x misplace some. `extracted/` is gitignored ([LAYOUT.md](./LAYOUT.md)); record the tool, its version and the date in the manifest's `[extraction]` table.

Install MinerU 4.x in its own environment, because its dependencies pin versions that conflict with other Python tooling, then download the `standard` tier's models once:

```bash
pipx install 'mineru>=4.0,<5'
mineru-kit models download --tier standard
```

## The gate

- `dev/gate.sh --fast` runs from the pre-commit hook (`git config core.hooksPath dev/git-hooks`) on what the commit stages. The repository has no CI.
- `dev/gate.sh --changed` runs what a branch's changes since `main` can affect. Run it before asking for a merge; it refuses while there are uncommitted changes.
- `dev/gate.sh --full` runs everything. Run it before a release. With `git config urpx.postPushGate true`, the pre-push hook also runs it in the background on each push to `main` ([dev/git-hooks/README.md](./dev/git-hooks/README.md)).
- `dev/gate-steps.toml` declares which changes select each step in `--fast` and `--changed`. A new step in `dev/gate.sh` or `dev/check_all.py` needs an entry there; `dev/test_gate_steps.py` fails without one.
- Exit codes: 0 green, 1 regression, 2 drift (a generated file was not committed), 3 refused (the harness cannot answer, for example a missing URPX checkout).
- `reports/` and `catalog/` are generated. The hook regenerates them from the staged tree; never edit them by hand.
- Seattle City Light's JSON-LD is generated from `src/rate_plans/`. Edit the source and run `python3 dev/check_generated.py --write` ([doc/dsl-source.md](./doc/dsl-source.md)).

## Conventions

- Answer questions about the URPX ontology and shapes (domains, ranges, closed shapes, allowed values) with SPARQL over the URPX checkout, using rdflib, not grep.
- `xsd:decimal` values are written as strings with an explicit scale (`"0.16100"`), never in exponent form; `dev/lint_decimal_literals.py` rejects ill-typed decimal literals. In Clojure source, use BigDecimals (`16.10M`).
- Clojure is pretty-printed, one form per line unless the form is short, and `clj-kondo` clean.
- Durable prose states invariants, not counts that go stale ("every document round-trips", not a tally of documents). Counts belong in generated reports.
- Markdown prose is one line per paragraph, not hard-wrapped.
- Commit messages say what the diff does, and nothing it does not.
