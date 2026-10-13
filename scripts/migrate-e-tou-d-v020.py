#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""
One-shot migration: PG&E E-TOU-D filing → URPX v0.2.0-candidate shape.

In-place rewrite of rate-plan_pge_e-tou-d_2026-03-27.jsonld.

Transformations:
  1. Add ProgramEnrollment instances for CCA, DA, TBS
  2. Add RateCase for CPUC Decision D.26-03-013; reference from base RPV + modifier RPMV
  3. Replace base EligibilityRule's hasCustomerProfile with hasConditionExpression
     (residential customer kind)
  4. Restructure BillingModel #1: move 21 PriceDefinitions out of 4 Ledgers,
     append referencesLedger to each
  5. Rewrite 3 base-charge tier ApplicabilityGroups using ConditionExpression
  6. Replace vintage PCIA EligibilityRule with two rules:
     - residential customer kind
     - CCA OR DA OR TBS program enrollment
  7. Restructure BillingModel #2 (vintage PCIA): same Ledger→BillingModel move
  8. Rewrite 18 vintage PCIA ApplicabilityGroups using ConditionExpression
     (DatatypeOperandNode integerValue for vintage year, pending urpx-org/urpx#17)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "ca/iou/pge/e-tou-d/versions/2026-03-27/rate-plan_pge_e-tou-d_2026-03-27.jsonld"


def cn_equals_object(cn_id, prop_iri, value_iri):
    """ComparisonNode: ObjectOperand-property = ObjectOperand-value."""
    return {
        "@type": "urpx:ComparisonNode",
        "@id": cn_id,
        "urpx:operator": {"@id": "urpx:equalsOperator"},
        "urpx:leftOperand": {
            "@type": "urpx:ObjectOperandNode",
            "urpx:conditionProperty": {"@id": prop_iri},
        },
        "urpx:rightOperand": {
            "@type": "urpx:ObjectOperandNode",
            "urpx:referencesValue": {"@id": value_iri},
        },
    }


def cn_not_equals_object(cn_id, prop_iri, value_iri):
    """ComparisonNode: ObjectOperand-property != ObjectOperand-value."""
    n = cn_equals_object(cn_id, prop_iri, value_iri)
    n["urpx:operator"] = {"@id": "urpx:notEqualsOperator"}
    return n


def cn_equals_integer(cn_id, prop_iri_str, int_val):
    """ComparisonNode: DatatypeOperand-property = DatatypeOperand-integer."""
    return {
        "@type": "urpx:ComparisonNode",
        "@id": cn_id,
        "urpx:operator": {"@id": "urpx:equalsOperator"},
        "urpx:leftOperand": {
            "@type": "urpx:DatatypeOperandNode",
            "urpx:conditionProperty": {"@id": prop_iri_str},
        },
        "urpx:rightOperand": {
            "@type": "urpx:DatatypeOperandNode",
            "urpx:integerValue": int_val,
        },
    }


def expr_single(cx_id, root_node):
    """ConditionExpression with single rooted node."""
    return {
        "@type": "urpx:ConditionExpression",
        "@id": cx_id,
        "urpx:rootNode": root_node,
    }


def boolop(bn_id, op, operands):
    """BooleanOperationNode."""
    return {
        "@type": "urpx:BooleanOperationNode",
        "@id": bn_id,
        "urpx:operator": {"@id": f"urpx:{op}Operator"},
        "urpx:operandNodes": operands,
    }


def main():
    data = json.loads(TARGET.read_text())
    graph = data["@graph"]

    # ── 1. Add ProgramEnrollment instances + RateCase ─────────────────────
    new_enrollments = [
        {
            "@type": "urpx:ProgramEnrollment",
            "@id": "pge:program-cca",
            "urpx:programName": "Community Choice Aggregation (CCA)",
            "urpx:programType": {"@id": "urpx:communityChoiceAggregation"},
        },
        {
            "@type": "urpx:ProgramEnrollment",
            "@id": "pge:program-da",
            "urpx:programName": "Direct Access (DA)",
        },
        {
            "@type": "urpx:ProgramEnrollment",
            "@id": "pge:program-tbs",
            "urpx:programName": "Transitional Bundled Service (TBS)",
        },
    ]
    rate_case = {
        "@type": "urpx:RateCase",
        "@id": "pge:rc-d-26-03-013",
        "urpx:caseNumber": "D.26-03-013",
        "urpx:name": "CPUC Decision D.26-03-013",
        "urpx:url": "https://docs.cpuc.ca.gov/PublishedDocs/Published/G000/M999/K999/26-03-013.PDF",
    }
    # insert after CARE/FERA (positions 0,1) and before TariffPublication
    insert_at = next(i for i, n in enumerate(graph) if n.get("@type") == "urpx:TariffPublication")
    for ent in new_enrollments + [rate_case]:
        graph.insert(insert_at, ent)
        insert_at += 1

    # ── 2-7. Mutate the RatePlan / RatePlanModifier in place ─────────────
    rate_plan = next(n for n in graph if n.get("@type") == "urpx:RatePlan")
    rate_plan_modifier = next(n for n in graph if n.get("@type") == "urpx:RatePlanModifier")

    rpv = rate_plan["urpx:hasRatePlanVersion"]
    rpmv = rate_plan_modifier["urpx:hasRatePlanModifierVersion"]

    # Property renames + relocation (Decision #102):
    #   RatePlan.ratePlanIdentifier → RatePlan.ratePlanUniqueIdentifier
    #   RatePlanModifierVersion.modifierIdentifier → RatePlanModifier.modifierUniqueIdentifier
    if "urpx:ratePlanIdentifier" in rate_plan:
        rate_plan["urpx:ratePlanUniqueIdentifier"] = rate_plan.pop("urpx:ratePlanIdentifier")
    if "urpx:modifierIdentifier" in rpmv:
        rate_plan_modifier["urpx:modifierUniqueIdentifier"] = rpmv.pop("urpx:modifierIdentifier")

    # Reference RateCase from both
    rpv["urpx:hasRateCase"] = {"@id": "pge:rc-d-26-03-013"}
    rpmv["urpx:hasRateCase"] = {"@id": "pge:rc-d-26-03-013"}

    # ── 3. Base EligibilityRule: hasCustomerProfile → hasConditionExpression ─
    base_er = rpv["urpx:hasEligibilityRule"][0]
    del base_er["urpx:hasCustomerProfile"]
    base_er["urpx:hasConditionExpression"] = expr_single(
        "pge:cx-residential",
        cn_equals_object("pge:cn-residential", "urpx:hasCustomerKind", "urpx:residentialKind"),
    )

    # ── 4. Restructure BillingModel #1: move PriceDefinitions up, add referencesLedger ─
    bm1 = rpv["urpx:hasPlanElements"]["urpx:hasBillingModel"]
    bm1_pds = []
    for ledger in bm1["urpx:hasLedger"]:
        ledger_id = ledger["@id"]
        pds = ledger.pop("urpx:hasPriceDefinition")
        if isinstance(pds, dict):
            pds = [pds]
        for pd in pds:
            pd["urpx:referencesLedger"] = {"@id": ledger_id}
            bm1_pds.append(pd)
    bm1["urpx:hasPriceDefinition"] = bm1_pds

    # ── 5. Rewrite 3 base-charge tier ApplicabilityGroups ─────────────────
    prog_enrollment = "urpx:hasProgramEnrollment"
    prices = rpv["urpx:hasPrices"]["urpx:hasPrice"]
    for price in prices:
        ag = price.get("urpx:hasApplicabilityGroup")
        if not ag:
            continue
        ag_id = ag["@id"]
        if ag_id == "pge:ag-base-charge-tier-1":
            for k in list(ag.keys()):
                if k.startswith("urpx:has") and k != "urpx:hasApplicabilityGroup":
                    if k in ("urpx:hasInclusionConstraint", "urpx:hasExclusionConstraint"):
                        del ag[k]
            ag["urpx:hasConditionExpression"] = expr_single(
                "pge:cx-tier-1",
                cn_equals_object("pge:cn-tier-1", prog_enrollment, "pge:program-care"),
            )
        elif ag_id == "pge:ag-base-charge-tier-2":
            ag.pop("urpx:hasInclusionConstraint", None)
            ag.pop("urpx:hasExclusionConstraint", None)
            ag["urpx:hasConditionExpression"] = expr_single(
                "pge:cx-tier-2",
                cn_equals_object("pge:cn-tier-2", prog_enrollment, "pge:program-fera"),
            )
        elif ag_id == "pge:ag-base-charge-tier-3":
            ag.pop("urpx:hasInclusionConstraint", None)
            ag.pop("urpx:hasExclusionConstraint", None)
            ag["urpx:hasConditionExpression"] = expr_single(
                "pge:cx-tier-3",
                boolop("pge:bn-tier-3-and", "and", [
                    cn_not_equals_object("pge:cn-tier-3-not-care", prog_enrollment, "pge:program-care"),
                    cn_not_equals_object("pge:cn-tier-3-not-fera", prog_enrollment, "pge:program-fera"),
                ]),
            )

    # ── 6. Vintage PCIA EligibilityRule: split into two rules ─────────────
    rpmv["urpx:hasEligibilityRule"] = [
        {
            "@type": "urpx:EligibilityRule",
            "@id": "pge:er-residential",
            "urpx:name": "Residential customer",
            "urpx:description": "Vintaged PCIA on E-TOU-D applies only to residential customers.",
            "urpx:hasConditionExpression": expr_single(
                "pge:cx-vpcia-residential",
                cn_equals_object("pge:cn-vpcia-residential", "urpx:hasCustomerKind", "urpx:residentialKind"),
            ),
        },
        {
            "@type": "urpx:EligibilityRule",
            "@id": "pge:er-cca-da-tbs",
            "urpx:name": "Generation service: CCA, DA, or TBS",
            "urpx:description": "Vintaged PCIA applies to customers receiving generation service from a non-utility provider (CCA, DA) or in transitional bundled service (TBS).",
            "urpx:hasConditionExpression": expr_single(
                "pge:cx-cca-da-tbs",
                boolop("pge:bn-cca-da-tbs-or", "or", [
                    cn_equals_object("pge:cn-program-cca", prog_enrollment, "pge:program-cca"),
                    cn_equals_object("pge:cn-program-da", prog_enrollment, "pge:program-da"),
                    cn_equals_object("pge:cn-program-tbs", prog_enrollment, "pge:program-tbs"),
                ]),
            ),
        },
    ]

    # ── 7. Restructure BillingModel #2 ────────────────────────────────────
    bm2 = rpmv["urpx:hasPlanElements"]["urpx:hasBillingModel"]
    bm2_pds = []
    for ledger in bm2["urpx:hasLedger"]:
        ledger_id = ledger["@id"]
        pds = ledger.pop("urpx:hasPriceDefinition")
        if isinstance(pds, dict):
            pds = [pds]
        for pd in pds:
            pd["urpx:referencesLedger"] = {"@id": ledger_id}
            bm2_pds.append(pd)
    bm2["urpx:hasPriceDefinition"] = bm2_pds

    # ── 8. Rewrite 18 vintage PCIA ApplicabilityGroups ────────────────────
    vintage_prop = "https://rate-plans.grid-coordination.energy/pge/departureVintage"
    for price in rpmv["urpx:hasPrices"]["urpx:hasPrice"]:
        ag = price.get("urpx:hasApplicabilityGroup")
        if not ag:
            continue
        ag_id = ag["@id"]
        if not ag_id.startswith("pge:ag-vpcia-"):
            continue
        year = int(ag_id.rsplit("-", 1)[-1])
        ag.pop("urpx:hasInclusionConstraint", None)
        ag.pop("urpx:hasExclusionConstraint", None)
        ag["urpx:hasConditionExpression"] = expr_single(
            f"pge:cx-vpcia-{year}",
            cn_equals_integer(f"pge:cn-vpcia-{year}", vintage_prop, year),
        )

    # ── Write back ────────────────────────────────────────────────────────
    TARGET.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {TARGET}")


if __name__ == "__main__":
    main()
