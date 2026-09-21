#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Attach a urpx:Evaluation to each partial CoverageClaim, from a sidecar file.

The corpus asserts urpx:partial on 50 CoverageClaims. A claim that says a filing
is incomplete without saying what is missing tells a consumer only that they
cannot trust it, not whether the gap matters to them. urpx:explainedBy carries a
urpx:Evaluation for exactly this, with evaluationKind urpx:coverageEvaluation:
"establishes a coverage claim's completeness verdict for its claimed scope".

The descriptions are determined per filing by reading the source PDF against what
the filing models. They arrive here as a sidecar JSON mapping claim @id to prose,
so that the judgement lives in a reviewed artifact and the mutation is mechanical.

APPLIES BY CLAIM @id, NOT BY FILE. pge:cc-e-tou-c-vintage-pcia-2026-03-01 is
defined in two filings, so keying on the id keeps both copies identical and
dev/normalize_copies.py --check clean.

urpx:evaluatedOn is sh:datatype xsd:dateTime and most filings carry no coercion
for it, so the term goes into @context alongside the value. Written as a bare
string it lands as xsd:string and fails the shape, the same trap as
urpx:dateRetrieved.

Usage:
    python3 dev/apply_coverage_evaluations.py <sidecar.json> [...] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

EVALUATED_ON = "2026-09-21T00:00:00"


def walk(node, fn):
    if isinstance(node, dict):
        fn(node)
        for k, v in node.items():
            if k == "@context":
                continue
            walk(v, fn)
    elif isinstance(node, list):
        for v in node:
            walk(v, fn)


def node_type(d):
    t = d.get("@type")
    if isinstance(t, str):
        return t
    if isinstance(t, list) and t:
        return t[0]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sidecars", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    descs: dict[str, str] = {}
    for s in args.sidecars:
        loaded = json.loads(Path(s).read_text(encoding="utf-8"))
        overlap = set(loaded) & set(descs)
        if overlap:
            print(f"REFUSED: {s} repeats claim id(s) already supplied: "
                  f"{sorted(overlap)[:3]}", file=sys.stderr)
            return 3
        descs.update(loaded)

    bad = [k for k, v in descs.items() if not isinstance(v, str) or len(v.strip()) < 40]
    if bad:
        print(f"REFUSED: {len(bad)} description(s) missing or too short to be a real "
              f"explanation: {bad[:3]}", file=sys.stderr)
        return 3

    files = corpus.all_filing_jsonld()
    corpus.require_nonempty(files, "rate-plan filings")

    applied: dict[str, int] = {}
    touched: list[Path] = []
    for p in files:
        path = Path(p)
        doc = json.loads(path.read_text(encoding="utf-8"))
        hits: list[str] = []

        def visit(d):
            if node_type(d) != "urpx:CoverageClaim":
                return
            cid = d.get("@id")
            if cid not in descs or "urpx:explainedBy" in d:
                return
            d["urpx:explainedBy"] = {
                "@type": "urpx:Evaluation",
                "@id": f"{cid}-evaluation",
                "urpx:evaluationKind": {"@id": "urpx:coverageEvaluation"},
                "urpx:description": descs[cid],
                "urpx:evaluatedOn": EVALUATED_ON,
            }
            hits.append(cid)

        walk(doc, visit)
        if not hits:
            continue

        ctx = doc.get("@context")
        if not isinstance(ctx, dict):
            print(f"REFUSED: {path.name} has no inline @context to carry the "
                  f"xsd:dateTime coercion", file=sys.stderr)
            return 3
        ctx.setdefault("urpx:evaluatedOn", {"@type": "xsd:dateTime"})

        if not args.dry_run:
            with path.open("w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
        touched.append(path)
        for c in hits:
            applied[c] = applied.get(c, 0) + 1

    unapplied = sorted(set(descs) - set(applied))
    for c in unapplied:
        print(f"  WARNING: no unexplained claim found for {c}", file=sys.stderr)

    verb = "would attach" if args.dry_run else "attached"
    dup = {c: n for c, n in applied.items() if n > 1}
    print(f"{verb} {len(applied)} evaluation(s) across {len(touched)} file(s)")
    if dup:
        print(f"  (claims defined in more than one file, kept identical: "
              f"{', '.join(f'{c} x{n}' for c, n in dup.items())})")
    return 1 if unapplied else 0


if __name__ == "__main__":
    raise SystemExit(main())
