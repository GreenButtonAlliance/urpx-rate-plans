#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Mint a stable @id for every blank node that needs identity across filings.

LAYOUT.md section 2 justifies re-serializing one subtree in several filings with
"RDF graph merge handles the overlap cleanly". That holds only for nodes that
carry an @id. 1184 operand nodes carry none, and neither do the PlanElements,
Prices, BillingModel, CalculationMethod and AlternativeDimensions nodes, so
rdflib mints a fresh blank node per parse per file and merging N copies of one
subtree leaves N blank children hanging off one named parent. sh:maxCount 1 on
leftOperand, rightOperand, hasPlanElements, hasPrices, hasBillingModel,
hasCalculationMethod and hasAlternativeDimensions then fires once per extra copy.

APPLIED CORPUS-WIDE, NOT WHERE A COLLISION WAS NOTICED. That is the lesson
LAYOUT.md section 6 records: a uniqueness convention enforced only where somebody
spotted a clash is not a convention, and the 509-@id mess this corpus just
cleaned up is what it produces.

NAMING: `<@id of the node that points at it>-<property, minus a `has` prefix,
kebab-cased>`.

  pge:e-tou-c-2026-03-01                      -> ...-plan-elements
                                              -> ...-prices
  pge:e-tou-c-2026-03-01-plan-elements        -> ...-plan-elements-billing-model
  cpau:e-hra-2023-01-01-cond-reserve-25-75    -> ...-left-operand
                                              -> ...-right-operand

Three properties this scheme needs, all measured true corpus-wide by --audit:

  1. Every blank node in scope hangs off a parent that is either already named or
     itself in scope, so a top-down walk always has a name to build on.
  2. No parent holds more than one blank in-scope child under a single property,
     so (parent, property) is unique and needs no ordinal. An ordinal would be
     the weak point anyway: it depends on array order, which is not guaranteed
     to agree between two serializations of one subtree.
  3. The parent @id is already scoped to its owning version (LAYOUT.md section 6,
     enforced by dev/lint_iri_scope.py), so the child inherits that scoping
     transitively. Deriving the name from the parent rather than re-deriving it
     from the owning version is what makes an inlined modifier's operands come
     out identically named in every filing that inlines them: CPAU's e-hra
     subtree hangs off `cpau:e-hra-2023-01-01` in e-1, e-1-tou and e-hra alike.

THE SELF-CHECK IS A RELABELLING ISOMORPHISM. Naming a blank node changes no
predicate, so a predicate-level diff would pass on arbitrary damage. Instead
every newly minted IRI in the after-graph is replaced by a fresh blank node and
the result must be isomorphic to the before-graph. That passes only if the file
changed by exactly this labelling: a dropped triple, an edited literal, or two
distinct blanks collapsed onto one name all fail it.

Usage:
    python3 dev/name_blank_nodes.py --audit      # check the three properties
    python3 dev/name_blank_nodes.py --plan       # print the names, write nothing
    python3 dev/name_blank_nodes.py --dry-run
    python3 dev/name_blank_nodes.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import rdflib
from rdflib.compare import to_isomorphic

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

# The types that need identity. Every one of them is either a direct target of a
# sh:maxCount 1 property or the sole parent of one, so leaving any of them blank
# leaves a duplicate that the merged graph cannot fold away.
#
# urpx:BillingModel is here for the second reason and only that reason: nothing
# points at a BillingModel more than once, but PlanElementsShape puts
# sh:maxCount 1 on urpx:hasBillingModel, so naming PlanElements without naming
# BillingModel trades five hasPlanElements violations for five hasBillingModel
# ones. Closure is the rule: naming a parent is only safe once every
# sh:maxCount 1 edge out of it lands on something named.
#
# urpx:PriceSet is listed because the hasPrices violations are often described
# as PriceSet ones. Every corpus PriceSet is already named, so it selects
# nothing; the blank node under urpx:hasPrices is a urpx:Prices.
SCOPE = {
    "urpx:CustomOperandNode",
    "urpx:ObjectOperandNode",
    "urpx:DatatypeOperandNode",
    "urpx:PlanElements",
    "urpx:Prices",
    "urpx:PriceSet",
    "urpx:CalculationMethod",
    "urpx:AlternativeDimensions",
    "urpx:BillingModel",
}


