#!/usr/bin/env python3
"""Validate a URPX rate-plan or rate-plan-modifier filing with its referenced base
RatePlan(s) loaded as data context (Path 1 per upstream urpx-org/urpx#23).

A standalone RatePlanModifier filing's `urpx:applicableToRatePlan` references its
base RatePlan(s) by IRI. SHACL's `sh:class urpx:RatePlan` constraint cannot resolve
those IRIs unless the base filing is also loaded into the same data graph.

Usage:
    python dev/validate-with-base.py <jsonld>           # validate one file with auto-located base context
    python dev/validate-with-base.py --all              # walk the corpus and validate each
    python dev/validate-with-base.py --rdfs <jsonld>    # also enable RDFS inference

Run inside the urpx-tariffs project root with the ../urpx checkout adjacent.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import rdflib
from pyshacl import validate

REPO_ROOT = Path(__file__).resolve().parent.parent
URPX_REPO = REPO_ROOT.parent / "urpx"
SHAPES_PATH = "shacl/urpx-shacl.ttl"
ONTOLOGY_PATH = "ontology/urpx-ontology.ttl"

# The URPX revision the corpus is authored against. Pinned deliberately: reading
# whatever ../urpx happens to have checked out let the shapes drift silently to a
# release whose namespace no term in the corpus matches, which made every shape
# target zero nodes and every file report PASS. Override with --urpx-rev (or the
# URPX_REV environment variable) when migrating to a new release.
DEFAULT_URPX_REV = "v0.2.1"
URPX_REV = os.environ.get("URPX_REV", DEFAULT_URPX_REV)

_GRAPH_CACHE: dict[tuple[str, str], rdflib.Graph] = {}


def _read_at_rev(rev: str, rel_path: str) -> str:
    """Read a file from ../urpx at a fixed git revision.

    The shapes are read from the URPX checkout rather than vendored into this
    repo, deliberately: this repository is destined to be public and must not
    carry URPX-derived specification files. That makes ../urpx a hard
    dependency, so every way it can be missing is reported with the command
    that fixes it.

    `git show <rev>:<path>` has been unreliable for the multi-megabyte SHACL
    blob, so fall back to resolving the blob hash and cat-file-ing it directly.
    """
    if not (URPX_REPO / ".git").exists():
        raise SystemExit(
            f"ERROR: no URPX checkout at {URPX_REPO}. The shapes are read from it at a "
            f"pinned revision and are deliberately not vendored here. Clone urpx-org/urpx "
            f"next to this repository."
        )
    try:
        return subprocess.run(
            ["git", "-C", str(URPX_REPO), "show", f"{rev}:{rel_path}"],
            check=True, capture_output=True, text=True,
        ).stdout
    except subprocess.CalledProcessError:
        pass
    try:
        ls = subprocess.run(
            ["git", "-C", str(URPX_REPO), "ls-tree", rev, rel_path],
            check=True, capture_output=True, text=True,
        ).stdout.split()
    except subprocess.CalledProcessError:
        raise SystemExit(
            f"ERROR: revision {rev!r} is unknown in {URPX_REPO}. If it is a new tag or "
            f"branch, fetch it first:  git -C {URPX_REPO} fetch --all --tags"
        ) from None
    if len(ls) < 3:
        raise SystemExit(
            f"ERROR: {rel_path} does not exist in {URPX_REPO} at revision {rev}. The URPX "
            f"repository layout may have changed at that release."
        )
    return subprocess.run(
        ["git", "-C", str(URPX_REPO), "cat-file", "-p", ls[2]],
        check=True, capture_output=True, text=True,
    ).stdout


def load_graph(rel_path: str, rev: str | None = None) -> rdflib.Graph:
    """Parse a Turtle file from ../urpx at the pinned revision, cached."""
    rev = rev or URPX_REV
    key = (rev, rel_path)
    if key not in _GRAPH_CACHE:
        g = rdflib.Graph()
        g.parse(data=_read_at_rev(rev, rel_path), format="turtle")
        _GRAPH_CACHE[key] = g
    return _GRAPH_CACHE[key]


def shapes_target_any(data_graph: rdflib.Graph, shapes_graph: rdflib.Graph) -> bool:
    """True if at least one class asserted in the data is targeted by a shape.

    Guards against a vacuous PASS: if the data and the shapes disagree about the
    URPX namespace, every shape selects zero focus nodes and pyshacl conforms
    trivially. That is indistinguishable from success without this check.
    """
    SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
    data_types = set(data_graph.objects(None, rdflib.RDF.type))
    targeted = set(shapes_graph.objects(None, SH.targetClass))
    targeted |= set(shapes_graph.subjects(rdflib.RDF.type, SH.NodeShape)) & data_types
    return bool(data_types & targeted)


def index_corpus() -> dict[str, Path]:
    """Map @id (RatePlan, RatePlanVersion, RatePlanModifier, or
    RatePlanModifierVersion — string IRI like 'pge:e-1', 'pge:e-tou-c-2026-03-01',
    'sce:care', 'sce:care-2025-11-15') → file path. Both base rate-plan filings
    and standalone modifier filings are indexed so cross-file supersedes /
    applicableToRatePlan references can resolve."""
    index: dict[str, Path] = {}
    for path in REPO_ROOT.glob("ca/**/rate-plan*.jsonld"):
        with open(path) as fh:
            data = json.load(fh)
        _walk_rate_plans(data, path, index)
    return index


def _walk_rate_plans(node, path, index):
    if isinstance(node, dict):
        t = node.get("@type")
        if t in ("urpx:RatePlan", "urpx:RatePlanVersion",
                 "urpx:RatePlanModifier", "urpx:RatePlanModifierVersion"):
            iid = node.get("@id")
            if iid:
                index[iid] = path
        for v in node.values():
            _walk_rate_plans(v, path, index)
    elif isinstance(node, list):
        for v in node:
            _walk_rate_plans(v, path, index)


# Properties whose value is a cross-file IRI reference that a base file must
# resolve. SHACL enforces sh:class on each, so the referent file must be loaded
# into the merged graph.
CROSS_FILE_REF_PROPS = ("urpx:applicableToRatePlan", "urpx:supersedes")


def find_base_refs(jsonld_path: Path) -> list[str]:
    """Return @id strings referenced by any cross-file ref property."""
    with open(jsonld_path) as fh:
        data = json.load(fh)
    refs: list[str] = []
    _walk_refs(data, refs)
    return refs


def _walk_refs(node, refs):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in CROSS_FILE_REF_PROPS:
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict) and "@id" in item:
                            refs.append(item["@id"])
                elif isinstance(v, dict) and "@id" in v:
                    refs.append(v["@id"])
            else:
                _walk_refs(v, refs)
    elif isinstance(node, list):
        for v in node:
            _walk_refs(v, refs)


def _collect_local_rate_plan_ids(node, out: set[str]):
    """Collect all RatePlan @ids declared (with @type) in this node tree."""
    if isinstance(node, dict):
        if node.get("@type") == "urpx:RatePlan":
            iid = node.get("@id")
            if iid:
                out.add(iid)
        for v in node.values():
            _collect_local_rate_plan_ids(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_local_rate_plan_ids(v, out)


def _collect_local_modifier_ids(node, out: set[str]):
    """Collect all RatePlanModifier @ids declared (with @type) in this node tree."""
    if isinstance(node, dict):
        if node.get("@type") == "urpx:RatePlanModifier":
            iid = node.get("@id")
            if iid:
                out.add(iid)
        for v in node.values():
            _collect_local_modifier_ids(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_local_modifier_ids(v, out)


def _file_embeds_any(path: Path, modifier_ids: set[str]) -> bool:
    """Return True if the JSON-LD file declares any of the given IRIs as urpx:RatePlanModifier."""
    with open(path) as fh:
        data = json.load(fh)
    declared: set[str] = set()
    _collect_local_modifier_ids(data, declared)
    return bool(declared & modifier_ids)


def validate_one(jsonld: Path, *, rdfs: bool = False, verbose: bool = True) -> bool:
    """Path 1 per upstream urpx-org/urpx#23: validate with referenced base RatePlan(s)
    loaded as data context.

    Strategy:
      1. Parse the file under test; record its primary subjects.
      2. Load all referenced base files into the same graph (so applicableToRatePlan
         IRIs resolve as urpx:RatePlan instances).
      3. Run pyshacl on the merged graph.
      4. Filter out violations whose Focus Node is a base-file resource (i.e., not a
         resource declared in the file under test) — those are base-validation
         concerns, not modifier-validation concerns. This deals with the cross-base
         IRI collision problem (e.g., LADWP R-1A and R-1B both declare
         ladwp:ledger-energy with different names — which is a real cross-filing
         collision but irrelevant to whether LADWP NEM itself is well-formed).
    """
    g_local = rdflib.Graph()
    g_local.parse(jsonld, format="json-ld")
    local_subjects: set = set(s for s in g_local.subjects() if isinstance(s, rdflib.URIRef))

    # Collect ALL @ids declared in the file under test (including BNode-anchored, but those won't be focus nodes via SHACL targetClass anyway)
    with open(jsonld) as fh:
        local_data = json.load(fh)
    local_rps: set[str] = set()
    _collect_local_rate_plan_ids(local_data, local_rps)
    # Modifier IRIs declared in the file under test (used to detect bases that embed redundant copies)
    local_modifier_ids: set[str] = set()
    _collect_local_modifier_ids(local_data, local_modifier_ids)

    base_refs = find_base_refs(jsonld)
    external_refs = [r for r in base_refs if r not in local_rps]

    g = rdflib.Graph()
    g += g_local

    loaded: list[str] = []
    skipped_redundant: list[str] = []
    missing: list[str] = []
    if external_refs:
        index = index_corpus()
        loaded_paths: set = set()
        for ref in external_refs:
            base = index.get(ref)
            if not base:
                missing.append(ref)
                continue
            if base == jsonld or base in loaded_paths:
                continue
            # Skip bases that embed redundant copies of the same modifier — the
            # embedded sub-graph re-introduces the modifier's resources with fresh
            # blank-node operand-node anchors, producing spurious MaxCount violations
            # on the modifier's own ComparisonNodes (e.g., the CPAU multi-source
            # filings still embed E-HRA / E-EEC-1 / E-NSE-1 sub-graphs that pre-date
            # standalone modifier extraction).
            if local_modifier_ids and _file_embeds_any(base, local_modifier_ids):
                skipped_redundant.append(str(base.relative_to(REPO_ROOT)))
                continue
            g.parse(base, format="json-ld")
            loaded_paths.add(base)
            loaded.append(str(base.relative_to(REPO_ROOT)))

    if verbose and loaded:
        print(f"  loaded {len(loaded)} base context(s)", file=sys.stderr)
    if verbose and missing:
        print(
            f"  WARN: cross-file references not found in corpus: {missing}",
            file=sys.stderr,
        )

    shapes = load_graph(SHAPES_PATH)
    ontology = load_graph(ONTOLOGY_PATH)

    if not shapes_target_any(g, shapes):
        print(
            f"ERROR {jsonld.relative_to(REPO_ROOT)}: no shape targets any class asserted "
            f"in this file at URPX {URPX_REV}. Validation would pass vacuously; refusing "
            f"to report a result. Check the urpx: namespace binding against the pinned "
            f"revision, or pass --urpx-rev.",
            file=sys.stderr,
        )
        return False

    conforms, results_graph, results_text = validate(
        g,
        shacl_graph=shapes,
        ont_graph=ontology,
        inference="rdfs" if rdfs else None,
        advanced=True,
    )

    if conforms:
        if verbose:
            print(f"PASS  {jsonld.relative_to(REPO_ROOT)}")
        return True

    # Compute the set of IRIs whose ONLY resolution paths were skipped bases (those
    # bases embed redundant copies of the modifier under test). The IRIs ARE typed
    # correctly in those skipped files — we just couldn't load them without
    # introducing collisions. Suppress class-check violations for those refs.
    URPX_NS = str(load_graph(ONTOLOGY_PATH).namespace_manager.store.namespace("urpx") or "")
    suppressed_xref_iris: set = set()
    if skipped_redundant and external_refs:
        index = index_corpus()
        # For each ref, check if all its candidate resolution files were skipped
        for ref in external_refs:
            base = index.get(ref)
            if not base:
                continue
            base_rel = str(base.relative_to(REPO_ROOT))
            if base_rel in skipped_redundant:
                # JSON-LD prefix expansion: ref like "cpau:e-1" → expand
                # We need the full IRI as it appears in rdflib triples
                ctx = local_data.get("@context", {})
                if isinstance(ctx, dict) and ":" in ref:
                    prefix, local = ref.split(":", 1)
                    base_iri = ctx.get(prefix)
                    if base_iri:
                        suppressed_xref_iris.add(rdflib.URIRef(f"{base_iri}{local}"))

    # Filter violations: keep only those whose Focus Node belongs to local_subjects.
    SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
    primary_violations: list[str] = []
    base_violations_count = 0
    suppressed_xref_count = 0
    for result_node in results_graph.subjects(rdflib.RDF.type, SH.ValidationResult):
        focus_nodes = list(results_graph.objects(result_node, SH.focusNode))
        if not focus_nodes:
            continue
        focus = focus_nodes[0]
        if focus not in local_subjects:
            base_violations_count += 1
            continue
        # Suppress xref class-failures whose value is an IRI whose only resolution path was skipped
        path = list(results_graph.objects(result_node, SH.resultPath))
        path_str = str(path[0]) if path else "?"
        if path_str.endswith(("applicableToRatePlan", "applicableToRatePlanVersion", "supersedes")):
            value_nodes = list(results_graph.objects(result_node, SH.value))
            if value_nodes and value_nodes[0] in suppressed_xref_iris:
                suppressed_xref_count += 1
                continue
        msg = list(results_graph.objects(result_node, SH.resultMessage))
        msg_str = str(msg[0]) if msg else "?"
        primary_violations.append(f"Focus: {focus} | Path: {path_str} | Message: {msg_str}")

    if verbose:
        if base_violations_count > 0:
            print(
                f"  ({base_violations_count} cross-base violation(s) suppressed — base-file concerns, not modifier-validation)",
                file=sys.stderr,
            )
        if suppressed_xref_count > 0:
            print(
                f"  ({suppressed_xref_count} xref class-check(s) suppressed — only resolution paths were skipped redundant-embed bases)",
                file=sys.stderr,
            )

    if not primary_violations:
        if verbose:
            print(f"PASS  {jsonld.relative_to(REPO_ROOT)}")
        return True

    if verbose:
        print(f"FAIL  {jsonld.relative_to(REPO_ROOT)}")
        for v in primary_violations:
            print(f"  {v}")
    return False


def main():
    global URPX_REV
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("jsonld", nargs="?", help="Path to a single JSON-LD file (relative to repo root or absolute)")
    ap.add_argument("--all", action="store_true", help="Validate every rate-plan*.jsonld in the corpus")
    ap.add_argument("--rdfs", action="store_true", help="Enable RDFS inference (-i rdfs equivalent)")
    ap.add_argument("--urpx-rev", default=URPX_REV,
                    help=f"URPX git revision in ../urpx to validate against (default: {URPX_REV})")
    args = ap.parse_args()
    URPX_REV = args.urpx_rev

    if args.all:
        files = sorted(REPO_ROOT.glob("ca/**/rate-plan*.jsonld"))
        fail = 0
        for f in files:
            if not validate_one(f, rdfs=args.rdfs):
                fail += 1
        total = len(files)
        print(f"\n{total - fail}/{total} passed")
        sys.exit(0 if fail == 0 else 1)

    if not args.jsonld:
        ap.error("provide a JSON-LD path or --all")

    p = Path(args.jsonld)
    if not p.is_absolute():
        # try repo-relative first
        candidate = REPO_ROOT / p
        if candidate.exists():
            p = candidate
    sys.exit(0 if validate_one(p, rdfs=args.rdfs) else 1)


if __name__ == "__main__":
    main()
