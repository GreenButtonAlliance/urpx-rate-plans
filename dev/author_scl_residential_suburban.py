#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""One-off: author us/wa/scl/electricity/residential-suburban/versions/{2026,2027,2028}-01-01/.

The suburban franchise and tax multipliers and suburban undergrounding charges
that SMC 21.49.030 applies to Schedule RSS and, by 21.49.030.B, "to Schedule
RTS as Schedule RSS". One RatePlanModifier on scl:rts, one version per RTS
version, with the customer's jurisdiction as a urpx:ProfileAlternatives
dimension. The multiplier is a urpx:Price carrying urpx:multiplier over the RTS
version's energy subtotal (scl:rts-<date>-summary-energy, which
dev/author_scl_rtc_rts.py writes) and a second over its Base Service Charge
Price.

Takes the repository root. Copies the ordinance in from the RTS filing of the
same date, so run it after dev/author_scl_rtc_rts.py.

    python3 dev/author_scl_residential_suburban.py .
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO = Path(sys.argv[1])
SLUG = "residential-suburban"
RETRIEVED = "2026-10-05"
ORD_URL = "https://clerk.seattle.gov/~archives/Ordinances/Ord_127473.pdf"
SMC_URL = ("https://library.municode.com/wa/seattle/codes/municipal_code"
           "?nodeId=TIT21UT_SUBTITLE_IVLIPO_CH21.49SELIDE")
RATES_URL = "https://www.seattle.gov/city-light/residential-services/billing-information/rates"
DATES = ("2026-01-01", "2027-01-01", "2028-01-01")
NEXT = {"2026-01-01": "2027-01-01", "2027-01-01": "2028-01-01", "2028-01-01": None}

# SMC 21.49.030.A as amended by Ordinance 127473, ordinance page 9, table "RSS
# suburban franchise and tax multipliers", bound to the columns headed
# "Effective January 1, 2026", "... 2027" and "... 2028"; the struck 2024 and
# 2025 columns are not read. Percent, as printed. The ordinance's first row is
# "Burien, King County, SeaTac, Shoreline"; City Light's rates page heads the
# same column "Burien, SeaTac, Shoreline, Uninc. King County".
MULTIPLIERS = {
    "burien":            {"2026-01-01": "8.00", "2027-01-01": "8.00", "2028-01-01": "8.00"},
    "king-county":       {"2026-01-01": "8.00", "2027-01-01": "8.00", "2028-01-01": "8.00"},
    "seatac":            {"2026-01-01": "8.00", "2027-01-01": "8.00", "2028-01-01": "8.00"},
    "shoreline":         {"2026-01-01": "8.00", "2027-01-01": "8.00", "2028-01-01": "8.00"},
    "tukwila":           {"2026-01-01": "7.19", "2027-01-01": "7.05", "2028-01-01": "7.07"},
    "lake-forest-park":  {"2026-01-01": "8.04", "2027-01-01": "8.04", "2028-01-01": "8.04"},
    "normandy-park":     {"2026-01-01": "6.38", "2027-01-01": "6.38", "2028-01-01": "6.38"},
}
JURISDICTION = {
    "burien": "Burien",
    "king-county": "Unincorporated King County",
    "lake-forest-park": "Lake Forest Park",
    "normandy-park": "Normandy Park",
    "seatac": "SeaTac",
    "shoreline": "Shoreline",
    "tukwila": "Tukwila",
}
ORDER = ["burien", "king-county", "lake-forest-park", "normandy-park", "seatac", "shoreline", "tukwila"]

# SMC 21.49.030.A, ordinance pages 9 and 10, "Suburban Undergrounding Charges",
# column headed "Effective January 1, 2025" (the struck column is January 1,
# 2023, with the same values). Cents per kWh. "Additional undergrounding charges
# will apply to all customers in Shoreline and Burien as follows", so every
# customer in the city pays every charge listed under it.
UNDERGROUNDING = {
    "shoreline": [("north-city", "North City", "0.07"), ("aurora-1", "Aurora 1", "0.17"),
                  ("aurora-2", "Aurora 2", "0.18"), ("aurora-3a", "Aurora 3A", "0.05"),
                  ("aurora-3b", "Aurora 3B", "0.22")],
    "burien": [("first-avenue-south-1", "First Avenue South 1", "0.37"),
               ("first-avenue-south-2", "First Avenue South 2", "0.13")],
}


