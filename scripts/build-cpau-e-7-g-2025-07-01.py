#!/usr/bin/env python3
"""
Build ca/pou/cpau/e-7-g/versions/2025-07-01/rate-plan-modifier_cpau_e-7-g_2025-07-01.jsonld.

CPAU Schedule E-7-G: Large Non-Residential GREEN POWER Electric Service.
A urpx:RatePlanModifier on the cpau:e-7 base that adds a Palo Alto Green
Charge ($0.0075/kWh) to E-7 customers participating in the Palo Alto
Green Program under the 100% Renewable Option.

Source PDF sha256 893342f553c7905560fc5278919fc082c722a8b051dcbff6893a060478d12099
retrieved from paloalto.gov 2026-04-30.

Sibling of CPAU E-2-G and E-4-G; same modifier pattern, different base.

NOTE on applicableToRatePlan: omitted here, matching the URPX-team
pattern in their pge-e-tou-c-vintage-pcia-2026-03-01 standalone modifier
test case. SHACL closed-world validation can't see the base RatePlan
declaration (in a sibling filing), so setting applicableToRatePlan to
{"@id": "cpau:e-7"} reports a class-membership violation. The modifier's
relationship to its base is described in prose only for now. Tracking
the structural-linkage question upstream as urpx-org/urpx#23; retrofit
once URPX team responds.

STRUCTURE:
- Single PriceDefinition: green-charge ($0.0075/kWh, both seasons)
- Single Price referencing it
- Modifier's own energy MetricInput + green-charge Ledger
- applicableToRatePlan: omitted pending urpx-org/urpx#23 (modifier-to-base
  linkage in standalone filings)

DEFERRED to follow-up bd issue:
  - 1000 kWh Block Purchase Option ($7.50 per 1000 kWh block).
    Different metric shape (per-block discrete purchase vs continuous
    per-kWh consumption); the per-block charge applies to a customer-
    designated quantity of blocks, not measured energy. Modeling
    questions: what MetricInput shape captures "blocks purchased"
    (per-customer state, not measured)? does URPX support discrete
    purchase semantics? File for follow-up.

Per-component rates from the PDF:
  100% Renewable Option (modeled here):
    Palo Alto Green Charge: 0.0075 / kWh (both seasons)
  1000 kWh Block Purchase Option (deferred):
    Palo Alto Green Charge: 7.50 / block of 1000 kWh
"""
import json
from pathlib import Path

ROOT = Path(str(Path(__file__).resolve().parent.parent))
OUT = ROOT / "ca/pou/cpau/e-7-g/versions/2025-07-01/rate-plan-modifier_cpau_e-7-g_2025-07-01.jsonld"

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
    "urpx:dateRetrieved": {"@type": "xsd:date"},
    "cpau": "https://example.com/cpau/",
    "org": "https://example.com/organizations/",
}

# ============================================================================
# MetricInput, Ledger, PriceDefinition, Price (the modifier's own pricing)
# ============================================================================
mi_energy = {
    "@type": "urpx:MetricInput", "@id": "cpau:e7g-mi-energy",
    "urpx:name": "Energy consumed (kWh)",
    "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
    "urpx:hasMetricSpecification": {
        "@type": "urpx:MetricSpecification", "@id": "cpau:e7g-ms-energy",
        "urpx:measurementKind": {"@id": "urpx:energy"},
        "urpx:unitOfMeasure": {"@id": "urpx:kWh"},
        "urpx:flowDirection": {"@id": "urpx:forward"},
    },
}

ledger_green = {
    "@type": "urpx:Ledger", "@id": "cpau:e7g-ledger-green-charge",
    "urpx:name": "Palo Alto Green Charge",
    "urpx:ledgerType": {"@id": "urpx:bundledLedger"},
    "urpx:referencesMetricInput": {"@id": "cpau:e7g-mi-energy"},
}

pd_green = {
    "@type": "urpx:PriceDefinition", "@id": "cpau:e7g-pd-green-charge",
    "urpx:name": "Palo Alto Green Charge (100% Renewable Option)",
    "urpx:chargeType": {"@id": "urpx:renewableFunding"},
    "urpx:chargeCategory": {"@id": "urpx:environmental"},
    "urpx:billPortion": {"@id": "urpx:supplyPortion"},
    "urpx:referencesLedger": {"@id": "cpau:e7g-ledger-green-charge"},
    "urpx:referencesMetricInput": {"@id": "cpau:e7g-mi-energy"},
}

