# Generating the corpus from Clojure source

Every URPX document in the corpus is to be generated from Clojure source written with `urpx.dsl`, as the Seattle City Light documents are today ([dsl-source.md](./dsl-source.md)). The generated JSON-LD stays committed and stays what the corpus publishes. A document records where it was generated from in its filing's manifest, the way it records the tariff document it was modeled from.

## Provenance

A filing whose documents are generated carries a `[generation]` table in its `tariff.toml`, beside `[source]` (the tariff document the facts come from) and `[extraction]` (how they were read from it). `[generation]` says how the committed bytes were made.

```toml
[generation]
generator = "urpx.dsl"
sources = [
  "src/rate_plans/us/wa/scl/rts.clj",
  "src/rate_plans/us/wa/scl/common.clj",
]
entry = "rate-plans.us.wa.scl.rts/rts"
command = "python3 dev/check_generated.py --write"
```

| Key | Meaning |
| --- | --- |
| `generator` | `urpx.dsl` for Clojure source; `python` for a filing still built by a script |
| `sources` | Repository paths of every source file the document is generated from |
| `entry` | The `:document` var of each document in the filing: a string, or an array when the filing holds more than one |
| `command` | The command that writes it |

A filing with no `[generation]` table is authored as JSON-LD. The table carries no hash, commit or generator version: the gate regenerates every generated document on every commit with the clj-urpx release pinned in `deps.edn` and fails on any difference, so the claim is checked rather than recorded, and the version is the one `deps.edn` names at that commit.

`schema/tariff-manifest.schema.json` gains the table, since the manifest schema is closed.

## Navigation

- `catalog/corpus.jsonld` gives each generated document's distribution `prov:wasDerivedFrom` links to its filing's `sources` and a `prov:wasGeneratedBy` activity titled with the filing's `generator` and associated with the clj-urpx release that emitted it, read from `deps.edn` when the catalog is built ([catalog/README.md](../catalog/README.md#model)). A client walking the DCAT catalog reaches the source and the generator without reading TOML, and a copy of the catalog published outside the repository keeps both.
- A generated report lists every generated document with its source files, entry and clj-urpx release, and every source file with the documents it emits.

## Checks

- Every path in `sources` exists, and regenerating `entry` writes the committed document byte for byte.
- Every document the source tree emits sits in a filing whose `[generation]` names it. Together with the first check, this makes the mapping hold in both directions.

## Conversion

1. **Normalize.** Re-emit each utility's authored documents through the clj-urpx emitter in a commit of its own. Every document already round-trips RDF-identically when emitted with its own @context over `urpx.emit/default-context` ([dsl-source.md](./dsl-source.md#evidence)), so the commit changes formatting only, and an RDF comparison of before and after proves it. From then on, byte equality is a fair acceptance test.
2. **Bootstrap.** A one-time converter writes DSL source from a family's JSON-LD, giving a starting point that regenerates its documents byte for byte.
3. **Refactor.** Restate the bootstrapped source as the tariff states it: rate tables keyed by effective date, period tables, holiday lists ([dsl-source.md](./dsl-source.md#requirements)). A new version is then a new row. Byte equality is the acceptance test at every step.
4. **Record.** Add `[generation]` to each converted filing and retire the scripts that built it. The `scripts/` rule (a filing whose data a script emitted ships that script) then describes the document's earlier bytes, which git history keeps.

## Order

Families with many versions and shared structure gain the most and convert first: PG&E residential (E-1, E-ELEC, E-TOU-C, E-TOU-D, EV2 and their modifiers), SCE TOU-D, and the Net Billing Tariff export-credit grids. PG&E E-TOU-C is the pilot. One-off filings convert last.

## DSL coverage

clj-urpx is extending `urpx.dsl` to express every construct the corpus uses, and then the whole URPX vocabulary. A family converts once the DSL expresses all of its constructs; the pilot establishes what the PG&E residential documents need.
