#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Make an inlined copy of a node agree with its authoritative definition.

LAYOUT.md section 2 lets a filing inline a subtree that another filing also
carries, and rests on those copies describing the same thing. Some do not, and
because the disagreements produce no SHACL violation the gate cannot see them:
the merged graph just takes the union and reports conformance.

Not every difference between copies is a defect. A urpx:RatePlan legitimately
nests a different urpx:hasRatePlanVersion in each of its filings, and a modifier
version legitimately lists a different urpx:applicableToRatePlanVersion in each
host, because those ARE per-filing facts and the union is the intended reading.
This script only touches properties whose value is a fact about the shared thing
itself, where two answers is a contradiction rather than a union.

AUTHORITY is the filing that owns the version: the one whose directory schedule
and date match the version's own @id. `cpau:e-hra-2023-01-01` is authoritative in
us/ca/cpau/electricity/e-hra/versions/2023-01-01/, and the copies inlined into
e-1 and e-1-tou follow it.

Usage:
    python3 dev/normalize_copies.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

VERSION_TYPES = {"urpx:RatePlanVersion", "urpx:RatePlanModifierVersion"}

# Properties that describe the shared thing, so all copies must agree.
#
#   hasDataSourceReference  names the document the version came from. One
#                           version cannot have been retrieved from two places
#                           on two dates; a filing re-verifying the PDF records
#                           that in its own tariff.toml, which is per-filing
#                           provenance and stays there.
#   hasIdentity             the utility's own identity block.
#   hasDynamicPricing       how a price is updated. A price that is reset
#                           annually by council action is that kind of price
#                           wherever it is serialized, so a copy omitting it
#                           shows a materially incomplete picture of a price
#                           whose whole point is that it moves.
#   applicableToRatePlan    which base plans a modifier can attach to. That is
#                           intrinsic to the modifier, not to the filing that
#                           bundles it: a modifier does not become compatible
#                           with fewer plans by being inlined somewhere. Note
#                           this is NOT applicableToRatePlanVersion, which IS a
#                           per-filing fact and stays out, per the note above.
#                           Added because dev/scenario_cost_models.py already refuses
#                           when copies disagree on this property while this
#                           script did not check it, so two tools in this repo
#                           answered the same question differently.
# hasModifierOptions and hasModifierVersionOptions are DELIBERATELY NOT here,
# and the reason is a modelling question this script must not settle by
# overwriting. cpau:e-1-2025-07-01 lists one option in its own July filing and
# three in the September one, and BOTH ARE CORRECT FOR THEIR OWN DATE:
# cpau:e-eec-1 and cpau:e-nse-1 are themselves 2025-09-01 versions and did not
# exist in July. So the corpus models "same base rates, more modifiers available
# later" by reusing one version @id across two filings, which makes the option
# list time-varying while the @id is not. Aligning to the authority would delete
# the September availability. The defect is upstream of the copy disagreement:
# either that version needs its own @id in the later filing, or the option list
# is a per-filing fact like applicableToRatePlanVersion. Tracked; not decided
# here.
SHARED_PROPERTIES = ("urpx:hasDataSourceReference", "urpx:hasIdentity",
                     "urpx:hasDynamicPricing", "urpx:applicableToRatePlan")


def node_type(d):
    t = d.get("@type")
    if isinstance(t, str):
        return t
    if isinstance(t, list) and t:
        return t[0]
    return None


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


def prefixes_used(value) -> set[str]:
    """Every CURIE prefix appearing as a key or an @id/@type inside `value`."""
    out: set[str] = set()

    def curie(s):
        if isinstance(s, str) and ":" in s and not s.startswith("http"):
            head = s.split(":", 1)[0]
            if head and not head.startswith("@"):
                out.add(head)

    def visit(v):
        if isinstance(v, dict):
            for k, x in v.items():
                curie(k)
                if k in ("@id", "@type"):
                    for y in (x if isinstance(x, list) else [x]):
                        curie(y)
                visit(x)
        elif isinstance(v, list):
            for x in v:
                visit(x)

    visit(value)
    return out


