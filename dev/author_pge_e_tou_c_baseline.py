#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Move PG&E Schedule E-TOU-C's baseline ladder into each base version.

The ladder was a sibling RatePlanModifier, pge:e-tou-c-baseline-tier, so every
composition without it (the base alone, and the base with D-CARE, E-FERA,
E-RSMART or the vintage PCIA) carried no Conservation Incentive Adjustment and no
tier bounds, and a modifier adjusting those bounds could never compose with the
base under a one-modifier policy. Each base version, 2026-03-01, 2026-03-27 and 2026-06-01,
now carries in its own document:

  - a kWh MetricInput `<version>-mi-energy-baseline` and a Conservation Incentive
    Adjustment ledger and PriceDefinition over it;
  - a `urpx:ServiceTiers` over that MetricInput with the three tiers the overlay
    carried: Tier 1 up to the Special Condition 1 quantity, Tier 2 to four times
    it, and Tier 2 Continued above that;
  - the Sheet 3 Conservation Incentive Adjustment as three Prices, one per tier,
    and, in the 2026-03-27 version, as members of both discountable subtotals.

WHY ONE CONTAINER OF 60. urpx:PlanElements carries sh:maxCount 1 on
urpx:hasProfileAlternatives, and each version already spent its container on the
income tier (CARE / FERA / standard) that prices the Base Services Charge. clj-urpx
selects one alternative per container, so the income tier, baseline territory and
baseline code become one container whose 60 members are the cells of their cross
product. A urpx:ServiceBracket names at most one alternative and a
urpx:PriceSetAlternative exactly one, so each territory-and-code bracket is
repeated for the three income tiers (360 per version) and the Base Services
Charge has one PriceSetAlternative per cell (60), each pricing the published
amount for its income tier.

The overlay document, its manifest entry and its coverage sidecar entry are
removed. Prose in the manifests and documents that described the overlay is
rewritten here.

Re-running is safe: the ladder and the container are rebuilt each time.

Run from the repo root: python3 dev/author_pge_e_tou_c_baseline.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PGE = REPO / "us/ca/pge/electricity"
SCHED = PGE / "e-tou-c"
DATES = ["2026-03-01", "2026-03-27", "2026-06-01"]
OVERLAY = SCHED / "versions/2026-03-01/rate-plan-modifier_pge_e-tou-c-baseline-tier_2026-03-01.jsonld"

# Special Condition 1, Sheet 5 (Cal. P.U.C. Sheet 61128-E), Baseline Quantities
# in kWh per day, identical in all three versions' PDFs (checked 2026-10-07).
#   territory: (Code B summer, Code B winter, Code H summer, Code H winter)
TERRITORIES = ["P", "Q", "R", "S", "T", "V", "W", "X", "Y", "Z"]
QUANTITY = {
    "P": ("13.5", "11.0", "15.2", "26.0"),
    "Q": ("9.8", "11.0", "8.5", "26.0"),
    "R": ("17.7", "10.4", "19.9", "26.7"),
    "S": ("15.0", "10.2", "17.8", "23.7"),
    "T": ("6.5", "7.5", "7.1", "12.9"),
    "V": ("7.1", "8.1", "10.4", "19.1"),
    "W": ("19.2", "9.8", "22.4", "19.0"),
    "X": ("9.8", "9.7", "8.5", "14.6"),
    "Y": ("10.5", "11.1", "12.0", "24.0"),
    "Z": ("5.9", "7.8", "6.7", "15.7"),
}
CODES = ["B", "H"]
SEASONS = ["summer", "winter"]
# Sheet 3 (Cal. P.U.C. Sheet 61126-E), $ per kWh.
CIA = {"t1": "-0.02786", "t2": "0.05354", "t2c": "0.05354"}

INCOME = [
    ("care", "Income Tier 1 (CARE-eligible)", "tier-1"),
    ("fera", "Income Tier 2 (FERA-eligible)", "tier-2"),
    ("standard", "Income Tier 3 (neither CARE nor FERA)", "tier-3"),
]


def ref(i: str) -> dict:
    return {"@id": i}


