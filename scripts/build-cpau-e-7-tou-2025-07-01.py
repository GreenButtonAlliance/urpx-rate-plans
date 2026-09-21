#!/usr/bin/env python3
"""
Build ca/pou/cpau/e-7-tou/versions/2025-07-01/rate-plan_cpau_e-7-tou_2025-07-01.jsonld.

CPAU Schedule E-7 TOU: Large Non-Residential Electric Time of Use Service.
Voluntary opt-in TOU rate for demand-metered customers with maximum
demand at least 1000 kW per site sustained 3+ consecutive months.
Same structural shape as CPAU E-4 TOU — different rate values, different
eligibility threshold (1000+ kW vs 500–1000 kW), much higher customer
charge ($578.08 vs $126.24/mo).

Source PDF sha256 22084af89323d2924c4c1c67a6ab9676a46ea96009412384a62429cbfb7eff2d
retrieved from paloalto.gov 2026-04-30.

STRUCTURE (parallel to CPAU E-4 TOU):
- 2 seasons (Summer May–Oct, Winter Nov–Apr)
- 3 TOU periods for energy (Peak / Mid-Peak / Off-Peak) — windows
  identical to CPAU E-4 TOU and PG&E patterns
- 2 demand windows (Peak Demand within energy peak window + Max Demand
  at any time)
- Holiday-aware (US federal holidays — same set as PG&E E-TOU-D)
- 27 PriceDefinitions: 18 energy + 8 demand + 1 customer charge

NOTABLE DIFFERENCES from CPAU E-4 TOU:
- Eligibility: maximum demand >= 1000 kW per site, sustained 3+ months
  (vs 500–1000 kW for E-4 TOU)
- Customer charge $578.08/month (vs $126.24)
- Section D.6 Voltage Discount is 2.8% (E-4 TOU is 2.5%)
- Section D.7 Standby Charge: $40.79/kW summer, $27.75/kW winter
  (E-4 TOU: $46.58 / $23.49)
- Section D.3 site-aggregation: customers may bundle multiple Accounts
  under one Schedule if Accounts are on contiguous parcels with a common
  billing address. URPX has no native vocabulary; noted, not modeled.
- No TES carve-out (E-4 has TES; E-4 TOU does not; E-7 has TES; E-7 TOU
  does not — TES exception is on the non-TOU schedules only).

DEFERRED (existing follow-ups, broaden scope when modeled):
  - Section D.6 Primary Voltage Discount (2.8% for >2 kV) — the project tracker
  - Section D.7 Standby Charge — the project tracker
  - Section D.5 12-month minimum commitment — the project tracker (URPX has no
    native vocabulary for minimum-term commitments)
  - Section D.4 Demand Meter installation rule: operations, not a rate.

Per-component rates from Section C of the PDF:
  Summer:   commodity / distribution / public-benefits
    Demand Peak    : 11.39 / 16.33 / —      = 27.72 / kW
    Demand Max     :  1.46 / 16.33 / —      = 17.79 / kW
    Energy Peak    : 0.18199 / 0.00402 / 0.00604 = 0.19205 / kWh
    Energy Mid-Peak: 0.14999 / 0.00402 / 0.00604 = 0.16005 / kWh
    Energy Off-Peak: 0.11276 / 0.00402 / 0.00604 = 0.12282 / kWh
  Winter:
    Demand Peak    :  1.46 / 14.42 / —      = 15.88 / kW
    Demand Max     :  1.46 / 14.42 / —      = 15.88 / kW
    Energy Peak    : 0.12225 / 0.00393 / 0.00604 = 0.13222 / kWh
    Energy Mid-Peak: 0.09648 / 0.00393 / 0.00604 = 0.10645 / kWh
    Energy Off-Peak: 0.06660 / 0.00393 / 0.00604 = 0.07657 / kWh
  Customer Charge: 578.08 / month
"""
import json
from pathlib import Path

