#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Fail a urpx:CustomOperandNode whose nearest owning node is a Price, PriceSet,
PriceSetAlternative or PriceDefinition.

A free-text condition on a price cannot be evaluated by a consumer, and a set of
prices told apart only by such conditions reads as concurrent, so mutually
exclusive prices get summed. URPX has a selection layer for that: a
urpx:ProfileAlternative carries the condition, and the PriceSetAlternative or
PriceDefinition naming it is selected declaratively. A condition on
a ProfileAlternative or an EligibilityRule is not in the price layer and passes.

THE OWNING NODE is the nearest ancestor whose type is not condition machinery
(ConditionExpression, the comparison, boolean and operand nodes,
ApplicabilityRule, ApplicabilityGroup). A finding is attributed to the nearest
enclosing RatePlanVersion or RatePlanModifierVersion, and counted once per
operand @id per version, so a modifier inlined into several filings counts once.

ALLOWLIST names the versions whose price-layer conditions stay, with the
reason. An entry whose version carries no such condition, or that no filing in
the corpus defines, fails as stale.

Exit codes: 0 clean, 1 a violation or a stale entry, 3 the harness could not
answer.

Usage:
    python3 dev/lint_price_layer_conditions.py [--verbose] [--file JSONLD ...]

--file checks the named documents instead of the corpus, with no stale check;
dev/test_price_layer_conditions.py uses it on altered copies.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

PRICE_LAYER = {"urpx:Price", "urpx:PriceSet", "urpx:PriceSetAlternative", "urpx:PriceDefinition"}
MACHINERY = {"urpx:ConditionExpression", "urpx:ComparisonNode", "urpx:BooleanOperationNode",
             "urpx:OperationNode", "urpx:ApplicabilityRule", "urpx:ApplicabilityGroup",
             "urpx:CustomOperandNode", "urpx:ObjectOperandNode", "urpx:DatatypeOperandNode"}
VERSIONS = {"urpx:RatePlanVersion", "urpx:RatePlanModifierVersion"}

_DYNAMIC = ("an event-day predicate: whether an event is called on the day being priced is a "
            "live signal, not a customer or service attribute, so no ProfileAlternative can "
            "select it. That is the dynamic-pricing case URPX has not defined.")
ALLOWLIST = {
    "pge:e-rsmart-2025-10-31": "SmartRate Credit Applicable, " + _DYNAMIC,
    "sce:tou-d-prime-cpp-2026-03-20": (
        "Is CPP Event Today, " + _DYNAMIC + " The version's other price-layer condition, "
        "Grandfathered D-SDP Dual Participation on the maximum-credit Price, is a customer "
        "attribute gating one credit cap rather than a choice among exclusive prices, so it has "
        "no alternative to select either."),
}


class Refused(Exception):
    pass


def types_of(node: dict) -> set[str]:
    t = node.get("@type")
    return set(t) if isinstance(t, list) else {t} if t else set()


def scan(rel: str, doc) -> list[dict]:
    """Every CustomOperandNode in `doc`, with its owner and owning version."""
    out: list[dict] = []

    def walk(x, owner, version):
        if isinstance(x, list):
            for v in x:
                walk(v, owner, version)
            return
        if not isinstance(x, dict):
            return
        ts = types_of(x)
        if "urpx:CustomOperandNode" in ts:
            out.append({"file": rel, "operand": x.get("@id"), "owner": owner, "version": version,
                        "property": x.get("urpx:customConditionProperty")})
        if ts & VERSIONS:
            version = x.get("@id")
        if ts and not ts & MACHINERY:
            owner = (sorted(ts)[0], x.get("@id"))
        for k, v in x.items():
            if k != "@context":
                walk(v, owner, version)

    walk(doc, None, None)
    return out


def price_layer(found: list[dict]) -> dict[str, dict[str, dict]]:
    """{version: {operand @id: finding}} for the operands owned by a price-layer node."""
    out: dict[str, dict[str, dict]] = {}
    for f in found:
        if f["owner"] and f["owner"][0] in PRICE_LAYER:
            out.setdefault(f["version"] or f["file"], {}).setdefault(f["operand"] or repr(f), f)
    return out


def run(files: list[Path], whole_corpus: bool = True, allowlist: dict | None = None,
        check_stale: bool | None = None) -> dict:
    """Scan `files`. Stale allowlist entries are checked over the corpus only,
    unless `check_stale` says otherwise, since a subset need not define them."""
    allowlist = ALLOWLIST if allowlist is None else allowlist
    check_stale = whole_corpus if check_stale is None else check_stale
    corpus.require_nonempty(files, "JSON-LD documents")
    found: list[dict] = []
    versions: set[str] = set()
    for p in files:
        rel = str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p)
        doc = json.loads(p.read_text())
        found += scan(rel, doc)
        versions |= {n.get("@id") for n in _versions(doc)}
    if whole_corpus and not found:
        raise Refused("no urpx:CustomOperandNode anywhere in the corpus, so the check compared "
                      "nothing; the walk has probably broken")
    layer = price_layer(found)
    stale = {}
    if check_stale:
        for v in allowlist:
            if v not in versions:
                stale[v] = "no document checked defines this version"
            elif v not in layer:
                stale[v] = "carries no price-layer CustomOperandNode"
    return {"found": len(found), "layer": layer, "stale": stale, "allowlist": allowlist}


def _versions(doc):
    if isinstance(doc, dict):
        if types_of(doc) & VERSIONS:
            yield doc
        for k, v in doc.items():
            if k != "@context":
                yield from _versions(v)
    elif isinstance(doc, list):
        for v in doc:
            yield from _versions(v)


def failing(r: dict) -> dict[str, dict]:
    """{version: operands} for the price-layer findings no allowlist entry covers."""
    return {v: o for v, o in r["layer"].items() if v not in r["allowlist"]}


def report(r: dict, verbose: bool) -> int:
    allowlist = r["allowlist"]
    bad = 0
    for v, ops in sorted(r["layer"].items()):
        if v in allowlist:
            print(f"allowlisted  {v}: {len(ops)} operand(s). {allowlist[v]}")
            continue
        bad += len(ops)
        for f in sorted(ops.values(), key=lambda f: f["operand"] or ""):
            print(f"PRICE-LAYER  {v}: {f['operand']} ({f['property'] or 'right operand'}) "
                  f"on {f['owner'][0]} {f['owner'][1]}, in {f['file']}. State the choice as a "
                  f"urpx:ProfileAlternative and reference it, or add an ALLOWLIST entry saying "
                  f"why it cannot be one.", file=sys.stderr)
    for v, why in sorted(r["stale"].items()):
        print(f"STALE        {v}: on ALLOWLIST but {why}", file=sys.stderr)
    if verbose:
        for v, ops in sorted(r["layer"].items()):
            for f in ops.values():
                print(f"  {v:<36} {f['owner'][0]:<26} {f['operand']}")
    failing = bad + len(r["stale"])
    allow = sum(len(o) for v, o in r["layer"].items() if v in allowlist)
    print(f"price-layer conditions: {bad} failing operand(s), {allow} allowlisted in "
          f"{sum(1 for v in r['layer'] if v in allowlist)} version(s), {len(r['stale'])} stale "
          f"allowlist entr{'y' if len(r['stale']) == 1 else 'ies'}, over {r['found']} "
          f"CustomOperandNodes", file=sys.stderr if failing else sys.stdout)
    return 1 if failing else 0


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
