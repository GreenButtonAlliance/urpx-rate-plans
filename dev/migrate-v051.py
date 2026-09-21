#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Migrate corpus filings from URPX v0.2.x to v0.5.1, one utility at a time.

This script ships in the real repository rather than the shadow one, because a
published dataset should carry the script that produced it. The July 2026
conversion is unreproducible precisely because no script survived it.

TWELVE ORDERED TRANSFORMS. T5 runs before T3/T4 because splitting a publication
changes what the wrapper contains.

THE SELF-CHECK IS A SET DIFFERENCE, NOT A COUNT. A triple-count delta is
invariant under a predicate swap and under a subject misattribution, and both
are live failure modes here. Every predicate added or removed must appear in the
transforms' declared signature; anything unaccounted for aborts the file.

Usage:
    python3 dev/migrate-v051.py --utility ladwp [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import rdflib

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

OLD_URPX = "https://urpx-org.github.io/urpx/ontology/"
NEW_URPX = "https://urpx.org/ns/ontology/"
OLD_TARGET = "https://github.com/urpx-org/urpx/raw/v0.2.0/ontology/urpx-ontology.ttl"
NEW_TARGET = "https://github.com/urpx-org/urpx/raw/v0.5.1/ontology/urpx-ontology.ttl"
SKOS = "http://www.w3.org/2004/02/skos/core#"

VERSION_TYPES = {"urpx:RatePlanVersion": "urpx:forRatePlan",
                 "urpx:RatePlanModifierVersion": "urpx:forRatePlanModifier"}
PARENT_OF = {"urpx:RatePlanVersion": "urpx:RatePlan",
             "urpx:RatePlanModifierVersion": "urpx:RatePlanModifier"}


def walk(node, fn):
    """Apply fn to every dict in the tree, NEVER descending into @context.

    The corpus @context uses prefixed keys as coercion terms (urpx:unitPrice ->
    {"@type": "xsd:decimal"}). A generic recursive walk rewrites those term
    definitions, silently turning a PREDICATE into a version URL. This rule is
    not an optimisation; without it T3 corrupts every file.
    """
    if isinstance(node, dict):
        fn(node)
        for k, v in node.items():
            if k == "@context":
                continue
            walk(v, fn)
    elif isinstance(node, list):
        for v in node:
            walk(v, fn)


def find_all(node, pred, out=None):
    out = [] if out is None else out
    def visit(d):
        if pred(d):
            out.append(d)
    walk(node, visit)
    return out


# --- transforms ---------------------------------------------------------------

def t1_context(doc, log):
    ctx = doc.get("@context")
    if not isinstance(ctx, dict):
        raise Migrate("@context is not an inline object; array form is tracked separately")
    if ctx.get("urpx") == OLD_URPX:
        ctx["urpx"] = NEW_URPX
        log("T1 urpx namespace rebound")
    ctx.setdefault("urpx:targetURPXVersion", {"@type": "xsd:anyURI"})


def t2_literal_iris(doc, log):
    """String VALUES holding the old base, e.g. urpx:dimensionProperty."""
    n = 0
    def visit(d):
        nonlocal n
        for k, v in list(d.items()):
            if k == "@context":
                continue
            if isinstance(v, str) and v.startswith(OLD_URPX):
                d[k] = v.replace(OLD_URPX, NEW_URPX, 1); n += 1
    walk(doc, visit)
    if n:
        log(f"T2 {n} literal IRI value(s) rebased")


# urpx:regulatoryFiling belonged to the retired 10-member PublicationTypeValue
# and is not a member of v0.5.1's 8-member SourcePublicationTypeValue. Upstream
# answered the successor question in its own v0.5.1 test case, which models the
# SAME node (pge:al-7846-e, PG&E Advice Letter 7846-E) as a SourcePublication
# with publicationType urpx:tariffSupplement. We follow their modelling of our
# own node rather than inventing a parallel one.
PUBLICATION_TYPE_SUCCESSOR = {"urpx:regulatoryFiling": "urpx:tariffSupplement"}

# SourcePublicationShape is CLOSED and does not admit hasRatePlan or
# hasRatePlanModifier. Those pointers are redundant anyway: the URPXPackage that
# encloses the publication already holds the same plans.
PUBLICATION_DROPPED = ("urpx:hasRatePlan", "urpx:hasRatePlanModifier")


def t5_split_publication(doc, log):
    n = 0
    def visit(d):
        nonlocal n
        if d.get("@type") != "urpx:TariffPublication":
            return
        d["@type"] = "urpx:SourcePublication"
        pt = d.get("urpx:publicationType")
        if isinstance(pt, dict) and "@id" in pt:
            old = pt["@id"]
            if old in PUBLICATION_TYPE_SUCCESSOR:
                pt["@id"] = PUBLICATION_TYPE_SUCCESSOR[old]
            elif not old.startswith("urpx:"):
                raise Migrate(f"unrecognised publicationType {old!r}")
            else:
                raise Migrate(f"publicationType {old!r} has no recorded v0.5.1 "
                              f"successor; add one to PUBLICATION_TYPE_SUCCESSOR "
                              f"rather than letting it through")
        for k in PUBLICATION_DROPPED:
            d.pop(k, None)
        n += 1
    walk(doc, visit)
    if n:
        log(f"T5 {n} TariffPublication -> SourcePublication (tariffSupplement)")


def t3_package(doc, log):
    changed = 0
    def visit(d):
        nonlocal changed
        if d.get("@type") == "urpx:URPXDocument":
            d["@type"] = "urpx:URPXPackage"
            if d.get("urpx:targetURPXVersion") == OLD_TARGET:
                d["urpx:targetURPXVersion"] = NEW_TARGET
            changed += 1
    walk(doc, visit)
    if changed:
        log(f"T3 {changed} URPXDocument -> URPXPackage")


def t4_synthesize_package(doc, path, log):
    """Insert a URPXPackage INTO a bare @graph, matching upstream's own pattern.

    Upstream's v0.5.1 pge-e-tou-c test case is a bare @graph holding a
    URPXPackage as ONE entry alongside other top-level entities, not a wrapper
    that swallows the document. That matters here: URPXPackageShape is closed and
    admits neither ProgramEnrollment nor RateCase, both of which PG&E filings
    carry as @graph siblings. Collapsing everything into a wrapper would make
    those nodes unplaceable; leaving them as siblings is both valid and what
    upstream does.

    The package takes the plans and modifiers inline and they leave the top level,
    because a URPXPackage exists precisely to declare targetURPXVersion over them.
    """
    if doc.get("@type") in ("urpx:URPXPackage", "urpx:URPXDocument"):
        return
    graph = doc.get("@graph")
    if graph is None:
        raise Migrate("no @graph and no wrapper; unrecognised document shape")
    if any(e.get("@type") == "urpx:URPXPackage" for e in graph):
        return

    plans = [e for e in graph if e.get("@type") == "urpx:RatePlan"]
    mods = [e for e in graph if e.get("@type") == "urpx:RatePlanModifier"]
    if not plans and not mods:
        raise Migrate("@graph holds no RatePlan or RatePlanModifier to package")

    date = path.parent.name
    schedule = path.parent.parent.parent.name
    utility = corpus.utility_of(path)
    pkg = {
        "@id": f"{utility}:doc-{schedule}-{date}",
        "@type": "urpx:URPXPackage",
        "urpx:targetURPXVersion": NEW_TARGET,
    }
    if plans:
        pkg["urpx:hasRatePlan"] = plans[0] if len(plans) == 1 else plans
    if mods:
        pkg["urpx:hasRatePlanModifier"] = mods[0] if len(mods) == 1 else mods

    siblings = [e for e in graph if e not in plans and e not in mods]
    doc["@graph"] = [pkg] + siblings
    kept = sorted({str(e.get("@type")) for e in siblings})
    log(f"T4 URPXPackage over {len(plans)} plan(s) + {len(mods)} modifier(s); "
        f"{len(siblings)} sibling(s) kept at @graph level: {', '.join(kept)}")


def t6_flatten_tariff_book_ref(doc, log):
    n = 0
    def visit(d):
        nonlocal n
        tbr = d.get("urpx:hasTariffBookReference")
        if tbr is None:
            return
        refs = tbr if isinstance(tbr, list) else [tbr]
        for r in refs:
            for k, v in r.items():
                if k in ("@type", "@id"):
                    continue
                d.setdefault(k, v)
        del d["urpx:hasTariffBookReference"]
        n += 1
    walk(doc, visit)
    if n:
        log(f"T6 {n} TariffBookReference flattened")


def t7_offered_by(doc, log):
    n = 0
    def visit(d):
        nonlocal n
        if "urpx:publishedBy" in d and d.get("@type") in (
                "urpx:RatePlan", "urpx:RatePlanVersion",
                "urpx:RatePlanModifier", "urpx:RatePlanModifierVersion"):
            d["urpx:offeredBy"] = d.pop("urpx:publishedBy"); n += 1
    walk(doc, visit)
    if n:
        log(f"T7 {n} publishedBy -> offeredBy")


def t8_org_identity(doc, ctx, log):
    """urpx:eiaId is not a defined term at ANY version; it validated only
    because OrganizationShape is open. Move it onto the identity chain."""
    n = 0
    def visit(d):
        nonlocal n
        if d.get("@type") != "urpx:Organization" or "urpx:eiaId" not in d:
            return
        eia = d.pop("urpx:eiaId")
        base = (d.get("@id") or "org:unknown")
        d["urpx:hasIdentity"] = {
            "@id": f"{base}-identity",
            "@type": "urpx:OrganizationIdentity",
            "urpx:hasName": {
                "@id": f"{base}-name",
                "@type": "urpx:OrganizationName",
                "urpx:name": d.get("urpx:legalName") or d.get("urpx:name") or base,
            },
            "urpx:hasIdentifier": {
                "@id": f"{base}-eia",
                "@type": "urpx:OrganizationIdentifier",
                "urpx:scheme": {"@id": "urpx:eiaScheme"},
                "skos:notation": str(eia),
            },
        }
        n += 1
    walk(doc, visit)
    if n:
        ctx.setdefault("skos", SKOS)
        log(f"T8 {n} Organization eiaId -> identity chain")


def t9_supersedes(doc, log):
    """Remove urpx:supersedes from version nodes; it is not admitted there.

    v0.5.1's RatePlanVersionShape and RatePlanModifierVersionShape are sh:closed
    and do not list supersedes, so leaving it is a hard ClosedConstraint
    violation. Upstream carries lineage on urpx:TariffFiling instead (four ConEd
    statement filings do exactly this) and on PricingModel, neither of which this
    corpus models yet.

    So the link is dropped rather than re-homed, and the lineage it recorded is
    temporarily unexpressed. That is deliberate and tracked as URPXT-ask1: the
    placement being removed is the one upstream issue #16 explicitly instructed
    on 2026-05-01, and v0.5.0 reversed it without a recorded discussion.
    """
    n = 0
    def visit(d):
        nonlocal n
        if d.get("@type") in VERSION_TYPES and "urpx:supersedes" in d:
            d.pop("urpx:supersedes"); n += 1
    walk(doc, visit)
    if n:
        log(f"T9 {n} supersedes dropped from version node(s); lineage pending URPXT-ask1")


def t10_back_links(doc, log):
    """Version nodes gain forRatePlan / forRatePlanModifier.

    Walks PARENT to CHILD. An earlier version searched the document for a node
    of the parent type and took the first one, which silently misattributed
    every version in a multi-source filing: CPAU e-1 holds three modifiers, so
    two of its modifier versions were linked to the wrong parent. The merged
    graph caught it as a MaxCount violation because the same version IRI then
    carried two different back-links across files. A predicate set-difference
    cannot see that, which is exactly why the gate is a merged graph.

    Nesting is KEPT: hasRatePlanVersion was re-admitted at sh:minCount 0.
    """
    n = 0
    NEST = {"urpx:RatePlan": ("urpx:hasRatePlanVersion", "urpx:forRatePlan"),
            "urpx:RatePlanModifier": ("urpx:hasRatePlanModifierVersion", "urpx:forRatePlanModifier")}

    def visit(parent):
        nonlocal n
        spec = NEST.get(parent.get("@type"))
        if not spec:
            return
        nest_prop, back_prop = spec
        pid = parent.get("@id")
        if not pid:
            raise Migrate(f"{parent.get('@type')} has no @id to point back at")
        versions = parent.get(nest_prop)
        if versions is None:
            return
        for vnode in (versions if isinstance(versions, list) else [versions]):
            if not isinstance(vnode, dict) or back_prop in vnode:
                continue
            vnode[back_prop] = {"@id": pid}
            n += 1

    walk(doc, visit)

    orphans = [d.get("@id") for d in find_all(doc, lambda x: x.get("@type") in VERSION_TYPES)
               if VERSION_TYPES[d["@type"]] not in d]
    if orphans:
        raise Migrate(f"version node(s) not reachable from a parent, so no back-link "
                      f"could be attributed: {orphans}")
    if n:
        log(f"T10 {n} version back-link(s)")


def t11_coverage_claim(doc, complete: bool, filing_date: str, log):
    """One version, one CoverageClaim, one verdict.

    A claim describes the VERSION, not the filing, and upstream names it after
    the version it describes (pge:cc-e-elec-2026-01-01 for version
    pge:e-elec-2026-01-01). tariff.toml's [modeling].complete describes the
    FILING, so deriving a per-version claim from it in every filing that embeds
    that version is a category error: pge:e-tou-c-vintage-pcia-2026-03-01 is
    carried by two filings whose manifests disagree (complete False and True),
    which produced one @id with two completenessResults and a MaxCount violation
    in the merged graph.

    So the full claim is authored only in the filing where the version is
    PRIMARY, meaning its date matches that filing's own version directory.
    Elsewhere the version references the same claim by @id, and the two unify in
    the merged graph exactly as every other cross-file reference does.
    """
    inlined = referenced = 0
    def visit(d):
        nonlocal inlined, referenced
        if d.get("@type") not in VERSION_TYPES or "urpx:hasCoverageClaim" in d:
            return
        vid = d.get("@id")
        if not vid:
            raise Migrate("version node has no @id, so no CoverageClaim can be named for it")
        prefix, _, localname = vid.partition(":")
        claim_id = f"{prefix}:cc-{localname}"
        if vid.endswith(filing_date):
            d["urpx:hasCoverageClaim"] = {
                "@id": claim_id,
                "@type": "urpx:CoverageClaim",
                "urpx:completenessResult": {"@id": "urpx:complete" if complete else "urpx:partial"},
                "urpx:selfContained": True,
            }
            inlined += 1
        else:
            d["urpx:hasCoverageClaim"] = {"@id": claim_id}
            referenced += 1
    walk(doc, visit)
    if inlined or referenced:
        log(f"T11 {inlined} CoverageClaim authored ({'complete' if complete else 'partial'})"
            + (f", {referenced} referenced by @id" if referenced else ""))


def t12_meter_count(doc, log):
    n = 0
    def visit(d):
        nonlocal n
        if "urpx:numberOfMeters" in d:
            d["urpx:meterCount"] = d.pop("urpx:numberOfMeters"); n += 1
    walk(doc, visit)
    if n:
        log(f"T12 {n} numberOfMeters -> meterCount")


class Migrate(Exception):
    pass


# Predicates the transforms are allowed to add or remove. Anything outside this
# signature aborts the file, which is the point of the self-check.
EXPECTED_REMOVED = {"hasTariffBookReference", "publishedBy", "eiaId", "numberOfMeters",
                    "supersedes", "hasRatePlan", "hasRatePlanModifier"}
EXPECTED_ADDED = {"offeredBy", "hasIdentity", "hasName", "name", "hasIdentifier", "scheme",
                  # T4 only: a synthesized URPXPackage introduces the wrapper's
                  # own predicates, which no other transform can produce.
                  "targetURPXVersion", "hasRatePlan", "hasRatePlanModifier",
                  "notation", "forRatePlan", "forRatePlanModifier", "hasCoverageClaim",
                  "completenessResult", "selfContained", "meterCount",
                  "pageStart", "pageEnd", "leafStart", "leafEnd", "sheetNumber",
                  "url", "title", "accessURL", "dateRetrieved", "description"}


def local(p) -> str:
    s = str(p)
    return s.rsplit("#", 1)[-1] if "#" in s else s.rsplit("/", 1)[-1]


def self_check(before_path: Path, after_text: str) -> list[str]:
    """Set difference on predicates. Returns unexplained changes."""
    b = rdflib.Graph(); b.parse(before_path, format="json-ld")
    a = rdflib.Graph(); a.parse(data=after_text, format="json-ld")
    bp = {local(p) for _, p, _ in b}
    ap = {local(p) for _, p, _ in a}
    unexplained = []
    for p in sorted(bp - ap):
        if p not in EXPECTED_REMOVED:
            unexplained.append(f"predicate disappeared unexpectedly: {p}")
    for p in sorted(ap - bp):
        if p not in EXPECTED_ADDED:
            unexplained.append(f"predicate appeared unexpectedly: {p}")
    return unexplained


def migrate_file(path: Path, complete: bool, dry_run: bool) -> bool:
    msgs: list[str] = []
    log = msgs.append
    doc = json.loads(path.read_text(encoding="utf-8"))
    try:
        t1_context(doc, log)
        t2_literal_iris(doc, log)
        t5_split_publication(doc, log)      # before T3/T4
        t3_package(doc, log)
        t4_synthesize_package(doc, path, log)
        t6_flatten_tariff_book_ref(doc, log)
        t7_offered_by(doc, log)
        t8_org_identity(doc, doc["@context"], log)
        t9_supersedes(doc, log)
        t10_back_links(doc, log)
        t11_coverage_claim(doc, complete, path.parent.name, log)
        t12_meter_count(doc, log)
    except Migrate as e:
        print(f"  REFUSED {path.name}: {e}", file=sys.stderr)
        return False

    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    problems = self_check(path, text)
    if problems:
        print(f"  REFUSED {path.name}: self-check found unexplained changes:", file=sys.stderr)
        for p in problems:
            print(f"      {p}", file=sys.stderr)
        return False

    print(f"  {path.name}")
    for m in msgs:
        print(f"      {m}")
    if not dry_run:
        path.write_text(text, encoding="utf-8")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--utility", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = [f for f in corpus.all_filing_jsonld() if corpus.utility_of(f) == args.utility]
    corpus.require_nonempty(files, f"filings for utility {args.utility!r}")

    import tomli
    ok = True
    print(f"{'DRY RUN: ' if args.dry_run else ''}migrating {len(files)} {args.utility} filing(s)\n")
    for f in files:
        manifest = f.parent / "tariff.toml"
        complete = False
        if manifest.exists():
            complete = tomli.loads(manifest.read_text(encoding="utf-8")).get("modeling", {}).get("complete", False)
        ok &= migrate_file(f, complete, args.dry_run)
    print()
    print("all files migrated" if ok else "one or more files REFUSED; nothing partial was written")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