ROOT = Path(str(Path(__file__).resolve().parent.parent))
OUT = ROOT / "ca/pou/cpau/e-7-tou/versions/2025-07-01/rate-plan_cpau_e-7-tou_2025-07-01.jsonld"

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
    "urpx:startTime": {"@type": "xsd:time"},
    "urpx:endTime": {"@type": "xsd:time"},
    "urpx:includeHolidays": {"@type": "xsd:boolean"},
    "urpx:includeNonHolidays": {"@type": "xsd:boolean"},
    "urpx:touPeriodNumber": {"@type": "xsd:integer"},
    "urpx:touTierNumber": {"@type": "xsd:integer"},
    "urpx:decimalValue": {"@type": "xsd:decimal"},
    "urpx:integerValue": {"@type": "xsd:integer"},
    "cpau": "https://example.com/cpau/",
    "org": "https://example.com/organizations/",
}


# ============================================================================
# Helpers
# ============================================================================

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


def cn_gte_decimal(cn_id, custom_prop, decimal_val):
    return {
        "@type": "urpx:ComparisonNode", "@id": cn_id,
        "urpx:operator": {"@id": "urpx:greaterThanOrEqualOperator"},
        "urpx:leftOperand": {"@type": "urpx:CustomOperandNode", "urpx:customConditionProperty": custom_prop},
        "urpx:rightOperand": {"@type": "urpx:CustomOperandNode", "urpx:decimalValue": decimal_val},
    }