def owns(path: Path, iri: str) -> bool:
    """Is this filing the authoritative home of `iri`?

    A version node's local part IS `<schedule>-<date>`, and since the scoping
    pass in LAYOUT.md section 6 every subordinate resource is named
    `<owning-version-local>-<descriptor>`. So the same prefix test answers both,
    and `cpau:e-hra-2023-01-01-price-25-75-gen-lt319` resolves to the e-hra
    filing rather than to whichever filing happens to inline it.

    Without the prefix case a subordinate node has no owner at all, and the
    majority rule then decides: three inlined copies lacking a property would
    outvote the one authoritative copy that has it, and the fix would run
    backwards, deleting from the original instead of filling in the copies.
    """
    local = iri.split(":", 1)[-1]
    schedule, date = corpus.parse_filing_path(path)[1:]
    stem = f"{schedule}-{date}"
    return local == stem or local.startswith(stem + "-")


def collect(files):
    """{iri: {path: node}} for every @id defined in more than one file."""
    seen: dict[str, dict[Path, dict]] = defaultdict(dict)
    for p in files:
        path = Path(p)
        doc = json.loads(path.read_text(encoding="utf-8"))

        def visit(d, _p=path):
            i = d.get("@id")
            if isinstance(i, str) and len(d) > 1:
                seen[i][_p] = d

        walk(doc, visit)
    return {k: v for k, v in seen.items() if len(v) > 1}


