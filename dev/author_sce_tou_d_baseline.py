#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Author the SCE Schedule TOU-D baseline ladder and the HPWH baseline modifier.

Part 1 edits the four TOU-D base filings (Option 4-9 PM and Option 5-8 PM,
2025-11-15 and 2026-03-20). Each gains, in its own version:

  - a kWh MetricInput `<version>-mi-energy-baseline` and a `Baseline Credit`
    ledger over it, which the Baseline Credit PriceDefinition now references;
  - a `urpx:ServiceTiers` over that MetricInput with Tier 1 (up to 100 percent
    of the Baseline Allocation) and Tier 2 (above it), one bracket per Baseline
    Region, Basic or All-Electric allocation and season, bounded in kWh per
    day from SCE Preliminary Statement Part H, Sheets 2 and 3;
  - a `urpx:ProfileAlternatives` with one alternative per region and
    allocation, the brackets' `urpx:referencesProfileAlternative`;
  - the Baseline Credit Price on `urpx:serviceTierNumber` 1, and a zero Price
    on Tier 2, both in the version's discountable subtotal.

Part 2 writes, as a second document in each base version's directory, the
`sce:<schedule>-hpwh` RatePlanModifier version whose adjusting brackets
(urpx-org/urpx#80) add the Part H Heat Pump Water Heater allocation to that
base version's Tier 1 upper bound and Tier 2 lower bound. One modifier per
schedule, because clj-urpx refuses an adjusting bracket whose target tier is
not in the composition.

Part 3 rewrites the base versions' prose on the Baseline Credit and HPWH, and
their manifests: Part H as a second source, its deferrals, and the modifier
slug in applicable_modifiers.

Re-running is safe: the ladder is rebuilt from the table below each time.

Run from the repo root: python3 dev/author_sce_tou_d_baseline.py
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCE = REPO / "us/ca/sce/electricity"

SCHEDULES = ["tou-d-4-9pm", "tou-d-5-8pm"]
DATES = ["2025-11-15", "2026-03-20", "2026-06-01", "2026-10-01"]

# Preliminary Statement Part H, paragraph 3: Sheet 2 (Cal. P.U.C. Sheet 74486-E)
# summer and Sheet 3 (74487-E) winter, both effective October 1, 2022 under
# Advice 4864-E and in force until Advice 5897-E replaced them on October 1,
# 2026. kWh per day, (Basic, All-Electric).
REGIONS = ["5", "6", "8", "9", "10", "13", "14", "15", "16"]
ALLOCATION_2022 = {
    "summer": {"5": ("17.0", "16.8"), "6": ("11.4", "8.7"), "8": ("12.8", "9.9"),
               "9": ("16.9", "12.5"), "10": ("19.3", "15.9"), "13": ("22.2", "24.2"),
               "14": ("19.2", "18.5"), "15": ("45.0", "24.0"), "16": ("14.7", "13.5")},
    "winter": {"5": ("18.4", "27.0"), "6": ("11.0", "12.6"), "8": ("10.3", "12.3"),
               "9": ("12.0", "13.9"), "10": ("12.1", "16.4"), "13": ("12.2", "23.0"),
               "14": ("11.9", "21.1"), "15": ("9.7", "17.4"), "16": ("12.4", "23.2")},
}
# The same paragraph as reissued effective October 1, 2026 under Advice 5897-E
# (Decision 26-04-033): Sheet 2 (91543-E) summer and Sheet 3 (91544-E) winter.
ALLOCATION_2026 = {
    "summer": {"5": ("16.5", "15.6"), "6": ("11.6", "8.5"), "8": ("13.1", "10.0"),
               "9": ("17.1", "12.9"), "10": ("19.8", "16.0"), "13": ("22.2", "22.7"),
               "14": ("20.1", "19.2"), "15": ("41.1", "23.3"), "16": ("14.9", "13.5")},
    "winter": {"5": ("18.3", "24.2"), "6": ("10.5", "11.8"), "8": ("9.7", "11.6"),
               "9": ("11.5", "13.2"), "10": ("11.6", "15.2"), "13": ("11.5", "19.6"),
               "14": ("11.9", "20.9"), "15": ("8.8", "16.1"), "16": ("12.5", "23.3")},
}
# The same sheets' Heat Pump Water Heater Allocation columns, kWh per day.
HPWH = {"summer": ("1.9", "1.9"), "winter": ("2.6", "3.0")}
CODES = [("basic", "Basic"), ("all-electric", "All-Electric")]
OPTION = {"tou-d-4-9pm": "Schedule TOU-D Option 4-9 PM", "tou-d-5-8pm": "Schedule TOU-D Option 5-8 PM"}

PART_H_URL = ("https://edisonintl.sharepoint.com/teams/Public/TM2/Shared%20Documents/Public/"
              "Regulatory/Tariff-SCE%20Tariff%20Books/Electric/Preliminary%20Statements/"
              "ELECTRIC_PRELIM_H.pdf")


class PartH:
    """One edition of Preliminary Statement Part H Sheets 2 and 3, as vendored."""

    def __init__(self, pdf, retrieved, leaves, effective, advice, docket, allocation):
        self.pdf, self.retrieved, self.leaves = pdf, retrieved, leaves
        self.effective, self.advice, self.docket, self.allocation = effective, advice, docket, allocation


PART_H_2022 = PartH("sce_prelim-h_2024-08-15.pdf", "2026-05-04", ("74486-E", "74487-E"),
                    "October 1, 2022", "4864-E",
                    "Decision 22-08-001 (Preliminary Statement Part H Sheets 2 and 3, Advice 4864-E)",
                    ALLOCATION_2022)
PART_H_2026 = PartH("sce_prelim-h_2026-10-01.pdf", "2026-10-06", ("91543-E", "91544-E"),
                    "October 1, 2026", "5897-E",
                    "Decision 26-04-033 (Preliminary Statement Part H Sheets 2 and 3, Advice 5897-E)",
                    ALLOCATION_2026)
# The edition in force at each base version's effective date.
PART_H = {"2025-11-15": PART_H_2022, "2026-03-20": PART_H_2022, "2026-06-01": PART_H_2022,
          "2026-10-01": PART_H_2026}

# Option name and the sheets whose footnote states the baseline rules, per
# base version.
SHEETS = {"tou-d-4-9pm": "Sheets 2 and 3", "tou-d-5-8pm": "Sheets 4 and 5"}
CREDIT = {"2025-11-15": "0.10449", "2026-03-20": "0.10108", "2026-06-01": "0.10099", "2026-10-01": "0.09101"}


def hpwh_description(sched: str, date: str) -> str:
    return (
        "Preliminary Statement Part H, paragraph 3, adds a Heat Pump Water Heater (HPWH) baseline quantity "
        "for customers attesting to having a HPWH and served under Schedule TOU-D-4-9 or TOU-D-5-8: 1.9 kWh "
        "per day in summer for the Basic and the All-Electric Allocation, and 2.6 (Basic) and 3.0 "
        f"(All-Electric) kWh per day in winter (Sheets 2 and 3, Cal. P.U.C. Sheets {PART_H[date].leaves[0]} and "
        f"{PART_H[date].leaves[1]}). This "
        f"version adds them to the baseline ladder of sce:{sched}-{date}: each of its 72 urpx:ServiceBracket "
        "names that version's Tier 1 or Tier 2 with urpx:adjustsServiceTier, a Baseline Region and allocation "
        "with urpx:referencesProfileAlternative, and a season, and offsets Tier 1's upper bound and Tier 2's "
        "lower bound by that cell's quantity, so the Baseline Credit reaches the larger allocation. The "
        "offsets are kWh per day, the unit of the bounds they adjust. urpx:adjustsServiceTier, "
        "urpx:lowerBoundOffset and urpx:upperBoundOffset are proposed in urpx-org/urpx#80 and are in no URPX "
        "release.")


def hpwh_evaluation(sched: str, date: str) -> str:
    return (
        "Part H's HPWH quantities are carried for every Baseline Region, allocation and season. They are kWh "
        "per day, as are the bounds they adjust, and this document does not state how a consumer scales "
        "either to a billing period, which Part H paragraph 3 does by the number of summer and winter days in "
        f"it. The adjusting brackets name the tier @ids of sce:{sched}-{date}, so a later version of the "
        "schedule needs its own version of this modifier.")


CONTEXT_TYPES = {
    "urpx:lowerBound": "xsd:decimal",
    "urpx:upperBound": "xsd:decimal",
}
HPWH_CONTEXT_TYPES = {
    "urpx:lowerBoundOffset": "xsd:decimal",
    "urpx:upperBoundOffset": "xsd:decimal",
    "urpx:booleanValue": "xsd:boolean",
}


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


def as_list(v):
    return v if isinstance(v, list) else [v]


def base_path(sched: str, date: str) -> Path:
    return SCE / sched / "versions" / date / f"rate-plan_sce_{sched}_{date}.jsonld"


# --- part 1: the ladder ------------------------------------------------------

def alternative_id(v: str, region: str, code: str) -> str:
    return f"{v}-pa-baseline-r{region}-{code}"


def comparison(cid: str, prop: str, value: str) -> dict:
    return {"@type": "urpx:ComparisonNode", "@id": cid,
            "urpx:operator": ref("urpx:equalsOperator"),
            "urpx:leftOperand": {"@type": "urpx:CustomOperandNode", "@id": f"{cid}-left-operand",
                                 "urpx:customConditionProperty": prop},
            "urpx:rightOperand": {"@type": "urpx:CustomOperandNode", "@id": f"{cid}-right-operand",
                                  "urpx:stringValue": value}}


def profile_alternatives(v: str) -> dict:
    alts = []
    for region in REGIONS:
        for code, label in CODES:
            a = alternative_id(v, region, code)
            alts.append({
                "@type": "urpx:ProfileAlternative", "@id": a,
                "urpx:name": f"Baseline Region {region}, {label} Allocation",
                "urpx:hasConditionExpression": {
                    "@type": "urpx:ConditionExpression", "@id": f"{a}-condition-expression",
                    "urpx:rootNode": {
                        "@type": "urpx:BooleanOperationNode", "@id": f"{a}-root-node",
                        "urpx:operator": ref("urpx:andOperator"),
                        "urpx:operandNodes": [comparison(f"{a}-region", "baselineRegion", region),
                                              comparison(f"{a}-code", "baselineCode", label)]}}})
    c = f"{v}-pa-baseline-region-code"
    return {
        "@type": "urpx:ProfileAlternatives", "@id": c,
        "urpx:name": "Baseline Region and Basic or All-Electric Allocation (Preliminary Statement Part H, paragraphs 2 and 3)",
        "urpx:hasAlternativeDimensions": {
            "@type": "urpx:AlternativeDimensions", "@id": f"{c}-alternative-dimensions",
            "urpx:hasAlternativeDimension": [
                {"@type": "urpx:AlternativeDimension", "urpx:dimensionDisplayName": "Baseline Region",
                 "urpx:customDimensionProperty": "baselineRegion",
                 "urpx:hasPossibleValues": {"@list": [{"@value": r, "@type": "xsd:string"} for r in REGIONS]}},
                {"@type": "urpx:AlternativeDimension", "urpx:dimensionDisplayName": "Baseline Allocation",
                 "urpx:customDimensionProperty": "baselineCode",
                 "urpx:hasPossibleValues": {"@list": [{"@value": l, "@type": "xsd:string"} for _, l in CODES]}},
            ]},
        "urpx:hasProfileAlternative": alts}


def bracket(bid, season_id, alt, lower=None, lower_op=None, upper=None, upper_op=None):
    b = {"@type": "urpx:ServiceBracket", "@id": bid,
         "urpx:appliesInSeason": ref(season_id),
         "urpx:referencesProfileAlternative": ref(alt)}
    if lower is not None:
        b["urpx:lowerBound"] = lower
        b["urpx:lowerBoundOperator"] = ref(lower_op)
    if upper is not None:
        b["urpx:upperBound"] = upper
        b["urpx:upperBoundOperator"] = ref(upper_op)
    return b


def service_tiers(v: str, date: str) -> dict:
    t1, t2 = [], []
    for season in ("summer", "winter"):
        sid = f"{v}-season-{season}"
        for region in REGIONS:
            for i, (code, _) in enumerate(CODES):
                x = PART_H[date].allocation[season][region][i]
                alt = alternative_id(v, region, code)
                t1.append(bracket(f"{v}-bracket-t1-r{region}-{code}-{season}", sid, alt,
                                  "0", "urpx:greaterThanOrEqualOperator",
                                  x, "urpx:lessThanOrEqualOperator"))
                t2.append(bracket(f"{v}-bracket-t2-r{region}-{code}-{season}", sid, alt,
                                  x, "urpx:greaterThanOperator"))
    return {
        "@type": "urpx:ServiceTiers", "@id": f"{v}-tiers-baseline",
        "urpx:referencesMetricInput": ref(f"{v}-mi-energy-baseline"),
        "urpx:hasServiceTier": [
            {"@type": "urpx:ServiceTier", "@id": f"{v}-tier-baseline-t1",
             "urpx:name": "Tier 1, Baseline Service: kWh per day up to 100 percent of the Baseline Allocation",
             "urpx:serviceTierNumber": 1, "urpx:hasServiceBracket": t1},
            {"@type": "urpx:ServiceTier", "@id": f"{v}-tier-baseline-t2",
             "urpx:name": "Tier 2, Nonbaseline Service: kWh per day above 100 percent of the Baseline Allocation",
             "urpx:serviceTierNumber": 2, "urpx:hasServiceBracket": t2},
        ]}


def insert_after(d: dict, after: str, key: str, value) -> dict:
    out = {}
    for k, x in d.items():
        if k == key:
            continue
        out[k] = x
        if k == after:
            out[key] = value
    if key not in out:
        out[key] = value
    return out


def ladder(sched: str, date: str) -> None:
    p = base_path(sched, date)
    doc = json.loads(p.read_text(encoding="utf-8"))
    for k, t in CONTEXT_TYPES.items():
        doc["@context"].setdefault(k, {"@type": t})
    v = f"sce:{sched}-{date}"
    version = doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]
    pe = version["urpx:hasPlanElements"]

    mis = [m for m in pe["urpx:hasMetricInput"] if m["@id"] != f"{v}-mi-energy-baseline"]
    energy = next(m for m in mis if m["@id"] == f"{v}-mi-energy")
    mis.insert(1, {"@type": "urpx:MetricInput", "@id": f"{v}-mi-energy-baseline",
                   "urpx:name": "kWh Energy Consumption, baseline-tier reference metric",
                   "urpx:metricInputType": ref("urpx:measuredMetricInput"),
                   "urpx:hasMetricSpecification": json.loads(json.dumps(energy["urpx:hasMetricSpecification"]))})
    pe["urpx:hasMetricInput"] = mis

    bm = pe["urpx:hasBillingModel"]
    ledgers = [l for l in bm["urpx:hasLedger"] if l["@id"] != f"{v}-ledger-baseline-credit"]
    at = next(i for i, l in enumerate(ledgers) if l["@id"] == f"{v}-ledger-energy-delivery") + 1
    ledgers.insert(at, {"@type": "urpx:Ledger", "@id": f"{v}-ledger-baseline-credit",
                        "urpx:name": "Baseline Credit",
                        "urpx:ledgerType": ref("urpx:deliveryLedger"),
                        "urpx:referencesMetricInput": ref(f"{v}-mi-energy-baseline")})
    bm["urpx:hasLedger"] = ledgers
    pd = find(bm, f"{v}-pd-baseline-credit")
    pd["urpx:referencesLedger"] = ref(f"{v}-ledger-baseline-credit")
    # ServiceTiers precede the ledgers, as in pge:e-1.
    new_bm = {}
    for k, x in bm.items():
        if k == "urpx:hasServiceTiers":
            continue
        if k == "urpx:hasLedger":
            new_bm["urpx:hasServiceTiers"] = [service_tiers(v, date)]
        new_bm[k] = x
    pe["urpx:hasBillingModel"] = new_bm
    version["urpx:hasPlanElements"] = insert_after(pe, "urpx:hasBillingModel",
                                                   "urpx:hasProfileAlternatives", profile_alternatives(v))

    ps = find(version["urpx:hasPrices"], f"{v}-ps-delivery-surcharges")
    t1 = f"{v}-price-baseline-credit"
    t2 = f"{v}-price-baseline-credit-nonbaseline"
    prices = [x for x in ps["urpx:hasPrice"] if x["@id"] != t2]
    at = next(i for i, x in enumerate(prices) if x["@id"] == t1)
    prices[at]["urpx:serviceTierNumber"] = 1
    prices.insert(at + 1, {"@type": "urpx:Price", "@id": t2,
                           "urpx:referencesPriceDefinition": ref(f"{v}-pd-baseline-credit"),
                           "urpx:name": "Baseline Credit, Tier 2 (above 100 percent of the Baseline Allocation)",
                           "urpx:unitPrice": "0.00000", "urpx:serviceTierNumber": 2})
    ps["urpx:hasPrice"] = prices
    summary = find(ps, f"{v}-summary-discountable")
    inc = [x for x in summary["urpx:includesPrice"] if x["@id"] != t2]
    at = next(i for i, x in enumerate(inc) if x["@id"] == t1)
    inc.insert(at + 1, ref(t2))
    summary["urpx:includesPrice"] = inc
    # The name counts the members; the Baseline Credit is now two of them.
    name = summary["urpx:name"]
    m = re.search(r"The (\d+) bill components the CARE and FERA", name)
    if m:
        n = int(m.group(1))
        summary["urpx:name"] = name.replace(
            m.group(0), f"The {n + 1} Prices (the bill's {n} components, with the Baseline Credit priced on "
                        "both baseline tiers) the CARE and FERA")

    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# --- part 2: the HPWH modifier ---------------------------------------------

