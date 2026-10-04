#!/usr/bin/env python3
"""
Build ca/pou/cpau/e-7/versions/2025-07-01/rate-plan_cpau_e-7_2025-07-01.jsonld.

CPAU Schedule E-7: Large Non-Residential Electric Service. Demand-metered
service for customers with maximum demand AT LEAST 1000 kW per month per
site, sustained at that level for 3+ consecutive months in the last 12.
Non-TOU sibling of E-7 TOU. Same structural shape as CPAU E-4 (medium
non-residential demand-metered, no TOU) — different rate values, different
eligibility threshold, much higher customer charge ($578.08 vs $126.24/mo
for E-4).

Source PDF sha256 e28f2171d5f74d4a8eff66d1ed552826132917257c61a50699be6f5716ab4f4b
retrieved from paloalto.gov 2026-04-30.

STRUCTURE (parallel to CPAU E-4):
- 2 seasons (Summer May–Oct, Winter Nov–Apr)
- NO TOU within periods
- Single energy rate per season (3-component unbundled: commodity /
  distribution / public-benefits)
- Single demand charge per season (2-component: commodity / distribution),
  computed as max kW in any 15-minute interval during the billing month
- Customer charge $578.08/month

Total: 6 energy PDs + 4 demand PDs + 1 customer-charge PD = 11 PDs.

NOTABLE DIFFERENCES from CPAU E-4:
- Eligibility threshold inverted: monthlyMaxDemand_kW >= 1000 (E-4 is < 1000)
- Sustained-3-months eligibility clause (E-4 has none — E-4 is the default
  for the demand-metered <1000 kW segment; E-7 requires sustained-large)
- Section D.6 Voltage Discount is 2.8% (E-4 is 2.5%)
- Section D.7 Standby Charge has different rates: $40.79/kW summer,
  $27.75/kW winter (E-4: $46.58 / $23.49)
- Section D.3 site-aggregation: E-7 customers may bundle multiple Accounts
  under one Schedule if the Accounts are on contiguous parcels with a
  common billing address. URPX has no native vocabulary for site-level
  account aggregation — noted in description, not modeled.
- TES (Thermal Energy Storage) carve-out (Section D.4) is identical to
  E-4's D.3 — same noon-6pm weekday demand window for TES customers.

DEFERRED to existing follow-up issues:
  - Section D.6 Primary Voltage Discount (2.8% for >2 kV) — the project tracker
    (originally filed for E-4 TOU; broaden scope; note rate variance
    across schedules)
  - Section D.7 Standby Charge — the project tracker (originally filed for E-4 TOU;
    broaden; note rate variance)
  - Section D.4 TES carve-out — URPXT-* (filed for E-4; same shape applies)
  - Section D.3 site-aggregation — file new upstream URPX issue if the
    feature is needed for downstream consumers

Per-component rates from Section C of the PDF:
  Summer:
    Demand: 12.07 + 31.54         = 43.61 / kW
    Energy: 0.12786 + 0.00402 + 0.00604 = 0.13792 / kWh
  Winter:
    Demand:  2.82 + 27.75         = 30.57 / kW
    Energy: 0.07973 + 0.00393 + 0.00604 = 0.08970 / kWh
  Customer Charge: 578.08 / month
"""
import json
from pathlib import Path

ROOT = Path(str(Path(__file__).resolve().parent.parent))
OUT = ROOT / "ca/pou/cpau/e-7/versions/2025-07-01/rate-plan_cpau_e-7_2025-07-01.jsonld"

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
    "cpau": "https://rate-plans.grid-coordination.energy/cpau/",
    "org": "https://rate-plans.grid-coordination.energy/organizations/",
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


def cn_gte_decimal(cn_id, custom_prop, decimal_val):
    return {
        "@type": "urpx:ComparisonNode", "@id": cn_id,
        "urpx:operator": {"@id": "urpx:greaterThanOrEqualOperator"},
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
    "@id": "cpau:e7-er-eligibility",
    "urpx:name": "Demand-metered, max demand at least 1000 kW sustained 3+ months",
    "urpx:description": (
        "Applies to large non-residential customers receiving Demand metered "
        "Electric Service whose maximum monthly demand is at least 1000 kW per "
        "site, sustained at that level for at least three consecutive months "
        "during the most recent 12-month period. Per Section A of the "
        "published Schedule E-7 (sheet E-7-1, effective 2025-07-01)."
    ),
    "urpx:hasConditionExpression": expr(
        "cpau:e7-cx-eligibility",
        boolop("cpau:e7-bn-eligibility-and", "and", [
            cn_eq_str("cpau:e7-cn-demand-metered", "metering", "Demand metered"),
            cn_gte_decimal("cpau:e7-cn-demand-min-1000", "monthlyMaxDemand_kW", "1000"),
            cn_eq_str("cpau:e7-cn-sustained-3mo", "demandSustainedConsecutiveMonths", "3"),
        ], logic_expression=(
            "metering = 'Demand metered' AND monthlyMaxDemand_kW >= 1000 AND "
            "demandSustainedConsecutiveMonths = 3"
        )),
    ),
}

