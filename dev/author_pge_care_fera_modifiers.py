#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""One-off: write the pge:d-care (2026-03-01) and pge:e-fera (2026-06-01)
RatePlanModifier filings. Takes the repository root. Each CoverageClaim
Evaluation it writes lists no deferrals; dev/resync_coverage_evaluations.py then
filled them from each filing's tariff.toml."""
import json
import sys
from pathlib import Path

REPO = Path(sys.argv[1])

BASES = [  # plan, current version local part
    ("e-1", "e-1-2026-03-01"),
    ("e-elec", "e-elec-2026-03-27"),
    ("e-tou-c", "e-tou-c-2026-03-27"),
    ("e-tou-d", "e-tou-d-2026-03-27"),
    ("ev2", "ev2-2026-03-27"),
]

CONTEXT = {
    "urpx": "https://urpx.org/ns/ontology/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "org": "https://rate-plans.grid-coordination.energy/organizations/",
    "pge": "https://rate-plans.grid-coordination.energy/pge/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "urpx:unitPrice": {"@type": "xsd:decimal"},
    "urpx:multiplier": {"@type": "xsd:decimal"},
    "urpx:effectiveDateTime": {"@type": "xsd:dateTime"},
    "urpx:startDate": {"@type": "xsd:date"},
    "urpx:initialEffectiveDate": {"@type": "xsd:date"},
    "urpx:pageStart": {"@type": "xsd:integer"},
    "urpx:pageEnd": {"@type": "xsd:integer"},
    "urpx:accessURL": {"@type": "xsd:anyURI"},
    "urpx:dateRetrieved": {"@type": "xsd:date"},
    "urpx:targetURPXVersion": {"@type": "xsd:anyURI"},
    "urpx:evaluatedOn": {"@type": "xsd:dateTime"},
}

OFFERED_BY = {
    "@type": "urpx:UtilityOperator",
    "@id": "org:utility-pge",
    "urpx:legalName": "Pacific Gas and Electric Company",
    "urpx:organizationType": {"@id": "urpx:utilityOrganization"},
    "urpx:hasIdentity": {
        "@id": "org:utility-pge-identity",
        "@type": "urpx:OrganizationIdentity",
        "urpx:hasName": {
            "@id": "org:utility-pge-name",
            "@type": "urpx:OrganizationName",
            "urpx:name": "Pacific Gas and Electric Company",
        },
        "urpx:hasIdentifier": {
            "@id": "org:utility-pge-eia",
            "@type": "urpx:OrganizationIdentifier",
            "urpx:scheme": {"@id": "urpx:eiaScheme"},
            "skos:notation": "14328",
        },
    },
}

EXEMPTIONS = {
    # key: (base Price descriptor, display name, base-charge description)
    "wildfire-fund": ("price-wildfire-fund", "Wildfire Fund Charge"),
    "wildfire-hardening": ("price-wildfire-hardening", "Wildfire Hardening Charge"),
    "recovery-bond": ("price-recovery-bond", "Recovery Bond Charge"),
    "recovery-bond-credit": ("price-recovery-bond-credit", "Recovery Bond Credit"),
}


