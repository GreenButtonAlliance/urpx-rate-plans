# Filings authored as Clojure source

Each filing's JSON-LD is generated from Clojure source written with `urpx.dsl`. The source states a filing the way its tariff does: rate tables keyed by effective date, a table of time-of-use brackets, a holiday list. The generated JSON-LD is committed and remains what the corpus publishes; the gate regenerates it and requires every document to equal its committed copy by RDF hash (`dev/rdf_hash.py`).

## Evidence

All 9 Seattle City Light documents (RTC and RTS 2026 to 2028, and the residential-suburban modifier 2026 to 2028) generate from one source tree with the same RDF hash as the committed files. The SCL source is 309 lines in 4 namespaces; RTS is 28, most of it a rates table copied from the ordinance's year columns. The committed RTC 2026 JSON-LD alone is 689 lines.

clj-urpx 0.39.0 loads all 88 corpus documents and emits 81 of them RDF-identically. The other 7 lose `ProgramEnrollment`, `SourcePublication` and `RateCase` nodes, or a `-0.00000` that becomes `0.00000`.

## Requirements

1. Generated equals committed. The gate fails on any document whose regenerated RDF hash differs from the committed file.
2. Typed definitions. Every definition is made with one macro, `defurpx`, naming its kind with a keyword. The value is validated against that kind's Malli schema when the namespace loads; a failure names the file, the line of the form, and the path to the bad value inside it.
3. Generation by registry. `defurpx` registers each definition; the generator writes every definition of kind `:document`. There is no manifest of documents.
4. Shared data is keyed by the date it takes effect and read as of each version's date. It is never edited in place, so an older version regenerates unchanged after a newer one is added.
5. References across documents are full IRIs, forward or back. A modifier names its base plan's Prices and tiers through the same function the base uses to mint them.
6. A sentence that restates table facts (rates, hours, multipliers) is generated from the tables. Other prose is a template filled from the definitions.
7. Unknown keys refuse. A misspelled key is an error, not a silently kept property.
8. Pretty-printed source, one form per line unless a form is short; `clj-kondo` clean.

## defurpx

```clojure
(defurpx :rates rts-rates
  "SMC 21.49.030.B as amended by Ordinance 127473, page 11; cents per meter
   per day (base) and per kWh, one entry per column 'Effective January 1, <year>'."
  {"2026-01-01" {:base-service-charge 39.45M :peak 16.32M :mid-peak 14.28M :off-peak 8.16M}
   "2027-01-01" {:base-service-charge 55.18M :peak 17.02M :mid-peak 14.89M :off-peak 8.51M}
   "2028-01-01" {:base-service-charge 77.22M :peak 17.86M :mid-peak 15.63M :off-peak 8.93M}})
```

`(defurpx kind name doc? value)` expands to a `def` whose var carries `{:urpx/kind kind}`, the docstring, file and line; validates the value against `(kind-schema kind)`, a multimethod whose `:default` refuses an unknown kind; and registers the var. A malformed row fails at load:

```
Invalid :rates bad-rates/rtc-rates (bad/bad_rates.clj:4)
  at ["2027-01-01" :peak]: 16.9 should be a BigDecimal with 2 decimal places, e.g. 16.10M
  at ["2028-1-1"]: "2028-1-1" should be a yyyy-mm-dd string
```

## Kinds

| Kind | Holds |
|---|---|
| `:utility` | identity: prefix, legal name, EIA id |
| `:source` | a source document: file, URL, retrieval date, pages |
| `:holidays` | holiday names and rules, observance, dated observed days |
| `:tou-periods` | period keys, labels, names |
| `:tou-brackets` | rows of period, days, start, end, holiday treatment |
| `:rates` | rates per effective date |
| `:percentages` | multipliers per jurisdiction per effective date |
| `:undergrounding` | per-kWh charges per jurisdiction per effective date |
| `:jurisdictions` | jurisdiction keys and names |
| `:description` | prose templates and dated notes |
| `:document` | one plan or modifier: identity, versions table, references to the kinds above |

These are the kinds SCL needed. Seasons, tiers and demand charges add kinds when the first utility that has them is ported.

## Layout

Source lives under `src/rate_plans/`, following the namespace-to-path rule and mirroring the corpus: `rate_plans/us/wa/scl/common.clj` holds what every SCL filing shares, and `rate_plans/us/wa/scl/rts.clj` one schedule. Generic namespaces (`rate_plans/tou.clj` and the like) know nothing about a utility. `corpus.json` gains a source kind so the walkers find them.

## What goes to clj-urpx

Generic, for clj-urpx: `defurpx`, the kind multimethod and registry; the kinds that are not corpus-specific; fixes for the gaps below; the expansion helpers once a second utility has used them; a clj-kondo hook shipped with the library.

Corpus-specific, here: the utility and schedule namespaces, the date-keyed shared data, the generator entry point, and the gate's equality check.

## Gaps in urpx.dsl 0.39.0

Each has a working workaround in the SCL spike.

| Gap | Workaround |
|---|---|
| `dsl-scope` local ids drop their prefix | build every `@id` as a full CURIE |
| references must be declared before use, so a version cannot name its enclosing plan | references are CURIE strings, forward or back |
| a qualified keyword value inside a scope is read as a local reference, so `:urpx/allDays` throws | vocabulary values as plain keywords converted to references |
| `condition-expression` rejects short keys (`:root-node`): `alias-map` reads the wrapped schema without dereferencing it | dereference before deriving aliases |
| unknown keys are kept silently | refuse any key that is neither a schema key nor its alias |
| `urpx:offeredBy` is in no version schema | passed through unvalidated |
| no builder for `ComparisonNode`, `UtilityOperator`, `OrganizationIdentity`, `OrganizationName` | raw maps |
| no way to write an RDF list (`hasPossibleValues`) | literal `@list` maps |
| `"24:00"` throws `DateTimeException`, though xsd:time allows 24:00:00 | mapped to `"00:00:00"` |
| a double such as `0.1610` emits `"0.161"` | BigDecimals with explicit scale |
| `ProgramEnrollment`, `SourcePublication`, `RateCase` are dropped on load | none needed for SCL |

## Acceptance

The 9 SCL documents, regenerated from source on clj-urpx's release, with the same RDF hashes. Then PSE Schedules 307 and 327, which share 19 riders and two Summary-Sheet versions: the first test of the helpers on a second utility.

## Open questions

1. Whether `tariff.toml` deferrals, READMEs and coverage evaluations are generated from the same source, which would retire the lints that check they agree with the JSON-LD.
2. The order of porting the rest of the corpus, and whether the Python generators (`dev/author_*.py`, `scripts/build-*.py`) are retired as each family is ported.
3. Where the expansion helpers live once stable: clj-urpx, or a separate library.
