#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Give PG&E E-TOU-C 2026-03-27 the Conservation Incentive Adjustment and the
baseline-allowance matrix its source prices, and move the income tier out.

Sheet 3 of this filing's own PDF prices the Conservation Incentive Adjustment at
($0.02786) on baseline usage and $0.05354 above it, and Sheet 5 (Cal. P.U.C. Sheet
61128-E) carries the baseline quantities over 10 territories x 2 codes x 2
seasons. Neither was in this version: a customer priced from it got no baseline
tiering and no CIA at all. The sibling 2026-03-01 version carries both in a
separate modifier and no counterpart was ever issued here.

WHY THIS GOES IN THE BASE PLAN RATHER THAN A MODIFIER. clj-urpx looks up tier
bounds in one function, called only on the base-plan branch of resolution; a
ledger contributed by a modifier goes down a branch that never calls it. So tiers
placed in a modifier are present in the composed graph and never consulted, which
is the state of the 2026-03-01 overlay and what its manifest records. Placing them
in the base plan is what makes the bounds reachable at the current pin, and is the
shape PG&E E-1 uses.

That costs the one urpx:hasProfileAlternatives container a urpx:PlanElements is
allowed, which this version spends on the income tier that prices the Base
Services Charge. So the income tier moves to a sibling modifier with a container
of its own, exactly as in E-1, and a caller nominates the two independently.

A second document rather than a second modifier in this one, because
urpx.core/load-rate-plan-modifier takes one urpx:RatePlanModifier per document and
the vintage-PCIA modifier already holds that slot here.

SEASON IS ON THE BRACKET, not in tier identity. This schedule draws three rungs
and discriminates each by cell and season, so each tier carries 40 brackets and
names this version's own urpx:Season nodes. E-1 instead folds season into six
tiers; both resolve, and this one keeps the season where the source puts it.

Idempotent: re-running against the files it has written changes nothing.

Run from the repo root:
    python3 scripts/build-pge-e-tou-c-baseline-matrix-2026-03-27.py
