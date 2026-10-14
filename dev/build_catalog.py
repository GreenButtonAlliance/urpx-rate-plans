#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Build the DCAT catalog of the corpus under catalog/.

Writes catalog/corpus.jsonld (DCAT 3 JSON-LD) and catalog/corpus.csv (one row
per filing directory), from each filing's tariff.toml, its utility's
utility.toml (through dev/utilities.py), the files in the filing directory, and
the values its JSON-LD documents declare, read with SPARQL. catalog/README.md
describes the model.

Three levels, each a resource whose dcterms:subject is the URPX entity it
covers:
  utility    dcat:DatasetSeries   subject: the urpx:UtilityOperator
  schedule   dcat:DatasetSeries   subject: the urpx:RatePlan or urpx:RatePlanModifier
  filing     dcat:Dataset         subject: each document's own version node
A filing is dcat:inSeries (and dcterms:isPartOf) its schedule, a schedule its
utility. Each JSON-LD document and each vendored source PDF is a
dcat:Distribution of its filing. A document in a filing whose tariff.toml
records [generation] (doc/dsl-corpus-generation.md) is prov:wasDerivedFrom each
of the filing's source files and prov:wasGeneratedBy an activity naming its
generator and, for urpx.dsl, the clj-urpx release deps.edn pins.

Every filing must summarize. One that cannot (a manifest field missing, a
document that does not parse, a document with no version node of its own, a
vendored PDF whose sha256 no [source] entry declares, a [source] entry with no
file unless it says vendored = false, a [generation] source that does not
exist) fails the build, which
then writes nothing. The output is validated against catalog/corpus.schema.json
and parsed back with rdflib before it is written: the dataset and distribution
counts read from it by SPARQL must equal what dev/corpus.py walks, and every
dcat:downloadURL must resolve, from catalog/, to a file on disk.

Deterministic: datasets in path order, no wall-clock date in the output.

Run from the repository root:
  python3 dev/build_catalog.py           build and write
  python3 dev/build_catalog.py --check   rebuild and compare with the committed
                                         files; exit 2 naming each dataset that
                                         differs

Exit 1 when a filing cannot be summarized or the output fails its own checks.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus  # noqa: E402
import utilities  # noqa: E402

REPO = corpus.REPO
CATALOG_DIR = REPO / "catalog"
JSONLD_OUT = CATALOG_DIR / "corpus.jsonld"
CSV_OUT = CATALOG_DIR / "corpus.csv"
SCHEMA = CATALOG_DIR / "corpus.schema.json"

URPX = "https://urpx.org/ns/ontology/"
IANA = "https://www.iana.org/assignments/media-types/"
ADMS_STATUS = "http://purl.org/adms/status/"
TARGET_RELEASE = re.compile(r"/v(\d+\.\d+\.\d+)/")
DEPS = REPO / "deps.edn"
CLJ_URPX = "energy.grid-coordination/clj-urpx"
CLJ_URPX_PIN = re.compile(re.escape(CLJ_URPX) + r'\s*\{\s*:mvn/version\s+"([^"]+)"')
DOC_NAME = re.compile(
    r"^(?P<kind>rate-plan|rate-plan-modifier)_(?P<utility>[a-z0-9-]+)_"
    r"(?P<slug>[a-z0-9-]+)_(?P<date>\d{4}-\d{2}-\d{2})\.jsonld$")
VERSION_TYPE = {"rate-plan": URPX + "RatePlanVersion",
                "rate-plan-modifier": URPX + "RatePlanModifierVersion"}
PLAN_TYPE = {"rate-plan": URPX + "RatePlan",
             "rate-plan-modifier": URPX + "RatePlanModifier"}

