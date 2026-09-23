#!/usr/bin/env python3
"""
Build ca/pou/cpau/e-3/versions/2007-07-01/rate-plan_cpau_e-3_2007-07-01.jsonld.

CPAU Schedule E-3: Customer-Owned Generation. Buyback rates that the
utility pays to customers operating their own (non-NEM-eligible)
generation facilities. Effective 2007-07-01 — long-stable, never
re-issued (oldest filing in the urpx-tariffs corpus).

Source PDF sha256 fdc56b03b2d143c5f39e9bf2d5cbf555ee259cfad025792be426c543606b0de6
retrieved from paloalto.gov 2026-04-30.

V1 SCOPE — FACILITIES WITHOUT INTERVAL METER ONLY.

The published Schedule E-3 covers four distinct pricing matrices:
  1. Without interval meter × Firm:     flat seasonal kWh credit + capacity ($/kW)
  2. Without interval meter × Non-Firm: flat seasonal kWh credit (no capacity)
  3. With interval meter × Firm:        TOU kWh credits + Peak capacity
  4. With interval meter × Non-Firm:    TOU kWh credits (no capacity)
Plus a market-based buyback rate for facilities with rated capacity
> 1 MW (range pricing $2-10/kW, $0.03-0.20/kWh).

V1 models cases (1) and (2) only. Cases (3) and (4) plus the market-
based buyback are deferred to follow-up bd issues — they exercise
several distinct modeling questions (TOU windows that DIFFER from CPAU
E-4 TOU and E-7 TOU; range pricing; the with-interval-meter alternative
on the same RatePlanVersion as the without-interval-meter case).

NEW URPX modeling territory exercised here for the first time in our corpus:
- Reverse-flow direction (urpx:reverse) on the energy MetricInput. URPX
  pattern for buyback already established by the CPAU E-EEC-1 / E-NSE-1
  modifiers in the multi-source CPAU E-1 2025-09-01 filing — same shape
  reused here.
- 2007-vintage long-stable rate filing (oldest in the corpus).
- chargeType urpx:creditEnergy + chargeCategory urpx:discount on each
  buyback PriceDefinition (matching the E-EEC-1 / E-NSE-1 pattern).
- Capacity-credit ($/kW/month) paid by the utility to firm-power
  generators — chargeType urpx:capacityCredit, the inverse direction
  of E-4 / E-4 TOU / E-7 / E-7 TOU's customer-facing demand charges.

DEFERRED to follow-up bd issues:
  - WITH-INTERVAL-METER case: 3 TOU periods Summer (Off-Peak / Mid-Peak /
    Peak) + 2 TOU periods Winter (Off-Peak / Peak). TOU windows DIFFER
    from CPAU E-4 TOU and E-7 TOU — Summer Peak is 12 noon to 6 PM (not
    4-9 PM); Winter Peak is 8 AM to 9 PM weekday. Holidays excluded.
  - MARKET-BASED BUYBACK for facilities > 1 MW: range pricing
    ($2-10/kW, $0.03-0.20/kWh). URPX modeling for range pricing — file
    upstream question.
  - Section E.5 customer charge for facilities served-as-load (not
    modeled — operator's discretion, "specified in the service contract").

Per-component rates from Section C of the PDF:
  Without interval meter:
    Firm Summer:     $4.32/kW/month (capacity) + $0.07902/kWh (energy)
    Firm Winter:     $4.32/kW/month (capacity) + $0.07831/kWh (energy)
    Non-Firm Summer:                              $0.07902/kWh (energy)
    Non-Firm Winter:                              $0.07831/kWh (energy)
"""
import json
from pathlib import Path

ROOT = Path(str(Path(__file__).resolve().parent.parent))
OUT = ROOT / "ca/pou/cpau/e-3/versions/2007-07-01/rate-plan_cpau_e-3_2007-07-01.jsonld"

CONTEXT = {
    "urpx": "https://schema.urpx.org/",
    "schema": "http://schema.org/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "urpx:unitPrice": {"@type": "xsd:decimal"},
    "urpx:effectiveDate": {"@type": "xsd:date"},
    "urpx:effectiveDateTime": {"@type": "xsd:dateTime"},
    "urpx:baseQuantity": {"@type": "xsd:decimal"},
    "urpx:startDate": {"@type": "xsd:date"},
    "urpx:initialEffectiveDate": {"@type": "xsd:date"},
    "urpx:url": {"@type": "xsd:anyURI"},
    "urpx:intervalDuration": {"@type": "xsd:duration"},
    "urpx:month": {"@type": "xsd:gMonth"},
    "urpx:yearlyRecurrence": {"@type": "xsd:boolean"},
    "urpx:isDefault": {"@type": "xsd:boolean"},
    "urpx:dateRetrieved": {"@type": "xsd:date"},
    "cpau": "https://example.com/cpau/",
    "org": "https://example.com/organizations/",
}


