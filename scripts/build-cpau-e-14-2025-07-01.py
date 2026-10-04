#!/usr/bin/env python3
"""
Build ca/pou/cpau/e-14/versions/2025-07-01/rate-plan_cpau_e-14_2025-07-01.jsonld.

CPAU Schedule E-14: Street Lights. Flat per-fixture-per-month rates for
street and highway lighting installations (and related traffic signals)
owned by governmental agencies other than the City of Palo Alto.

Source PDF sha256 49e522c59311aa2b05059b0bc7d0d20d2f072920dfdf9079e1761648c4c2c240
retrieved from paloalto.gov 2026-04-30.

STRUCTURE:
- Eligibility: any governmental agency other than the City of Palo Alto
  with street/highway lighting installations operated and maintained by
  CPAU. CPAU supplies electricity AND switching AND maintains the
  lighting system (lamps + glassware). Per Section A.
- One PriceDefinition per fixture type, each with a per-month flat
  rate (not metered — CPAU bills based on count of fixtures of each
  type that the customer has installed):
    - 1 mercury-vapor lamp (400W)
    - 4 high-pressure sodium vapor (HPSV) lamps (70/100/150/250W)
    - 5 LED lamps (70/100/150/175/250W-equivalent)
    - 4 traffic signal heads (12" RYG, 8" RYG, 12" Arrow RYG, 12" Beacon)
    - 1 pedestrian head
    - 1 controller
    - 1 speed signs
    - (other lamps: per Section D.5, CPAU prepares an interim rate for
      any lamp not on the schedule until the new rate is added)
- Each fixture type has its own MetricInput (count of fixtures of that
  type at the customer's installation), referenced by its PriceDefinition.
- One PriceDefinition per published fixture type, plus the switching surcharge.
- $2.50/month switching surcharge per separately-switched circuit
  (Section D.2) — modeled as an extra PD with custom-condition
  ApplicabilityGroup; only applies to circuits below 10 kW lamp load.
  Or noted in description and not modeled — I'll include it as a flat
  surcharge PD with prose noting the conditional applicability.

NEW URPX modeling territory exercised here for the first time in our corpus:
- Per-fixture-type pricing with a separate MetricInput per type (fixture
  counts as profileMetricInput). Conceptually parallel to ServiceTier
  but for discrete fixture enumerations rather than usage tiers.
- chargeType urpx:serviceNonMetered (vs. previous filings' usageCharge
  / serviceMetered / demandDirect).

DEFERRED to follow-up (description-only):
- Section D.5 interim-rate provision for lamps not on the schedule
  (operator's discretion; not a published rate).
- Section D.3 annual burning schedule (4100 hours/year operational rule).

Per-fixture rates from Section C of the PDF: see PRICE_VALUES below.
"""
import json
from pathlib import Path

ROOT = Path(str(Path(__file__).resolve().parent.parent))
OUT = ROOT / "ca/pou/cpau/e-14/versions/2025-07-01/rate-plan_cpau_e-14_2025-07-01.jsonld"

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
    "@id": "cpau:e14-er-eligibility",
    "urpx:name": "Governmental agency street/highway lighting (other than City of Palo Alto)",
    "urpx:description": (
        "Applies to street and highway lighting installations owned by any "
        "governmental agency other than the City of Palo Alto, where CPAU "
        "elects to operate and maintain the installation (supplying "
        "electricity, performing switching, and maintaining lamps and "
        "glassware). Per Section A of the published Schedule E-14."
    ),
    "urpx:hasConditionExpression": expr(
        "cpau:e14-cx-eligibility",
        boolop("cpau:e14-bn-eligibility-and", "and", [
            cn_eq_obj("cpau:e14-cn-non-residential", "urpx:hasCustomerKind", "urpx:nonResidentialKind"),
            cn_eq_str("cpau:e14-cn-customer-class", "customerClass", "Governmental Agency"),
            cn_eq_str("cpau:e14-cn-installation-type", "installationType", "Street/highway lighting"),
        ], logic_expression=(
            "hasCustomerKind = nonResidentialKind AND "
            "customerClass = 'Governmental Agency' AND "
            "installationType = 'Street/highway lighting'"
        )),
    ),
}

# ============================================================================
# Per-fixture-type MetricInputs, Ledgers, PriceDefinitions, Prices
# ============================================================================

