#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""One-off: state DER-type discriminators with the typed urpx:conditionProperty
urpx:derType where URPX's DERTypeValue enumeration names the type."""
import json
import sys
from pathlib import Path

R = Path(sys.argv[1])


def typed(cid, value):
    return {"@type": "urpx:ComparisonNode", "@id": cid,
            "urpx:operator": {"@id": "urpx:equalsOperator"},
            "urpx:leftOperand": {"@type": "urpx:ObjectOperandNode", "@id": f"{cid}-left-operand",
                                 "urpx:conditionProperty": {"@id": "urpx:derType"}},
            "urpx:rightOperand": {"@type": "urpx:ObjectOperandNode", "@id": f"{cid}-right-operand",
                                  "urpx:referencesValue": {"@id": value}}}


def find(x, i):
    if isinstance(x, dict):
        if x.get("@id") == i:
            return x
        for v in x.values():
            r = find(v, i)
            if r is not None:
                return r
    elif isinstance(x, list):
        for v in x:
            r = find(v, i)
            if r is not None:
                return r


def edit(rel, fn):
    p = R / rel
    doc = json.loads(p.read_text())
    fn(doc)
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


OLD_OTHER = ("Has other CEC-eligible renewable DER (biomass / solar thermal / geothermal / fuel cells "
             "using renewable fuels / digester gas / municipal solid waste / landfill gas / ocean wave "
             "/ ocean thermal / tidal current)")
NEW_OTHER = ("Has other CEC-eligible renewable DER (biomass / solar thermal / fuel cells using renewable "
             "fuels / municipal solid waste / ocean wave / ocean thermal / tidal current)")


def smud(prefix, old_desc_tail, new_desc_tail):
    def fn(doc):
        bn = find(doc, f"smud:bn-{prefix}-qualifying-der")
        ops = bn["urpx:operandNodes"]
        i = [o["@id"] for o in ops].index(f"smud:cn-{prefix}-other-renewable")
        other = ops[i]
        assert other["urpx:leftOperand"]["urpx:customConditionProperty"] == OLD_OTHER
        other["urpx:leftOperand"]["urpx:customConditionProperty"] = NEW_OTHER
        ops[i:i] = [typed(f"smud:cn-{prefix}-geothermal", "urpx:geothermalDER"),
                    typed(f"smud:cn-{prefix}-waste-digestion", "urpx:wasteDigestionDER")]
        rule = find(doc, f"smud:er-{prefix}-qualifying-der")
        assert old_desc_tail in rule["urpx:description"], prefix
        rule["urpx:description"] = rule["urpx:description"].replace(old_desc_tail, new_desc_tail)
    return fn


edit("us/ca/smud/electricity/nem1/versions/2021-09-17/rate-plan-modifier_smud_nem1_2021-09-17.jsonld",
     smud("nem1",
          "Modeled as a 4-way OR over the most common URPX DER enum values (solar, wind, hydro) plus a "
          "CustomOperandNode for other renewable types not covered by the URPX enum.",
          "Modeled as an OR over the URPX DER enum values that name a listed source (solar, wind, hydro, "
          "geothermal, and waste digestion for digester gas and landfill gas) plus a CustomOperandNode "
          "for the listed sources the enum does not name (biomass, solar thermal, fuel cells using "
          "renewable fuels, municipal solid waste, ocean wave, ocean thermal, tidal current)."))
edit("us/ca/smud/electricity/ssr/versions/2022-03-01/rate-plan-modifier_smud_ssr_2022-03-01.jsonld",
     smud("ssr",
          "Modeled as a 4-way OR over the most common URPX DER enum values (solar, wind, storage, hydro) "
          "plus a CustomOperandNode for other renewable types not covered by the URPX enum (biomass / "
          "geothermal / fuel cells / etc.).",
          "Modeled as an OR over the URPX DER enum values that name a listed source (solar, wind, "
          "storage, hydro, geothermal, and waste digestion for digester gas and landfill gas) plus a "
          "CustomOperandNode for the listed sources the enum does not name (biomass, solar thermal, "
          "fuel cells using renewable fuels, municipal solid waste, ocean wave, ocean thermal, tidal "
          "current)."))


def ladwp(doc):
    bn = find(doc, "ladwp:bn-nem-customer-generator-and-conditions")
    ops = bn["urpx:operandNodes"]
    i = [o["@id"] for o in ops].index("ladwp:cn-nem-customer-generator")
    old = ops[i]
    assert old["urpx:leftOperand"]["urpx:customConditionProperty"] == "Customer-Generator (on-site PV/wind/hybrid)"
    ops[i] = {"@type": "urpx:BooleanOperationNode", "@id": "ladwp:bn-nem-customer-generator-der",
              "urpx:operator": {"@id": "urpx:orOperator"},
              "urpx:operandNodes": [typed("ladwp:cn-nem-customer-generator-solar", "urpx:solarDER"),
                                    typed("ladwp:cn-nem-customer-generator-wind", "urpx:windDER")]}


edit("us/ca/ladwp/electricity/nem/versions/2008-09-01/rate-plan-modifier_ladwp_nem_2008-09-01.jsonld", ladwp)
