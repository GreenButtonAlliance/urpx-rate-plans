#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Author the CARE and FERA discountable subtotals and their discount Prices.

The headline percentage discount is the largest single thing this corpus did not
model: SCE CARE at 32.5 percent, SDG&E CARE at 35 and SDG&E FERA at 18, together
roughly 2.28M customers. Only the line-item exemptions were modeled, so a consumer
computing a CARE customer's bill got the undiscounted one.

THE SHAPE. A urpx:PriceSummary in the BASE PLAN filing, hung off the PriceSet
holding most of its line items, whose urpx:includesPrice names the discountable
ones. A urpx:Price in the MODIFIER filing carrying urpx:multiplier (the negative
discount rate) and urpx:basedOnPrice naming EVERY candidate base summary. The
summary belongs with the prices it sums; the discount belongs to the program.

MULTIPLE basedOnPrice VALUES ARE DISJUNCTIVE: candidate bases, exactly one of
which is present in the documents a caller passes. Composing the modifier with
base X, the summaries of the other eight are simply absent and the one present is
used. This is what lets ONE discount Price serve nine base plans without reusing
an @id or minting a discount per plan. Zero resolvable candidates is still an
error, so a typo stays loud.

ONE SUMMARY PER PLAN, NOT PER TOU PERIOD. Summary members are gated to the instant
being resolved by the same season, month and TOU predicates that gate a tier, so a
summary naming every discountable line item is correct in every period: only the
members in effect are summed.

WHAT EACH TARIFF EXCLUDES, which is why the member lists differ:
  SCE (D-CARE Sheet 1): the discount applies "prior to the application of the
    PUCRF and any applicable user fees, taxes, and late payment charges", so only
    PUCRF and the California Climate Credit fall outside. The Climate Credit is
    excluded because it "is applied after the calculation of city and county
    utility users' taxes", and the discount is applied before them.
  SDG&E CARE (E-CARE Sheet 1): "less any applicable exemptions, minimum bill
    amount and base services charge".
  SDG&E FERA (Schedule FERA Sheet 1): "less any minimum bill amount or base
    services charge". FERA grants no exemptions, so it pays the DWR Bond Charge
    and the Wildfire Fund NBC and CARE does not. Same plan, different members.
  PG&E CARE (D-CARE Sheet 1): "total bundled volumetric charges less charges from
    which they are exempt (Wildfire Fund Charge, Wildfire Hardening Charge,
    Recovery Bond Charge, Recovery Bond Credit, and the CARE surcharge portion of
    the public purpose program charge ...) ... (except for the California Climate
    Credit, which will not be discounted)". The base services charge is not
    volumetric. No base publishes the CARE surcharge portion, so the PPP charge
    stays whole in the subtotal.
  PG&E FERA (E-FERA Sheet 1): "total bundled volumetric charges", "after FERA
    customers are exempted from the Wildfire Hardening Charge, Recovery Bond
    Charge, and the Recovery Bond Credit". FERA pays the Wildfire Fund Charge.

PG&E base filings inline a vintage-PCIA modifier, so members are read from the
urpx:RatePlanVersion alone, and only the current version of each plan gets a
subtotal (--current-only), since a superseded version takes part in no scenario
cost model.

Usage:
    python3 dev/author_care_summaries.py [--utility sdge] [--current-only] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

# Excluded from both programs: the fixed charge each tariff carves out by name.
# sdge:ev-tou prices a Minimum Bill where the other eight price a Base Services
# Charge, and both tariffs name both.
EXCLUDE_BOTH = re.compile(r"(base-services-charge|minimum-bill)")
# Excluded from CARE only, as "any applicable exemptions": the charges a CARE
# customer does not pay. FERA grants no exemptions, so these stay in its base.
EXCLUDE_CARE_ONLY = re.compile(r"(dwr-bc|wf-nbc)")
# Excluded from both on SCE: named by the tariff as applied after the discount.
EXCLUDE_SCE = re.compile(r"(price-pucrf|price-climate-credit)")
# PG&E: the base services charge (one Price per income tier) and the Climate
# Credit for both programs; the charges each program is exempt from.
EXCLUDE_PGE_BOTH = re.compile(r"(price-base-charge|price-climate-credit)")
EXCLUDE_PGE = {
    "care": re.compile(r"(price-wildfire-fund|price-wildfire-hardening|price-recovery-bond)"),
    "fera": re.compile(r"(price-wildfire-hardening|price-recovery-bond)"),
}
# The directory each program's modifier is filed under.
MODIFIER_DIRS = {"pge": {"care": "d-care", "fera": "e-fera"}}

PROGRAMS = {
    "care": {"sdge": "-0.35", "sce": "-0.325", "pge": "-0.35"},
    "fera": {"sdge": "-0.18", "sce": "-0.18", "pge": "-0.18"},
}


def node_type(d):
    t = d.get("@type")
    if isinstance(t, str):
        return t
    if isinstance(t, list) and t:
        return t[0]
    return None


