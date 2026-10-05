#!/usr/bin/env python3
"""SHACL-validate the urpx-rate-plans corpus against a pinned URPX revision.

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

    --urpx-rev <rev>         URPX revision to validate against, in place of the
                             one each file's urpx: binding dispatches to
    --with <jsonld>          merge a derived document (repeatable) into the
                             --merged or --utility graph, e.g.
                             reports/scenario-cost-models.jsonld
    --rdfs                   enable RDFS inference
    --keys                   print stable violation keys, for baseline comparison
    --write-baseline         record every merged mode's key profile
    --check-baseline         compare every merged mode against that record
                             (add --utility <slug> to compare just one)

Exit codes: 0 conforming, 1 violations or a new baseline key, 2 a baseline key
is gone (an improvement, refresh deliberately), 3 refused (the harness cannot produce a
meaningful answer, e.g. the data and the shapes share no vocabulary).

Run from the project root. The URPX checkout is found at $URPX_CHECKOUT.
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
# The URPX standard is cloned outside this project family. Override with
# URPX_CHECKOUT to point at a different working copy.
URPX_REPO = Path(
    os.environ.get("URPX_CHECKOUT", Path.home() / "projects" / "URPX" / "repo" / "urpx")
)
SHAPES_PATH = "shacl/urpx-shacl.ttl"
ONTOLOGY_PATH = "ontology/urpx-ontology.ttl"

# The URPX revision the corpus is authored against. Pinned deliberately: reading
# whatever the checkout happens to have checked out let the shapes drift silently to a
# release whose namespace no term in the corpus matches, which made every shape
# target zero nodes and every file report PASS. Override with --urpx-rev (or the
# URPX_REV environment variable) when migrating to a new release.
DEFAULT_URPX_REV = "v0.2.1"
URPX_REV = os.environ.get("URPX_REV", DEFAULT_URPX_REV)

_GRAPH_CACHE: dict[tuple[str, str], rdflib.Graph] = {}


# Git exports these to hooks; in a linked worktree GIT_DIR names this
# repository's worktree git dir, and `git -C <URPX checkout>` then looks there,
# so the pre-commit gate refused with "revision ... is unknown". The URPX
# checkout is a different repository and must be located from its own path.
_REPO_LOCATING_GIT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                           "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                           "GIT_PREFIX")


def _urpx_git(*args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in _REPO_LOCATING_GIT_VARS}
    return subprocess.run(["git", "-C", str(URPX_REPO), *args],
                          check=True, capture_output=True, text=True, env=env)


def _read_at_rev(rev: str, rel_path: str) -> str:
    """Read a file from the URPX checkout at a fixed git revision.

    The shapes are read from the URPX checkout rather than vendored into this
    repo, deliberately: this repository is destined to be public and must not
    carry URPX-derived specification files. That makes the checkout a hard
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
        return _urpx_git("show", f"{rev}:{rel_path}").stdout
    except subprocess.CalledProcessError:
        pass
    try:
        ls = _urpx_git("ls-tree", rev, rel_path).stdout.split()
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
    return _urpx_git("cat-file", "-p", ls[2]).stdout


def load_graph(rel_path: str, rev: str | None = None) -> rdflib.Graph:
    """Parse a Turtle file from the URPX checkout at the pinned revision, cached."""
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
# Delegated to dev/corpus.py so a restructure changes one module, not fourteen
# globs across nine files.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus  # noqa: E402


def corpus_files(utility: str | None = None) -> list[Path]:
    """Every rate-plan filing, optionally narrowed to one utility."""
    files = corpus.all_filing_jsonld()
    corpus.require_nonempty(files, "rate-plan filings")
    if utility is None:
        return files
    return [f for f in files if utility_of(f) == utility]


def utility_of(path: Path) -> str:
    return corpus.utility_of(path)


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


# --- version dispatch ---------------------------------------------------------
# During the per-utility migration waves the corpus carries TWO vocabularies at
# once. Each file declares which one it uses via its @context urpx binding, and
# the shape set is selected from that rather than from a global flag.
#
# A FILE is indivisible: urpx:hasCoverageClaim is sh:minCount 1 on two sh:closed
# shapes, so a half-migrated file matches neither shape set. The CORPUS is not
# indivisible, which is what makes staged waves legal at all.
#
# The gate unit is a merged graph, so a mixed-vocabulary SET is refused rather
# than guessed at: validating it against either shape set would silently exempt
# half the files.
OLD_URPX_NS = "https://urpx-org.github.io/urpx/ontology/"
NEW_URPX_NS = "https://urpx.org/ns/ontology/"

