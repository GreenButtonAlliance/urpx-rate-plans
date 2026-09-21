#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Scope every subordinate @id to its owning version, per LAYOUT.md section 6.

LAYOUT.md has specified `<utility>:<schedule>-<date>-<descriptor>` for
subordinate resources since the E-ELEC reissue, with the worked example
`pge:e-elec-2026-03-27-price-public-purpose`, but it said to apply it "only to
the IRIs that actually collide on content". A uniqueness convention applied only
where somebody noticed a collision is not a convention: 509 subordinate @ids
were minted by more than one schedule, and in the merged graph
`sce:price-gen-summer-on-peak-2026-03-20` carried three different unit prices at
once. A further 34 were claimed by two versions of one schedule.

SCOPE COMES FROM THE OWNING VERSION, NOT THE DIRECTORY. The two differ wherever a
filing inlines another schedule's subtree, which 8 of them do: CPAU's e-1 inlines
the whole `cpau:e-hra` modifier and PG&E inlines a per-plan PCIA modifier into
five base filings. Directory scoping would rename one modifier's children three
different ways and mint three copies of one resource. Owner scoping gives them
one name in all three files, which is what they are.

dev/lint_iri_scope.py enforces the result so it cannot drift back.

THE SELF-CHECK IS A RENAME-MAP ISOMORPHISM, NOT A PREDICATE SET DIFFERENCE.
A rename changes no predicates at all, so the check used by migrate-v051.py
cannot see anything here: it would pass on a file this script had mangled
arbitrarily, as long as the vocabulary was untouched. Instead the before-graph
has the rename map applied to it in RDF space, and the result must be
isomorphic to the after-graph. That is exact and total: it passes only if the
file changed by precisely this rename and in no other way.

Blank nodes make plain triple comparison useless here (rdflib relabels them on
every parse), so the comparison goes through rdflib.compare.to_isomorphic.

Usage:
    python3 dev/rescope_iris.py --plan                 # print the map, write nothing
    python3 dev/rescope_iris.py --utility pge --dry-run
    python3 dev/rescope_iris.py --utility pge
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import rdflib
from rdflib.compare import to_isomorphic

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# The scope-defining nodes. A subordinate resource belongs to the nearest one of
# these that encloses it, and their @ids already carry the `<schedule>-<date>`
# form that LAYOUT.md section 6 prescribes.
VERSION_TYPES = {"urpx:RatePlanVersion", "urpx:RatePlanModifierVersion"}

# The identity layer. These name real-world entities that genuinely span the
# schedules of a utility, so one shared @id is the correct modeling and scoping
# them per schedule would mint N copies of one thing. dev/lint_consistency.py
# actively enforces that the RatePlan-level fields stay byte-identical across
# filings, so renaming these would also break that linter.
IDENTITY_TYPES = {
    "urpx:Organization",
    "urpx:OrganizationIdentity",
    "urpx:OrganizationName",
    "urpx:OrganizationIdentifier",
    "urpx:RateCase",
    "urpx:RatePlan",
    "urpx:RatePlanModifier",
    # Version nodes already carry the documented `<utility>:<schedule>-<date>`
    # form, so they are scoped by construction. Five of them are nonetheless
    # defined in two files with differing property sets; that is a duplicate
    # definition rather than an ambiguous @id, and is tracked separately.
    *VERSION_TYPES,
    "urpx:SourcePublication",
    "urpx:TariffPublication",
    "urpx:ProgramEnrollment",
}

# Types kept shared across schedules. A wrong entry here fails SILENTLY the
# first time two schedules diverge, whereas a wrong omission only costs a
# redundant IRI, so the bar for adding one is high and the list is short.
#
# The binding constraint is not whether the concept feels utility-level, it is
# CLOSURE: a shared @id is safe only if every sh:maxCount 1 value it carries is
# a literal, or an IRI that is itself kept shared. Anything else breaks when the
# wave rewrites its children, because the shared parent then has one value per
# schedule. Measured on PG&E: keeping urpx:ProfileAlternative shared while
# scoping its condition subtree takes the merged graph from 145 violations to
# 158, adding one hasConditionExpression MaxCount to each of the 21 @ids kept
# shared. Both types below are leaves under that test.
#
#   urpx:MetricSpecification  42 @ids, one body each, no maxCount-1 edge into
#                             the scoped set.
#   urpx:CoverageClaim        already carries the documented
#                             `<utility>:cc-<schedule>-<date>` form, so it is
#                             scoped by construction; the 3 multi-schedule ones
#                             are byte-identical.
#
# urpx:Season is deliberately NOT here. All 24 corpus Seasons agree today, but
# SeasonShape puts no sh:maxCount on urpx:month and 72 of 72 corpus Seasons are
# month-based, so a future divergence unions the months and the gate stays
# green. CPAU is the one utility whose schedules disagree on season bounds and
# the one that already mints per-schedule Season @ids.
KEEP_SHARED_TYPES: set[str] = {
    "urpx:MetricSpecification",
    "urpx:CoverageClaim",
}


