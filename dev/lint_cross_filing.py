#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Two checks that look across filings, which per-filing SHACL and clj-urpx
cannot. dev/lint_consistency.py is the third, for RatePlan-level fields.

REFERENCES. Every @id a filing references under the corpus namespace
(https://rate-plans.grid-coordination.energy/, LAYOUT.md section 6) is defined
by some filing. A modifier filing names its base plans by IRI and a base filing
that inlines a modifier inherits its references (LAYOUT.md section 2), so a
reference may resolve in another file; it must resolve somewhere.

  - A reference is a node object holding only "@id": it adds no triple about
    that IRI as subject.
  - A definition is a node object holding "@id" and anything else, "@type"
    alone included, since that asserts rdf:type.
  - urpx: terms and IRIs outside the corpus namespace are not checked here;
    SHACL owns the vocabulary. An @id whose prefix the @context does not bind
    is a finding: JSON-LD reads it as an absolute IRI with that scheme, so it
    would otherwise fall outside the namespace silently.

ALIGNMENT. Directory, file name and IRIs name the same filing. For a document
at

    <country>/<subdivision>/<utility>/<carrier>/<schedule>/versions/<date>/
        <kind>_<utility>_<slug>_<date>.jsonld

the file name's kind matches the document kind corpus.json found it as, its
utility and date match the directory's, the `<utility>` prefix is bound to the
corpus namespace's `<utility>/`, and the document's URPXPackage, top entity
(urpx:RatePlan, or urpx:RatePlanModifier for a modifier) and that entity's one
version are `<utility>:doc-<slug>-<date>`, `<utility>:<slug>` and
`<utility>:<slug>-<date>`. The slug equals the schedule, except for a modifier
that the base's own PDF prices and that therefore sits in the base's directory
(LAYOUT.md section 2): its slug is `<schedule>-<descriptor>`, the directory holds
the base filing, and the modifier's version names `<utility>:<schedule>` in
urpx:applicableToRatePlan.

Exit codes: 0 clean, 1 a finding, 3 the harness could not answer.

Usage:
    python3 dev/lint_cross_filing.py [--verbose] [--root DIR --file JSONLD ...]

--file checks the named documents as the whole corpus, with paths parsed under
--root; dev/test_cross_filing.py uses it on fixtures.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

IRI_ROOT = "https://rate-plans.grid-coordination.energy/"
FILE_NAME = re.compile(r"(rate-plan|rate-plan-modifier)_([^_]+)_([^_]+)_(\d{4}-\d{2}-\d{2})\.jsonld")
ABSOLUTE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://|urn:")
TOP = {"rate-plan": ("urpx:hasRatePlan", "urpx:RatePlan", "urpx:hasRatePlanVersion"),
       "rate-plan-modifier": ("urpx:hasRatePlanModifier", "urpx:RatePlanModifier",
                              "urpx:hasRatePlanModifierVersion")}


class Refused(Exception):
    pass


def context_of(doc, rel: str) -> dict:
    """The document's one inline @context, refusing the features under which a
    string could be a reference this walk does not see."""
    ctx = doc.get("@context") if isinstance(doc, dict) else None
    if not isinstance(ctx, dict):
        raise Refused(f"{rel}: no inline object @context")
    for k, v in ctx.items():
        if k in ("@base", "@vocab", "@import"):
            raise Refused(f"{rel}: @context sets {k}, which this lint does not expand")
        if isinstance(v, dict) and (v.get("@type") in ("@id", "@vocab") or "@context" in v):
            raise Refused(f"{rel}: @context term {k!r} coerces strings to IRIs or scopes a "
                          "context, so a reference could hide in a plain string")
    return ctx


def expand(curie: str, ctx: dict) -> str | None:
    """The IRI a node @id names, or None when its prefix is unbound."""
    if ABSOLUTE.match(curie):
        return curie
    prefix, sep, suffix = curie.partition(":")
    if sep and isinstance(ctx.get(prefix), str):
        return ctx[prefix] + suffix
    return None


def walk_ids(doc, ctx: dict, rel: str):
    """(kind, @id as written, IRI or None) for every node object; kind is
    "ref" or "def" as the module docstring defines them."""
    out = []

    def walk(n) -> None:
        if isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, dict):
            if "@context" in n and n is not doc:
                raise Refused(f"{rel}: an embedded @context, which this lint does not apply")
            if isinstance(n.get("@id"), str):
                kind = "ref" if set(n) == {"@id"} else "def"
                out.append((kind, n["@id"], expand(n["@id"], ctx)))
            for k, v in n.items():
                if k not in ("@context", "@id", "@type", "@value"):
                    walk(v)

    walk(doc)
    return out