# (fixture_id_slug, display_name, unit_price_per_month, category)
# category ∈ {"street-light", "traffic-signal"}
FIXTURES = [
    # Mercury-vapor lamps
    ("mv-400w",          "Mercury-Vapor Lamp 400W",          "53.53",  "street-light"),
    # High-pressure sodium vapor lamps
    ("hpsv-70w",         "HPSV Lamp 70W",                    "35.37",  "street-light"),
    ("hpsv-100w",        "HPSV Lamp 100W",                   "45.35",  "street-light"),
    ("hpsv-150w",        "HPSV Lamp 150W",                   "62.00",  "street-light"),
    ("hpsv-250w",        "HPSV Lamp 250W",                   "95.30",  "street-light"),
    # LED lamps
    ("led-70w-eq",       "LED Lamp 70W-equivalent",          "13.27",  "street-light"),
    ("led-100w-eq",      "LED Lamp 100W-equivalent",         "20.83",  "street-light"),
    ("led-150w-eq",      "LED Lamp 150W-equivalent",         "27.80",  "street-light"),
    ("led-175w-eq",      "LED Lamp 175W-equivalent",         "31.43",  "street-light"),
    ("led-250w",         "LED Lamp 250W",                    "46.87",  "street-light"),
    # Traffic signals
    ("tsig-12head-ryg",  "Traffic Signal 12\" Head (RYG)",   "27.12",  "traffic-signal"),
    ("tsig-8head-ryg",   "Traffic Signal 8\" Head (RYG)",    "23.55",  "traffic-signal"),
    ("tsig-12arrow-ryg", "Traffic Signal 12\" Arrow (RYG)",  "25.49",  "traffic-signal"),
    ("tsig-12beacon",    "Traffic Signal 12\" Beacon",       "10.19",  "traffic-signal"),
    ("tsig-pedestrian",  "Traffic Signal Pedestrian Head",    "9.36",  "traffic-signal"),
    ("tsig-controller",  "Traffic Signal Controller",        "20.05",  "traffic-signal"),
    ("tsig-speed-signs", "Speed Signs",                      "92.73",  "traffic-signal"),
]

