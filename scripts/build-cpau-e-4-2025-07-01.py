#!/usr/bin/env python3
"""
Build ca/pou/cpau/e-4/versions/2025-07-01/rate-plan_cpau_e-4_2025-07-01.jsonld.

CPAU Schedule E-4: Medium Non-Residential Electric Service. Demand-metered
Secondary service for customers with maximum demand BELOW 1000 kW. Non-TOU
sibling of E-4 TOU (which adds TOU + a 500-1000 kW sustained eligibility
constraint and is voluntary opt-in).

Source PDF sha256 4718a89bab6269b62ede59f7eed226585bafe2e746e59c9f0183f3a2831cff63
retrieved from paloalto.gov 2026-04-30.

STRUCTURE (much simpler than E-4 TOU):
- 2 seasons (Summer May–Oct, Winter Nov–Apr)
- NO TOU within periods
- Single energy rate per season (3-component unbundled: commodity /
  distribution / public-benefits)
- Single demand charge per season (2-component: commodity / distribution),
  computed as the max kW measured in any 15-minute interval during the
  billing month (urpx:CalculationMethod with aggregationMethod=urpx:maximum,
  intervalDuration=P1M)
- Customer charge $126.24/month

Total: 6 energy PDs + 4 demand PDs + 1 customer-charge PD = 11 PDs.

Reuses the CPAU E-2 non-TOU seasonal pattern (urpx:appliesInSeason on
PriceDefinition + urpx:hasSeasons on PlanElements) and the E-4 TOU
demand-charge pattern (urpx:demand measurementKind, urpx:kW unit, demand
MetricInput with PT15M, max-aggregation CalculationMethod).

DEFERRED to existing follow-up issues:
  - Section D.5 Primary Voltage Discount (2.5% for >2 kV) — the project tracker
    (originally filed for E-4 TOU; generalize to all CPAU commercial)
  - Section D.6 Standby Charge — the project tracker (originally filed for E-4 TOU;
    generalize)
  - Section D.3 TES carve-out (Thermal Energy Storage customers' billing
    demand uses noon-6pm weekday window instead of all-hours) — new bd
    issue to file after this filing lands

Per-component rates from Section C of the PDF:
  Summer:
    Demand: 11.09 + 38.08         = 49.17 / kW
    Energy: 0.12441 + 0.02797 + 0.00604 = 0.15842 / kWh
  Winter:
    Demand:  2.60 + 23.49         = 26.09 / kW
    Energy: 0.08028 + 0.02797 + 0.00604 = 0.11429 / kWh
  Customer Charge: 126.24 / month
"""
import json
from pathlib import Path

ROOT = Path(str(Path(__file__).resolve().parent.parent))
OUT = ROOT / "ca/pou/cpau/e-4/versions/2025-07-01/rate-plan_cpau_e-4_2025-07-01.jsonld"

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
    "urpx:decimalValue": {"@type": "xsd:decimal"},
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


def cn_lt_decimal(cn_id, custom_prop, decimal_val):
    return {
        "@type": "urpx:ComparisonNode", "@id": cn_id,
        "urpx:operator": {"@id": "urpx:lessThanOperator"},
        "urpx:leftOperand": {"@type": "urpx:CustomOperandNode", "urpx:customConditionProperty": custom_prop},
        "urpx:rightOperand": {"@type": "urpx:CustomOperandNode", "urpx:decimalValue": decimal_val},
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
    "@id": "cpau:e4-er-eligibility",
    "urpx:name": "Demand-metered Secondary, max demand below 1000 kW",
    "urpx:description": (
        "Applies to customers receiving Demand metered Secondary Electric "
        "Service whose maximum monthly demand is below 1000 kW. May include "
        "master-metered multi-family facilities or other facilities requiring "
        "demand-metered service, as determined by the City. Per Section A of "
        "the published Schedule E-4 (sheet E-4-1, effective 2025-07-01)."
    ),
    "urpx:hasConditionExpression": expr(
        "cpau:e4-cx-eligibility",
        boolop("cpau:e4-bn-eligibility-and", "and", [
            cn_eq_str("cpau:e4-cn-demand-metered", "metering", "Demand metered Secondary"),
            cn_lt_decimal("cpau:e4-cn-demand-below-1000", "monthlyMaxDemand_kW", "1000"),
        ], logic_expression=(
            "metering = 'Demand metered Secondary' AND monthlyMaxDemand_kW < 1000"
        )),
    ),
}