def check_references(docs: dict) -> tuple[dict, list[dict]]:
    """docs: {rel: parsed document}. Returns (counts, findings)."""
    defined: set[str] = set()
    refs: dict[str, set[str]] = defaultdict(set)
    findings: list[dict] = []
    for rel, doc in docs.items():
        ctx = context_of(doc, rel)
        for kind, written, iri in walk_ids(doc, ctx, rel):
            if iri is None:
                findings.append({"check": "references", "file": rel,
                                 "why": f"@id {written!r} uses a prefix the @context does not bind"})
            elif kind == "def":
                defined.add(iri)
            elif iri.startswith(IRI_ROOT):
                refs[iri].add(rel)
    for iri in sorted(set(refs) - defined):
        for rel in sorted(refs[iri]):
            findings.append({"check": "references", "file": rel,
                             "why": f"references {iri}, which no filing defines"})
    return {"defined": len(defined), "referenced": len(refs)}, findings


def one(v):
    """A single node, allowing the one-element list some filings write."""
    if isinstance(v, list) and len(v) == 1:
        return v[0]
    return v if isinstance(v, dict) else None


def package_of(doc) -> dict | None:
    nodes = doc.get("@graph", [doc]) if isinstance(doc, dict) else []
    found = [n for n in nodes if isinstance(n, dict) and n.get("@type") == "urpx:URPXPackage"]
    return found[0] if len(found) == 1 else None


def applies_to(version: dict) -> set[str]:
    v = version.get("urpx:applicableToRatePlan", [])
    return {x.get("@id") for x in (v if isinstance(v, list) else [v]) if isinstance(x, dict)}


def check_alignment(path: Path, kind: str, doc, root: Path) -> list[str]:
    """Why `path` disagrees with its directory or its IRIs; empty when it agrees."""
    utility, schedule, date = corpus.parse_filing_path(path, root)
    m = FILE_NAME.fullmatch(path.name)
    if not m:
        return ["file name is not <kind>_<utility>_<slug>_<date>.jsonld"]
    stem, f_utility, slug, f_date = m.groups()
    why = []
    if stem != kind:
        why.append(f"file name says {stem}, corpus.json found it as {kind}")
    if f_utility != utility:
        why.append(f"file name's utility {f_utility!r} is not the directory's {utility!r}")
    if f_date != date:
        why.append(f"file name's date {f_date} is not the directory's {date}")
    if doc.get("@context", {}).get(utility) != f"{IRI_ROOT}{utility}/":
        why.append(f"prefix {utility!r} is not bound to {IRI_ROOT}{utility}/")

    pkg = package_of(doc)
    if pkg is None:
        return why + ["no single urpx:URPXPackage node"]
    if pkg.get("@id") != f"{utility}:doc-{slug}-{date}":
        why.append(f"package @id {pkg.get('@id')!r} is not {utility}:doc-{slug}-{date}")
    has, top_type, has_version = TOP[stem]
    top = one(pkg.get(has))
    if top is None or top.get("@type") != top_type:
        return why + [f"no single {top_type} under {has}"]
    if top.get("@id") != f"{utility}:{slug}":
        why.append(f"{top_type} @id {top.get('@id')!r} is not {utility}:{slug}")
    version = one(top.get(has_version))
    if version is None:
        return why + [f"no single version under {has_version}"]
    if version.get("@id") != f"{utility}:{slug}-{date}":
        why.append(f"version @id {version.get('@id')!r} is not {utility}:{slug}-{date}")

    if slug != schedule:
        base = path.parent / f"rate-plan_{utility}_{schedule}_{date}.jsonld"
        if stem != "rate-plan-modifier":
            why.append(f"slug {slug!r} is not the directory's schedule {schedule!r}")
        elif not slug.startswith(f"{schedule}-"):
            why.append(f"modifier slug {slug!r} neither is nor extends the directory's "
                       f"schedule {schedule!r}")
        elif not base.exists():
            why.append(f"modifier {slug!r} sits in {schedule}/ but the directory holds no {base.name}")
        elif f"{utility}:{schedule}" not in applies_to(version):
            why.append(f"modifier {slug!r} sits in {schedule}/ but its version does not name "
                       f"{utility}:{schedule} in urpx:applicableToRatePlan")
    return why


