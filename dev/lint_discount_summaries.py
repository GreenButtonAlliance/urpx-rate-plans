#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Check that each CARE/FERA discountable subtotal names the right prices, names
each of them ONCE, and adds up to the number the tariff describes.

The percentage discount is computed as a multiplier over the members a
urpx:PriceSummary names. Nothing else in the repository notices if those members
drift out of step with the plan they summarize, and the failure is quiet in the
worst way: adding a price to a base plan without adding it to the subtotal makes
the modeled discount too small, and every gate stays green, because the summary
is still internally valid and still resolves.

So this re-derives each subtotal from the tariff rule and compares. Three checks,
each catching a different way the subtotal can be wrong:

  MEMBERSHIP   the right set of prices is named. Catches a charge left out.
  DEFINITIONS  no price definition is named twice within one summary. Catches a
               charge counted more than once.
  ARITHMETIC   the subtotal, and the discount taken from it, resolve to the
               numbers the tariff describes, at every TOU band. Reports those
               numbers. Also catches the one case DEFINITIONS structurally
               cannot see: two DIFFERENT definitions carrying the same
               touPeriodNumber, which group separately and so raise no
               duplicate, but leave one band charging twice and another not at
               all. That shows up as bands built from unequal numbers of
               definitions.

WHY THE SECOND AND THIRD EXIST. This file once compared membership and nothing
else, and a subtotal can name exactly the right set of PriceDefinitions while
naming one of them six times. Eight summaries did: sdge:ev-tou, sdge:ev-tou-2
and sdge:ev-tou-5 each carried one undifferentiated urpx:PriceDefinition for
TOU-varying transmission and distribution, and sdge:tou-dr2 one for TOU-varying
TRAC, with one urpx:Price per band hanging off it. The subtotal therefore
collected the same charge once per TOU period. sdge:ev-tou's CARE discount
resolved to -0.9255435 against an instant-correct -0.2999885, a 3.09x
overstatement, and drove the composed marginal rate to -0.0770735 per kWh.
Membership was clean throughout, because the right PriceDefinitions were all
named. Nothing here compared a number, so nothing noticed.

THE RULES, each traceable to a sentence in the source schedule:
  SCE, Schedule D-CARE Sheet 1: the discount applies "prior to the application of
    the Public Utilities Commission Reimbursement Fee (PUCRF) and any applicable
    user fees, taxes, and late payment charges". Of those only the PUCRF exists
    in this corpus. The California Climate Credit is also outside, because
    Special Condition 12 applies it "after the calculation of city and county
    utility users' taxes" and the discount is applied before them. Everything
    else the plan prices is inside, and CARE and FERA share one subtotal.
  SDG&E CARE, Schedule E-CARE Sheet 2 (Cal. P.U.C. Sheet 64350-E): "The line-item
    bill discounts will be applied to the total bill (less any applicable
    exemptions, minimum bill amount and base services charge) as calculated for
    bundled service customers." The CARE Surcharge is one of those exemptions,
    so the subtotal names each base's PPP net of the surcharge and leaves the
    surcharge Price out. That ordering reproduces every Total Effective CARE
    Rate the base schedules publish, e.g. DR Sheet 1 (0.41443 - 0.00864) x 0.65
    = 0.26376.
  SDG&E FERA, Schedule FERA Sheet 1: "a separate line-item bill discount of 18%
    applied to the total bill (less any minimum bill amount or base services
    charge) as calculated for bundled service customers." FERA receives no
    exemptions, so it pays the DWR Bond Charge and the Wildfire Fund NBC that
    CARE does not, and the two programs need different member lists on the same
    plan.
  PG&E CARE, Schedule D-CARE Sheet 1: "total bundled volumetric charges less
    charges from which they are exempt (Wildfire Fund Charge, Wildfire Hardening
    Charge, Recovery Bond Charge, Recovery Bond Credit, and the CARE surcharge
    portion of the public purpose program charge ...) ... (except for the
    California Climate Credit, which will not be discounted)". The base services
    charge is not volumetric. No base publishes the CARE surcharge portion, so
    the PPP charge is a member whole.
  PG&E FERA, Schedule E-FERA Sheet 1: "total bundled volumetric charges",
    "after FERA customers are exempted from the Wildfire Hardening Charge,
    Recovery Bond Charge, and the Recovery Bond Credit". FERA pays the Wildfire
    Fund Charge, so it is a FERA member and not a CARE one. A PG&E base filing
    also inlines a vintage-PCIA modifier, whose Prices are not the plan's and are
    no member of either subtotal.

  SCE GENERATION, every residential base's Rates table, footnote 2 ("Generation
    = The Generation rates are applicable only to Bundled Service Customers",
    Schedule D Sheet 2; "The Gen rates ..." on each Schedule TOU-D option's
    sheet) with Special Condition 4.b/4.c of Schedule D and 11.b/11.c of
    Schedule TOU-D, which bill Direct Access and CCA Service customers for
    Delivery Service and not SCE Generation. sce:da-crs and sce:cca-crs cancel
    it with multiplier -1 over a per-base subtotal whose @id ends
    "-summary-generation". Its members are exactly the base's Prices whose
    PriceDefinition carries urpx:billPortion urpx:supplyPortion: the Generation
    column and the DWR Energy Credit, which the same Special Condition provides
    to Bundled Service Customers. A discount naming one such subtotal must name
    every one of its utility.

