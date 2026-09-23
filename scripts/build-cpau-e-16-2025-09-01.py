#!/usr/bin/env python3
"""
Build ca/pou/cpau/e-16/versions/2025-09-01/rate-plan_cpau_e-16_2025-09-01.jsonld.

CPAU Schedule E-16: Unmetered Electric Service. For customers with
unmetered electric service for billboards, telephone services, railroad
signals, cathodic protection units, traffic cameras, wireless antennas,
cable TV power supplies, automatic irrigation systems, and other
miscellaneous unmetered service.

Source PDF sha256 2cac3f08473a98babe23f2656cf4c5464568158f4d0a966417dc5c633da05f16
retrieved from paloalto.gov 2026-04-30.

PARTIAL MODELING — Section C.1 customer charge only.

Section C.2 published energy-charge clause is:
  "Energy Charge: (for all kWh supplied) using Electric Rate Schedule E-2
   plus all applicable riders"

This is a CROSS-SCHEDULE REFERENCE pattern. We can't see how to express
'this schedule's energy charge equals another schedule's energy charge
plus modifiers' structurally in URPX. Two related upstream questions
are in flight:
  - urpx-org/urpx#23 (modifier-to-base linkage) covers the modifier side
    of cross-file references.
  - A separate question for cross-RatePlan energy-charge reference may
    be appropriate; filing decision deferred until #23 resolves so we
    see whether the URPX-team's pattern for #23 also covers this case.

For now, the energy charge is described in prose only; only the customer
charge ($10.96/month) is modeled structurally. Consumers who need an
E-16 customer's full bill must combine this filing with cpau:e-2 (and
applicable rider modifiers) per the description text.

Section E miscellaneous fees (license fees for electric conduit usage,
utility pole attachments, communication equipment mounting) are also
deferred — they're annual rates rather than monthly, several apply
to physical infrastructure rather than energy service, and Section F
indexes them to CPI. Out of scope for v1; tracked as a follow-up.

Per-component rates from the PDF:
  Section C.1 Customer Charge: $10.96/month
  Section C.2 Energy: see E-2 (NOT modeled structurally)
  Section C.3 Minimum Charge = Customer Charge ($10.96)
"""
import json
from pathlib import Path

ROOT = Path(str(Path(__file__).resolve().parent.parent))
OUT = ROOT / "ca/pou/cpau/e-16/versions/2025-09-01/rate-plan_cpau_e-16_2025-09-01.jsonld"

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
    "urpx:isDefault": {"@type": "xsd:boolean"},
    "urpx:dateRetrieved": {"@type": "xsd:date"},
    "cpau": "https://example.com/cpau/",
    "org": "https://example.com/organizations/",
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
    "@id": "cpau:e16-er-eligibility",
    "urpx:name": "Unmetered electric service customer",
    "urpx:description": (
        "Applies to customers contracting with the City of Palo Alto Utilities "
        "for UNMETERED electric service for billboards, unmetered telephone "
        "services, telephone booths, railroad signals, cathodic protection "
        "units, traffic cameras, wireless antennas and related equipment, "
        "community antenna television and video systems, cable TV power "
        "supplies, automatic irrigation systems, and other miscellaneous "
        "Electric Utility fees to public agencies and private entities. Per "
        "Section A of the published Schedule E-16."
    ),
    "urpx:hasConditionExpression": expr(
        "cpau:e16-cx-eligibility",
        cn_eq_str("cpau:e16-cn-unmetered", "metering", "Unmetered"),
    ),
}

# ---- MetricInputs ----------------------------------------------------------
mi_meter_count = {
    "@type": "urpx:MetricInput", "@id": "cpau:e16-mi-meter-count",
    "urpx:name": "Service-account count (one per contracted unmetered service)",
    "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
    "urpx:profileMetricProperty": {"@id": "urpx:meterCount"},
}

# ---- Ledgers ---------------------------------------------------------------
ledgers = [
    {"@type": "urpx:Ledger", "@id": "cpau:e16-ledger-service",
     "urpx:name": "Customer (service) charge",
     "urpx:ledgerType": {"@id": "urpx:profileMetricLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e16-mi-meter-count"}},
]