def cn_lte_decimal(cn_id, custom_prop, decimal_val):
    return {
        "@type": "urpx:ComparisonNode", "@id": cn_id,
        "urpx:operator": {"@id": "urpx:lessThanOrEqualOperator"},
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


def time_bracket(tb_id, season_id, day_type, start, end, *, include_holidays=None, include_non_holidays=None):
    tb = {
        "@type": "urpx:TimeBracket", "@id": tb_id,
        "urpx:startTime": start, "urpx:endTime": end,
        "urpx:appliesInSeason": {"@id": season_id},
        "urpx:dayType": {"@id": f"urpx:{day_type}"},
    }
    if include_holidays is not None: tb["urpx:includeHolidays"] = include_holidays
    if include_non_holidays is not None: tb["urpx:includeNonHolidays"] = include_non_holidays
    return tb


# ============================================================================
# Eligibility (Section A)
# ============================================================================
eligibility_rule = {
    "@type": "urpx:EligibilityRule",
    "@id": "cpau:e7tou-er-eligibility",
    "urpx:name": "Demand-metered, max demand at least 1000 kW sustained 3+ months",
    "urpx:description": (
        "Voluntary opt-in rate for large non-residential customers receiving "
        "Demand metered Electric Service whose maximum monthly demand is at "
        "least 1000 kW per site, sustained at that level for at least three "
        "consecutive months in the most recent 12-month period. Section A of "
        "the published Schedule E-7 TOU."
    ),
    "urpx:hasConditionExpression": expr(
        "cpau:e7tou-cx-eligibility",
        boolop("cpau:e7tou-bn-eligibility-and", "and", [
            cn_eq_str("cpau:e7tou-cn-demand-metered", "metering", "Demand metered"),
            cn_gte_decimal("cpau:e7tou-cn-demand-min-1000", "monthlyMaxDemand_kW", "1000"),
            cn_eq_str("cpau:e7tou-cn-sustained-3mo", "demandSustainedConsecutiveMonths", "3"),
        ], logic_expression=(
            "metering = 'Demand metered' AND monthlyMaxDemand_kW >= 1000 AND "
            "demandSustainedConsecutiveMonths = 3"
        )),
    ),
}

# ============================================================================
# Seasons
# ============================================================================
season_summer = {
    "@type": "urpx:Season", "@id": "cpau:e7tou-season-summer",
    "urpx:seasonName": "Summer", "urpx:yearlyRecurrence": True,
    "urpx:month": ["--05", "--06", "--07", "--08", "--09", "--10"],
}
season_winter = {
    "@type": "urpx:Season", "@id": "cpau:e7tou-season-winter",
    "urpx:seasonName": "Winter", "urpx:yearlyRecurrence": True,
    "urpx:month": ["--11", "--12", "--01", "--02", "--03", "--04"],
}

# ============================================================================
# HolidayCalendar — federal-holiday set commonly observed by CA utilities
# (matches PG&E E-TOU-D pattern). Inferred since the PDF says "holidays" without
# enumerating; CPAU follows the standard CA utility-holiday convention.
# ============================================================================
holiday_calendar = {
    "@type": "urpx:HolidayCalendar",
    "@id": "cpau:e7tou-holidays",
    "urpx:hasHoliday": [
        {"@type": "urpx:Holiday", "@id": "cpau:e7tou-holiday-new-years",
         "urpx:holidayName": "New Year's Day",   "urpx:holidayRule": "January 1 (legally observed)"},
        {"@type": "urpx:Holiday", "@id": "cpau:e7tou-holiday-presidents",
         "urpx:holidayName": "Presidents' Day",  "urpx:holidayRule": "Third Monday in February"},
        {"@type": "urpx:Holiday", "@id": "cpau:e7tou-holiday-memorial",
         "urpx:holidayName": "Memorial Day",     "urpx:holidayRule": "Last Monday in May"},
        {"@type": "urpx:Holiday", "@id": "cpau:e7tou-holiday-independence",
         "urpx:holidayName": "Independence Day", "urpx:holidayRule": "July 4 (legally observed)"},
        {"@type": "urpx:Holiday", "@id": "cpau:e7tou-holiday-labor",
         "urpx:holidayName": "Labor Day",        "urpx:holidayRule": "First Monday in September"},
        {"@type": "urpx:Holiday", "@id": "cpau:e7tou-holiday-veterans",
         "urpx:holidayName": "Veterans Day",     "urpx:holidayRule": "November 11 (legally observed)"},
        {"@type": "urpx:Holiday", "@id": "cpau:e7tou-holiday-thanksgiving",
         "urpx:holidayName": "Thanksgiving Day", "urpx:holidayRule": "Fourth Thursday in November"},
        {"@type": "urpx:Holiday", "@id": "cpau:e7tou-holiday-christmas",
         "urpx:holidayName": "Christmas Day",    "urpx:holidayRule": "December 25 (legally observed)"},
    ],
}

# ============================================================================
# MetricInputs
# ============================================================================
mi_energy = {
    "@type": "urpx:MetricInput", "@id": "cpau:e7tou-mi-energy",
    "urpx:name": "Energy consumed (kWh)",
    "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
    "urpx:hasMetricSpecification": {
        "@type": "urpx:MetricSpecification", "@id": "cpau:e7tou-ms-energy",
        "urpx:measurementKind": {"@id": "urpx:energy"},
        "urpx:unitOfMeasure": {"@id": "urpx:kWh"},
        "urpx:flowDirection": {"@id": "urpx:forward"},
    },
}
mi_demand = {
    "@type": "urpx:MetricInput", "@id": "cpau:e7tou-mi-demand",
    "urpx:name": "Demand (kW, 15-minute interval)",
    "urpx:metricInputType": {"@id": "urpx:measuredMetricInput"},
    "urpx:hasMetricSpecification": {
        "@type": "urpx:MetricSpecification", "@id": "cpau:e7tou-ms-demand",
        "urpx:measurementKind": {"@id": "urpx:demand"},
        "urpx:unitOfMeasure": {"@id": "urpx:kW"},
        "urpx:flowDirection": {"@id": "urpx:forward"},
        "urpx:intervalDuration": "PT15M",
        "urpx:intervalType": {"@id": "urpx:fifteenMinuteInterval"},
    },
}
mi_meter_count = {
    "@type": "urpx:MetricInput", "@id": "cpau:e7tou-mi-meter-count",
    "urpx:name": "Meter count",
    "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
    "urpx:profileMetricProperty": {"@id": "urpx:meterCount"},
}

# ============================================================================
# Ledgers
# ============================================================================
ledgers = [
    {"@type": "urpx:Ledger", "@id": "cpau:e7tou-ledger-energy-commodity",
     "urpx:name": "Energy — Commodity", "urpx:ledgerType": {"@id": "urpx:supplyLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e7tou-mi-energy"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e7tou-ledger-energy-distribution",
     "urpx:name": "Energy — Distribution", "urpx:ledgerType": {"@id": "urpx:distributionLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e7tou-mi-energy"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e7tou-ledger-energy-public-benefits",
     "urpx:name": "Energy — Public Benefits", "urpx:ledgerType": {"@id": "urpx:bundledLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e7tou-mi-energy"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e7tou-ledger-demand-commodity",
     "urpx:name": "Demand — Commodity", "urpx:ledgerType": {"@id": "urpx:supplyLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e7tou-mi-demand"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e7tou-ledger-demand-distribution",
     "urpx:name": "Demand — Distribution", "urpx:ledgerType": {"@id": "urpx:distributionLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e7tou-mi-demand"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e7tou-ledger-service",
     "urpx:name": "Customer (service) charge", "urpx:ledgerType": {"@id": "urpx:profileMetricLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e7tou-mi-meter-count"}},
]

# ============================================================================
# TOU Schedules — TWO separate schedules, one per metric input
# ============================================================================

# ---- Energy TOU schedule ---------------------------------------------------
# Summer:
#   Peak     : 16:00-21:00 weekday non-holiday
#   Mid-Peak : 14:00-16:00 + 21:00-23:00 weekday non-holiday
#   Off-Peak : everything else (incl. weekends and weekday holidays all-day)
# Winter:
#   Peak     : 16:00-21:00 weekday non-holiday
#   Mid-Peak : 09:00-14:00 weekday non-holiday
#   Off-Peak : everything else

def off_peak_brackets(prefix, season_id, peak_start, peak_end, midpeak_segments):
    """Build TimeBrackets for the off-peak period given peak + mid-peak windows.
    midpeak_segments is a list of (start, end) tuples covering the mid-peak times.
    Off-peak = everything not in peak or any mid-peak segment, plus all weekends
    plus all weekday holidays.
    Returns the full list of TimeBrackets that together cover off-peak."""
    # Compute the weekday-non-holiday off-peak gaps:
    # All non-peak/non-mid-peak hours on weekday non-holidays.
    busy = sorted([(peak_start, peak_end)] + list(midpeak_segments))
    gaps = []
    cursor = "00:00:00"
    for s, e in busy:
        if cursor < s:
            gaps.append((cursor, s))
        cursor = e
    if cursor < "24:00:00":
        # endTime "00:00:00" is the wraparound-to-midnight convention used by PG&E E-TOU-D
        gaps.append((cursor, "00:00:00"))
    brackets = []
    for i, (s, e) in enumerate(gaps):
        brackets.append(time_bracket(
            f"{prefix}-tb-weekday-{i+1}", season_id, "weekdayDays", s, e,
            include_holidays=False, include_non_holidays=True,
        ))
    # Weekday holidays — entire day is off-peak
    brackets.append(time_bracket(
        f"{prefix}-tb-weekday-holiday", season_id, "weekdayDays", "00:00:00", "00:00:00",
        include_holidays=True, include_non_holidays=False,
    ))
    # Weekends — entire day, both holiday and non-holiday
    brackets.append(time_bracket(
        f"{prefix}-tb-weekend", season_id, "weekendDays", "00:00:00", "00:00:00",
    ))
    return brackets


energy_periods = [
    # Summer Peak
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e7tou-energy-period-summer-peak",
     "urpx:name": "Summer Peak", "urpx:touPeriodNumber": 1,
     "urpx:hasTimeBracket": [time_bracket(
         "cpau:e7tou-energy-tb-summer-peak", "cpau:e7tou-season-summer",
         "weekdayDays", "16:00:00", "21:00:00",
         include_holidays=False, include_non_holidays=True,
     )]},
    # Summer Mid-Peak (TWO segments)
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e7tou-energy-period-summer-mid-peak",
     "urpx:name": "Summer Mid-Peak", "urpx:touPeriodNumber": 2,
     "urpx:hasTimeBracket": [
         time_bracket("cpau:e7tou-energy-tb-summer-mid-peak-afternoon",
                      "cpau:e7tou-season-summer", "weekdayDays", "14:00:00", "16:00:00",
                      include_holidays=False, include_non_holidays=True),
         time_bracket("cpau:e7tou-energy-tb-summer-mid-peak-evening",
                      "cpau:e7tou-season-summer", "weekdayDays", "21:00:00", "23:00:00",
                      include_holidays=False, include_non_holidays=True),
     ]},
    # Summer Off-Peak (gaps + weekends + weekday holidays)
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e7tou-energy-period-summer-off-peak",
     "urpx:name": "Summer Off-Peak", "urpx:touPeriodNumber": 3,
     "urpx:hasTimeBracket": off_peak_brackets(
         "cpau:e7tou-energy-summer-off-peak", "cpau:e7tou-season-summer",
         "16:00:00", "21:00:00",
         [("14:00:00", "16:00:00"), ("21:00:00", "23:00:00")],
     )},
    # Winter Peak
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e7tou-energy-period-winter-peak",
     "urpx:name": "Winter Peak", "urpx:touPeriodNumber": 4,
     "urpx:hasTimeBracket": [time_bracket(
         "cpau:e7tou-energy-tb-winter-peak", "cpau:e7tou-season-winter",
         "weekdayDays", "16:00:00", "21:00:00",
         include_holidays=False, include_non_holidays=True,
     )]},
    # Winter Mid-Peak (single segment 9-2)
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e7tou-energy-period-winter-mid-peak",
     "urpx:name": "Winter Mid-Peak", "urpx:touPeriodNumber": 5,
     "urpx:hasTimeBracket": [time_bracket(
         "cpau:e7tou-energy-tb-winter-mid-peak", "cpau:e7tou-season-winter",
         "weekdayDays", "09:00:00", "14:00:00",
         include_holidays=False, include_non_holidays=True,
     )]},
    # Winter Off-Peak
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e7tou-energy-period-winter-off-peak",
     "urpx:name": "Winter Off-Peak", "urpx:touPeriodNumber": 6,
     "urpx:hasTimeBracket": off_peak_brackets(
         "cpau:e7tou-energy-winter-off-peak", "cpau:e7tou-season-winter",
         "16:00:00", "21:00:00",
         [("09:00:00", "14:00:00")],
     )},
]