Both utilities say TOTAL BILL. A bill carries each charge once, at the rate
applicable to the usage being billed, so a charge that varies by TOU period or
by service tier belongs in the subtotal once and not once per band. URPX says the
same thing about the property itself: urpx:includesPrice is documented as
"AGGREGATION semantics: References prices being summed into this summary
total/subtotal ... Explicit reference avoids double counting in billing
calculations", and urpx:PriceSummary as "Explicitly references included line
items to avoid double counting".

Also checks that every discount Price still names EVERY candidate subtotal. Those
are read disjunctively, so a missing candidate does not fail validation; it makes
the modifier silently unvaluable against that one base plan.

A multiplier Price whose candidates are line-item Prices rather than subtotals,
such as sdge:care's CARE Surcharge exemption (multiplier -1 over each base's
CARE Surcharge Price), is checked the same way at plan grain: every candidate
names a Price some base filing defines, no plan has two candidates, and, where
the candidates span more than one plan, every plan in the modifier's
urpx:applicableToRatePlan has one. A single-plan candidate set is a Price
scoped to that plan, as smud:nem1's per-plan credits are.

Exit: 0 clean, 1 drift, 3 refused.

Usage:
    python3 dev/lint_discount_summaries.py [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

EXCLUDE_FIXED = re.compile(r"(base-services-charge|minimum-bill)")
# The CARE Surcharge is split out of each SDG&E base's PPP charge as its own
# Price, so the summary can name the PPP net of it. Anchored, because the net
# Price's @id ends "-ppp-net-of-care-surcharge" and belongs in the subtotal.
EXCLUDE_EXEMPT = re.compile(r"(dwr-bc|wf-nbc|-price-udc-care-surcharge$)")
EXCLUDE_SCE = re.compile(r"(price-pucrf|price-climate-credit)")
EXCLUDE_PGE_BOTH = re.compile(r"(price-base-charge|price-climate-credit)")
EXCLUDE_PGE = {
    "care": re.compile(r"(price-wildfire-fund|price-wildfire-hardening|price-recovery-bond)"),
    "fera": re.compile(r"(price-wildfire-hardening|price-recovery-bond)"),
}
GENERATION = "-summary-generation"


class Refused(Exception):
    """Nothing to check, so a clean verdict would be vacuous."""

# Properties that distinguish two Prices sharing one PriceDefinition. Naming
# them is what lets the DEFINITIONS failure say WHY the two are not the same
# line item, which is the difference between a fixable report and a puzzle.
DISCRIMINATORS = ("urpx:touPeriodNumber", "urpx:serviceTierNumber")


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


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def ref_id(x):
    return x.get("@id") if isinstance(x, dict) else x


def rel(path: Path) -> str:
    """`path` relative to the repository, or whole when it lies outside it."""
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


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
        if utility == "pge" and (EXCLUDE_PGE_BOTH.search(pid)
                                 or EXCLUDE_PGE[program].search(pid)):
            return
        out.append(pid)

    if utility == "pge":
        # The base version only: the filing also inlines a modifier version.
        for v in versions_of(doc):
            walk(v, visit)
    else:
        walk(doc, visit)
    return out


def versions_of(doc) -> list[dict]:
    out: list[dict] = []
    walk(doc, lambda d: out.append(d)
         if node_type(d) == "urpx:RatePlanVersion" else None)
    return out


def expected_generation(path: Path) -> list[str]:
    """Prices whose PriceDefinition is billed as urpx:supplyPortion."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    pds: dict[str, dict] = {}
    prices: list[dict] = []

    def visit(d):
        t = node_type(d)
        if t == "urpx:PriceDefinition" and d.get("@id"):
            pds[d["@id"]] = d
        elif t == "urpx:Price" and d.get("@id"):
            prices.append(d)

    walk(doc, visit)
    return [p["@id"] for p in prices
            if ref_id((pds.get(ref_id(p.get("urpx:referencesPriceDefinition"))) or {})
                      .get("urpx:billPortion")) == "urpx:supplyPortion"]


class Filing:
    """The nodes of one filing, indexed the three ways the checks below need."""

    def __init__(self, path: Path):
        self.path = path
        self.doc = json.loads(path.read_text(encoding="utf-8"))
        self.prices: dict[str, dict] = {}
        self.pds: dict[str, dict] = {}
        self.summaries: dict[str, dict] = {}
        self.discounts: dict[str, dict] = {}
        self.bands: set[int] = set()
        self.plans: set[str] = set()        # urpx:forRatePlan of its base versions
        self.applicable: set[str] = set()   # urpx:applicableToRatePlan of its modifier versions

        def visit(d):
            t, i = node_type(d), d.get("@id")
            if t == "urpx:RatePlanVersion" and d.get("urpx:forRatePlan"):
                self.plans.add(ref_id(d["urpx:forRatePlan"]))
            elif t == "urpx:RatePlanModifierVersion":
                self.applicable.update(ref_id(x) for x in
                                       as_list(d.get("urpx:applicableToRatePlan")))
            if t == "urpx:Price" and i:
                self.prices[i] = d
                if "urpx:multiplier" in d:
                    self.discounts[i] = d
            elif t == "urpx:PriceDefinition" and i:
                self.pds[i] = d
            elif t == "urpx:PriceSummary" and i and d.get("urpx:includesPrice"):
                self.summaries[i] = d
            elif t == "urpx:TOUPeriod" and d.get("urpx:touPeriodNumber") is not None:
                self.bands.add(int(d["urpx:touPeriodNumber"]))

        walk(self.doc, visit)

    def pd_of(self, price_id: str):
        """The PriceDefinition a Price references, or None."""
        p = self.prices.get(price_id)
        if p is None:
            return None
        return ref_id(p.get("urpx:referencesPriceDefinition"))

    def members(self, summary_id: str) -> list[str]:
        mem = self.summaries[summary_id].get("urpx:includesPrice")
        return [m["@id"] for m in as_list(mem)]

    def band_of_member(self, member_id):
        """The TOU band gating a member: its own, else its PriceDefinition's.

        clj-urpx reads it in exactly that order (price-active-at-tou? then
        pd-active-at-tou?), and URPX permits urpx:touPeriodNumber on both. If
        this file read only the definition, a filing that put the band on the
        Price would go unnarrowed here while the resolver narrowed it, and the
        arithmetic below would describe a subtotal nobody computes.
        """
        n = (self.prices.get(member_id) or {}).get("urpx:touPeriodNumber")
        if n is None:
            n = (self.pds.get(self.pd_of(member_id)) or {}).get(
                "urpx:touPeriodNumber")
        return None if n is None else int(n)

    def discriminator_of_pd(self, pd_id, prop):
        """The value of `prop` on a member's PriceDefinition, or None."""
        pd = self.pds.get(pd_id)
        if pd is None:
            return None
        n = pd.get(prop)
        return None if n is None else int(n)

    def unnarrowed(self, members, prop):
        """Distinct values of `prop` among `members` PriceDefinitions.

        Two or more means a discriminator the band filter did not resolve, so
        several mutually exclusive variants of one charge are simultaneously in
        the subtotal.
        """
        if prop == "urpx:serviceTierNumber":
            vals = {self.tier_of(m) for m in members}
        else:
            vals = {self.discriminator_of_pd(self.pd_of(m), prop)
                    for m in members}
        return sorted(v for v in vals if v is not None) if len(
            {v for v in vals if v is not None}) > 1 else []

    def additive_plus_lowest_rung(self, members):
        """Every untiered member, plus the lowest rung of the tier ladder.

        urpx:serviceTierNumber marks a block-tier ladder, whose rungs are
        mutually exclusive per kWh; a bare member is an additive component. This
        mirrors clj-urpx's additive-plus-lowest-rung exactly, and it has to: if
        this file's idea of which members are live differs from the resolver's,
        its arithmetic describes a subtotal nobody computes. The tier number is
        read from the member Price first and then from its PriceDefinition,
        because this corpus puts it in the second place and URPX permits both.
        """
        tiered, bare = [], []
        for m in members:
            n = self.tier_of(m)
            (tiered if n is not None else bare).append(m)
        if tiered:
            bare.append(min(tiered, key=self.tier_of))
        return bare

    def tier_of(self, member_id):
        p = self.prices.get(member_id) or {}
        n = p.get("urpx:serviceTierNumber")
        if n is None:
            n = (self.pds.get(self.pd_of(member_id)) or {}).get(
                "urpx:serviceTierNumber")
        return None if n is None else int(n)

    def active_members(self, summary_id: str, band: int) -> list[str]:
        """Members in effect in `band`.

        A member whose PriceDefinition carries no urpx:touPeriodNumber applies in
        every band; one that carries a number applies only in that band. This is
        the rule a consumer resolving the summary at an instant applies, so it is
        the rule the arithmetic here has to use to mean anything.
        """
        out = []
        for m in self.members(summary_id):
            b = self.band_of_member(m)
            if b is None or b == band:
                out.append(m)
        return self.additive_plus_lowest_rung(out)

    def unit(self, price_id: str):
        """The member's unit price, or None when there is no number to read.

        None rather than zero, deliberately. A member naming a Price this filing
        does not define, or one carrying no urpx:unitPrice, is a subtotal that
        cannot be added up; treating it as zero would let the arithmetic below
        report a confident total with a charge silently missing from it, which
        is the exact failure this file exists to catch.
        """
        v = self.prices.get(price_id, {}).get("urpx:unitPrice")
        return None if v is None else Decimal(str(v))


def check_definitions(filings: list[Filing]) -> tuple[list[dict], int]:
    """No summary may name one PriceDefinition through more than one Price.

    Returns the problems and the number of (summary, PriceDefinition) groups
    examined, which is this check's denominator.
    """
    problems: list[dict] = []
    groups = 0
    for f in filings:
        for sid in sorted(f.summaries):
            by_pd: dict[str, list[str]] = {}
            for m in f.members(sid):
                pd = f.pd_of(m)
                if pd is None:
                    # Nothing to group on. Left alone deliberately: a member with
                    # no PriceDefinition cannot be shown to duplicate another.
                    continue
                by_pd.setdefault(pd, []).append(m)
            groups += len(by_pd)
            for pd, mem in sorted(by_pd.items()):
                if len(mem) < 2:
                    continue
                # Rungs of one block-tier ladder, told apart by
                # urpx:serviceTierNumber on the Price (pge:e-1's Conservation
                # Incentive Adjustment). They are alternatives per kWh, and the
                # resolver and check_arithmetic both keep only the lowest rung,
                # so naming every rung counts the charge once.
                tiers = [f.tier_of(m) for m in mem]
                if None not in tiers and len(set(tiers)) == len(tiers):
                    continue
                differ = sorted({k for m in mem for k in f.prices[m]
                                 if k in DISCRIMINATORS})
                problems.append({
                    "summary": sid,
                    "file": rel(f.path),
                    "definition": pd,
                    "members": [(m, str(f.unit(m))) for m in mem],
                    "discriminators": differ,
                })
    return problems, groups


def check_arithmetic(filings: list[Filing]) -> tuple[list[dict], int]:
    """The subtotal, and the discount taken from it, must be the right NUMBER.

    For every (discount, summary, TOU band) the corpus defines, the subtotal is
    resolved to an actual decimal two ways and the two are compared:

      as named    every member active in that band, summed. This is what a
                  consumer aggregating urpx:includesPrice computes.
      counted once  each PriceDefinition contributing exactly one price, which
                  is what "applied to the total bill" means.

    Where a definition still contributes several active members, no single
    "counted once" value exists, so this reports the RANGE the correct subtotal
    must lie in rather than inventing one. That matters: for a TOU-varying charge
    the band filter narrows it to one member and the range collapses to the exact
    right answer, but for a tier-varying charge it does not, and printing one
    endpoint as if it were the answer would be a confident wrong number of
    exactly the kind this file exists to catch.

    There is deliberately no third "subtotal below its own ceiling" comparison.
    Written as an elif it could never fire (as-named equals counted-once only
    when each definition contributed one member, and a sum of values never
    exceeds the sum of their magnitudes), and a branch that cannot fail is not a
    check.

    Returns the problems and the number of (discount, summary, band) triples
    evaluated, which is this check's denominator.
    """
    problems: list[dict] = []
    evaluated = 0
    per_band: dict[tuple, dict] = {}
    by_summary = {sid: f for f in filings for sid in f.summaries}

    for f in filings:
        for did in sorted(f.discounts):
            d = f.discounts[did]
            mult = Decimal(str(d["urpx:multiplier"]))
            for ref in as_list(d.get("urpx:basedOnPrice")):
                sid = ref_id(ref)
                base = by_summary.get(sid)
                if base is None:
                    # A candidate naming a summary outside the corpus is the
                    # membership check's business, not this one's.
                    continue
                bands = sorted(base.bands) or [None]
                for band in bands:
                    evaluated += 1
                    # A plan with no TOU bands still has a tier ladder, so the
                    # rung partition applies on both paths. Without it here, a
                    # flat tiered plan (SCE Schedule D) is compared unnarrowed
                    # against a resolver that does narrow, and this file reports
                    # a defect the consumer does not have.
                    mem = (base.additive_plus_lowest_rung(base.members(sid))
                           if band is None
                           else base.active_members(sid, band))

                    blind = [m for m in mem if base.unit(m) is None]
                    if blind:
                        problems.append({
                            "kind": "unvaluable",
                            "discount": did, "summary": sid, "band": band,
                            "file": rel(base.path),
                            "members": sorted(blind),
                        })
                        continue
                    # There was an "unnarrowed discriminator" check here. It is
                    # gone because it became unreachable: after the rung
                    # partition at most one tiered member survives, and the band
                    # read above resolves Price then PriceDefinition, so no
                    # second value of either discriminator can reach this point.
                    # Measured before removing: 0 fires across 132 (summary,
                    # band) combinations, and 0 Prices in 73 filings carry a
                    # touPeriodNumber their definition lacks. It earned its keep
                    # while the resolver summed whole tier ladders; clj-urpx
                    # 0.23.0 partitions them, and a branch that cannot fire is
                    # not a check. The shape it guarded is still caught by
                    # check_definitions, which is negative-tested.
                    named = sum((base.unit(m) for m in mem), Decimal(0))

                    # One bucket per definition; a definition with several
                    # active members is the defect, and its contribution to a
                    # correct subtotal is somewhere between its smallest and
                    # largest member.
                    buckets: dict[str, list[Decimal]] = {}
                    for m in mem:
                        buckets.setdefault(base.pd_of(m) or m, []).append(base.unit(m))
                    lo = sum((min(v) for v in buckets.values()), Decimal(0))
                    hi = sum((max(v) for v in buckets.values()), Decimal(0))
                    repeated = {pd: v for pd, v in buckets.items() if len(v) > 1}

                    per_band[(did, sid)] = per_band.get((did, sid), {})
                    per_band[(did, sid)][band] = (len(buckets), str(named), base)

                    if not repeated:
                        continue
                    discounts = sorted([mult * lo, mult * hi])
                    problems.append({
                        "kind": "double-counted",
                        "discount": did, "summary": sid, "band": band,
                        "file": rel(base.path),
                        "named": str(named),
                        "once_lo": str(lo), "once_hi": str(hi),
                        "modeled": str(mult * named),
                        "correct_lo": str(discounts[0]),
                        "correct_hi": str(discounts[1]),
                        "ratio": (str((mult * named) / (mult * lo))
                                  if lo == hi and lo != 0 else None),
                        "repeated": {pd: len(v) for pd, v in sorted(repeated.items())},
                    })

    # Every TOU band of one summary must be built from the same NUMBER of
    # PriceDefinitions. This is the part the duplicate-definition check above
    # cannot see: two DIFFERENT definitions carrying the same touPeriodNumber
    # for one charge group under different keys, so nothing there objects, but
    # one band then charges it twice and another band not at all. The counts
    # are what diverge, and they diverge whichever definitions are involved.
    for (did, sid), bands in sorted(per_band.items(), key=lambda kv: kv[0]):
        counts = {b: n for b, (n, _, _) in bands.items() if b is not None}
        if len(set(counts.values())) > 1:
            base = next(iter(bands.values()))[2]
            problems.append({
                "kind": "uneven-bands",
                "discount": did, "summary": sid,
                "file": rel(base.path),
                "counts": dict(sorted(counts.items())),
                "values": {b: v for b, (_, v, _) in sorted(bands.items())
                           if b is not None},
            })
    return problems, evaluated


def check(files) -> tuple[list[dict], dict]:
    """Every problem in `files`, and the counts a clean verdict reports.

    Raises Refused when a check would pass over nothing.
    """
    filings = [Filing(Path(f)) for f in files]

    summaries: dict[str, tuple[Path, list[str]]] = {}
    candidates: dict[str, list[str]] = {}
    owner: dict[str, Filing] = {}
    plans_of_price: dict[str, set[str]] = {}
    for f in filings:
        for sid in f.summaries:
            summaries[sid] = (f.path, f.members(sid))
        for did, d in f.discounts.items():
            candidates[did] = [ref_id(x) for x in as_list(d.get("urpx:basedOnPrice"))]
            owner[did] = f
        for pid in f.prices:
            plans_of_price.setdefault(pid, set()).update(f.plans)

    # A multiplier over line-item Prices, not over subtotals: checked at plan
    # grain below and kept out of the subtotal candidate check.
    line_item = {did for did, cands in candidates.items()
                 if cands and not any(c in summaries for c in cands)}

    if not summaries:
        raise Refused("no urpx:PriceSummary anywhere; this linter would pass "
                      "vacuously.")
    if not candidates:
        raise Refused("no urpx:Price carries a urpx:multiplier, so there is no "
                      "discount to check.")

    problems: list[dict] = []

    # MEMBERSHIP.
    for sid, (path, members) in sorted(summaries.items()):
        utility = utility_of(path)
        program = ("care" if "-care-" in sid else
                   "fera" if "-fera-" in sid else "shared")
        want = (expected_generation(path) if sid.endswith(GENERATION) else
                expected(path, utility, "care" if program == "shared" else program))
        missing = sorted(set(want) - set(members))
        extra = sorted(set(members) - set(want))
        if missing or extra:
            problems.append({"summary": sid, "file": rel(path),
                             "missing": missing, "unexpected": extra})

    for did in sorted(line_item):
        cands = candidates[did]
        unresolved = sorted(c for c in cands if c not in plans_of_price)
        per_plan: dict[str, list[str]] = {}
        for c in cands:
            for plan in plans_of_price.get(c, ()):
                per_plan.setdefault(plan, []).append(c)
        applicable = owner[did].applicable
        # A candidate set spanning one plan is a Price scoped to that plan by
        # naming only its line item (smud:nem1's per-plan credits); one spanning
        # several is a set of alternatives and has to cover every plan.
        uncovered = (sorted(p for p in applicable if p not in per_plan)
                     if len(per_plan) > 1 else [])
        repeated = {p: sorted(cs) for p, cs in sorted(per_plan.items()) if len(cs) > 1}
        stray = sorted(p for p in per_plan if p not in applicable)
        if unresolved or uncovered or repeated or stray:
            problems.append({"line_item_discount": did,
                             "file": rel(owner[did].path),
                             "unresolved": unresolved, "uncovered": uncovered,
                             "repeated": repeated, "stray": stray})

    all_sums = set(summaries)
    for pid, cands in sorted(candidates.items()):
        if pid in line_item:
            continue
        util = pid.split(":")[0]
        if any(c.endswith(GENERATION) for c in cands):
            want = {s for s in all_sums
                    if s.split(":")[0] == util and s.endswith(GENERATION)}
            gap = sorted(want - set(cands))
            if gap:
                problems.append({"discount": pid, "missing_candidates": gap})
            continue
        # A CARE discount names the CARE subtotals, a FERA discount the FERA ones,
        # and where a utility publishes one shared subtotal both name it. Demanding
        # every summary of the utility would require CARE to name FERA's.
        prog = "care" if re.search(r"(care-price|[:-]care-)", pid) else "fera"
        want = {
            s for s in all_sums
            if s.split(":")[0] == util
            and (f"-{prog}-discountable" in s or s.endswith("-summary-discountable"))
        }
        gap = sorted(want - set(cands))
        if gap:
            problems.append({"discount": pid, "missing_candidates": gap})

    # DEFINITIONS and ARITHMETIC, each refusing on its own empty denominator
    # rather than reporting "clean" over nothing to check.
    dup_problems, groups = check_definitions(filings)
    if groups == 0:
        raise Refused("no summary member resolves to a urpx:PriceDefinition, so "
                      "the duplicate-definition check has nothing to group on and "
                      "would pass vacuously.")
    problems.extend(dup_problems)

    math_problems, evaluated = check_arithmetic(filings)
    if evaluated == 0:
        raise Refused("no (discount, subtotal) pair resolved to a summary in "
                      "this corpus, so no subtotal arithmetic was compared and "
                      "this linter would pass vacuously.")
    problems.extend(math_problems)
    return problems, {"summaries": len(summaries), "discounts": len(candidates),
                      "groups": groups, "evaluated": evaluated}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    files = corpus.all_filing_jsonld()
    corpus.require_nonempty(files, "rate-plan filings")
    try:
        problems, n = check(files)
    except Refused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(problems, indent=2))
        return 1 if problems else 0

    if not problems:
        print(f"discount subtotals: clean ({n['summaries']} summaries, "
              f"{n['discounts']} discount prices, {n['groups']} summary/definition "
              f"groups, {n['evaluated']} subtotal values compared)")
        return 0

    print(f"discount subtotals: {len(problems)} problem(s)\n")
    for p in problems:
        if "missing" in p:
            print(f"  {p['summary']}")
            print(f"      in {p['file']}")
            for m in p["missing"]:
                print(f"      MISSING from the subtotal: {m}")
            for e in p["unexpected"]:
                print(f"      should NOT be in the subtotal: {e}")
        elif "line_item_discount" in p:
            print(f"  {p['line_item_discount']} does not name one base Price per plan")
            print(f"      in {p['file']}")
            for m in p["unresolved"]:
                print(f"      names no Price any filing defines: {m}")
            for m in p["uncovered"]:
                print(f"      NO candidate for applicable plan: {m}")
            for plan, cs in p["repeated"].items():
                print(f"      {len(cs)} candidates for {plan}: {', '.join(cs)}")
            for m in p["stray"]:
                print(f"      candidate in a plan not in applicableToRatePlan: {m}")
        elif "missing_candidates" in p:
            print(f"  {p['discount']} does not name every candidate subtotal")
            for m in p["missing_candidates"]:
                print(f"      MISSING candidate: {m}")
        elif "definition" in p:
            why = (" and ".join(k.split(":")[1] for k in p["discriminators"])
                   or "nothing this linter can see")
            print(f"  {p['summary']}")
            print(f"      in {p['file']}")
            print(f"      COUNTED {len(p['members'])} TIMES: {p['definition']}")
            print(f"      the members differ only by {why}, so they are one "
                  f"charge, not {len(p['members'])}:")
            for mid, val in p["members"]:
                print(f"          {mid}  {val}")
        elif p.get("kind") == "unvaluable":
            band = ("no TOU period defined" if p["band"] is None
                    else f"TOU period {p['band']}")
            print(f"  {p['discount']} over {p['summary']} ({band})")
            print(f"      in {p['file']}")
            print(f"      the subtotal cannot be added up: these members name no")
            print(f"      price this filing defines, or carry no urpx:unitPrice:")
            for m in p["members"]:
                print(f"          {m}")
        elif p.get("kind") == "double-counted":
            band = ("no TOU period defined" if p["band"] is None
                    else f"TOU period {p['band']}")
            exact = p["once_lo"] == p["once_hi"]
            print(f"  {p['discount']} over {p['summary']} ({band})")
            print(f"      in {p['file']}")
            for pd, n in p["repeated"].items():
                print(f"      counted {n} times: {pd}")
            print(f"      subtotal as named        {p['named']}")
            if exact:
                print(f"      subtotal counted once    {p['once_lo']}")
                print(f"      discount modeled         {p['modeled']}")
                print(f"      discount counted once    {p['correct_lo']}")
                print(f"      overstated by            {p['ratio']}x")
            else:
                # The band filter did not narrow the repeat to one member, so
                # the correct subtotal is a range, not a number. Reporting a
                # range is the honest form; picking an endpoint would not be.
                print(f"      subtotal counted once    between {p['once_lo']} "
                      f"and {p['once_hi']}")
                print(f"      discount modeled         {p['modeled']}")
                print(f"      discount counted once    between {p['correct_lo']} "
                      f"and {p['correct_hi']}")
        elif p.get("kind") == "uneven-bands":
            print(f"  {p['discount']} over {p['summary']}")
            print(f"      in {p['file']}")
            print(f"      the TOU bands of one subtotal are built from different")
            print(f"      numbers of price definitions, so at least one band")
            print(f"      charges something twice or not at all:")
            for b, n in p["counts"].items():
                print(f"          TOU period {b}: {n} definitions, "
                      f"subtotal {p['values'][b]}")
        print()
    print("A price missing from a subtotal makes the modeled discount too small,\n"
          "a price named twice makes it too large, and every other check stays\n"
          "green either way. See LAYOUT.md and the tariff sentences quoted at the\n"
          "top of this file.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