def find(x, i):
    if isinstance(x, dict):
        if x.get("@id") == i:
            return x
        for v in x.values():
            r = find(v, i)
            if r is not None:
                return r
    elif isinstance(x, list):
        for v in x:
            r = find(v, i)
            if r is not None:
                return r
    return None


def quantity(territory: str, code: str, season: str) -> str:
    return QUANTITY[territory][CODES.index(code) * 2 + SEASONS.index(season)]


def times4(q: str) -> str:
    from decimal import Decimal
    return str((Decimal(q) * 4).quantize(Decimal("0.1")))


def base_path(date: str) -> Path:
    return SCHED / "versions" / date / f"rate-plan_pge_e-tou-c_{date}.jsonld"


# --- the container -----------------------------------------------------------

def cell_id(v: str, income: str, territory: str, code: str) -> str:
    return f"{v}-pa-{income}-{territory.lower()}-{code.lower()}"


def enrollment(n: str, operator: str, program: str) -> dict:
    return {"@type": "urpx:ComparisonNode", "@id": n,
            "urpx:operator": ref(operator),
            "urpx:leftOperand": {"@type": "urpx:ObjectOperandNode", "@id": f"{n}-left-operand",
                                 "urpx:conditionProperty": ref("urpx:hasProgramEnrollment")},
            "urpx:rightOperand": {"@type": "urpx:ObjectOperandNode", "@id": f"{n}-right-operand",
                                  "urpx:referencesValue": ref(program)}}


def custom(n: str, prop: str, value: str) -> dict:
    return {"@type": "urpx:ComparisonNode", "@id": n,
            "urpx:operator": ref("urpx:equalsOperator"),
            "urpx:leftOperand": {"@type": "urpx:CustomOperandNode", "@id": f"{n}-left-operand",
                                 "urpx:customConditionProperty": prop},
            "urpx:rightOperand": {"@type": "urpx:CustomOperandNode", "@id": f"{n}-right-operand",
                                  "urpx:stringValue": value}}


def cell(v: str, income: str, label: str, territory: str, code: str) -> dict:
    s = cell_id(v, income, territory, code)
    if income == "care":
        tier = [enrollment(f"{s}-care", "urpx:equalsOperator", "pge:program-care")]
    elif income == "fera":
        tier = [enrollment(f"{s}-fera", "urpx:equalsOperator", "pge:program-fera")]
    else:
        tier = [enrollment(f"{s}-not-care", "urpx:notEqualsOperator", "pge:program-care"),
                enrollment(f"{s}-not-fera", "urpx:notEqualsOperator", "pge:program-fera")]
    return {
        "@type": "urpx:ProfileAlternative", "@id": s,
        "urpx:name": f"{label}, Baseline Territory {territory}, Code {code}",
        "urpx:hasConditionExpression": {
            "@type": "urpx:ConditionExpression", "@id": f"{s}-condition-expression",
            "urpx:rootNode": {
                "@type": "urpx:BooleanOperationNode", "@id": f"{s}-root-node",
                "urpx:operator": ref("urpx:andOperator"),
                "urpx:operandNodes": tier + [custom(f"{s}-territory", "baselineTerritory", territory),
                                             custom(f"{s}-code", "baselineCode", code)]}}}


def container(v: str) -> dict:
    c = f"{v}-pa-income-territory-code"
    return {
        "@type": "urpx:ProfileAlternatives", "@id": c,
        "urpx:name": ("Income tier (CARE / FERA / standard) by Baseline Territory and Baseline Code "
                      "(Sheet 1 RATES; Special Condition 1, Sheet 5)"),
        "urpx:hasAlternativeDimensions": {
            "@type": "urpx:AlternativeDimensions", "@id": f"{c}-alternative-dimensions",
            "urpx:hasAlternativeDimension": [
                {"@type": "urpx:AlternativeDimension",
                 "urpx:dimensionDisplayName": "Program Enrollment",
                 "urpx:dimensionProperty": "https://urpx.org/ns/ontology/hasProgramEnrollment",
                 "urpx:hasPossibleValues": {"@list": [ref("pge:program-care"), ref("pge:program-fera")]}},
                {"@type": "urpx:AlternativeDimension",
                 "urpx:dimensionDisplayName": "Baseline Territory",
                 "urpx:customDimensionProperty": "baselineTerritory",
                 "urpx:hasPossibleValues": {"@list": [{"@value": t, "@type": "xsd:string"} for t in TERRITORIES]}},
                {"@type": "urpx:AlternativeDimension",
                 "urpx:dimensionDisplayName": "Baseline Code",
                 "urpx:customDimensionProperty": "baselineCode",
                 "urpx:hasPossibleValues": {"@list": [{"@value": c_, "@type": "xsd:string"} for c_ in CODES]}},
            ]},
        "urpx:hasProfileAlternative": [cell(v, i, label, t, c_)
                                       for i, label, _ in INCOME for t in TERRITORIES for c_ in CODES]}


