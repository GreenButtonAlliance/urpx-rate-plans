#!/usr/bin/env python3
"""
Build ca/pou/cpau/e-2/versions/2025-07-01/rate-plan_cpau_e-2_2025-07-01.jsonld.

CPAU Schedule E-2: Residential Master-Metered and Small Non-Residential
Electric Service. First commercial filing in our corpus. Source PDF
sha256 6712eab3cb9621774bc82cffb5689c5c323acb37278d4c9b9016a617be6157cc
retrieved from paloalto.gov 2026-04-29.

Structure: 2-period seasonal rate (Summer May–Oct, Winter Nov–Apr). No
TOU within periods, no tiers. 3-component unbundling per kWh:
commodity / distribution / public-benefits. Plus a flat $6.22/month
customer charge.

Eligibility (Sec A of the PDF): EITHER
  - non-residential customer + non-demand-metered service, OR
  - residential customer + master-metered multi-family + non-demand-metered

NEW URPX patterns exercised here (first time in our corpus):
  1. urpx:nonResidentialKind in eligibility — first commercial filing
  2. urpx:appliesInSeason on PriceDefinition — non-TOU seasonal
     applicability (PG&E uses TOU + ApplicabilityRule.month; CPAU
     E-1-TOU uses TOU + Season-via-TOUPeriod; this is the simplest
     case: just Season, no TOU)
  3. urpx:hasSeasons on PlanElements — declares the Season instances
  4. Customer charge with monthly intervalDuration P1M (residential
     CPAU + PG&E use P1D)
"""
import json
from pathlib import Path

ROOT = Path(str(Path(__file__).resolve().parent.parent))
OUT = ROOT / "ca/pou/cpau/e-2/versions/2025-07-01/rate-plan_cpau_e-2_2025-07-01.jsonld"

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
    "cpau": "https://rate-plans.grid-coordination.energy/cpau/",
    "org": "https://rate-plans.grid-coordination.energy/organizations/",
}


def cn_eq_obj(cn_id, prop_iri, value_iri):
    return {
        "@type": "urpx:ComparisonNode", "@id": cn_id,
        "urpx:operator": {"@id": "urpx:equalsOperator"},
        "urpx:leftOperand": {"@type": "urpx:ObjectOperandNode", "urpx:conditionProperty": {"@id": prop_iri}},
        "urpx:rightOperand": {"@type": "urpx:ObjectOperandNode", "urpx:referencesValue": {"@id": value_iri}},
    }


def cn_eq_str(cn_id, custom_prop, str_val):
    return {
        "@type": "urpx:ComparisonNode", "@id": cn_id,
        "urpx:operator": {"@id": "urpx:equalsOperator"},
        "urpx:leftOperand": {"@type": "urpx:CustomOperandNode", "urpx:customConditionProperty": custom_prop},
        "urpx:rightOperand": {"@type": "urpx:CustomOperandNode", "urpx:stringValue": str_val},
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
    "@id": "cpau:er-e2-eligibility",
    "urpx:name": "Non-residential non-demand or master-metered multi-family",
    "urpx:description": (
        "Applies to (a) non-residential customers receiving non-demand-metered "
        "Electric Service, OR (b) customers with accounts at master-metered "
        "multi-family facilities receiving non-demand-metered Electric Service. "
        "Per Section A of the published Schedule E-2 (sheet E-2-1, effective "
        "2025-07-01)."
    ),
    "urpx:hasConditionExpression": expr(
        "cpau:cx-e2-eligibility",
        boolop("cpau:bn-e2-eligibility-or", "or", [
            boolop("cpau:bn-e2-non-residential", "and", [
                cn_eq_obj("cpau:cn-e2-non-residential-kind", "urpx:hasCustomerKind", "urpx:nonResidentialKind"),
                cn_eq_str("cpau:cn-e2-non-residential-metering", "metering", "Non-Demand metered"),
            ], logic_expression="hasCustomerKind = nonResidentialKind AND metering = 'Non-Demand metered'"),
            boolop("cpau:bn-e2-master-metered-mf", "and", [
                cn_eq_obj("cpau:cn-e2-master-metered-residential-kind", "urpx:hasCustomerKind", "urpx:residentialKind"),
                cn_eq_str("cpau:cn-e2-master-metered-dwelling", "dwellingType", "Master-metered multi-family"),
                cn_eq_str("cpau:cn-e2-master-metered-metering", "metering", "Non-Demand metered"),
            ], logic_expression="hasCustomerKind = residentialKind AND dwellingType = 'Master-metered multi-family' AND metering = 'Non-Demand metered'"),
        ], logic_expression="(non-residential branch) OR (master-metered multi-family branch)"),
    ),
}