class Naming(Exception):
    pass


def node_type(d) -> str | None:
    t = d.get("@type")
    if isinstance(t, str):
        return t
    if isinstance(t, list) and t:
        return t[0]
    return None


def suffix(prop: str) -> str:
    """`urpx:hasPlanElements` -> `plan-elements`, `urpx:leftOperand` -> `left-operand`.

    The `has` prefix is dropped because it reads as a verb on an edge and as
    noise in a name; `pge:e-tou-c-2026-03-01-plan-elements` is the documented
    `<utility>:<schedule>-<date>-<descriptor>` shape, `...-has-plan-elements`
    is not.
    """
    local = prop.split(":", 1)[-1]
    if local.startswith("has") and len(local) > 3 and local[3].isupper():
        local = local[3:]
    return re.sub(r"(?<!^)(?=[A-Z])", "-", local).lower()


def walk_named(node, fn, parent_id=None, prop=None):
    """Top-down walk carrying the @id of the node that points at this one.

    Top-down matters: a blank PlanElements is named before its blank BillingModel
    child is reached, so the child has a parent name to build on.
    """
    if isinstance(node, dict):
        fn(node, parent_id, prop)
        here = node.get("@id")
        here = here if isinstance(here, str) else None
        for k, v in node.items():
            if k == "@context":
                continue
            walk_named(v, fn, here if here is not None else parent_id, k)
    elif isinstance(node, list):
        for v in node:
            walk_named(v, fn, parent_id, prop)


def existing_ids() -> set[str]:
    out: set[str] = set()

    def visit(d, _p, _k):
        i = d.get("@id")
        if isinstance(i, str):
            out.add(i)

    for p in corpus.all_filing_jsonld():
        walk_named(json.loads(Path(p).read_text(encoding="utf-8")), visit)
    return out


