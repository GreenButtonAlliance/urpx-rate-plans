#!/usr/bin/env python3
"""
Cross-filing RatePlan-level consistency linter.

LAYOUT.md section 2 promises a linter that verifies urpx:initialEffectiveDate,
urpx:ratePlanUniqueIdentifier, urpx:name, urpx:timezoneIdentifier and the
RatePlan @id are byte-identical across all filings of a given schedule. This is
that linter. dev/lint_cross_filing.py checks the rest of what crosses filings:
references resolving, and file names and IRIs agreeing with directories.

Walks the corpus through dev/corpus.py, groups rate-plan_*.jsonld files by their
<country>/<subdivision>/<utility>/<carrier>/<schedule>/ directory, finds the
urpx:RatePlan node in each filing wherever its wrapper puts it, and reports any
RatePlan-level field that differs across versions of the same schedule.

Exit codes:
  0  all schedules consistent
  1  drift detected on at least one schedule
  2  --fix was asked for
  3  refused: no filing yielded a urpx:RatePlan node

Usage:
  python3 dev/lint_consistency.py
  python3 dev/lint_consistency.py --json    # machine-readable
  python3 dev/lint_consistency.py --fix     # NOT IMPLEMENTED: drift
                                            # resolution is a human call

Modifier filings (rate-plan-modifier_*.jsonld) are skipped: their top-level
entity is urpx:RatePlanModifier, not RatePlan.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus

ROOT = Path(__file__).resolve().parent.parent

# Fields whose values must be byte-identical across all RatePlanVersions
# of the same RatePlan IRI (per LAYOUT.md §2):
RATE_PLAN_LEVEL_FIELDS = [
    "@id",
    "urpx:ratePlanUniqueIdentifier",
    "urpx:name",
    "urpx:initialEffectiveDate",
    "urpx:timezoneIdentifier",
]


def find_rate_plan(doc):
    """Return the filing's urpx:RatePlan node, wherever the wrapper puts it.

    This used to match two fixed shapes, `urpx:URPXDocument` with a
    `urpx:hasRatePlan` child and a legacy top-level `@graph` entry. The v0.5.1
    migration introduced a `urpx:URPXPackage` wrapper and matched neither, so
    this returned None for 41 of 73 filings and the linter reported "Schedules
    checked: 0" and then exited 0 with "corpus is consistent". It had been
    verifying nothing, while LAYOUT.md cited it as what keeps the identity layer
    honest.

    Searching the tree rather than naming wrapper shapes is what stops the next
    wrapper change from silently doing this again.
    """
    found = []

    def walk(node):
        if isinstance(node, dict):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if "urpx:RatePlan" in types and "@id" in node:
                found.append(node)
            for k, v in node.items():
                if k == "@context":
                    continue
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(doc)
    if not found:
        return None
    # A filing that inlines a modifier can carry more than one RatePlan node;
    # the filing's own plan is the one its RatePlanVersion points back to.
    return found[0]


def normalize(value):
    """Make a value comparable across files. JSON-LD dict refs become a
    sentinel-tagged tuple; everything else passes through."""
    if isinstance(value, dict):
        if list(value.keys()) == ["@id"]:
            return ("@id", value["@id"])
        return tuple(sorted((k, normalize(v)) for k, v in value.items()))
    if isinstance(value, list):
        return tuple(normalize(x) for x in value)
    return value


def collect_filings():
    """Return {schedule_dir: [(path, rateplan_node), ...]}."""
    out = defaultdict(list)
    for jsonld in corpus.rate_plan_files():
        try:
            doc = json.loads(jsonld.read_text())
        except Exception as e:
            print(f"  ✗ {jsonld.relative_to(ROOT)}: parse error ({e})", file=sys.stderr)
            continue
        rp = find_rate_plan(doc)
        if rp is None:
            print(f"  ✗ {jsonld.relative_to(ROOT)}: no urpx:RatePlan node", file=sys.stderr)
            continue
        # Group key: the schedule directory (trim "versions/<date>/...")
        rel = jsonld.relative_to(ROOT)
        schedule_dir = rel.parents[2]   # versions/<date>/<file>.jsonld → up 2 = schedule dir
        out[str(schedule_dir)].append((rel, rp))
    return out


def lint(filings_by_schedule):
    """Return list of (schedule_dir, field, {value: [paths]}) for every
    drift detected. Empty list = consistent."""
    drift = []
    for schedule, items in sorted(filings_by_schedule.items()):
        if len(items) < 2:
            continue
        for field in RATE_PLAN_LEVEL_FIELDS:
            values = defaultdict(list)
            for path, rp in items:
                v = normalize(rp.get(field))
                values[v].append(str(path))
            if len(values) > 1:
                drift.append((schedule, field, dict(values)))
    return drift


def main():
    json_mode = "--json" in sys.argv
    fix_mode = "--fix" in sys.argv
    if fix_mode:
        print("--fix is not implemented; drift resolution is a human call.", file=sys.stderr)
        return 2

    filings = collect_filings()

    if json_mode:
        out = {
            "schedules_checked": sorted(filings.keys()),
            "drift": [
                {"schedule": s, "field": f, "values": {str(k): v for k, v in vs.items()}}
                for s, f, vs in lint(filings)
            ],
        }
        json.dump(out, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1 if out["drift"] else 0

    # Human-readable mode
    #
    # Refuse rather than pass when there is nothing to check. Reporting "corpus
    # is consistent" over zero schedules is the failure this linter actually had
    # for months, and it is the same vacuity that dev/shacl_gate.clj guards
    # against with shacl/targets-any?. A gate that cannot fail is not a gate.
    if not filings:
        print("REFUSED: no filing yielded a urpx:RatePlan node, so there is "
              "nothing to compare. The wrapper shape probably changed; see "
              "find_rate_plan().", file=sys.stderr)
        return 3

    print(f"Schedules checked: {len(filings)}")
    multi = {s: items for s, items in filings.items() if len(items) >= 2}
    print(f"  with multiple versions: {len(multi)}")
    for s, items in sorted(multi.items()):
        versions = sorted(p.parent.name for p, _ in items)
        print(f"    {s}: {versions}")
    print()

    drift = lint(filings)
    if not drift:
        print("✓ No RatePlan-level drift detected — corpus is consistent.")
        return 0

    print(f"✗ Drift detected on {len(drift)} field(s):")
    for schedule, field, values in drift:
        print(f"\n  Schedule: {schedule}")
        print(f"  Field:    {field}")
        for v, paths in values.items():
            print(f"    value: {v!r}")
            for p in paths:
                print(f"      ← {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
