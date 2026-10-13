#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""
URPX v0.2.0 migration for PG&E residential TOU filings (E-TOU-D, E-TOU-C, E-1).

Shared shape: residential TOU with CARE/FERA/Tier-3 base charge + 18-vintage PCIA
modifier. EV2 is excluded — it has DER + annual-cap rules that need a separate
script.

Usage: python3 migrate-pge-residential-v020.py <filing-key>
where filing-key is one of: e-tou-d, e-tou-c, e-1
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Per-filing configuration. Pieces that differ between filings:
#   - file path
#   - whether to add a RateCase (only filings under AL 7869-E do)
#   - the residential rule's @id (per-filing slug)
FILINGS = {
    "e-tou-d": {
        "path": ROOT / "ca/iou/pge/e-tou-d/versions/2026-03-27/rate-plan_pge_e-tou-d_2026-03-27.jsonld",
        "rate_case": {
            "@id": "pge:rc-d-26-03-013",
            "case_number": "D.26-03-013",
            "name": "CPUC Decision D.26-03-013",
            "url": "https://docs.cpuc.ca.gov/PublishedDocs/Published/G000/M999/K999/26-03-013.PDF",
        },
    },
    "e-tou-c": {"path": ROOT / "ca/iou/pge/e-tou-c/versions/2026-03-01/rate-plan_pge_e-tou-c_2026-03-01.jsonld"},
    "e-1":     {"path": ROOT / "ca/iou/pge/e-1/versions/2026-03-01/rate-plan_pge_e-1_2026-03-01.jsonld"},
}


def cn_equals_object(cn_id, prop_iri, value_iri):
    return {
        "@type": "urpx:ComparisonNode", "@id": cn_id,
        "urpx:operator": {"@id": "urpx:equalsOperator"},
        "urpx:leftOperand": {"@type": "urpx:ObjectOperandNode", "urpx:conditionProperty": {"@id": prop_iri}},
        "urpx:rightOperand": {"@type": "urpx:ObjectOperandNode", "urpx:referencesValue": {"@id": value_iri}},
    }


def cn_not_equals_object(cn_id, prop_iri, value_iri):
    n = cn_equals_object(cn_id, prop_iri, value_iri)
    n["urpx:operator"] = {"@id": "urpx:notEqualsOperator"}
    return n


def cn_equals_integer_custom(cn_id, custom_prop_label, int_val):
    """ComparisonNode for a custom (non-URPX-native) property compared to an integer.
    Per urpx-condition-modeling.md, custom concepts use CustomOperandNode rather
    than DatatypeOperandNode with an arbitrary IRI as conditionProperty."""
    return {
        "@type": "urpx:ComparisonNode", "@id": cn_id,
        "urpx:operator": {"@id": "urpx:equalsOperator"},
        "urpx:leftOperand": {"@type": "urpx:CustomOperandNode", "urpx:customConditionProperty": custom_prop_label},
        "urpx:rightOperand": {"@type": "urpx:CustomOperandNode", "urpx:integerValue": int_val},
    }


def expr_single(cx_id, root_node):
    return {"@type": "urpx:ConditionExpression", "@id": cx_id, "urpx:rootNode": root_node}


def boolop(bn_id, op, operands, logic_expression=None):
    n = {
        "@type": "urpx:BooleanOperationNode", "@id": bn_id,
        "urpx:operator": {"@id": f"urpx:{op}Operator"},
        "urpx:operandNodes": operands,
    }
    if logic_expression:
        n["urpx:logicExpression"] = logic_expression
    return n


def restructure_billing_model(bm):
    """Move all hasPriceDefinition values from each Ledger up to the BillingModel,
    adding referencesLedger to each PriceDefinition pointing back at its Ledger."""
    pds_collected = []
    for ledger in bm.get("urpx:hasLedger", []):
        ledger_id = ledger["@id"]
        pds = ledger.pop("urpx:hasPriceDefinition", None)
        if pds is None:
            continue
        if isinstance(pds, dict):
            pds = [pds]
        for pd in pds:
            pd["urpx:referencesLedger"] = {"@id": ledger_id}
            pds_collected.append(pd)
    bm["urpx:hasPriceDefinition"] = pds_collected