def hpwh_path(sched: str, date: str) -> Path:
    return SCE / sched / "versions" / date / f"rate-plan-modifier_sce_{sched}-hpwh_{date}.jsonld"


def hpwh_brackets(v: str, sched: str, date: str) -> list[dict]:
    out = []
    base = f"sce:{sched}-{date}"
    if True:
        for season in ("summer", "winter"):
            for region in REGIONS:
                for i, (code, _) in enumerate(CODES):
                    delta = HPWH[season][i]
                    alt = alternative_id(base, region, code)
                    for tier, prop in (("t1", "urpx:upperBoundOffset"), ("t2", "urpx:lowerBoundOffset")):
                        out.append({
                            "@type": "urpx:ServiceBracket",
                            "@id": f"{v}-bracket-{tier}-r{region}-{code}-{season}",
                            "urpx:adjustsServiceTier": ref(f"{base}-tier-baseline-{tier}"),
                            "urpx:appliesInSeason": ref(f"{v}-season-{season}"),
                            "urpx:referencesProfileAlternative": ref(alt),
                            prop: delta})
    return out


def hpwh(sched: str, date: str, evaluation: str, description: str) -> dict:
    m = f"sce:{sched}-hpwh"
    v = f"{m}-{date}"
    base_doc = json.loads(base_path(sched, date).read_text(encoding="utf-8"))
    ctx = {k: x for k, x in base_doc["@context"].items()}
    for k, t in HPWH_CONTEXT_TYPES.items():
        ctx.setdefault(k, {"@type": t})
    energy_spec = find(base_doc, "sce:ms-energy")
    cx = f"{v}-cx-hpwh-attested"
    base_version = base_doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]
    # In effect exactly when the base version whose tiers it adjusts is.
    window = {k: base_version[k] for k in ("urpx:effectiveDateTime", "urpx:expirationDateTime") if k in base_version}
    return {
        "@context": ctx,
        "@type": "urpx:URPXPackage",
        "@id": f"sce:doc-{sched}-hpwh-{date}",
        "urpx:targetURPXVersion": base_doc["urpx:targetURPXVersion"],
        "urpx:hasRatePlanModifier": {
            "@type": "urpx:RatePlanModifier",
            "@id": m,
            "urpx:name": f"{OPTION[sched]} Heat Pump Water Heater Baseline Allocation (Preliminary Statement Part H)",
            "urpx:modifierUniqueIdentifier": f"{sched.upper()}-HPWH",
            "urpx:initialEffectiveDate": "2022-10-01",
            "urpx:timezoneIdentifier": "America/Los_Angeles",
            "urpx:hasRatePlanModifierVersion": {
                "@type": "urpx:RatePlanModifierVersion",
                "@id": v,
                "urpx:version": date,
                "urpx:modifierVersionNumber": date,
                "urpx:changeReason": ref("urpx:rateCase"),
                "urpx:description": description,
                **window,
                "urpx:priceCurrency": "USD",
                "urpx:commodity": ref("urpx:electricity"),
                "urpx:serviceRole": ref("urpx:bundledServiceRole"),
                "urpx:applicableToRatePlan": [ref(f"sce:{sched}")],
                "urpx:hasDataSourceReference": {
                    "@type": "urpx:DataSourceReference",
                    "@id": f"{v}-data-source-reference",
                    "urpx:fileName": "ELECTRIC_PRELIM_H.pdf",
                    "urpx:mediaType": ref("urpx:applicationPdf"),
                    "urpx:accessURL": PART_H_URL,
                    "urpx:dateRetrieved": PART_H[date].retrieved,
                    "urpx:dataSourceType": ref("urpx:utilityWebsiteSource"),
                    "urpx:pageStart": 2, "urpx:pageEnd": 3,
                    "urpx:leafStart": PART_H[date].leaves[0], "urpx:leafEnd": PART_H[date].leaves[1]},
                "urpx:hasEligibilityRule": [{
                    "@type": "urpx:EligibilityRule",
                    "@id": f"{v}-er-hpwh-attested",
                    "urpx:name": "Customer attesting to having a Heat Pump Water Heater",
                    "urpx:description": ("Preliminary Statement Part H, paragraph 3: \"The applicable Heat Pump Water "
                                         "Heater (HPWH) baseline quantity applies to Customers attesting to having a "
                                         "HPWH and served under either Schedule TOU-D-4-9 or TOU-D-5-8.\" The schedule "
                                         "half is urpx:applicableToRatePlan; the attestation is this condition."),
                    "urpx:hasConditionExpression": {
                        "@type": "urpx:ConditionExpression", "@id": cx,
                        "urpx:rootNode": {
                            "@type": "urpx:ComparisonNode", "@id": f"{cx}-root-node",
                            "urpx:operator": ref("urpx:equalsOperator"),
                            "urpx:leftOperand": {"@type": "urpx:CustomOperandNode",
                                                 "@id": f"{cx}-root-node-left-operand",
                                                 "urpx:customConditionProperty": "Heat Pump Water Heater Attested"},
                            "urpx:rightOperand": {"@type": "urpx:CustomOperandNode",
                                                  "@id": f"{cx}-root-node-right-operand",
                                                  "urpx:booleanValue": True}}}}],
                "urpx:hasPlanElements": {
                    "@type": "urpx:PlanElements",
                    "@id": f"{v}-plan-elements",
                    "urpx:hasSeasons": [
                        {"@type": "urpx:Season", "@id": f"{v}-season-summer", "urpx:seasonName": "Summer",
                         "urpx:month": ["--06", "--07", "--08", "--09"]},
                        {"@type": "urpx:Season", "@id": f"{v}-season-winter", "urpx:seasonName": "Winter",
                         "urpx:month": ["--10", "--11", "--12", "--01", "--02", "--03", "--04", "--05"]}],
                    "urpx:hasMetricInput": [{
                        "@type": "urpx:MetricInput", "@id": f"{v}-mi-energy-baseline",
                        "urpx:name": "kWh Energy Consumption, baseline-tier reference metric",
                        "urpx:metricInputType": ref("urpx:measuredMetricInput"),
                        "urpx:hasMetricSpecification": energy_spec}],
                    "urpx:hasBillingModel": {
                        "@type": "urpx:BillingModel",
                        "@id": f"{v}-plan-elements-billing-model",
                        "urpx:hasServiceTiers": [{
                            "@type": "urpx:ServiceTiers", "@id": f"{v}-tiers-hpwh",
                            "urpx:referencesMetricInput": ref(f"{v}-mi-energy-baseline"),
                            "urpx:hasServiceTier": [{
                                "@type": "urpx:ServiceTier", "@id": f"{v}-tier-hpwh-host",
                                "urpx:name": "Heat Pump Water Heater Allocation, added to the TOU-D baseline ladder",
                                "urpx:hasServiceBracket": hpwh_brackets(v, sched, date)}]}]}},
                "urpx:hasPrices": {"@type": "urpx:Prices", "@id": f"{v}-prices"},
                "urpx:offeredBy": find(base_doc, "org:utility-sce"),
                "urpx:forRatePlanModifier": ref(m),
                "urpx:hasCoverageClaim": {
                    "@id": f"sce:cc-{sched}-hpwh-{date}", "@type": "urpx:CoverageClaim",
                    "urpx:completenessResult": ref("urpx:partial"),
                    "urpx:selfContained": False,
                    "urpx:explainedBy": {
                        "@type": "urpx:Evaluation", "@id": f"sce:cc-{sched}-hpwh-{date}-evaluation",
                        "urpx:evaluationKind": ref("urpx:coverageEvaluation"),
                        "urpx:description": evaluation,
                        "urpx:evaluatedOn": "2026-10-06T00:00:00"}}}}}