class Rescope(Exception):
    pass


def walk(node, fn):
    """Apply fn to every dict in the tree, NEVER descending into @context.

    The corpus @context binds prefixed terms to coercion rules
    (`urpx:unitPrice` -> {"@type": "xsd:decimal"}). A generic recursive walk
    rewrites those term definitions. Same rule, same reason, as migrate-v051.py.
    """
    if isinstance(node, dict):
        fn(node)
        for k, v in node.items():
            if k == "@context":
                continue
            walk(v, fn)
    elif isinstance(node, list):
        for v in node:
            walk(v, fn)


def node_type(d) -> str | None:
    t = d.get("@type")
    if isinstance(t, str):
        return t
    if isinstance(t, list) and t:
        return t[0]
    return None


def schedule_of(path: Path) -> str:
    return path.parts[len(path.parts) - 4]


def walk_owned(node, fn, owner=None):
    """Like walk, but tracks the nearest enclosing version node's @id.

    The scope of a subordinate resource is the RatePlanVersion or
    RatePlanModifierVersion that contains it, NOT the directory it happens to
    sit in. Those differ: CPAU's e-1 filing inlines the whole `cpau:e-hra`
    modifier subtree, and PG&E inlines a per-plan PCIA modifier into five base
    filings. Scoping by directory would rename `cpau:hra-price-25-75-gen-480-642`
    three different ways and mint three copies of one real modifier; scoping by
    owner renames it identically in all three and keeps it correctly shared.
    """
    if isinstance(node, dict):
        t = node_type(node)
        if t in VERSION_TYPES and isinstance(node.get("@id"), str):
            owner = node["@id"]
        fn(node, owner)
        for k, v in node.items():
            if k == "@context":
                continue
            walk_owned(v, fn, owner)
    elif isinstance(node, list):
        for v in node:
            walk_owned(v, fn, owner)


def scan():
    """Corpus-wide inventory. Returns (defs, types, owners) keyed by @id."""
    defs: dict[str, set[Path]] = defaultdict(set)
    types: dict[str, str | None] = {}
    owners: dict[str, set[str]] = defaultdict(set)
    for p in corpus.all_filing_jsonld():
        doc = json.loads(Path(p).read_text(encoding="utf-8"))

        def visit(d, own, _p=Path(p)):
            if "@id" in d and len(d) > 1:
                defs[d["@id"]].add(_p)
                t = node_type(d)
                if t is not None:
                    types.setdefault(d["@id"], t)
                if own is not None:
                    owners[d["@id"]].add(own)

        walk_owned(doc, visit)
    return defs, types, owners


def ambiguous(defs, types, owners) -> set[str]:
    """@ids claimed by more than one owning version, excluding the identity layer.

    The test is the OWNER count, not the schedule count. Those come apart in
    both directions and only the owner test is right:

      - One owner, several schedules: an inlined modifier. `cpau:e-hra-...`
        subordinates appear under e-1, e-1-tou and e-hra but are one resource,
        and sharing the @id is correct.
      - Several owners, one schedule: two versions of a schedule each minting
        `pge:price-pcia`. The merged graph then holds one Price with two unit
        prices, which is the same defect as the cross-schedule case and is what
        this section of LAYOUT.md originally described.
    """
    out = set()
    for iri in defs:
        t = types.get(iri)
        if t in IDENTITY_TYPES or t in KEEP_SHARED_TYPES:
            continue
        if len(owners.get(iri, ())) > 1:
            out.add(iri)
    return out


