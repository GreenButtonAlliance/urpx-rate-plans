# Corpus catalog

A generated inventory of every filing in this corpus, in two projections:

- [`corpus.jsonld`](corpus.jsonld): a [DCAT 3](https://www.w3.org/TR/vocab-dcat-3/) catalog in JSON-LD, with its `@context` inline.
- [`corpus.csv`](corpus.csv): one row per filing directory.

[`corpus.schema.json`](corpus.schema.json) is the JSON Schema of `corpus.jsonld`.

## How it is generated

```
python3 dev/build_catalog.py           # build and write both files
python3 dev/build_catalog.py --check   # exit 2 when the committed files differ from a rebuild
```

The generator walks the corpus with `dev/corpus.py` and reads each filing's `tariff.toml`, its utility's `utility.toml`, the files in the filing directory, and the values its JSON-LD documents declare, by SPARQL. It writes nothing, and exits 1, when any filing cannot be summarized: a manifest field it needs is missing, a document does not parse or has no version node of its own, a vendored file's sha256 is not declared in `[source]`, or a `[generation]` source does not exist. Before writing, it validates the JSON-LD against the schema, parses it back with rdflib from this directory, and requires the counts and links it reads there to agree with the walk. Output is deterministic: path order, and no date that is not in the corpus.

`dev/check_all.py` runs the generator, and its drift check fails when the result differs from the committed files. The pre-commit hook stages a regenerated catalog with the commit that changed the corpus, and `dev/gate.sh --fast` runs `--check`. Do not hand-edit `corpus.jsonld` or `corpus.csv`.

## Model

Every reference to a repository path is relative to this directory, so `../us/ca/pge/` resolves to the PG&E directory when the file is read where it sits. URPX entities keep the IRIs the documents give them.

| Level | Class | `@id` | `dcterms:subject` | Other properties |
|---|---|---|---|---|
| Utility | `dcat:DatasetSeries` | `../us/<state>/<utility>/` | the `urpx:UtilityOperator`, with `urpx:legalName` and its EIA identifier as the documents model it (`skos:notation` under `urpx:eiaScheme`) | `dcterms:spatial`: a `dcterms:Location` whose `dcterms:identifier` is the ISO 3166-2 code from the path, such as `US-CA` |
| Schedule | `dcat:DatasetSeries` | `../us/.../<schedule>/` | the `urpx:RatePlan` or `urpx:RatePlanModifier`, with `urpx:name` and its unique identifier | `dcat:inSeries` and `dcterms:isPartOf` the utility |
| Filing | `dcat:Dataset` | `../us/.../versions/<date>/` | each document's own `urpx:RatePlanVersion` or `urpx:RatePlanModifierVersion` | `dcat:inSeries` and `dcterms:isPartOf` the schedule; `dcat:prev` the filing before it; `dcat:theme` the version's `urpx:commodity`; `dcterms:temporal` with `dcat:startDate` and `dcat:endDate` from the version's `urpx:effectiveDateTime` and `urpx:expirationDateTime`; `adms:status` |
| File | `dcat:Distribution` | none | | `dcat:downloadURL`, `dcat:mediaType` (an IANA media type IRI), `dcat:byteSize`, `spdx:checksum` (SHA-256); for a generated document, `prov:wasDerivedFrom` and `prov:wasGeneratedBy` |

Each filing has one distribution per JSON-LD document and one per vendored source document. A document's distribution carries `dcterms:conformsTo` the ontology its `urpx:targetURPXVersion` names, with that release as `dcat:version`. A source document's distribution carries `dcterms:source`, the URL it was retrieved from, and `dcterms:created`, the date it was retrieved, both from `tariff.toml`.

A document whose filing records `[generation]` in `tariff.toml` ([doc/dsl-corpus-generation.md](../doc/dsl-corpus-generation.md)) is generated, and its distribution carries `prov:wasDerivedFrom` each of the filing's `sources`, as paths relative to this directory, and `prov:wasGeneratedBy` a `prov:Activity` whose `dcterms:title` is the filing's `generator`. For `urpx.dsl`, the activity is `prov:wasAssociatedWith` a `prov:SoftwareAgent` for the clj-urpx release `deps.edn` pins: its Clojars page as `@id`, `energy.grid-coordination/clj-urpx` as `dcterms:title` and the release as `dcat:version`. The generator refuses when a source path does not exist or `deps.edn` pins no clj-urpx release.

A filing's dates are those of its own version: the version in the document named for the filing's schedule, when the directory holds more than one document. `adms:status` is `http://purl.org/adms/status/Completed` when `[modeling].complete` is true and `http://purl.org/adms/status/UnderDevelopment` when it is false.

Schedules are dataset series because their filings are separate datasets, each priced for its own period, the case DCAT 3 gives series for; DCAT's version properties describe revisions of one dataset. Utilities are series of schedule series, which DCAT 3 allows.

## Querying

Every filing in force at an instant, per utility. The documents' date-times carry no offset and are local to the utility.

```sparql
PREFIX dcat: <http://www.w3.org/ns/dcat#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?utility (COUNT(?filing) AS ?current) WHERE {
  BIND ("2026-10-06T17:00:00"^^xsd:dateTime AS ?at)
  ?filing a dcat:Dataset ; dcat:inSeries ?schedule ; dcterms:temporal ?t .
  ?schedule dcat:inSeries/dcterms:identifier ?utility .
  ?t dcat:startDate ?start .
  FILTER (?start <= ?at)
  FILTER NOT EXISTS { ?t dcat:endDate ?end . FILTER (?end <= ?at) }
  FILTER NOT EXISTS {
    ?later dcat:inSeries ?schedule ; dcterms:temporal/dcat:startDate ?s2 .
    FILTER (?s2 > ?start && ?s2 <= ?at)
  }
} GROUP BY ?utility ORDER BY ?utility
```

## CSV columns

| Column | Source |
|---|---|
| `storage_path` | the filing directory |
| `utility`, `schedule` | the path |
| `utility_legal_name`, `eia_id` | `utility.toml` |
| `jurisdiction` | the path's country and subdivision, as ISO 3166-2 |
| `plan_kind` | `rate-plan` or `rate-plan-modifier`, from the document named for the schedule |
| `rate_plan_iri`, `rate_plan_identifier`, `rate_plan_name` | that document's plan: `@id`, `urpx:ratePlanUniqueIdentifier` or `urpx:modifierUniqueIdentifier`, `urpx:name` |
| `version_iris` | each document's own version, that document's first, space-separated |
| `effective_date_start`, `effective_date_end` | that version's `urpx:effectiveDateTime` and `urpx:expirationDateTime`, as written |
| `commodity` | that version's `urpx:commodity` |
| `urpx_version` | the release named by the documents' `urpx:targetURPXVersion` |
| `documents` | the JSON-LD file names |
| `source_urls`, `source_sha256`, `source_retrieved_on` | `tariff.toml` `[source]`, one per source document, space-separated, in manifest order |
| `complete` | `tariff.toml` `[modeling].complete` |
