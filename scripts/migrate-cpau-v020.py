#!/usr/bin/env python3
"""
Migrate CPAU rate-plan JSON-LD from URPX v0.1.x (as on urpx-org/urpx PR #7
cpau-rate-plans branch, head e8ed4f0) to URPX v0.2.0-candidate.

Also translates IRI prefix urpx:cpau-* to cpau:* per urpx-rate-plans convention,
and produces filings ready to drop into ca/pou/cpau/<schedule>/versions/<date>/.

Usage: python3 migrate-cpau-v020.py <input.jsonld> <output.jsonld>

This script handles the two BASE RatePlans (E-1, E-1-TOU). The three
modifier-only files (E-EEC-1, E-HRA, E-NSE-1) are deferred — they have
a packaging architectural decision pending (cross-RatePlan applicability
+ urpx-org/urpx#16 SHACL-stub issue).
"""
import json
import sys
from pathlib import Path


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


def reprefix(s, mapping):
    """Translate IRI strings like 'urpx:cpau-foo' → 'cpau:foo' per the mapping."""
    if isinstance(s, str):
        for old, new in mapping.items():
            if s.startswith(old):
                return new + s[len(old):]
    return s


def walk(obj, mapping):
    """Recursively translate all string @id values matching the prefix mapping."""
    if isinstance(obj, dict):
        return {k: walk(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [walk(v, mapping) for v in obj]
    return reprefix(obj, mapping)


def make_eligibility_rule_for_e_1(rule_id):
    """E-1 EligibilityRule: residential customer + single-family dwelling + separately metered."""
    return {
        "@type": "urpx:EligibilityRule",
        "@id": rule_id,
        "urpx:name": "Residential single-family separately-metered service",
        "urpx:description": (
            "Applies to all single-family residential electric service supplied through "
            "one meter at one point of delivery for domestic purposes in a single-family "
            "dwelling unit within the City of Palo Alto electric service area."
        ),
        "urpx:hasConditionExpression": expr_single(
            "cpau:cx-residential-single-family",
            boolop("cpau:bn-residential-single-family-and", "and", [
                cn_equals_object("cpau:cn-residential", "urpx:hasCustomerKind", "urpx:residentialKind"),
                cn_equals_string_custom("cpau:cn-single-family", "dwellingType", "Single-family dwelling"),
                cn_equals_string_custom("cpau:cn-separately-metered", "metering", "Separately metered"),
            ], logic_expression="hasCustomerKind = residentialKind AND dwellingType = 'Single-family dwelling' AND metering = 'Separately metered'"),
        ),
    }


def make_eligibility_rule_for_e_1_tou(rule_id):
    """E-1-TOU EligibilityRule: same as E-1 plus AMI-meter requirement."""
    return {
        "@type": "urpx:EligibilityRule",
        "@id": rule_id,
        "urpx:name": "Residential TOU eligibility",
        "urpx:description": (
            "Voluntary residential TOU service. Eligibility: single-family dwelling, "
            "separately metered, equipped with AMI (advanced metering infrastructure) "
            "supporting time-of-use measurement."
        ),
        "urpx:hasConditionExpression": expr_single(
            "cpau:cx-residential-tou",
            boolop("cpau:bn-residential-tou-and", "and", [
                cn_equals_object("cpau:cn-residential", "urpx:hasCustomerKind", "urpx:residentialKind"),
                cn_equals_string_custom("cpau:cn-single-family", "dwellingType", "Single-family dwelling"),
                cn_equals_string_custom("cpau:cn-separately-metered", "metering", "Separately metered"),
                cn_equals_string_custom("cpau:cn-ami", "metering", "AMI"),
            ], logic_expression="hasCustomerKind = residentialKind AND dwellingType = 'Single-family dwelling' AND metering = 'Separately metered' AND has AMI meter"),
        ),
    }


def migrate_base_rate_plan(data, schedule_key):
    """Apply v0.1.x → v0.2.0 transforms to the in-memory CPAU base RatePlan."""
    # Translate prefix
    mapping = {"urpx:cpau-": "cpau:", "urpx:utility-cpau": "org:utility-cpau"}
    data = walk(data, mapping)

    # Add cpau prefix to @context, also xsd:integer for integerValue
    ctx = data["@context"]
    ctx["cpau"] = "https://rate-plans.grid-coordination.energy/cpau/"
    ctx["org"] = "https://rate-plans.grid-coordination.energy/organizations/"

    rate_plan = data
    rpv = rate_plan["urpx:hasRatePlanVersion"]

    # Property rename
    if "urpx:ratePlanIdentifier" in rate_plan:
        rate_plan["urpx:ratePlanUniqueIdentifier"] = rate_plan.pop("urpx:ratePlanIdentifier")

    # Replace EligibilityRule with v0.2.0 form
    if schedule_key == "e-1":
        rpv["urpx:hasEligibilityRule"] = [make_eligibility_rule_for_e_1("cpau:er-residential-single-family")]
    elif schedule_key == "e-1-tou":
        rpv["urpx:hasEligibilityRule"] = [make_eligibility_rule_for_e_1_tou("cpau:er-residential-tou")]

    # Restructure BillingModel: hasPriceDefinition Ledger → BillingModel + referencesLedger
    pe = rpv["urpx:hasPlanElements"]
    bm = pe["urpx:hasBillingModel"]
    restructure_billing_model(bm)

    # Update profileMetricProperty: numberOfMeters → meterCount
    for mi in pe.get("urpx:hasMetricInput", []):
        pmp = mi.get("urpx:profileMetricProperty")
        if isinstance(pmp, dict) and pmp.get("@id") == "urpx:numberOfMeters":
            pmp["@id"] = "urpx:meterCount"

    # ServiceTierShape (closed) does not allow `description` or `hasCalculationMethod`.
    # Strip them and lift any non-trivial calculation-method content into the
    # ServiceTiers' or BillingModel's level if needed (CPAU's are just intervalDuration P1D
    # which is implied by the per-day baseline).
    for st in bm.get("urpx:hasServiceTiers", {}).get("urpx:hasServiceTier", []):
        st.pop("urpx:description", None)
        st.pop("urpx:hasCalculationMethod", None)

    return data


def rewrite_legacy_conditions_to_expression(rule, prefix):
    """For an EligibilityRule or ApplicabilityRule with legacy hasCondition[].
    Convert to hasConditionExpression. Strips hasCustomerProfile + logicExpression
    + hasCondition; adds hasConditionExpression."""
    rule.pop("urpx:hasCustomerProfile", None)
    conditions = rule.pop("urpx:hasCondition", [])
    if isinstance(conditions, dict):
        conditions = [conditions]
    rule.pop("urpx:logicExpression", None)
    if not conditions:
        return  # nothing to do; if EligibilityRule we'd add a residential check, but skip for now
    comparison_nodes = []
    for c in conditions:
        cn_id = c.get("@id", f"{prefix}-cn") if isinstance(c, dict) else f"{prefix}-cn"
        if not isinstance(c, dict):
            continue  # bare IRI ref; skip (broken legacy)
        ctype = c.get("urpx:conditionType")
        cval = c.get("urpx:conditionValue")
        cop = c.get("urpx:operator", {}).get("@id", "urpx:equalsOperator")
        comparison_nodes.append({
            "@type": "urpx:ComparisonNode",
            "@id": str(cn_id).replace("condition-", "cn-") if "condition-" in str(cn_id) else cn_id,
            "urpx:operator": {"@id": cop},
            "urpx:leftOperand": {
                "@type": "urpx:CustomOperandNode",
                "urpx:customConditionProperty": ctype or "unknown",
            },
            "urpx:rightOperand": {
                "@type": "urpx:CustomOperandNode",
                "urpx:stringValue": str(cval) if cval is not None else "",
            },
        })
    if len(comparison_nodes) == 1:
        rule["urpx:hasConditionExpression"] = expr_single(f"{prefix}-cx", comparison_nodes[0])
    elif len(comparison_nodes) > 1:
        rule["urpx:hasConditionExpression"] = expr_single(
            f"{prefix}-cx",
            boolop(f"{prefix}-bn-and", "and", comparison_nodes),
        )


def walk_rewrite_applicability_rules(obj, parent_id=""):
    """Recursively find ApplicabilityRule instances and rewrite their conditions."""
    if isinstance(obj, dict):
        if obj.get("@type") == "urpx:ApplicabilityRule" and "urpx:hasCondition" in obj:
            rewrite_legacy_conditions_to_expression(obj, parent_id or "applic")
        for k, v in obj.items():
            new_parent = obj.get("@id", parent_id) if k != "@id" else parent_id
            walk_rewrite_applicability_rules(v, new_parent)
    elif isinstance(obj, list):
        for v in obj:
            walk_rewrite_applicability_rules(v, parent_id)


def migrate_modifier(data, target_rate_plan_iri=None):
    """Apply v0.1.x → v0.2.0 transforms to a CPAU RatePlanModifier file.

    Returns the modified RatePlanModifier dict (suitable for nesting in another
    @graph). Strips the @context (the integrating filing supplies it) and the
    top-level wrapper.

    If `target_rate_plan_iri` is given, scopes applicableToRatePlan to only that
    IRI (since SHACL requires referents to be in the same graph; the modifier
    may originally list multiple base RatePlans across multiple filings, and
    only one will be in this filing's @graph).
    """
    mapping = {"urpx:cpau-": "cpau:", "urpx:utility-cpau": "org:utility-cpau"}
    data = walk(data, mapping)

    # Top-level is the RatePlanModifier itself (single-document file)
    rpm = data
    rpm.pop("@context", None)
    rpmv = rpm["urpx:hasRatePlanModifierVersion"]

    # Decision #100 — drop urpx:isOptional from RatePlanModifier
    rpm.pop("urpx:isOptional", None)

    # Property rename + relocation: modifierIdentifier (RPMV) → modifierUniqueIdentifier (RPM)
    if "urpx:modifierIdentifier" in rpmv:
        rpm["urpx:modifierUniqueIdentifier"] = rpmv.pop("urpx:modifierIdentifier")

    # Rewrite EligibilityRule on RPMV: remove hasCustomerProfile, hasCondition → hasConditionExpression
    for er in rpmv.get("urpx:hasEligibilityRule", []):
        rewrite_legacy_conditions_to_expression(er, er.get("@id", "er"))
        # If the rule had ONLY hasCustomerProfile (no conditions), synthesize a residential check
        if "urpx:hasConditionExpression" not in er:
            er["urpx:hasConditionExpression"] = expr_single(
                f"{er['@id']}-cx",
                cn_equals_object(f"{er['@id']}-cn-residential", "urpx:hasCustomerKind", "urpx:residentialKind"),
            )

    # Scope applicableToRatePlan to the target RatePlan (if specified)
    if target_rate_plan_iri:
        atrp = rpmv.get("urpx:applicableToRatePlan")
        if isinstance(atrp, list):
            scoped = [n for n in atrp if (n.get("@id") if isinstance(n, dict) else n) == target_rate_plan_iri]
            if len(scoped) == 1:
                rpmv["urpx:applicableToRatePlan"] = scoped[0]
            elif len(scoped) == 0:
                # Target wasn't in the list — keep the original (probably a bug; log + leave)
                pass

    # Restructure BillingModel: hasPriceDefinition Ledger → BillingModel + referencesLedger
    pe = rpmv.get("urpx:hasPlanElements", {})
    bm = pe.get("urpx:hasBillingModel")
    if bm:
        restructure_billing_model(bm)

    # Update profileMetricProperty: numberOfMeters → meterCount
    for mi in pe.get("urpx:hasMetricInput", []):
        pmp = mi.get("urpx:profileMetricProperty")
        if isinstance(pmp, dict) and pmp.get("@id") == "urpx:numberOfMeters":
            pmp["@id"] = "urpx:meterCount"

    # Recursively rewrite any ApplicabilityRule.hasCondition → hasConditionExpression
    walk_rewrite_applicability_rules(rpm)

    return rpm


def integrate_modifiers(base_path, modifier_paths, out_path):
    """Add the migrated modifiers to the base RatePlan filing's @graph.

    Reads the base filing (already at v0.2.0; in our repo it's NOT yet wrapped
    in @graph — single top-level RatePlan), wraps it, and adds the modifiers.
    """
    base = json.loads(Path(base_path).read_text())

    # If base is single top-level RatePlan, lift to @graph form
    if "@graph" not in base:
        ctx = base.pop("@context")
        rate_plan = base
        graph = [rate_plan]
        base = {"@context": ctx, "@graph": graph}

    # Identify the base RatePlan IRI for scoping applicableToRatePlan
    base_rp_iri = next(
        (n["@id"] for n in base["@graph"] if n.get("@type") == "urpx:RatePlan"),
        None,
    )

    for mp in modifier_paths:
        mod_data = json.loads(Path(mp).read_text())
        migrated = migrate_modifier(mod_data, target_rate_plan_iri=base_rp_iri)
        base["@graph"].append(migrated)

    Path(out_path).write_text(json.dumps(base, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out_path} with {len(base['@graph'])} top-level entities")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} migrate-base <input.jsonld> <output.jsonld> <schedule-key>", file=sys.stderr)
        print(f"       {sys.argv[0]} integrate-modifiers <base-output.jsonld> <output.jsonld> <modifier-input>...", file=sys.stderr)
        sys.exit(2)

    cmd = sys.argv[1]
    if cmd == "migrate-base":
        in_path = Path(sys.argv[2])
        out_path = Path(sys.argv[3])
        schedule_key = sys.argv[4]
        data = json.loads(in_path.read_text())
        migrated = migrate_base_rate_plan(data, schedule_key)
        out_path.write_text(json.dumps(migrated, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {out_path}")
    elif cmd == "integrate-modifiers":
        base_path = sys.argv[2]
        out_path = sys.argv[3]
        modifier_paths = sys.argv[4:]
        integrate_modifiers(base_path, modifier_paths, out_path)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