CONTEXT = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dcterms": "http://purl.org/dc/terms/",
    "spdx": "http://spdx.org/rdf/terms#",
    "adms": "http://www.w3.org/ns/adms#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "prov": "http://www.w3.org/ns/prov#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "urpx": URPX,
    "title": "dcterms:title",
    "description": "dcterms:description",
    "identifier": "dcterms:identifier",
    "dataset": {"@id": "dcat:dataset", "@container": "@set"},
    "distribution": {"@id": "dcat:distribution", "@container": "@set"},
    "inSeries": {"@id": "dcat:inSeries", "@type": "@id"},
    "isPartOf": {"@id": "dcterms:isPartOf", "@type": "@id"},
    "prev": {"@id": "dcat:prev", "@type": "@id"},
    "subject": {"@id": "dcterms:subject", "@container": "@set"},
    "theme": {"@id": "dcat:theme", "@type": "@id", "@container": "@set"},
    "spatial": "dcterms:spatial",
    "temporal": "dcterms:temporal",
    "startDate": {"@id": "dcat:startDate", "@type": "xsd:dateTime"},
    "endDate": {"@id": "dcat:endDate", "@type": "xsd:dateTime"},
    "status": {"@id": "adms:status", "@type": "@id"},
    "conformsTo": "dcterms:conformsTo",
    "version": "dcat:version",
    "downloadURL": {"@id": "dcat:downloadURL", "@type": "@id"},
    "mediaType": {"@id": "dcat:mediaType", "@type": "@id"},
    "byteSize": {"@id": "dcat:byteSize", "@type": "xsd:nonNegativeInteger"},
    "checksum": "spdx:checksum",
    "algorithm": {"@id": "spdx:algorithm", "@type": "@id"},
    "checksumValue": {"@id": "spdx:checksumValue", "@type": "xsd:hexBinary"},
    "source": {"@id": "dcterms:source", "@type": "@id"},
    "created": {"@id": "dcterms:created", "@type": "xsd:date"},
    "name": "urpx:name",
    "legalName": "urpx:legalName",
    "ratePlanUniqueIdentifier": "urpx:ratePlanUniqueIdentifier",
    "modifierUniqueIdentifier": "urpx:modifierUniqueIdentifier",
    "hasIdentity": "urpx:hasIdentity",
    "hasIdentifier": "urpx:hasIdentifier",
    "scheme": {"@id": "urpx:scheme", "@type": "@id"},
    "notation": "skos:notation",
    "wasDerivedFrom": {"@id": "prov:wasDerivedFrom", "@type": "@id", "@container": "@set"},
    "wasGeneratedBy": "prov:wasGeneratedBy",
    "wasAssociatedWith": "prov:wasAssociatedWith",
}

CSV_COLUMNS = [
    "storage_path", "utility", "utility_legal_name", "eia_id", "jurisdiction",
    "schedule", "plan_kind", "rate_plan_iri", "rate_plan_identifier",
    "rate_plan_name", "version_iris", "effective_date_start",
    "effective_date_end", "commodity", "urpx_version", "documents",
    "source_urls", "source_sha256", "source_retrieved_on", "complete",
]

PREFIX = f"PREFIX urpx: <{URPX}>\nPREFIX skos: <http://www.w3.org/2004/02/skos/core#>\n"
Q_VERSIONS = PREFIX + """
SELECT ?v ?vtype ?plan ?ptype ?eff ?exp ?commodity ?org WHERE {
  VALUES (?vtype ?link ?ptype) {
    (urpx:RatePlanVersion urpx:forRatePlan urpx:RatePlan)
    (urpx:RatePlanModifierVersion urpx:forRatePlanModifier urpx:RatePlanModifier)
  }
  ?v a ?vtype ; ?link ?plan .
  ?plan a ?ptype .
  OPTIONAL { ?v urpx:effectiveDateTime ?eff }
  OPTIONAL { ?v urpx:expirationDateTime ?exp }
  OPTIONAL { ?v urpx:commodity ?commodity }
  OPTIONAL { ?v urpx:offeredBy ?org }
}"""
Q_PLAN = PREFIX + """
SELECT ?name ?identifier WHERE {
  OPTIONAL { ?plan urpx:name ?name }
  OPTIONAL { ?plan urpx:ratePlanUniqueIdentifier|urpx:modifierUniqueIdentifier ?identifier }
}"""
Q_TARGET = PREFIX + "SELECT DISTINCT ?target WHERE { ?package urpx:targetURPXVersion ?target }"
Q_ORG = PREFIX + """
SELECT ?identity ?identifier ?notation WHERE {
  ?org urpx:hasIdentity ?identity .
  ?identity urpx:hasIdentifier ?identifier .
  ?identifier urpx:scheme urpx:eiaScheme ; skos:notation ?notation .
}"""


class Unsummarizable(Exception):
    """A filing the catalog cannot describe. The message names the file."""