# --- part 3: the base filings' prose and manifests --------------------------

OLD_HPWH_SENTENCE = ("Heat Pump Water Heater (HPWH) customers receive an additional baseline allocation per "
                     "Preliminary Statement Part H (modeling deferred \u2014 baseline credit modifier not yet captured).")


def ladder_sentence(sched: str, date: str) -> str:
    v = f"sce:{sched}-{date}"
    return (f"The Baseline Credit applies up to 100 percent of the Baseline Allocation: Tier 1 of {v}-tiers-baseline "
            "carries the Preliminary Statement Part H allocation for each Baseline Region and Basic or All-Electric "
            "Allocation in kWh per day, and the credit is priced on Tier 1 only. The Heat Pump Water Heater "
            f"allocation Part H adds is the modifier sce:{sched}-hpwh, a second document in this filing's directory.")


def ladder_evaluation_sentence(sched: str, date: str) -> str:
    return (" Two things Preliminary Statement Part H states are not represented either: how the kWh-per-day "
            f"allocations bounding Tier 1 of sce:{sched}-{date}-tiers-baseline scale to a billing period, and the "
            "Medical Baseline Allocation it adds to them.")


def prose(sched: str, date: str) -> None:
    p = base_path(sched, date)
    doc = json.loads(p.read_text(encoding="utf-8"))
    version = doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]
    d = version["urpx:description"]
    if OLD_HPWH_SENTENCE in d:
        version["urpx:description"] = d.replace(OLD_HPWH_SENTENCE, ladder_sentence(sched, date))
    ev = version["urpx:hasCoverageClaim"]["urpx:explainedBy"]
    e = ev["urpx:description"]
    opt = OPTION[sched].replace("Schedule TOU-D ", "")
    if date == "2026-03-20" and e.startswith("Three things"):
        head, _, rest = e.partition(" Second, the ")
        rest = rest.replace(" Third, the two pilot", " Second, the two pilot", 1)
        e = f"Two things published for {opt} are not represented in this filing. First, the " + rest
        e += ladder_evaluation_sentence(sched, date)
    elif date == "2025-11-15" and e.startswith("Two provisions"):
        _, _, rest = e.partition(" The second is the ")
        e = f"One provision on the {opt} rate sheets is not represented in this filing: the " + rest
        e = e.replace("Two further rate-sheet lines", "Two rate-sheet lines", 1)
        e += ladder_evaluation_sentence(sched, date)
    ev["urpx:description"] = e
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