energy_tou_schedule = {
    "@type": "urpx:TOUSchedule", "@id": "cpau:e7tou-energy-tou-schedule",
    "urpx:name": "E-4 TOU Energy schedule",
    "urpx:referencesMetricInput": {"@id": "cpau:e7tou-mi-energy"},
    "urpx:hasCalendar": {"@id": "cpau:e7tou-holidays"},
    "urpx:hasTOUTier": [{
        "@type": "urpx:TOUTier", "@id": "cpau:e7tou-energy-tou-tier-1",
        "urpx:touTierNumber": 1,
        "urpx:hasTOUPeriod": energy_periods,
    }],
}

# ---- Demand TOU schedule ---------------------------------------------------
# Demand Peak    : 16:00-21:00 weekday non-holiday (same window as energy peak)
# Max Demand     : ALL HOURS every day (no time gating)

demand_periods = [
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e7tou-demand-period-summer-peak",
     "urpx:name": "Summer Demand Peak", "urpx:touPeriodNumber": 1,
     "urpx:hasTimeBracket": [time_bracket(
         "cpau:e7tou-demand-tb-summer-peak", "cpau:e7tou-season-summer",
         "weekdayDays", "16:00:00", "21:00:00",
         include_holidays=False, include_non_holidays=True,
     )]},
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e7tou-demand-period-summer-max",
     "urpx:name": "Summer Max Demand", "urpx:touPeriodNumber": 2,
     "urpx:hasTimeBracket": [time_bracket(
         "cpau:e7tou-demand-tb-summer-max", "cpau:e7tou-season-summer",
         "allDays", "00:00:00", "00:00:00",
         include_holidays=True, include_non_holidays=True,
     )]},
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e7tou-demand-period-winter-peak",
     "urpx:name": "Winter Demand Peak", "urpx:touPeriodNumber": 3,
     "urpx:hasTimeBracket": [time_bracket(
         "cpau:e7tou-demand-tb-winter-peak", "cpau:e7tou-season-winter",
         "weekdayDays", "16:00:00", "21:00:00",
         include_holidays=False, include_non_holidays=True,
     )]},
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e7tou-demand-period-winter-max",
     "urpx:name": "Winter Max Demand", "urpx:touPeriodNumber": 4,
     "urpx:hasTimeBracket": [time_bracket(
         "cpau:e7tou-demand-tb-winter-max", "cpau:e7tou-season-winter",
         "allDays", "00:00:00", "00:00:00",
         include_holidays=True, include_non_holidays=True,
     )]},
]