def build(slug, date, ident, name, program_iri, program_label, rate, exemptions,
          dsr, description, sheet_cite, eligibility_desc):
    v = f"pge:{slug}-{date}"
    mi = f"{v}-mi-energy"
    ledgers, pds, prices = [], [], []

    def add(key, pd_name, price_name, charge_type, portion, mult, based_on):
        led = f"{v}-ledger-{key}"
        pd = f"{v}-pd-{key}"
        ledgers.append({
            "@type": "urpx:Ledger", "@id": led, "urpx:name": pd_name,
            "urpx:ledgerType": {"@id": "urpx:bundledLedger"},
            "urpx:referencesMetricInput": {"@id": mi},
        })
        pds.append({
            "@type": "urpx:PriceDefinition", "@id": pd, "urpx:name": pd_name,
            "urpx:chargeType": {"@id": charge_type},
            "urpx:chargeCategory": {"@id": "urpx:discount"},
            "urpx:billPortion": {"@id": portion},
            "urpx:referencesLedger": {"@id": led},
        })
        prices.append({
            "@type": "urpx:Price", "@id": f"{v}-price-{key}",
            "urpx:name": price_name,
            "urpx:referencesPriceDefinition": {"@id": pd},
            "urpx:multiplier": mult,
            "urpx:basedOnPrice": [{"@id": b} for b in based_on],
            "urpx:startDate": date,
        })

    for key in exemptions:
        desc, label = EXEMPTIONS[key]
        add(f"{key}-exemption",
            f"{program_label} {label} exemption",
            f"{program_label} {label} exemption: the negative of the {label} Price "
            f"of whichever base plan this is composed with",
            "urpx:creditEnergy", "urpx:bundledPortion", "-1",
            [f"pge:{ver}-{desc}" for _, ver in BASES])
    pct = str(int(round(-float(rate) * 100)))
    add("bill-discount",
        f"{program_label} {pct} percent discount on the discountable volumetric subtotal",
        f"{program_label} {pct} percent discount on the base plan's "
        f"{program_label}-discountable volumetric subtotal, per {sheet_cite}",
        "urpx:creditMisc", "urpx:deliveryPortion", rate,
        [f"pge:{ver}-summary-{program_label.lower()}-discountable" for _, ver in BASES])

    version = {
        "@type": "urpx:RatePlanModifierVersion",
        "@id": v,
        "urpx:version": date,
        "urpx:modifierVersionNumber": date,
        "urpx:changeReason": {"@id": "urpx:rateCase"},
        "urpx:description": description,
        "urpx:effectiveDateTime": f"{date}T00:00:00",
        "urpx:priceCurrency": "USD",
        "urpx:commodity": {"@id": "urpx:electricity"},
        "urpx:serviceRole": {"@id": "urpx:bundledServiceRole"},
        "urpx:applicableToRatePlan": [{"@id": f"pge:{p}"} for p, _ in BASES],
        "urpx:hasDataSourceReference": dsr,
        "urpx:hasEligibilityRule": [{
            "@type": "urpx:EligibilityRule",
            "@id": f"{v}-er-eligible",
            "urpx:name": f"{program_label}-enrolled residential customer",
            "urpx:description": eligibility_desc,
            "urpx:hasConditionExpression": {
                "@type": "urpx:ConditionExpression",
                "@id": f"{v}-cx-eligible",
                "urpx:rootNode": {
                    "@type": "urpx:BooleanOperationNode",
                    "@id": f"{v}-bn-residential-and-enrolled",
                    "urpx:operator": {"@id": "urpx:andOperator"},
                    "urpx:operandNodes": [
                        {
                            "@type": "urpx:ComparisonNode",
                            "@id": f"{v}-cn-residential",
                            "urpx:operator": {"@id": "urpx:equalsOperator"},
                            "urpx:leftOperand": {
                                "@type": "urpx:ObjectOperandNode",
                                "@id": f"{v}-cn-residential-left-operand",
                                "urpx:conditionProperty": {"@id": "urpx:hasCustomerKind"},
                            },
                            "urpx:rightOperand": {
                                "@type": "urpx:ObjectOperandNode",
                                "@id": f"{v}-cn-residential-right-operand",
                                "urpx:referencesValue": {"@id": "urpx:residentialKind"},
                            },
                        },
                        {
                            "@type": "urpx:ComparisonNode",
                            "@id": f"{v}-cn-program-enrollment",
                            "urpx:operator": {"@id": "urpx:equalsOperator"},
                            "urpx:leftOperand": {
                                "@type": "urpx:ObjectOperandNode",
                                "@id": f"{v}-cn-program-enrollment-left-operand",
                                "urpx:conditionProperty": {"@id": "urpx:hasProgramEnrollment"},
                            },
                            "urpx:rightOperand": {
                                "@type": "urpx:ObjectOperandNode",
                                "@id": f"{v}-cn-program-enrollment-right-operand",
                                "urpx:referencesValue": {"@id": program_iri},
                            },
                        },
                    ],
                },
            },
        }],
        "urpx:hasPlanElements": {
            "@type": "urpx:PlanElements",
            "@id": f"{v}-plan-elements",
            "urpx:hasMetricInput": [{
                "@type": "urpx:MetricInput",
                "@id": mi,
                "urpx:name": "kWh Energy Consumption",
                "urpx:metricInputType": {"@id": "urpx:measuredMetricInput"},
                "urpx:hasMetricSpecification": {
                    "@type": "urpx:MetricSpecification",
                    "@id": f"{v}-ms-energy",
                    "urpx:measurementKind": {"@id": "urpx:energy"},
                    "urpx:unitOfMeasure": {"@id": "urpx:kWh"},
                },
            }],
            "urpx:hasBillingModel": {
                "@type": "urpx:BillingModel",
                "@id": f"{v}-plan-elements-billing-model",
                "urpx:hasLedger": ledgers,
                "urpx:hasPriceDefinition": pds,
            },
        },
        "urpx:hasPrices": {
            "@type": "urpx:Prices",
            "@id": f"{v}-prices",
            "urpx:hasPrice": prices,
        },
        "urpx:offeredBy": OFFERED_BY,
        "urpx:forRatePlanModifier": {"@id": f"pge:{slug}"},
        "urpx:hasCoverageClaim": {
            "@id": f"pge:cc-{slug}-{date}",
            "@type": "urpx:CoverageClaim",
            "urpx:completenessResult": {"@id": "urpx:partial"},
            "urpx:selfContained": True,
            "urpx:explainedBy": {
                "@type": "urpx:Evaluation",
                "@id": f"pge:cc-{slug}-{date}-evaluation",
                "urpx:evaluationKind": {"@id": "urpx:coverageEvaluation"},
                "urpx:description": (
                    "This filing does not carry everything its source document "
                    "states. 0 parts are deferred, listed here in the same words as "
                    "the filing's tariff.toml [modeling].deferrals so the two records "
                    "cannot drift."),
                "urpx:evaluatedOn": "2026-10-05T00:00:00",
            },
        },
    }
    doc = {
        "@context": CONTEXT,
        "@type": "urpx:URPXPackage",
        "@id": f"pge:doc-{slug}-{date}",
        "urpx:targetURPXVersion": "https://github.com/urpx-org/urpx/raw/v0.5.1/ontology/urpx-ontology.ttl",
        "urpx:hasRatePlanModifier": {
            "@type": "urpx:RatePlanModifier",
            "@id": f"pge:{slug}",
            "urpx:name": name,
            "urpx:modifierUniqueIdentifier": ident,
            "urpx:initialEffectiveDate": date,
            "urpx:timezoneIdentifier": "America/Los_Angeles",
            "urpx:hasRatePlanModifierVersion": version,
        },
    }
    out = REPO / f"us/ca/pge/electricity/{slug}/versions/{date}/rate-plan-modifier_pge_{slug}_{date}.jsonld"
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", out.relative_to(REPO))