# ---- PriceDefinitions ------------------------------------------------------
customer_charge_pd = {
    "@type": "urpx:PriceDefinition", "@id": "cpau:e16-pd-customer-charge",
    "urpx:name": "Customer Charge",
    "urpx:description": (
        "Per Section C.1 of the published Schedule E-16. Set using the "
        "annual SEIU salary schedule. Also serves as the minimum monthly "
        "charge per Section C.3."
    ),
    "urpx:chargeType": {"@id": "urpx:minimumBill"},
    "urpx:chargeCategory": {"@id": "urpx:serviceCharge"},
    "urpx:billPortion": {"@id": "urpx:bundledPortion"},
    "urpx:baseQuantity": "1",
    "urpx:hasCalculationMethod": {
        "@type": "urpx:CalculationMethod", "@id": "cpau:e16-pd-customer-charge-cm",
        "urpx:intervalDuration": "P1M",
    },
    "urpx:referencesLedger": {"@id": "cpau:e16-ledger-service"},
}

all_pds = [customer_charge_pd]

prices = [{
    "@type": "urpx:Price",
    "@id": "cpau:e16-price-customer-charge",
    "urpx:name": "Customer Charge",
    "urpx:referencesPriceDefinition": {"@id": "cpau:e16-pd-customer-charge"},
    "urpx:startDate": "2025-09-01",
    "urpx:unitPrice": "10.96",
}]

# ---- Assembly --------------------------------------------------------------
billing_model = {
    "@type": "urpx:BillingModel", "@id": "cpau:e16-billing-model",
    "urpx:hasLedger": ledgers,
    "urpx:hasPriceDefinition": all_pds,
}

plan_elements = {
    "@type": "urpx:PlanElements", "@id": "cpau:e16-plan-elements",
    "urpx:hasMetricInput": [mi_meter_count],
    "urpx:hasBillingModel": billing_model,
}

prices_block = {
    "@type": "urpx:Prices", "@id": "cpau:e16-prices",
    "urpx:hasPriceSet": [{
        "@type": "urpx:PriceSet", "@id": "cpau:e16-price-set",
        "urpx:hasPrice": prices,
    }],
}

data_source_reference = {
    "@type": "urpx:DataSourceReference", "@id": "cpau:e16-dsr",
    "urpx:name": "CPAU Schedule E-16 (effective 2025-09-01)",
    "urpx:fileName": "e-16-effective-2025-09-01.pdf",
    "urpx:url": "https://www.paloalto.gov/files/assets/public/v/2/utilities/rates-schedules-for-utilities/city-facility-utility-rates/e-16-effective-2025-09-01.pdf",
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
    "@type": "urpx:RatePlanVersion", "@id": "cpau:e-16-2025-09-01",
    "urpx:version": "1.0",
    "urpx:effectiveDateTime": "2025-09-01T00:00:00",
    "urpx:description": (
        "CPAU Schedule E-16 (Unmetered Electric Service), effective "
        "2025-09-01. PARTIAL MODELING. Customer charge $10.96/month "
        "(Section C.1) is modeled structurally. The Section C.2 energy "
        "charge — published as 'using Electric Rate Schedule E-2 plus all "
        "applicable riders' — is a cross-schedule reference for which we "
        "couldn't figure out a structural URPX pattern. Energy charge "
        "described in prose only; consumers needing a full E-16 bill must "
        "combine this filing with cpau:e-2 and applicable riders. Section D "
        "estimation method (kWh estimated from Total Wattage × annual "
        "operating hours / 1000 / 12) is a calculation rule documented in "
        "prose. Section E miscellaneous rates (license fees for conduit "
        "usage, utility pole attachments, communication equipment mounting) "
        "are not modeled in v1 — annual rates rather than monthly, indexed "
        "to CPI per Section F; deferred to a follow-up. Customer charge is "
        "also the minimum monthly charge per Section C.3."
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
    "@type": "urpx:RatePlan", "@id": "cpau:e-16",
    "urpx:name": "Unmetered Electric Service",
    "urpx:ratePlanUniqueIdentifier": "CPAU-E-16",
    "urpx:initialEffectiveDate": "2025-09-01",
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