# ---- Seasons ---------------------------------------------------------------
season_summer = {
    "@type": "urpx:Season",
    "@id": "cpau:e2-season-summer",
    "urpx:seasonName": "Summer",
    "urpx:yearlyRecurrence": True,
    "urpx:month": ["--05", "--06", "--07", "--08", "--09", "--10"],
}
season_winter = {
    "@type": "urpx:Season",
    "@id": "cpau:e2-season-winter",
    "urpx:seasonName": "Winter",
    "urpx:yearlyRecurrence": True,
    "urpx:month": ["--11", "--12", "--01", "--02", "--03", "--04"],
}

# ---- MetricInputs ----------------------------------------------------------
mi_energy = {
    "@type": "urpx:MetricInput",
    "@id": "cpau:e2-mi-energy",
    "urpx:name": "Energy consumed (kWh)",
    "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
    "urpx:hasMetricSpecification": {
        "@type": "urpx:MetricSpecification",
        "@id": "cpau:e2-ms-energy",
        "urpx:measurementKind": {"@id": "urpx:energy"},
        "urpx:unitOfMeasure": {"@id": "urpx:kWh"},
        "urpx:flowDirection": {"@id": "urpx:forward"},
    },
}
mi_meter_count = {
    "@type": "urpx:MetricInput",
    "@id": "cpau:e2-mi-meter-count",
    "urpx:name": "Meter count",
    "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
    "urpx:profileMetricProperty": {"@id": "urpx:meterCount"},
}

