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
import sys
from pathlib import Path

import rdflib
from pyshacl import validate

REPO_ROOT = Path(__file__).resolve().parent.parent
URPX_REPO = REPO_ROOT.parent / "urpx"
SHAPES = URPX_REPO / "shacl" / "urpx-shacl.ttl"
ONTOLOGY = URPX_REPO / "ontology" / "urpx-ontology.ttl"


def index_corpus() -> dict[str, Path]:
    """Map RatePlan @id (string IRI like 'pge:e-1') → file path."""
    index: dict[str, Path] = {}
    for path in REPO_ROOT.glob("ca/**/rate-plan_*.jsonld"):
        with open(path) as fh:
            data = json.load(fh)
        _walk_rate_plans(data, path, index)
    return index


def _walk_rate_plans(node, path, index):
    if isinstance(node, dict):
        if node.get("@type") == "urpx:RatePlan":
            iid = node.get("@id")
            if iid:
                index[iid] = path
        for v in node.values():
            _walk_rate_plans(v, path, index)
    elif isinstance(node, list):
        for v in node:
            _walk_rate_plans(v, path, index)


def find_base_refs(jsonld_path: Path) -> list[str]:
    """Return @id strings referenced by urpx:applicableToRatePlan."""
    with open(jsonld_path) as fh:
        data = json.load(fh)
    refs: list[str] = []
    _walk_refs(data, refs)
    return refs


def _walk_refs(node, refs):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "urpx:applicableToRatePlan":
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
            f"  WARN: applicableToRatePlan references not found in corpus: {missing}",
            file=sys.stderr,
        )

    shapes = rdflib.Graph()
    shapes.parse(SHAPES, format="turtle")
    ontology = rdflib.Graph()
    ontology.parse(ONTOLOGY, format="turtle")

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
    URPX_NS = "https://urpx-org.github.io/urpx/ontology/"
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
        if path_str.endswith(("applicableToRatePlan", "applicableToRatePlanVersion")):
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

    shapes = rdflib.Graph()
    shapes.parse(SHAPES, format="turtle")
    ontology = rdflib.Graph()
    ontology.parse(ONTOLOGY, format="turtle")

    conforms, _, results_text = validate(
        g,
        shacl_graph=shapes,
        ont_graph=ontology,
        inference="rdfs" if rdfs else None,
        advanced=True,
    )
    if verbose:
        if conforms:
            print(f"PASS  {jsonld.relative_to(REPO_ROOT)}")
        else:
            print(f"FAIL  {jsonld.relative_to(REPO_ROOT)}")
            for line in results_text.splitlines():
                if line.startswith(("Focus", "Result", "Message")) or "Constraint" in line:
                    print(f"  {line}")
    return conforms


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("jsonld", nargs="?", help="Path to a single JSON-LD file (relative to repo root or absolute)")
    ap.add_argument("--all", action="store_true", help="Validate every rate-plan*.jsonld in the corpus")
    ap.add_argument("--rdfs", action="store_true", help="Enable RDFS inference (-i rdfs equivalent)")
    args = ap.parse_args()

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