URPX_NAMESPACE_REVS = {
    "https://urpx-org.github.io/urpx/ontology/": "v0.2.1",
    # The candidate branch was deleted from origin once PR #60 merged. 95eb8e22
    # was its tip and is the revision this corpus was migrated against; repoint
    # to the v0.5.1 tag once it is cut.
    "https://urpx.org/ns/ontology/": "95eb8e22",
}


def declared_namespace(jsonld: Path) -> str | None:
    """The urpx: binding a file declares in its @context, without parsing RDF."""
    ctx = json.loads(jsonld.read_text(encoding="utf-8")).get("@context")
    if isinstance(ctx, dict):
        return ctx.get("urpx")
    if isinstance(ctx, list):
        for part in ctx:
            if isinstance(part, dict) and "urpx" in part:
                return part["urpx"]
    return None


def dispatch_rev(files: list[Path]) -> tuple[str | None, str | None]:
    """Return (revision, error). Refuses a mixed-vocabulary file set."""
    seen: dict[str, list[Path]] = {}
    for f in files:
        ns = declared_namespace(f)
        seen.setdefault(str(ns), []).append(f)
    if len(seen) > 1:
        lines = [f"    {ns}  ({len(fs)} file(s))" for ns, fs in sorted(seen.items())]
        return None, ("mixed URPX vocabularies in one graph:\n" + "\n".join(lines) +
                      "\n    Validating a mixed set against either shape set would exempt "
                      "half the files. Migrate a whole utility at a time.")
    ns = next(iter(seen))
    rev = URPX_NAMESPACE_REVS.get(ns)
    if rev is None:
        return None, f"unknown urpx namespace {ns!r}; no shape revision is mapped to it"
    return rev, None


def validate_files(files: list[Path], label: str, *, rdfs: bool = False,
                   verbose: bool = True, show_keys: bool = False,
                   rev_override: str | None = None, extra: list[Path] = ()):
    """Validate `files` as ONE merged graph. Returns (status, keys).

    `extra` documents are merged in after dispatch, so a derived document is
    held to the corpus's shape revision (or `rev_override`) rather than choosing
    its own. One that contributes no triple is refused: merging nothing would
    report the corpus's conformance as the derived document's.
    """
    if not files:
        # An empty file set conforms trivially. That is the vacuous pass this
        # harness exists to refuse, and it is exactly what a restructure that
        # breaks discovery would produce.
        print(f"REFUSED  {label}: no filings matched. Corpus discovery is broken "
              f"or the selector is wrong; refusing to report conformance over "
              f"an empty graph.", file=sys.stderr)
        return REFUSED, []

    rev, err = dispatch_rev(list(files) + list(extra))
    if err:
        print(f"REFUSED  {label}: {err}", file=sys.stderr)
        return REFUSED, []
    if rev_override:
        rev = rev_override

    g = rdflib.Graph()
    for f in files:
        g.parse(f, format="json-ld")
    for f in extra:
        before = len(g)
        g.parse(f, format="json-ld")
        if len(g) == before:
            print(f"REFUSED  {label}: {f} adds no triple to the graph.", file=sys.stderr)
            return REFUSED, []

    shapes = load_graph(SHAPES_PATH, rev)
    ontology = load_graph(ONTOLOGY_PATH, rev)

    if not shapes_target_any(g, shapes):
        print(f"REFUSED  {label}: no shape targets any class asserted in these "
              f"{len(files)} file(s) at URPX {rev}. Validation would pass "
              f"vacuously. Check the urpx: namespace binding against the pinned "
              f"revision, or pass --urpx-rev.", file=sys.stderr)
        return REFUSED, []

    conforms, results_graph, _ = validate(
        g, shacl_graph=shapes, ont_graph=ontology,
        inference="rdfs" if rdfs else None, advanced=True,
    )
    keys = violation_keys(results_graph)

    if verbose:
        n = f"{len(files)} files" + (f" + {len(extra)} derived" if extra else "")
        if conforms:
            print(f"PASS  {label}  ({n}, URPX {rev})")
        else:
            print(f"FAIL  {label}  ({n}, URPX {rev}, {len(keys)} violations)")
            if show_keys:
                for focus, path, comp in keys:
                    print(f"  {focus} | {path} | {comp.rsplit('#', 1)[-1]}")
    return (OK if conforms else VIOLATIONS), keys


# --- baseline -----------------------------------------------------------------
BASELINE_DIR = REPO_ROOT / "dev" / "baseline"


def declaring_files(iri: str, index: dict[str, set[str]]) -> set[str]:
    return index.get(iri, set())