NEW_DEFERRALS = [
    ("Preliminary Statement Part H, paragraph 3: \"The total billable baseline quantity is determined based upon "
     "the total number of winter days and total number of summer days during the billing period. Total billable "
     "baseline is then proportionately billed to winter and summer periods based upon the percentage of "
     "customer-consumption registered during the winter and summer seasons.\" The Tier 1 and Tier 2 brackets "
     "carry the Sheet 2 and Sheet 3 quantities as kWh-per-day bounds on a kWh MetricInput, qualified by season, "
     "as pge:e-tou-c does. Nothing in the filing states the daily basis, the multiplication by the "
     "days of each season in a billing period, or the proration by consumption, so a consumer must scale the "
     "bounds to the billing period itself."),
    ("Preliminary Statement Part H, paragraph 4: \"The standard Medical Baseline Allocation will be 16.5 kWh per "
     "day\", provided \"in addition to the applicable Baseline Allocation set forth in Paragraph 3\". Not "
     "modeled: the Tier 1 and Tier 2 bounds here carry the paragraph 3 allocation only, and sce:medical-baseline "
     "carries the Schedule MB-E Wildfire Fund exemption and no allocation. An adjusting-bracket modifier of the "
     "form this filing's HPWH document uses (urpx-org/urpx#80) is the available route."),
]


