#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""One-off: author the JSON-LD of us/wa/pse/electricity/327/versions/{2026-05-01,2026-10-01}/.

Takes the repository root. Schedule 327 takes the same supplemental schedules
at the same rates as Schedule 307, so RIDERS and the rider sources come from
dev/author_pse_307.py; the TOU structure, Energy Charge and text are 327's
own. Run once, then dev/resync_coverage_evaluations.py, which owns each
CoverageClaim Evaluation's text; a re-run keeps the Evaluation already on
disk. dev/author_pse_327_manifests.py writes the tariff.toml files and copies
the source PDFs.

    python3 dev/author_pse_327.py .
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from author_pse_307 import PSE, RETRIEVED, RIDERS, UTC129, nahd, ref  # noqa: E402

REPO = Path(sys.argv[1])

# (slug, period number, label, $/kWh): sheet 327-A, column "Beginning January 29, 2026"
ENERGY = [("summer-peak", 1, "Summer Peak", "0.271839"),
          ("summer-off-peak", 2, "Summer Off-Peak", "0.122055"),
          ("winter-peak", 3, "Winter Peak", "0.503575"),
          ("winter-off-peak", 4, "Winter Off-Peak", "0.127088"),
          ("summer-super-off-peak", 5, "Summer Super Off-Peak", "0.075542"),
          ("winter-super-off-peak", 6, "Winter Super Off-Peak", "0.075542")]


