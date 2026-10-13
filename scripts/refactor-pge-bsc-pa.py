#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Refactor PG&E filings' income-tier Base Services Charge to ProfileAlternatives + PriceSetAlternatives idiom.

Per upstream urpx-org/urpx#9 (closed) and Una's guidance:
- Define a ProfileAlternatives in PlanElements describing the Income Tier dimension
- Three ProfileAlternative entries (CARE, FERA, Standard), each carrying its own hasConditionExpression
- The 3 BSC Prices move into a PriceSetAlternatives wrapping (under hasPriceSetAlternatives), with each PriceSetAlternative referencing its corresponding ProfileAlternative
- Per-Price hasApplicabilityGroup entries are removed (the condition moves up to the ProfileAlternative)

Run on a single file. Idempotent (skips files already refactored).
"""
import json, sys, copy
from pathlib import Path

PROFILE_ALTS_BLOCK = {
    "@type": "urpx:ProfileAlternatives",
    "@id": "pge:pa-income-tier",
    "urpx:name": "Income tier (CARE / FERA / Standard)",
    "urpx:hasAlternativeDimensions": {
        "@type": "urpx:AlternativeDimensions",
        "urpx:hasAlternativeDimension": [{
            "@type": "urpx:AlternativeDimension",
            "urpx:dimensionDisplayName": "Program Enrollment",
            "urpx:dimensionProperty": "https://urpx-org.github.io/urpx/ontology/hasProgramEnrollment",
            "urpx:hasPossibleValues": {
                "@list": [
                    {"@id": "pge:program-care"},
                    {"@id": "pge:program-fera"}
                ]
            }
        }]
    },
    "urpx:hasProfileAlternative": [
        {
            "@type": "urpx:ProfileAlternative",
            "@id": "pge:pa-income-tier-care",
            "urpx:name": "Income Tier 1 — CARE-eligible",
            "urpx:hasConditionExpression": {
                "@type": "urpx:ConditionExpression",
                "@id": "pge:cx-pa-care",
                "urpx:rootNode": {
                    "@type": "urpx:ComparisonNode",
                    "@id": "pge:cn-pa-care",
                    "urpx:operator": {"@id": "urpx:equalsOperator"},
                    "urpx:leftOperand": {
                        "@type": "urpx:ObjectOperandNode",
                        "urpx:conditionProperty": {"@id": "urpx:hasProgramEnrollment"}
                    },
                    "urpx:rightOperand": {
                        "@type": "urpx:ObjectOperandNode",
                        "urpx:referencesValue": {"@id": "pge:program-care"}
                    }
                }
            }
        },
        {
            "@type": "urpx:ProfileAlternative",
            "@id": "pge:pa-income-tier-fera",
            "urpx:name": "Income Tier 2 — FERA-eligible",
            "urpx:hasConditionExpression": {
                "@type": "urpx:ConditionExpression",
                "@id": "pge:cx-pa-fera",
                "urpx:rootNode": {
                    "@type": "urpx:ComparisonNode",
                    "@id": "pge:cn-pa-fera",
                    "urpx:operator": {"@id": "urpx:equalsOperator"},
                    "urpx:leftOperand": {
                        "@type": "urpx:ObjectOperandNode",
                        "urpx:conditionProperty": {"@id": "urpx:hasProgramEnrollment"}
                    },
                    "urpx:rightOperand": {
                        "@type": "urpx:ObjectOperandNode",
                        "urpx:referencesValue": {"@id": "pge:program-fera"}
                    }
                }
            }
        },
        {
            "@type": "urpx:ProfileAlternative",
            "@id": "pge:pa-income-tier-standard",
            "urpx:name": "Income Tier 3 — neither CARE nor FERA (standard)",
            "urpx:hasConditionExpression": {
                "@type": "urpx:ConditionExpression",
                "@id": "pge:cx-pa-standard",
                "urpx:rootNode": {
                    "@type": "urpx:BooleanOperationNode",
                    "@id": "pge:bn-pa-standard",
                    "urpx:operator": {"@id": "urpx:andOperator"},
                    "urpx:operandNodes": [
                        {
                            "@type": "urpx:ComparisonNode",
                            "@id": "pge:cn-pa-not-care",
                            "urpx:operator": {"@id": "urpx:notEqualsOperator"},
                            "urpx:leftOperand": {
                                "@type": "urpx:ObjectOperandNode",
                                "urpx:conditionProperty": {"@id": "urpx:hasProgramEnrollment"}
                            },
                            "urpx:rightOperand": {
                                "@type": "urpx:ObjectOperandNode",
                                "urpx:referencesValue": {"@id": "pge:program-care"}
                            }
                        },
                        {
                            "@type": "urpx:ComparisonNode",
                            "@id": "pge:cn-pa-not-fera",
                            "urpx:operator": {"@id": "urpx:notEqualsOperator"},
                            "urpx:leftOperand": {
                                "@type": "urpx:ObjectOperandNode",
                                "urpx:conditionProperty": {"@id": "urpx:hasProgramEnrollment"}
                            },
                            "urpx:rightOperand": {
                                "@type": "urpx:ObjectOperandNode",
                                "urpx:referencesValue": {"@id": "pge:program-fera"}
                            }
                        }
                    ]
                }
            }
        }
    ]
}

# Mapping from old Price @id suffix → new ProfileAlternative @id
TIER_MAP = {
    'tier-1': 'pge:pa-income-tier-care',
    'tier-2': 'pge:pa-income-tier-fera',
    'tier-3': 'pge:pa-income-tier-standard',
}


def refactor(data):
    """Mutate data in place. Returns True if changed."""
    # Find PlanElements
    plan_elements = _find_first(data, lambda n: isinstance(n, dict) and n.get('@type') == 'urpx:PlanElements')
    if not plan_elements:
        return False
    if 'urpx:hasProfileAlternatives' in plan_elements:
        return False  # already refactored

    # Find Prices container
    prices_container = _find_first(data, lambda n: isinstance(n, dict) and n.get('@type') == 'urpx:Prices')
    if not prices_container:
        return False
    has_price = prices_container.get('urpx:hasPrice')
    if not isinstance(has_price, list):
        return False

    # Extract the 3 BSC tier Prices
    bsc_prices = []
    other_prices = []
    for p in has_price:
        pid = p.get('@id', '') if isinstance(p, dict) else ''
        if pid in ('pge:price-base-charge-tier-1', 'pge:price-base-charge-tier-2', 'pge:price-base-charge-tier-3'):
            bsc_prices.append(p)
        else:
            other_prices.append(p)
    if len(bsc_prices) != 3:
        return False

    # Strip hasApplicabilityGroup from each BSC Price
    for bp in bsc_prices:
        bp.pop('urpx:hasApplicabilityGroup', None)

    # Build PriceSetAlternatives container
    price_set_alts = []
    for bp in bsc_prices:
        suffix = bp['@id'].rsplit('-', 1)[1]
        # 'tier-1' suffix needs special handling — split differently
        # @id like 'pge:price-base-charge-tier-1' — the tier suffix is 'tier-1' (last 2 segments)
        parts = bp['@id'].split('-')
        tier_key = '-'.join(parts[-2:])  # 'tier-1'
        pa_ref = TIER_MAP.get(tier_key)
        if not pa_ref:
            continue
        psa = {
            "@type": "urpx:PriceSetAlternative",
            "@id": f"pge:psa-bsc-{tier_key}",
            "urpx:referencesProfileAlternative": {"@id": pa_ref},
            "urpx:hasPrice": [bp]
        }
        price_set_alts.append(psa)

    # Build the PriceSetAlternatives wrapping
    psa_wrap = {
        "@type": "urpx:PriceSetAlternatives",
        "@id": "pge:psa-bsc-by-income-tier",
        "urpx:name": "Base Services Charge — varies by income tier (CARE / FERA / Standard)",
        "urpx:referencesProfileAlternatives": {"@id": "pge:pa-income-tier"},
        "urpx:hasPriceSetAlternative": price_set_alts
    }

    # Insert hasProfileAlternatives in PlanElements (after hasBillingModel)
    new_pe = {}
    inserted_pa = False
    for k, v in plan_elements.items():
        new_pe[k] = v
        if k == 'urpx:hasBillingModel' and not inserted_pa:
            new_pe['urpx:hasProfileAlternatives'] = copy.deepcopy(PROFILE_ALTS_BLOCK)
            inserted_pa = True
    if not inserted_pa:
        new_pe['urpx:hasProfileAlternatives'] = copy.deepcopy(PROFILE_ALTS_BLOCK)
    plan_elements.clear()
    plan_elements.update(new_pe)

    # Update Prices: replace hasPrice with the residual; add hasPriceSetAlternatives
    prices_container['urpx:hasPrice'] = other_prices
    existing_psas = prices_container.get('urpx:hasPriceSetAlternatives')
    if isinstance(existing_psas, list):
        existing_psas.append(psa_wrap)
    elif isinstance(existing_psas, dict):
        prices_container['urpx:hasPriceSetAlternatives'] = [existing_psas, psa_wrap]
    else:
        prices_container['urpx:hasPriceSetAlternatives'] = [psa_wrap]

    return True


def _find_first(node, pred):
    if pred(node):
        return node
    if isinstance(node, dict):
        for v in node.values():
            r = _find_first(v, pred)
            if r is not None: return r
    elif isinstance(node, list):
        for v in node:
            r = _find_first(v, pred)
            if r is not None: return r
    return None


def main():
    if len(sys.argv) < 2:
        print("usage: refactor-pge-bsc-pa.py <file.jsonld>", file=sys.stderr); sys.exit(2)
    p = Path(sys.argv[1])
    with open(p) as fh: data = json.load(fh)
    if refactor(data):
        with open(p, 'w') as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write('\n')
        print(f'refactored: {p}')
    else:
        print(f'no changes (already refactored or unexpected structure): {p}')


if __name__ == '__main__':
    main()