def walk(node, fn, ctx=None):
    if isinstance(node, dict):
        fn(node, ctx)
        t = node_type(node)
        here = node.get("@id") if t in ("urpx:PriceSet", "urpx:PriceSetAlternative") else ctx
        for k, v in node.items():
            if k == "@context":
                continue
            walk(v, fn, here)
    elif isinstance(node, list):
        for v in node:
            walk(v, fn, ctx)


def plan_members(path: Path, utility: str):
    """Return (care_members, fera_members, host_price_set_id)."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    prices: list[tuple[str, str | None]] = []
    counts: Counter = Counter()

    def visit(d, ps):
        if node_type(d) == "urpx:Price" and d.get("@id"):
            prices.append((d["@id"], ps))
            counts[ps] += 1

    if utility == "pge":
        # Only the base version's own Prices: the filing also inlines a
        # vintage-PCIA RatePlanModifierVersion.
        versions = []
        walk(doc, lambda d, _c: versions.append(d)
             if node_type(d) == "urpx:RatePlanVersion" else None)
        if len(versions) != 1:
            raise SystemExit(f"REFUSED: {path.name} has {len(versions)} RatePlanVersions")
        walk(versions[0], visit)
    else:
        walk(doc, visit)
    if not prices:
        raise SystemExit(f"REFUSED: {path.name} has no Price nodes")

    def keep(pid, program):
        if EXCLUDE_BOTH.search(pid):
            return False
        if utility == "sce" and EXCLUDE_SCE.search(pid):
            return False
        if program == "care" and utility == "sdge" and EXCLUDE_CARE_ONLY.search(pid):
            return False
        if utility == "pge" and (EXCLUDE_PGE_BOTH.search(pid)
                                 or EXCLUDE_PGE[program].search(pid)):
            return False
        return True

    care = [p for p, _ in prices if keep(p, "care")]
    fera = [p for p, _ in prices if keep(p, "fera")]
    host = counts.most_common(1)[0][0]
    if host is None:
        raise SystemExit(f"REFUSED: {path.name} has no PriceSet to host a summary")
    return care, fera, host, doc


def summary_id(plan_slug: str, date: str, program: str) -> str:
    return f"{plan_slug}-{date}-summary-{program}-discountable"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--utility", default="sdge")
    ap.add_argument("--current-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    u = args.utility

    bases = sorted(
        p for p in corpus.all_filing_jsonld()
        if f"/{u}/" in str(p) and "/rate-plan_" in str(p)
    )
    # Only plans the modifiers actually apply to.
    applicable: set[str] = set()
    for prog in ("care", "fera"):
        mod = MODIFIER_DIRS.get(u, {}).get(prog, prog)
        for m in corpus.all_filing_jsonld():
            if f"/{u}/electricity/{mod}/" not in str(m):
                continue
            doc = json.loads(Path(m).read_text(encoding="utf-8"))

            def visit(d, _ctx):
                v = d.get("urpx:applicableToRatePlan")
                for y in (v if isinstance(v, list) else [v]):
                    if isinstance(y, dict) and y.get("@id"):
                        applicable.add(y["@id"])

            walk(doc, visit)

    latest: dict[str, str] = {}
    for b in bases:
        slug, date = corpus.parse_filing_path(Path(b))[1:]
        latest[slug] = max(latest.get(slug, date), date)

    made: dict[str, list[str]] = {"care": [], "fera": []}
    for b in bases:
        path = Path(b)
        slug = corpus.parse_filing_path(path)[1]
        if f"{u}:{slug}" not in applicable:
            continue
        date = path.parent.name
        if args.current_only and date != latest[slug]:
            continue
        care, fera, host, doc = plan_members(path, u)

        pfx = f"{u}:{slug}"
        sums = []

        # SCE excludes the same two items for both programs (the PUCRF and the
        # Climate Credit, both applied after the discount), so CARE and FERA have
        # identical members and one subtotal serves both, with the programs
        # differing only in multiplier. SDG&E carves out the fixed charge and,
        # for CARE alone, the exemptions, so there the member lists genuinely
        # differ and two summaries are required.
        if care == fera:
            sid = summary_id(pfx, date, "discountable")
            sums.append({
                "@type": "urpx:PriceSummary",
                "@id": sid,
                "urpx:name": _name(u, slug, "shared", len(care)),
                "urpx:includesPrice": [{"@id": m} for m in care],
            })
            made["care"].append(sid)
            made["fera"].append(sid)
            placed = [0]

            def place_shared(d, _ctx):
                if d.get("@id") == host:
                    d["urpx:hasPriceSummary"] = sums
                    placed[0] += 1

            walk(doc, place_shared)
            if placed[0] != 1:
                raise SystemExit(f"REFUSED: {path.name} host {host} matched {placed[0]}")
            if not args.dry_run:
                with path.open("w", encoding="utf-8") as fh:
                    json.dump(doc, fh, indent=2, ensure_ascii=False)
                    fh.write("\n")
            print(f"  {slug:12s} {date}  shared subtotal {len(care):3d} members "
                  f"-> {host.split(':')[-1]}")
            continue

        for program, members in (("care", care), ("fera", fera)):
            if len(members) < 2:
                print(f"  SKIP {slug} {program}: only {len(members)} member(s); "
                      f"includesPrice is sh:minCount 2, so reference the Price "
                      f"directly instead of wrapping it", file=sys.stderr)
                continue
            sid = summary_id(pfx, date, program)
            sums.append({
                "@type": "urpx:PriceSummary",
                "@id": sid,
                "urpx:name": _name(u, slug, program, len(members)),
                "urpx:includesPrice": [{"@id": m} for m in members],
            })
            made[program].append(sid)

        placed = [0]

        def place(d, _ctx):
            if d.get("@id") == host:
                d["urpx:hasPriceSummary"] = sums
                placed[0] += 1

        walk(doc, place)
        if placed[0] != 1:
            raise SystemExit(f"REFUSED: {path.name} host PriceSet {host} matched "
                             f"{placed[0]} times")
        if not args.dry_run:
            with path.open("w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
        print(f"  {slug:10s} CARE {len(care):3d}  FERA {len(fera):3d}  -> {host.split(':')[-1]}")

    print(f"\n{len(made['care'])} CARE and {len(made['fera'])} FERA summaries "
          f"{'would be ' if args.dry_run else ''}written for {u}")
    out = REPO / "dev" / f"care-summaries-{u}.json"
    if not args.dry_run:
        out.write_text(json.dumps(made, indent=2) + "\n", encoding="utf-8")
        print(f"candidate lists written to {out.relative_to(REPO)}")
    return 0


def _name(u: str, slug: str, program: str, n: int) -> str:
    if program == "shared":
        return (f"Discountable subtotal for {slug.upper()}. The {n} bill components "
                f"the CARE and FERA percentage discounts both apply to. Schedule "
                f"D-CARE Sheet 1 applies the discount before the PUCRF, user fees, "
                f"taxes and late payment charges, so the PUCRF is excluded, and the "
                f"California Climate Credit is excluded because Special Condition 12 "
                f"applies it after those taxes. Both programs discount the same "
                f"components and differ only in rate, so one subtotal serves both.")
    p = program.upper()
    if u == "pge" and program == "care":
        return (f"CARE-discountable subtotal for {slug.upper()}. The {n} volumetric "
                f"charges the Schedule D-CARE percentage discount applies to: "
                f"\"total bundled volumetric charges less charges from which they "
                f"are exempt\" (Sheet 1). Excludes the Wildfire Fund Charge, the "
                f"Wildfire Hardening Charge, the Recovery Bond Charge and the "
                f"Recovery Bond Credit, and the base services charge, which is not "
                f"volumetric. The Public Purpose Programs charge is included whole: "
                f"Sheet 1 also exempts its CARE surcharge portion, which the base "
                f"schedule does not publish.")
    if u == "pge":
        return (f"FERA-discountable subtotal for {slug.upper()}. The {n} volumetric "
                f"charges the Schedule E-FERA percentage discount applies to: "
                f"\"total bundled volumetric charges\", generation included, "
                f"\"after FERA customers are exempted from the Wildfire Hardening "
                f"Charge, Recovery Bond Charge, and the Recovery Bond Credit\" "
                f"(Sheet 1). Excludes those three and the base services charge, "
                f"which is not volumetric. Unlike CARE, the Wildfire Fund Charge is "
                f"inside this subtotal.")
    if u == "sce":
        return (f"{p}-discountable subtotal for {slug.upper()}. The {n} bill "
                f"components the {p} percentage discount applies to. Schedule "
                f"D-CARE Sheet 1 applies the discount before the PUCRF, user fees, "
                f"taxes and late payment charges, so the PUCRF is excluded; the "
                f"California Climate Credit is excluded because it is applied "
                f"after those taxes and so falls outside the discounted subtotal.")
    if program == "care":
        return (f"CARE-discountable subtotal for {slug.upper()}. The {n} bill "
                f"components the CARE percentage discount applies to, which "
                f"Schedule E-CARE Sheet 1 defines as the bill less any applicable "
                f"exemptions, minimum bill amount and base services charge. "
                f"Excludes the fixed charge, and excludes the DWR Bond Charge and "
                f"the California Wildfire Fund Non-Bypassable Charge because a "
                f"CARE customer is exempt from both.")
    return (f"FERA-discountable subtotal for {slug.upper()}. The {n} bill "
            f"components the FERA percentage discount applies to, which Schedule "
            f"FERA Sheet 1 defines as the bill less any minimum bill amount or "
            f"base services charge. Excludes the fixed charge only. Unlike CARE, "
            f"FERA grants no charge exemptions, so the DWR Bond Charge and the "
            f"California Wildfire Fund Non-Bypassable Charge are inside this "
            f"subtotal.")


if __name__ == "__main__":
    raise SystemExit(main())
