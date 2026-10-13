#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Refactor PG&E filings' vintage-PCIA modifier sub-graph to ProfileAlternatives + PriceSetAlternatives idiom.

Per upstream urpx-org/urpx#9 (closed) and Una's guidance, the canonical v0.2.0 idiom is:
- Single ProfileAlternatives in PlanElements describing the Vintage Year dimension
- N ProfileAlternative entries (one per year), each carrying its own hasConditionExpression
- N Prices move into a PriceSetAlternatives wrapping (under hasPriceSetAlternatives), each PriceSetAlternative referencing the matching ProfileAlternative
- Per-Price hasApplicabilityGroup entries are removed (the condition moves up to ProfileAlternative)

departureVintage is a custom (PG&E-private) property, not URPX-native. Per design discussion
2026-05-01: mint a custom URI for urpx:dimensionProperty (synthetic but valid xsd:anyURI),
keep CustomOperandNode.customConditionProperty="departureVintage" on each ProfileAlternative's
ComparisonNode (mirrors the existing per-Price conditions). A follow-up upstream issue will
ask for customDimensionProperty (string) parallel to customConditionProperty.

Run on a single file. Idempotent (skips files already refactored).
"""
import json
import re
import sys
import copy
from pathlib import Path

DEPARTURE_VINTAGE_URI = "https://rate-plans.grid-coordination.energy/pge/properties/departureVintage"

PRICE_ID_RE = re.compile(r'^pge:price-vpcia-(\d{4})$')


def build_profile_alternatives(years: list[int]) -> dict:
    return {
        "@type": "urpx:ProfileAlternatives",
        "@id": "pge:pa-departure-vintage",
        "urpx:name": "Vintaged PCIA — departure-vintage year",
        "urpx:hasAlternativeDimensions": {
            "@type": "urpx:AlternativeDimensions",
            "urpx:hasAlternativeDimension": [{
                "@type": "urpx:AlternativeDimension",
                "urpx:dimensionDisplayName": "Departure Vintage Year",
                "urpx:dimensionProperty": DEPARTURE_VINTAGE_URI,
                "urpx:hasPossibleValues": {
                    "@list": [
                        {"@value": y, "@type": "xsd:integer"} for y in years
                    ]
                }
            }]
        },
        "urpx:hasProfileAlternative": [
            {
                "@type": "urpx:ProfileAlternative",
                "@id": f"pge:pa-vintage-{y}",
                "urpx:name": f"Departure vintage {y}",
                "urpx:hasConditionExpression": {
                    "@type": "urpx:ConditionExpression",
                    "@id": f"pge:cx-pa-vintage-{y}",
                    "urpx:rootNode": {
                        "@type": "urpx:ComparisonNode",
                        "@id": f"pge:cn-pa-vintage-{y}",
                        "urpx:operator": {"@id": "urpx:equalsOperator"},
                        "urpx:leftOperand": {
                            "@type": "urpx:CustomOperandNode",
                            "urpx:customConditionProperty": "departureVintage"
                        },
                        "urpx:rightOperand": {
                            "@type": "urpx:CustomOperandNode",
                            "urpx:integerValue": y
                        }
                    }
                }
            }
            for y in years
        ]
    }


def find_vpcia_modifier_version(node):
    """Return the RatePlanModifierVersion dict for the *-vintage-pcia modifier."""
    if isinstance(node, dict):
        if node.get('@type') == 'urpx:RatePlanModifier' and 'vintage-pcia' in node.get('@id', ''):
            ver = node.get('urpx:hasRatePlanModifierVersion')
            if isinstance(ver, dict):
                return ver
            if isinstance(ver, list) and ver and isinstance(ver[0], dict):
                return ver[0]
        for v in node.values():
            r = find_vpcia_modifier_version(v)
            if r is not None:
                return r
    elif isinstance(node, list):
        for v in node:
            r = find_vpcia_modifier_version(v)
            if r is not None:
                return r
    return None


def refactor(data) -> bool:
    """Mutate data in place. Returns True if changed."""
    ver = find_vpcia_modifier_version(data)
    if ver is None:
        return False

    plan_elements = ver.get('urpx:hasPlanElements')
    if not isinstance(plan_elements, dict):
        return False
    if 'urpx:hasProfileAlternatives' in plan_elements:
        return False  # already refactored

    prices_container = ver.get('urpx:hasPrices')
    if not isinstance(prices_container, dict):
        return False
    has_price = prices_container.get('urpx:hasPrice')
    if not isinstance(has_price, list):
        return False

    # Extract vintage Prices (one per year)
    vintage_prices = []
    other_prices = []
    for p in has_price:
        pid = p.get('@id', '') if isinstance(p, dict) else ''
        m = PRICE_ID_RE.match(pid)
        if m:
            vintage_prices.append((int(m.group(1)), p))
        else:
            other_prices.append(p)
    if not vintage_prices:
        return False

    vintage_prices.sort(key=lambda t: t[0])
    years = [y for y, _ in vintage_prices]

    # Strip hasApplicabilityGroup from each vintage Price
    for _, p in vintage_prices:
        p.pop('urpx:hasApplicabilityGroup', None)

    # Build PriceSetAlternative entries
    price_set_alts = [
        {
            "@type": "urpx:PriceSetAlternative",
            "@id": f"pge:psa-vpcia-{y}",
            "urpx:referencesProfileAlternative": {"@id": f"pge:pa-vintage-{y}"},
            "urpx:hasPrice": [p]
        }
        for y, p in vintage_prices
    ]
    psa_wrap = {
        "@type": "urpx:PriceSetAlternatives",
        "@id": "pge:psa-vpcia-by-vintage",
        "urpx:name": "Vintaged PCIA — varies by departure-vintage year",
        "urpx:referencesProfileAlternatives": {"@id": "pge:pa-departure-vintage"},
        "urpx:hasPriceSetAlternative": price_set_alts
    }

    # Insert hasProfileAlternatives in PlanElements (after hasBillingModel if present)
    new_pe = {}
    inserted = False
    for k, v in plan_elements.items():
        new_pe[k] = v
        if k == 'urpx:hasBillingModel' and not inserted:
            new_pe['urpx:hasProfileAlternatives'] = build_profile_alternatives(years)
            inserted = True
    if not inserted:
        new_pe['urpx:hasProfileAlternatives'] = build_profile_alternatives(years)
    plan_elements.clear()
    plan_elements.update(new_pe)

    # Update Prices: replace hasPrice with the residual; add hasPriceSetAlternatives
    prices_container['urpx:hasPrice'] = other_prices
    existing = prices_container.get('urpx:hasPriceSetAlternatives')
    if isinstance(existing, list):
        existing.append(psa_wrap)
    elif isinstance(existing, dict):
        prices_container['urpx:hasPriceSetAlternatives'] = [existing, psa_wrap]
    else:
        prices_container['urpx:hasPriceSetAlternatives'] = [psa_wrap]

    # Drop the empty hasPrice if no other prices remain (cleaner output)
    if not other_prices:
        prices_container.pop('urpx:hasPrice', None)

    return True


def main():
    if len(sys.argv) < 2:
        print("usage: refactor-pge-vintage-pcia-pa.py <file.jsonld>", file=sys.stderr)
        sys.exit(2)
    p = Path(sys.argv[1])
    with open(p) as fh:
        data = json.load(fh)
    if refactor(data):
        with open(p, 'w') as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write('\n')
        print(f'refactored: {p}')
    else:
        print(f'no changes (already refactored or unexpected structure): {p}')


if __name__ == '__main__':
    main()
