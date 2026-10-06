#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""One-off: author the JSON-LD of us/wa/pse/electricity/307/versions/{2026-05-01,2026-10-01}/.

Takes the repository root. Run once, then dev/resync_coverage_evaluations.py,
which owns each CoverageClaim Evaluation's text; a re-run keeps the Evaluation
already on disk. dev/author_pse_307_manifests.py writes the tariff.toml files
and copies the source PDFs.

    python3 dev/author_pse_307.py .
"""
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(sys.argv[1])
RETRIEVED = "2026-10-05"
PSE = "https://www.pse.com/-/media/Project/PSE/Portal/Rate-documents/Electric/"
UTC129 = "https://apiproxy.utc.wa.gov/cases/GetDocument?docID=4&year=2025&docketNumber=250648"

# (key, schedule label, PDF basename, sheet, sheet effective, name, value(s), chargeType, chargeCategory, group)
# value is a dict keyed by version date when it differs between versions.
RIDERS = [
    ("sch-111", "111", "elec_sch_111.pdf", "111-C", "2026-01-01",
     "Greenhouse Gas Emissions Cap and Invest Adjustment (Schedule 111)", "-0.012600",
     "adjustmentTariff", "environmental", "electricity"),
    ("sch-111-supplemental", "111", "elec_sch_111.pdf", "111-K", "2026-01-01",
     "Greenhouse Gas Emissions Cap and Invest Adjustment Supplemental Rate (Schedule 111)", "0.002963",
     "adjustmentTariff", "environmental", "electricity"),
    ("sch-129", "129", None, "129-B", None,
     "Low Income Program (Schedule 129)", {"2026-05-01": "0.007550", "2026-10-01": "0.009204"},
     "publicBenefits", "regulatory", "electricity"),
    ("sch-129d", "129D", "elec_sch_129d.pdf", "129D-A", "2026-01-01",
     "Bill Discount Rate Rider (Schedule 129D)", "0.002958",
     "publicBenefits", "regulatory", "electricity"),
    ("sch-140", "140", "elec_sch_140.pdf", "140-B", "2026-05-01",
     "Property Tax Tracker (Schedule 140)", "0.002010",
     "taxAdjustment", "taxes", "electricity"),
    ("sch-141a", "141A", "elec_sch_141a.pdf", "141A-A", "2026-01-01",
     "Energy Charge Credit Recovery Adjustment (Schedule 141A)", "0.002010",
     "recoverySurcharge", "adjustment", "electricity"),
    ("sch-141cei", "141CEI", "elec_sch_141cei.pdf", "141CEI-A", "2025-01-29",
     "Clean Energy Implementation Tracker (Schedule 141CEI)", "0.000000",
     "tariffRider", "adjustment", "electricity"),
    ("sch-141col", "141COL", "elec_sch_141col.pdf", "141COL-B", "2026-01-01",
     "Colstrip Adjustment Rider (Schedule 141COL)", "-0.001183",
     "tariffRider", "adjustment", "electricity"),
    ("sch-141n", "141N", "elec_sch_141n.pdf", "141N", "2025-01-29",
     "Rates Not Subject to Refund Rate Adjustment (Schedule 141N)", "0.000000",
     "tariffRider", "adjustment", "electricity"),
    ("sch-141pfg", "141PFG", "elec_sch_141pfg.pdf", "141PFG", "2025-01-29",
     "Participatory Funding Grants Rate Adjustment (Schedule 141PFG)", "0.000000",
     "tariffRider", "adjustment", "electricity"),
    ("sch-141r", "141R", "elec_sch_141r.pdf", "141R", "2025-01-29",
     "Rates Subject to Refund Rate Adjustment (Schedule 141R)", "0.000000",
     "tariffRider", "adjustment", "electricity"),
    ("sch-141tep", "141TEP", "elec_sch_141tep.pdf", "141TEP-A", "2026-05-01",
     "Transportation Electrification Plan Adjustment Rider (Schedule 141TEP)", "0.000520",
     "tariffRider", "adjustment", "electricity"),
    ("sch-141tex", "141TEX", "elec_sch_141tex.pdf", "141TEX-A", "2025-04-15",
     "Targeted Exception Rate Adjustment (Schedule 141TEX)", "0.000457",
     "tariffRider", "adjustment", "electricity"),
    ("sch-141wfp", "141WFP", "elec_sch_141wfp.pdf", "141WFP-A", "2026-03-21",
     "Wildfire Prevention Tracker (Schedule 141WFP)", "0.002246",
     "tariffRider", "adjustment", "electricity"),
    ("sch-142", "142", "elec_sch_142.pdf", "142-H", "2026-05-01",
     "Revenue Decoupling Adjustment Mechanism (Schedule 142)", "-0.000166",
     "adjustmentTariff", "adjustment", "electricity"),
    ("sch-95", "95", "elec_sch_095.pdf", "95", "2026-01-01",
     "Power Cost Adjustment Clause (Schedule 95)", "0.035046",
     "adjustmentPowerCost", "adjustment", "additional"),
    ("sch-95-supplemental", "95", "elec_sch_095.pdf", "95-E.3", "2025-10-01",
     "Power Cost Adjustment Clause Supplemental Rate (Schedule 95)", "0.003673",
     "adjustmentPowerCost", "adjustment", "additional"),
    ("sch-120", "120", "elec_sch_120.pdf", "120", "2026-05-01",
     "Electricity Conservation Service Rider (Schedule 120)", "0.009409",
     "efficiencyFunding", "regulatory", "additional"),
    ("sch-194", "194", "elec_sch_194.pdf", "194-A", "2025-10-01",
     "Residential and Farm Energy Exchange Benefit (Schedule 194)", "-0.006648",
     "creditTariffRider", "adjustment", "additional"),
    ("sch-95a", "95A", "elec_sch_095a.pdf", "95-G", "2026-05-01",
     "Federal Incentive Tracker (Schedule 95A)", "-0.002378",
     "creditTariffRider", "adjustment", "additional"),
    ("sch-137", "137", "elec_sch_137.pdf", "137-A", "2025-01-01",
     "Temporary Customer Charge or Credit (Schedule 137)", "0.000000",
     "tariffRider", "adjustment", "additional"),
]



def ref(i):
    return {"@id": i}


def nahd(year):
    nov1 = dt.date(year, 11, 1)
    first_thu = nov1 + dt.timedelta(days=(3 - nov1.weekday()) % 7)
    return first_thu + dt.timedelta(days=22)


def build(date, expires=None):
    v = f"pse:307-{date}"
    pe = f"{v}-plan-elements"
    S = {"summer": f"{v}-season-summer", "winter": f"{v}-season-winter"}
    mi_e, mi_m = f"{v}-mi-energy", f"{v}-mi-meter-count"
    L = {"energy": f"{v}-ledger-energy-charge",
         "electricity": f"{v}-ledger-electricity-charge-adjustments",
         "additional": f"{v}-ledger-additional-electricity-charges",
         "basic": f"{v}-ledger-basic-charge"}

    def bracket(name, start, end, season, day, hol=None):
        b = {"@type": "urpx:TimeBracket", "@id": f"{v}-time-bracket-{name}",
             "urpx:startTime": start, "urpx:endTime": end,
             "urpx:appliesInSeason": ref(S[season]), "urpx:dayType": ref(f"urpx:{day}")}
        if hol is not None:
            b["urpx:includeHolidays"] = hol
            b["urpx:includeNonHolidays"] = not hol
        return b

    def period(name, num, label, brackets):
        return {"@type": "urpx:TOUPeriod", "@id": f"{v}-tou-period-{name}", "urpx:name": label,
                "urpx:touPeriodNumber": num, "urpx:hasTimeBracket": brackets}

    tiers = [
        {"@type": "urpx:TOUTier", "@id": f"{v}-tou-tier-peak", "urpx:tierSourceName": "Peak",
         "urpx:touTierStandardName": ref("urpx:peakTier"), "urpx:touTierNumber": 1,
         "urpx:hasTOUPeriod": [
             period("summer-peak", 1, "Summer Peak (weekdays 5pm-8pm, not on a legal holiday)", [
                 bracket("summer-peak-evening", "17:00:00", "20:00:00", "summer", "weekdayDays", False)]),
             period("winter-peak", 3, "Winter Peak (weekdays 7am-10am and 5pm-8pm, not on a legal holiday)", [
                 bracket("winter-peak-morning", "07:00:00", "10:00:00", "winter", "weekdayDays", False),
                 bracket("winter-peak-evening", "17:00:00", "20:00:00", "winter", "weekdayDays", False)]),
         ]},
        {"@type": "urpx:TOUTier", "@id": f"{v}-tou-tier-off-peak", "urpx:tierSourceName": "Off-Peak",
         "urpx:touTierStandardName": ref("urpx:offPeakTier"), "urpx:touTierNumber": 2,
         "urpx:hasTOUPeriod": [
             period("summer-off-peak", 2, "Summer Off-Peak (weekdays 12am-5pm and 8pm-12am; all day on weekends and legal holidays)", [
                 bracket("summer-off-peak-weekday-early", "00:00:00", "17:00:00", "summer", "weekdayDays"),
                 bracket("summer-off-peak-weekday-late", "20:00:00", "00:00:00", "summer", "weekdayDays"),
                 bracket("summer-off-peak-holiday-evening", "17:00:00", "20:00:00", "summer", "weekdayDays", True),
                 bracket("summer-off-peak-weekend", "00:00:00", "00:00:00", "summer", "weekendDays")]),
             period("winter-off-peak", 4, "Winter Off-Peak (weekdays 12am-7am, 10am-5pm and 8pm-12am; all day on weekends and legal holidays)", [
                 bracket("winter-off-peak-weekday-early", "00:00:00", "07:00:00", "winter", "weekdayDays"),
                 bracket("winter-off-peak-weekday-midday", "10:00:00", "17:00:00", "winter", "weekdayDays"),
                 bracket("winter-off-peak-weekday-late", "20:00:00", "00:00:00", "winter", "weekdayDays"),
                 bracket("winter-off-peak-holiday-morning", "07:00:00", "10:00:00", "winter", "weekdayDays", True),
                 bracket("winter-off-peak-holiday-evening", "17:00:00", "20:00:00", "winter", "weekdayDays", True),
                 bracket("winter-off-peak-weekend", "00:00:00", "00:00:00", "winter", "weekendDays")]),
         ]},
    ]

    def holiday(slug, name, rule=None, date_=None, nearest=False):
        h = {"@type": "urpx:Holiday", "@id": f"{v}-holiday-{slug}", "urpx:holidayName": name}
        if rule:
            h["urpx:holidayRule"] = rule
        if date_:
            h["urpx:holidayDate"] = {"@value": date_, "@type": "xsd:date"}
        if nearest:
            h["urpx:observanceRule"] = ref("urpx:nearestWeekdayObservance")
        return h

    holidays = [
        holiday("new-years-day", "New Year's Day", "January 1", nearest=True),
        holiday("martin-luther-king-jr-day", "Martin Luther King, Jr. Day", "Third Monday in January"),
        holiday("presidents-day", "Presidents' Day", "Third Monday in February"),
        holiday("memorial-day", "Memorial Day", "Last Monday in May"),
        holiday("juneteenth", "Juneteenth", "June 19", nearest=True),
        holiday("independence-day", "Independence Day", "July 4", nearest=True),
        holiday("labor-day", "Labor Day", "First Monday in September"),
        holiday("veterans-day", "Veterans' Day", "November 11", nearest=True),
        holiday("thanksgiving-day", "Thanksgiving Day", "Fourth Thursday in November"),
    ] + [
        holiday(f"native-american-heritage-day-{y}", "Native American Heritage Day", date_=nahd(y).isoformat())
        for y in range(int(date[:4]), 2041)
    ] + [
        holiday("christmas-day", "Christmas Day", "December 25", nearest=True),
    ]

    energy_pds, energy_prices = [], []
    tou = [("summer-peak", 1, "Summer Peak", "0.335186"), ("summer-off-peak", 2, "Summer Off-Peak", "0.108197"),
           ("winter-peak", 3, "Winter Peak", "0.532445"), ("winter-off-peak", 4, "Winter Off-Peak", "0.108197")]
    for slug, num, label, val in tou:
        energy_pds.append({"@type": "urpx:PriceDefinition", "@id": f"{v}-pd-energy-charge-{slug}",
                           "urpx:name": f"Time-of-Use Energy Charge, {label} (Schedule 307)",
                           "urpx:chargeType": ref("urpx:usageCharge"), "urpx:chargeCategory": ref("urpx:auxiliaryCharge"),
                           "urpx:billPortion": ref("urpx:bundledPortion"), "urpx:touPeriodNumber": num,
                           "urpx:referencesLedger": ref(L["energy"])})
        energy_prices.append({"@type": "urpx:Price", "@id": f"{v}-price-energy-charge-{slug}",
                              "urpx:referencesPriceDefinition": ref(f"{v}-pd-energy-charge-{slug}"),
                              "urpx:name": f"Energy Charge, {label}", "urpx:unitPrice": val})

    rider_pds, rider_prices = [], []
    for key, sch, pdf, sheet, eff, name, val, ctype, ccat, group in RIDERS:
        if isinstance(val, dict):
            val = val[date]
        if sch == "129" and date == "2026-05-01":
            dsr = {"@type": "urpx:DataSourceReference",
                   "urpx:fileName": "pse_129_2025-10-01.pdf", "urpx:accessURL": UTC129,
                   "urpx:mediaType": ref("urpx:applicationPdf"), "urpx:dateRetrieved": RETRIEVED,
                   "urpx:dataSourceType": ref("urpx:regulatoryWebsiteSource"),
                   "urpx:leafStart": "129-B", "urpx:leafEnd": "129-B"}
        else:
            fn = pdf or "elec_sch_129.pdf"
            dsr = {"@type": "urpx:DataSourceReference", "urpx:fileName": fn, "urpx:accessURL": PSE + fn,
                   "urpx:mediaType": ref("urpx:applicationPdf"), "urpx:dateRetrieved": RETRIEVED,
                   "urpx:dataSourceType": ref("urpx:utilityWebsiteSource"),
                   "urpx:leafStart": sheet, "urpx:leafEnd": sheet}
        rider_pds.append({"@type": "urpx:PriceDefinition", "@id": f"{v}-pd-{key}", "urpx:name": name,
                          "urpx:chargeType": ref(f"urpx:{ctype}"), "urpx:chargeCategory": ref(f"urpx:{ccat}"),
                          "urpx:billPortion": ref("urpx:bundledPortion"),
                          "urpx:hasDataSourceReference": dsr,
                          "urpx:referencesLedger": ref(L[group])})
        rider_prices.append({"@type": "urpx:Price", "@id": f"{v}-price-{key}",
                             "urpx:referencesPriceDefinition": ref(f"{v}-pd-{key}"),
                             "urpx:name": name, "urpx:unitPrice": val})

    basic_pd = {"@type": "urpx:PriceDefinition", "@id": f"{v}-pd-basic-charge",
                "urpx:name": "Basic Charge, single phase (Schedule 307)",
                "urpx:chargeType": ref("urpx:customerCharge"), "urpx:chargeCategory": ref("urpx:serviceCharge"),
                "urpx:billPortion": ref("urpx:bundledPortion"), "urpx:baseQuantity": "1",
                "urpx:hasCalculationMethod": {"@type": "urpx:CalculationMethod",
                                              "@id": f"{v}-pd-basic-charge-calculation-method",
                                              "urpx:intervalDuration": "P1M"},
                "urpx:referencesLedger": ref(L["basic"])}

    def ledger(k, name):
        return {"@type": "urpx:Ledger", "@id": L[k], "urpx:name": name, "urpx:ledgerType": ref("urpx:bundledLedger"),
                "urpx:referencesMetricInput": ref(mi_m if k == "basic" else mi_e)}

    version = {
        "@type": "urpx:RatePlanVersion",
        "@id": v,
        "urpx:description": DESCRIPTION[date],
        "urpx:effectiveDateTime": f"{date}T00:00:00",
    }
    if expires:
        version["urpx:expirationDateTime"] = f"{expires}T00:00:00"
    version.update({
        "urpx:changeReason": ref("urpx:riderUpdate"),
        "urpx:priceCurrency": "USD",
        "urpx:commodity": ref("urpx:electricity"),
        "urpx:serviceRole": ref("urpx:bundledServiceRole"),
        "urpx:customerChoice": ref("urpx:voluntaryChoice"),
        "urpx:isDefault": False,
        "urpx:hasDataSourceReference": {
            "@type": "urpx:DataSourceReference", "urpx:fileName": "elec_sch_307.pdf",
            "urpx:mediaType": ref("urpx:applicationPdf"), "urpx:accessURL": PSE + "elec_sch_307.pdf",
            "urpx:dateRetrieved": RETRIEVED, "urpx:dataSourceType": ref("urpx:utilityWebsiteSource"),
            "urpx:pageStart": 1, "urpx:pageEnd": 4, "urpx:leafStart": "307", "urpx:leafEnd": "307-C"},
        "urpx:hasEligibilityRule": [{
            "@type": "urpx:EligibilityRule", "@id": f"{v}-er-residential",
            "urpx:name": "Eligibility for Schedule 307 Residential Service Time-of-Use",
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
            "urpx:hasSeasons": [
                {"@type": "urpx:Season", "@id": S["summer"], "urpx:seasonName": "Summer",
                 "urpx:month": ["--04", "--05", "--06", "--07", "--08", "--09"]},
                {"@type": "urpx:Season", "@id": S["winter"], "urpx:seasonName": "Winter",
                 "urpx:month": ["--10", "--11", "--12", "--01", "--02", "--03"]}],
            "urpx:hasHolidayCalendar": {"@type": "urpx:HolidayCalendar", "@id": f"{v}-holidays",
                                        "urpx:hasHoliday": holidays},
            "urpx:hasMetricInput": [
                {"@type": "urpx:MetricInput", "@id": mi_e, "urpx:name": "kWh Energy Consumption Prices",
                 "urpx:metricInputType": ref("urpx:measuredMetricInput"),
                 "urpx:hasMetricSpecification": {"@type": "urpx:MetricSpecification", "@id": "pse:ms-energy",
                                                 "urpx:measurementKind": ref("urpx:energy"),
                                                 "urpx:unitOfMeasure": ref("urpx:kWh")}},
                {"@type": "urpx:MetricInput", "@id": mi_m, "urpx:name": "Per Meter Prices",
                 "urpx:metricInputType": ref("urpx:profileMetricInput"),
                 "urpx:profileMetricProperty": ref("urpx:meterCount")}],
            "urpx:hasBillingModel": {
                "@type": "urpx:BillingModel", "@id": f"{pe}-billing-model",
                "urpx:hasTOUSchedule": {"@type": "urpx:TOUSchedule", "@id": f"{v}-tou-schedule",
                                        "urpx:referencesMetricInput": ref(mi_e), "urpx:hasTOUTier": tiers},
                "urpx:hasLedger": [
                    ledger("energy", "Time-of-Use Energy Charge (Schedule 307)"),
                    ledger("electricity", "Electricity Charge adjustments by supplemental schedules"),
                    ledger("additional", "Additional Electricity Charges and other charges and credits by supplemental schedules"),
                    ledger("basic", "Basic Charge")],
                "urpx:hasPriceDefinition": energy_pds + rider_pds + [basic_pd]}},
        "urpx:hasPrices": {
            "@type": "urpx:Prices", "@id": f"{v}-prices",
            "urpx:hasPrice": [{"@type": "urpx:Price", "@id": f"{v}-price-basic-charge",
                               "urpx:referencesPriceDefinition": ref(f"{v}-pd-basic-charge"),
                               "urpx:startDate": date, "urpx:name": "Basic Charge, single phase",
                               "urpx:unitPrice": "7.49"}],
            "urpx:hasPriceSet": [
                {"@type": "urpx:PriceSet", "@id": f"{v}-ps-energy-charge", "urpx:startDate": date,
                 "urpx:hasPrice": energy_prices},
                {"@type": "urpx:PriceSet", "@id": f"{v}-ps-supplemental-schedules", "urpx:startDate": date,
                 "urpx:hasPrice": rider_prices}]},
        "urpx:offeredBy": {
            "@type": "urpx:UtilityOperator", "@id": "org:utility-pse", "urpx:legalName": "Puget Sound Energy, Inc.",
            "urpx:organizationType": ref("urpx:utilityOrganization"),
            "urpx:hasIdentity": {"@id": "org:utility-pse-identity", "@type": "urpx:OrganizationIdentity",
                                 "urpx:hasName": {"@id": "org:utility-pse-name", "@type": "urpx:OrganizationName",
                                                  "urpx:name": "Puget Sound Energy, Inc."},
                                 "urpx:hasIdentifier": {"@id": "org:utility-pse-eia", "@type": "urpx:OrganizationIdentifier",
                                                        "urpx:scheme": ref("urpx:eiaScheme"), "skos:notation": "15500"}}},
        "urpx:forRatePlan": ref("pse:307"),
        "urpx:hasCoverageClaim": {
            "@id": f"pse:cc-307-{date}", "@type": "urpx:CoverageClaim",
            "urpx:completenessResult": ref("urpx:partial"), "urpx:selfContained": True,
            "urpx:explainedBy": {"@type": "urpx:Evaluation", "@id": f"pse:cc-307-{date}-evaluation",
                                 "urpx:evaluationKind": ref("urpx:coverageEvaluation"),
                                 "urpx:description": "This filing does not carry everything its source document states. 0 parts are deferred, listed here in the same words as the filing's tariff.toml [modeling].deferrals so the two records cannot drift.",
                                 "urpx:evaluatedOn": "2026-10-05T00:00:00"}},
    })

    ctx = json.load(open(REPO / "us/ca/smud/electricity/tod-5-8pm/versions/2026-01-01/rate-plan_smud_tod-5-8pm_2026-01-01.jsonld"))["@context"]
    ctx = {("pse" if k == "smud" else k): (val.replace("/smud/", "/pse/") if k == "smud" else val) for k, val in ctx.items()}
    ctx["urpx:expirationDateTime"] = {"@type": "xsd:dateTime"}
    return {
        "@context": ctx,
        "@type": "urpx:URPXPackage",
        "@id": f"pse:doc-307-{date}",
        "urpx:targetURPXVersion": "https://github.com/urpx-org/urpx/raw/v0.5.1/ontology/urpx-ontology.ttl",
        "urpx:hasRatePlan": {
            "@type": "urpx:RatePlan", "@id": "pse:307",
            "urpx:name": "Residential Service Time-of-Use",
            "urpx:ratePlanUniqueIdentifier": "307",
            "urpx:initialEffectiveDate": "2023-10-01",
            "urpx:timezoneIdentifier": "America/Los_Angeles",
            "urpx:hasRatePlanVersion": version}}


ELIGIBILITY = (
    "Sheet 307, AVAILABILITY: available to a Customer eligible for Schedule 7 Residential Service where PSE "
    "determines that adequate metering is available, on or after October 1, 2023; participation is limited to "
    "6,500 Customer accounts; PSE may limit participation for study purposes; a Customer taking optional "
    "Schedule 171 service is not eligible. ENROLLMENT: the Customer must complete PSE's enrollment process. "
    "Schedule 7 limits residential service to service delivered through one meter to a single-family unit and "
    "used principally for domestic purposes, including an adult family home. The condition expression tests "
    "only that the customer is residential.")

COMMON = (
    "Puget Sound Energy's optional residential time-of-use schedule, WN U-60 Electric Tariff G Schedule 307, "
    "sheets 307 through 307-C (307, 307-A and 307-B issued September 22, 2025 under Advice No. 2025-39, "
    "effective December 12, 2025, Docket UE-250725). It is a schedule in its own right rather than a rider on "
    "Schedule 7: it prices its own Basic Charge and a time-of-use Energy Charge, and a Customer leaves it by "
    "changing to Schedule 7. The Energy Charge here is the sheet 307-A column headed 'Beginning January 29, 2026'. "
    "Winter is October 1 through March 31 with Peak 7am-10am and 5pm-8pm; Summer is April 1 through September 30 "
    "with Peak 5pm-8pm; every other hour, and all day on weekends and the eleven legal holidays sheet 307-B lists, "
    "is Off-Peak. Each supplemental schedule that prices Schedule 307 per kWh is carried as its own Price with the "
    "rate that schedule states for Schedule 307, and each PriceDefinition cites the schedule and "
    "sheet. ")

DESCRIPTION = {
    "2026-05-01": COMMON + (
        "This version is the set of rates in force from May 1, 2026, the effective date of the newest supplemental "
        "sheets it carries (Schedules 95A, 120, 140, 141TEP and 142), until October 1, 2026, when the 25th Revision "
        "of Sheet 129-B replaced the Schedule 129 rate of $0.007550 per kWh carried here."),
    "2026-10-01": COMMON + (
        "This version is the set of rates in force from October 1, 2026, the effective date of the 25th Revision "
        "of Sheet 129-B (Schedule 129 Low Income Program, $0.009204 per kWh)."),
}

if __name__ == "__main__":
    for date, exp in (("2026-05-01", "2026-10-01"), ("2026-10-01", None)):
        d = REPO / f"us/wa/pse/electricity/307/versions/{date}"
        d.mkdir(parents=True, exist_ok=True)
        out = d / f"rate-plan_pse_307_{date}.jsonld"
        prev = None
        if out.exists():
            prev = json.load(open(out))
        doc = build(date, exp)
        if prev:  # keep a resynced evaluation
            pv = prev["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]["urpx:hasCoverageClaim"]["urpx:explainedBy"]["urpx:description"]
            doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]["urpx:hasCoverageClaim"]["urpx:explainedBy"]["urpx:description"] = pv
        out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        print("wrote", out)
