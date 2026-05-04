#!/usr/bin/env python3
"""Generate the SCE DA-CRS and CCA-CRS RatePlanModifier filings (URPXT-cah.9).

Both schedules share an identical structure (4 components: WFC/CTC/FRC/PCIA)
and identical Domestic-class values per PCIA vintage. The two filings differ
only in modifier identity and eligibility-program label.

Output:
  ca/iou/sce/da-crs/versions/2026-03-20/rate-plan-modifier_sce_da-crs_2026-03-20.jsonld
  ca/iou/sce/cca-crs/versions/2026-03-20/rate-plan-modifier_sce_cca-crs_2026-03-20.jsonld

Source values: ELECTRIC_SCHEDULES_DA-CRS.pdf and ELECTRIC_SCHEDULES_CCA-CRS.pdf
in the live SCE tariff-book Other Rates folder, AL 5725-E equivalents
effective 2026-01-01. PDFs staged at scripts/sce-live-tariff-book-2026-05-04/
other-rates/. PCIA vintage values are identical between the two schedules.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

# Per-vintage PCIA values for Domestic customer class. From DA-CRS Sheets 4-9
# (identical values appear on CCA-CRS Sheets 4-9).
PCIA_VINTAGES: list[tuple[str, str]] = [
    ("2001", "0.00009"),
    ("2004", "0.00009"),
    ("2009", "0.01742"),
    ("2010", "0.02077"),
    ("2011", "0.02508"),
    ("2012", "0.02563"),
    ("2013", "0.02608"),
    ("2014", "0.02443"),
    ("2015", "0.02367"),
    ("2016", "0.02321"),
    ("2017", "0.02322"),
    ("2018", "0.02311"),
    ("2019", "0.02141"),
    ("2020", "0.02015"),
    ("2021", "0.02007"),
    ("2022", "0.02419"),
    ("2023", "0.02624"),
    ("2024", "0.01175"),
    ("2025", "-0.00644"),
    ("2026", "-0.00644"),
]

# Fixed-value Domestic-class components from DA-CRS / CCA-CRS Sheet 3.
WFC_VALUE = "0.00591"
CTC_VALUE = "0.00014"
FRC_VALUE = "0.00619"

CONTEXT = {
    "urpx": "https://urpx-org.github.io/urpx/ontology/",
    "schema": "http://schema.org/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "org": "https://example.com/organizations/",
    "sce": "https://example.com/sce/",
    "urpx:unitPrice": {"@type": "xsd:decimal"},
    "urpx:effectiveDate": {"@type": "xsd:date"},
    "urpx:effectiveDateTime": {"@type": "xsd:dateTime"},
    "urpx:initialEffectiveDate": {"@type": "xsd:date"},
    "urpx:startDate": {"@type": "xsd:date"},
    "urpx:url": {"@type": "xsd:anyURI"},
    "urpx:pageStart": {"@type": "xsd:integer"},
    "urpx:pageEnd": {"@type": "xsd:integer"},
    "urpx:accessURL": {"@type": "xsd:anyURI"},
    "urpx:dateRetrieved": {"@type": "xsd:date"},
    "urpx:targetURPXVersion": {"@type": "xsd:anyURI"},
}

# Both DA-CRS and CCA-CRS apply to the same set of SCE residential
# RatePlans currently modeled in this corpus.
APPLICABLE_BASES = [
    "sce:d",
    "sce:tou-d-4-9pm",
    "sce:tou-d-5-8pm",
    "sce:tou-d-prime",
]

# All SCE residential filing PDFs in the live tariff book carry these
# attribution stamps for the AL 5725-E rate effective date (Jan 1, 2026).
EFFECTIVE_DATE = "2026-03-20"   # filing date = most-recent per-sheet in source PDF
PRICE_START_DATE = "2026-01-01" # when actual values became effective per AL 5725-E


def make_modifier(*, slug: str, slug_uppercase: str,
                  esp_eligibility_value: str,
                  vintage_property: str,
                  source_filename: str,
                  source_sha256: str,
                  source_url: str,
                  newest_leaf: str,
                  description: str) -> dict[str, Any]:
    """Build the URPXDocument-wrapped RatePlanModifier for one CRS schedule."""
    base_iri = f"sce:{slug}"
    version_iri = f"{base_iri}-{EFFECTIVE_DATE}"

    # PriceDefinitions — each on its own Ledger so marginal-unit-rate sums
    # all 4 components independently (per urpx.price/marginal-unit-rate
    # semantics: ONE tier-price per ledger contributes; multi-component
    # ledgers would only count the first).
    pd_wfc = {
        "@type": "urpx:PriceDefinition",
        "@id": f"{base_iri}-pd-wfc",
        "urpx:name": "Wildfire Fund Non-Bypassable Charge (WFC)",
        "urpx:chargeType": {"@id": "urpx:environmentalFunding"},
        "urpx:chargeCategory": {"@id": "urpx:environmental"},
        "urpx:billPortion": {"@id": "urpx:deliveryPortion"},
        "urpx:referencesLedger": {"@id": f"{base_iri}-ledger-wfc"},
    }
    pd_ctc = {
        "@type": "urpx:PriceDefinition",
        "@id": f"{base_iri}-pd-ctc",
        "urpx:name": "Competition Transition Charge (CTC)",
        "urpx:chargeType": {"@id": "urpx:adjustmentPowerCost"},
        "urpx:chargeCategory": {"@id": "urpx:adjustment"},
        "urpx:billPortion": {"@id": "urpx:deliveryPortion"},
        "urpx:referencesLedger": {"@id": f"{base_iri}-ledger-ctc"},
    }
    pd_frc = {
        "@type": "urpx:PriceDefinition",
        "@id": f"{base_iri}-pd-frc",
        "urpx:name": "Fixed Recovery Charge (FRC)",
        "urpx:chargeType": {"@id": "urpx:recoverySurcharge"},
        "urpx:chargeCategory": {"@id": "urpx:adjustment"},
        "urpx:billPortion": {"@id": "urpx:bundledPortion"},
        "urpx:referencesLedger": {"@id": f"{base_iri}-ledger-frc"},
    }
    pd_pcia = {
        "@type": "urpx:PriceDefinition",
        "@id": f"{base_iri}-pd-pcia",
        "urpx:name": "Power Charge Indifference Adjustment (PCIA) — vintage-discriminated by customer's enrollment year",
        "urpx:chargeType": {"@id": "urpx:adjustmentPowerCost"},
        "urpx:chargeCategory": {"@id": "urpx:adjustment"},
        "urpx:billPortion": {"@id": "urpx:supplyPortion"},
        "urpx:referencesLedger": {"@id": f"{base_iri}-ledger-pcia"},
    }

    # Fixed-value Prices
    fixed_prices = [
        {
            "@type": "urpx:Price",
            "@id": f"{base_iri}-price-wfc-{EFFECTIVE_DATE}",
            "urpx:referencesPriceDefinition": {"@id": f"{base_iri}-pd-wfc"},
            "urpx:startDate": PRICE_START_DATE,
            "urpx:name": "Wildfire Fund Non-Bypassable Charge",
            "urpx:unitPrice": WFC_VALUE,
        },
        {
            "@type": "urpx:Price",
            "@id": f"{base_iri}-price-ctc-{EFFECTIVE_DATE}",
            "urpx:referencesPriceDefinition": {"@id": f"{base_iri}-pd-ctc"},
            "urpx:startDate": PRICE_START_DATE,
            "urpx:name": "Competition Transition Charge",
            "urpx:unitPrice": CTC_VALUE,
        },
        {
            "@type": "urpx:Price",
            "@id": f"{base_iri}-price-frc-{EFFECTIVE_DATE}",
            "urpx:referencesPriceDefinition": {"@id": f"{base_iri}-pd-frc"},
            "urpx:startDate": PRICE_START_DATE,
            "urpx:name": "Fixed Recovery Charge",
            "urpx:unitPrice": FRC_VALUE,
        },
    ]

    # Per-vintage PCIA Prices, each with hasApplicabilityRule gating on the
    # customer's vintage year via CustomOperandNode.
    vintage_prices = []
    for year, value in PCIA_VINTAGES:
        vintage_prices.append({
            "@type": "urpx:Price",
            "@id": f"{base_iri}-price-pcia-v{year}-{EFFECTIVE_DATE}",
            "urpx:referencesPriceDefinition": {"@id": f"{base_iri}-pd-pcia"},
            "urpx:startDate": PRICE_START_DATE,
            "urpx:name": f"PCIA — {year} Vintage",
            "urpx:unitPrice": value,
            "urpx:hasApplicabilityRule": {
                "@type": "urpx:ApplicabilityRule",
                "@id": f"{version_iri}-ar-pcia-v{year}",
                "urpx:name": f"Applies when customer's {vintage_property} = {year}",
                "urpx:hasConditionExpression": {
                    "@type": "urpx:ConditionExpression",
                    "@id": f"{version_iri}-cx-pcia-v{year}",
                    "urpx:rootNode": {
                        "@type": "urpx:ComparisonNode",
                        "@id": f"{version_iri}-cn-pcia-v{year}",
                        "urpx:operator": {"@id": "urpx:equalsOperator"},
                        "urpx:leftOperand": {
                            "@type": "urpx:CustomOperandNode",
                            "urpx:customConditionProperty": vintage_property,
                        },
                        "urpx:rightOperand": {
                            "@type": "urpx:CustomOperandNode",
                            "urpx:stringValue": year,
                        },
                    },
                },
            },
        })

    return {
        "@context": CONTEXT,
        "@type": "urpx:URPXDocument",
        "@id": f"sce:doc-{slug}-{EFFECTIVE_DATE}",
        "urpx:targetURPXVersion": "https://github.com/urpx-org/urpx/raw/v0.2.0/ontology/urpx-ontology.ttl",
        "urpx:hasRatePlanModifier": {
            "@type": "urpx:RatePlanModifier",
            "@id": base_iri,
            "urpx:name": f"Schedule {slug_uppercase}",
            "urpx:modifierUniqueIdentifier": slug_uppercase,
            "urpx:initialEffectiveDate": "2023-07-27",
            "urpx:timezoneIdentifier": "America/Los_Angeles",
            "urpx:hasRatePlanModifierVersion": {
                "@type": "urpx:RatePlanModifierVersion",
                "@id": version_iri,
                "urpx:version": EFFECTIVE_DATE,
                "urpx:modifierVersionNumber": EFFECTIVE_DATE,
                "urpx:changeReason": {"@id": "urpx:rateCase"},
                "urpx:description": description,
                "urpx:effectiveDateTime": f"{EFFECTIVE_DATE}T00:00:00",
                "urpx:priceCurrency": "USD",
                "urpx:commodity": {"@id": "urpx:electricity"},
                "urpx:serviceRole": {"@id": "urpx:bundledServiceRole"},
                "urpx:publishedBy": {
                    "@type": "urpx:Organization",
                    "@id": "org:utility-sce",
                    "urpx:legalName": "Southern California Edison Company",
                    "urpx:organizationType": {"@id": "urpx:utilityOrganization"},
                },
                "urpx:applicableToRatePlan": [{"@id": iri} for iri in APPLICABLE_BASES],
                "urpx:hasDataSourceReference": {
                    "@type": "urpx:DataSourceReference",
                    "urpx:fileName": source_filename,
                    "urpx:mediaType": {"@id": "urpx:applicationPdf"},
                    "urpx:accessURL": source_url,
                    "urpx:dateRetrieved": "2026-05-04",
                    "urpx:dataSourceType": {"@id": "urpx:utilityWebsiteSource"},
                    "urpx:hasTariffBookReference": {
                        "@type": "urpx:TariffBookReference",
                        "urpx:pageStart": 3,
                        "urpx:pageEnd": 9,
                        "urpx:leafStart": "74861-E",
                        "urpx:leafEnd": newest_leaf,
                    },
                },
                "urpx:hasEligibilityRule": [{
                    "@type": "urpx:EligibilityRule",
                    "@id": f"{version_iri}-er-eligible",
                    "urpx:name": f"{slug_uppercase}-eligible customer",
                    "urpx:description": (
                        f"Customer is enrolled in {esp_eligibility_value} service. "
                        "The cost-responsibility surcharge under this Schedule recovers "
                        "stranded power-procurement costs allocated to customers who have "
                        "departed Bundled Service. Eligibility is by enrollment record; "
                        "PCIA value depends on the customer's vintage year (year of "
                        "departing-load enrollment) — see per-Price ApplicabilityRule "
                        "gates below."
                    ),
                    "urpx:hasConditionExpression": {
                        "@type": "urpx:ConditionExpression",
                        "@id": f"{version_iri}-cx-eligible",
                        "urpx:rootNode": {
                            "@type": "urpx:ComparisonNode",
                            "@id": f"{version_iri}-cn-eligible",
                            "urpx:operator": {"@id": "urpx:equalsOperator"},
                            "urpx:leftOperand": {
                                "@type": "urpx:CustomOperandNode",
                                "urpx:customConditionProperty": "Energy Service Type",
                            },
                            "urpx:rightOperand": {
                                "@type": "urpx:CustomOperandNode",
                                "urpx:stringValue": esp_eligibility_value,
                            },
                        },
                    },
                }],
                "urpx:hasPlanElements": {
                    "@type": "urpx:PlanElements",
                    "urpx:hasMetricInput": [{
                        "@type": "urpx:MetricInput",
                        "@id": f"{base_iri}-mi-energy",
                        "urpx:name": "kWh Energy Consumption Prices",
                        "urpx:metricInputType": {"@id": "urpx:measuredMetricInput"},
                        "urpx:hasMetricSpecification": {
                            "@type": "urpx:MetricSpecification",
                            "@id": f"{base_iri}-ms-energy",
                            "urpx:measurementKind": {"@id": "urpx:energy"},
                            "urpx:unitOfMeasure": {"@id": "urpx:kWh"},
                        },
                    }],
                    "urpx:hasBillingModel": {
                        "@type": "urpx:BillingModel",
                        "urpx:hasLedger": [
                            {
                                "@type": "urpx:Ledger",
                                "@id": f"{base_iri}-ledger-wfc",
                                "urpx:name": f"{slug_uppercase} Wildfire Fund Non-Bypassable Charge",
                                "urpx:ledgerType": {"@id": "urpx:deliveryLedger"},
                                "urpx:referencesMetricInput": {"@id": f"{base_iri}-mi-energy"},
                            },
                            {
                                "@type": "urpx:Ledger",
                                "@id": f"{base_iri}-ledger-ctc",
                                "urpx:name": f"{slug_uppercase} Competition Transition Charge",
                                "urpx:ledgerType": {"@id": "urpx:deliveryLedger"},
                                "urpx:referencesMetricInput": {"@id": f"{base_iri}-mi-energy"},
                            },
                            {
                                "@type": "urpx:Ledger",
                                "@id": f"{base_iri}-ledger-frc",
                                "urpx:name": f"{slug_uppercase} Fixed Recovery Charge",
                                "urpx:ledgerType": {"@id": "urpx:bundledLedger"},
                                "urpx:referencesMetricInput": {"@id": f"{base_iri}-mi-energy"},
                            },
                            {
                                "@type": "urpx:Ledger",
                                "@id": f"{base_iri}-ledger-pcia",
                                "urpx:name": f"{slug_uppercase} Power Charge Indifference Adjustment (vintage-conditional)",
                                "urpx:ledgerType": {"@id": "urpx:supplyLedger"},
                                "urpx:referencesMetricInput": {"@id": f"{base_iri}-mi-energy"},
                            },
                        ],
                        "urpx:hasPriceDefinition": [pd_wfc, pd_ctc, pd_frc, pd_pcia],
                    },
                },
                "urpx:hasPrices": {
                    "@type": "urpx:Prices",
                    "urpx:hasPrice": fixed_prices + vintage_prices,
                },
            },
        },
    }


DA_DESCRIPTION = (
    "Schedule DA-CRS — Direct Access Cost Responsibility Surcharge. "
    "Recovers stranded power-procurement costs allocated to residential "
    "customers who have elected Direct Access (DA) service from a third-party "
    "Energy Service Provider (ESP). Applied as an overlay to the customer's "
    "base SCE residential RatePlan (Schedule D, TOU-D-4-9PM, TOU-D-5-8PM, "
    "TOU-D-PRIME). Composed of four components for the Domestic customer "
    "class: WFC ($0.00591/kWh, Wildfire Fund Non-Bypassable Charge), "
    "CTC ($0.00014/kWh, Competition Transition Charge), FRC ($0.00619/kWh, "
    "Fixed Recovery Charge), and PCIA (Power Charge Indifference Adjustment, "
    "vintage-discriminated by customer's DA enrollment year — 20 vintages "
    "from 2001 through 2026, ranging from $-0.00644 for 2025/2026 vintages "
    "(credits, where DA customers' departing-load is below market price) to "
    "$0.02624 for 2023 vintage). Per-Price hasApplicabilityRule on each PCIA "
    "vintage gates on customer's `DA Vintage Year` CustomOperandNode property."
    " Per the Otherwise Applicable Tariff (OAT) reconciliation prose on TOU-D"
    " Sheet 18 SC 11 / Schedule D Sheet 6 SC 4, DA customer's OAT charges "
    "apply EXCEPT the DWRBC component is subtracted from total Delivery "
    "Service before billing-determinant multiplication; this OAT-side "
    "adjustment is NOT modeled here (would require itemizing DWRBC as a "
    "separate PriceDefinition in the base TOU-D / Schedule D filings). "
    "Customer-subgroup exemption table on Sheet 3 distinguishes DA, PC-TBS, "
    "GTSR-GR, GTSR-CR — only the default DA subgroup is captured by the "
    "Eligibility Rule here. Sibling Schedule CCA-CRS (modeled at "
    "ca/iou/sce/cca-crs/) carries identical Domestic-class PCIA values "
    "for CCA-Service customers."
)

CCA_DESCRIPTION = (
    "Schedule CCA-CRS — CCA Cost Responsibility Surcharge. "
    "Recovers stranded power-procurement costs allocated to residential "
    "customers served by a Community Choice Aggregator (CCA) instead of "
    "Bundled SCE service. Applied as an overlay to the customer's base SCE "
    "residential RatePlan (Schedule D, TOU-D-4-9PM, TOU-D-5-8PM, "
    "TOU-D-PRIME). Composed of four components for the Domestic customer "
    "class: WFC ($0.00591/kWh), CTC ($0.00014/kWh), FRC ($0.00619/kWh), "
    "and PCIA (vintage-discriminated, identical PCIA values to Schedule "
    "DA-CRS — 20 vintages from 2001 through 2026, ranging from $-0.00644 "
    "for 2025/2026 to $0.02624 for 2023). Per-Price hasApplicabilityRule "
    "on each PCIA vintage gates on customer's `CCA Vintage Year` "
    "CustomOperandNode property. Per the OAT reconciliation prose on TOU-D"
    " Sheet 18 SC 11 / Schedule D Sheet 6 SC 4, CCA customer's OAT charges "
    "apply EXCEPT the DWRBC component is subtracted from total Delivery "
    "Service; this OAT-side adjustment is NOT modeled here. CCA-CRS Sheet 3"
    " has a richer customer-subgroup exemption table than DA-CRS — CCA "
    "customers on Medical Baseline are WFC-exempt; CCA customers on CARE "
    "are WFC-exempt + FRC-exempt; CCA customers on FERA are FRC-exempt; "
    "Continuous DA/CCA customers are WFC + PCIA-exempt; Returning "
    "Continuous DA customers are WFC-exempt. Only the default CCA "
    "Customers subgroup is captured by the Eligibility Rule here; the "
    "subgroup exemptions are stacking interactions with already-modeled "
    "CARE / FERA modifiers and are deferred to a follow-up issue."
)


def main() -> None:
    repo = pathlib.Path(__file__).resolve().parent.parent
    base_url = ("https://edisonintl.sharepoint.com/teams/Public/TM2/Shared%20"
                "Documents/Public/Regulatory/Tariff-SCE%20Tariff%20Books/"
                "Electric/Schedules/Other%20Rates")

    da = make_modifier(
        slug="da-crs",
        slug_uppercase="DA-CRS",
        esp_eligibility_value="Direct Access",
        vintage_property="DA Vintage Year",
        source_filename="ELECTRIC_SCHEDULES_DA-CRS.pdf",
        source_sha256="946bdef1b697bff7d7e0b37f550b7ee14c7a2cb0fb3528668fcd7d4f758f398e",
        source_url=f"{base_url}/ELECTRIC_SCHEDULES_DA-CRS.pdf",
        newest_leaf="90853-E",
        description=DA_DESCRIPTION,
    )
    cca = make_modifier(
        slug="cca-crs",
        slug_uppercase="CCA-CRS",
        esp_eligibility_value="Community Choice Aggregation",
        vintage_property="CCA Vintage Year",
        source_filename="ELECTRIC_SCHEDULES_CCA-CRS.pdf",
        source_sha256="b0b32770715fabab09ca94a8595ace3bde4e948b11085d6c602a066cc5201728",
        source_url=f"{base_url}/ELECTRIC_SCHEDULES_CCA-CRS.pdf",
        newest_leaf="90840-E",
        description=CCA_DESCRIPTION,
    )

    da_path = repo / "ca/iou/sce/da-crs/versions/2026-03-20/rate-plan-modifier_sce_da-crs_2026-03-20.jsonld"
    cca_path = repo / "ca/iou/sce/cca-crs/versions/2026-03-20/rate-plan-modifier_sce_cca-crs_2026-03-20.jsonld"
    da_path.write_text(json.dumps(da, indent=2, ensure_ascii=False) + "\n")
    cca_path.write_text(json.dumps(cca, indent=2, ensure_ascii=False) + "\n")

    print(f"Wrote {da_path.relative_to(repo)} ({da_path.stat().st_size} bytes)")
    print(f"Wrote {cca_path.relative_to(repo)} ({cca_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