build(
    "d-care", "2026-03-01", "D-CARE",
    "Schedule D-CARE Line-Item Discount for California Alternate Rates for Energy (CARE) Customers",
    "pge:program-care", "CARE", "-0.35",
    ["wildfire-fund", "wildfire-hardening", "recovery-bond", "recovery-bond-credit"],
    {
        "@type": "urpx:DataSourceReference",
        "urpx:fileName": "ELEC_SCHEDS_D-CARE.pdf",
        "urpx:mediaType": {"@id": "urpx:applicationPdf"},
        "urpx:accessURL": "https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_SCHEDS_D-CARE.pdf",
        "urpx:dateRetrieved": "2026-09-23",
        "urpx:dataSourceType": {"@id": "urpx:utilityWebsiteSource"},
        "urpx:pageStart": 1,
        "urpx:pageEnd": 2,
        "urpx:leafStart": "61093-E",
        "urpx:leafEnd": "59087-E",
    },
    "Line-item CARE discount applied to PG&E residential base plans E-1, E-TOU-C, "
    "E-TOU-D, EV2 and E-ELEC. Sheet 1: a CARE customer receives a percentage discount "
    "\"on their total bundled volumetric charges less charges from which they are "
    "exempt (Wildfire Fund Charge, Wildfire Hardening Charge, Recovery Bond Charge, "
    "Recovery Bond Credit, and the CARE surcharge portion of the public purpose "
    "program charge used to fund the CARE discount) on their otherwise applicable "
    "rate schedule (except for the California Climate Credit, which will not be "
    "discounted)\"; Sheet 2 sets the D-CARE Discount at 35.000 percent. The exemptions "
    "are carried as urpx:multiplier -1 over the composed base's own charge, "
    "and the discount as urpx:multiplier -0.35 over the base's "
    "CARE-discountable urpx:PriceSummary; each names its candidates in every base plan "
    "it applies to, read as alternatives. The base services charge is not discounted: Sheet 1 "
    "assigns a CARE customer to Income Tier 1, which each base prices as a "
    "urpx:ProfileAlternative.",
    "Schedule D-CARE Sheet 2",
    "Residential customer enrolled in CARE. Sheet 1 APPLICABILITY qualifies the "
    "applicant \"for California Alternate Rates for Energy (CARE) under the "
    "eligibility and certification criteria set forth in Electric Rule 19.1\"; "
    "Special Condition 2 limits it to the primary residence and states that "
    "\"Customers or sub-metered tenants participating in the Family Electric Rate "
    "Assistance (FERA) program cannot concurrently participate in the CARE program.\"",
)