def subject_index() -> dict[str, set[str]]:
    """Map every subject IRI to the set of files asserting it.

    Used to triage a violation: a focus node asserted in more than one file is
    cross-filing @id reuse (the known, accepted condition), while one confined to
    a single file would be a real defect hiding inside the accepted noise.
    """
    index: dict[str, set[str]] = {}
    for f in corpus_files():
        g = rdflib.Graph()
        g.parse(f, format="json-ld")
        rel = str(f.relative_to(REPO_ROOT))
        for s in set(g.subjects()):
            if isinstance(s, rdflib.URIRef):
                index.setdefault(str(s), set()).add(rel)
    return index


def collect_modes(*, rdfs: bool = False) -> dict:
    """Run every merged mode and return its key profile.

    Per-file is deliberately excluded: it produces 248 violations over only 162
    distinct keys, so its keys are not comparable with the merged schema.

    MID-MIGRATION: while the waves are running the corpus carries two
    vocabularies, so the whole-corpus merged mode legitimately cannot run. That
    mode is recorded as unavailable and the per-utility modes still collect,
    because those ARE homogeneous (a wave migrates a whole utility at once).
    Refusal for any OTHER reason still aborts: only mixedness is tolerated, and
    only for the one mode that spans utilities.
    """
    modes: dict[str, dict] = {}
    _, mixed_err = dispatch_rev(corpus_files())
    if mixed_err and mixed_err.startswith("mixed"):
        modes["corpus"] = {"unavailable": "mixed vocabularies during migration"}
    else:
        status, keys = validate_files(corpus_files(), "corpus (merged)",
                                      rdfs=rdfs, verbose=False)
        if status == REFUSED:
            return {}
        modes["corpus"] = {"count": len(keys), "keys": [list(k) for k in keys]}
    for u in utilities():
        st, ks = validate_files(corpus_files(u), f"{u} (merged)",
                                rdfs=rdfs, verbose=False)
        if st == REFUSED:
            return {}
        modes[u] = {"count": len(ks), "keys": [list(k) for k in ks]}
    return modes


def baseline_path(rev: str | None = None) -> Path:
    """One file, not one per revision.

    Dispatch makes the shape revision a per-FILE property, so during the waves a
    single baseline legitimately spans two vocabularies. Naming it after one of
    them would be a lie.
    """
    return BASELINE_DIR / "corpus.json"


def write_baseline(*, rdfs: bool = False) -> int:
    modes = collect_modes(rdfs=rdfs)
    if not modes:
        print("REFUSED  cannot record a baseline the harness would not report.",
              file=sys.stderr)
        return 3
    idx = subject_index()
    triage: dict[str, int] = {}
    unexplained: list[list[str]] = []
    if "keys" in modes["corpus"]:
        triage_keys = modes["corpus"]["keys"]
    else:
        seen = {tuple(k) for m, d in modes.items() if m != "corpus" for k in d["keys"]}
        triage_keys = [list(k) for k in sorted(seen)]
    for k in triage_keys:
        n = len(declaring_files(k[0], idx))
        if n > 1:
            triage["cross-filing-iri-reuse"] = triage.get("cross-filing-iri-reuse", 0) + 1
        else:
            triage["single-file"] = triage.get("single-file", 0) + 1
            unexplained.append(k)

    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "note_rev": "Shape revision is per-file, dispatched from each file's @context urpx binding.",
        "note": ("Accepted violations at this URPX revision. Compared as SETS, not "
                 "counts: a count is invariant under one violation being traded for "
                 "another, which is what a migration produces. Per-file mode is "
                 "excluded because its keys are not comparable. "
                 "The 'cross-filing-iri-reuse' triage counts focus nodes asserted in "
                 "more than one file. What that means changed once subordinate @ids "
                 "were scoped to their owning version: it no longer covers one "
                 "descriptor minted by several schedules (dev/lint_iri_scope.py now "
                 "refuses that outright), and every remaining key is a node DEFINED "
                 "twice, which is a different defect tracked separately."),
        "triage": triage,
        "unexplained_single_file_keys": unexplained,
        "modes": modes,
    }
    path = baseline_path()
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(REPO_ROOT)}")
    for m, d in sorted(modes.items()):
        print(f"  {m:8s} {d['count']:4d}" if "count" in d
              else f"  {m:8s}    - ({d['unavailable']})")
    print(f"  triage: {triage}")
    if unexplained:
        print(f"  WARNING: {len(unexplained)} key(s) whose focus node is asserted in "
              f"only one file; those are not explained by cross-filing reuse.",
              file=sys.stderr)
    return 0