def rel(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def link(path: Path, directory: bool = False) -> str:
    """A reference to a repository path, relative to catalog/."""
    return "../" + rel(path) + ("/" if directory else "")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checksum(digest: str) -> dict:
    return {"@type": "spdx:Checksum", "algorithm": "spdx:checksumAlgorithm_sha256",
            "checksumValue": digest}


def sources_of(manifest: dict, where: str) -> list[dict]:
    """The [source] entries, single-source or multi-source, in manifest order."""
    src = manifest.get("source")
    if not isinstance(src, dict):
        raise Unsummarizable(f"{where}: no [source] table")
    entries = [src] if "url" in src else [v for v in src.values() if isinstance(v, dict)]
    if not entries:
        raise Unsummarizable(f"{where}: [source] declares no document")
    for e in entries:
        for field in ("url", "sha256", "retrieved_on"):
            if field not in e:
                raise Unsummarizable(f"{where}: a [source] entry lacks {field}")
    return entries


def clj_urpx_release() -> str:
    """The clj-urpx release deps.edn pins: the one that emits every urpx.dsl document."""
    m = CLJ_URPX_PIN.search(DEPS.read_text()) if DEPS.is_file() else None
    if not m:
        raise Unsummarizable(f"{rel(DEPS) if DEPS.is_file() else 'deps.edn'}: pins no {CLJ_URPX} release")
    return m.group(1)


def generation_of(manifest: dict, where: str) -> dict | None:
    """The filing's [generation] table, its sources checked to exist, or None."""
    g = manifest.get("generation")
    if g is None:
        return None
    for src in g.get("sources", []):
        if not (REPO / src).is_file():
            raise Unsummarizable(f"{where}: [generation] source {src} does not exist")
    return g


def read_document(path: Path) -> dict:
    """The document's own version and plan, its declared URPX version and the
    organization offering it, read by SPARQL."""
    from rdflib import Graph, URIRef

    where = rel(path)
    m = DOC_NAME.match(path.name)
    if not m:
        raise Unsummarizable(f"{where}: file name is not <kind>_<utility>_<slug>_<date>.jsonld")
    g = Graph()
    try:
        g.parse(path, format="json-ld")
    except Exception as e:  # rdflib raises several unrelated types on bad input
        raise Unsummarizable(f"{where}: does not parse as JSON-LD: {type(e).__name__}: {e}")

    own_local = f"{m['slug']}-{m['date']}"
    rows: dict[str, dict] = {}
    for r in g.query(Q_VERSIONS):
        v = str(r.v)
        if v.rsplit("/", 1)[-1] != own_local or str(r.vtype) != VERSION_TYPE[m["kind"]]:
            continue
        row = rows.setdefault(v, {"plan": set(), "ptype": set(), "eff": set(), "exp": set(),
                                  "commodity": set(), "org": set()})
        for key in row:
            value = getattr(r, key)
            if value is not None:
                row[key].add(str(value))
    if len(rows) != 1:
        raise Unsummarizable(
            f"{where}: {len(rows)} {VERSION_TYPE[m['kind']].rsplit('/', 1)[-1]} nodes named "
            f"…/{own_local} with a plan; exactly one is required")
    vid, row = next(iter(rows.items()))
    for key, label in (("plan", "urpx:forRatePlan / urpx:forRatePlanModifier"),
                       ("eff", "urpx:effectiveDateTime"), ("commodity", "urpx:commodity"),
                       ("org", "urpx:offeredBy")):
        if len(row[key]) != 1:
            raise Unsummarizable(f"{where}: {vid} carries {len(row[key])} values of {label}; one is required")
    if len(row["exp"]) > 1:
        raise Unsummarizable(f"{where}: {vid} carries {len(row['exp'])} urpx:expirationDateTime values")
    plan = row["plan"].pop()

    names = {(str(r.name) if r.name else None, str(r.identifier) if r.identifier else None)
             for r in g.query(Q_PLAN, initBindings={"plan": URIRef(plan)})}
    if len(names) != 1 or None in next(iter(names)):
        raise Unsummarizable(f"{where}: {plan} needs exactly one urpx:name and one unique identifier")
    name, identifier = names.pop()

    targets = sorted(str(r.target) for r in g.query(Q_TARGET))
    if len(targets) != 1:
        raise Unsummarizable(f"{where}: declares {len(targets)} urpx:targetURPXVersion values; one is required")
    release = TARGET_RELEASE.search(targets[0])
    if not release:
        raise Unsummarizable(f"{where}: urpx:targetURPXVersion {targets[0]} names no release /vX.Y.Z/")

    org = row["org"].pop()
    eia = sorted({(str(r.identity), str(r.identifier), str(r.notation))
                  for r in g.query(Q_ORG, initBindings={"org": URIRef(org)})})
    return {
        "path": path, "kind": m["kind"], "slug": m["slug"], "date": m["date"],
        "version": vid, "plan": plan, "plan_type": PLAN_TYPE[m["kind"]],
        "name": name, "identifier": identifier,
        "effective": row["eff"].pop(), "expires": row["exp"].pop() if row["exp"] else None,
        "commodity": row["commodity"].pop(), "org": org, "eia": eia,
        "target": targets[0], "release": release.group(1),
    }


def summarize_filing(d: Path, documents: list[Path], pdfs: list[Path]) -> dict:
    """One filing directory: its manifest, its documents and its vendored PDFs."""
    where = rel(d / corpus.TARIFF_MANIFEST)
    utility, schedule, date = corpus.parse_filing_path(d / corpus.TARIFF_MANIFEST)
    try:
        manifest = corpus.load_toml(d / corpus.TARIFF_MANIFEST)
    except Exception as e:
        raise Unsummarizable(f"{where}: does not parse as TOML: {e}")
    for field, want in (("utility", utility), ("schedule", schedule), ("effective_date", date)):
        if field not in manifest:
            raise Unsummarizable(f"{where}: lacks {field}")
        if str(manifest[field]) != want:
            raise Unsummarizable(f"{where}: {field} = {manifest[field]!r}, but the path says {want!r}")
    complete = manifest.get("modeling", {}).get("complete")
    if not isinstance(complete, bool):
        raise Unsummarizable(f"{where}: lacks [modeling].complete")
    sources = sources_of(manifest, where)
    generation = generation_of(manifest, where)

    if not documents:
        raise Unsummarizable(f"{rel(d)}: holds no JSON-LD document")
    docs = [read_document(p) for p in documents]
    primary = [doc for doc in docs if doc["slug"] == schedule]
    if len(primary) != 1:
        raise Unsummarizable(
            f"{rel(d)}: {len(primary)} documents named for schedule {schedule!r}; exactly one is required")
    primary = primary[0]
    docs.sort(key=lambda doc: (doc is not primary, doc["path"].name))

    by_sha = {s["sha256"]: s for s in sources}
    vendored = []
    for p in pdfs:
        digest = sha256(p)
        if digest not in by_sha:
            raise Unsummarizable(f"{rel(p)}: sha256 {digest} is not declared by any [source] entry in {where}")
        vendored.append((p, digest, by_sha[digest]))
    found = {digest for _p, digest, _s in vendored}
    for s in sources:
        cited = s.get("vendored", True) is False
        if cited and s["sha256"] in found:
            raise Unsummarizable(f"{where}: {s['url']} is declared vendored = false, but a file in the filing has its sha256")
        if not cited and s["sha256"] not in found:
            raise Unsummarizable(f"{where}: no vendored file has the sha256 of {s['url']}")

    return {"dir": d, "utility": utility, "schedule": schedule, "date": date,
            "manifest": manifest, "complete": complete, "sources": sources,
            "docs": docs, "primary": primary, "pdfs": vendored, "generation": generation}


def generated_by(generation: dict) -> dict:
    """The activity that wrote a generated document: its generator and, for
    urpx.dsl, the clj-urpx release as a software agent."""
    activity = {"@type": "prov:Activity", "title": generation["generator"]}
    if generation["generator"] == "urpx.dsl":
        release = clj_urpx_release()
        activity["wasAssociatedWith"] = {
            "@id": f"https://clojars.org/{CLJ_URPX}/versions/{release}",
            "@type": "prov:SoftwareAgent",
            "title": CLJ_URPX,
            "version": release,
        }
    return activity


def distribution_of_document(doc: dict, generation: dict | None) -> dict:
    p = doc["path"]
    dist = {
        "@type": "dcat:Distribution",
        "title": p.name,
        "downloadURL": link(p),
        "mediaType": IANA + corpus.LAYOUT["kinds"][doc["kind"]]["media_type"],
        "byteSize": p.stat().st_size,
        "checksum": checksum(sha256(p)),
        "conformsTo": {"@id": doc["target"], "@type": "dcterms:Standard", "version": doc["release"]},
    }
    if generation is not None:
        dist["wasDerivedFrom"] = [link(REPO / src) for src in generation["sources"]]
        dist["wasGeneratedBy"] = generated_by(generation)
    return dist


def distribution_of_pdf(p: Path, digest: str, source: dict) -> dict:
    return {
        "@type": "dcat:Distribution",
        "title": p.name,
        "downloadURL": link(p),
        "mediaType": IANA + source.get("media_type", "application/pdf"),
        "byteSize": p.stat().st_size,
        "checksum": checksum(digest),
        "source": source["url"],
        "created": str(source["retrieved_on"]),
    }


def build() -> tuple[dict, str]:
    """(catalog JSON-LD, CSV text). Raises SystemExit naming every filing that
    cannot be summarized."""
    dirs = corpus.filing_dirs()
    corpus.require_nonempty(dirs, "filing directories")
    documents: dict[Path, list[Path]] = {d: [] for d in dirs}
    for p in corpus.all_filing_jsonld():
        documents.setdefault(p.parent, []).append(p)
    pdfs: dict[Path, list[Path]] = {d: [] for d in dirs}
    for p in corpus.paths("source-document"):
        pdfs.setdefault(p.parent, []).append(p)
    errors = [f"{rel(d)}: a document or source file with no tariff.toml beside it"
              for d in sorted(set(documents) | set(pdfs)) if d not in set(dirs)]

    filings = []
    for d in dirs:
        try:
            filings.append(summarize_filing(d, documents[d], pdfs[d]))
        except Unsummarizable as e:
            errors.append(str(e))
    if any(f["generation"] and f["generation"]["generator"] == "urpx.dsl" for f in filings):
        try:
            clj_urpx_release()
        except Unsummarizable as e:
            errors.append(str(e))
    idents = utilities.BY_SLUG
    for f in filings:
        if f["utility"] not in idents:
            errors.append(f"{rel(f['dir'])}: no utility.toml for {f['utility']!r}")
    if errors:
        raise SystemExit("ERROR: the catalog cannot summarize every filing; nothing written.\n  "
                         + "\n  ".join(errors))

    datasets: list[tuple[tuple, dict]] = []
    rows: list[dict] = []
    by_utility: dict[Path, list[dict]] = {}
    for f in filings:
        by_utility.setdefault(corpus.utility_dir(f["dir"]), []).append(f)

    for udir, ufilings in by_utility.items():
        ident = idents[ufilings[0]["utility"]]
        orgs = {doc["org"] for f in ufilings for doc in f["docs"]}
        if len(orgs) != 1:
            raise SystemExit(f"ERROR: {rel(udir)}: filings name {len(orgs)} urpx:offeredBy organizations: {sorted(orgs)}")
        org = {"@id": orgs.pop(), "@type": "urpx:UtilityOperator", "legalName": ident.legal_name}
        chains = {c for f in ufilings for doc in f["docs"] for c in doc["eia"] if c[2] == ident.eia_id}
        if ident.eia_id and len(chains) == 1:
            identity, identifier, notation = chains.pop()
            org["hasIdentity"] = {"@id": identity, "hasIdentifier": {
                "@id": identifier, "scheme": "urpx:eiaScheme", "notation": notation}}
        elif ident.eia_id:
            raise SystemExit(f"ERROR: {rel(udir)}: utility.toml gives eia_id {ident.eia_id}, and the filings "
                             f"carry {len(chains)} urpx:eiaScheme identifiers with that notation")
        country = udir.parent.parent.name.upper()
        jurisdiction = f"{country}-{udir.parent.name.upper()}"
        title = ident.legal_name or ident.short_name or udir.name
        datasets.append((Path(rel(udir)).parts, {
            "@id": link(udir, True), "@type": "dcat:DatasetSeries",
            "identifier": rel(udir), "title": title,
            "spatial": {"@type": "dcterms:Location", "identifier": jurisdiction},
            "subject": [org],
        }))

        by_schedule: dict[Path, list[dict]] = {}
        for f in ufilings:
            by_schedule.setdefault(f["dir"].parent.parent, []).append(f)
        for sdir, sfilings in by_schedule.items():
            sfilings.sort(key=lambda f: f["date"])
            plans = {f["primary"]["plan"] for f in sfilings}
            if len(plans) != 1:
                raise SystemExit(f"ERROR: {rel(sdir)}: its filings are for {len(plans)} plans: {sorted(plans)}")
            latest = sfilings[-1]["primary"]
            identifier_key = ("ratePlanUniqueIdentifier" if latest["kind"] == "rate-plan"
                              else "modifierUniqueIdentifier")
            short = ident.short_name or udir.name
            datasets.append((Path(rel(sdir)).parts, {
                "@id": link(sdir, True), "@type": "dcat:DatasetSeries",
                "identifier": rel(sdir), "title": f"{short} {latest['identifier']}",
                "inSeries": link(udir, True), "isPartOf": link(udir, True),
                "subject": [{"@id": latest["plan"], "@type": "urpx:" + latest["plan_type"].rsplit("/", 1)[-1],
                             "name": latest["name"], identifier_key: latest["identifier"]}],
            }))

            prev = None
            for f in sfilings:
                p = f["primary"]
                temporal = {"@type": "dcterms:PeriodOfTime", "startDate": p["effective"]}
                if p["expires"]:
                    temporal["endDate"] = p["expires"]
                ds = {
                    "@id": link(f["dir"], True), "@type": "dcat:Dataset",
                    "identifier": rel(f["dir"]),
                    "title": f"{short} {p['identifier']}, effective {p['effective'][:10]}",
                    "inSeries": link(sdir, True), "isPartOf": link(sdir, True),
                }
                if prev:
                    ds["prev"] = prev
                ds.update({
                    "subject": [{"@id": doc["version"],
                                 "@type": "urpx:" + VERSION_TYPE[doc["kind"]].rsplit("/", 1)[-1]}
                                for doc in f["docs"]],
                    "theme": [p["commodity"]],
                    "temporal": temporal,
                    "status": ADMS_STATUS + ("Completed" if f["complete"] else "UnderDevelopment"),
                    "distribution": [distribution_of_document(doc, f["generation"]) for doc in f["docs"]]
                                    + [distribution_of_pdf(*v) for v in sorted(f["pdfs"], key=lambda v: v[0].name)],
                })
                prev = ds["@id"]
                datasets.append((Path(rel(f["dir"])).parts, ds))
                rows.append({
                    "storage_path": rel(f["dir"]),
                    "utility": f["utility"],
                    "utility_legal_name": ident.legal_name,
                    "eia_id": ident.eia_id,
                    "jurisdiction": jurisdiction,
                    "schedule": f["schedule"],
                    "plan_kind": p["kind"],
                    "rate_plan_iri": p["plan"],
                    "rate_plan_identifier": p["identifier"],
                    "rate_plan_name": p["name"],
                    "version_iris": " ".join(doc["version"] for doc in f["docs"]),
                    "effective_date_start": p["effective"],
                    "effective_date_end": p["expires"] or "",
                    "commodity": p["commodity"].removeprefix(URPX),
                    "urpx_version": " ".join(sorted({doc["release"] for doc in f["docs"]})),
                    "documents": " ".join(doc["path"].name for doc in f["docs"]),
                    "source_urls": " ".join(s["url"] for s in f["sources"]),
                    "source_sha256": " ".join(s["sha256"] for s in f["sources"]),
                    "source_retrieved_on": " ".join(str(s["retrieved_on"]) for s in f["sources"]),
                    "complete": "true" if f["complete"] else "false",
                })

    datasets.sort(key=lambda t: t[0])
    rows.sort(key=lambda r: Path(r["storage_path"]).parts)
    catalog = {
        "@context": CONTEXT,
        "@id": JSONLD_OUT.name,
        "@type": "dcat:Catalog",
        "title": "urpx-rate-plans corpus",
        "description": (
            "Generated by dev/build_catalog.py from each filing's tariff.toml, its utility's "
            "utility.toml, and the values its JSON-LD documents declare. One dcat:Dataset per "
            "filing directory, in a dcat:DatasetSeries per schedule, in one per utility; one "
            "dcat:Distribution per JSON-LD document and per vendored source document; a "
            "generated document's distribution is prov:wasDerivedFrom its source files and "
            "prov:wasGeneratedBy the generator and clj-urpx release that wrote it. Do not "
            "hand-edit."),
        "dataset": [ds for _k, ds in datasets],
    }
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=CSV_COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return catalog, out.getvalue()


def render(catalog: dict) -> str:
    return json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"


def schema_problems(catalog: dict) -> list[str]:
    import jsonschema
    validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text()))
    return [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}"
            for e in sorted(validator.iter_errors(catalog), key=lambda e: list(map(str, e.absolute_path)))]


