#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Refuse a subordinate @id claimed by more than one owning version.

LAYOUT.md section 6 has specified `<utility>:<schedule>-<date>-<descriptor>`
since the E-ELEC reissue, but it said to apply the rule "only to the IRIs that
actually collide on content". A uniqueness convention applied only where somebody
noticed a collision is not a convention: by the time it was measured, 509
subordinate @ids were minted by more than one schedule and
`sce:price-gen-summer-on-peak-2026-03-20` carried three different unit prices in
the merged graph.

This linter is the difference between a convention and a rule. It runs in
dev/gate.sh, so a new filing that reuses a descriptor fails at commit rather than
at the next audit.

THE TEST IS THE OWNER COUNT, NOT THE SCHEDULE COUNT. Those come apart in both
directions:

  - One owner, several schedules is CORRECT. CPAU's e-1 filing inlines the whole
    `cpau:e-hra` modifier, so `cpau:e-hra-2023-01-01-price-25-75-gen-480-642`
    appears under e-1, e-1-tou and e-hra. It is one resource and the three files
    agree about it.
  - Several owners, one schedule is a DEFECT. Two versions of PG&E E-ELEC each
    minting `pge:price-pcia` put one Price with two unit prices in the merged
    graph, which is the cross-version case the section was originally about.

Exit codes: 0 clean, 1 a violation, 3 the harness could not answer.

Usage:
    python3 dev/lint_iri_scope.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402
import rescope_iris as rescope  # noqa: E402


def findings():
    defs, types, owners = rescope.scan()
    corpus.require_nonempty(list(defs), "identified nodes")
    out = []
    for iri in sorted(rescope.ambiguous(defs, types, owners)):
        out.append({
            "id": iri,
            "type": types.get(iri),
            "owners": sorted(owners.get(iri, ())),
            "files": sorted(str(p.relative_to(REPO)) for p in defs[iri]),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        bad = findings()
    except Exception as e:  # noqa: BLE001 - refusing is a distinct outcome
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(bad, indent=2))
        return 1 if bad else 0

    if not bad:
        print("IRI scope: clean (every subordinate @id has exactly one owning version)")
        return 0

    print(f"IRI scope: {len(bad)} subordinate @id(s) claimed by more than one "
          f"owning version\n")
    for f in bad:
        print(f"  {f['id']}  ({f['type']})")
        for o in f["owners"]:
            print(f"      owner: {o}")
        for p in f["files"]:
            print(f"      in:    {p}")
        print()
    print("Each of these is one IRI denoting more than one resource, so the merged")
    print("graph carries every owner's values at once. Fix with:")
    print("    python3 dev/rescope_iris.py --plan        # review")
    print("    python3 dev/rescope_iris.py               # apply")
    print("See LAYOUT.md section 6.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