def extraction_note(sched: str, date: str) -> str:
    v = f"sce:{sched}-{date}"
    h = PART_H[date]
    dated = ("dated by its latest sheets (4 to 6, effective\nAugust 15, 2024)" if h is PART_H_2022
             else "dated by its latest sheets (2 and 3, effective\nOctober 1, 2026)")
    note = f"""
Baseline ladder. The rate sheet footnote ({SHEETS[sched]}):
"The Baseline Credit applies up to 100% of the Baseline Allocation,
regardless of Time-of-Use time period. Additional Baseline Allocations apply
for Customers with Heat Pump Water Heaters served under this Option. The
Baseline Allocation is set forth in Preliminary Statement, Part H." Part H
paragraph 3, Sheet 2 (Cal. P.U.C. Sheet {h.leaves[0]}, summer) and Sheet 3
({h.leaves[1]}, winter), both effective {h.effective} under Advice {h.advice}, gives
them in kWh per day by Baseline Region (5, 6, 8, 9, 10, 13, 14, 15, 16) and
Basic or All-Electric Allocation: 36 cells. Each is a Tier 1 bracket from 0 to
the allocation and a Tier 2 bracket above it in {v}-tiers-baseline,
qualified by the version's season and by a ProfileAlternative on the custom
dimensions baselineRegion and baselineCode. Part H is vendored here as
{h.pdf}, {dated}. The Baseline Credit has its own ledger over the kWh
MetricInput {v}-mi-energy-baseline, priced $({CREDIT[date]}) on Tier 1 and 0
on Tier 2; both Prices are in {v}-summary-discountable.

Heat Pump Water Heater allocation.
rate-plan-modifier_sce_{sched}-hpwh_{date}.jsonld, a second document in this
directory, carries Part H's HPWH Allocation (1.9 kWh per day in summer for
both allocations; 2.6 Basic and 3.0 All-Electric in winter) as adjusting
ServiceBrackets on this version's Tier 1 upper and Tier 2 lower bounds. They
use urpx:adjustsServiceTier, urpx:lowerBoundOffset and urpx:upperBoundOffset,
proposed in urpx-org/urpx#80 and in no URPX release, so the document does not
validate against the v0.5.1 shapes; dev/shacl.sh excepts exactly
the results #80 would remove, under BOUND_OFFSET_EXCEPTION. clj-urpx 0.52.0
resolves the offsets. The modifier is in effect exactly when this version is.
"""
    return note