# --- the ladder --------------------------------------------------------------

def bracket(bid, season_id, alt, lower, lower_op, upper=None, upper_op=None):
    b = {"@type": "urpx:ServiceBracket", "@id": bid,
         "urpx:appliesInSeason": ref(season_id),
         "urpx:referencesProfileAlternative": ref(alt),
         "urpx:lowerBound": lower, "urpx:lowerBoundOperator": ref(lower_op)}
    if upper is not None:
        b["urpx:upperBound"] = upper
        b["urpx:upperBoundOperator"] = ref(upper_op)
    return b


def service_tiers(v: str) -> dict:
    rungs = {"t1": [], "t2": [], "t2c": []}
    for income, _, _ in INCOME:
        for territory in TERRITORIES:
            for code in CODES:
                alt = cell_id(v, income, territory, code)
                for season in SEASONS:
                    q = quantity(territory, code, season)
                    sid = f"{v}-season-{season}"
                    stem = f"{income}-{territory.lower()}-{code.lower()}-{season}"
                    rungs["t1"].append(bracket(f"{v}-bracket-t1-{stem}", sid, alt,
                                               "0", "urpx:greaterThanOrEqualOperator",
                                               q, "urpx:lessThanOrEqualOperator"))
                    rungs["t2"].append(bracket(f"{v}-bracket-t2-{stem}", sid, alt,
                                               q, "urpx:greaterThanOperator",
                                               times4(q), "urpx:lessThanOrEqualOperator"))
                    rungs["t2c"].append(bracket(f"{v}-bracket-t2c-{stem}", sid, alt,
                                                times4(q), "urpx:greaterThanOperator"))
    names = {
        "t1": "Tier 1, baseline usage: kWh per day up to the Special Condition 1 quantity",
        "t2": "Tier 2, over baseline usage: kWh per day above the Special Condition 1 quantity, to four times it",
        "t2c": "Tier 2 Continued: kWh per day above four times the Special Condition 1 quantity",
    }
    return {
        "@type": "urpx:ServiceTiers", "@id": f"{v}-tiers-baseline",
        "urpx:referencesMetricInput": ref(f"{v}-mi-energy-baseline"),
        "urpx:hasServiceTier": [
            {"@type": "urpx:ServiceTier", "@id": f"{v}-tier-baseline-{r}", "urpx:name": names[r],
             "urpx:serviceTierNumber": n, "urpx:hasServiceBracket": rungs[r]}
            for n, r in ((1, "t1"), (2, "t2"), (3, "t2c"))]}


def bsc_alternatives(v: str, date: str, old: dict) -> dict:
    """60 PriceSetAlternatives, each the published amount for its income tier."""
    by_tier = {}
    for psa in old["urpx:hasPriceSetAlternative"]:
        price = psa["urpx:hasPrice"][0]
        by_tier[psa["@id"].rsplit("-psa-bsc-", 1)[1]] = price
    alts = []
    for income, label, tier in INCOME:
        template = by_tier[tier]
        for territory in TERRITORIES:
            for code in CODES:
                stem = f"{income}-{territory.lower()}-{code.lower()}"
                p = copy.deepcopy(template)
                p["@id"] = f"{v}-price-base-charge-{stem}"
                p["urpx:name"] = f"Base Services Charge, {label}, Baseline Territory {territory}, Code {code}"
                alts.append({"@type": "urpx:PriceSetAlternative", "@id": f"{v}-psa-bsc-{stem}",
                             "urpx:referencesProfileAlternative": ref(cell_id(v, income, territory, code)),
                             "urpx:hasPrice": [p]})
    out = {k: x for k, x in old.items() if k != "urpx:hasPriceSetAlternative"}
    out["urpx:name"] = ("Base Services Charge by income tier (CARE / FERA / standard), one alternative per "
                        "income tier, Baseline Territory and Baseline Code cell")
    out["urpx:referencesProfileAlternatives"] = ref(f"{v}-pa-income-territory-code")
    out["urpx:hasPriceSetAlternative"] = alts
    return out