def audit() -> int:
    """Check the three properties the naming scheme rests on."""
    orphans: list[str] = []
    multi: list[str] = []
    by_prop: Counter = Counter()
    unscoped_named: Counter = Counter()

    for p in corpus.all_filing_jsonld():
        doc = json.loads(Path(p).read_text(encoding="utf-8"))

        def visit(d, parent_id, prop, _p=Path(p)):
            t = node_type(d)
            if t not in SCOPE:
                return
            if isinstance(d.get("@id"), str):
                unscoped_named[t] += 1
                return
            by_prop[(t, prop)] += 1
            if parent_id is None:
                orphans.append(f"{_p.name}: blank {t} under {prop} has no named ancestor")

        walk_named(doc, visit)

        # Property 2 is about SIBLINGS, so it is checked on the arrays directly.
        def sibs(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == "@context":
                        continue
                    if isinstance(v, list):
                        n = sum(1 for x in v if isinstance(x, dict)
                                and node_type(x) in SCOPE and "@id" not in x)
                        if n > 1:
                            multi.append(f"{Path(p).name}: {node.get('@id')} has {n} "
                                         f"blank in-scope children under {k}")
                    sibs(v)
            elif isinstance(node, list):
                for v in node:
                    sibs(v)

        sibs(doc)

    print("blank in-scope nodes, by (type, incoming property):")
    for (t, prop), n in sorted(by_prop.items()):
        print(f"  {t:32s} {prop:32s} {n:5d}")
    print(f"  total {sum(by_prop.values())}")
    if unscoped_named:
        print("\nalready named (left alone):")
        for t, n in sorted(unscoped_named.items()):
            print(f"  {t:32s} {n:5d}")

    ok = True
    print(f"\n[1] blanks with no named ancestor: {len(orphans)}")
    for o in orphans[:5]:
        print(f"      {o}")
    ok &= not orphans
    print(f"[2] parents with >1 blank in-scope child under one property: {len(multi)}")
    for m in multi[:5]:
        print(f"      {m}")
    ok &= not multi

    names, clashes = plan_all()
    print(f"[3] minted names colliding with an existing @id or each other: {len(clashes)}")
    for c in clashes[:5]:
        print(f"      {c}")
    ok &= not clashes
    print(f"\n{sum(len(v) for v in names.values())} name(s) would be minted across "
          f"{len(names)} file(s).")
    return 0 if ok else 1


def name_file(doc) -> list[tuple[str, str, str]]:
    """Assign @ids in place. Returns (parent, property, new @id) per assignment."""
    minted: list[tuple[str, str, str]] = []

    def visit(d, parent_id, prop):
        t = node_type(d)
        if t not in SCOPE or isinstance(d.get("@id"), str):
            return
        if parent_id is None:
            raise Naming(f"blank {t} under {prop} has no named parent")
        if ":" not in parent_id:
            raise Naming(f"parent {parent_id!r} is not a CURIE")
        new = f"{parent_id}-{suffix(prop)}"
        # Insert after @type so the diff reads as one added line in the place
        # the rest of the corpus puts it.
        items = list(d.items())
        d.clear()
        placed = False
        for k, v in items:
            d[k] = v
            if k == "@type" and not placed:
                d["@id"] = new
                placed = True
        if not placed:
            rest = list(d.items())
            d.clear()
            d["@id"] = new
            d.update(rest)
        minted.append((parent_id, prop, new))

    walk_named(doc, visit)
    return minted


def plan_all() -> tuple[dict[Path, list[tuple[str, str, str]]], list[str]]:
    """Plan every file and report any name that collides.

    A minted name may legitimately repeat ACROSS files: that is the whole point,
    two serializations of one subtree must agree. It may never repeat within a
    file, and it may never equal an @id that already exists anywhere.
    """
    have = existing_ids()
    out: dict[Path, list[tuple[str, str, str]]] = {}
    clashes: list[str] = []
    provenance: dict[str, set[str]] = defaultdict(set)
    for p in corpus.all_filing_jsonld():
        p = Path(p)
        doc = json.loads(p.read_text(encoding="utf-8"))
        try:
            minted = name_file(doc)
        except Naming as e:
            clashes.append(f"{p.name}: {e}")
            continue
        seen: set[str] = set()
        for parent, prop, new in minted:
            if new in have:
                clashes.append(f"{p.name}: {new} already exists in the corpus")
            if new in seen:
                clashes.append(f"{p.name}: {new} minted twice in one file")
            seen.add(new)
            provenance[new].add(f"{parent}|{prop}")
        if minted:
            out[p] = minted
    for new, srcs in provenance.items():
        if len(srcs) > 1:
            clashes.append(f"{new} is minted from {len(srcs)} different (parent, property) "
                           f"pairs: {sorted(srcs)[:2]}")
    return out, clashes


def self_check(before_path: Path, after_text: str, minted: set[str]) -> list[str]:
    """Replace every minted IRI in the after-graph with a fresh blank node and
    require isomorphism with the before-graph.

    Exact and total: it passes only if the file changed by precisely this
    labelling of blank nodes and in no other way.
    """
    ctx = json.loads(before_path.read_text(encoding="utf-8")).get("@context", {})
    if not isinstance(ctx, dict):
        return ["@context is not an inline object; cannot expand CURIEs to check"]

    def expand(iri: str) -> str:
        prefix, _, local = iri.partition(":")
        base = ctx.get(prefix)
        return f"{base}{local}" if isinstance(base, str) else iri

    full = {expand(m) for m in minted}

    b = rdflib.Graph()
    b.parse(before_path, format="json-ld")
    a = rdflib.Graph()
    a.parse(data=after_text, format="json-ld")

    sub: dict[str, rdflib.BNode] = {}

    def unname(term):
        if isinstance(term, rdflib.URIRef) and str(term) in full:
            return sub.setdefault(str(term), rdflib.BNode())
        return term

    unnamed = rdflib.Graph()
    for s, pr, o in a:
        unnamed.add((unname(s), pr, unname(o)))

    if to_isomorphic(b) == to_isomorphic(unnamed):
        return []
    return [f"graph is not the original with {len(minted)} blank node(s) labelled: "
            f"before {len(b)} triples, after-unlabelled {len(unnamed)} triples"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true",
                    help="check the properties the scheme rests on, write nothing")
    ap.add_argument("--check", action="store_true",
                    help="gate mode: exit 1 if any in-scope blank node remains")
    ap.add_argument("--plan", action="store_true", help="print the names, write nothing")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--utility", help="restrict the rewrite to one utility")
    args = ap.parse_args()

    files = corpus.all_filing_jsonld()
    corpus.require_nonempty(files, "rate-plan filings")

    if args.audit:
        return audit()

    plan, clashes = plan_all()

    if args.check:
        # A gate, not a report. --audit exits 0 whether or not blank nodes are
        # waiting to be named, which is fine for inspection and useless for
        # enforcement; wiring --audit into gate.sh would have produced yet
        # another step that cannot fail.
        if clashes:
            print("REFUSED: minted names are not unique:", file=sys.stderr)
            for c in clashes[:20]:
                print(f"    {c}", file=sys.stderr)
            return 3
        n = sum(len(v) for v in plan.values())
        if n:
            print(f"blank nodes: {n} in-scope blank node(s) across {len(plan)} "
                  f"file(s) carry no @id\n", file=sys.stderr)
            for p in sorted(plan)[:5]:
                print(f"    {p.relative_to(REPO)}: {len(plan[p])}", file=sys.stderr)
            if len(plan) > 5:
                print(f"    ... and {len(plan) - 5} more file(s)", file=sys.stderr)
            print("\nA blank node under a sh:maxCount 1 edge multiplies when two "
                  "filings serialize\nthe same subtree, and the merged graph then "
                  "holds one child per filing. Fix:\n"
                  "    python3 dev/name_blank_nodes.py --plan   # review\n"
                  "    python3 dev/name_blank_nodes.py          # apply\n"
                  "See LAYOUT.md section 6.", file=sys.stderr)
            return 1
        print("blank nodes: clean (no in-scope blank node lacks an @id)")
        return 0
    if clashes:
        print("REFUSED: minted names are not unique:", file=sys.stderr)
        for c in clashes[:20]:
            print(f"    {c}", file=sys.stderr)
        return 3

    paths = sorted(plan)
    if args.utility:
        paths = [p for p in paths if f"/{args.utility}/" in str(p)]
        if not paths:
            print(f"REFUSED: no filings for utility {args.utility!r} carry a blank "
                  f"node in scope.", file=sys.stderr)
            return 3

    if args.plan:
        for p in paths:
            print(p)
            for parent, prop, new in plan[p]:
                print(f"    {parent}  --{prop}-->  {new}")
        return 0

    ok = True
    total = 0
    for p in paths:
        doc = json.loads(p.read_text(encoding="utf-8"))
        minted = name_file(doc)
        text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
        problems = self_check(p, text, {m[2] for m in minted})
        if problems:
            print(f"  REFUSED {p.name}:", file=sys.stderr)
            for msg in problems:
                print(f"    {msg}", file=sys.stderr)
            ok = False
            continue
        if args.dry_run:
            print(f"  {p.name}: would name {len(minted)} blank node(s)")
        else:
            p.write_text(text, encoding="utf-8")
            print(f"  {p.name}: named {len(minted)} blank node(s)")
        total += len(minted)
    print(f"\n{total} blank node(s) named across {len(paths)} file(s).")
    if not ok:
        print("One or more files were refused; nothing partial was written for them.",
              file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