demand_tou_schedule = {
    "@type": "urpx:TOUSchedule", "@id": "cpau:e7tou-demand-tou-schedule",
    "urpx:name": "E-4 TOU Demand schedule",
    "urpx:referencesMetricInput": {"@id": "cpau:e7tou-mi-demand"},
    "urpx:hasCalendar": {"@id": "cpau:e7tou-holidays"},
    "urpx:hasTOUTier": [{
        "@type": "urpx:TOUTier", "@id": "cpau:e7tou-demand-tou-tier-1",
        "urpx:touTierNumber": 1,
        "urpx:hasTOUPeriod": demand_periods,
    }],
}

# ============================================================================
# PriceDefinitions
# ============================================================================

def pd_energy(pd_id, name, ledger_id, period_num, season_id):
    return {
        "@type": "urpx:PriceDefinition", "@id": pd_id, "urpx:name": name,
        "urpx:chargeType": {"@id": "urpx:usageCharge"},
        "urpx:chargeCategory": {"@id": "urpx:auxiliaryCharge"},
        "urpx:billPortion": {"@id": "urpx:supplyPortion"},
        "urpx:appliesInSeason": {"@id": season_id},
        "urpx:touPeriodNumber": period_num,
        "urpx:referencesLedger": {"@id": ledger_id},
        "urpx:referencesMetricInput": {"@id": "cpau:e7tou-mi-energy"},
    }