build(
    "e-fera", "2026-06-01", "E-FERA",
    "Schedule E-FERA Family Electric Rate Assistance",
    "pge:program-fera", "FERA", "-0.18",
    ["wildfire-hardening", "recovery-bond", "recovery-bond-credit"],
    {
        "@type": "urpx:DataSourceReference",
        "urpx:fileName": "ELEC_SCHEDS_E-FERA.pdf",
        "urpx:mediaType": {"@id": "urpx:applicationPdf"},
        "urpx:accessURL": "https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_SCHEDS_E-FERA.pdf",
        "urpx:dateRetrieved": "2026-09-23",
        "urpx:dataSourceType": {"@id": "urpx:utilityWebsiteSource"},
        "urpx:pageStart": 1,
        "urpx:pageEnd": 3,
        "urpx:leafStart": "61123-E",
        "urpx:leafEnd": "55923-E",
    },
    "FERA discount applied to PG&E residential base plans E-1, E-TOU-C, E-TOU-D, EV2 "
    "and E-ELEC. Sheet 1: \"Customers taking service on this rate schedule will receive "
    "an 18 percent discount on their total bundled volumetric charges on their "
    "otherwise applicable rate schedule\", and \"Discounts will be applied as a "
    "residual reduction to distribution charges, after FERA customers are exempted "
    "from the Wildfire Hardening Charge, Recovery Bond Charge, and the Recovery Bond "
    "Credit.\" Those exemptions are carried as urpx:multiplier -1 over the "
    "composed base's own charge, and the discount as urpx:multiplier "
    "-0.18 over the base's FERA-discountable urpx:PriceSummary, which includes the "
    "generation charges; each names its candidates in every base plan it applies to, read as "
    "alternatives. The base services charge is not discounted: Sheet 1 assigns a FERA "
    "customer to Income Tier 2, which each base prices as a urpx:ProfileAlternative.",
    "Schedule E-FERA Sheet 1",
    "Residential customer enrolled in FERA. Sheet 1 APPLICABILITY requires \"a total "
    "gross annual household income of between 200%+$1, be below 250% of federal "
    "poverty guidelines, and have three or more persons residing full time in their "
    "household\"; Special Condition 2 limits it to the primary residence and states "
    "that \"Customers or sub-metered tenants participating in the California "
    "Alternate Rates for Energy (CARE) program cannot concurrently participate in the "
    "FERA program.\"",
)