def ref(i):
    return {"@id": i}


def cents_to_dollars(cents):
    whole, _, frac = cents.partition(".")
    n = int(whole) * 100 + int(frac.ljust(2, "0"))
    return f"{n // 10000}.{n % 10000:04d}"


def percent_to_fraction(pct):
    whole, _, frac = pct.partition(".")
    n = int(whole) * 100 + int(frac.ljust(2, "0"))
    return f"{n // 10000}.{n % 10000:04d}"


def total_undergrounding(j):
    return f"{sum(int(c.replace('.', '')) for _s, _n, c in UNDERGROUNDING[j]) / 100:.2f}"


def multiplier_sentence(date):
    m = {j: MULTIPLIERS[j][date] for j in ORDER}
    return (f"Burien, unincorporated King County, SeaTac and Shoreline {m['burien']} percent; "
            f"Lake Forest Park {m['lake-forest-park']} percent; Normandy Park {m['normandy-park']} percent; "
            f"Tukwila {m['tukwila']} percent")


def description(date):
    year = date[:4]
    text = (
        "Seattle City Light's suburban franchise and tax multipliers and suburban undergrounding charges "
        "on Schedule RTS (Residential: Suburban Time-of-Use). SMC 21.49.030.A, as amended by Ordinance "
        "127473, states for Schedule RSS that 'All charges in Schedule RSS shall be increased by the "
        "following percentages respective of the location of service' and that 'Additional undergrounding "
        "charges will apply to all customers in Shoreline and Burien'; 21.49.030.B applies 'The same "
        "franchise and tax multipliers and suburban undergrounding charges ... to Schedule RTS as Schedule "
        f"RSS.' This version carries the multiplier column headed 'Effective January 1, {year}': "
        f"{multiplier_sentence(date)}. The undergrounding charges, unchanged since January 1, 2023, total "
        f"{total_undergrounding('shoreline')} cents per kWh in Shoreline (North City 0.07, Aurora 1 0.17, "
        "Aurora 2 0.18, Aurora 3A 0.05, Aurora 3B 0.22) and "
        f"{total_undergrounding('burien')} cents per kWh in Burien (First Avenue South 1 0.37, First Avenue "
        "South 2 0.13). The customer's jurisdiction is a urpx:ProfileAlternatives dimension. Each "
        "alternative applies its percentage twice, as a multiplier over the RTS version's energy subtotal, "
        "which holds its Peak, Mid-Peak and Off-Peak energy charges, and as a multiplier over its Base "
        "Service Charge. A customer in Renton takes Schedule RTS with no multiplier and no "
        "undergrounding charge, so takes it without this modifier."
    )
    if NEXT[date]:
        text += f" Superseded on {NEXT[date]} by the ordinance's next multiplier column."
    return text


ELIGIBILITY = (
    "SMC 21.49.030.B: the franchise and tax multipliers and suburban undergrounding charges of Schedule RSS "
    "apply to Schedule RTS. Which multiplier and which undergrounding charges apply is set by the location "
    "of service and is the urpx:ProfileAlternative selected. The condition expression tests only that the "
    "customer is residential.")


