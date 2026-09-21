#!/usr/bin/env python3
"""
URPX v0.2.0 migration for PG&E E-ELEC (Residential Time-Of-Use, Electric Home).

Source: urpx-org/urpx test-cases/pge-e-elec-2026-01-01/data/urpx-rate-plan_pge_e-elec_2026-01-01.jsonld
        (v0.2.0-candidate branch; uses intermediate v0.2.0 vocabulary
        — ConditionLogic/ObjectTerminalNode/CustomTerminalNode that has been
        superseded by ConditionExpression/ObjectOperandNode/CustomOperandNode.)
Target: ca/iou/pge/e-elec/versions/2026-01-01/rate-plan_pge_e-elec_2026-01-01.jsonld

Differences from migrate-ev2-v020.py:
  - No income-tier base-charge ApplicabilityGroups (E-ELEC has a single flat
    base services charge of $0.49281/meter/day)
  - No annual-usage-cap rule (EV2-specific; E-ELEC has no usage cap)
  - California Climate Credit is present (similar pattern to E-TOU-C 2026-03-01)
  - Eligibility conditions: storage / EVCharging / heatpump / NBT (Net Billing
    Tariff) joined by OR. Storage and EVCharging map to URPX DER vocabulary;
    heatpump maps to urpx:hasHVAC + urpx:airSourceHeatPump (per the published
    tariff text); NBT has no URPX-native vocabulary so uses CustomOperandNode.
  - No vintage PCIA modifier in the fixture (Sheet 4 of the PDF lists the
    vintage table, but the source fixture doesn't include a modifier — left
    as a follow-up).
"""
import json
from pathlib import Path

ROOT = Path(str(Path(__file__).resolve().parent.parent))
SRC = Path("/tmp/e-elec.jsonld")
OUT = ROOT / "ca/iou/pge/e-elec/versions/2026-01-01/rate-plan_pge_e-elec_2026-01-01.jsonld"


def cn_equals_object(cn_id, prop_iri, value_iri):
    return {
        "@type": "urpx:ComparisonNode", "@id": cn_id,
        "urpx:operator": {"@id": "urpx:equalsOperator"},
        "urpx:leftOperand": {"@type": "urpx:ObjectOperandNode", "urpx:conditionProperty": {"@id": prop_iri}},
        "urpx:rightOperand": {"@type": "urpx:ObjectOperandNode", "urpx:referencesValue": {"@id": value_iri}},
    }


def cn_equals_string_custom(cn_id, custom_prop_label, str_val):
    return {
        "@type": "urpx:ComparisonNode", "@id": cn_id,
        "urpx:operator": {"@id": "urpx:equalsOperator"},
        "urpx:leftOperand": {"@type": "urpx:CustomOperandNode", "urpx:customConditionProperty": custom_prop_label},
        "urpx:rightOperand": {"@type": "urpx:CustomOperandNode", "urpx:stringValue": str_val},
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


def main():
    data = json.loads(SRC.read_text())

    # The source is a single top-level RatePlan (not @graph form). Wrap it.
    if "@graph" not in data:
        ctx = data.pop("@context")
        rate_plan = data
        data = {"@context": ctx, "@graph": [rate_plan]}

    rate_plan = next(n for n in data["@graph"] if n.get("@type") == "urpx:RatePlan")
    rpv = rate_plan["urpx:hasRatePlanVersion"]

    # Property rename
    if "urpx:ratePlanIdentifier" in rate_plan:
        rate_plan["urpx:ratePlanUniqueIdentifier"] = rate_plan.pop("urpx:ratePlanIdentifier")

    # Replace EligibilityRule with two v0.2.0 rules: residential + qualifying technology
    rpv["urpx:hasEligibilityRule"] = [
        # ER1: residential customer kind
        {
            "@type": "urpx:EligibilityRule",
            "@id": "pge:er-residential",
            "urpx:name": "Residential customer",
            "urpx:description": "Available to PG&E residential customers (individually-metered, whole-house service).",
            "urpx:hasConditionExpression": expr_single(
                "pge:cx-residential",
                cn_equals_object("pge:cn-residential", "urpx:hasCustomerKind", "urpx:residentialKind"),
            ),
        },
        # ER2: at least one qualifying technology (storage / EV / heat-pump / NBT)
        {
            "@type": "urpx:EligibilityRule",
            "@id": "pge:er-qualifying-technology",
            "urpx:name": "Qualifying electric technology: storage, EV, heat pump, or NBT enrollment",
            "urpx:description": (
                "Available to customers who have one or more of: a currently registered battery-electric "
                "vehicle (BEV) or plug-in hybrid (PHEV) — both map to urpx:evChargingDER since URPX's "
                "DERTypeValue enum does not distinguish them; energy storage (per Special Condition "
                "interconnection requirements); or an electric heat pump as primary water-heating or "
                "climate-control source. Customers billed on the Net Billing Tariff (NBT) must take "
                "service on E-ELEC and are not required to have any of the qualifying technologies "
                "above; the NBT condition is therefore included as a fourth OR-leaf."
            ),
            "urpx:hasConditionExpression": expr_single(
                "pge:cx-qualifying-technology",
                boolop("pge:bn-qualifying-technology-or", "or", [
                    cn_equals_object("pge:cn-storage", "urpx:derType", "urpx:storageDER"),
                    cn_equals_object("pge:cn-ev-charging", "urpx:derType", "urpx:evChargingDER"),
                    cn_equals_object("pge:cn-heat-pump", "urpx:hasHVAC", "urpx:airSourceHeatPump"),
                    cn_equals_string_custom("pge:cn-nbt", "Program Enrollment", "Net Billing Tariff (NBT)"),
                ]),
            ),
        },
    ]

    # The existing source already has BillingModel-owned PriceDefinitions with
    # referencesLedger (Una's prior-day SHACL-compliance push handled that).
    # Sanity-check: the legacy hasCondition arrays inside Conditions and the
    # ObjectTerminalNode/CustomTerminalNode types are now unreferenced (we replaced
    # the EligibilityRule), so they'll just be garbage-collected when we serialize.
    # The bare urpx:hasCondition on the EligibilityRule is gone (we overrode the
    # whole hasEligibilityRule list); the nested Condition objects with their
    # legacy operand types are no longer referenced from anywhere.

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