def ladder(date: str) -> None:
    p = base_path(date)
    doc = json.loads(p.read_text(encoding="utf-8"))
    for k in ("urpx:lowerBound", "urpx:upperBound"):
        doc["@context"].setdefault(k, {"@type": "xsd:decimal"})
    v = f"pge:e-tou-c-{date}"
    pkg = doc["@graph"][0]
    version = pkg["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]
    pe = version["urpx:hasPlanElements"]

    mis = [m for m in pe["urpx:hasMetricInput"] if m["@id"] != f"{v}-mi-energy-baseline"]
    energy = next(m for m in mis if m["@id"] == f"{v}-mi-energy")
    mis.insert(mis.index(energy) + 1, {
        "@type": "urpx:MetricInput", "@id": f"{v}-mi-energy-baseline",
        "urpx:name": "kWh Energy Consumption, baseline-tier reference metric",
        "urpx:metricInputType": ref("urpx:measuredMetricInput"),
        "urpx:hasMetricSpecification": copy.deepcopy(energy["urpx:hasMetricSpecification"])})
    pe["urpx:hasMetricInput"] = mis

    bm = pe["urpx:hasBillingModel"]
    ledgers = [x for x in bm["urpx:hasLedger"] if x["@id"] != f"{v}-ledger-cia"]
    at = next(i for i, x in enumerate(ledgers) if x["@id"] == f"{v}-ledger-adjustments") + 1
    ledgers.insert(at, {"@type": "urpx:Ledger", "@id": f"{v}-ledger-cia",
                        "urpx:name": "Conservation Incentive Adjustment",
                        "urpx:ledgerType": ref("urpx:bundledLedger"),
                        "urpx:referencesMetricInput": ref(f"{v}-mi-energy-baseline")})
    pds = [x for x in bm["urpx:hasPriceDefinition"] if x["@id"] != f"{v}-pd-cia"]
    at = next(i for i, x in enumerate(pds) if x["@id"] == f"{v}-pd-dist-winter-off-peak") + 1
    pds.insert(at, {"@type": "urpx:PriceDefinition", "@id": f"{v}-pd-cia",
                    "urpx:name": "Conservation Incentive Adjustment",
                    "urpx:chargeType": ref("urpx:conservationCharge"),
                    "urpx:chargeCategory": ref("urpx:adjustment"),
                    "urpx:billPortion": ref("urpx:bundledPortion"),
                    "urpx:referencesLedger": ref(f"{v}-ledger-cia")})
    new_bm = {}
    for k, x in bm.items():
        if k == "urpx:hasServiceTiers":
            continue
        if k == "urpx:hasLedger":
            new_bm["urpx:hasServiceTiers"] = [service_tiers(v)]
        new_bm[k] = x
    new_bm["urpx:hasLedger"] = ledgers
    new_bm["urpx:hasPriceDefinition"] = pds
    pe["urpx:hasBillingModel"] = new_bm
    pe["urpx:hasProfileAlternatives"] = container(v)

    prices = version["urpx:hasPrices"]
    sets = [s for s in prices["urpx:hasPriceSet"] if s["@id"] != f"{v}-ps-conservation-incentive-adjustment"]
    dist = next(s for s in sets if s["@id"] == f"{v}-ps-distribution-charges")
    labels = {"t1": "Tier 1 (baseline usage)", "t2": "Tier 2 (over baseline usage)",
              "t2c": "Tier 2 Continued (over baseline usage)"}
    cia = {"@type": "urpx:PriceSet", "@id": f"{v}-ps-conservation-incentive-adjustment",
           "urpx:startDate": dist["urpx:startDate"],
           "urpx:hasPrice": [{"@type": "urpx:Price", "@id": f"{v}-price-cia-{r}",
                              "urpx:referencesPriceDefinition": ref(f"{v}-pd-cia"),
                              "urpx:name": f"Conservation Incentive Adjustment, {labels[r]}",
                              "urpx:unitPrice": CIA[r], "urpx:serviceTierNumber": n}
                             for n, r in ((1, "t1"), (2, "t2"), (3, "t2c"))]}
    sets.insert(sets.index(dist) + 1, cia)
    prices["urpx:hasPriceSet"] = sets
    for alts in prices["urpx:hasPriceSetAlternatives"]:
        if alts["@id"] == f"{v}-psa-bsc-by-income-tier" and \
                alts["urpx:referencesProfileAlternatives"]["@id"] == f"{v}-pa-income-tier":
            prices["urpx:hasPriceSetAlternatives"][prices["urpx:hasPriceSetAlternatives"].index(alts)] = \
                bsc_alternatives(v, date, alts)

    for program, before, after in (("care", "The 16 volumetric charges", "The 17 volumetric charges"),
                                   ("fera", "The 17 volumetric charges", "The 18 volumetric charges")):
        s = find(prices, f"{v}-summary-{program}-discountable")
        if s is None:
            continue
        inc = [x for x in s["urpx:includesPrice"] if not x["@id"].startswith(f"{v}-price-cia-")]
        at = next(i for i, x in enumerate(inc) if x["@id"] == f"{v}-price-dist-winter-off-peak") + 1
        inc[at:at] = [ref(f"{v}-price-cia-{r}") for r in ("t1", "t2", "t2c")]
        s["urpx:includesPrice"] = inc
        if before in s["urpx:name"]:
            s["urpx:name"] = s["urpx:name"].replace(
                before, after + ", the Conservation Incentive Adjustment counted once across its three "
                                "baseline tiers,", 1)

    for key in ("urpx:hasModifierOptions", "urpx:hasModifierVersionOptions"):
        version[key] = [x for x in version[key] if not x["@id"].startswith("pge:e-tou-c-baseline-tier")]
    version["urpx:description"] = rewrite_description(version["urpx:description"], v)
    ev = version["urpx:hasCoverageClaim"]["urpx:explainedBy"]
    ev["urpx:description"] = ev["urpx:description"].replace(
        "this filing carries the time-of-use dimension and the sibling baseline-tier modifier carries the tier "
        "dimension, but nothing states how the two combine.",
        "this filing carries both the time-of-use dimension and the baseline tiers, but nothing states how the "
        "two combine.")
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


LADDER_SENTENCE = (
    "The Conservation Incentive Adjustment is priced on {v}-tiers-baseline: Tier 1 up to the Special "
    "Condition 1 baseline quantity, Tier 2 to four times it and Tier 2 Continued above that, in kWh per day "
    "for each of the 10 baseline territories, Code B (basic) and Code H (all-electric), and both seasons. "
    "The territory and code share one urpx:ProfileAlternatives with the income tier, {v}-pa-income-territory-code, "
    "whose 60 members are the cells of the three dimensions; each urpx:ServiceBracket names one cell and one "
    "season.")


def rewrite_description(d: str, v: str) -> str:
    old_0301 = ("The Conservation Incentive Adjustment applies per the 10-territory × 2-code × 2-season "
                "baseline-allowance matrix and is modeled in the sibling RatePlanModifier file "
                "`rate-plan-modifier_pge_e-tou-c-baseline-tier_2026-03-01.jsonld` (one urpx:ServiceTiers container "
                "holding three tiers, over a 20-member baselineTerritory-by-baselineCode urpx:ProfileAlternatives, "
                "with each of its 120 urpx:ServiceBracket carrying the per-cell urpx:referencesProfileAlternative and "
                "the urpx:appliesInSeason).")
    old_0327 = ("Baseline credit and Conservation Incentive Adjustment apply per the 10-territory × 2-code × "
                "2-season baseline-allowance matrix and are modeled in the sibling RatePlanModifier file at "
                "`versions/2026-03-01/rate-plan-modifier_pge_e-tou-c-baseline-tier_2026-03-01.jsonld` (the matrix "
                "didn't change between 2026-03-01 and 2026-03-27, so no reissue of the modifier was needed; "
                "`applicableToRatePlan` references `pge:e-tou-c` and resolves across versions).")
    new = LADDER_SENTENCE.format(v=v)
    for old in (old_0301, old_0327):
        d = d.replace(old, new)
    if new not in d:
        raise SystemExit(f"{v}: description sentence on the overlay not found")
    return d


# --- manifests and the rest of the corpus ------------------------------------

def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def replace_deferral(text: str, prefix: str, new: list[str]) -> str:
    """Replace the one deferral starting with `prefix` by `new` (none to drop it)."""
    lines = text.split("\n")
    hits = [i for i, line in enumerate(lines) if line.startswith(" " + toml_str(prefix)[:-1])]
    if not hits:
        if all((" " + toml_str(n) + ",") in lines for n in new):
            return text
        raise SystemExit(f"deferral not found: {prefix[:60]}")
    i = hits[0]
    lines[i:i + 1] = [" " + toml_str(n) + "," for n in new]
    return "\n".join(lines)


def per_day(date: str) -> str:
    return (
        "Special Condition 1 (Sheet 5, Cal. P.U.C. Sheet 61128-E) publishes the baseline quantities as kWh PER "
        f"DAY. pge:e-tou-c-{date}-mi-energy-baseline declares unitOfMeasure urpx:kWh with no intervalDuration, "
        "so a bracket bound of 13.5 reads as 13.5 kWh rather than 13.5 kWh per day; on a 30-day summer bill in "
        "territory P the real Tier 1 ceiling is 405 kWh. v0.5.1 MetricSpecificationShape carries "
        "urpx:intervalDuration (xsd:duration, maxCount 1), so P1D is expressible. Put the interval there and not "
        "on a PriceDefinition's CalculationMethod, where an interval states the window a charge is calculated over "
        "rather than the period the baseline quantity is published in.")


def four_times(date: str) -> str:
    return (
        "The schedule draws one usage boundary, baseline versus over baseline: Sheet 2's 'Applied to Baseline Usage "
        "Only' and the two Sheet 3 Conservation Incentive Adjustment lines. This version asserts a third tier, "
        f"pge:e-tou-c-{date}-tier-baseline-t2c 'above four times the Special Condition 1 quantity', and caps tier 2 "
        "at exactly 4x the Special Condition 1 quantity in every cell. Nothing in the ten sheets states 400 percent, "
        "four times, or a second over-baseline tier. Both tiers price at $0.05354 so the split is economically "
        "inert, but it publishes a boundary this filing does not. Either cite the source for the 4x figure or "
        "collapse Tier 2 and Tier 2 Continued.")


PRORATION_0301 = (
    "Neither proration rule is carried. Sheet 1 states that time-of-use period usage is assigned to baseline tiers "
    "pro rata, so that a customer with twenty percent of its usage in the peak period has twenty percent of the "
    "usage in each tier treated as on-peak. Special Condition 4 (Sheet 6) prorates the daily baseline quantity and "
    "rates by the number of days of each season in a bill spanning the June 1 or October 1 changeover. This version "
    "carries both the time-of-use dimension and the baseline tiers, but nothing states how the two combine or how a "
    "daily quantity scales to a billing period. Not expressible at v0.5.1: CalculationMethodShape is sh:closed with "
    "no condition or allocation path and only the free-text calculationFormula, which no consumer reads; "
    "urpx:prorationMethod is an xsd:string on BillingModel scoped to mid-period service start and stop.")

PRORATION_0327 = (
    "Sheet 1, RATES: 'TOU period usage is assigned to tiers on a pro-rated basis. For example, if twenty percent of "
    "a customer's usage is in the peak period, then twenty percent of the total usage in each tier will be treated "
    "as on-peak usage.' This is the rule composing this version's TOU dimension with its baseline tiers, and "
    "neither is stated to depend on the other. Under v0.5.1, CalculationMethodShape is sh:closed and the only slot "
    "is the free-text calculationFormula, so the rule can be recorded as prose but not as a computable composition. "
    "Standard-level, not a modeling oversight.")

REVIEW_0301_OLD = ("RatePlan + Vintaged-PCIA RatePlanModifier in single @graph. The Conservation Incentive Adjustment "
                   "and the baseline allowance matrix are modeled in the sibling "
                   "rate-plan-modifier_pge_e-tou-c-baseline-tier_2026-03-01.jsonld, which covers all ten baseline "
                   "territories in both codes across both seasons.")
REVIEW_0301_NEW = ("RatePlan + Vintaged-PCIA RatePlanModifier in single @graph. The Conservation Incentive Adjustment "
                   "and the baseline allowance matrix, all ten baseline territories in both codes across both seasons, "
                   "are in the base version: pge:e-tou-c-2026-03-01-tiers-baseline, over the 60-cell income tier, "
                   "territory and code container pge:e-tou-c-2026-03-01-pa-income-territory-code.")
REVIEW_0327_ADD = (" The Conservation Incentive Adjustment and the baseline allowance matrix are in this version: "
                   "pge:e-tou-c-2026-03-27-tiers-baseline, over the 60-cell income tier, territory and code "
                   "container pge:e-tou-c-2026-03-27-pa-income-territory-code.")


def manifests() -> None:
    p = SCHED / "versions/2026-03-01/tariff.toml"
    t = p.read_text(encoding="utf-8")
    t = replace_deferral(t, "Special Condition 1 (Sheet 5, Cal. P.U.C. Sheet 61128-E) publishes the baseline "
                            "quantities as kWh PER DAY.", [per_day("2026-03-01")])
    t = replace_deferral(t, "The schedule draws one usage boundary", [four_times("2026-03-01")])
    t = replace_deferral(t, "Neither proration rule is carried.", [PRORATION_0301])
    t = replace_deferral(t, "The baseline overlay carries the tier matrix", [])
    t = t.replace(' "e-tou-c-baseline-tier",\n', "")
    t = t.replace(REVIEW_0301_OLD, REVIEW_0301_NEW)
    if REVIEW_0301_NEW not in t:
        raise SystemExit("2026-03-01 review note not rewritten")
    p.write_text(t, encoding="utf-8")

    p = SCHED / "versions/2026-03-27/tariff.toml"
    t = p.read_text(encoding="utf-8")
    t = replace_deferral(t, "Sheet 1, RATES: 'TOU period usage is assigned to tiers on a pro-rated basis.",
                         [PRORATION_0327])
    t = replace_deferral(t, "This version's own document carries neither the Conservation Incentive Adjustment",
                         [per_day("2026-03-27"), four_times("2026-03-27")])
    t = t.replace(' "e-tou-c-baseline-tier",\n', "")
    marker = 'notes = "Sheet 2 reissued under AL 7869-E'
    i = t.index(marker)
    end = t.index('"\n', i + len(marker))
    if REVIEW_0327_ADD not in t[i:end]:
        t = t[:end] + REVIEW_0327_ADD + t[end:]
    p.write_text(t, encoding="utf-8")

    for prog in ("d-care/versions/2026-03-01", "e-fera/versions/2026-06-01"):
        p = PGE / prog / "tariff.toml"
        t = p.read_text(encoding="utf-8")
        t = t.replace("as pge:e-1-income-tier\nand pge:e-tou-c-baseline-tier do.", "as pge:e-1-income-tier\ndoes.")
        t = replace_deferral(t, "The E-TOU-C Conservation Incentive Adjustment is outside the E-TOU-C subtotal.", [])
        p.write_text(t, encoding="utf-8")


def main() -> int:
    if OVERLAY.exists():
        OVERLAY.unlink()
        print(f"removed {OVERLAY.relative_to(REPO)}")
    for date in DATES:
        ladder(date)
        print(f"ladder  {base_path(date).relative_to(REPO)}")
    manifests()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