def pd_demand(pd_id, name, ledger_id, period_num, season_id, peak_or_max):
    pd = {
        "@type": "urpx:PriceDefinition", "@id": pd_id, "urpx:name": name,
        "urpx:chargeType": {"@id": "urpx:demandDirect"},
        "urpx:chargeCategory": {"@id": "urpx:auxiliaryCharge"},
        "urpx:billPortion": {"@id": "urpx:supplyPortion"},
        "urpx:appliesInSeason": {"@id": season_id},
        "urpx:touPeriodNumber": period_num,
        "urpx:referencesLedger": {"@id": ledger_id},
        "urpx:referencesMetricInput": {"@id": "cpau:e7tou-mi-demand"},
        "urpx:hasCalculationMethod": {
            "@type": "urpx:CalculationMethod",
            "@id": f"{pd_id}-cm",
            "urpx:aggregationMethod": {"@id": "urpx:maximum"},
            "urpx:intervalDuration": "P1M",
            "urpx:intervalType": {"@id": "urpx:monthlyInterval"},
            "urpx:description": (
                "Maximum demand (kW) measured in any 15-minute interval during "
                + ("the peak window only" if peak_or_max == "peak" else "any time of the billing period")
                + ", aggregated as the maximum over the monthly billing period."
            ),
        },
    }
    return pd


# Energy PDs: 3 components × 3 periods × 2 seasons = 18
energy_pds = []
energy_specs = [
    # (period_num, season_id, period_label)
    (1, "cpau:e7tou-season-summer", "summer-peak"),
    (2, "cpau:e7tou-season-summer", "summer-mid-peak"),
    (3, "cpau:e7tou-season-summer", "summer-off-peak"),
    (4, "cpau:e7tou-season-winter", "winter-peak"),
    (5, "cpau:e7tou-season-winter", "winter-mid-peak"),
    (6, "cpau:e7tou-season-winter", "winter-off-peak"),
]
for period_num, season_id, label in energy_specs:
    energy_pds.append(pd_energy(
        f"cpau:e7tou-pd-energy-commodity-{label}",
        f"Energy Commodity {label.replace('-', ' ').title()}",
        "cpau:e7tou-ledger-energy-commodity", period_num, season_id))
    energy_pds.append(pd_energy(
        f"cpau:e7tou-pd-energy-distribution-{label}",
        f"Energy Distribution {label.replace('-', ' ').title()}",
        "cpau:e7tou-ledger-energy-distribution", period_num, season_id))
    energy_pds.append(pd_energy(
        f"cpau:e7tou-pd-energy-public-benefits-{label}",
        f"Energy Public Benefits {label.replace('-', ' ').title()}",
        "cpau:e7tou-ledger-energy-public-benefits", period_num, season_id))