def manifest(sched: str, date: str) -> None:
    import tomli as tomllib
    p = base_path(sched, date).parent / "tariff.toml"
    text = p.read_text(encoding="utf-8")
    if "[source.prelim_h]" not in text:
        src_start = text.index("[source]\n")
        src_end = text.index("\n\n", src_start)
        body = text[src_start + len("[source]\n"):src_end]
        indented = "\n".join("  " + l for l in body.splitlines())
        pdf = base_path(sched, date).parent / PART_H[date].pdf
        text = (text[:src_start] + "[source]\n\n  [source.base]\n" + indented + "\n\n"
                "  # Preliminary Statement Part H: the Baseline Allocations bounding Tier 1 and the\n"
                "  # HPWH Allocation the second document in this directory adds to them.\n"
                "  [source.prelim_h]\n"
                f"  url = {toml_str(PART_H_URL)}\n"
                f'  sha256 = "{sha256(pdf)}"\n'
                f'  retrieved_on = "{PART_H[date].retrieved}"\n'
                '  media_type = "application/pdf"\n'
                '  filing_type = "advice-letter"\n'
                f'  filing_id = "SCE-AL-{PART_H[date].advice}"' + text[src_end:])
        reg_start = text.index("[regulator]\n")
        reg_end = text.index("\n\n", reg_start)
        body = text[reg_start + len("[regulator]\n"):reg_end]
        indented = "\n".join("  " + l for l in body.splitlines())
        text = (text[:reg_start] + "[regulator]\n  [regulator.base]\n" + indented + "\n\n"
                "  [regulator.prelim_h]\n"
                '  authority = "puc"\n'
                f'  docket = "{PART_H[date].docket}"'
                + text[reg_end:])
        ex = text.index("[extraction]")
        n0 = text.index('notes = """', ex) + len('notes = """')
        n1 = text.index('"""', n0)
        text = text[:n1].rstrip("\n") + "\n" + extraction_note(sched, date) + text[n1:]

    if "\nBaseline ladder" not in text:
        ex = text.index("[extraction]")
        n0 = text.index('notes = """', ex) + len('notes = """')
        n1 = text.index('"""', n0)
        text = text[:n1].rstrip("\n") + "\n" + extraction_note(sched, date) + text[n1:]

    data = tomllib.loads(text)
    stale = [d for d in data["modeling"]["deferrals"]
             if d.startswith(("Baseline Credit", "Heat Pump Water Heater", "Additional Baseline Allocation"))]
    lines = text.split("\n")
    out, in_def = [], False
    for line in lines:
        if line.startswith("deferrals = ["):
            in_def = True
            out.append(line)
            for d in NEW_DEFERRALS:
                entry = " " + toml_str(d) + ","
                if entry not in lines:
                    out.append(entry)
            continue
        if in_def and line == "]":
            in_def = False
        if in_def and line.startswith(' "'):
            if json.loads(line.strip().rstrip(",")) in stale:
                continue
        out.append(line)
    text = "\n".join(out).replace(' "hpwh-baseline",', f' "{sched}-hpwh",')
    tomllib.loads(text)
    p.write_text(text, encoding="utf-8")


def main() -> int:
    for sched in SCHEDULES:
        for date in DATES:
            ladder(sched, date)
            prose(sched, date)
            manifest(sched, date)
            print(f"ladder  {base_path(sched, date).relative_to(REPO)}")
    for sched in SCHEDULES:
      for date in DATES:
        p = hpwh_path(sched, date)
        doc = hpwh(sched, date, hpwh_evaluation(sched, date), hpwh_description(sched, date))
        p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"hpwh    {p.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
