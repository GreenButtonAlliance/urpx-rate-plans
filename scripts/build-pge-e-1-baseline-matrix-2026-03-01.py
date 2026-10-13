#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Write PG&E E-1's full baseline-allowance matrix, and move the income tier out.

Schedule E-1 Special Condition 2, Sheet 4 (Cal. P.U.C. Sheet 61099-E) prices a
baseline allowance over 10 territories x 2 codes (B basic, H all-electric) x 2
seasons: 40 kWh/day values, each the Tier 1 boundary, with Tier 2 ending at four
times it. Until this script ran, the filing carried ONE of the 40, Territory P
Code B, so the tier boundaries were wrong for nine of ten territories and for
every all-electric customer. That is what this builds: 20 ProfileAlternative
cells over two AlternativeDimension nodes, and 20 cell-scoped ServiceBrackets on
each of the six existing ServiceTiers, 120 in all.

WHY THE INCOME TIER MOVES TO ITS OWN DOCUMENT. urpx:PlanElements carries
sh:maxCount 1 on urpx:hasProfileAlternatives, so a version has exactly one
container to select on, and this filing already spent it on the income tier
(CARE / FERA / standard) that prices the Base Services Charge. Both dimensions
are real and neither is optional, so one of them has to move to a sibling version
with a container of its own. The baseline matrix stays in the base plan because
it sets the tier boundaries the energy price depends on, which is what a consumer
computing a marginal price needs; the Base Services Charge is a flat daily amount
that does not vary with usage. So the base plan keeps the matrix and a new
sibling urpx:RatePlanModifier carries the Base Services Charge.

Two consequences, both stated rather than hidden:

  - A consumer resolving the base plan ALONE gets no Base Services Charge. The
    charge is mandatory for every E-1 customer, and URPX has no way to say a
    modifier is required: urpx:hasModifierOptions is the only link and the word
    is accurate about what it expresses. Recorded as a deferral in tariff.toml,
    which is where the CoverageClaim Evaluation is generated from.
  - Three approaches that would have kept the charge in the base plan were tried
    against the shapes and the consumer first. Gating three Prices on program
    enrollment with urpx:hasApplicabilityGroup validates, and clj-urpx 0.32.0
    does not evaluate those predicates: price.clj's condition-gates MARKS them
    and the Price then "fires UNCONDITIONALLY at resolution", so all three daily
    charges would apply at once and every customer would be billed their sum.
    Pricing the charge in the base at the Tier 3 amount and re-pricing it in the
    modifier has no precedent in this corpus to measure against: no modifier in
    the 34 we have prices a PriceDefinition its base defines. And carrying the
    matrix in a modifier instead, the shape sibling e-tou-c uses, leaves the
    base plan's own six brackets as a second source of tier bounds.

SEASON IS STILL NOT IN THE DATA. Each bracket names a cell and nothing else:
season stays where this filing already keeps it, in the identity of the six
tiers (three summer rungs, three winter rungs). Writing urpx:appliesInSeason on
all 120 is now possible, since clj-urpx 0.32.0 selects on it and this filing
declares its own two urpx:Season nodes, but it is a separate change with its own
resolution consequences and tariff.toml still carries the deferral saying season
is absent from the machine-readable data.

Idempotent: re-running against the files it has already written is a no-op.

Run from the repo root:
    python3 scripts/build-pge-e-1-baseline-matrix-2026-03-01.py
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

FILING = corpus.filing_dir("pge", "e-1", "2026-03-01")
BASE = FILING / "rate-plan_pge_e-1_2026-03-01.jsonld"
MOD = FILING / "rate-plan-modifier_pge_e-1-income-tier_2026-03-01.jsonld"

V = "pge:e-1-2026-03-01"          # the base RatePlanVersion
MV = "pge:e-1-income-tier-2026-03-01"  # the new RatePlanModifierVersion