def graph_problems(text: str) -> list[str]:
    """Parse the catalog as RDF, from where it is written, and require its
    counts and links to agree with the walk."""
    from rdflib import Graph
    g = Graph()
    g.parse(data=text, format="json-ld", publicID=JSONLD_OUT.as_uri())
    q = """PREFIX dcat: <http://www.w3.org/ns/dcat#>
    SELECT (COUNT(DISTINCT ?ds) AS ?n) WHERE { ?cat a dcat:Catalog ; dcat:dataset ?ds . ?ds a dcat:Dataset }"""
    problems = []
    n = int(next(iter(g.query(q))).n)
    if n != len(corpus.filing_dirs()):
        problems.append(f"{n} dcat:Dataset (excluding series) in the graph, {len(corpus.filing_dirs())} filing directories walked")
    urls = [str(r.u) for r in g.query(
        "PREFIX dcat: <http://www.w3.org/ns/dcat#> SELECT ?u WHERE { ?d a dcat:Distribution ; dcat:downloadURL ?u }")]
    want = len(corpus.all_filing_jsonld()) + len(corpus.paths("source-document"))
    if len(urls) != want:
        problems.append(f"{len(urls)} distributions in the graph, {want} documents and source files walked")
    from urllib.parse import unquote, urlparse
    for u in urls:
        parsed = urlparse(u)
        if parsed.scheme != "file" or not Path(unquote(parsed.path)).is_file():
            problems.append(f"downloadURL {u} does not resolve to a file")
    for r in g.query("PREFIX prov: <http://www.w3.org/ns/prov#> SELECT DISTINCT ?s WHERE { ?d prov:wasDerivedFrom ?s }"):
        parsed = urlparse(str(r.s))
        if parsed.scheme != "file" or not Path(unquote(parsed.path)).is_file():
            problems.append(f"prov:wasDerivedFrom {r.s} does not resolve to a file")
    return problems