# ---- Ledgers ---------------------------------------------------------------
ledgers = [
    {"@type": "urpx:Ledger", "@id": "cpau:e2-ledger-commodity",
     "urpx:name": "Commodity (energy supply)",
     "urpx:ledgerType": {"@id": "urpx:supplyLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e2-mi-energy"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e2-ledger-distribution",
     "urpx:name": "Distribution",
     "urpx:ledgerType": {"@id": "urpx:distributionLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e2-mi-energy"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e2-ledger-public-benefits",
     "urpx:name": "Public Benefits",
     "urpx:ledgerType": {"@id": "urpx:bundledLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e2-mi-energy"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e2-ledger-service",
     "urpx:name": "Customer (service) charge",
     "urpx:ledgerType": {"@id": "urpx:profileMetricLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e2-mi-meter-count"}},
]


# ---- PriceDefinitions ------------------------------------------------------
def pd_unbundled(pd_id, name, ledger_id, season_id):
    return {
        "@type": "urpx:PriceDefinition",
        "@id": pd_id,
        "urpx:name": name,
        "urpx:chargeType": {"@id": "urpx:usageCharge"},
        "urpx:chargeCategory": {"@id": "urpx:auxiliaryCharge"},
        "urpx:billPortion": {"@id": "urpx:supplyPortion"},
        "urpx:appliesInSeason": {"@id": season_id},
        "urpx:referencesLedger": {"@id": ledger_id},
    }


pds = [
    pd_unbundled("cpau:e2-pd-commodity-summer",        "Commodity Summer",        "cpau:e2-ledger-commodity",        "cpau:e2-season-summer"),
    pd_unbundled("cpau:e2-pd-distribution-summer",     "Distribution Summer",     "cpau:e2-ledger-distribution",     "cpau:e2-season-summer"),
    pd_unbundled("cpau:e2-pd-public-benefits-summer",  "Public Benefits Summer",  "cpau:e2-ledger-public-benefits",  "cpau:e2-season-summer"),
    pd_unbundled("cpau:e2-pd-commodity-winter",        "Commodity Winter",        "cpau:e2-ledger-commodity",        "cpau:e2-season-winter"),
    pd_unbundled("cpau:e2-pd-distribution-winter",     "Distribution Winter",     "cpau:e2-ledger-distribution",     "cpau:e2-season-winter"),
    pd_unbundled("cpau:e2-pd-public-benefits-winter",  "Public Benefits Winter",  "cpau:e2-ledger-public-benefits",  "cpau:e2-season-winter"),
    {
        "@type": "urpx:PriceDefinition",
        "@id": "cpau:e2-pd-customer-charge",
        "urpx:name": "Customer Charge",
        "urpx:chargeType": {"@id": "urpx:serviceMetered"},
        "urpx:chargeCategory": {"@id": "urpx:serviceCharge"},
        "urpx:billPortion": {"@id": "urpx:supplyPortion"},
        "urpx:baseQuantity": "1",
        "urpx:hasCalculationMethod": {
            "@type": "urpx:CalculationMethod",
            "@id": "cpau:e2-cm-monthly",
            "urpx:intervalDuration": "P1M",
        },
        "urpx:referencesLedger": {"@id": "cpau:e2-ledger-service"},
    },
]

# ---- Prices (the actual rate values) ---------------------------------------
PRICE_VALUES = {
    "cpau:e2-pd-commodity-summer":         "0.15075",
    "cpau:e2-pd-distribution-summer":      "0.10806",
    "cpau:e2-pd-public-benefits-summer":   "0.00604",
    "cpau:e2-pd-commodity-winter":         "0.09334",
    "cpau:e2-pd-distribution-winter":      "0.07352",
    "cpau:e2-pd-public-benefits-winter":   "0.00604",
    "cpau:e2-pd-customer-charge":          "6.22",
}


def price_for(pd):
    pd_id = pd["@id"]
    name = pd["urpx:name"]
    pid = pd_id.replace("e2-pd-", "e2-price-")
    p = {
        "@type": "urpx:Price",
        "@id": pid,
        "urpx:name": name,
        "urpx:referencesPriceDefinition": {"@id": pd_id},
        "urpx:startDate": "2025-07-01",
        "urpx:unitPrice": PRICE_VALUES[pd_id],
    }
    return p


prices_list = [price_for(pd) for pd in pds]

# ---- BillingModel ----------------------------------------------------------
billing_model = {
    "@type": "urpx:BillingModel",
    "@id": "cpau:e2-billing-model",
    "urpx:hasLedger": ledgers,
    "urpx:hasPriceDefinition": pds,
}

# ---- PlanElements ----------------------------------------------------------
plan_elements = {
    "@type": "urpx:PlanElements",
    "@id": "cpau:e2-plan-elements",
    "urpx:hasSeasons": [season_summer, season_winter],
    "urpx:hasMetricInput": [mi_energy, mi_meter_count],
    "urpx:hasBillingModel": billing_model,
}

# ---- Prices block ----------------------------------------------------------
prices_block = {
    "@type": "urpx:Prices",
    "@id": "cpau:e2-prices",
    "urpx:hasPriceSet": [
        {
            "@type": "urpx:PriceSet",
            "@id": "cpau:e2-price-set",
            "urpx:hasPrice": prices_list,
        }
    ],
}

# ---- DataSourceReference ---------------------------------------------------
data_source_reference = {
    "@type": "urpx:DataSourceReference",
    "@id": "cpau:e2-dsr",
    "urpx:name": "CPAU Schedule E-2 (effective 2025-07-01)",
    "urpx:fileName": "e-2-effective-2025-07-01.pdf",
    "urpx:url": "https://www.paloalto.gov/files/assets/public/v/5/utilities/rates-schedules-for-utilities/commercial-utility-rates/e-2-effective-2025-07-01.pdf",
    "urpx:mediaType": {"@id": "urpx:applicationPdf"},
    "urpx:dataSourceType": {"@id": "urpx:utilityWebsiteSource"},
    "urpx:dateRetrieved": "2026-04-29",
}

publishing_org = {
    "@type": "urpx:Organization",
    "@id": "org:utility-cpau",
    "urpx:legalName": "City of Palo Alto Utilities",
    "urpx:eiaId": "3203",
    "urpx:organizationType": {"@id": "urpx:municipalOrganization"},
}

# ---- RatePlanVersion -------------------------------------------------------
rpv = {
    "@type": "urpx:RatePlanVersion",
    "@id": "cpau:e-2-2025-07-01",
    "urpx:version": "1.0",
    "urpx:effectiveDateTime": "2025-07-01T00:00:00",
    "urpx:description": (
        "CPAU Schedule E-2 (Residential Master-Metered and Small Non-Residential "
        "Electric Service), effective 2025-07-01. Two-period seasonal rate "
        "(Summer May–Oct, Winter Nov–Apr) with three-component unbundled energy "
        "pricing (commodity / distribution / public benefits) plus a flat "
        "$6.22/month customer charge."
    ),
    "urpx:customerChoice": {"@id": "urpx:mandatoryChoice"},
    "urpx:isDefault": True,
    "urpx:changeReason": {"@id": "urpx:initial"},
    "urpx:serviceRole": {"@id": "urpx:bundledServiceRole"},
    "urpx:publishedBy": publishing_org,
    "urpx:hasDataSourceReference": data_source_reference,
    "urpx:hasEligibilityRule": [eligibility_rule],
    "urpx:hasPlanElements": plan_elements,
    "urpx:hasPrices": prices_block,
}

# ---- RatePlan --------------------------------------------------------------
rate_plan = {
    "@type": "urpx:RatePlan",
    "@id": "cpau:e-2",
    "urpx:name": "Residential Master-Metered and Small Non-Residential Electric Service",
    "urpx:ratePlanUniqueIdentifier": "CPAU-E-2",
    "urpx:initialEffectiveDate": "2025-07-01",
    "urpx:timezoneIdentifier": "America/Los_Angeles",
    "urpx:hasRatePlanVersion": rpv,
}

# ---- @graph wrapper --------------------------------------------------------
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
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