# Special Condition 2, Sheet 4 (Cal. P.U.C. Sheet 61099-E), Baseline Quantities
# in kWh per day. Each value is the Tier 1 boundary; Tier 2 ends at 4x it.
# Verified against this filing's own PDF on 2026-09-23: 40 of 40 agree.
#   territory: (Code B summer, Code B winter, Code H summer, Code H winter)
SHEET4 = {
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
TERRITORIES = list(SHEET4)
CODES = ["B", "H"]
TIER2_MULTIPLE = 4

# Base Services Charge, dollars per customer per day, Sheet 1 (61247-E).
BSC = [
    ("tier-1", "care", "0.19713", "Income Tier 1 (CARE-eligible)"),
    ("tier-2", "fera", "0.39688", "Income Tier 2 (FERA-eligible)"),
    ("tier-3", "standard", "0.79343", "Income Tier 3 (no qualifying enrollment)"),
]

# Everything the base plan hands to the new modifier. Named so the move is
# idempotent: a second run finds none of them and changes nothing.
MOVED = {
    f"{V}-pa-income-tier", f"{V}-ledger-base-charge", f"{V}-pd-base-charge",
    f"{V}-psa-bsc-by-income-tier",
}

TIERS_CONTAINER = f"{V}-tiers-baseline"


def quantity(territory: str, code: str, season: str) -> Decimal:
    b_summer, b_winter, h_summer, h_winter = SHEET4[territory]
    return Decimal({("B", "summer"): b_summer, ("B", "winter"): b_winter,
                    ("H", "summer"): h_summer, ("H", "winter"): h_winter}[(code, season)])


def kwh(value: Decimal) -> str:
    """A bound as the sheet prints it, to one decimal place."""
    return str(value.quantize(Decimal("0.1")))


# ---------------------------------------------------------------------------
# Baseline territory x code, in the base plan
# ---------------------------------------------------------------------------

def cell_id(territory: str, code: str) -> str:
    return f"{V}-pa-tc-{territory.lower()}-{code.lower()}"


def cell(territory: str, code: str) -> dict:
    """One ProfileAlternative: this territory AND this code.

    Both operands are CustomOperandNode with urpx:customConditionProperty,
    the same shape the sibling e-tou-c baseline-tier modifier uses, because
    neither baseline territory nor baseline code is a named URPX property.
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
    """Possible values as typed literals, the form the sibling overlay uses."""
    return [{"@value": v, "@type": "xsd:string"} for v in values]


def territory_container() -> dict:
    return {
        "@type": "urpx:ProfileAlternatives", "@id": f"{V}-pa-baseline-territory-code",
        "urpx:name": "Baseline Territory and Baseline Code (Special Condition 2, Sheet 4)",
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


def brackets(season: str, rung: str) -> list[dict]:
    """The 20 cell-scoped bounds for one tier.

    No urpx:appliesInSeason: `season` picks the column of Sheet 4 to read,
    and the tier this sits on is the one that carries the season.
    """
    out = []
    for territory in TERRITORIES:
        for code in CODES:
            q = quantity(territory, code, season)
            b = {"@type": "urpx:ServiceBracket",
                 "@id": f"{V}-bracket-{season}-{rung}-{territory.lower()}-{code.lower()}",
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
            else:                                    # t2c, the unbounded top rung
                b["urpx:lowerBound"] = kwh(q * TIER2_MULTIPLE)
                b["urpx:lowerBoundOperator"] = {"@id": "urpx:greaterThanOperator"}
            out.append(b)
    return out


# ---------------------------------------------------------------------------
# Income tier, in its own document
# ---------------------------------------------------------------------------

def enrollment_comparison(suffix: str, operator: str, program: str) -> dict:
    n = f"{MV}-cn-{suffix}"
    return {
        "@type": "urpx:ComparisonNode", "@id": n,
        "urpx:operator": {"@id": operator},
        "urpx:leftOperand": {
            "@type": "urpx:ObjectOperandNode", "@id": f"{n}-left-operand",
            "urpx:conditionProperty": {"@id": "urpx:hasProgramEnrollment"}},
        "urpx:rightOperand": {
            "@type": "urpx:ObjectOperandNode", "@id": f"{n}-right-operand",
            "urpx:referencesValue": {"@id": program}},
    }


def income_cell(slug: str, name: str, root: dict) -> dict:
    return {
        "@type": "urpx:ProfileAlternative", "@id": f"{MV}-pa-income-tier-{slug}",
        "urpx:name": name,
        "urpx:hasConditionExpression": {
            "@type": "urpx:ConditionExpression",
            "@id": f"{MV}-cx-income-tier-{slug}", "urpx:rootNode": root},
    }


def income_container() -> dict:
    return {
        "@type": "urpx:ProfileAlternatives", "@id": f"{MV}-pa-income-tier",
        "urpx:name": "Income tier (CARE / FERA / standard)",
        "urpx:hasAlternativeDimensions": {
            "@type": "urpx:AlternativeDimensions",
            "@id": f"{MV}-pa-income-tier-alternative-dimensions",
            "urpx:hasAlternativeDimension": [{
                "@type": "urpx:AlternativeDimension",
                "urpx:dimensionDisplayName": "Program Enrollment",
                "urpx:dimensionProperty": "https://urpx.org/ns/ontology/hasProgramEnrollment",
                "urpx:hasPossibleValues": {"@list": [{"@id": "pge:program-care"},
                                                     {"@id": "pge:program-fera"}]},
            }]},
        "urpx:hasProfileAlternative": [
            income_cell("care", "Income Tier 1, CARE-eligible",
                        enrollment_comparison("care", "urpx:equalsOperator",
                                              "pge:program-care")),
            income_cell("fera", "Income Tier 2, FERA-eligible",
                        enrollment_comparison("fera", "urpx:equalsOperator",
                                              "pge:program-fera")),
            income_cell("standard", "Income Tier 3, neither CARE nor FERA", {
                "@type": "urpx:BooleanOperationNode", "@id": f"{MV}-bn-income-tier-standard",
                "urpx:operator": {"@id": "urpx:andOperator"},
                "urpx:operandNodes": [
                    enrollment_comparison("not-care", "urpx:notEqualsOperator",
                                          "pge:program-care"),
                    enrollment_comparison("not-fera", "urpx:notEqualsOperator",
                                          "pge:program-fera"),
                ]}),
        ],
    }


def modifier_document(context: dict, base_version: dict) -> dict:
    """The sibling document carrying the Base Services Charge.

    Everything it needs is its own, including a meter-count MetricInput: a
    urpx:PlanElements requires at least one, and the sibling vintage-PCIA
    modifier in the base document mints its own rather than naming the base
    plan's for the same reason.
    """
    return {
        "@context": copy.deepcopy(context),
        "@graph": [{
            "@id": "pge:doc-e-1-income-tier-2026-03-01", "@type": "urpx:URPXPackage",
            "urpx:targetURPXVersion": base_version["_target"],
            "urpx:hasRatePlanModifier": {
                "@type": "urpx:RatePlanModifier", "@id": "pge:e-1-income-tier",
                "urpx:name": "E-1 Base Services Charge by income tier",
                "urpx:initialEffectiveDate": "2026-03-01",
                "urpx:timezoneIdentifier": "America/Los_Angeles",
                "urpx:modifierUniqueIdentifier": "E-1-INCOME-TIER",
                "urpx:hasRatePlanModifierVersion": {
                    "@type": "urpx:RatePlanModifierVersion", "@id": MV,
                    "urpx:modifierVersionNumber": "2026-03-01",
                    "urpx:description": (
                        "The Base Services Charge of Schedule E-1, a flat amount per customer "
                        "per day at three income tiers: 0.19713 for Income Tier 1 (CARE), "
                        "0.39688 for Income Tier 2 (FERA) and 0.79343 for Income Tier 3, per "
                        "Sheet 1 (Cal. P.U.C. Sheet 61247-E). Every E-1 customer pays one of "
                        "the three, so this modifier is not elective; it is separate from the "
                        "base plan because urpx:PlanElements allows one "
                        "urpx:hasProfileAlternatives container and the base plan spends its "
                        "container on the 20-cell baseline Territory x Code matrix that sets "
                        "the energy tier boundaries. A caller nominates income tier here and "
                        "baseline Territory and Code on the base plan, one container each."),
                    "urpx:changeReason": {"@id": "urpx:rateCase"},
                    "urpx:effectiveDateTime": base_version["_effective"],
                    "urpx:priceCurrency": "USD",
                    "urpx:commodity": {"@id": "urpx:electricity"},
                    "urpx:serviceRole": {"@id": "urpx:bundledServiceRole"},
                    # BOTH ARE LISTS, and a bare object is not the same thing to a
                    # consumer even though JSON-LD expands the two identically.
                    # urpx.arrangements/applicability reads them with
                    # (keep :jsonld/id coll); over a bare map that iterates
                    # MapEntry values and yields the empty set, so the modifier
                    # would pair with no base at all while validating clean and
                    # raising nothing. Measured at clj-urpx 0.32.0. All 33 other
                    # modifier filings in this corpus use lists.
                    "urpx:applicableToRatePlan": [{"@id": "pge:e-1"}],
                    "urpx:applicableToRatePlanVersion": [{"@id": V}],
                    "urpx:hasDataSourceReference": copy.deepcopy(base_version["_source"]),
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
                            "urpx:hasLedger": [{
                                "@type": "urpx:Ledger", "@id": f"{MV}-ledger-base-charge",
                                "urpx:name": "Base Services Charge",
                                "urpx:ledgerType": {"@id": "urpx:bundledLedger"},
                                "urpx:referencesMetricInput": {"@id": f"{MV}-mi-meter-count"},
                            }],
                            "urpx:hasPriceDefinition": [{
                                "@type": "urpx:PriceDefinition", "@id": f"{MV}-pd-base-charge",
                                "urpx:name": "Base Services Charge",
                                "urpx:chargeType": {"@id": "urpx:minimumBill"},
                                "urpx:chargeCategory": {"@id": "urpx:serviceCharge"},
                                "urpx:billPortion": {"@id": "urpx:bundledPortion"},
                                "urpx:baseQuantity": "1",
                                "urpx:hasCalculationMethod": {
                                    "@type": "urpx:CalculationMethod",
                                    "@id": f"{MV}-pd-base-charge-calculation-method",
                                    "urpx:intervalDuration": "P1D"},
                                "urpx:referencesLedger": {"@id": f"{MV}-ledger-base-charge"},
                            }]},
                        "urpx:hasProfileAlternatives": income_container(),
                    },
                    "urpx:hasPrices": {
                        "@type": "urpx:Prices", "@id": f"{MV}-prices",
                        "urpx:hasPriceSetAlternatives": [{
                            "@type": "urpx:PriceSetAlternatives",
                            "@id": f"{MV}-psa-bsc-by-income-tier",
                            "urpx:name": "Base Services Charge by income tier",
                            "urpx:referencesProfileAlternatives": {"@id": f"{MV}-pa-income-tier"},
                            "urpx:hasPriceSetAlternative": [
                                {"@type": "urpx:PriceSetAlternative",
                                 "@id": f"{MV}-psa-bsc-{slug}",
                                 "urpx:referencesProfileAlternative": {
                                     "@id": f"{MV}-pa-income-tier-{cell}"},
                                 "urpx:hasPrice": [{
                                     "@type": "urpx:Price",
                                     "@id": f"{MV}-price-base-charge-{slug}",
                                     "urpx:referencesPriceDefinition": {
                                         "@id": f"{MV}-pd-base-charge"},
                                     "urpx:startDate": "2026-03-01",
                                     "urpx:name": f"Base Services Charge, {label}",
                                     "urpx:unitPrice": price}]}
                                for slug, cell, price, label in BSC
                            ]}]},
                    "urpx:offeredBy": copy.deepcopy(base_version["_offered_by"]),
                    "urpx:forRatePlanModifier": {"@id": "pge:e-1-income-tier"},
                    "urpx:hasCoverageClaim": {
                        "@id": "pge:cc-e-1-income-tier-2026-03-01",
                        "@type": "urpx:CoverageClaim",
                        "urpx:completenessResult": {"@id": "urpx:partial"},
                        "urpx:selfContained": True,
                        "urpx:explainedBy": {
                            "@type": "urpx:Evaluation",
                            "@id": "pge:cc-e-1-income-tier-2026-03-01-evaluation",
                            "urpx:evaluationKind": {"@id": "urpx:coverageEvaluation"},
                            "urpx:description": (
                                "The three income-tier totals are carried and are the amounts "
                                "a customer is billed. Sheet 3 (Cal. P.U.C. Sheet 61098-E) also "
                                "publishes the same charge by component, 4 components x 3 income "
                                "tiers = 12 values, and none of the 12 appears here. The "
                                "components sum to the totals, so no bill is wrong; the "
                                "published unbundling is absent. Income Tier 2 is also narrower "
                                "here than on Sheet 1: it is gated on FERA enrollment alone, "
                                "and Sheet 1 admits a second branch, a resident of an "
                                "affordable rental unit in the California Housing Partnership "
                                "database restricted to 80 percent of Area Median Income, who "
                                "resolves to Tier 3 here and is billed 0.79343 rather than "
                                "0.39688. Both are listed in the filing's tariff.toml "
                                "[modeling].deferrals."),
                        }},
                }},
        }],
    }


# ---------------------------------------------------------------------------

def add_option(version: dict, key: str, iri: str) -> None:
    current = version.get(key) or []
    current = current if isinstance(current, list) else [current]
    if not any(x.get("@id") == iri for x in current):
        current.append({"@id": iri})
    version[key] = current


def main() -> int:
    doc = json.loads(BASE.read_text())
    package = next(n for n in doc["@graph"] if n.get("@type") == "urpx:URPXPackage")
    version = package["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]
    elements = version["urpx:hasPlanElements"]
    billing = elements["urpx:hasBillingModel"]

    # The baseline matrix takes the base plan's one container.
    elements["urpx:hasProfileAlternatives"] = territory_container()

    # Everything the Base Services Charge needs leaves.
    for key in ("urpx:hasLedger", "urpx:hasPriceDefinition"):
        billing[key] = [n for n in billing[key] if n.get("@id") not in MOVED]
    prices = version["urpx:hasPrices"]
    kept = [n for n in (prices.get("urpx:hasPriceSetAlternatives") or [])
            if n.get("@id") not in MOVED]
    if kept:
        prices["urpx:hasPriceSetAlternatives"] = kept
    else:
        prices.pop("urpx:hasPriceSetAlternatives", None)

    # 20 bounds per tier, on the six tiers already there. The container's old @id
    # named the one cell it used to hold.
    tiers = billing["urpx:hasServiceTiers"]
    tiers["@id"] = TIERS_CONTAINER
    for tier in tiers["urpx:hasServiceTier"]:
        _, season, rung = tier["@id"].split(":", 1)[1].split("-", 2)
        tier["urpx:hasServiceBracket"] = brackets(season, rung)

    add_option(version, "urpx:hasModifierOptions", "pge:e-1-income-tier")
    add_option(version, "urpx:hasModifierVersionOptions", MV)

    borrowed = {"_target": package["urpx:targetURPXVersion"],
                "_effective": version["urpx:effectiveDateTime"],
                "_source": version["urpx:hasDataSourceReference"],
                "_offered_by": version["urpx:offeredBy"]}

    BASE.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    MOD.write_text(json.dumps(modifier_document(doc["@context"], borrowed),
                              indent=2, ensure_ascii=False) + "\n")

    cells = len(elements["urpx:hasProfileAlternatives"]["urpx:hasProfileAlternative"])
    bounds = sum(len(t["urpx:hasServiceBracket"]) for t in tiers["urpx:hasServiceTier"])
    print(f"{BASE.name}: {cells} baseline cells, {bounds} brackets across "
          f"{len(tiers['urpx:hasServiceTier'])} tiers")
    print(f"{MOD.name}: Base Services Charge at {len(BSC)} income tiers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