def generate() -> tuple[str, str]:
    catalog, table = build()
    problems = schema_problems(catalog)
    if problems:
        raise SystemExit("ERROR: the catalog does not validate against "
                         f"{rel(SCHEMA)}; nothing written.\n  " + "\n  ".join(problems))
    text = render(catalog)
    problems = graph_problems(text)
    if problems:
        raise SystemExit("ERROR: the catalog read back as RDF disagrees with the walk; nothing written.\n  "
                         + "\n  ".join(problems))
    return text, table


def describe_drift(committed: str, rebuilt: str) -> list[str]:
    try:
        old = {d["@id"]: d for d in json.loads(committed)["dataset"]}
    except (ValueError, KeyError, TypeError):
        return [f"{rel(JSONLD_OUT)} is not a catalog this generator wrote"]
    new = {d["@id"]: d for d in json.loads(rebuilt)["dataset"]}
    out = [f"in the committed catalog, not in the corpus: {i}" for i in sorted(old.keys() - new.keys())]
    out += [f"in the corpus, not in the committed catalog: {i}" for i in sorted(new.keys() - old.keys())]
    out += [f"differs from the corpus: {i}" for i in sorted(old.keys() & new.keys()) if old[i] != new[i]]
    return out or [f"{rel(JSONLD_OUT)} differs outside the datasets"]


def main(argv: list[str]) -> int:
    if argv not in ([], ["--check"]):
        print("usage: python3 dev/build_catalog.py [--check]", file=sys.stderr)
        return 2
    text, table = generate()
    n = text.count('"@type": "dcat:Dataset"')
    if argv == ["--check"]:
        drift = []
        committed = JSONLD_OUT.read_text() if JSONLD_OUT.exists() else ""
        if committed != text:
            drift += describe_drift(committed, text) if committed else [f"{rel(JSONLD_OUT)} is missing"]
        if not CSV_OUT.exists() or CSV_OUT.read_text() != table:
            drift.append(f"{rel(CSV_OUT)} differs from a rebuild")
        if drift:
            print("FAIL: the committed catalog differs from a rebuild (run python3 dev/build_catalog.py):")
            for line in drift:
                print(f"  {line}")
            return 2
        print(f"OK: catalog matches a rebuild ({n} filings)")
        return 0
    CATALOG_DIR.mkdir(exist_ok=True)
    JSONLD_OUT.write_text(text)
    CSV_OUT.write_text(table)
    print(f"Wrote {rel(JSONLD_OUT)} and {rel(CSV_OUT)} ({n} filings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
