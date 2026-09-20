#!/usr/bin/env python3
"""SHACL-validate the urpx-tariffs corpus against a pinned URPX revision.

The gate unit is a MERGED graph per utility, not a per-file run. Cross-file
references (`urpx:applicableToRatePlan`, `urpx:supersedes`) only resolve when the
referent is in the same graph, and no modifier pairing crosses a utility
boundary, so merging one utility resolves every reference it has. The six
per-utility profiles sum to the whole-corpus profile exactly, so a wave gated on
its own utility loses no coverage.

An earlier version validated file-by-file and suppressed the resulting cross-file
violations to reach a clean report. That suppression is gone: it hid 735
cross-base violations and 7 xref class-checks, which is indistinguishable from
having none.

Modes:
    --all                    every utility, each as its own merged graph (the gate)
    --utility <slug>         one utility merged (the wave gate)
    --merged                 the whole corpus as one graph; the only mode that can
                             see a NEW cross-utility @id collision
    --per-file               each file alone, unsuppressed (DIAGNOSTIC, expect
                             failures from unresolved cross-file references)
    <jsonld>                 one file alone (DIAGNOSTIC, same caveat)

    --urpx-rev <rev>         URPX revision in ../urpx to validate against
    --rdfs                   enable RDFS inference
    --keys                   print stable violation keys, for baseline comparison

Exit codes: 0 conforming, 1 violations, 3 refused (the harness cannot produce a
meaningful answer, e.g. the data and the shapes share no vocabulary).

Run from the urpx-tariffs project root with the ../urpx checkout adjacent.
"""
from __future__ import annotations

import argparse
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


# --- corpus discovery -------------------------------------------------------
# One place, so the pending restructure to us/<subdivision>/<utility>/<carrier>/
# changes this function and nothing else.
CORPUS_ROOT = "ca"
_UTILITY_PATH_INDEX = 2   # ca/<class>/<utility>/...


def corpus_files(utility: str | None = None) -> list[Path]:
    """Every rate-plan filing, optionally narrowed to one utility."""
    files = sorted(REPO_ROOT.glob(f"{CORPUS_ROOT}/**/rate-plan*.jsonld"))
    if utility is None:
        return files
    return [f for f in files if utility_of(f) == utility]


def utility_of(path: Path) -> str:
    return path.relative_to(REPO_ROOT).parts[_UTILITY_PATH_INDEX]


def utilities() -> list[str]:
    return sorted({utility_of(f) for f in corpus_files()})


# --- validation -------------------------------------------------------------
SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")

OK, VIOLATIONS, REFUSED = "ok", "violations", "refused"


def violation_keys(results_graph: rdflib.Graph) -> list[tuple[str, str, str]]:
    """Stable (focusNode, resultPath, constraintComponent) keys, sorted.

    Keys rather than counts: a count is invariant under a violation being traded
    for a different one, which is exactly the failure a migration produces.
    """
    keys = []
    for r in results_graph.subjects(rdflib.RDF.type, SH.ValidationResult):
        focus = next(results_graph.objects(r, SH.focusNode), None)
        path = next(results_graph.objects(r, SH.resultPath), None)
        comp = next(results_graph.objects(r, SH.sourceConstraintComponent), None)
        keys.append((str(focus), str(path), str(comp)))
    return sorted(keys)