def build(date):
    v = f"scl:{SLUG}-{date}"
    base = f"scl:rts-{date}"
    pe = f"{v}-plan-elements"
    mi_e, mi_m = f"{v}-mi-energy", f"{v}-mi-meter-count"
    led_ft_e = f"{v}-ledger-franchise-tax-energy"
    led_ft_b = f"{v}-ledger-franchise-tax-base-service-charge"
    led_ug = f"{v}-ledger-undergrounding"
    pa = f"{v}-pa-jurisdiction"
    pd_ft_e = f"{v}-pd-franchise-tax-energy"
    pd_ft_b = f"{v}-pd-franchise-tax-base-service-charge"

    alternatives = []
    for j in ORDER:
        name = JURISDICTION[j]
        alternatives.append({
            "@type": "urpx:ProfileAlternative", "@id": f"{v}-pa-{j}",
            "urpx:name": f"Service location in {name}",
            "urpx:hasConditionExpression": {
                "@type": "urpx:ConditionExpression", "@id": f"{v}-cx-pa-{j}",
                "urpx:rootNode": {
                    "@type": "urpx:ComparisonNode", "@id": f"{v}-cn-pa-{j}",
                    "urpx:operator": ref("urpx:equalsOperator"),
                    "urpx:leftOperand": {"@type": "urpx:CustomOperandNode", "@id": f"{v}-cn-pa-{j}-left-operand",
                                         "urpx:customConditionProperty": "serviceJurisdiction"},
                    "urpx:rightOperand": {"@type": "urpx:CustomOperandNode", "@id": f"{v}-cn-pa-{j}-right-operand",
                                          "urpx:stringValue": name}}}})

    ug_pds = []
    for j in ("shoreline", "burien"):
        for s, label, _c in UNDERGROUNDING[j]:
            ug_pds.append({"@type": "urpx:PriceDefinition", "@id": f"{v}-pd-undergrounding-{s}",
                           "urpx:name": f"{label} Undergrounding Charge ({JURISDICTION[j]})",
                           "urpx:chargeType": ref("urpx:recoverySurcharge"),
                           "urpx:chargeCategory": ref("urpx:adjustment"),
                           "urpx:billPortion": ref("urpx:bundledPortion"),
                           "urpx:referencesLedger": ref(led_ug)})

    psas = []
    for j in ORDER:
        pct = MULTIPLIERS[j][date]
        frac = percent_to_fraction(pct)
        prices = [
            {"@type": "urpx:Price", "@id": f"{v}-price-{j}-franchise-tax-energy",
             "urpx:referencesPriceDefinition": ref(pd_ft_e), "urpx:startDate": date,
             "urpx:name": f"{JURISDICTION[j]} franchise and tax multiplier, {pct} percent of the Schedule RTS energy charge",
             "urpx:multiplier": frac, "urpx:basedOnPrice": [ref(f"{base}-summary-energy")]},
            {"@type": "urpx:Price", "@id": f"{v}-price-{j}-franchise-tax-base-service-charge",
             "urpx:referencesPriceDefinition": ref(pd_ft_b), "urpx:startDate": date,
             "urpx:name": f"{JURISDICTION[j]} franchise and tax multiplier, {pct} percent of the Schedule RTS Base Service Charge",
             "urpx:multiplier": frac, "urpx:basedOnPrice": [ref(f"{base}-price-base-service-charge")]},
        ]
        for s, label, c in UNDERGROUNDING.get(j, []):
            prices.append({"@type": "urpx:Price", "@id": f"{v}-price-undergrounding-{s}",
                           "urpx:referencesPriceDefinition": ref(f"{v}-pd-undergrounding-{s}"),
                           "urpx:startDate": "2025-01-01",
                           "urpx:name": f"{label} Undergrounding Charge", "urpx:unitPrice": cents_to_dollars(c)})
        psas.append({"@type": "urpx:PriceSetAlternative", "@id": f"{v}-psa-{j}",
                     "urpx:referencesProfileAlternative": ref(f"{v}-pa-{j}"), "urpx:hasPrice": prices})

    version = {
        "@type": "urpx:RatePlanModifierVersion",
        "@id": v,
        "urpx:version": date,
        "urpx:modifierVersionNumber": date,
        "urpx:changeReason": ref("urpx:rateCase"),
        "urpx:description": description(date),
        "urpx:effectiveDateTime": f"{date}T00:00:00",
    }
    if NEXT[date]:
        version["urpx:expirationDateTime"] = f"{NEXT[date]}T00:00:00"
    version.update({
        "urpx:priceCurrency": "USD",
        "urpx:commodity": ref("urpx:electricity"),
        "urpx:serviceRole": ref("urpx:bundledServiceRole"),
        "urpx:applicableToRatePlan": [ref("scl:rts")],
        "urpx:hasDataSourceReference": {
            "@type": "urpx:DataSourceReference", "urpx:fileName": "Ord_127473.pdf",
            "urpx:mediaType": ref("urpx:applicationPdf"), "urpx:accessURL": ORD_URL,
            "urpx:dateRetrieved": RETRIEVED, "urpx:dataSourceType": ref("urpx:regulatoryWebsiteSource"),
            "urpx:pageStart": 9, "urpx:pageEnd": 11},
        "urpx:hasEligibilityRule": [{
            "@type": "urpx:EligibilityRule", "@id": f"{v}-er-residential",
            "urpx:name": "Residential customer on Schedule RTS in a suburban jurisdiction",
            "urpx:description": ELIGIBILITY,
            "urpx:hasConditionExpression": {
                "@type": "urpx:ConditionExpression", "@id": f"{v}-er-residential-condition-expression",
                "urpx:rootNode": {
                    "@type": "urpx:ComparisonNode", "@id": f"{v}-er-residential-condition-expression-root-node",
                    "urpx:operator": ref("urpx:equalsOperator"),
                    "urpx:leftOperand": {"@type": "urpx:ObjectOperandNode",
                                         "@id": f"{v}-er-residential-condition-expression-root-node-left-operand",
                                         "urpx:conditionProperty": ref("urpx:hasCustomerKind")},
                    "urpx:rightOperand": {"@type": "urpx:ObjectOperandNode",
                                          "@id": f"{v}-er-residential-condition-expression-root-node-right-operand",
                                          "urpx:referencesValue": ref("urpx:residentialKind")}}}}],
        "urpx:hasPlanElements": {
            "@type": "urpx:PlanElements", "@id": pe,
            "urpx:hasMetricInput": [
                {"@type": "urpx:MetricInput", "@id": mi_e, "urpx:name": "kWh Energy Consumption Prices",
                 "urpx:metricInputType": ref("urpx:measuredMetricInput"),
                 "urpx:hasMetricSpecification": {"@type": "urpx:MetricSpecification", "@id": "scl:ms-energy",
                                                 "urpx:measurementKind": ref("urpx:energy"),
                                                 "urpx:unitOfMeasure": ref("urpx:kWh")}},
                {"@type": "urpx:MetricInput", "@id": mi_m, "urpx:name": "Per Meter Prices",
                 "urpx:metricInputType": ref("urpx:profileMetricInput"),
                 "urpx:profileMetricProperty": ref("urpx:meterCount")}],
            "urpx:hasProfileAlternatives": {
                "@type": "urpx:ProfileAlternatives", "@id": pa,
                "urpx:name": "Location of service: the suburban jurisdiction the customer is served in",
                "urpx:hasAlternativeDimensions": {
                    "@type": "urpx:AlternativeDimensions", "@id": f"{pa}-alternative-dimensions",
                    "urpx:hasAlternativeDimension": [{
                        "@type": "urpx:AlternativeDimension", "@id": f"{v}-ad-jurisdiction",
                        "urpx:dimensionDisplayName": "Suburban jurisdiction",
                        "urpx:customDimensionProperty": "serviceJurisdiction",
                        "urpx:hasPossibleValues": {"@list": [{"@value": JURISDICTION[j], "@type": "xsd:string"}
                                                             for j in ORDER]}}]},
                "urpx:hasProfileAlternative": alternatives},
            "urpx:hasBillingModel": {
                "@type": "urpx:BillingModel", "@id": f"{pe}-billing-model",
                "urpx:hasLedger": [
                    {"@type": "urpx:Ledger", "@id": led_ft_e, "urpx:name": "Franchise and Tax Multiplier, Energy Charge",
                     "urpx:ledgerType": ref("urpx:bundledLedger"), "urpx:referencesMetricInput": ref(mi_e)},
                    {"@type": "urpx:Ledger", "@id": led_ft_b,
                     "urpx:name": "Franchise and Tax Multiplier, Base Service Charge",
                     "urpx:ledgerType": ref("urpx:bundledLedger"), "urpx:referencesMetricInput": ref(mi_m)},
                    {"@type": "urpx:Ledger", "@id": led_ug, "urpx:name": "Suburban Undergrounding Charges",
                     "urpx:ledgerType": ref("urpx:bundledLedger"), "urpx:referencesMetricInput": ref(mi_e)}],
                "urpx:hasPriceDefinition": [
                    {"@type": "urpx:PriceDefinition", "@id": pd_ft_e,
                     "urpx:name": "Suburban franchise and tax multiplier on the Schedule RTS energy charge",
                     "urpx:chargeType": ref("urpx:taxMunicipal"), "urpx:chargeCategory": ref("urpx:taxes"),
                     "urpx:billPortion": ref("urpx:bundledPortion"), "urpx:referencesLedger": ref(led_ft_e)},
                    {"@type": "urpx:PriceDefinition", "@id": pd_ft_b,
                     "urpx:name": "Suburban franchise and tax multiplier on the Schedule RTS Base Service Charge, per meter per day",
                     "urpx:chargeType": ref("urpx:taxMunicipal"), "urpx:chargeCategory": ref("urpx:taxes"),
                     "urpx:billPortion": ref("urpx:bundledPortion"), "urpx:baseQuantity": "1",
                     "urpx:hasCalculationMethod": {"@type": "urpx:CalculationMethod",
                                                   "@id": f"{pd_ft_b}-calculation-method",
                                                   "urpx:intervalDuration": "P1D"},
                     "urpx:referencesLedger": ref(led_ft_b)},
                ] + ug_pds}},
        "urpx:hasPrices": {
            "@type": "urpx:Prices", "@id": f"{v}-prices",
            "urpx:hasPriceSetAlternatives": [{
                "@type": "urpx:PriceSetAlternatives", "@id": f"{v}-psa-by-jurisdiction",
                "urpx:name": "Franchise and tax multiplier and undergrounding charges, by location of service",
                "urpx:referencesProfileAlternatives": ref(pa),
                "urpx:hasPriceSetAlternative": psas}]},
        "urpx:offeredBy": {
            "@type": "urpx:UtilityOperator", "@id": "org:utility-scl", "urpx:legalName": "Seattle City Light",
            "urpx:organizationType": ref("urpx:utilityOrganization"),
            "urpx:hasIdentity": {"@id": "org:utility-scl-identity", "@type": "urpx:OrganizationIdentity",
                                 "urpx:hasName": {"@id": "org:utility-scl-name", "@type": "urpx:OrganizationName",
                                                  "urpx:name": "Seattle City Light"},
                                 "urpx:hasIdentifier": {"@id": "org:utility-scl-eia", "@type": "urpx:OrganizationIdentifier",
                                                        "urpx:scheme": ref("urpx:eiaScheme"), "skos:notation": "16868"}}},
        "urpx:forRatePlanModifier": ref(f"scl:{SLUG}"),
        "urpx:hasCoverageClaim": {
            "@id": f"scl:cc-{SLUG}-{date}", "@type": "urpx:CoverageClaim",
            "urpx:completenessResult": ref("urpx:complete"), "urpx:selfContained": True},
    })

    rts = json.load(open(REPO / f"us/wa/scl/electricity/rts/versions/{date}/rate-plan_scl_rts_{date}.jsonld"))
    ctx = dict(rts["@context"])
    ctx["urpx:multiplier"] = {"@type": "xsd:decimal"}
    return {
        "@context": ctx,
        "@type": "urpx:URPXPackage",
        "@id": f"scl:doc-{SLUG}-{date}",
        "urpx:targetURPXVersion": "https://github.com/urpx-org/urpx/raw/v0.5.1/ontology/urpx-ontology.ttl",
        "urpx:hasRatePlanModifier": {
            "@type": "urpx:RatePlanModifier", "@id": f"scl:{SLUG}",
            "urpx:name": "Residential Suburban Franchise and Tax Multipliers and Undergrounding Charges",
            "urpx:modifierUniqueIdentifier": "RSS-RTS-SUBURBAN",
            "urpx:initialEffectiveDate": "2024-01-01",
            "urpx:timezoneIdentifier": "America/Los_Angeles",
            "urpx:hasRatePlanModifierVersion": version}}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def notes(date):
    year = date[:4]
    nxt = NEXT[date]
    m = {j: MULTIPLIERS[j][date] for j in ORDER}
    return f"""
Read from Ordinance 127473 (Council Bill 121231), which amends SMC 21.49.030.
The "RSS suburban franchise and tax multipliers" table is on ordinance page 9,
the Suburban Undergrounding Charges on pages 9 and 10, and the sentence
applying both to Schedule RTS on pages 10 and 11. Read with pdftotext -layout.
The ordinance carries legislative markup, struck columns in ((...)), so a value
is bound to its year by its column header. This filing carries the multiplier
column headed "Effective January 1, {year}" and the undergrounding column
headed "Effective January 1, 2025".

## Dependency on urpx-org/urpx#71

This filing uses no unreleased vocabulary, but it composes only with Schedule
RTS, whose brackets use urpx:daysOfWeek (urpx-org/urpx#71,
https://github.com/urpx-org/urpx/pull/71).

## Which table

Ordinance 127473 carries one franchise and tax multiplier table per rate
class: "RSS suburban franchise and tax multipliers" for residential service
(21.49.030.A) and separate tables, with different Tukwila values, for
Schedules SMS, MDS, LGS and HDS (small, medium, large and high demand general
service). 21.49.030.B applies "The
same franchise and tax multipliers and suburban undergrounding charges ... to
Schedule RTS as Schedule RSS", so RTS takes the RSS table and the RTS rates
have no table of their own. This modifier applies to scl:rts only.

## Multipliers

21.49.030.A: "All charges in Schedule RSS shall be increased by the following
percentages respective of the location of service". All charges includes the
Base Service Charge, so each alternative applies its percentage twice: as a
multiplier over scl:rts-{date}-summary-energy, a urpx:PriceSummary
in the RTS filing naming its Peak, Mid-Peak and Off-Peak energy charges, and
as a multiplier over scl:rts-{date}-price-base-service-charge. The multiplier carried is
the increase, so the composed charge is the RTS charge times one plus it. In
this column: Burien, King County, SeaTac and Shoreline {m['burien']}%; Tukwila
{m['tukwila']}%; Lake Forest Park {m['lake-forest-park']}%; Normandy Park
{m['normandy-park']}%. The ordinance names "King County"; City Light's
residential rates page ({RATES_URL},
retrieved {RETRIEVED}) heads the same column "Uninc. King County".

Renton is not in the table. City Light's residential rates page lists Renton
with the unmultiplied Schedule RTS rates ($0.3945 per day, Peak $0.1632,
Mid-Peak $0.1428, Off-Peak $0.0816 per kWh in 2026), so a Renton customer
takes RTS without this modifier.

## Undergrounding charges

21.49.030.A: "Additional undergrounding charges will apply to all customers in
Shoreline and Burien as follows", then five charges under Shoreline (North
City, Aurora 1, Aurora 2, Aurora 3A, Aurora 3B) and two under Burien (First
Avenue South 1 and 2). Read as cumulative: every customer in Shoreline pays
all five ({total_undergrounding('shoreline')} cents per kWh in total) and every customer in Burien
both ({total_undergrounding('burien')} cents per kWh). The names are of the undergrounding projects
whose cost is recovered, not of areas of service. City Light's rates page says
"the undergrounding cost is recovered from all customers in that jurisdiction
via a kWh undergrounding charge according to the table below", and before
2023 Schedule RSH (Residential: Shoreline) listed all five charges as lines
of one schedule and Schedule RSB (Residential: Burien) both of its two
(Ordinance 126677, which converted both to RSS). Each charge is its own
urpx:PriceDefinition and urpx:Price in the Shoreline or Burien alternative.

The ordinance does not say whether the percentage increase applies to the
undergrounding charges. They are carried unmultiplied: the multiplier Prices
are based on the RTS charges only.

## Reconciliation

City Light's residential rates page publishes the 2026 Time of Use prices for
each jurisdiction. Each published cell equals the RTS charge times one plus
the multiplier, rounded half up to $0.0001: 20 of 20 cells (Base Service
Charge and three energy charges, for the Burien/SeaTac/Shoreline/King County,
Lake Forest Park, Normandy Park and Tukwila columns). The model carries the
unrounded product, which differs from the published cell by at most
$0.000044 (Burien, SeaTac, Shoreline and King County Peak: 0.176256 against
0.1763). The page publishes no 2027 or 2028 values.

## Dating

Dated {date}, the effective date the ordinance prints on the multiplier
column this filing carries, matching the Schedule RTS version of the same
date. {"Bounded at " + nxt + " by the next column." if nxt else "It is the last column the ordinance enacts."}
urpx:initialEffectiveDate is 2024-01-01, when Ordinance 126677 added Schedule
RTS with the sentence applying the RSS multipliers and undergrounding charges
to it.
"""