def new_iri(iri: str, owner: str) -> str:
    """`<util>:<desc>` -> `<util>:<owner-local>-<desc>`, per LAYOUT.md section 6.

    The owner's local part is already the documented `<schedule>-<date>` form
    (`pge:e-elec-2026-03-27`), so prefixing with it yields exactly the documented
    shape `pge:e-elec-2026-03-27-price-public-purpose`. Taking the scope from the
    owner rather than from the path is what makes an inlined modifier's children
    come out identical in every file that inlines them.
    """
    if ":" not in iri:
        raise Rescope(f"not a CURIE: {iri}")
    prefix, desc = iri.split(":", 1)
    oprefix, olocal = owner.split(":", 1)
    if oprefix != prefix:
        raise Rescope(f"{iri} is owned by {owner}, which is in a different prefix")

    # The owner supplies the date; a second copy in the descriptor is noise.
    desc = DATE_RE.sub("", desc)
    desc = re.sub(r"-{2,}", "-", desc).strip("-")

    # Drop a leading descriptor token the owner already states, so that
    # `hra-price-...` under owner `e-hra-2023-01-01` does not become
    # `e-hra-2023-01-01-hra-price-...`. Only an exact whole-token match counts,
    # and build_map re-checks for collisions afterwards either way.
    otokens = set(olocal.split("-"))
    parts = desc.split("-")
    while len(parts) > 1 and parts[0] in otokens:
        parts.pop(0)
    desc = "-".join(parts)
    if not desc:
        raise Rescope(f"descriptor empty after normalising: {iri}")

    return f"{prefix}:{olocal}-{desc}"


def build_map(paths, amb, owners) -> dict[Path, dict[str, str]]:
    """Per-file rename map. The same @id maps differently in different files
    whenever it has different owners there, which is the entire point, so the
    map cannot be global."""
    out: dict[Path, dict[str, str]] = {}
    for p in paths:
        doc = json.loads(p.read_text(encoding="utf-8"))
        seen: set[str] = set()
        own_here: dict[str, set[str]] = defaultdict(set)

        def visit(d, own):
            i = d.get("@id")
            if isinstance(i, str):
                seen.add(i)
                if len(d) > 1 and own is not None:
                    own_here[i].add(own)

        walk_owned(doc, visit)

        m: dict[str, str] = {}
        for i in sorted(seen & amb):
            here = own_here.get(i, set())
            # A file that only REFERENCES an ambiguous @id has to adopt whatever
            # name its definition takes, so the scope comes from the corpus-wide
            # owner set. With more than one owner the reference genuinely does
            # not determine a referent, which is the defect itself and not
            # something this script may guess at.
            o = here or owners.get(i, set())
            if len(o) > 1 and not here:
                # A referencing-only file with several candidate owners: the
                # filing's own directory names which one it means. The PG&E
                # E-TOU-C baseline-tier modifier sits in e-tou-c/2026-03-01 and
                # makes 120 bare appliesInSeason references to seasons it does
                # not define; those mean E-TOU-C's seasons, not EV2's.
                sched = schedule_of(p)
                date = p.parent.name
                want = f"{i.split(':', 1)[0]}:{sched}-{date}"
                if want in o:
                    o = {want}
            if len(o) != 1:
                where = "defines" if here else "only references"
                raise Rescope(
                    f"{p.name} {where} {i}, which has {len(o)} owning versions "
                    f"({sorted(o)[:4]}{'...' if len(o) > 4 else ''}); no scope is "
                    f"determined. Either the type is genuinely utility-level and "
                    f"belongs in KEEP_SHARED_TYPES, or the reference is ambiguous "
                    f"and the filing must say which one it means.")
            m[i] = new_iri(i, next(iter(o)))

        collisions = [k for k, v in m.items() if v in seen and v != k]
        if collisions:
            raise Rescope(f"{p.name}: rename target already exists: {collisions}")
        if len(set(m.values())) != len(m):
            dupes = [v for v in m.values() if list(m.values()).count(v) > 1]
            raise Rescope(f"{p.name}: two @ids collapse onto one new @id: {sorted(set(dupes))[:3]}")
        if m:
            out[p] = m
    return out


def apply_map(doc, m: dict[str, str]) -> int:
    n = 0

    def visit(d):
        nonlocal n
        v = d.get("@id")
        if isinstance(v, str) and v in m:
            d["@id"] = m[v]
            n += 1

    walk(doc, visit)
    return n


