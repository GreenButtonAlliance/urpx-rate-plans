#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Check that each CARE/FERA discountable subtotal still names the right prices.

The percentage discount is computed as a multiplier over the members a
urpx:PriceSummary names. Nothing else in the repository notices if those members
drift out of step with the plan they summarise, and the failure is quiet in the
worst way: adding a price to a base plan without adding it to the subtotal makes
the modeled discount too small, and every gate stays green, because the summary
is still internally valid and still resolves.

So this re-derives each subtotal from the tariff rule and compares.

THE RULES, each traceable to a sentence in the source schedule:
  SCE, Schedule D-CARE Sheet 1: the discount applies "prior to the application of
    the Public Utilities Commission Reimbursement Fee (PUCRF) and any applicable
    user fees, taxes, and late payment charges". Of those only the PUCRF exists
    in this corpus. The California Climate Credit is also outside, because
    Special Condition 12 applies it "after the calculation of city and county
    utility users' taxes" and the discount is applied before them. Everything
    else the plan prices is inside, and CARE and FERA share one subtotal.
  SDG&E CARE, Schedule E-CARE Sheet 1: the bill "less any applicable exemptions,
    minimum bill amount and base services charge".
  SDG&E FERA, Schedule FERA Sheet 1: "less any minimum bill amount or base
    services charge". FERA receives no exemptions, so it pays the DWR Bond Charge
    and the Wildfire Fund NBC that CARE does not, and the two programs need
    different member lists on the same plan.

Also checks that every discount Price still names EVERY candidate subtotal. Those
are read disjunctively, so a missing candidate does not fail validation; it makes
the modifier silently unvaluable against that one base plan.

Exit: 0 clean, 1 drift, 3 refused.

Usage:
    python3 dev/lint_discount_summaries.py [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

EXCLUDE_FIXED = re.compile(r"(base-services-charge|minimum-bill)")
EXCLUDE_EXEMPT = re.compile(r"(dwr-bc|wf-nbc)")
EXCLUDE_SCE = re.compile(r"(price-pucrf|price-climate-credit)")


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


def utility_of(path: Path) -> str:
    """Utility segment, located by the `us` root rather than a fixed index.

    corpus.all_filing_jsonld() yields ABSOLUTE paths, so a positional index reads
    a directory from the developer's home path instead of the utility, which
    silently disables every utility-specific rule and makes this linter report
    the whole corpus as broken.
    """
    parts = path.parts
    i = parts.index("us")
    return parts[i + 2]


def expected(path: Path, utility: str, program: str) -> list[str]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []

    def visit(d):
        if node_type(d) != "urpx:Price" or not d.get("@id"):
            return
        pid = d["@id"]
        if EXCLUDE_FIXED.search(pid):
            return
        if utility == "sce" and EXCLUDE_SCE.search(pid):
            return
        if utility == "sdge" and program == "care" and EXCLUDE_EXEMPT.search(pid):
            return
        out.append(pid)

    walk(doc, visit)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    files = corpus.all_filing_jsonld()
    corpus.require_nonempty(files, "rate-plan filings")

    summaries: dict[str, tuple[Path, list[str]]] = {}
    candidates: dict[str, list[str]] = {}
    for f in files:
        p = Path(f)
        doc = json.loads(p.read_text(encoding="utf-8"))

        def visit(d, _p=p):
            t = node_type(d)
            if t == "urpx:PriceSummary" and d.get("@id"):
                mem = d.get("urpx:includesPrice") or []
                summaries[d["@id"]] = (
                    _p, [m["@id"] for m in (mem if isinstance(mem, list) else [mem])])
            if t == "urpx:Price" and "urpx:multiplier" in d and d.get("@id"):
                b = d.get("urpx:basedOnPrice") or []
                candidates[d["@id"]] = [
                    x["@id"] for x in (b if isinstance(b, list) else [b])]

        walk(doc, visit)

    if not summaries:
        print("REFUSED: no urpx:PriceSummary anywhere; this linter would pass "
              "vacuously.", file=sys.stderr)
        return 3

    problems: list[dict] = []
    for sid, (path, members) in sorted(summaries.items()):
        utility = utility_of(path)
        program = ("care" if "-care-" in sid else
                   "fera" if "-fera-" in sid else "shared")
        want = expected(path, utility, "care" if program == "shared" else program)
        missing = sorted(set(want) - set(members))
        extra = sorted(set(members) - set(want))
        if missing or extra:
            problems.append({"summary": sid, "file": str(path.relative_to(REPO)),
                             "missing": missing, "unexpected": extra})

    all_sums = set(summaries)
    for pid, cands in sorted(candidates.items()):
        util = pid.split(":")[0]
        # A CARE discount names the CARE subtotals, a FERA discount the FERA ones,
        # and where a utility publishes one shared subtotal both name it. Demanding
        # every summary of the utility would require CARE to name FERA's.
        prog = "care" if "care-price" in pid or ":care-" in pid else "fera"
        want = {
            s for s in all_sums
            if s.split(":")[0] == util
            and (f"-{prog}-discountable" in s or s.endswith("-summary-discountable"))
        }
        gap = sorted(want - set(cands))
        if gap:
            problems.append({"discount": pid, "missing_candidates": gap})

    if args.json:
        print(json.dumps(problems, indent=2))
        return 1 if problems else 0

    if not problems:
        print(f"discount subtotals: clean ({len(summaries)} summaries, "
              f"{len(candidates)} discount prices)")
        return 0

    print(f"discount subtotals: {len(problems)} problem(s)\n")
    for p in problems:
        if "summary" in p:
            print(f"  {p['summary']}")
            print(f"      in {p['file']}")
            for m in p["missing"]:
                print(f"      MISSING from the subtotal: {m}")
            for e in p["unexpected"]:
                print(f"      should NOT be in the subtotal: {e}")
        else:
            print(f"  {p['discount']} does not name every candidate subtotal")
            for m in p["missing_candidates"]:
                print(f"      MISSING candidate: {m}")
        print()
    print("A price missing from a subtotal makes the modeled discount too small,\n"
          "and every other check stays green. See LAYOUT.md and the tariff\n"
          "sentences quoted at the top of this file.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