# Two ledgers: one for street lights, one for traffic signals
ledgers = [
    {"@type": "urpx:Ledger", "@id": "cpau:e14-ledger-street-lights",
     "urpx:name": "Street lights — flat per-lamp-per-month service",
     "urpx:ledgerType": {"@id": "urpx:profileMetricLedger"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e14-ledger-traffic-signals",
     "urpx:name": "Traffic signals — flat per-fixture-per-month service",
     "urpx:ledgerType": {"@id": "urpx:profileMetricLedger"}},
]

LEDGER_BY_CATEGORY = {
    "street-light":   "cpau:e14-ledger-street-lights",
    "traffic-signal": "cpau:e14-ledger-traffic-signals",
}

metric_inputs = []
price_definitions = []
prices = []

for slug, name, unit_price, category in FIXTURES:
    mi_id = f"cpau:e14-mi-count-{slug}"
    pd_id = f"cpau:e14-pd-{slug}"
    price_id = f"cpau:e14-price-{slug}"

    mi = {
        "@type": "urpx:MetricInput", "@id": mi_id,
        "urpx:name": f"Count of fixtures: {name}",
        "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
    }
    metric_inputs.append(mi)

    # Each fixture-type ledger needs its OWN MetricInput link, since the
    # ledger's referencesMetricInput is single-valued and we want each PD
    # to gate on its own fixture count. Use the ledger as the category
    # bucket and let each PD reference its specific MetricInput directly.
    pd = {
        "@type": "urpx:PriceDefinition", "@id": pd_id,
        "urpx:name": name,
        "urpx:chargeType": {"@id": "urpx:serviceNonMetered"},
        "urpx:chargeCategory": {"@id": "urpx:serviceCharge"},
        "urpx:billPortion": {"@id": "urpx:bundledPortion"},
        "urpx:baseQuantity": "1",
        "urpx:hasCalculationMethod": {
            "@type": "urpx:CalculationMethod",
            "@id": f"{pd_id}-cm",
            "urpx:intervalDuration": "P1M",
        },
        "urpx:referencesLedger": {"@id": LEDGER_BY_CATEGORY[category]},
        "urpx:referencesMetricInput": {"@id": mi_id},
    }
    price_definitions.append(pd)

    price = {
        "@type": "urpx:Price",
        "@id": price_id,
        "urpx:name": name,
        "urpx:referencesPriceDefinition": {"@id": pd_id},
        "urpx:startDate": "2025-07-01",
        "urpx:unitPrice": unit_price,
    }
    prices.append(price)

# Switching surcharge ($2.50/month per separately-switched circuit when
# circuit lamp load < 10 kW). Modeled here as a separate PD with a custom
# condition; consumer is responsible for evaluating the 10-kW threshold.
mi_switching = {
    "@type": "urpx:MetricInput", "@id": "cpau:e14-mi-switching-circuit-count",
    "urpx:name": "Count of separately-switched circuits below 10 kW lamp load",
    "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
}
metric_inputs.append(mi_switching)

ledger_switching = {
    "@type": "urpx:Ledger", "@id": "cpau:e14-ledger-switching-surcharge",
    "urpx:name": "Switching surcharge",
    "urpx:ledgerType": {"@id": "urpx:profileMetricLedger"},
}
ledgers.append(ledger_switching)

pd_switching = {
    "@type": "urpx:PriceDefinition", "@id": "cpau:e14-pd-switching-surcharge",
    "urpx:name": "Switching surcharge (per separately-switched circuit < 10 kW)",
    "urpx:description": (
        "Per Section D.2: CPAU performs switching at no charge provided "
        "there are at least 10 kW of lamp load on each separately-switched "
        "circuit. For circuits below that threshold (or where the switching "
        "is not made for CPAU's convenience), an extra $2.50/month is "
        "charged per circuit."
    ),
    "urpx:chargeType": {"@id": "urpx:serviceNonMetered"},
    "urpx:chargeCategory": {"@id": "urpx:serviceCharge"},
    "urpx:billPortion": {"@id": "urpx:bundledPortion"},
    "urpx:baseQuantity": "1",
    "urpx:hasCalculationMethod": {
        "@type": "urpx:CalculationMethod",
        "@id": "cpau:e14-pd-switching-surcharge-cm",
        "urpx:intervalDuration": "P1M",
    },
    "urpx:referencesLedger": {"@id": "cpau:e14-ledger-switching-surcharge"},
    "urpx:referencesMetricInput": {"@id": "cpau:e14-mi-switching-circuit-count"},
}
price_definitions.append(pd_switching)

price_switching = {
    "@type": "urpx:Price",
    "@id": "cpau:e14-price-switching-surcharge",
    "urpx:name": "Switching surcharge",
    "urpx:referencesPriceDefinition": {"@id": "cpau:e14-pd-switching-surcharge"},
    "urpx:startDate": "2025-07-01",
    "urpx:unitPrice": "2.50",
}
prices.append(price_switching)

# ============================================================================
# Assembly
# ============================================================================
billing_model = {
    "@type": "urpx:BillingModel", "@id": "cpau:e14-billing-model",
    "urpx:hasLedger": ledgers,
    "urpx:hasPriceDefinition": price_definitions,
}

plan_elements = {
    "@type": "urpx:PlanElements", "@id": "cpau:e14-plan-elements",
    "urpx:hasMetricInput": metric_inputs,
    "urpx:hasBillingModel": billing_model,
}

prices_block = {
    "@type": "urpx:Prices", "@id": "cpau:e14-prices",
    "urpx:hasPriceSet": [{
        "@type": "urpx:PriceSet", "@id": "cpau:e14-price-set",
        "urpx:hasPrice": prices,
    }],
}

data_source_reference = {
    "@type": "urpx:DataSourceReference", "@id": "cpau:e14-dsr",
    "urpx:name": "CPAU Schedule E-14 (effective 2025-07-01)",
    "urpx:fileName": "e-14-effective-2025-07-01.pdf",
    "urpx:url": "https://www.paloalto.gov/files/assets/public/v/4/utilities/rates-schedules-for-utilities/city-facility-utility-rates/e-14-effective-2025-07-01.pdf",
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
    "@type": "urpx:RatePlanVersion", "@id": "cpau:e-14-2025-07-01",
    "urpx:version": "1.0",
    "urpx:effectiveDateTime": "2025-07-01T00:00:00",
    "urpx:description": (
        "CPAU Schedule E-14 (Street Lights), effective 2025-07-01. Flat "
        "per-fixture-per-month rates for street and highway lighting "
        "installations (and related traffic signals) owned by governmental "
        "agencies other than the City of Palo Alto. CPAU supplies "
        "electricity, performs switching, and maintains lamps and glassware. "
        "Each lamp rating, traffic-signal type and speed-sign type on the "
        "published rate sheet has its own PriceDefinition, as does the "
        "switching surcharge, and each carries its own MetricInput counting "
        "the fixtures of that type. Section D.5 interim-rate provision (for lamps "
        "not on the schedule) is documented in prose only — not modeled. "
        "Section D.3 annual burning schedule (4100 hours/year operational "
        "rule) is also prose-only."
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
    "@type": "urpx:RatePlan", "@id": "cpau:e-14",
    "urpx:name": "Street Lights",
    "urpx:ratePlanUniqueIdentifier": "CPAU-E-14",
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
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(price_definitions)} PDs)")


if __name__ == "__main__":
    main()