def authority(iri: str, copies: dict[Path, dict]) -> Path | None:
    """The owning filing, or the single copy carrying the property when the
    version has no filing of its own (an Organization has no version at all)."""
    owners = [p for p in copies if owns(p, iri)]
    return owners[0] if len(owners) == 1 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="gate mode: exit 1 if any shared property disagrees")
    args = ap.parse_args()

    files = corpus.all_filing_jsonld()
    corpus.require_nonempty(files, "rate-plan filings")

    multi = collect(files)
    edits: dict[Path, list[str]] = defaultdict(list)
    unresolved: list[str] = []

    for iri, copies in sorted(multi.items()):
        for prop in SHARED_PROPERTIES:
            # Absence counts as a value. One copy omitting a property the others
            # carry is the same contradiction as two copies disagreeing about
            # it, and it is the easier one to miss: the merged graph silently
            # takes the union, so the omission never surfaces anywhere.
            values = {p: json.dumps(n.get(prop), sort_keys=True)
                      for p, n in copies.items()}
            present = dict(copies)
            if len(set(values.values())) <= 1:
                continue

            src = authority(iri, copies)
            if src is None or prop not in copies[src]:
                # Prefer the majority reading only when it is unambiguous;
                # otherwise say so rather than pick one.
                counts: dict[str, int] = defaultdict(int)
                for v in values.values():
                    counts[v] += 1
                top = sorted(counts.items(), key=lambda kv: -kv[1])
                if len(top) > 1 and top[0][1] == top[1][1]:
                    unresolved.append(f"{iri}.{prop}: no owning filing and no "
                                      f"majority among {len(present)} copies")
                    continue
                canonical = json.loads(top[0][0])
            else:
                canonical = copies[src].get(prop)
            if canonical is None:
                unresolved.append(f"{iri}.{prop}: the owning filing omits it, "
                                  f"but {len(present)} copies disagree")
                continue

            for p, n in present.items():
                if json.dumps(n.get(prop), sort_keys=True) == json.dumps(canonical, sort_keys=True):
                    continue
                n[prop] = json.loads(json.dumps(canonical))
                edits[p].append(f"{iri}.{prop.split(':')[-1]}")

    if unresolved:
        print("REFUSED, no authoritative copy to follow:", file=sys.stderr)
        for u in unresolved:
            print(f"  {u}", file=sys.stderr)
        return 3

    if not edits:
        print("copies: clean (every shared property agrees across its copies)")
        return 0

    if args.check:
        # A gate, not a report. Reporting the disagreement and exiting 0 is the
        # shape of check this repo has shipped four times while it verified
        # nothing.
        n = sum(len(v) for v in edits.values())
        print(f"copies: {n} shared property value(s) disagree across their "
              f"copies, in {len(edits)} file(s)\n", file=sys.stderr)
        for pth in sorted(edits):
            print(f"    {pth.relative_to(REPO)}", file=sys.stderr)
            for e in edits[pth]:
                print(f"        {e}", file=sys.stderr)
        print("\nThese describe one shared thing, so two answers is a "
              "contradiction the\nmerged graph hides by taking the union. Fix:\n"
              "    python3 dev/normalize_copies.py --dry-run\n"
              "    python3 dev/normalize_copies.py\n"
              "See LAYOUT.md section 2.", file=sys.stderr)
        return 1

    # Every filing's @context, so a prefix a copied subtree needs can be
    # resolved from wherever the corpus already declares it.
    all_contexts = [json.loads(Path(f).read_text(encoding="utf-8")).get("@context", {})
                    for f in files]
    all_contexts = [c for c in all_contexts if isinstance(c, dict)]
    added: dict[Path, list[str]] = {}

    # One file holds many nodes, so rewrite each file once from its own parse.
    for p in sorted(edits):
        doc = json.loads(p.read_text(encoding="utf-8"))
        # iri -> {props}, not iri -> prop: a node with two corrected properties
        # would otherwise silently keep only the last one written.
        targets: dict[str, set[str]] = defaultdict(set)
        for e in edits[p]:
            iri, prop = e.rsplit(".", 1)
            targets[iri].add(f"urpx:{prop}")

        def fix(d):
            i = d.get("@id")
            if not (isinstance(i, str) and i in targets and len(d) > 1):
                return
            for prop in targets[i]:
                src = authority(i, multi[i])
                if src is not None:
                    canonical = multi[i][src].get(prop)
                else:
                    vals = [n.get(prop) for n in multi[i].values() if prop in n]
                    canonical = vals[0] if vals else None
                if canonical is not None:
                    d[prop] = json.loads(json.dumps(canonical))

        walk(doc, fix)

        # A copied subtree may use a prefix the destination never bound. The
        # baseline-tier modifier had no `skos` binding, so an OrganizationIdentifier
        # copied into it produced the literal predicate "skos:notation" instead of
        # the SKOS IRI, and tripped sh:closed. Carry the binding across with the
        # value, or refuse: writing a subtree the destination cannot express is
        # worse than leaving the copies disagreeing.
        ctx = doc.get("@context")
        if isinstance(ctx, dict):
            needed = set()
            for iri in targets:
                for prop in targets[iri]:
                    for n in multi[iri].values():
                        if prop in n:
                            needed |= prefixes_used({prop: n[prop]})
            missing = sorted(x for x in needed if x not in ctx)
            for prefix in missing:
                binding = next((c[prefix] for c in all_contexts
                                if isinstance(c.get(prefix), str)), None)
                if binding is None:
                    print(f"REFUSED: {p.name} needs a binding for {prefix!r} that "
                          f"no filing in the corpus declares", file=sys.stderr)
                    return 3
                ctx[prefix] = binding
                added.setdefault(p, []).append(f"@context += {prefix} -> {binding}")

        print(f"  {p.name}")
        for e in edits[p]:
            print(f"    {e}")
        for e in added.get(p, []):
            print(f"    {e}")
        if not args.dry_run:
            with p.open("w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2, ensure_ascii=False)
                fh.write("\n")

    verb = "would align" if args.dry_run else "aligned"
    print(f"\n{verb} {sum(len(v) for v in edits.values())} property value(s) "
          f"across {len(edits)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
