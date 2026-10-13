#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Fail two Prices in one filing version that occupy the same cell with the
same start.

clj-urpx resolves one Price per cell: the PriceDefinition a Price references,
plus the Price's own urpx:serviceTierNumber and urpx:touPeriodNumber. Among the
Prices in a cell it keeps the latest-starting, and on equal starts it keeps the
first it reads, so the other is never read and nothing reports it. SMUD NEM1 had
this: its tod-5-8pm and tod-low-use credits shared five PriceDefinitions, and a
tod-low-use composition valued no credit.

THE CELL is (PriceDefinition @id, serviceTierNumber, touPeriodNumber); an absent
tier or period equals another absent one. THE START is the Price's
urpx:startDate, else its enclosing urpx:PriceSet's, else none; no start equals
no start.

THE SCOPE is what clj-urpx reads together: every Price of the version outside a
urpx:PriceSetAlternative, plus the Prices of any one alternative. Two
alternatives are never read together, so a cell they share is not a finding.
Prices are counted by @id, so a modifier inlined into several filings counts
once.

Exit codes: 0 clean, 1 a shared cell, 3 the harness could not answer.

Usage:
    python3 dev/lint_price_cells.py [--verbose] [--file JSONLD ...]

--file checks the named documents instead of the corpus; dev/test_price_cells.py
uses it on altered copies.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

VERSIONS = {"urpx:RatePlanVersion", "urpx:RatePlanModifierVersion"}


class Refused(Exception):
    pass


def types_of(node: dict) -> set[str]:
    t = node.get("@type")
    return set(t) if isinstance(t, list) else {t} if t else set()


def scan(rel: str, doc) -> list[dict]:
    """Every Price in `doc` that references a PriceDefinition, with its version,
    its PriceSetAlternative (or None), its cell and its start."""
    out: list[dict] = []

    def walk(x, version, alt, set_start):
        if isinstance(x, list):
            for v in x:
                walk(v, version, alt, set_start)
            return
        if not isinstance(x, dict):
            return
        ts = types_of(x)
        if ts & VERSIONS:
            version, alt, set_start = x.get("@id"), None, None
        if "urpx:PriceSetAlternative" in ts:
            alt = x.get("@id")
        if "urpx:PriceSet" in ts:
            set_start = x.get("urpx:startDate", set_start)
        if "urpx:Price" in ts and isinstance(x.get("urpx:referencesPriceDefinition"), dict):
            out.append({"file": rel, "version": version, "alt": alt, "price": x.get("@id"),
                        "cell": (x["urpx:referencesPriceDefinition"].get("@id"),
                                 x.get("urpx:serviceTierNumber"), x.get("urpx:touPeriodNumber")),
                        "start": x.get("urpx:startDate", set_start)})
        for k, v in x.items():
            if k != "@context":
                walk(v, version, alt, set_start)

    walk(doc, None, None, None)
    return out


def shared(prices: list[dict]) -> list[dict]:
    """The cells shared within one scope, each reported once."""
    by_version: dict[str, dict[object, dict[str, dict]]] = {}
    for p in prices:
        v = by_version.setdefault(p["version"] or p["file"], {})
        v.setdefault(p["alt"], {}).setdefault(p["price"] or repr(p), p)
    found: dict[tuple, dict] = {}
    for version, scopes in by_version.items():
        common = list(scopes.get(None, {}).values())
        alts = [a for a in scopes if a is not None] or [None]
        for a in alts:
            members = common + (list(scopes[a].values()) if a is not None else [])
            groups: dict[tuple, list[dict]] = {}
            for p in members:
                groups.setdefault((p["cell"], p["start"]), []).append(p)
            for (cell, start), ps in groups.items():
                if len(ps) < 2:
                    continue
                ids = tuple(sorted(p["price"] or "?" for p in ps))
                key = (version, cell, start, ids)
                found.setdefault(key, {"version": version, "cell": cell, "start": start,
                                       "prices": ids, "file": ps[0]["file"],
                                       "alternatives": set()})["alternatives"].add(a)
    return list(found.values())


def run(files: list[Path], whole_corpus: bool = True) -> dict:
    corpus.require_nonempty(files, "JSON-LD documents")
    prices: list[dict] = []
    for p in files:
        rel = str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p)
        prices += scan(rel, json.loads(p.read_text()))
    if whole_corpus and not prices:
        raise Refused("no urpx:Price referencing a PriceDefinition anywhere in the corpus, so the "
                      "check compared nothing; the walk has probably broken")
    return {"prices": len({p["price"] for p in prices}),
            "versions": len({p["version"] for p in prices}),
            "shared": shared(prices)}


def report(r: dict, verbose: bool) -> int:
    for f in sorted(r["shared"], key=lambda f: (f["version"], str(f["cell"]))):
        pd, tier, period = f["cell"]
        where = "" if f["alternatives"] == {None} else \
            f" (with alternative {', '.join(sorted(a for a in f['alternatives'] if a))})"
        tier, period = ("none" if x is None else x for x in (tier, period))
        print(f"SHARED-CELL  {f['version']}: {', '.join(f['prices'])} all reference {pd}"
              f" with serviceTierNumber {tier}, touPeriodNumber {period} and start "
              f"{f['start'] or 'none'}{where}, in {f['file']}. clj-urpx reads one of them. Give "
              f"each its own PriceDefinition, or tell them apart by tier, period or start.",
              file=sys.stderr)
    if verbose:
        print(f"  {r['prices']} Prices in {r['versions']} versions")
    n = len(r["shared"])
    print(f"price cells: {n} shared cell(s), over {r['prices']} Prices in {r['versions']} versions",
          file=sys.stderr if n else sys.stdout)
    return 1 if n else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--file", nargs="+", type=Path, help="check these documents instead of the corpus")
    args = ap.parse_args(argv)
    try:
        r = (run([p.resolve() for p in args.file], whole_corpus=False) if args.file
             else run(corpus.all_filing_jsonld()))
    except (Refused, SystemExit) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001 - refusing is a distinct outcome
        print(f"REFUSED: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    return report(r, args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
