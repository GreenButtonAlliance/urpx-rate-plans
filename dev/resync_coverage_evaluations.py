#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Regenerate each CoverageClaim Evaluation from the filing's own deferrals.

WHY THIS EXISTS. The Evaluations say, in their own first sentence, that the parts
are "listed here in the same words as the filing's tariff.toml [modeling].deferrals
so the two records cannot drift". They were authored that way once, from
hand-written sidecars since retired, and nothing kept it
true. Every deferral corrected since then was corrected in the TOML alone, so the
JSON-LD became the stale copy of every fix, while still asserting it could not be.
An in-document prose audit measured the drift on 2026-09-23: six PG&E Evaluations had
diverged item by item, one of them at 0.23 similarity, and the TOML was the corrected
side in every case.

That sentence is a good invariant. The problem was that it was a promise rather than
a derivation. This script makes it a derivation: the TOML is the owner, the Evaluation
is generated, and re-running is how they are kept identical.

APPLIES BY CLAIM @id, NOT BY FILE, because
a claim @id can be defined in more than one filing, and the copies must stay
byte-identical or dev/lint_copy_divergence.py fails. The text is derived from the
OWNING filing's TOML, then written to every occurrence of that @id.

Only Evaluations already carrying the "same words" sentence are touched. An Evaluation
whose prose was deliberately written to say something else is left alone, because
overwriting it would silently discard a judgement.

Run from the repo root:
    python3 dev/resync_coverage_evaluations.py [--check]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

MARKER = "listed here in the same words as the filing's tariff.toml"
HEADER = ("This filing does not carry everything its source document states. {n} parts are "
          "deferred, listed here in the same words as the filing's tariff.toml "
          "[modeling].deferrals so the two records cannot drift.")


def description_for(deferrals: list[str]) -> str:
    """The Evaluation prose a filing's deferrals imply, whitespace-normalized.

    Normalizing is required rather than cosmetic: the TOML wraps its strings across
    lines and the JSON-LD does not, so a raw copy would differ on whitespace alone
    and every run would report drift that is not there.
    """
    items = " ".join(f"({i}) {' '.join(d.split())}" for i, d in enumerate(deferrals, 1))
    return HEADER.format(n=len(deferrals)) + " " + items


def evaluations(doc) -> dict[str, dict]:
    """Every Evaluation node in a document, by @id."""
    out: dict[str, dict] = {}

    def walk(x):
        if isinstance(x, dict):
            if x.get("@type") == "urpx:Evaluation" and x.get("@id"):
                out[x["@id"]] = x
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(doc)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit 1 without writing")
    args = ap.parse_args()

    # What each owning filing's deferrals say the prose should be.
    want: dict[str, str] = {}
    for toml in corpus.tariff_tomls():
        d = corpus.load_toml(toml)
        deferrals = (d.get("modeling") or {}).get("deferrals") or []
        if not deferrals:
            continue
        for jsonld in sorted(toml.parent.glob("*.jsonld")):
            for cid, node in evaluations(json.loads(jsonld.read_text())).items():
                if MARKER in (node.get("urpx:description") or ""):
                    want[cid] = description_for(deferrals)
    corpus.require_nonempty(
        want, "CoverageClaim Evaluations deriving their prose from a manifest")

    drifted, rewritten, files = [], 0, set()
    for jsonld in corpus.all_filing_jsonld():
        doc = json.loads(jsonld.read_text())
        changed = False
        for cid, node in evaluations(doc).items():
            target = want.get(cid)
            if target is None:
                continue
            if node.get("urpx:description") != target:
                drifted.append((jsonld, cid))
                if not args.check:
                    node["urpx:description"] = target
                    changed = True
        if changed:
            jsonld.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
            rewritten += 1
            files.add(jsonld)

    if args.check:
        if drifted:
            print(f"coverage evaluations: {len(drifted)} drifted from their manifest "
                  f"in {len({p for p, _ in drifted})} file(s)", file=sys.stderr)
            for p, cid in drifted[:30]:
                print(f"  {p.relative_to(REPO)}: {cid}", file=sys.stderr)
            print("\n  Each of these asserts its parts are listed in the same words as the "
                  "filing's\n  tariff.toml. Run dev/resync_coverage_evaluations.py to make that "
                  "true again.", file=sys.stderr)
            return 1
        print(f"coverage evaluations: clean ({len(want)} derived from their manifests, "
              f"all identical to the deferrals they quote)")
        return 0

    print(f"coverage evaluations: {len(drifted)} rewritten across {rewritten} file(s) "
          f"({len(want)} derived in total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
