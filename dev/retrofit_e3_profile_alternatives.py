#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""One-off: restate cpau:e-3's interval-meter and power-type gates as one
ProfileAlternatives (2 dimensions, 4 cells) plus one PriceSetAlternatives."""
import copy
import json
import sys
from pathlib import Path

path = Path(sys.argv[1]) / "us/ca/cpau/electricity/e-3/versions/2007-07-01/rate-plan_cpau_e-3_2007-07-01.jsonld"
doc = json.loads(path.read_text())
v = doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]
pe = v["urpx:hasPlanElements"]
bm = pe["urpx:hasBillingModel"]
prices = v["urpx:hasPrices"]

c1, c2 = prices["urpx:hasPriceSet"]
assert c1["@id"] == "cpau:e3-price-set" and c2["@id"] == "cpau:e3-price-set-c2"
FIRM_ONLY = {"cpau:e3-pd-firm-capacity-summer", "cpau:e3-pd-firm-capacity-winter",
             "cpau:e3-pd-c2-firm-capacity-summer-peak", "cpau:e3-pd-c2-firm-capacity-winter-peak"}

# The gates being replaced, checked before they go.
def gate(node):
    root = node["urpx:hasApplicabilityGroup"]["urpx:hasConditionExpression"]["urpx:rootNode"]
    r = root["urpx:rightOperand"]
    return (root["urpx:leftOperand"]["urpx:customConditionProperty"],
            r.get("urpx:booleanValue", r.get("urpx:stringValue")))

assert gate(c1) == ("hasIntervalMeter", False) and gate(c2) == ("hasIntervalMeter", True)
pds = {pd["@id"]: pd for pd in bm["urpx:hasPriceDefinition"]}
gated = {i for i, pd in pds.items() if "urpx:hasApplicabilityGroup" in pd}
assert gated == FIRM_ONLY, gated
assert all(gate(pds[i]) == ("powerType", "Firm") for i in gated)
for i in gated:
    del pds[i]["urpx:hasApplicabilityGroup"]

PA = "cpau:e3-pa-buyback-configuration"
METER = [(False, "no-interval-meter", "without an interval meter (Section C.1)", c1),
         (True, "interval-meter", "with an interval meter (Section C.2)", c2)]
POWER = [("Firm", "firm"), ("Non-Firm", "non-firm")]


def cmp(cid, prop, key, value):
    return {"@type": "urpx:ComparisonNode", "@id": cid,
            "urpx:operator": {"@id": "urpx:equalsOperator"},
            "urpx:leftOperand": {"@type": "urpx:CustomOperandNode", "@id": f"{cid}-left-operand",
                                 "urpx:customConditionProperty": prop},
            "urpx:rightOperand": {"@type": "urpx:CustomOperandNode", "@id": f"{cid}-right-operand",
                                  key: value}}


alternatives, psas = [], []
for meter, mslug, mtext, ps in METER:
    for power, pslug in POWER:
        aid = f"{PA}-{mslug}-{pslug}"
        alternatives.append({
            "@type": "urpx:ProfileAlternative",
            "@id": aid,
            "urpx:name": f"{power} power, facility {mtext}",
            "urpx:hasConditionExpression": {
                "@type": "urpx:ConditionExpression",
                "@id": f"{aid}-cx",
                "urpx:rootNode": {
                    "@type": "urpx:BooleanOperationNode",
                    "@id": f"{aid}-bn",
                    "urpx:operator": {"@id": "urpx:andOperator"},
                    "urpx:operandNodes": [
                        cmp(f"{aid}-meter", "hasIntervalMeter", "urpx:booleanValue", meter),
                        cmp(f"{aid}-power", "powerType", "urpx:stringValue", power),
                    ],
                },
            },
        })
        members = [copy.deepcopy(p) for p in ps["urpx:hasPrice"]
                   if power == "Firm" or p["urpx:referencesPriceDefinition"]["@id"] not in FIRM_ONLY]
        psas.append({
            "@type": "urpx:PriceSetAlternative",
            "@id": f"cpau:e3-psa-buyback-{mslug}-{pslug}",
            "urpx:name": f"{ps['urpx:name']}, {power} power",
            "urpx:referencesProfileAlternative": {"@id": aid},
            "urpx:hasPrice": members,
        })

profile_alternatives = {
    "@type": "urpx:ProfileAlternatives",
    "@id": PA,
    "urpx:name": "Buyback table (Section C.1 without, C.2 with an interval meter) and type of power (Firm or Non-Firm, Special Note 1)",
    "urpx:hasAlternativeDimensions": {
        "@type": "urpx:AlternativeDimensions",
        "@id": f"{PA}-alternative-dimensions",
        "urpx:hasAlternativeDimension": [
            {"@type": "urpx:AlternativeDimension", "@id": "cpau:e3-ad-interval-meter",
             "urpx:dimensionDisplayName": "Facility equipped with an interval meter",
             "urpx:customDimensionProperty": "hasIntervalMeter",
             "urpx:hasPossibleValues": {"@list": [{"@value": "false", "@type": "xsd:boolean"},
                                                   {"@value": "true", "@type": "xsd:boolean"}]}},
            {"@type": "urpx:AlternativeDimension", "@id": "cpau:e3-ad-power-type",
             "urpx:dimensionDisplayName": "Type of Power",
             "urpx:customDimensionProperty": "powerType",
             "urpx:hasPossibleValues": {"@list": [{"@value": "Firm", "@type": "xsd:string"},
                                                   {"@value": "Non-Firm", "@type": "xsd:string"}]}},
        ],
    },
    "urpx:hasProfileAlternative": alternatives,
}

# PlanElements: the container goes after hasMetricInput, as in the NBT filings.
rebuilt = {}
for k, val in pe.items():
    rebuilt[k] = val
    if k == "urpx:hasMetricInput":
        rebuilt["urpx:hasProfileAlternatives"] = profile_alternatives
pe.clear()
pe.update(rebuilt)

del prices["urpx:hasPriceSet"]
prices["urpx:hasPriceSetAlternatives"] = [{
    "@type": "urpx:PriceSetAlternatives",
    "@id": "cpau:e3-psa-buyback",
    "urpx:name": "Buyback prices, by buyback table and type of power",
    "urpx:referencesProfileAlternatives": {"@id": PA},
    "urpx:hasPriceSetAlternative": psas,
}]

# Self-check: each cell holds exactly the Prices the source table gives it.
old = json.loads(path.read_text())["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]["urpx:hasPrices"]["urpx:hasPriceSet"]
old_c = {s["@id"]: {p["@id"]: p for p in s["urpx:hasPrice"]} for s in old}
for psa in psas:
    ids = {p["@id"] for p in psa["urpx:hasPrice"]}
    src = old_c["cpau:e3-price-set" if "no-interval" in psa["@id"] else "cpau:e3-price-set-c2"]
    want = set(src) if psa["@id"].endswith("-firm") and not psa["@id"].endswith("non-firm") else \
        {i for i, p in src.items() if p["urpx:referencesPriceDefinition"]["@id"] not in FIRM_ONLY}
    assert ids == want, (psa["@id"], ids ^ want)
    assert all(p == src[p["@id"]] for p in psa["urpx:hasPrice"])
    print(psa["@id"], len(ids))
if "--dry-run" not in sys.argv:
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