# Demand PDs: 2 components × 2 demand-types (peak/max) × 2 seasons = 8
demand_pds = []
demand_specs = [
    (1, "cpau:e7tou-season-summer", "summer-peak", "peak"),
    (2, "cpau:e7tou-season-summer", "summer-max", "max"),
    (3, "cpau:e7tou-season-winter", "winter-peak", "peak"),
    (4, "cpau:e7tou-season-winter", "winter-max", "max"),
]
for period_num, season_id, label, kind in demand_specs:
    demand_pds.append(pd_demand(
        f"cpau:e7tou-pd-demand-commodity-{label}",
        f"Demand Commodity {label.replace('-', ' ').title()}",
        "cpau:e7tou-ledger-demand-commodity", period_num, season_id, kind))
    demand_pds.append(pd_demand(
        f"cpau:e7tou-pd-demand-distribution-{label}",
        f"Demand Distribution {label.replace('-', ' ').title()}",
        "cpau:e7tou-ledger-demand-distribution", period_num, season_id, kind))

# Customer Charge PD
customer_charge_pd = {
    "@type": "urpx:PriceDefinition", "@id": "cpau:e7tou-pd-customer-charge",
    "urpx:name": "Customer Charge",
    "urpx:chargeType": {"@id": "urpx:serviceMetered"},
    "urpx:chargeCategory": {"@id": "urpx:serviceCharge"},
    "urpx:billPortion": {"@id": "urpx:supplyPortion"},
    "urpx:baseQuantity": "1",
    "urpx:hasCalculationMethod": {
        "@type": "urpx:CalculationMethod", "@id": "cpau:e7tou-pd-customer-charge-cm",
        "urpx:intervalDuration": "P1M",
    },
    "urpx:referencesLedger": {"@id": "cpau:e7tou-ledger-service"},
}

all_pds = energy_pds + demand_pds + [customer_charge_pd]

# ============================================================================
# Prices — unitPrice values from Section C of the PDF
# ============================================================================
PRICE_VALUES = {
    # Energy summer
    "cpau:e7tou-pd-energy-commodity-summer-peak":         "0.18199",
    "cpau:e7tou-pd-energy-distribution-summer-peak":      "0.00402",
    "cpau:e7tou-pd-energy-public-benefits-summer-peak":   "0.00604",
    "cpau:e7tou-pd-energy-commodity-summer-mid-peak":     "0.14999",
    "cpau:e7tou-pd-energy-distribution-summer-mid-peak":  "0.00402",
    "cpau:e7tou-pd-energy-public-benefits-summer-mid-peak": "0.00604",
    "cpau:e7tou-pd-energy-commodity-summer-off-peak":     "0.11276",
    "cpau:e7tou-pd-energy-distribution-summer-off-peak":  "0.00402",
    "cpau:e7tou-pd-energy-public-benefits-summer-off-peak": "0.00604",
    # Energy winter
    "cpau:e7tou-pd-energy-commodity-winter-peak":         "0.12225",
    "cpau:e7tou-pd-energy-distribution-winter-peak":      "0.00393",
    "cpau:e7tou-pd-energy-public-benefits-winter-peak":   "0.00604",
    "cpau:e7tou-pd-energy-commodity-winter-mid-peak":     "0.09648",
    "cpau:e7tou-pd-energy-distribution-winter-mid-peak":  "0.00393",
    "cpau:e7tou-pd-energy-public-benefits-winter-mid-peak": "0.00604",
    "cpau:e7tou-pd-energy-commodity-winter-off-peak":     "0.06660",
    "cpau:e7tou-pd-energy-distribution-winter-off-peak":  "0.00393",
    "cpau:e7tou-pd-energy-public-benefits-winter-off-peak": "0.00604",
    # Demand summer
    "cpau:e7tou-pd-demand-commodity-summer-peak":         "11.39",
    "cpau:e7tou-pd-demand-distribution-summer-peak":      "16.33",
    "cpau:e7tou-pd-demand-commodity-summer-max":          "1.46",
    "cpau:e7tou-pd-demand-distribution-summer-max":       "16.33",
    # Demand winter
    "cpau:e7tou-pd-demand-commodity-winter-peak":         "1.46",
    "cpau:e7tou-pd-demand-distribution-winter-peak":      "14.42",
    "cpau:e7tou-pd-demand-commodity-winter-max":          "1.46",
    "cpau:e7tou-pd-demand-distribution-winter-max":       "14.42",
    # Customer
    "cpau:e7tou-pd-customer-charge":                       "578.08",
}

prices_list = []
for pd in all_pds:
    pd_id = pd["@id"]
    price = {
        "@type": "urpx:Price",
        "@id": pd_id.replace("-pd-", "-price-"),
        "urpx:name": pd["urpx:name"],
        "urpx:referencesPriceDefinition": {"@id": pd_id},
        "urpx:startDate": "2025-07-01",
        "urpx:unitPrice": PRICE_VALUES[pd_id],
    }
    prices_list.append(price)