def validate_files(files: list[Path], label: str, *, rdfs: bool = False,
                   verbose: bool = True, show_keys: bool = False):
    """Validate `files` as ONE merged graph. Returns (status, keys)."""
    if not files:
        # An empty file set conforms trivially. That is the vacuous pass this
        # harness exists to refuse, and it is exactly what a restructure that
        # breaks discovery would produce.
        print(f"REFUSED  {label}: no filings matched. Corpus discovery is broken "
              f"or the selector is wrong; refusing to report conformance over "
              f"an empty graph.", file=sys.stderr)
        return REFUSED, []

    g = rdflib.Graph()
    for f in files:
        g.parse(f, format="json-ld")

    shapes = load_graph(SHAPES_PATH)
    ontology = load_graph(ONTOLOGY_PATH)

    if not shapes_target_any(g, shapes):
        print(f"REFUSED  {label}: no shape targets any class asserted in these "
              f"{len(files)} file(s) at URPX {URPX_REV}. Validation would pass "
              f"vacuously. Check the urpx: namespace binding against the pinned "
              f"revision, or pass --urpx-rev.", file=sys.stderr)
        return REFUSED, []

    conforms, results_graph, _ = validate(
        g, shacl_graph=shapes, ont_graph=ontology,
        inference="rdfs" if rdfs else None, advanced=True,
    )
    keys = violation_keys(results_graph)

    if verbose:
        if conforms:
            print(f"PASS  {label}  ({len(files)} files)")
        else:
            print(f"FAIL  {label}  ({len(files)} files, {len(keys)} violations)")
            if show_keys:
                for focus, path, comp in keys:
                    print(f"  {focus} | {path} | {comp.rsplit('#', 1)[-1]}")
    return (OK if conforms else VIOLATIONS), keys


def main():
    global URPX_REV
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jsonld", nargs="?", help="A single JSON-LD file (DIAGNOSTIC)")
    ap.add_argument("--all", action="store_true",
                    help="Every utility, each merged separately (the gate)")
    ap.add_argument("--utility", metavar="SLUG", help="One utility, merged")
    ap.add_argument("--merged", action="store_true",
                    help="The whole corpus as one graph")
    ap.add_argument("--per-file", action="store_true",
                    help="Each file alone, unsuppressed (DIAGNOSTIC)")
    ap.add_argument("--rdfs", action="store_true", help="Enable RDFS inference")
    ap.add_argument("--keys", action="store_true", help="Print violation keys")
    ap.add_argument("--urpx-rev", default=URPX_REV,
                    help=f"URPX revision in ../urpx (default: {URPX_REV})")
    args = ap.parse_args()
    URPX_REV = args.urpx_rev
    kw = dict(rdfs=args.rdfs, show_keys=args.keys)

    if args.merged:
        status, _ = validate_files(corpus_files(), "corpus (merged)", **kw)
        sys.exit({OK: 0, VIOLATIONS: 1, REFUSED: 3}[status])

    if args.utility:
        files = corpus_files(args.utility)
        status, _ = validate_files(files, f"{args.utility} (merged)", **kw)
        sys.exit({OK: 0, VIOLATIONS: 1, REFUSED: 3}[status])

    if args.all:
        names = utilities()
        if not names:
            print("REFUSED  corpus discovery found no utilities.", file=sys.stderr)
            sys.exit(3)
        statuses = []
        for u in names:
            st, _ = validate_files(corpus_files(u), f"{u} (merged)", **kw)
            statuses.append(st)
        ok = sum(1 for s in statuses if s == OK)
        print(f"\n{ok}/{len(names)} utilities conforming")
        if REFUSED in statuses:
            sys.exit(3)
        sys.exit(0 if ok == len(names) else 1)

    if args.per_file:
        files = corpus_files()
        if not files:
            print("REFUSED  corpus discovery found no filings.", file=sys.stderr)
            sys.exit(3)
        print("DIAGNOSTIC: per-file mode leaves cross-file references unresolved, "
              "so failures here are expected and are not a gate signal.\n",
              file=sys.stderr)
        statuses = [validate_files([f], str(f.relative_to(REPO_ROOT)), **kw)[0]
                    for f in files]
        ok = sum(1 for s in statuses if s == OK)
        print(f"\n{ok}/{len(files)} conforming (per-file, diagnostic)")
        sys.exit(3 if REFUSED in statuses else (0 if ok == len(files) else 1))

    if not args.jsonld:
        ap.error("give a JSON-LD path, or one of --all / --utility / --merged / --per-file")

    p = Path(args.jsonld)
    if not p.is_absolute() and (REPO_ROOT / p).exists():
        p = REPO_ROOT / p
    print("DIAGNOSTIC: single-file mode leaves cross-file references unresolved.",
          file=sys.stderr)
    status, _ = validate_files([p], str(p.relative_to(REPO_ROOT)), **kw)
    sys.exit({OK: 0, VIOLATIONS: 1, REFUSED: 3}[status])


if __name__ == "__main__":
    main()