# ---- Seasons ---------------------------------------------------------------
season_summer = {
    "@type": "urpx:Season", "@id": "cpau:e4-season-summer",
    "urpx:seasonName": "Summer", "urpx:yearlyRecurrence": True,
    "urpx:month": ["--05", "--06", "--07", "--08", "--09", "--10"],
}
season_winter = {
    "@type": "urpx:Season", "@id": "cpau:e4-season-winter",
    "urpx:seasonName": "Winter", "urpx:yearlyRecurrence": True,
    "urpx:month": ["--11", "--12", "--01", "--02", "--03", "--04"],
}

# ---- MetricInputs ----------------------------------------------------------
mi_energy = {
    "@type": "urpx:MetricInput", "@id": "cpau:e4-mi-energy",
    "urpx:name": "Energy consumed (kWh)",
    "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
    "urpx:hasMetricSpecification": {
        "@type": "urpx:MetricSpecification", "@id": "cpau:e4-ms-energy",
        "urpx:measurementKind": {"@id": "urpx:energy"},
        "urpx:unitOfMeasure": {"@id": "urpx:kWh"},
        "urpx:flowDirection": {"@id": "urpx:forward"},
    },
}
mi_demand = {
    "@type": "urpx:MetricInput", "@id": "cpau:e4-mi-demand",
    "urpx:name": "Demand (kW, 15-minute interval)",
    "urpx:metricInputType": {"@id": "urpx:measuredMetricInput"},
    "urpx:hasMetricSpecification": {
        "@type": "urpx:MetricSpecification", "@id": "cpau:e4-ms-demand",
        "urpx:measurementKind": {"@id": "urpx:demand"},
        "urpx:unitOfMeasure": {"@id": "urpx:kW"},
        "urpx:flowDirection": {"@id": "urpx:forward"},
        "urpx:intervalDuration": "PT15M",
        "urpx:intervalType": {"@id": "urpx:fifteenMinuteInterval"},
    },
}
mi_meter_count = {
    "@type": "urpx:MetricInput", "@id": "cpau:e4-mi-meter-count",
    "urpx:name": "Meter count",
    "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
    "urpx:profileMetricProperty": {"@id": "urpx:meterCount"},
}