# ============================================================================
# Assembly
# ============================================================================
billing_model = {
    "@type": "urpx:BillingModel", "@id": "cpau:e7tou-billing-model",
    "urpx:hasLedger": ledgers,
    "urpx:hasPriceDefinition": all_pds,
    "urpx:hasTOUSchedule": [energy_tou_schedule, demand_tou_schedule],
}

plan_elements = {
    "@type": "urpx:PlanElements", "@id": "cpau:e7tou-plan-elements",
    "urpx:hasSeasons": [season_summer, season_winter],
    "urpx:hasHolidayCalendar": holiday_calendar,
    "urpx:hasMetricInput": [mi_energy, mi_demand, mi_meter_count],
    "urpx:hasBillingModel": billing_model,
}

prices_block = {
    "@type": "urpx:Prices", "@id": "cpau:e7tou-prices",
    "urpx:hasPriceSet": [{
        "@type": "urpx:PriceSet", "@id": "cpau:e7tou-price-set",
        "urpx:hasPrice": prices_list,
    }],
}

data_source_reference = {
    "@type": "urpx:DataSourceReference", "@id": "cpau:e7tou-dsr",
    "urpx:name": "CPAU Schedule E-7 TOU (effective 2025-07-01)",
    "urpx:fileName": "e-7-tou-effective-2025-07-01.pdf",
    "urpx:url": "https://www.paloalto.gov/files/assets/public/v/5/utilities/rates-schedules-for-utilities/commercial-utility-rates/e-7-tou-effective-2025-07-01.pdf",
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
    "@type": "urpx:RatePlanVersion", "@id": "cpau:e-7-tou-2025-07-01",
    "urpx:version": "1.0",
    "urpx:effectiveDateTime": "2025-07-01T00:00:00",
    "urpx:description": (
        "CPAU Schedule E-7 TOU (Large Non-Residential Electric Time of Use "
        "Service), effective 2025-07-01. Voluntary opt-in rate for demand-metered "
        "customers with maximum demand at least 1000 kW per site, sustained 3+ "
        "consecutive months in the most recent 12-month period. Two seasons; three "
        "TOU periods for energy (Peak / Mid-Peak / Off-Peak); two demand windows "
        "(Peak Demand within the energy peak window, plus Max Demand at any time). "
        "Holiday-aware (US federal holidays observed by CA utilities). Section D.3 "
        "site-aggregation feature (multiple Accounts on contiguous parcels with a "
        "common billing address) is noted but not modeled — URPX has no native "
        "vocabulary for site-level account aggregation. Modeled in v1: eligibility, "
        "seasons, TOU windows, energy + demand pricing, monthly customer charge. "
        "NOT modeled in v1 (deferred): Section D.6 Primary Voltage Discount (2.8% "
        "for >2 kV service), Section D.7 Standby Charge (non-utility on-site "
        "generation), Section D.5 12-month minimum commitment."
    ),
    "urpx:customerChoice": {"@id": "urpx:voluntaryChoice"},
    "urpx:isDefault": False,
    "urpx:changeReason": {"@id": "urpx:initial"},
    "urpx:serviceRole": {"@id": "urpx:bundledServiceRole"},
    "urpx:publishedBy": publishing_org,
    "urpx:hasDataSourceReference": data_source_reference,
    "urpx:hasEligibilityRule": [eligibility_rule],
    "urpx:hasPlanElements": plan_elements,
    "urpx:hasPrices": prices_block,
}

rate_plan = {
    "@type": "urpx:RatePlan", "@id": "cpau:e-7-tou",
    "urpx:name": "Large Non-Residential Electric Time of Use Service",
    "urpx:ratePlanUniqueIdentifier": "CPAU-E-7-TOU",
    "urpx:initialEffectiveDate": "2025-07-01",
    "urpx:timezoneIdentifier": "America/Los_Angeles",
    "urpx:hasRatePlanVersion": rpv,
}

doc = {"@context": CONTEXT, "@graph": [rate_plan]}


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(all_pds)} PDs, {len(prices_list)} prices)")


if __name__ == "__main__":
    main()