# ---- Seasons ---------------------------------------------------------------
season_summer = {
    "@type": "urpx:Season", "@id": "cpau:e7-season-summer",
    "urpx:seasonName": "Summer", "urpx:yearlyRecurrence": True,
    "urpx:month": ["--05", "--06", "--07", "--08", "--09", "--10"],
}
season_winter = {
    "@type": "urpx:Season", "@id": "cpau:e7-season-winter",
    "urpx:seasonName": "Winter", "urpx:yearlyRecurrence": True,
    "urpx:month": ["--11", "--12", "--01", "--02", "--03", "--04"],
}

# ---- MetricInputs ----------------------------------------------------------
mi_energy = {
    "@type": "urpx:MetricInput", "@id": "cpau:e7-mi-energy",
    "urpx:name": "Energy consumed (kWh)",
    "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
    "urpx:hasMetricSpecification": {
        "@type": "urpx:MetricSpecification", "@id": "cpau:e7-ms-energy",
        "urpx:measurementKind": {"@id": "urpx:energy"},
        "urpx:unitOfMeasure": {"@id": "urpx:kWh"},
        "urpx:flowDirection": {"@id": "urpx:forward"},
    },
}
mi_demand = {
    "@type": "urpx:MetricInput", "@id": "cpau:e7-mi-demand",
    "urpx:name": "Demand (kW, 15-minute interval)",
    "urpx:metricInputType": {"@id": "urpx:measuredMetricInput"},
    "urpx:hasMetricSpecification": {
        "@type": "urpx:MetricSpecification", "@id": "cpau:e7-ms-demand",
        "urpx:measurementKind": {"@id": "urpx:demand"},
        "urpx:unitOfMeasure": {"@id": "urpx:kW"},
        "urpx:flowDirection": {"@id": "urpx:forward"},
        "urpx:intervalDuration": "PT15M",
        "urpx:intervalType": {"@id": "urpx:fifteenMinuteInterval"},
    },
}
mi_meter_count = {
    "@type": "urpx:MetricInput", "@id": "cpau:e7-mi-meter-count",
    "urpx:name": "Meter count",
    "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
    "urpx:profileMetricProperty": {"@id": "urpx:meterCount"},
}