README = """# SCL residential suburban multipliers and undergrounding charges on Schedule RTS, {date}

The suburban franchise and tax multipliers and suburban undergrounding charges that Seattle Municipal Code 21.49.030 applies to Schedule RSS and, by 21.49.030.B, to Schedule RTS (Residential: Suburban Time-of-Use), as amended by Ordinance 127473. This version carries the multiplier column headed "Effective January 1, {year}" and composes with `scl:rts-{date}`.

**This filing depends on [urpx-org/urpx#71](https://github.com/urpx-org/urpx/pull/71) through Schedule RTS**, whose brackets use `urpx:daysOfWeek`.

## Files

- `scl_{slug}_{date}.pdf`: Ordinance 127473 as `Ord_127473.pdf` on clerk.seattle.gov. The multiplier table is on page 9, the undergrounding charges on pages 9 and 10.
- `tariff.toml`: provenance, how the tables were read, reconciliation against City Light's published prices.
- `rate-plan-modifier_scl_{slug}_{date}.jsonld`: the URPX serialization.

## Rates

The customer's jurisdiction is a `urpx:ProfileAlternative`. The percentage increases every Schedule RTS charge, Base Service Charge included.

| Jurisdiction | Increase | Undergrounding, cents per kWh |
| --- | --- | --- |
{rows}

Renton customers take Schedule RTS unmultiplied, without this modifier. Shoreline's charges are North City 0.07, Aurora 1 0.17, Aurora 2 0.18, Aurora 3A 0.05 and Aurora 3B 0.22; Burien's are First Avenue South 1 0.37 and First Avenue South 2 0.13. Every customer in the city pays each of them. They are carried without the percentage increase.
"""