def check_baseline(*, rdfs: bool = False, only: str | None = None) -> int:
    path = baseline_path()
    if not path.exists():
        print(f"REFUSED  no baseline at {path.relative_to(REPO_ROOT)}; "
              f"run --write-baseline first.", file=sys.stderr)
        return 3
    recorded = json.loads(path.read_text(encoding="utf-8"))["modes"]

    if only:
        # --fast path: compare one utility instead of re-running all seven modes.
        if only not in recorded:
            print(f"REFUSED  {only!r} is not a recorded mode in "
                  f"{path.relative_to(REPO_ROOT)}.", file=sys.stderr)
            return 3
        st, ks = validate_files(corpus_files(only), f"{only} (merged)",
                                rdfs=rdfs, verbose=False)
        if st == REFUSED:
            return 3
        current = {only: {"count": len(ks), "keys": [list(k) for k in ks]}}
        recorded = {only: recorded[only]}
    else:
        current = collect_modes(rdfs=rdfs)
        if not current:
            return 3

    new_keys, gone_keys = 0, 0
    for mode in sorted(set(recorded) | set(current)):
        if "unavailable" in recorded.get(mode, {}) or "unavailable" in current.get(mode, {}):
            print(f"SKIP {mode:8s} unavailable (mixed vocabularies during migration)")
            continue
        was = {tuple(k) for k in recorded.get(mode, {}).get("keys", [])}
        now = {tuple(k) for k in current.get(mode, {}).get("keys", [])}
        added, removed = now - was, was - now

        # A migration wave moves every predicate from the v0.2.x namespace to the
        # v0.5.1 one, so each surviving violation leaves as one key and returns as
        # another. Pair those up and report them as MIGRATED rather than as a
        # regression plus a fix, which is what they would otherwise read as on
        # every single wave. Nothing is hidden: the pairs are counted and shown,
        # and anything that does not pair exactly stays a regression.
        def shifted(k):
            return (k[0], k[1].replace(OLD_URPX_NS, NEW_URPX_NS), k[2])
        migrated = {k for k in removed if shifted(k) in added}
        added = added - {shifted(k) for k in migrated}
        removed = removed - migrated

        new_keys += len(added)
        gone_keys += len(removed)
        flag = "OK  " if not (added or removed) else "DIFF"
        shift = f"  ~{len(migrated)} migrated" if migrated else ""
        print(f"{flag} {mode:8s} baseline {len(was):4d}  now {len(now):4d}"
              f"  +{len(added)} -{len(removed)}{shift}")
        for k in sorted(added):
            print(f"      NEW      {k[0]} | {k[1]} | {k[2].rsplit('#', 1)[-1]}")
        for k in sorted(removed):
            print(f"      RESOLVED {k[0]} | {k[1]} | {k[2].rsplit('#', 1)[-1]}")

    if new_keys:
        print(f"\n{new_keys} new violation key(s): regression.", file=sys.stderr)
        return 1
    if gone_keys:
        print(f"\n{gone_keys} baseline key(s) no longer present: improvement. "
              f"Refresh the baseline deliberately with --write-baseline.",
              file=sys.stderr)
        return 2
    print("\nidentical to baseline")
    return 0


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
    ap.add_argument("--write-baseline", action="store_true",
                    help="Record every merged mode's key profile under dev/baseline/")
    ap.add_argument("--check-baseline", action="store_true",
                    help="Compare every merged mode against the recorded baseline")
    ap.add_argument("--urpx-rev", default=None,
                    help="URPX revision, overriding per-file dispatch")
    ap.add_argument("--with", dest="extra", action="append", default=[], metavar="JSONLD",
                    help="A derived document to merge into the --merged or --utility graph")
    args = ap.parse_args()
    if args.urpx_rev:
        URPX_REV = args.urpx_rev
    extra = [p if p.is_absolute() else REPO_ROOT / p for p in map(Path, args.extra)]
    missing = [str(p) for p in extra if not p.exists()]
    if missing:
        print(f"REFUSED  --with names no file: {', '.join(missing)}", file=sys.stderr)
        sys.exit(3)
    if extra and not (args.merged or args.utility):
        print("REFUSED  --with needs --merged or --utility.", file=sys.stderr)
        sys.exit(3)
    kw = dict(rdfs=args.rdfs, show_keys=args.keys, rev_override=args.urpx_rev)

    if args.write_baseline:
        sys.exit(write_baseline(rdfs=args.rdfs))

    if args.check_baseline:
        sys.exit(check_baseline(rdfs=args.rdfs, only=args.utility))

    if args.merged:
        status, _ = validate_files(corpus_files(), "corpus (merged)", extra=extra, **kw)
        sys.exit({OK: 0, VIOLATIONS: 1, REFUSED: 3}[status])

    if args.utility:
        files = corpus_files(args.utility)
        status, _ = validate_files(files, f"{args.utility} (merged)", extra=extra, **kw)
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