"""
from __future__ import annotations

import copy
import json
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

FILING = corpus.filing_dir("pge", "e-tou-c", "2026-03-27")
BASE = FILING / "rate-plan_pge_e-tou-c_2026-03-27.jsonld"
MOD = FILING / "rate-plan-modifier_pge_e-tou-c-income-tier_2026-03-27.jsonld"

V = "pge:e-tou-c-2026-03-27"
MV = "pge:e-tou-c-income-tier-2026-03-27"

# Special Condition 1, Sheet 5 (Cal. P.U.C. Sheet 61128-E), baseline quantities in
# kWh per day. Each value is the Tier 1 boundary; Tier 2 ends at four times it.
# Read from this filing's own PDF and compared against the same table as verified
# from PG&E E-1's Sheet 4: 40 of 40 agree.
#   territory: (Code B summer, Code B winter, Code H summer, Code H winter)
SHEET5 = {
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
TERRITORIES = list(SHEET5)
CODES = ["B", "H"]
TIER2_MULTIPLE = 4
SEASONS = ("summer", "winter")

# Sheet 3. The rung, its tier number, and the adjustment it prices.
RUNGS = [
    ("t1", 1, "-0.02786", "Tier 1, within baseline"),
    ("t2", 2, "0.05354", "Tier 2, over baseline"),
    ("t2c", 3, "0.05354", "Tier 2 Continued, over baseline"),
]

# Everything the base plan hands to the new modifier, named so the move is
# idempotent: a second run finds none of them.
MOVED = {f"{V}-pa-income-tier", f"{V}-ledger-base-charge", f"{V}-pd-base-charge",
         f"{V}-psa-bsc-by-income-tier"}


def quantity(territory: str, code: str, season: str) -> Decimal:
    b_summer, b_winter, h_summer, h_winter = SHEET5[territory]
    return Decimal({("B", "summer"): b_summer, ("B", "winter"): b_winter,
                    ("H", "summer"): h_summer, ("H", "winter"): h_winter}[(code, season)])


def kwh(value: Decimal) -> str:
    """A bound as the sheet prints it, to one decimal place."""
    return str(value.quantize(Decimal("0.1")))


def season_id(season: str) -> str:
    return f"{V}-season-{season}"


# ---------------------------------------------------------------------------
# Baseline territory x code
# ---------------------------------------------------------------------------

def cell_id(territory: str, code: str) -> str:
    return f"{V}-pa-tc-{territory.lower()}-{code.lower()}"


def cell(territory: str, code: str) -> dict:
    """One ProfileAlternative: this territory AND this code.

    Both operands are CustomOperandNode, because neither baseline territory nor
    baseline code is a property URPX names.
    """
    s = cell_id(territory, code)

    def comparison(suffix: str, prop: str, value: str) -> dict:
        n = f"{s}-{suffix}"
        return {
            "@type": "urpx:ComparisonNode", "@id": n,
            "urpx:operator": {"@id": "urpx:equalsOperator"},
            "urpx:leftOperand": {
                "@type": "urpx:CustomOperandNode", "@id": f"{n}-left-operand",
                "urpx:customConditionProperty": prop},
            "urpx:rightOperand": {
                "@type": "urpx:CustomOperandNode", "@id": f"{n}-right-operand",
                "urpx:stringValue": value},
        }

    return {
        "@type": "urpx:ProfileAlternative", "@id": s,
        "urpx:name": f"Baseline Territory {territory}, Code {code}",
        "urpx:hasConditionExpression": {
            "@type": "urpx:ConditionExpression", "@id": f"{s}-condition-expression",
            "urpx:rootNode": {
                "@type": "urpx:BooleanOperationNode", "@id": f"{s}-root-node",
                "urpx:operator": {"@id": "urpx:andOperator"},
                "urpx:operandNodes": [
                    comparison("territory", "baselineTerritory", territory),
                    comparison("code", "baselineCode", code),
                ]}},
    }


def string_values(values: list[str]) -> list[dict]:
    return [{"@value": v, "@type": "xsd:string"} for v in values]


def territory_container() -> dict:
    return {
        "@type": "urpx:ProfileAlternatives", "@id": f"{V}-pa-baseline-territory-code",
        "urpx:name": "Baseline Territory and Baseline Code (Special Condition 1, Sheet 5)",
        "urpx:hasAlternativeDimensions": {
            "@type": "urpx:AlternativeDimensions",
            "@id": f"{V}-pa-baseline-territory-code-alternative-dimensions",
            "urpx:hasAlternativeDimension": [
                {"@type": "urpx:AlternativeDimension",
                 "urpx:dimensionDisplayName": "Baseline Territory",
                 "urpx:customDimensionProperty": "baselineTerritory",
                 "urpx:hasPossibleValues": {"@list": string_values(TERRITORIES)}},
                {"@type": "urpx:AlternativeDimension",
                 "urpx:dimensionDisplayName": "Baseline Code",
                 "urpx:customDimensionProperty": "baselineCode",
                 "urpx:hasPossibleValues": {"@list": string_values(CODES)}},
            ]},
        "urpx:hasProfileAlternative": [cell(t, c) for t in TERRITORIES for c in CODES],
    }


def brackets(rung: str) -> list[dict]:
    """The 40 bounds for one rung: every cell in both seasons."""
    out = []
    for season in SEASONS:
        for territory in TERRITORIES:
            for code in CODES:
                q = quantity(territory, code, season)
                b = {"@type": "urpx:ServiceBracket",
                     "@id": f"{V}-bracket-{rung}-{territory.lower()}-{code.lower()}-{season}",
                     "urpx:appliesInSeason": {"@id": season_id(season)},
                     "urpx:referencesProfileAlternative": {"@id": cell_id(territory, code)}}
                if rung == "t1":
                    b["urpx:lowerBound"] = "0"
                    b["urpx:lowerBoundOperator"] = {"@id": "urpx:greaterThanOrEqualOperator"}
                    b["urpx:upperBound"] = kwh(q)
                    b["urpx:upperBoundOperator"] = {"@id": "urpx:lessThanOrEqualOperator"}
                elif rung == "t2":
                    b["urpx:lowerBound"] = kwh(q)
                    b["urpx:lowerBoundOperator"] = {"@id": "urpx:greaterThanOperator"}
                    b["urpx:upperBound"] = kwh(q * TIER2_MULTIPLE)
                    b["urpx:upperBoundOperator"] = {"@id": "urpx:lessThanOrEqualOperator"}
                else:
                    b["urpx:lowerBound"] = kwh(q * TIER2_MULTIPLE)
                    b["urpx:lowerBoundOperator"] = {"@id": "urpx:greaterThanOperator"}
                out.append(b)
    return out


def tiers_container() -> dict:
    return {
        "@type": "urpx:ServiceTiers", "@id": f"{V}-tiers-baseline",
        "urpx:referencesMetricInput": {"@id": f"{V}-mi-energy-baseline"},
        "urpx:hasServiceTier": [
            {"@type": "urpx:ServiceTier", "@id": f"{V}-tier-baseline-{rung}",
             "urpx:name": f"Tier {number}, {label.split(', ', 1)[1]}",
             "urpx:serviceTierNumber": number,
             "urpx:hasServiceBracket": brackets(rung)}
            for rung, number, _price, label in RUNGS],
    }


def baseline_metric_input() -> dict:
    return {
        "@type": "urpx:MetricInput", "@id": f"{V}-mi-energy-baseline",
        "urpx:name": "Energy consumption (kWh), baseline-tier reference metric",
        "urpx:metricInputType": {"@id": "urpx:measuredMetricInput"},
        "urpx:hasMetricSpecification": {
            "@type": "urpx:MetricSpecification", "@id": f"{V}-ms-energy-baseline",
            "urpx:commodity": {"@id": "urpx:electricity"},
            "urpx:measurementKind": {"@id": "urpx:energy"},
            "urpx:unitOfMeasure": {"@id": "urpx:kWh"}},
    }


def cia_ledger() -> dict:
    return {
        "@type": "urpx:Ledger", "@id": f"{V}-ledger-cia",
        "urpx:name": "Conservation Incentive Adjustment",
        "urpx:ledgerType": {"@id": "urpx:bundledLedger"},
        "urpx:referencesMetricInput": {"@id": f"{V}-mi-energy-baseline"},
    }


def cia_price_definition() -> dict:
    return {
        "@type": "urpx:PriceDefinition", "@id": f"{V}-pd-cia",
        "urpx:name": "Conservation Incentive Adjustment",
        "urpx:chargeType": {"@id": "urpx:conservationCharge"},
        "urpx:chargeCategory": {"@id": "urpx:adjustment"},
        "urpx:billPortion": {"@id": "urpx:bundledPortion"},
        "urpx:referencesLedger": {"@id": f"{V}-ledger-cia"},
    }


def cia_prices() -> list[dict]:
    return [{"@type": "urpx:Price", "@id": f"{V}-price-cia-{rung}",
             "urpx:referencesPriceDefinition": {"@id": f"{V}-pd-cia"},
             "urpx:name": f"Conservation Incentive Adjustment, {label}",
             "urpx:unitPrice": price,
             "urpx:serviceTierNumber": number}
            for rung, number, price, label in RUNGS]


# ---------------------------------------------------------------------------

def rescope(subtrees: list, old_prefix: str, new_prefix: str) -> list:
    """Move a set of nodes into another version's IRI space.

    Every @id under these subtrees that starts with `old_prefix` is renamed, and
    every reference to one of those @ids is rewritten with it. References to
    anything else, such as the pge:program-care enrollments the income cells
    name, are left alone: a node that belongs to the base plan keeps its name.
    Without this the moved container would keep an @id naming the base version
    while living in the modifier's document, and a caller nominating it would
    have to key on the wrong version.
    """
    renamed: dict[str, str] = {}

    def collect(x):
        if isinstance(x, dict):
            i = x.get("@id")
            if isinstance(i, str) and i.startswith(old_prefix):
                renamed[i] = new_prefix + i[len(old_prefix):]
            for v in x.values():
                collect(v)
        elif isinstance(x, list):
            for v in x:
                collect(v)

    def rewrite(x):
        if isinstance(x, dict):
            return {k: (renamed.get(v, v) if k == "@id" and isinstance(v, str) else rewrite(v))
                    for k, v in x.items()}
        if isinstance(x, list):
            return [rewrite(v) for v in x]
        return x

    for t in subtrees:
        collect(t)
    return [rewrite(t) for t in subtrees]


def add_option(version: dict, key: str, iri: str) -> None:
    current = version.get(key) or []
    current = current if isinstance(current, list) else [current]
    if not any(x.get("@id") == iri for x in current):
        current.append({"@id": iri})
    version[key] = current


def modifier_document(context: dict, borrowed: dict) -> dict:
    """The sibling document carrying the Base Services Charge by income tier."""
    return {
        "@context": copy.deepcopy(context),
        "@graph": [{
            "@id": "pge:doc-e-tou-c-income-tier-2026-03-27", "@type": "urpx:URPXPackage",
            "urpx:targetURPXVersion": borrowed["target"],
            "urpx:hasRatePlanModifier": {
                "@type": "urpx:RatePlanModifier", "@id": "pge:e-tou-c-income-tier",
                "urpx:name": "E-TOU-C Base Services Charge by income tier",
                "urpx:initialEffectiveDate": "2026-03-27",
                "urpx:timezoneIdentifier": "America/Los_Angeles",
                "urpx:modifierUniqueIdentifier": "E-TOU-C-INCOME-TIER",
                "urpx:hasRatePlanModifierVersion": {
                    "@type": "urpx:RatePlanModifierVersion", "@id": MV,
                    "urpx:modifierVersionNumber": "2026-03-27",
                    "urpx:description": (
                        "The Base Services Charge of Schedule E-TOU-C, a flat amount per "
                        "customer per day at three income tiers: 0.19713 for Income Tier 1 "
                        "(CARE), 0.39688 for Income Tier 2 (FERA) and 0.79343 for Income Tier "
                        "3, per Sheet 1. Every E-TOU-C customer pays one of the three, so "
                        "this modifier is not elective. It is separate from the base plan "
                        "because urpx:PlanElements allows one urpx:hasProfileAlternatives "
                        "container and the base plan spends its container on the baseline "
                        "Territory by Code matrix, which is the only dimension its "
                        "urpx:ServiceBracket bounds can be qualified by. A caller nominates "
                        "income tier here and baseline Territory and Code on the base plan."),
                    "urpx:changeReason": {"@id": "urpx:rateCase"},
                    "urpx:effectiveDateTime": borrowed["effective"],
                    "urpx:priceCurrency": "USD",
                    "urpx:commodity": {"@id": "urpx:electricity"},
                    "urpx:serviceRole": {"@id": "urpx:bundledServiceRole"},
                    "urpx:applicableToRatePlan": [{"@id": "pge:e-tou-c"}],
                    "urpx:applicableToRatePlanVersion": [{"@id": V}],
                    "urpx:hasDataSourceReference": copy.deepcopy(borrowed["source"]),
                    "urpx:hasPlanElements": {
                        "@type": "urpx:PlanElements", "@id": f"{MV}-plan-elements",
                        "urpx:hasMetricInput": [{
                            "@type": "urpx:MetricInput", "@id": f"{MV}-mi-meter-count",
                            "urpx:name": "Per Meter Prices",
                            "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
                            "urpx:profileMetricProperty": {"@id": "urpx:meterCount"},
                        }],
                        "urpx:hasBillingModel": {
                            "@type": "urpx:BillingModel", "@id": f"{MV}-billing-model",
                            "urpx:hasLedger": [borrowed["bsc_ledger"]],
                            "urpx:hasPriceDefinition": [borrowed["bsc_pd"]]},
                        "urpx:hasProfileAlternatives": borrowed["income_container"],
                    },
                    "urpx:hasPrices": {
                        "@type": "urpx:Prices", "@id": f"{MV}-prices",
                        "urpx:hasPriceSetAlternatives": [borrowed["bsc_psa"]]},
                    "urpx:offeredBy": copy.deepcopy(borrowed["offered_by"]),
                    "urpx:forRatePlanModifier": {"@id": "pge:e-tou-c-income-tier"},
                    "urpx:hasCoverageClaim": {
                        "@id": "pge:cc-e-tou-c-income-tier-2026-03-27",
                        "@type": "urpx:CoverageClaim",
                        "urpx:completenessResult": {"@id": "urpx:partial"},
                        "urpx:selfContained": True,
                        "urpx:explainedBy": {
                            "@type": "urpx:Evaluation",
                            "@id": "pge:cc-e-tou-c-income-tier-2026-03-27-evaluation",
                            "urpx:evaluationKind": {"@id": "urpx:coverageEvaluation"},
                            "urpx:description": (
                                "The three income-tier amounts are carried and are what a "
                                "customer is billed. Income Tier 2 is narrower here than on "
                                "Sheet 1: it is gated on FERA enrollment alone, and Sheet 1 "
                                "admits a second branch, a resident of an affordable rental "
                                "unit in the California Housing Partnership database "
                                "restricted to 80 percent of Area Median Income, who resolves "
                                "to Tier 3 here and is billed 0.79343 rather than 0.39688. "
                                "Recorded in the filing's tariff.toml."),
                        }},
                }}}]}


def main() -> int:
    doc = json.loads(BASE.read_text())
    package = next(n for n in doc["@graph"] if n.get("@type") == "urpx:URPXPackage")
    version = package["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]
    elements = version["urpx:hasPlanElements"]
    billing = elements["urpx:hasBillingModel"]

    # What the Base Services Charge needs, before its container slot is taken.
    income_container = elements["urpx:hasProfileAlternatives"]
    assert income_container["@id"] == f"{V}-pa-income-tier", income_container["@id"]
    bsc_ledger = next(n for n in billing["urpx:hasLedger"]
                      if n["@id"] == f"{V}-ledger-base-charge")
    bsc_pd = next(n for n in billing["urpx:hasPriceDefinition"]
                  if n["@id"] == f"{V}-pd-base-charge")
    psas = version["urpx:hasPrices"].get("urpx:hasPriceSetAlternatives") or []
    psas = psas if isinstance(psas, list) else [psas]
    bsc_psa = next(n for n in psas if n["@id"] == f"{V}-psa-bsc-by-income-tier")

    borrowed = {
        "target": package["urpx:targetURPXVersion"],
        "effective": version["urpx:effectiveDateTime"],
        "source": version["urpx:hasDataSourceReference"],
        "offered_by": version["urpx:offeredBy"],
    }
    moved = rescope([copy.deepcopy(income_container), copy.deepcopy(bsc_ledger),
                     copy.deepcopy(bsc_pd), copy.deepcopy(bsc_psa)], V, MV)
    borrowed["income_container"], borrowed["bsc_ledger"] = moved[0], moved[1]
    borrowed["bsc_pd"], borrowed["bsc_psa"] = moved[2], moved[3]

    # The bounds are decimals and the @context is what says so. Without these two
    # terms every bound serializes as xsd:string and SHACL reports one
    # DatatypeConstraintComponent per literal: 200 of them, silently, since the
    # document is otherwise well formed.
    for term in ("urpx:lowerBound", "urpx:upperBound"):
        doc["@context"].setdefault(term, {"@type": "xsd:decimal"})

    # The base plan keeps the matrix and gains the adjustment it prices.
    elements["urpx:hasProfileAlternatives"] = territory_container()
    mis = elements["urpx:hasMetricInput"]
    mis = mis if isinstance(mis, list) else [mis]
    if not any(m.get("@id") == f"{V}-mi-energy-baseline" for m in mis):
        mis.append(baseline_metric_input())
    elements["urpx:hasMetricInput"] = mis

    billing["urpx:hasLedger"] = [n for n in billing["urpx:hasLedger"]
                                 if n.get("@id") not in MOVED]
    if not any(n.get("@id") == f"{V}-ledger-cia" for n in billing["urpx:hasLedger"]):
        billing["urpx:hasLedger"].append(cia_ledger())
    billing["urpx:hasPriceDefinition"] = [n for n in billing["urpx:hasPriceDefinition"]
                                          if n.get("@id") not in MOVED]
    if not any(n.get("@id") == f"{V}-pd-cia" for n in billing["urpx:hasPriceDefinition"]):
        billing["urpx:hasPriceDefinition"].append(cia_price_definition())
    billing["urpx:hasServiceTiers"] = tiers_container()

    prices = version["urpx:hasPrices"]
    kept = [n for n in psas if n.get("@id") not in MOVED]
    if kept:
        prices["urpx:hasPriceSetAlternatives"] = kept
    else:
        prices.pop("urpx:hasPriceSetAlternatives", None)
    bare = prices.get("urpx:hasPrice") or []
    bare = bare if isinstance(bare, list) else [bare]
    have = {n.get("@id") for n in bare}
    bare += [p for p in cia_prices() if p["@id"] not in have]
    prices["urpx:hasPrice"] = bare

    add_option(version, "urpx:hasModifierOptions", "pge:e-tou-c-income-tier")
    add_option(version, "urpx:hasModifierVersionOptions", MV)

    BASE.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    MOD.write_text(json.dumps(modifier_document(doc["@context"], borrowed),
                              indent=2, ensure_ascii=False) + "\n")

    tiers = billing["urpx:hasServiceTiers"]["urpx:hasServiceTier"]
    bounds = sum(len(t["urpx:hasServiceBracket"]) for t in tiers)
    print(f"{BASE.name}: {len(territory_container()['urpx:hasProfileAlternative'])} cells, "
          f"{bounds} brackets across {len(tiers)} tiers, {len(cia_prices())} CIA prices")
    print(f"{MOD.name}: Base Services Charge at three income tiers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