def build(date, expires=None):
    v = f"pse:327-{date}"
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

    def peak(s, num):
        return period(f"{s}-peak", num,
                      f"{s.title()} Peak (weekdays 7am-10am and 5pm-8pm, not on a legal holiday)", [
                          bracket(f"{s}-peak-morning", "07:00:00", "10:00:00", s, "weekdayDays", False),
                          bracket(f"{s}-peak-evening", "17:00:00", "20:00:00", s, "weekdayDays", False)])

    def off_peak(s, num):
        return period(f"{s}-off-peak", num,
                      f"{s.title()} Off-Peak (weekdays 10am-5pm and 8pm-11pm; 7am-11pm on weekends and legal holidays)", [
                          bracket(f"{s}-off-peak-weekday-midday", "10:00:00", "17:00:00", s, "weekdayDays"),
                          bracket(f"{s}-off-peak-weekday-evening", "20:00:00", "23:00:00", s, "weekdayDays"),
                          bracket(f"{s}-off-peak-holiday-morning", "07:00:00", "10:00:00", s, "weekdayDays", True),
                          bracket(f"{s}-off-peak-holiday-evening", "17:00:00", "20:00:00", s, "weekdayDays", True),
                          bracket(f"{s}-off-peak-weekend", "07:00:00", "23:00:00", s, "weekendDays")])

    def super_off_peak(s, num):
        return period(f"{s}-super-off-peak", num, f"{s.title()} Super Off-Peak (daily 11pm-7am)", [
            bracket(f"{s}-super-off-peak-early", "00:00:00", "07:00:00", s, "allDays"),
            bracket(f"{s}-super-off-peak-late", "23:00:00", "00:00:00", s, "allDays")])

    tiers = [
        {"@type": "urpx:TOUTier", "@id": f"{v}-tou-tier-peak", "urpx:tierSourceName": "Peak",
         "urpx:touTierStandardName": ref("urpx:peakTier"), "urpx:touTierNumber": 1,
         "urpx:hasTOUPeriod": [peak("summer", 1), peak("winter", 3)]},
        {"@type": "urpx:TOUTier", "@id": f"{v}-tou-tier-off-peak", "urpx:tierSourceName": "Off-Peak",
         "urpx:touTierStandardName": ref("urpx:offPeakTier"), "urpx:touTierNumber": 2,
         "urpx:hasTOUPeriod": [off_peak("summer", 2), off_peak("winter", 4)]},
        {"@type": "urpx:TOUTier", "@id": f"{v}-tou-tier-super-off-peak", "urpx:tierSourceName": "Super Off-Peak",
         "urpx:touTierStandardName": ref("urpx:superOffPeakTier"), "urpx:touTierNumber": 3,
         "urpx:hasTOUPeriod": [super_off_peak("summer", 5), super_off_peak("winter", 6)]},
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
    for slug, num, label, val in ENERGY:
        energy_pds.append({"@type": "urpx:PriceDefinition", "@id": f"{v}-pd-energy-charge-{slug}",
                           "urpx:name": f"Time-of-Use Energy Charge, {label} (Schedule 327)",
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
                "urpx:name": "Basic Charge, single phase (Schedule 327)",
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
            "@type": "urpx:DataSourceReference", "urpx:fileName": "elec_sch_327.pdf",
            "urpx:mediaType": ref("urpx:applicationPdf"), "urpx:accessURL": PSE + "elec_sch_327.pdf",
            "urpx:dateRetrieved": RETRIEVED, "urpx:dataSourceType": ref("urpx:utilityWebsiteSource"),
            "urpx:pageStart": 1, "urpx:pageEnd": 4, "urpx:leafStart": "327", "urpx:leafEnd": "327-C"},
        "urpx:hasEligibilityRule": [{
            "@type": "urpx:EligibilityRule", "@id": f"{v}-er-residential",
            "urpx:name": "Eligibility for Schedule 327 Residential Service Time-of-Use with Super Off-Peak",
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
                    ledger("energy", "Time-of-Use Energy Charge (Schedule 327)"),
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
        "urpx:forRatePlan": ref("pse:327"),
        "urpx:hasCoverageClaim": {
            "@id": f"pse:cc-327-{date}", "@type": "urpx:CoverageClaim",
            "urpx:completenessResult": ref("urpx:partial"), "urpx:selfContained": True,
            "urpx:explainedBy": {"@type": "urpx:Evaluation", "@id": f"pse:cc-327-{date}-evaluation",
                                 "urpx:evaluationKind": ref("urpx:coverageEvaluation"),
                                 "urpx:description": "This filing does not carry everything its source document states. 0 parts are deferred, listed here in the same words as the filing's tariff.toml [modeling].deferrals so the two records cannot drift.",
                                 "urpx:evaluatedOn": "2026-10-05T00:00:00"}},
    })

    ctx = json.load(open(REPO / "us/wa/pse/electricity/307/versions/2026-10-01/rate-plan_pse_307_2026-10-01.jsonld"))["@context"]
    return {
        "@context": ctx,
        "@type": "urpx:URPXPackage",
        "@id": f"pse:doc-327-{date}",
        "urpx:targetURPXVersion": "https://github.com/urpx-org/urpx/raw/v0.5.1/ontology/urpx-ontology.ttl",
        "urpx:hasRatePlan": {
            "@type": "urpx:RatePlan", "@id": "pse:327",
            "urpx:name": "Residential Service Time-of-Use with Super Off-Peak",
            "urpx:ratePlanUniqueIdentifier": "327",
            "urpx:initialEffectiveDate": "2023-10-01",
            "urpx:timezoneIdentifier": "America/Los_Angeles",
            "urpx:hasRatePlanVersion": version}}


ELIGIBILITY = (
    "Sheet 327, AVAILABILITY: available to a Customer eligible for Schedule 7 Residential Service where PSE "
    "determines that adequate metering is available, on or after October 1, 2023; participation is limited to "
    "2,500 Customer accounts; PSE may limit participation for study purposes; a Customer taking optional "
    "Schedule 171 service is not eligible. ENROLLMENT: the Customer must complete PSE's enrollment process. "
    "Schedule 7 limits residential service to service delivered through one meter to a single-family unit and "
    "used principally for domestic purposes, including an adult family home. The condition expression tests "
    "only that the customer is residential.")

COMMON = (
    "Puget Sound Energy's optional residential time-of-use schedule with a super off-peak period, WN U-60 "
    "Electric Tariff G Schedule 327, sheets 327 through 327-C (327, 327-A and 327-B issued September 22, 2025 "
    "under Advice No. 2025-39, effective December 12, 2025, Docket UE-250725). It is a schedule in its own right "
    "rather than a rider on Schedule 7 or Schedule 307: it prices its own Basic Charge and a three-period "
    "time-of-use Energy Charge, and a Customer leaves it by changing to Schedule 7. The Energy Charge here is the "
    "sheet 327-A column headed 'Beginning January 29, 2026'. Winter is October 1 through March 31 and Summer April 1 "
    "through September 30; in both, Peak is 7am-10am and 5pm-8pm on weekdays and Off-Peak is 10am-5pm and 8pm-11pm "
    "on weekdays and 7am-11pm on weekends and the eleven legal holidays sheet 327-B lists. Super Off-Peak is "
    "11pm-7am every day of the year at one price. Each supplemental schedule that prices Schedule 327 per kWh is "
    "carried as its own Price with the rate that schedule states for Schedule 327, and each PriceDefinition cites "
    "the schedule and sheet. ")

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
        d = REPO / f"us/wa/pse/electricity/327/versions/{date}"
        d.mkdir(parents=True, exist_ok=True)
        out = d / f"rate-plan_pse_327_{date}.jsonld"
        prev = None
        if out.exists():
            prev = json.load(open(out))
        doc = build(date, exp)
        if prev:  # keep a resynced evaluation
            pv = prev["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]["urpx:hasCoverageClaim"]["urpx:explainedBy"]["urpx:description"]
            doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]["urpx:hasCoverageClaim"]["urpx:explainedBy"]["urpx:description"] = pv
        out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        print("wrote", out)
