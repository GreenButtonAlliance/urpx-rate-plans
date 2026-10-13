#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""
URPX v0.2.0 migration for PG&E EV2 (2026-03-27) filing.

EV2-specific differences from the residential-TOU migration script:
  - RateCase pge:rc-d-26-03-013 (CPUC Decision D.26-03-013) — same as E-TOU-D
  - DER eligibility rule (BEV/PHEV/storage/heatpump) is rewritten as a
    BooleanOperationNode of three ComparisonNodes:
       * urpx:derType = urpx:evChargingDER  (covers BEV + PHEV — both are
         plug-in EVs; URPX's DERTypeValue enum has no BEV/PHEV distinction)
       * urpx:derType = urpx:storageDER
       * urpx:hasHVAC = urpx:airSourceHeatPump
    This uses ObjectOperandNode.referencesValue with URPX's DER + HVAC
    vocabulary.
  - Annual usage cap rule expressed as a ComparisonNode comparing a new
    rolling-aligned MetricInput against integerValue 800. The "% of baseline"
    semantic is still informal pending URPX vocabulary; description carries
    the prose.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "ca/iou/pge/ev2/versions/2026-03-27/rate-plan_pge_ev2_2026-03-27.jsonld"

RATE_CASE = {
    "@type": "urpx:RateCase",
    "@id": "pge:rc-d-26-03-013",
    "urpx:caseNumber": "D.26-03-013",
    "urpx:name": "CPUC Decision D.26-03-013",
    "urpx:url": "https://docs.cpuc.ca.gov/PublishedDocs/Published/G000/M999/K999/26-03-013.PDF",
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
    """Per urpx-condition-modeling.md, custom concepts use CustomOperandNode."""
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


def main():
    data = json.loads(TARGET.read_text())
    graph = data["@graph"]
    prog_enrollment = "urpx:hasProgramEnrollment"

    # ── 1. Add ProgramEnrollment instances + RateCase ─────────────────────
    new_entities = [
        {"@type": "urpx:ProgramEnrollment", "@id": "pge:program-cca",
         "urpx:programName": "Community Choice Aggregation (CCA)",
         "urpx:programType": {"@id": "urpx:communityChoiceAggregation"}},
        {"@type": "urpx:ProgramEnrollment", "@id": "pge:program-da",
         "urpx:programName": "Direct Access (DA)"},
        {"@type": "urpx:ProgramEnrollment", "@id": "pge:program-tbs",
         "urpx:programName": "Transitional Bundled Service (TBS)"},
        RATE_CASE,
    ]
    insert_at = next(i for i, n in enumerate(graph) if n.get("@type") == "urpx:TariffPublication")
    for ent in new_entities:
        graph.insert(insert_at, ent)
        insert_at += 1

    # ── 2. Locate RatePlan + RatePlanModifier ─────────────────────────────
    rate_plan = next(n for n in graph if n.get("@type") == "urpx:RatePlan")
    rate_plan_modifier = next(n for n in graph if n.get("@type") == "urpx:RatePlanModifier")
    rpv = rate_plan["urpx:hasRatePlanVersion"]
    rpmv = rate_plan_modifier["urpx:hasRatePlanModifierVersion"]

    # ── 3. Property renames + relocation ─────────────────────────────────
    if "urpx:ratePlanIdentifier" in rate_plan:
        rate_plan["urpx:ratePlanUniqueIdentifier"] = rate_plan.pop("urpx:ratePlanIdentifier")
    if "urpx:modifierIdentifier" in rpmv:
        rate_plan_modifier["urpx:modifierUniqueIdentifier"] = rpmv.pop("urpx:modifierIdentifier")

    # ── 4. Reference RateCase from RPV + RPMV ─────────────────────────────
    rpv["urpx:hasRateCase"] = {"@id": RATE_CASE["@id"]}
    rpmv["urpx:hasRateCase"] = {"@id": RATE_CASE["@id"]}

    # ── 5. Rewrite base EligibilityRules: residential + DER + cap ────────
    rpv["urpx:hasEligibilityRule"] = [
        # Residential customer
        {
            "@type": "urpx:EligibilityRule", "@id": "pge:er-residential",
            "urpx:name": "Residential customer",
            "urpx:description": "Available to PG&E residential customers (Schedule E-1 eligible).",
            "urpx:hasConditionExpression": expr_single(
                "pge:cx-residential",
                cn_equals_object("pge:cn-residential", "urpx:hasCustomerKind", "urpx:residentialKind"),
            ),
        },
        # Qualifying equipment: BEV/PHEV (evChargingDER) OR storage OR airSourceHeatPump
        {
            "@type": "urpx:EligibilityRule", "@id": "pge:er-qualifying-equipment",
            "urpx:name": "Qualifying equipment: registered EV, battery storage, or electric heat pump",
            "urpx:description": "Available to customers who have a currently registered battery-electric vehicle (BEV) or plug-in hybrid (PHEV), battery storage (pilot, capped at 30,000 customers), or electric heat pump as primary water-heating or climate-control source. Pure HEVs and low-speed EVs/electric motorcycles/bicycles are excluded — by absence of a registered EV (urpx:evChargingDER), they do not satisfy this rule. BEV and PHEV both map to urpx:evChargingDER since URPX's DERTypeValue enum does not distinguish them.",
            "urpx:hasConditionExpression": expr_single(
                "pge:cx-qualifying-equipment",
                boolop("pge:bn-qualifying-equipment-or", "or", [
                    cn_equals_object("pge:cn-ev-charging", "urpx:derType", "urpx:evChargingDER"),
                    cn_equals_object("pge:cn-storage", "urpx:derType", "urpx:storageDER"),
                    cn_equals_object("pge:cn-heat-pump", "urpx:hasHVAC", "urpx:airSourceHeatPump"),
                ]),
            ),
        },
        # Annual usage cap: rolling-12-month kWh ≤ 800 (% of baseline; informal)
        {
            "@type": "urpx:EligibilityRule", "@id": "pge:er-annual-usage-cap",
            "urpx:name": "Annual usage cap: 800% of baseline allowance over rolling 12 months",
            "urpx:description": "Customers taking service on this rate schedule cannot exceed 800% of their annual baseline allowance, measured as the total usage for the customer over the last 12 months divided by the total annual baseline allowance using the approved baseline allowances for those months. Customers at premises with total usage in excess of 800% of baseline over 12 consecutive months are removed from Schedule EV2 and prohibited from taking service on any electric vehicle rate schedule for 12 months. Such customers are defaulted to Schedule E-TOU-D. Modeled as ComparisonNode (lessThanOrEqualOperator) with leftOperand referencing pge:mi-energy-annual-rolling (rolling 12-month aligned kWh) and rightOperand integerValue 800. The percent-of-baseline UoM is still informal — the right-side 800 represents 800% of baseline, not 800 kWh. Full formalization pending URPX vocabulary for percent-of-baseline UoM.",
            "urpx:hasConditionExpression": expr_single(
                "pge:cx-annual-usage-cap",
                {
                    "@type": "urpx:ComparisonNode",
                    "@id": "pge:cn-annual-usage-cap",
                    "urpx:operator": {"@id": "urpx:lessThanOrEqualOperator"},
                    "urpx:leftOperand": {
                        "@type": "urpx:ObjectOperandNode",
                        "urpx:referencesMetricInput": {"@id": "pge:mi-energy-annual-rolling"},
                    },
                    "urpx:rightOperand": {
                        "@type": "urpx:DatatypeOperandNode",
                        "urpx:integerValue": 800,
                    },
                },
            ),
        },
    ]

    # ── 5b. Add the rolling-12-month MetricInput ──────────────────────────
    # Append to the base RPV's hasPlanElements.hasMetricInput
    pe_metric_inputs = rpv["urpx:hasPlanElements"].setdefault("urpx:hasMetricInput", [])
    pe_metric_inputs.append({
        "@type": "urpx:MetricInput",
        "@id": "pge:mi-energy-annual-rolling",
        "urpx:name": "Rolling 12-month kWh consumption (for annual usage cap)",
        "urpx:metricInputType": {"@id": "urpx:measuredMetricInput"},
        "urpx:hasMetricSpecification": {
            "@type": "urpx:MetricSpecification",
            "@id": "pge:ms-energy-annual-rolling",
            "urpx:measurementKind": {"@id": "urpx:energy"},
            "urpx:unitOfMeasure": {"@id": "urpx:kWh"},
            "urpx:intervalDuration": "P1Y",
            "urpx:intervalAlignment": {"@id": "urpx:rollingAligned"},
        },
    })

    # ── 6. Restructure base BillingModel ─────────────────────────────────
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

    # ── 8. Vintage PCIA EligibilityRule split ─────────────────────────────
    rpmv["urpx:hasEligibilityRule"] = [
        {
            "@type": "urpx:EligibilityRule", "@id": "pge:er-vpcia-residential",
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

    # ── 9. Restructure vintage PCIA BillingModel ─────────────────────────
    bm2 = rpmv["urpx:hasPlanElements"]["urpx:hasBillingModel"]
    restructure_billing_model(bm2)

    # ── 10. Rewrite 18 vintage PCIA ApplicabilityGroups ───────────────────
    # 'departureVintage' is a non-URPX-native concept; use CustomOperandNode
    # per urpx-condition-modeling.md.
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

    TARGET.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {TARGET}")


if __name__ == "__main__":
    main()