def cn_eq_str(cn_id, custom_prop, str_val):
    return {
        "@type": "urpx:ComparisonNode", "@id": cn_id,
        "urpx:operator": {"@id": "urpx:equalsOperator"},
        "urpx:leftOperand": {"@type": "urpx:CustomOperandNode", "urpx:customConditionProperty": custom_prop},
        "urpx:rightOperand": {"@type": "urpx:CustomOperandNode", "urpx:stringValue": str_val},
    }


def cn_eq_bool(cn_id, custom_prop, bool_val):
    return {
        "@type": "urpx:ComparisonNode", "@id": cn_id,
        "urpx:operator": {"@id": "urpx:equalsOperator"},
        "urpx:leftOperand": {"@type": "urpx:CustomOperandNode", "urpx:customConditionProperty": custom_prop},
        "urpx:rightOperand": {"@type": "urpx:CustomOperandNode", "urpx:booleanValue": bool_val},
    }


def boolop(bn_id, op, operands, logic_expression=None):
    n = {
        "@type": "urpx:BooleanOperationNode", "@id": bn_id,
        "urpx:operator": {"@id": f"urpx:{op}Operator"},
        "urpx:operandNodes": operands,
    }
    if logic_expression:
        n["urpx:logicExpression"] = logic_expression
    return n


def expr(cx_id, root):
    return {"@type": "urpx:ConditionExpression", "@id": cx_id, "urpx:rootNode": root}


# ---- Eligibility -----------------------------------------------------------
eligibility_rule = {
    "@type": "urpx:EligibilityRule",
    "@id": "cpau:e3-er-eligibility",
    "urpx:name": "Customer-owned generation, not NEM-eligible, without interval meter",
    "urpx:description": (
        "Applies to customer-owned power generating facilities that are NOT "
        "eligible for net metering (per Section A) and that are NOT equipped "
        "with an interval meter (Section C.1 case). Customers with interval "
        "meters take Section C.2 buyback rates which are not modeled in v1 "
        "(see deferred follow-up). Customers with rated capacity > 1 MW may "
        "request the market-based buyback rate per Section C.3 (also deferred)."
    ),
    "urpx:hasConditionExpression": expr(
        "cpau:e3-cx-eligibility",
        boolop("cpau:e3-bn-eligibility-and", "and", [
            cn_eq_str("cpau:e3-cn-customer-owned-generation",
                      "facilityType", "Customer-owned generation"),
            cn_eq_bool("cpau:e3-cn-not-nem-eligible",
                       "nemEligible", False),
            cn_eq_bool("cpau:e3-cn-no-interval-meter",
                       "hasIntervalMeter", False),
        ], logic_expression=(
            "facilityType = 'Customer-owned generation' AND nemEligible = false "
            "AND hasIntervalMeter = false"
        )),
    ),
}

# ---- Seasons ---------------------------------------------------------------
season_summer = {
    "@type": "urpx:Season", "@id": "cpau:e3-season-summer",
    "urpx:seasonName": "Summer", "urpx:yearlyRecurrence": True,
    "urpx:month": ["--05", "--06", "--07", "--08", "--09", "--10"],
}
season_winter = {
    "@type": "urpx:Season", "@id": "cpau:e3-season-winter",
    "urpx:seasonName": "Winter", "urpx:yearlyRecurrence": True,
    "urpx:month": ["--11", "--12", "--01", "--02", "--03", "--04"],
}

# ---- MetricInputs (REVERSE FLOW for both energy and capacity) --------------
mi_energy_export = {
    "@type": "urpx:MetricInput", "@id": "cpau:e3-mi-energy-export",
    "urpx:name": "Customer-generated energy delivered to utility (kWh, reverse flow)",
    "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
    "urpx:hasMetricSpecification": {
        "@type": "urpx:MetricSpecification", "@id": "cpau:e3-ms-energy-export",
        "urpx:measurementKind": {"@id": "urpx:energy"},
        "urpx:unitOfMeasure": {"@id": "urpx:kWh"},
        "urpx:flowDirection": {"@id": "urpx:reverse"},
    },
}
mi_firm_capacity = {
    "@type": "urpx:MetricInput", "@id": "cpau:e3-mi-firm-capacity",
    "urpx:name": "Customer firm-power contracted capacity (kW, reverse flow)",
    "urpx:metricInputType": {"@id": "urpx:measuredMetricInput"},
    "urpx:hasMetricSpecification": {
        "@type": "urpx:MetricSpecification", "@id": "cpau:e3-ms-firm-capacity",
        "urpx:measurementKind": {"@id": "urpx:demand"},
        "urpx:unitOfMeasure": {"@id": "urpx:kW"},
        "urpx:flowDirection": {"@id": "urpx:reverse"},
    },
}

