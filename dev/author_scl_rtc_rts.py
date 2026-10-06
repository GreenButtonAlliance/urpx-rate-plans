#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""One-off: author us/wa/scl/electricity/{rtc,rts}/versions/{2026,2027,2028}-01-01/.

Takes the repository root and a directory holding Ordinance 127473 as fetched
(Ord_127473.pdf). Writes each filing's JSON-LD, tariff.toml and README.md, and
copies the ordinance in as the source PDF. Run once, then
dev/resync_coverage_evaluations.py, which owns each CoverageClaim Evaluation's
text; a re-run keeps the Evaluation already on disk.

    python3 dev/author_scl_rtc_rts.py . <download-dir>
"""
import datetime as dt
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO = Path(sys.argv[1])
SRC = Path(sys.argv[2]) if len(sys.argv) > 2 else None
RETRIEVED = "2026-10-05"
ORD_URL = "https://clerk.seattle.gov/~archives/Ordinances/Ord_127473.pdf"
SMC_URL = ("https://library.municode.com/wa/seattle/codes/municipal_code"
           "?nodeId=TIT21UT_SUBTITLE_IVLIPO_CH21.49SELIDE")
TOU_URL = "https://www.seattle.gov/city-light/residential-services/billing-information/time-of-use"
LAST_DATED_YEAR = 2040

# SMC 21.49.030.B as amended by Ordinance 127473, ordinance page 11. Cents per
# meter per day (base) and cents per kWh (energy), bound to the columns headed
# "Effective January 1, 2026", "Effective January 1, 2027" and "Effective
# January 1, 2028"; the struck 2024 and 2025 columns are not read.
RATES = {
    "rtc": {"2026-01-01": ("39.45", "8.05", "14.09", "16.10"),
            "2027-01-01": ("55.18", "8.45", "14.79", "16.90"),
            "2028-01-01": ("77.22", "8.69", "15.21", "17.38")},
    "rts": {"2026-01-01": ("39.45", "8.16", "14.28", "16.32"),
            "2027-01-01": ("55.18", "8.51", "14.89", "17.02"),
            "2028-01-01": ("77.22", "8.93", "15.63", "17.86")},
}
NEXT = {"2026-01-01": "2027-01-01", "2027-01-01": "2028-01-01", "2028-01-01": None}
PLAN = {
    "rtc": {"code": "RTC", "name": "Residential: City Time-of-Use", "where": "inside the City of Seattle"},
    "rts": {"code": "RTS", "name": "Residential: Suburban Time-of-Use",
            "where": "in the suburban jurisdictions City Light serves"},
}
MON_SAT = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
FIXED = [("new-years-day", "New Year's Day", 1, 1), ("independence-day", "Independence Day", 7, 4),
         ("christmas-day", "Christmas Day", 12, 25)]


def ref(i):
    return {"@id": i}


def dollars(cents):
    """Cents as written in the ordinance, to dollars, exactly."""
    whole, _, frac = cents.partition(".")
    n = int(whole) * 100 + int(frac.ljust(2, "0"))
    return f"{n // 10000}.{n % 10000:04d}"


def observed_mondays(first_year):
    out = []
    for y in range(first_year, LAST_DATED_YEAR + 1):
        for slug, name, m, d in FIXED:
            day = dt.date(y, m, d)
            if day.weekday() == 6:
                out.append((slug, name, day + dt.timedelta(days=1)))
    return sorted(out, key=lambda x: x[2])


def description(sched, date):
    p = PLAN[sched]
    base, off, mid, peak = RATES[sched][date]
    year = date[:4]
    text = (
        f"Seattle City Light Schedule {p['code']} ({p['name']}), the optional residential time-of-use "
        f"schedule for customers {p['where']}, Seattle Municipal Code 21.49.030.B as amended by "
        "Ordinance 127473 (Council Bill 121231, passed July 21, 2026, approved July 22, 2026). "
        f"This version carries the column headed 'Effective January 1, {year}': Base Service Charge "
        f"{base} cents per meter per day; Energy Off-Peak {off}, Mid-Peak {mid} and Peak {peak} cents per kWh. "
        "Off-Peak is 12 a.m. to 6 a.m. every day; Mid-Peak is 6 a.m. to 5 p.m. and 9 p.m. to 12 a.m. "
        "Mondays through Saturdays and 6 a.m. to 12 a.m. on Sundays and holidays; Peak is 5 p.m. to "
        "9 p.m. Mondays through Saturdays, other than on a holiday. There are no seasons and no blocks. "
        "The Monday-through-Saturday and Sunday brackets name their days with urpx:daysOfWeek, "
        "proposed in urpx-org/urpx#71 and in no URPX release yet."
    )
    if date == "2026-01-01":
        text += (" The 2026 column was enacted by Ordinance 127122 and is restated unchanged by "
                 "Ordinance 127473; City Light opened enrollment in the schedule on May 4, 2026.")
    if NEXT[date]:
        text += f" Superseded on {NEXT[date]} by the ordinance's next column."
    return text


ELIGIBILITY = (
    "SMC 21.49.030.B as amended by Ordinance 127473: Schedules RTC and RTS are optional rate schedules "
    "available to customers who meet eligibility requirements outlined in City Light's Department Policy "
    "and Procedure (DPP) 500 P III-434, as amended, or successor rule. Customers may return to their "
    "default rate schedule but will not be able to re-enroll in Schedule RTC or RTS until 12 months from "
    "the time of unenrollment. City Light's residential Time of Use page requires an advanced meter and a "
    "Utility Services Website profile, and does not offer the rate to net metering customers. "
    "21.49.030.C limits normal residential service to single-phase. The condition expression tests only "
    "that the customer is residential.")


def build(sched, date):
    p = PLAN[sched]
    base, off, mid, peak = RATES[sched][date]
    v = f"scl:{sched}-{date}"
    pe = f"{v}-plan-elements"
    mi_e, mi_m = f"{v}-mi-energy", f"{v}-mi-meter-count"
    led_e, led_b = f"{v}-ledger-energy-charge", f"{v}-ledger-base-service-charge"

    def bracket(name, start, end, day, days=None, holidays=None, non_holidays=None):
        b = {"@type": "urpx:TimeBracket", "@id": f"{v}-time-bracket-{name}",
             "urpx:startTime": start, "urpx:endTime": end, "urpx:dayType": ref(f"urpx:{day}")}
        if days:
            b["urpx:daysOfWeek"] = [ref(f"urpx:{d}") for d in days]
        if holidays is not None:
            b["urpx:includeHolidays"] = holidays
        if non_holidays is not None:
            b["urpx:includeNonHolidays"] = non_holidays
        return b

    def tier(slug, source, std, num, label, brackets):
        return {"@type": "urpx:TOUTier", "@id": f"{v}-tou-tier-{slug}", "urpx:tierSourceName": source,
                "urpx:touTierStandardName": ref(f"urpx:{std}"), "urpx:touTierNumber": num,
                "urpx:hasTOUPeriod": [{"@type": "urpx:TOUPeriod", "@id": f"{v}-tou-period-{slug}",
                                       "urpx:name": label, "urpx:touPeriodNumber": num,
                                       "urpx:hasTimeBracket": brackets}]}

    # Every instant falls in exactly one bracket. A holiday is told apart from
    # the day it falls on by the holiday flags: the Monday-through-Saturday
    # brackets exclude holidays, and one all-days bracket admitting only
    # holidays prices them as Sunday is priced.
    tiers = [
        tier("peak", "Energy Peak", "peakTier", 1,
             "Peak (5pm-9pm Mondays through Saturdays, not on a holiday)", [
                 bracket("peak-mon-sat", "17:00:00", "21:00:00", "customDays", MON_SAT, holidays=False)]),
        tier("mid-peak", "Energy Mid-Peak", "midPeakTier", 2,
             "Mid-Peak (6am-5pm and 9pm-12am Mondays through Saturdays; 6am-12am Sundays and holidays)", [
                 bracket("mid-peak-mon-sat-day", "06:00:00", "17:00:00", "customDays", MON_SAT, holidays=False),
                 bracket("mid-peak-mon-sat-late", "21:00:00", "00:00:00", "customDays", MON_SAT, holidays=False),
                 bracket("mid-peak-sunday", "06:00:00", "00:00:00", "customDays", ["sunday"], holidays=False),
                 bracket("mid-peak-holiday", "06:00:00", "00:00:00", "allDays", holidays=True, non_holidays=False)]),
        tier("off-peak", "Energy Off-Peak", "offPeakTier", 3, "Off-Peak (12am-6am every day)", [
            bracket("off-peak-every-day", "00:00:00", "06:00:00", "allDays")]),
    ]

    def holiday(slug, name, rule=None, date_=None):
        h = {"@type": "urpx:Holiday", "@id": f"{v}-holiday-{slug}", "urpx:holidayName": name}
        if rule:
            h["urpx:holidayRule"] = rule
        if date_:
            h["urpx:holidayDate"] = {"@value": date_, "@type": "xsd:date"}
        return h

    holidays = [
        holiday("new-years-day", "New Year's Day", "January 1"),
        holiday("memorial-day", "Memorial Day", "Last Monday in May"),
        holiday("independence-day", "Independence Day", "July 4"),
        holiday("labor-day", "Labor Day", "First Monday in September"),
        holiday("thanksgiving-day", "Thanksgiving Day", "Fourth Thursday in November"),
        holiday("christmas-day", "Christmas Day", "December 25"),
    ] + [holiday(f"{slug}-{d.isoformat()}", f"{name} (observed)", date_=d.isoformat())
         for slug, name, d in observed_mondays(int(date[:4]))]

    energy_pds, energy_prices = [], []
    for slug, num, label, cents in (("peak", 1, "Peak", peak), ("mid-peak", 2, "Mid-Peak", mid),
                                    ("off-peak", 3, "Off-Peak", off)):
        energy_pds.append({"@type": "urpx:PriceDefinition", "@id": f"{v}-pd-energy-charge-{slug}",
                           "urpx:name": f"Energy Charge, {label} (Schedule {p['code']})",
                           "urpx:chargeType": ref("urpx:usageCharge"),
                           "urpx:chargeCategory": ref("urpx:auxiliaryCharge"),
                           "urpx:billPortion": ref("urpx:bundledPortion"), "urpx:touPeriodNumber": num,
                           "urpx:referencesLedger": ref(led_e)})
        energy_prices.append({"@type": "urpx:Price", "@id": f"{v}-price-energy-charge-{slug}",
                              "urpx:referencesPriceDefinition": ref(f"{v}-pd-energy-charge-{slug}"),
                              "urpx:name": f"Energy {label}", "urpx:unitPrice": dollars(cents)})

    base_pd = {"@type": "urpx:PriceDefinition", "@id": f"{v}-pd-base-service-charge",
               "urpx:name": f"Base Service Charge, per meter per day (Schedule {p['code']})",
               "urpx:chargeType": ref("urpx:customerCharge"), "urpx:chargeCategory": ref("urpx:serviceCharge"),
               "urpx:billPortion": ref("urpx:bundledPortion"), "urpx:baseQuantity": "1",
               "urpx:hasCalculationMethod": {"@type": "urpx:CalculationMethod",
                                             "@id": f"{v}-pd-base-service-charge-calculation-method",
                                             "urpx:intervalDuration": "P1D"},
               "urpx:referencesLedger": ref(led_b)}

    version = {
        "@type": "urpx:RatePlanVersion",
        "@id": v,
        "urpx:description": description(sched, date),
        "urpx:effectiveDateTime": f"{date}T00:00:00",
    }
    if NEXT[date]:
        version["urpx:expirationDateTime"] = f"{NEXT[date]}T00:00:00"
    version.update({
        "urpx:changeReason": ref("urpx:rateCase"),
        "urpx:priceCurrency": "USD",
        "urpx:commodity": ref("urpx:electricity"),
        "urpx:serviceRole": ref("urpx:bundledServiceRole"),
        "urpx:customerChoice": ref("urpx:voluntaryChoice"),
        "urpx:isDefault": False,
        "urpx:hasDataSourceReference": {
            "@type": "urpx:DataSourceReference", "urpx:fileName": "Ord_127473.pdf",
            "urpx:mediaType": ref("urpx:applicationPdf"), "urpx:accessURL": ORD_URL,
            "urpx:dateRetrieved": RETRIEVED, "urpx:dataSourceType": ref("urpx:regulatoryWebsiteSource"),
            "urpx:pageStart": 10, "urpx:pageEnd": 12},
        "urpx:hasEligibilityRule": [{
            "@type": "urpx:EligibilityRule", "@id": f"{v}-er-residential",
            "urpx:name": f"Eligibility for Schedule {p['code']} ({p['name']})",
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
            "urpx:hasHolidayCalendar": {"@type": "urpx:HolidayCalendar", "@id": f"{v}-holidays",
                                        "urpx:hasHoliday": holidays},
            "urpx:hasMetricInput": [
                {"@type": "urpx:MetricInput", "@id": mi_e, "urpx:name": "kWh Energy Consumption Prices",
                 "urpx:metricInputType": ref("urpx:measuredMetricInput"),
                 "urpx:hasMetricSpecification": {"@type": "urpx:MetricSpecification", "@id": "scl:ms-energy",
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
                    {"@type": "urpx:Ledger", "@id": led_e, "urpx:name": f"Time-of-Use Energy Charge (Schedule {p['code']})",
                     "urpx:ledgerType": ref("urpx:bundledLedger"), "urpx:referencesMetricInput": ref(mi_e)},
                    {"@type": "urpx:Ledger", "@id": led_b, "urpx:name": "Base Service Charge",
                     "urpx:ledgerType": ref("urpx:bundledLedger"), "urpx:referencesMetricInput": ref(mi_m)}],
                "urpx:hasPriceDefinition": energy_pds + [base_pd]}},
        "urpx:hasPrices": {
            "@type": "urpx:Prices", "@id": f"{v}-prices",
            "urpx:hasPrice": [{"@type": "urpx:Price", "@id": f"{v}-price-base-service-charge",
                               "urpx:referencesPriceDefinition": ref(f"{v}-pd-base-service-charge"),
                               "urpx:startDate": date, "urpx:name": "Base Service Charge",
                               "urpx:unitPrice": dollars(base)}],
            "urpx:hasPriceSet": [
                {"@type": "urpx:PriceSet", "@id": f"{v}-ps-energy-charge", "urpx:startDate": date,
                 "urpx:hasPrice": energy_prices}]},
        "urpx:offeredBy": {
            "@type": "urpx:UtilityOperator", "@id": "org:utility-scl", "urpx:legalName": "Seattle City Light",
            "urpx:organizationType": ref("urpx:utilityOrganization"),
            "urpx:hasIdentity": {"@id": "org:utility-scl-identity", "@type": "urpx:OrganizationIdentity",
                                 "urpx:hasName": {"@id": "org:utility-scl-name", "@type": "urpx:OrganizationName",
                                                  "urpx:name": "Seattle City Light"},
                                 "urpx:hasIdentifier": {"@id": "org:utility-scl-eia", "@type": "urpx:OrganizationIdentifier",
                                                        "urpx:scheme": ref("urpx:eiaScheme"), "skos:notation": "16868"}}},
        "urpx:forRatePlan": ref(f"scl:{sched}"),
        "urpx:hasCoverageClaim": {
            "@id": f"scl:cc-{sched}-{date}", "@type": "urpx:CoverageClaim",
            "urpx:completenessResult": ref("urpx:partial"), "urpx:selfContained": True,
            "urpx:explainedBy": {"@type": "urpx:Evaluation", "@id": f"scl:cc-{sched}-{date}-evaluation",
                                 "urpx:evaluationKind": ref("urpx:coverageEvaluation"),
                                 "urpx:description": "This filing does not carry everything its source document states. 0 parts are deferred, listed here in the same words as the filing's tariff.toml [modeling].deferrals so the two records cannot drift.",
                                 "urpx:evaluatedOn": f"{RETRIEVED}T00:00:00"}},
    })

    pse = json.load(open(REPO / "us/wa/pse/electricity/307/versions/2026-10-01/rate-plan_pse_307_2026-10-01.jsonld"))
    ctx = {("scl" if k == "pse" else k): (val.replace("/pse/", "/scl/") if k == "pse" else val)
           for k, val in pse["@context"].items()}
    return {
        "@context": ctx,
        "@type": "urpx:URPXPackage",
        "@id": f"scl:doc-{sched}-{date}",
        "urpx:targetURPXVersion": "https://github.com/urpx-org/urpx/raw/v0.5.1/ontology/urpx-ontology.ttl",
        "urpx:hasRatePlan": {
            "@type": "urpx:RatePlan", "@id": f"scl:{sched}",
            "urpx:name": p["name"],
            "urpx:ratePlanUniqueIdentifier": p["code"],
            "urpx:initialEffectiveDate": "2024-01-01",
            "urpx:timezoneIdentifier": "America/Los_Angeles",
            "urpx:hasRatePlanVersion": version}}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


UNRELEASED = """
## Unreleased vocabulary: urpx:daysOfWeek (urpx-org/urpx#71)