# ---- Ledgers ---------------------------------------------------------------
ledgers = [
    {"@type": "urpx:Ledger", "@id": "cpau:e7-ledger-energy-commodity",
     "urpx:name": "Energy — Commodity", "urpx:ledgerType": {"@id": "urpx:supplyLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e7-mi-energy"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e7-ledger-energy-distribution",
     "urpx:name": "Energy — Distribution", "urpx:ledgerType": {"@id": "urpx:distributionLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e7-mi-energy"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e7-ledger-energy-public-benefits",
     "urpx:name": "Energy — Public Benefits", "urpx:ledgerType": {"@id": "urpx:bundledLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e7-mi-energy"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e7-ledger-demand-commodity",
     "urpx:name": "Demand — Commodity", "urpx:ledgerType": {"@id": "urpx:supplyLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e7-mi-demand"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e7-ledger-demand-distribution",
     "urpx:name": "Demand — Distribution", "urpx:ledgerType": {"@id": "urpx:distributionLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e7-mi-demand"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e7-ledger-service",
     "urpx:name": "Customer (service) charge", "urpx:ledgerType": {"@id": "urpx:profileMetricLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e7-mi-meter-count"}},
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
        "urpx:referencesMetricInput": {"@id": "cpau:e7-mi-energy"},
    }


def pd_demand(pd_id, name, ledger_id, season_id):
    return {
        "@type": "urpx:PriceDefinition", "@id": pd_id, "urpx:name": name,
        "urpx:chargeType": {"@id": "urpx:demandDirect"},
        "urpx:chargeCategory": {"@id": "urpx:auxiliaryCharge"},
        "urpx:billPortion": {"@id": "urpx:supplyPortion"},
        "urpx:appliesInSeason": {"@id": season_id},
        "urpx:referencesLedger": {"@id": ledger_id},
        "urpx:referencesMetricInput": {"@id": "cpau:e7-mi-demand"},
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
    ("summer", "cpau:e7-season-summer"),
    ("winter", "cpau:e7-season-winter"),
]
for sname, sid in energy_specs:
    pds_energy.append(pd_energy(
        f"cpau:e7-pd-energy-commodity-{sname}",
        f"Energy Commodity {sname.title()}",
        "cpau:e7-ledger-energy-commodity", sid))
    pds_energy.append(pd_energy(
        f"cpau:e7-pd-energy-distribution-{sname}",
        f"Energy Distribution {sname.title()}",
        "cpau:e7-ledger-energy-distribution", sid))
    pds_energy.append(pd_energy(
        f"cpau:e7-pd-energy-public-benefits-{sname}",
        f"Energy Public Benefits {sname.title()}",
        "cpau:e7-ledger-energy-public-benefits", sid))

pds_demand = []
for sname, sid in energy_specs:
    pds_demand.append(pd_demand(
        f"cpau:e7-pd-demand-commodity-{sname}",
        f"Demand Commodity {sname.title()}",
        "cpau:e7-ledger-demand-commodity", sid))
    pds_demand.append(pd_demand(
        f"cpau:e7-pd-demand-distribution-{sname}",
        f"Demand Distribution {sname.title()}",
        "cpau:e7-ledger-demand-distribution", sid))

customer_charge_pd = {
    "@type": "urpx:PriceDefinition", "@id": "cpau:e7-pd-customer-charge",
    "urpx:name": "Customer Charge",
    "urpx:chargeType": {"@id": "urpx:serviceMetered"},
    "urpx:chargeCategory": {"@id": "urpx:serviceCharge"},
    "urpx:billPortion": {"@id": "urpx:supplyPortion"},
    "urpx:baseQuantity": "1",
    "urpx:hasCalculationMethod": {
        "@type": "urpx:CalculationMethod", "@id": "cpau:e7-pd-customer-charge-cm",
        "urpx:intervalDuration": "P1M",
    },
    "urpx:referencesLedger": {"@id": "cpau:e7-ledger-service"},
}

all_pds = pds_energy + pds_demand + [customer_charge_pd]

# ---- Prices (the actual rate values) ---------------------------------------
PRICE_VALUES = {
    "cpau:e7-pd-energy-commodity-summer":         "0.12786",
    "cpau:e7-pd-energy-distribution-summer":      "0.00402",
    "cpau:e7-pd-energy-public-benefits-summer":   "0.00604",
    "cpau:e7-pd-energy-commodity-winter":         "0.07973",
    "cpau:e7-pd-energy-distribution-winter":      "0.00393",
    "cpau:e7-pd-energy-public-benefits-winter":   "0.00604",
    "cpau:e7-pd-demand-commodity-summer":         "12.07",
    "cpau:e7-pd-demand-distribution-summer":      "31.54",
    "cpau:e7-pd-demand-commodity-winter":         "2.82",
    "cpau:e7-pd-demand-distribution-winter":      "27.75",
    "cpau:e7-pd-customer-charge":                 "578.08",
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
    "@type": "urpx:BillingModel", "@id": "cpau:e7-billing-model",
    "urpx:hasLedger": ledgers,
    "urpx:hasPriceDefinition": all_pds,
}

plan_elements = {
    "@type": "urpx:PlanElements", "@id": "cpau:e7-plan-elements",
    "urpx:hasSeasons": [season_summer, season_winter],
    "urpx:hasMetricInput": [mi_energy, mi_demand, mi_meter_count],
    "urpx:hasBillingModel": billing_model,
}

prices_block = {
    "@type": "urpx:Prices", "@id": "cpau:e7-prices",
    "urpx:hasPriceSet": [{
        "@type": "urpx:PriceSet", "@id": "cpau:e7-price-set",
        "urpx:hasPrice": prices_list,
    }],
}

data_source_reference = {
    "@type": "urpx:DataSourceReference", "@id": "cpau:e7-dsr",
    "urpx:name": "CPAU Schedule E-7 (effective 2025-07-01)",
    "urpx:fileName": "e-7-effective-2025-07-01.pdf",
    "urpx:url": "https://www.paloalto.gov/files/assets/public/v/6/utilities/rates-schedules-for-utilities/commercial-utility-rates/e-7-effective-2025-07-01.pdf",
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
    "@type": "urpx:RatePlanVersion", "@id": "cpau:e-7-2025-07-01",
    "urpx:version": "1.0",
    "urpx:effectiveDateTime": "2025-07-01T00:00:00",
    "urpx:description": (
        "CPAU Schedule E-7 (Large Non-Residential Electric Service), effective "
        "2025-07-01. Demand-metered service for customers with maximum demand "
        "at least 1000 kW per site sustained 3+ consecutive months in the most "
        "recent 12-month period. Two-period seasonal rate (Summer May–Oct, "
        "Winter Nov–Apr); no TOU within periods. Three-component unbundled "
        "energy ($/kWh: commodity / distribution / public-benefits) plus a "
        "two-component demand charge ($/kW: commodity / distribution) plus a "
        "flat $578.08/month customer charge. Demand is measured as the max kW "
        "in any 15-minute interval over the billing month "
        "(urpx:CalculationMethod with aggregationMethod=urpx:maximum). "
        "Section D.3 site-aggregation feature (qualifying customers may "
        "request service for multiple Accounts on contiguous parcels with a "
        "common billing address) is noted but not modeled — URPX has no "
        "native vocabulary for site-level account aggregation. NOT modeled "
        "in v1: Section D.6 Primary Voltage Discount (2.8% for >2 kV), "
        "Section D.7 Standby Charge, Section D.4 TES carve-out (noon-6pm "
        "weekday demand window for Thermal Energy Storage customers)."
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
    "@type": "urpx:RatePlan", "@id": "cpau:e-7",
    "urpx:name": "Large Non-Residential Electric Service",
    "urpx:ratePlanUniqueIdentifier": "CPAU-E-7",
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