price_green = {
    "@type": "urpx:Price",
    "@id": "cpau:e7g-price-green-charge",
    "urpx:name": "Palo Alto Green Charge",
    "urpx:referencesPriceDefinition": {"@id": "cpau:e7g-pd-green-charge"},
    "urpx:startDate": "2025-07-01",
    "urpx:unitPrice": "0.0075",
}

# ============================================================================
# Assembly — the modifier's own PlanElements + Prices
# ============================================================================
billing_model = {
    "@type": "urpx:BillingModel", "@id": "cpau:e7g-billing-model",
    "urpx:hasLedger": [ledger_green],
    "urpx:hasPriceDefinition": [pd_green],
}

plan_elements = {
    "@type": "urpx:PlanElements", "@id": "cpau:e7g-plan-elements",
    "urpx:hasMetricInput": [mi_energy],
    "urpx:hasBillingModel": billing_model,
}

prices_block = {
    "@type": "urpx:Prices", "@id": "cpau:e7g-prices",
    "urpx:hasPriceSet": [{
        "@type": "urpx:PriceSet", "@id": "cpau:e7g-price-set",
        "urpx:hasPrice": [price_green],
    }],
}

data_source_reference = {
    "@type": "urpx:DataSourceReference", "@id": "cpau:e7g-dsr",
    "urpx:name": "CPAU Schedule E-7-G (effective 2025-07-01)",
    "urpx:fileName": "e-7-g-effective-2025-07-01.pdf",
    "urpx:url": "https://www.paloalto.gov/files/assets/public/v/6/utilities/rates-schedules-for-utilities/commercial-utility-rates/e-7-g-effective-2025-07-01.pdf",
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

rpmv = {
    "@type": "urpx:RatePlanModifierVersion",
    "@id": "cpau:e-7-g-2025-07-01",
    "urpx:version": "2025-07-01",
    "urpx:modifierVersionNumber": "2025-07-01",
    "urpx:effectiveDateTime": "2025-07-01T00:00:00",
    "urpx:changeReason": {"@id": "urpx:initial"},
    "urpx:description": (
        "Palo Alto Green Program modifier on Schedule E-7 (Large "
        "Non-Residential Electric Service, demand-metered, >= 1000 kW "
        "sustained 3+ months). Applies to E-7 customers participating in "
        "the Palo Alto Green Program under the 100% Renewable Option, "
        "adding a $0.0075/kWh Palo Alto Green Charge to all energy "
        "consumption. Eligibility per Section A of the published Schedule "
        "E-7-G: customers who qualify for E-7 Service AND "
        "who choose to participate in the Palo Alto Green Program. The 1000 "
        "kWh Block Purchase Option ($7.50/block) is also published in the "
        "same rate filing but is not modeled here — different metric shape "
        "(per-block discrete purchase vs continuous per-kWh consumption); "
        "tracked as a follow-up."
    ),
    "urpx:priceCurrency": "USD",
    "urpx:commodity": {"@id": "urpx:electricity"},
    "urpx:serviceRole": {"@id": "urpx:bundledServiceRole"},
    # urpx:applicableToRatePlan omitted pending urpx-org/urpx#23 — the base
    # RatePlan (cpau:e-7) is in a sibling filing, and SHACL closed-world
    # validation can't confirm class membership across files. The modifier's
    # relationship to its base is captured in the description prose above.
    "urpx:publishedBy": publishing_org,
    "urpx:hasDataSourceReference": data_source_reference,
    "urpx:hasPlanElements": plan_elements,
    "urpx:hasPrices": prices_block,
}

rate_plan_modifier = {
    "@type": "urpx:RatePlanModifier",
    "@id": "cpau:e-7-g",
    "urpx:name": "Palo Alto Green Program (E-7 base)",
    "urpx:modifierUniqueIdentifier": "CPAU-E-7-G",
    "urpx:initialEffectiveDate": "2025-07-01",
    "urpx:timezoneIdentifier": "America/Los_Angeles",
    "urpx:hasRatePlanModifierVersion": rpmv,
}

doc = {"@context": CONTEXT, "@graph": [rate_plan_modifier]}


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