def stray_string_refs(doc, m) -> list[str]:
    """Any renamed @id still appearing as a bare string value somewhere.

    A reference site that is a plain string rather than {"@id": ...} would be
    missed by apply_map and left dangling, so it is an error rather than a
    warning: the file would validate and mean the wrong thing.
    """
    hits: list[str] = []

    def visit(d):
        for k, v in d.items():
            if k in ("@context", "@id"):
                continue
            if isinstance(v, str) and v in m:
                hits.append(f"{k} = {v}")
            elif isinstance(v, list):
                hits.extend(f"{k}[] = {x}" for x in v if isinstance(x, str) and x in m)

    walk(doc, visit)
    return hits


def expand(iri: str, ctx: dict) -> str:
    prefix, _, local = iri.partition(":")
    base = ctx.get(prefix)
    return f"{base}{local}" if isinstance(base, str) else iri


def self_check(before_path: Path, after_text: str, m: dict[str, str]) -> list[str]:
    """Apply the rename map to the BEFORE graph, then require isomorphism.

    Passes only if the file changed by exactly this rename. A predicate-level
    check cannot see a rename at all and would pass on arbitrary damage.
    """
    ctx = json.loads(before_path.read_text(encoding="utf-8")).get("@context", {})
    if not isinstance(ctx, dict):
        return ["@context is not an inline object; cannot expand CURIEs to check"]
    full = {expand(k, ctx): expand(v, ctx) for k, v in m.items()}

    b = rdflib.Graph()
    b.parse(before_path, format="json-ld")
    renamed = rdflib.Graph()
    for s, p, o in b:
        if isinstance(s, rdflib.URIRef) and str(s) in full:
            s = rdflib.URIRef(full[str(s)])
        if isinstance(o, rdflib.URIRef) and str(o) in full:
            o = rdflib.URIRef(full[str(o)])
        renamed.add((s, p, o))

    a = rdflib.Graph()
    a.parse(data=after_text, format="json-ld")

    if to_isomorphic(renamed) == to_isomorphic(a):
        return []
    only_expected = set(renamed) - set(a)
    only_actual = set(a) - set(renamed)
    msgs = [f"graph is not the rename of the original: "
            f"{len(only_expected)} triple(s) missing, {len(only_actual)} unexpected"]
    for t in list(only_expected)[:3]:
        msgs.append(f"    missing:    {t}")
    for t in list(only_actual)[:3]:
        msgs.append(f"    unexpected: {t}")
    return msgs


def rescope_file(path: Path, m: dict[str, str], dry_run: bool) -> bool:
    doc = json.loads(path.read_text(encoding="utf-8"))
    stray = stray_string_refs(doc, m)
    if stray:
        print(f"  REFUSED {path.name}: @id used as a bare string value: {stray[:3]}",
              file=sys.stderr)
        return False

    n = apply_map(doc, m)
    if n == 0:
        print(f"  {path.name}: already scoped")
        return True

    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    problems = self_check(path, text, m)
    if problems:
        print(f"  REFUSED {path.name}:", file=sys.stderr)
        for p in problems:
            print(f"    {p}", file=sys.stderr)
        return False

    if dry_run:
        print(f"  {path.name}: would rewrite {n} @id occurrence(s), "
              f"{len(m)} distinct @id(s)")
    else:
        path.write_text(text, encoding="utf-8")
        print(f"  {path.name}: rewrote {n} @id occurrence(s), {len(m)} distinct @id(s)")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--utility", help="restrict the rewrite to one utility")
    ap.add_argument("--plan", action="store_true",
                    help="print the rename map and write nothing")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    defs, types, owners = scan()
    corpus.require_nonempty(list(defs), "identified nodes")
    amb = ambiguous(defs, types, owners)
    if not amb:
        print("No ambiguous subordinate @ids. Nothing to do.")
        return 0

    paths = sorted({p for i in amb for p in defs[i]})
    if args.utility:
        paths = [p for p in paths if f"/{args.utility}/" in str(p)]
        if not paths:
            print(f"REFUSED: no filings for utility {args.utility!r} define an "
                  f"ambiguous @id.", file=sys.stderr)
            return 3

    try:
        rename = build_map(paths, amb, owners)
    except Rescope as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3

    print(f"{len(amb)} ambiguous @id(s) corpus-wide; "
          f"{len(rename)} file(s) in this run.\n")

    if args.plan:
        for p in sorted(rename):
            print(f"{p}")
            for old, new in sorted(rename[p].items()):
                print(f"    {old}\n      -> {new}")
        return 0

    ok = True
    for p in sorted(rename):
        ok &= rescope_file(p, rename[p], args.dry_run)
    if not ok:
        print("\nOne or more files were refused; nothing partial was written "
              "for them.", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