def run(paths: list[tuple[Path, str]], root: Path = REPO, whole_corpus: bool = True) -> dict:
    """paths: (document, corpus.json kind)."""
    if not paths:
        raise Refused("no JSON-LD documents to check")
    docs: dict[str, dict] = {}
    findings: list[dict] = []
    for p, kind in paths:
        rel = str(p.relative_to(root)) if p.is_relative_to(root) else str(p)
        try:
            docs[rel] = json.loads(p.read_text())
        except (OSError, ValueError) as e:
            raise Refused(f"{rel}: {e}")
        try:
            why = check_alignment(p, kind, docs[rel], root)
        except ValueError as e:
            why = [str(e)]
        findings += [{"check": "alignment", "file": rel, "why": w} for w in why]
    counts, ref_findings = check_references(docs)
    if whole_corpus and not counts["referenced"]:
        raise Refused("no reference under the corpus namespace anywhere in the corpus, so the "
                      "check resolved nothing; the walk has probably broken")
    return {"documents": len(docs), **counts, "findings": findings + ref_findings}


def corpus_paths() -> list[tuple[Path, str]]:
    return [(p, kind) for kind in corpus.LAYOUT["documents"] for p in corpus.paths(kind)]


def kind_of(path: Path) -> str:
    return "rate-plan-modifier" if path.name.startswith("rate-plan-modifier_") else "rate-plan"


def report(r: dict, verbose: bool, limit: int = 10) -> int:
    by_file: dict[str, list[dict]] = defaultdict(list)
    for f in r["findings"]:
        by_file[f["file"]].append(f)
    for rel, fs in sorted(by_file.items()):
        print(f"CROSS-FILING  {rel}: {len(fs)} finding(s)", file=sys.stderr)
        for f in fs if verbose else fs[:limit]:
            print(f"  {f['check']}: {f['why']}", file=sys.stderr)
        if not verbose and len(fs) > limit:
            print(f"  ... {len(fs) - limit} more; --verbose lists them all", file=sys.stderr)
    bad = len(r["findings"])
    print(f"cross-filing: {bad} finding(s) in {len(by_file)} document(s); {r['documents']} "
          f"documents aligned against their paths, {r['referenced']} referenced corpus IRIs "
          f"resolved against {r['defined']} defined",
          file=sys.stderr if bad else sys.stdout)
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--root", type=Path, default=REPO, help="parse --file paths under this tree")
    ap.add_argument("--file", nargs="+", type=Path, help="check these documents instead of the corpus")
    args = ap.parse_args(argv)
    try:
        if args.file:
            r = run([(p.resolve(), kind_of(p)) for p in args.file], args.root.resolve(),
                    whole_corpus=False)
        else:
            r = run(corpus_paths())
    except (Refused, SystemExit) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3
    return report(r, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