This filing uses urpx:daysOfWeek, proposed in urpx-org/urpx#71
(https://github.com/urpx-org/urpx/pull/71) and in no URPX release. Its
Monday-through-Saturday and Sunday brackets carry urpx:dayType
urpx:customDays with urpx:daysOfWeek naming the days. It does not validate
against the v0.5.1 SHACL on that property: TimeBracketShape is sh:closed and
does not admit it, so pyshacl reports one sh:ClosedConstraintComponent result
per such bracket and listed day. dev/validate-with-base.py excepts exactly those results
(DAYS_OF_WEEK_EXCEPTION), and every other result still fails. If #71 does not
merge in this form, these brackets have to be remodeled.
"""


def notes(sched, date):
    p = PLAN[sched]
    year = date[:4]
    out = f"""
Read from Ordinance 127473 (Council Bill 121231), which amends SMC 21.49.030.
The Schedule {p['code']} table is on ordinance page 11 and the period
definitions on pages 11 and 12. Read from the page rendered as an image as
well as from pdftotext -layout, because the ordinance carries legislative
markup: the 2024 and 2025 columns are struck ((...)) and the 2027 and 2028
columns are underlined additions, so a value is bound to its year by its
column header, not by its position after markup is stripped. This filing
carries the column headed "Effective January 1, {year}".
{UNRELEASED}
## Structure

Schedules RTC and RTS are each a RatePlan of their own: each has its own rate
table in SMC 21.49.030.B, its own Base Service Charge and its own energy
charges. RTS differs from RTC only in its energy charges; the franchise and
tax multipliers and the Shoreline and Burien undergrounding charges that
21.49.030.B applies "to Schedule RTS as Schedule RSS" are not carried (see
[modeling].deferrals).

The schedule has no seasons and no blocks. The six TimeBrackets do not
overlap and together cover every hour: Off-Peak, allDays 00:00-06:00; Peak, customDays Monday through
Saturday 17:00-21:00 excluding holidays; Mid-Peak, customDays Monday through
Saturday 06:00-17:00 and 21:00-24:00 excluding holidays, customDays Sunday
06:00-24:00 excluding holidays, and allDays 06:00-24:00 on holidays only.

## Holidays

SMC 21.49.030.B names "holidays" without listing them. City Light's
residential Time of Use page ({TOU_URL},
retrieved {RETRIEVED}) states which and how they are observed: "City light
observes holidays defined by the North American Electric Reliability
Corporation (NERC)": New Year's Day, Memorial Day, Independence Day, Labor
Day, Thanksgiving Day, Christmas Day. "If any of these fall on a Sunday, the
NERC holiday is observed on the following Monday. If they fall on a Saturday,
the holiday remains on that Saturday." Per LAYOUT.md section 4.4 that stated
rule governs rather than RCW 1.16.050. New Year's Day, Independence Day and
Christmas Day carry no urpx:observanceRule, so each resolves on its actual
date and a Saturday one stays on Saturday; the Monday after each that falls
on a Sunday is carried as a dated urpx:Holiday through {LAST_DATED_YEAR}. The
other three always fall on a Monday or Thursday.
"""
    if date == "2026-01-01":
        out += """
## Dating

Dated 2026-01-01, the effective date the ordinance prints on the column this
filing carries. That column was enacted by Ordinance 127122 (Council Bill
120856, approved November 26, 2024), whose RTC and RTS tables carry the same
2026 values, and Ordinance 127473 restates it unchanged. Ordinance 127473
also replaced the eligibility text, effective as provided by SMC 1.04.020
and 1.04.070 after its July 22, 2026 approval; the eligibility rule here
carries the replaced text. Enrollment opened on May 4, 2026, as reported at
https://www.chronline.com/stories/seattle-city-light-launches-new-time-of-use-electricity-rate,402991
(May 24, 2026). Bounded at 2027-01-01 by the next column.
"""
    else:
        nxt = NEXT[date]
        out += f"""
## Dating

Dated {date}, the effective date the ordinance prints on the column this
filing carries. Ordinance 127473 enacts it: the column is an underlined
addition, and the ordinance takes effect as provided by SMC 1.04.020 and
1.04.070 after its July 22, 2026 approval. {"Bounded at " + nxt + " by the next column." if nxt else "It is the last column the ordinance enacts."}
"""
    out += """
## Initial effective date

urpx:initialEffectiveDate is 2024-01-01. Ordinance 126677 (Council Bill
120411) added Schedules RTC and RTS to SMC 21.49.030 as "Time-of-Day" rates,
with a single column headed "Effective January 1, 2024"; Ordinance 127122
renamed them "Time-of-Use".
"""
    return out


def deferrals(sched, date):
    first = int(date[:4])
    obs = ", ".join(d.isoformat() for _s, _n, d in observed_mondays(first))
    out = [
        "City Light's residential Time of Use page: a NERC holiday that falls on a Sunday \"is observed on the "
        "following Monday\"; one on a Saturday \"remains on that Saturday\". New Year's Day, Independence Day "
        f"and Christmas Day in scl:{sched}-{date}-holidays carry no urpx:observanceRule, so each resolves on its "
        "actual date and a Saturday one stays on Saturday. The Monday after a Sunday New Year's Day, "
        f"Independence Day or Christmas Day is carried as a dated urpx:Holiday with urpx:holidayDate: {obs}. "
        f"After {LAST_DATED_YEAR} each such Sunday holiday needs a further dated entry, until "
        "urpx:mondayIfSundayObservance (proposed in urpx-org/urpx#77) can state the rule; the dated entries then come out.",
    ]
    if sched == "rts":
        out.append(
            "SMC 21.49.030.B: \"The same franchise and tax multipliers and suburban undergrounding charges apply "
            "to Schedule RTS as Schedule RSS.\" Not carried. The RSS multipliers increase all charges by "
            "location of service (in the column this filing carries: Burien, King County, SeaTac and Shoreline "
            + {"2026-01-01": "8.00%; Tukwila 7.19%; Lake Forest Park 8.04%; Normandy Park 6.38%",
               "2027-01-01": "8.00%; Tukwila 7.05%; Lake Forest Park 8.04%; Normandy Park 6.38%",
               "2028-01-01": "8.00%; Tukwila 7.07%; Lake Forest Park 8.04%; Normandy Park 6.38%"}[date]
            + "), and per-kWh undergrounding charges of 0.05 to 0.37 cents apply in parts of Shoreline and "
            "Burien. Every charge here is the unmultiplied rate, which is what a customer in a jurisdiction "
            "with no multiplier, such as Renton, pays.")
    return out


README = """# SCL Schedule {code} ({name}), {date}

Seattle City Light's optional residential time-of-use schedule for customers {where}, Seattle Municipal Code 21.49.030.B as amended by Ordinance 127473. This version carries the ordinance column headed "Effective January 1, {year}".

**This filing uses `urpx:daysOfWeek`, proposed in [urpx-org/urpx#71](https://github.com/urpx-org/urpx/pull/71) and not in any URPX release. It does not validate against the v0.5.1 SHACL on that property**: `TimeBracketShape` is closed, so each bracket carrying `urpx:daysOfWeek` fails it. `dev/validate-with-base.py` excepts exactly those results under `DAYS_OF_WEEK_EXCEPTION`. The pinned clj-urpx resolves `urpx:customDays` on every day, so this filing is withheld from the marginal-rate baseline and the scenario cost models until clj-urpx 0.39.0 (`dev/withheld-filings.json`).

## Files

- `scl_{sched}_{date}.pdf`: Ordinance 127473 as `Ord_127473.pdf` on clerk.seattle.gov. Schedule {code} is on page 11.
- `tariff.toml`: provenance, how the columns were read, holiday handling, deferrals.
- `rate-plan_scl_{sched}_{date}.jsonld`: the URPX serialization.

## Rates

| Line | Ordinance | Carried |
| --- | --- | --- |
| Base Service Charge | {base} cents per meter per day | ${base_d} per day |
| Energy Peak (5-9pm Mon-Sat, not holidays) | {peak} cents per kWh | ${peak_d} per kWh |
| Energy Mid-Peak (6am-5pm and 9pm-12am Mon-Sat; 6am-12am Sundays and holidays) | {mid} cents per kWh | ${mid_d} per kWh |
| Energy Off-Peak (12am-6am every day) | {off} cents per kWh | ${off_d} per kWh |

Holidays are the six NERC holidays City Light names: New Year's Day, Memorial Day, Independence Day, Labor Day, Thanksgiving Day and Christmas Day. One falling on a Sunday is observed the following Monday; one falling on a Saturday stays on Saturday.
"""


def write_manifest(sched, date, pdf):
    p = PLAN[sched]
    lines = [
        "# Identity --------------------------------------------------------------------",
        'utility = "scl"', f'schedule = "{sched}"', f'effective_date = "{date}"', "",
        "# This filing uses urpx:daysOfWeek, proposed in urpx-org/urpx#71 and in no URPX",
        "# release. It does not validate against the v0.5.1 SHACL on that property. See",
        "# [extraction].notes and README.md.",
        "",
        "# Source ----------------------------------------------------------------------",
        "[source]", f"url = {q(ORD_URL)}", f'sha256 = "{sha(pdf)}"', f'retrieved_on = "{RETRIEVED}"',
        'media_type = "application/pdf"', 'filing_type = "ordinance"', 'filing_id = "Ordinance 127473"',
        f"landing_page = {q(SMC_URL)}", "",
        "# Regulatory ------------------------------------------------------------------",
        "[regulator]", 'authority = "city-council"', 'docket = "Council Bill 121231"', "",
        "# Extraction ------------------------------------------------------------------",
        "[extraction]", 'tool = "pdftotext"', 'tool_version = "26.09.0"', f'extracted_on = "{RETRIEVED}"',
        'notes = """' + notes(sched, date) + '"""', "",
        "# Validation ------------------------------------------------------------------",
        "# shacl_passed is false: against the v0.5.1 shapes every bracket carrying",
        "# urpx:daysOfWeek fails TimeBracketShape's sh:closed (urpx-org/urpx#71).",
        "[validation]", "shacl_passed = false", 'validator = "pyshacl (URPX v0.5.1) + clj-urpx"',
        f'validated_on = "{RETRIEVED}"', "",
        "# Modeling --------------------------------------------------------------------",
        "[modeling]", "complete = false", "deferrals = ["]
    for x in deferrals(sched, date):
        lines.append(" " + q(x) + ",")
    lines += ["]", "applicable_modifiers = []", "",
              "# Review ----------------------------------------------------------------------",
              "[review]", 'status = "draft"',
              'notes = "Uses urpx:daysOfWeek from urpx-org/urpx#71, which is in no URPX release."', ""]
    return "\n".join(lines)


if __name__ == "__main__":
    for sched in ("rtc", "rts"):
        for date in ("2026-01-01", "2027-01-01", "2028-01-01"):
            d = REPO / f"us/wa/scl/electricity/{sched}/versions/{date}"
            d.mkdir(parents=True, exist_ok=True)
            pdf = d / f"scl_{sched}_{date}.pdf"
            if SRC:
                shutil.copyfile(SRC / "Ord_127473.pdf", pdf)
            out = d / f"rate-plan_scl_{sched}_{date}.jsonld"
            doc = build(sched, date)
            if out.exists():  # keep a resynced evaluation
                prev = json.load(open(out))
                pv = prev["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]["urpx:hasCoverageClaim"]["urpx:explainedBy"]["urpx:description"]
                doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]["urpx:hasCoverageClaim"]["urpx:explainedBy"]["urpx:description"] = pv
            out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
            (d / "tariff.toml").write_text(write_manifest(sched, date, pdf))
            base, off, mid, peak = RATES[sched][date]
            (d / "README.md").write_text(README.format(
                code=PLAN[sched]["code"], name=PLAN[sched]["name"], where=PLAN[sched]["where"], date=date,
                year=date[:4], sched=sched, base=base, off=off, mid=mid, peak=peak, base_d=dollars(base),
                off_d=dollars(off), mid_d=dollars(mid), peak_d=dollars(peak)))
            print("wrote", d)