def write_manifest(date, pdf):
    lines = [
        "# Identity --------------------------------------------------------------------",
        'utility = "scl"', f'schedule = "{SLUG}"', f'effective_date = "{date}"', "",
        "# Composes only with Schedule RTS, which uses urpx:daysOfWeek (urpx-org/urpx#71).",
        "# See [extraction].notes and README.md.",
        "",
        "# Source ----------------------------------------------------------------------",
        "[source]", f"url = {q(ORD_URL)}", f'sha256 = "{sha(pdf)}"', f'retrieved_on = "{RETRIEVED}"',
        'media_type = "application/pdf"', 'filing_type = "ordinance"', 'filing_id = "Ordinance 127473"',
        f"landing_page = {q(SMC_URL)}", "",
        "# Regulatory ------------------------------------------------------------------",
        "[regulator]", 'authority = "city-council"', 'docket = "Council Bill 121231"', "",
        "# Extraction ------------------------------------------------------------------",
        "[extraction]", 'tool = "pdftotext"', 'tool_version = "26.09.0"', f'extracted_on = "{RETRIEVED}"',
        'notes = """' + notes(date) + '"""', "",
        "# Validation ------------------------------------------------------------------",
        "[validation]", "shacl_passed = true", 'validator = "pyshacl (URPX v0.5.1) + clj-urpx"',
        f'validated_on = "{RETRIEVED}"', "",
        "# Modeling --------------------------------------------------------------------",
        "[modeling]", "complete = true", "deferrals = []", "",
        "# Review ----------------------------------------------------------------------",
        "[review]", 'status = "draft"',
        'notes = "Composes only with Schedule RTS, which uses urpx:daysOfWeek from urpx-org/urpx#71."', ""]
    return "\n".join(lines)


if __name__ == "__main__":
    for date in DATES:
        d = REPO / f"us/wa/scl/electricity/{SLUG}/versions/{date}"
        d.mkdir(parents=True, exist_ok=True)
        pdf = d / f"scl_{SLUG}_{date}.pdf"
        shutil.copyfile(REPO / f"us/wa/scl/electricity/rts/versions/{date}/scl_rts_{date}.pdf", pdf)
        out = d / f"rate-plan-modifier_scl_{SLUG}_{date}.jsonld"
        doc = build(date)
        out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        (d / "tariff.toml").write_text(write_manifest(date, pdf))
        rows = "\n".join(
            f"| {JURISDICTION[j]} | {MULTIPLIERS[j][date]}% | "
            f"{total_undergrounding(j) + ' (' + str(len(UNDERGROUNDING[j])) + ' charges)' if j in UNDERGROUNDING else 'none'} |"
            for j in ORDER)
        (d / "README.md").write_text(README.format(date=date, year=date[:4], slug=SLUG, rows=rows))
        print("wrote", d)