def migrate(key):
    cfg = FILINGS[key]
    path = cfg["path"]
    data = json.loads(path.read_text())
    graph = data["@graph"]
    prog_enrollment = "urpx:hasProgramEnrollment"

    # ── 1. Add CCA/DA/TBS ProgramEnrollment instances + (optionally) RateCase ─
    new_entities = [
        {"@type": "urpx:ProgramEnrollment", "@id": "pge:program-cca",
         "urpx:programName": "Community Choice Aggregation (CCA)",
         "urpx:programType": {"@id": "urpx:communityChoiceAggregation"}},
        {"@type": "urpx:ProgramEnrollment", "@id": "pge:program-da",
         "urpx:programName": "Direct Access (DA)"},
        {"@type": "urpx:ProgramEnrollment", "@id": "pge:program-tbs",
         "urpx:programName": "Transitional Bundled Service (TBS)"},
    ]
    if "rate_case" in cfg:
        rc = cfg["rate_case"]
        new_entities.append({
            "@type": "urpx:RateCase", "@id": rc["@id"],
            "urpx:caseNumber": rc["case_number"],
            "urpx:name": rc["name"],
            "urpx:url": rc["url"],
        })
    insert_at = next(i for i, n in enumerate(graph) if n.get("@type") == "urpx:TariffPublication")
    for ent in new_entities:
        graph.insert(insert_at, ent)
        insert_at += 1

    # ── 2. Locate RatePlan + RatePlanModifier ─────────────────────────────
    rate_plan = next(n for n in graph if n.get("@type") == "urpx:RatePlan")
    rate_plan_modifier = next(n for n in graph if n.get("@type") == "urpx:RatePlanModifier")
    rpv = rate_plan["urpx:hasRatePlanVersion"]
    rpmv = rate_plan_modifier["urpx:hasRatePlanModifierVersion"]

    # ── 3. Property renames + relocation (Decision #102 + closed-shape changes) ─
    if "urpx:ratePlanIdentifier" in rate_plan:
        rate_plan["urpx:ratePlanUniqueIdentifier"] = rate_plan.pop("urpx:ratePlanIdentifier")
    if "urpx:modifierIdentifier" in rpmv:
        rate_plan_modifier["urpx:modifierUniqueIdentifier"] = rpmv.pop("urpx:modifierIdentifier")

    # ── 4. Reference RateCase from RPV + RPMV (only if filing has one) ────
    if "rate_case" in cfg:
        rpv["urpx:hasRateCase"] = {"@id": cfg["rate_case"]["@id"]}
        rpmv["urpx:hasRateCase"] = {"@id": cfg["rate_case"]["@id"]}

    # ── 5. Rewrite base EligibilityRule: hasCustomerProfile → hasConditionExpression ─
    base_er = rpv["urpx:hasEligibilityRule"][0]
    base_er.pop("urpx:hasCustomerProfile", None)
    base_er["urpx:hasConditionExpression"] = expr_single(
        "pge:cx-residential",
        cn_equals_object("pge:cn-residential", "urpx:hasCustomerKind", "urpx:residentialKind"),
    )

    # ── 6. Restructure base BillingModel (Decision #093) ──────────────────
    bm1 = rpv["urpx:hasPlanElements"]["urpx:hasBillingModel"]
    restructure_billing_model(bm1)

    # ── 7. Rewrite 3 base-charge tier ApplicabilityGroups ─────────────────
    for price in rpv["urpx:hasPrices"]["urpx:hasPrice"]:
        ag = price.get("urpx:hasApplicabilityGroup")
        if not ag:
            continue
        ag_id = ag["@id"]
        if ag_id == "pge:ag-base-charge-tier-1":
            ag.pop("urpx:hasInclusionConstraint", None)
            ag.pop("urpx:hasExclusionConstraint", None)
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
                ], logic_expression="hasProgramEnrollment != program-care AND hasProgramEnrollment != program-fera"),
            )

    # ── 8. Vintage PCIA EligibilityRule split into two (residential + CCA/DA/TBS) ─
    rpmv["urpx:hasEligibilityRule"] = [
        {
            "@type": "urpx:EligibilityRule", "@id": "pge:er-residential",
            "urpx:name": "Residential customer",
            "urpx:description": "Vintaged PCIA applies only to residential customers.",
            "urpx:hasConditionExpression": expr_single(
                "pge:cx-vpcia-residential",
                cn_equals_object("pge:cn-vpcia-residential", "urpx:hasCustomerKind", "urpx:residentialKind"),
            ),
        },
        {
            "@type": "urpx:EligibilityRule", "@id": "pge:er-cca-da-tbs",
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

    # ── 9. Restructure vintage PCIA BillingModel ──────────────────────────
    bm2 = rpmv["urpx:hasPlanElements"]["urpx:hasBillingModel"]
    restructure_billing_model(bm2)

    # ── 10. Rewrite 18 vintage PCIA ApplicabilityGroups ───────────────────
    # 'departureVintage' is a non-URPX-native concept, so per
    # urpx-condition-modeling.md we use CustomOperandNode rather than
    # DatatypeOperandNode with a custom IRI on conditionProperty.
    for price in rpmv["urpx:hasPrices"]["urpx:hasPrice"]:
        ag = price.get("urpx:hasApplicabilityGroup")
        if not ag or not ag["@id"].startswith("pge:ag-vpcia-"):
            continue
        year = int(ag["@id"].rsplit("-", 1)[-1])
        ag.pop("urpx:hasInclusionConstraint", None)
        ag.pop("urpx:hasExclusionConstraint", None)
        ag["urpx:hasConditionExpression"] = expr_single(
            f"pge:cx-vpcia-{year}",
            cn_equals_integer_custom(f"pge:cn-vpcia-{year}", "departureVintage", year),
        )

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in FILINGS:
        print(f"Usage: {sys.argv[0]} <{ '|'.join(FILINGS) }>", file=sys.stderr)
        sys.exit(2)
    migrate(sys.argv[1])