# ---- Ledgers ---------------------------------------------------------------
ledgers = [
    {"@type": "urpx:Ledger", "@id": "cpau:e4-ledger-energy-commodity",
     "urpx:name": "Energy — Commodity", "urpx:ledgerType": {"@id": "urpx:supplyLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e4-mi-energy"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e4-ledger-energy-distribution",
     "urpx:name": "Energy — Distribution", "urpx:ledgerType": {"@id": "urpx:distributionLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e4-mi-energy"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e4-ledger-energy-public-benefits",
     "urpx:name": "Energy — Public Benefits", "urpx:ledgerType": {"@id": "urpx:bundledLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e4-mi-energy"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e4-ledger-demand-commodity",
     "urpx:name": "Demand — Commodity", "urpx:ledgerType": {"@id": "urpx:supplyLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e4-mi-demand"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e4-ledger-demand-distribution",
     "urpx:name": "Demand — Distribution", "urpx:ledgerType": {"@id": "urpx:distributionLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e4-mi-demand"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e4-ledger-service",
     "urpx:name": "Customer (service) charge", "urpx:ledgerType": {"@id": "urpx:profileMetricLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e4-mi-meter-count"}},
]


# ---- PriceDefinitions ------------------------------------------------------
def pd_energy(pd_id, name, ledger_id, season_id):
    return {
        "@type": "urpx:PriceDefinition", "@id": pd_id, "urpx:name": name,
        "urpx:chargeType": {"@id": "urpx:usageCharge"},
        "urpx:chargeCategory": {"@id": "urpx:auxiliaryCharge"},
        "urpx:billPortion": {"@id": "urpx:supplyPortion"},
        "urpx:appliesInSeason": {"@id": season_id},
        "urpx:referencesLedger": {"@id": ledger_id},
        "urpx:referencesMetricInput": {"@id": "cpau:e4-mi-energy"},
    }


def pd_demand(pd_id, name, ledger_id, season_id):
    return {
        "@type": "urpx:PriceDefinition", "@id": pd_id, "urpx:name": name,
        "urpx:chargeType": {"@id": "urpx:demandDirect"},
        "urpx:chargeCategory": {"@id": "urpx:auxiliaryCharge"},
        "urpx:billPortion": {"@id": "urpx:supplyPortion"},
        "urpx:appliesInSeason": {"@id": season_id},
        "urpx:referencesLedger": {"@id": ledger_id},
        "urpx:referencesMetricInput": {"@id": "cpau:e4-mi-demand"},
        "urpx:hasCalculationMethod": {
            "@type": "urpx:CalculationMethod", "@id": f"{pd_id}-cm",
            "urpx:aggregationMethod": {"@id": "urpx:maximum"},
            "urpx:intervalDuration": "P1M",
            "urpx:intervalType": {"@id": "urpx:monthlyInterval"},
            "urpx:description": (
                "Maximum demand (kW) measured in any 15-minute interval at any "
                "time during the monthly billing period. Per Section D.3 of the "
                "PDF, the City may use a 5-minute interval at its discretion "
                "for customers with intermittent or fluctuating loads; the "
                "default 15-minute interval is modeled here."
            ),
        },
    }


pds_energy = []
energy_specs = [
    ("summer", "cpau:e4-season-summer"),
    ("winter", "cpau:e4-season-winter"),
]
for sname, sid in energy_specs:
    pds_energy.append(pd_energy(
        f"cpau:e4-pd-energy-commodity-{sname}",
        f"Energy Commodity {sname.title()}",
        "cpau:e4-ledger-energy-commodity", sid))
    pds_energy.append(pd_energy(
        f"cpau:e4-pd-energy-distribution-{sname}",
        f"Energy Distribution {sname.title()}",
        "cpau:e4-ledger-energy-distribution", sid))
    pds_energy.append(pd_energy(
        f"cpau:e4-pd-energy-public-benefits-{sname}",
        f"Energy Public Benefits {sname.title()}",
        "cpau:e4-ledger-energy-public-benefits", sid))

pds_demand = []
for sname, sid in energy_specs:
    pds_demand.append(pd_demand(
        f"cpau:e4-pd-demand-commodity-{sname}",
        f"Demand Commodity {sname.title()}",
        "cpau:e4-ledger-demand-commodity", sid))
    pds_demand.append(pd_demand(
        f"cpau:e4-pd-demand-distribution-{sname}",
        f"Demand Distribution {sname.title()}",
        "cpau:e4-ledger-demand-distribution", sid))

customer_charge_pd = {
    "@type": "urpx:PriceDefinition", "@id": "cpau:e4-pd-customer-charge",
    "urpx:name": "Customer Charge",
    "urpx:chargeType": {"@id": "urpx:serviceMetered"},
    "urpx:chargeCategory": {"@id": "urpx:serviceCharge"},
    "urpx:billPortion": {"@id": "urpx:supplyPortion"},
    "urpx:baseQuantity": "1",
    "urpx:hasCalculationMethod": {
        "@type": "urpx:CalculationMethod", "@id": "cpau:e4-pd-customer-charge-cm",
        "urpx:intervalDuration": "P1M",
    },
    "urpx:referencesLedger": {"@id": "cpau:e4-ledger-service"},
}

all_pds = pds_energy + pds_demand + [customer_charge_pd]

# ---- Prices (the actual rate values) ---------------------------------------
PRICE_VALUES = {
    "cpau:e4-pd-energy-commodity-summer":         "0.12441",
    "cpau:e4-pd-energy-distribution-summer":      "0.02797",
    "cpau:e4-pd-energy-public-benefits-summer":   "0.00604",
    "cpau:e4-pd-energy-commodity-winter":         "0.08028",
    "cpau:e4-pd-energy-distribution-winter":      "0.02797",
    "cpau:e4-pd-energy-public-benefits-winter":   "0.00604",
    "cpau:e4-pd-demand-commodity-summer":         "11.09",
    "cpau:e4-pd-demand-distribution-summer":      "38.08",
    "cpau:e4-pd-demand-commodity-winter":         "2.60",
    "cpau:e4-pd-demand-distribution-winter":      "23.49",
    "cpau:e4-pd-customer-charge":                 "126.24",
}

prices_list = []
for pd in all_pds:
    pd_id = pd["@id"]
    prices_list.append({
        "@type": "urpx:Price",
        "@id": pd_id.replace("-pd-", "-price-"),
        "urpx:name": pd["urpx:name"],
        "urpx:referencesPriceDefinition": {"@id": pd_id},
        "urpx:startDate": "2025-07-01",
        "urpx:unitPrice": PRICE_VALUES[pd_id],
    })

# ---- Assembly --------------------------------------------------------------
billing_model = {
    "@type": "urpx:BillingModel", "@id": "cpau:e4-billing-model",
    "urpx:hasLedger": ledgers,
    "urpx:hasPriceDefinition": all_pds,
}

plan_elements = {
    "@type": "urpx:PlanElements", "@id": "cpau:e4-plan-elements",
    "urpx:hasSeasons": [season_summer, season_winter],
    "urpx:hasMetricInput": [mi_energy, mi_demand, mi_meter_count],
    "urpx:hasBillingModel": billing_model,
}

prices_block = {
    "@type": "urpx:Prices", "@id": "cpau:e4-prices",
    "urpx:hasPriceSet": [{
        "@type": "urpx:PriceSet", "@id": "cpau:e4-price-set",
        "urpx:hasPrice": prices_list,
    }],
}

data_source_reference = {
    "@type": "urpx:DataSourceReference", "@id": "cpau:e4-dsr",
    "urpx:name": "CPAU Schedule E-4 (effective 2025-07-01)",
    "urpx:fileName": "e-4-effective-2025-07-01.pdf",
    "urpx:url": "https://www.paloalto.gov/files/assets/public/v/5/utilities/rates-schedules-for-utilities/commercial-utility-rates/e-4-effective-2025-07-01.pdf",
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
    "@type": "urpx:RatePlanVersion", "@id": "cpau:e-4-2025-07-01",
    "urpx:version": "1.0",
    "urpx:effectiveDateTime": "2025-07-01T00:00:00",
    "urpx:description": (
        "CPAU Schedule E-4 (Medium Non-Residential Electric Service), effective "
        "2025-07-01. Demand-metered Secondary service for customers with maximum "
        "demand below 1000 kW. Two-period seasonal rate (Summer May–Oct, Winter "
        "Nov–Apr); no TOU within periods. Three-component unbundled energy "
        "($/kWh: commodity / distribution / public-benefits) plus a two-component "
        "demand charge ($/kW: commodity / distribution) plus a flat $126.24/month "
        "customer charge. Demand is measured as the max kW in any 15-minute "
        "interval over the billing month (urpx:CalculationMethod with "
        "aggregationMethod=urpx:maximum). NOT modeled in v1: Section D.5 Primary "
        "Voltage Discount, Section D.6 Standby Charge, Section D.3 TES carve-out "
        "(noon-6pm weekday demand window for Thermal Energy Storage customers)."
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

rate_plan = {
    "@type": "urpx:RatePlan", "@id": "cpau:e-4",
    "urpx:name": "Medium Non-Residential Electric Service",
    "urpx:ratePlanUniqueIdentifier": "CPAU-E-4",
    "urpx:initialEffectiveDate": "2025-07-01",
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
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(all_pds)} PDs)")


if __name__ == "__main__":
    main()