# ---- Ledgers ---------------------------------------------------------------
ledgers = [
    {"@type": "urpx:Ledger", "@id": "cpau:e3-ledger-energy-buyback",
     "urpx:name": "Customer-owned-generation energy buyback",
     "urpx:ledgerType": {"@id": "urpx:supplyLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e3-mi-energy-export"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e3-ledger-firm-capacity-credit",
     "urpx:name": "Firm-power capacity credit",
     "urpx:ledgerType": {"@id": "urpx:supplyLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e3-mi-firm-capacity"}},
]

# ---- PriceDefinitions ------------------------------------------------------
# 2 energy buyback PDs (Summer/Winter) — applies to both Firm and Non-Firm
# 2 capacity-credit PDs (Summer/Winter) — Firm-only via inline ApplicabilityGroup
def pd_energy_buyback(pd_id, name, season_id):
    return {
        "@type": "urpx:PriceDefinition", "@id": pd_id, "urpx:name": name,
        "urpx:chargeType": {"@id": "urpx:creditEnergy"},
        "urpx:chargeCategory": {"@id": "urpx:discount"},
        "urpx:billPortion": {"@id": "urpx:bundledPortion"},
        "urpx:appliesInSeason": {"@id": season_id},
        "urpx:referencesLedger": {"@id": "cpau:e3-ledger-energy-buyback"},
        "urpx:referencesMetricInput": {"@id": "cpau:e3-mi-energy-export"},
    }


def firm_applicability_group(suffix):
    return {
        "@type": "urpx:ApplicabilityGroup",
        "@id": f"cpau:e3-ag-firm-power-{suffix}",
        "urpx:name": "Firm power customers only",
        "urpx:hasConditionExpression": expr(
            f"cpau:e3-cx-firm-power-{suffix}",
            cn_eq_str(f"cpau:e3-cn-firm-power-{suffix}", "powerType", "Firm"),
        ),
    }


def pd_capacity_credit(pd_id, name, season_id, ag_suffix):
    return {
        "@type": "urpx:PriceDefinition", "@id": pd_id, "urpx:name": name,
        "urpx:chargeType": {"@id": "urpx:creditGeneration"},
        "urpx:chargeCategory": {"@id": "urpx:discount"},
        "urpx:billPortion": {"@id": "urpx:bundledPortion"},
        "urpx:appliesInSeason": {"@id": season_id},
        "urpx:hasApplicabilityGroup": firm_applicability_group(ag_suffix),
        "urpx:baseQuantity": "1",
        "urpx:hasCalculationMethod": {
            "@type": "urpx:CalculationMethod", "@id": f"{pd_id}-cm",
            "urpx:intervalDuration": "P1M",
        },
        "urpx:referencesLedger": {"@id": "cpau:e3-ledger-firm-capacity-credit"},
        "urpx:referencesMetricInput": {"@id": "cpau:e3-mi-firm-capacity"},
    }


pds = [
    pd_energy_buyback("cpau:e3-pd-energy-summer", "Energy Buyback Summer", "cpau:e3-season-summer"),
    pd_energy_buyback("cpau:e3-pd-energy-winter", "Energy Buyback Winter", "cpau:e3-season-winter"),
    pd_capacity_credit("cpau:e3-pd-firm-capacity-summer", "Firm Capacity Credit Summer", "cpau:e3-season-summer", "summer"),
    pd_capacity_credit("cpau:e3-pd-firm-capacity-winter", "Firm Capacity Credit Winter", "cpau:e3-season-winter", "winter"),
]

PRICE_VALUES = {
    "cpau:e3-pd-energy-summer":         "0.07902",
    "cpau:e3-pd-energy-winter":         "0.07831",
    "cpau:e3-pd-firm-capacity-summer":  "4.32",
    "cpau:e3-pd-firm-capacity-winter":  "4.32",
}

prices = []
for pd in pds:
    pd_id = pd["@id"]
    prices.append({
        "@type": "urpx:Price",
        "@id": pd_id.replace("-pd-", "-price-"),
        "urpx:name": pd["urpx:name"],
        "urpx:referencesPriceDefinition": {"@id": pd_id},
        "urpx:startDate": "2007-07-01",
        "urpx:unitPrice": PRICE_VALUES[pd_id],
    })

# ---- Assembly --------------------------------------------------------------
billing_model = {
    "@type": "urpx:BillingModel", "@id": "cpau:e3-billing-model",
    "urpx:hasLedger": ledgers,
    "urpx:hasPriceDefinition": pds,
}

plan_elements = {
    "@type": "urpx:PlanElements", "@id": "cpau:e3-plan-elements",
    "urpx:hasSeasons": [season_summer, season_winter],
    "urpx:hasMetricInput": [mi_energy_export, mi_firm_capacity],
    "urpx:hasBillingModel": billing_model,
}

prices_block = {
    "@type": "urpx:Prices", "@id": "cpau:e3-prices",
    "urpx:hasPriceSet": [{
        "@type": "urpx:PriceSet", "@id": "cpau:e3-price-set",
        "urpx:hasPrice": prices,
    }],
}

data_source_reference = {
    "@type": "urpx:DataSourceReference", "@id": "cpau:e3-dsr",
    "urpx:name": "CPAU Schedule E-3 (effective 2007-07-01)",
    "urpx:fileName": "e-3-rate-effective-2007-07-01.pdf",
    "urpx:url": "https://www.paloalto.gov/files/assets/public/v/1/utilities/rates-schedules-for-utilities/commercial-utility-rates/e-3-rate-effective-2007-07-01.pdf",
    "urpx:mediaType": {"@id": "urpx:applicationPdf"},
    "urpx:dataSourceType": {"@id": "urpx:utilityWebsiteSource"},
    "urpx:dateRetrieved": "2026-04-30",
}

publishing_org = {
    "@type": "urpx:Organization", "@id": "org:utility-cpau",
    "urpx:legalName": "City of Palo Alto Utilities",
    "urpx:eiaId": "3203",
    "urpx:organizationType": {"@id": "urpx:municipalOrganization"},
}

rpv = {
    "@type": "urpx:RatePlanVersion", "@id": "cpau:e-3-2007-07-01",
    "urpx:version": "1.0",
    "urpx:effectiveDateTime": "2007-07-01T00:00:00",
    "urpx:description": (
        "CPAU Schedule E-3 (Customer-Owned Generation), effective 2007-07-01 — "
        "buyback rates the utility pays for power produced by customer-owned "
        "generation facilities that are NOT NEM-eligible. Long-stable schedule "
        "(no published reissues since 2007). V1 models the WITHOUT-interval-"
        "meter case only (Section C.1): 2 seasons; flat per-kWh energy "
        "buyback (applies to both Firm and Non-Firm power); plus a Firm-only "
        "$4.32/kW/month capacity credit. Reverse-flow direction throughout — "
        "first reverse-flow filing in the urpx-tariffs corpus (the existing "
        "CPAU E-EEC-1 / E-NSE-1 modifiers are also reverse-flow but ride "
        "inside CPAU E-1 2025-09-01's @graph). DEFERRED to follow-up: "
        "Section C.2 with-interval-meter TOU buyback (3 TOU periods Summer + "
        "2 TOU periods Winter, with TOU windows that DIFFER from CPAU E-4 "
        "TOU / E-7 TOU); Section C.3 market-based buyback rate for "
        "facilities > 1 MW (range pricing, $2-10/kW, $0.03-0.20/kWh)."
    ),
    "urpx:customerChoice": {"@id": "urpx:voluntaryChoice"},
    "urpx:isDefault": False,
    "urpx:changeReason": {"@id": "urpx:initial"},
    "urpx:serviceRole": {"@id": "urpx:bundledServiceRole"},
    "urpx:publishedBy": publishing_org,
    "urpx:hasDataSourceReference": data_source_reference,
    "urpx:hasEligibilityRule": [eligibility_rule],
    "urpx:hasPlanElements": plan_elements,
    "urpx:hasPrices": prices_block,
}

rate_plan = {
    "@type": "urpx:RatePlan", "@id": "cpau:e-3",
    "urpx:name": "Customer-Owned Generation Retail Rate",
    "urpx:ratePlanUniqueIdentifier": "CPAU-E-3",
    "urpx:initialEffectiveDate": "2007-07-01",
    "urpx:timezoneIdentifier": "America/Los_Angeles",
    "urpx:hasRatePlanVersion": rpv,
}

doc = {"@context": CONTEXT, "@graph": [rate_plan]}


def main():
    # Refuse rather than create. This path predates the 2026-09-20 restructure,
    # so mkdir(parents=True) here wrote the filing into a ca/<class>/ tree that
    # dev/corpus.py does not walk: the write succeeded, the byte count printed,
    # and every lint kept passing over a corpus that had silently lost the file.
    # Not retargeted at the live filing on purpose, because this script's inline
    # data predates it and would overwrite curated work.
    if not OUT.parent.is_dir():
        raise SystemExit(
            f"REFUSING: {OUT.parent} does not exist. This writer targets the "
            f"pre-2026-09-20 layout; see dev/corpus.py filing_path() for the "
            f"current shape. Creating the directory would lose the filing silently."
        )
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(pds)} PDs)")


if __name__ == "__main__":
    main()
