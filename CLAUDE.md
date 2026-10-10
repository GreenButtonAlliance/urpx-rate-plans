# urpx-rate-plans

A corpus of URPX rate plans, each a filing directory holding the tariff PDF, a `tariff.toml` manifest and the JSON-LD. Read [LAYOUT.md](./LAYOUT.md) before changing anything; walk the corpus with a walker from `corpus.json`, not hand-written globs. Setup is in [CONTRIBUTING.md](./CONTRIBUTING.md#setup).

## The session

Start an nREPL from the repository root and leave it running:

```bash
clojure -M:nrepl
```

It writes `.nrepl-port`. Run Claude Code from the same root with [clojure-mcp](https://github.com/bhauman/clojure-mcp) configured as an MCP server. Its `list_nrepl_ports` tool finds the server and `clojure_eval` evaluates in it. Use them to answer questions about clj-urpx and clj-shacl by introspection (`doc`, `source`, `dir`, `ns-publics`) before reading jars or grepping.

`dev/shacl.sh`, and so the gate's SHACL step, runs inside that nREPL when one answers, and otherwise starts a JVM. Changing a dependency version in `deps.edn` needs a restart of the nREPL.

Stop an nREPL only by its own PID. Never `pkill` or `killall` by pattern: other sessions on the same machine run their own.

## Agents and worktrees

Parallel work runs in git worktrees, one branch each. In a worktree, set `URPX_NREPL_PORT=none` so `dev/shacl.sh` starts its own JVM rather than using an nREPL started in another checkout. An agent stops when its gate is green; merging to `main` is a maintainer's decision.

## The gate

- `dev/gate.sh --fast` runs from the pre-commit hook (`git config core.hooksPath dev/git-hooks`). It is the only automatic check; the repository has no CI.
- `dev/gate.sh --full` runs everything. Run it before asking for a merge.
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
