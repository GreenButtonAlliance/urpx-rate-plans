#!/usr/bin/env python3
"""
Build ca/pou/cpau/e-4-tou/versions/2025-07-01/rate-plan_cpau_e-4-tou_2025-07-01.jsonld.

CPAU Schedule E-4 TOU: Medium Non-Residential Electric Time of Use Service.
First demand-charge filing in our corpus and first commercial TOU filing.
Source PDF sha256 87a5bbb38a64af17e8d80c0402ab81c1caca2c03ec18fc0850603c5f468ddb48
retrieved from paloalto.gov 2026-04-29.

VOLUNTARY rate schedule for demand-metered Secondary Electric Service
customers with sustained demand 500–1000 kW. 12-month minimum commitment.

NEW URPX modeling territory exercised here for the first time in our corpus:
  1. urpx:demand measurementKind + urpx:kW unit-of-measure (per-kW pricing)
  2. Two distinct demand charges per season:
       - Peak Demand: max kW within 4-9 PM weekday-non-holiday window
       - Max Demand: max kW any time of month (full window, all days)
     Each modeled as its own PriceDefinition + Price chain via separate
     TOUPeriods on a Demand TOUSchedule.
  3. Two separate TOUSchedules in one filing — energy and demand have
     different period structures (energy has Peak/Mid-Peak/Off-Peak;
     demand has Peak/Max only) so each MetricInput gets its own
     TOUSchedule (urpx:TOUSchedule.referencesMetricInput).
  4. Commercial TOU windows that DIFFER between Summer and Winter
     (Summer Mid-Peak: 2-4pm + 9-11pm; Winter Mid-Peak: 9am-2pm).
  5. Holiday-aware TOU using the established PG&E E-TOU-D pattern
     (HolidayCalendar at PlanElements; includeHolidays/includeNonHolidays
     booleans on TimeBracket).
  6. CalculationMethod with aggregationMethod=urpx:maximum on demand
     PriceDefinitions (vs. implicit sum-aggregation for energy).

DEFERRED (filed as follow-ups, not modeled in v1):
  - Section D.5 Primary Voltage Discount: 2.5% discount for service at
    line voltage > 2 kV. Conditional discount Price gated by a
    custom-condition ApplicabilityGroup on serviceVoltage.
  - Section D.7 Standby Charge: per-kW summer/winter charges for
    customers with non-utility on-site generation, with NEM-eligibility
    exemptions. Effectively a separate set of PDs gated by an
    EligibilityRule on Customer.hasGenerator.
  - Section D.4 12-month minimum commitment: contract clause; URPX has
    no native vocabulary for minimum-term commitments (consider filing
    upstream).
  - Section D.3 Demand Meter installation rule (>8000 kWh for 3 months
    triggers demand metering): operations rule, not a rate.

Per-component rates from Section C of the PDF:
  Summer:   commodity / distribution / public-benefits
    Demand Peak    : 9.82  / 19.07  / —      = 28.89 / kW
    Demand Max     : 1.30  / 19.07  / —      = 20.37 / kW
    Energy Peak    : 0.17208 / 0.02817 / 0.00604 = 0.20629 / kWh
    Energy Mid-Peak: 0.14181 / 0.02817 / 0.00604 = 0.17602 / kWh
    Energy Off-Peak: 0.10662 / 0.02817 / 0.00604 = 0.14083 / kWh
  Winter:
    Demand Peak    : 1.31  / 11.91  / —      = 13.22 / kW
    Demand Max     : 1.31  / 11.91  / —      = 13.22 / kW
    Energy Peak    : 0.12096 / 0.02775 / 0.00604 = 0.15475 / kWh
    Energy Mid-Peak: 0.09547 / 0.02775 / 0.00604 = 0.12926 / kWh
    Energy Off-Peak: 0.06590 / 0.02775 / 0.00604 = 0.09969 / kWh
  Customer Charge: 126.24 / month
"""
import json
from pathlib import Path

ROOT = Path(str(Path(__file__).resolve().parent.parent))
OUT = ROOT / "ca/pou/cpau/e-4-tou/versions/2025-07-01/rate-plan_cpau_e-4-tou_2025-07-01.jsonld"

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
    "cpau": "https://rate-plans.grid-coordination.energy/cpau/",
    "org": "https://rate-plans.grid-coordination.energy/organizations/",
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
    "@id": "cpau:e4tou-er-eligibility",
    "urpx:name": "Demand-metered Secondary, demand 500-1000 kW sustained 3 months",
    "urpx:description": (
        "Voluntary opt-in rate for customers receiving Demand metered Secondary "
        "Electric Service whose monthly demand is between 500 and 1000 kW, "
        "sustained at that level for at least three consecutive months in the "
        "most recent 12-month period. Section A of the published Schedule E-4 TOU."
    ),
    "urpx:hasConditionExpression": expr(
        "cpau:e4tou-cx-eligibility",
        boolop("cpau:e4tou-bn-eligibility-and", "and", [
            cn_eq_str("cpau:e4tou-cn-demand-metered", "metering", "Demand metered Secondary"),
            cn_gte_decimal("cpau:e4tou-cn-demand-min-500", "monthlyMaxDemand_kW", "500"),
            cn_lte_decimal("cpau:e4tou-cn-demand-max-1000", "monthlyMaxDemand_kW", "1000"),
            cn_eq_str("cpau:e4tou-cn-sustained-3mo", "demandSustainedConsecutiveMonths", "3"),
        ], logic_expression=(
            "metering = 'Demand metered Secondary' AND monthlyMaxDemand_kW >= 500 AND "
            "monthlyMaxDemand_kW <= 1000 AND demandSustainedConsecutiveMonths = 3"
        )),
    ),
}

# ============================================================================
# Seasons
# ============================================================================
season_summer = {
    "@type": "urpx:Season", "@id": "cpau:e4tou-season-summer",
    "urpx:seasonName": "Summer", "urpx:yearlyRecurrence": True,
    "urpx:month": ["--05", "--06", "--07", "--08", "--09", "--10"],
}
season_winter = {
    "@type": "urpx:Season", "@id": "cpau:e4tou-season-winter",
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
    "@id": "cpau:e4tou-holidays",
    "urpx:hasHoliday": [
        {"@type": "urpx:Holiday", "@id": "cpau:e4tou-holiday-new-years",
         "urpx:holidayName": "New Year's Day",   "urpx:holidayRule": "January 1 (legally observed)"},
        {"@type": "urpx:Holiday", "@id": "cpau:e4tou-holiday-presidents",
         "urpx:holidayName": "Presidents' Day",  "urpx:holidayRule": "Third Monday in February"},
        {"@type": "urpx:Holiday", "@id": "cpau:e4tou-holiday-memorial",
         "urpx:holidayName": "Memorial Day",     "urpx:holidayRule": "Last Monday in May"},
        {"@type": "urpx:Holiday", "@id": "cpau:e4tou-holiday-independence",
         "urpx:holidayName": "Independence Day", "urpx:holidayRule": "July 4 (legally observed)"},
        {"@type": "urpx:Holiday", "@id": "cpau:e4tou-holiday-labor",
         "urpx:holidayName": "Labor Day",        "urpx:holidayRule": "First Monday in September"},
        {"@type": "urpx:Holiday", "@id": "cpau:e4tou-holiday-veterans",
         "urpx:holidayName": "Veterans Day",     "urpx:holidayRule": "November 11 (legally observed)"},
        {"@type": "urpx:Holiday", "@id": "cpau:e4tou-holiday-thanksgiving",
         "urpx:holidayName": "Thanksgiving Day", "urpx:holidayRule": "Fourth Thursday in November"},
        {"@type": "urpx:Holiday", "@id": "cpau:e4tou-holiday-christmas",
         "urpx:holidayName": "Christmas Day",    "urpx:holidayRule": "December 25 (legally observed)"},
    ],
}

# ============================================================================
# MetricInputs
# ============================================================================
mi_energy = {
    "@type": "urpx:MetricInput", "@id": "cpau:e4tou-mi-energy",
    "urpx:name": "Energy consumed (kWh)",
    "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
    "urpx:hasMetricSpecification": {
        "@type": "urpx:MetricSpecification", "@id": "cpau:e4tou-ms-energy",
        "urpx:measurementKind": {"@id": "urpx:energy"},
        "urpx:unitOfMeasure": {"@id": "urpx:kWh"},
        "urpx:flowDirection": {"@id": "urpx:forward"},
    },
}
mi_demand = {
    "@type": "urpx:MetricInput", "@id": "cpau:e4tou-mi-demand",
    "urpx:name": "Demand (kW, 15-minute interval)",
    "urpx:metricInputType": {"@id": "urpx:measuredMetricInput"},
    "urpx:hasMetricSpecification": {
        "@type": "urpx:MetricSpecification", "@id": "cpau:e4tou-ms-demand",
        "urpx:measurementKind": {"@id": "urpx:demand"},
        "urpx:unitOfMeasure": {"@id": "urpx:kW"},
        "urpx:flowDirection": {"@id": "urpx:forward"},
        "urpx:intervalDuration": "PT15M",
        "urpx:intervalType": {"@id": "urpx:fifteenMinuteInterval"},
    },
}
mi_meter_count = {
    "@type": "urpx:MetricInput", "@id": "cpau:e4tou-mi-meter-count",
    "urpx:name": "Meter count",
    "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
    "urpx:profileMetricProperty": {"@id": "urpx:meterCount"},
}

# ============================================================================
# Ledgers
# ============================================================================
ledgers = [
    {"@type": "urpx:Ledger", "@id": "cpau:e4tou-ledger-energy-commodity",
     "urpx:name": "Energy — Commodity", "urpx:ledgerType": {"@id": "urpx:supplyLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e4tou-mi-energy"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e4tou-ledger-energy-distribution",
     "urpx:name": "Energy — Distribution", "urpx:ledgerType": {"@id": "urpx:distributionLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e4tou-mi-energy"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e4tou-ledger-energy-public-benefits",
     "urpx:name": "Energy — Public Benefits", "urpx:ledgerType": {"@id": "urpx:bundledLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e4tou-mi-energy"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e4tou-ledger-demand-commodity",
     "urpx:name": "Demand — Commodity", "urpx:ledgerType": {"@id": "urpx:supplyLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e4tou-mi-demand"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e4tou-ledger-demand-distribution",
     "urpx:name": "Demand — Distribution", "urpx:ledgerType": {"@id": "urpx:distributionLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e4tou-mi-demand"}},
    {"@type": "urpx:Ledger", "@id": "cpau:e4tou-ledger-service",
     "urpx:name": "Customer (service) charge", "urpx:ledgerType": {"@id": "urpx:profileMetricLedger"},
     "urpx:referencesMetricInput": {"@id": "cpau:e4tou-mi-meter-count"}},
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
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e4tou-energy-period-summer-peak",
     "urpx:name": "Summer Peak", "urpx:touPeriodNumber": 1,
     "urpx:hasTimeBracket": [time_bracket(
         "cpau:e4tou-energy-tb-summer-peak", "cpau:e4tou-season-summer",
         "weekdayDays", "16:00:00", "21:00:00",
         include_holidays=False, include_non_holidays=True,
     )]},
    # Summer Mid-Peak (TWO segments)
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e4tou-energy-period-summer-mid-peak",
     "urpx:name": "Summer Mid-Peak", "urpx:touPeriodNumber": 2,
     "urpx:hasTimeBracket": [
         time_bracket("cpau:e4tou-energy-tb-summer-mid-peak-afternoon",
                      "cpau:e4tou-season-summer", "weekdayDays", "14:00:00", "16:00:00",
                      include_holidays=False, include_non_holidays=True),
         time_bracket("cpau:e4tou-energy-tb-summer-mid-peak-evening",
                      "cpau:e4tou-season-summer", "weekdayDays", "21:00:00", "23:00:00",
                      include_holidays=False, include_non_holidays=True),
     ]},
    # Summer Off-Peak (gaps + weekends + weekday holidays)
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e4tou-energy-period-summer-off-peak",
     "urpx:name": "Summer Off-Peak", "urpx:touPeriodNumber": 3,
     "urpx:hasTimeBracket": off_peak_brackets(
         "cpau:e4tou-energy-summer-off-peak", "cpau:e4tou-season-summer",
         "16:00:00", "21:00:00",
         [("14:00:00", "16:00:00"), ("21:00:00", "23:00:00")],
     )},
    # Winter Peak
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e4tou-energy-period-winter-peak",
     "urpx:name": "Winter Peak", "urpx:touPeriodNumber": 4,
     "urpx:hasTimeBracket": [time_bracket(
         "cpau:e4tou-energy-tb-winter-peak", "cpau:e4tou-season-winter",
         "weekdayDays", "16:00:00", "21:00:00",
         include_holidays=False, include_non_holidays=True,
     )]},
    # Winter Mid-Peak (single segment 9-2)
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e4tou-energy-period-winter-mid-peak",
     "urpx:name": "Winter Mid-Peak", "urpx:touPeriodNumber": 5,
     "urpx:hasTimeBracket": [time_bracket(
         "cpau:e4tou-energy-tb-winter-mid-peak", "cpau:e4tou-season-winter",
         "weekdayDays", "09:00:00", "14:00:00",
         include_holidays=False, include_non_holidays=True,
     )]},
    # Winter Off-Peak
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e4tou-energy-period-winter-off-peak",
     "urpx:name": "Winter Off-Peak", "urpx:touPeriodNumber": 6,
     "urpx:hasTimeBracket": off_peak_brackets(
         "cpau:e4tou-energy-winter-off-peak", "cpau:e4tou-season-winter",
         "16:00:00", "21:00:00",
         [("09:00:00", "14:00:00")],
     )},
]

energy_tou_schedule = {
    "@type": "urpx:TOUSchedule", "@id": "cpau:e4tou-energy-tou-schedule",
    "urpx:name": "E-4 TOU Energy schedule",
    "urpx:referencesMetricInput": {"@id": "cpau:e4tou-mi-energy"},
    "urpx:hasCalendar": {"@id": "cpau:e4tou-holidays"},
    "urpx:hasTOUTier": [{
        "@type": "urpx:TOUTier", "@id": "cpau:e4tou-energy-tou-tier-1",
        "urpx:touTierNumber": 1,
        "urpx:hasTOUPeriod": energy_periods,
    }],
}

# ---- Demand TOU schedule ---------------------------------------------------
# Demand Peak    : 16:00-21:00 weekday non-holiday (same window as energy peak)
# Max Demand     : ALL HOURS every day (no time gating)

demand_periods = [
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e4tou-demand-period-summer-peak",
     "urpx:name": "Summer Demand Peak", "urpx:touPeriodNumber": 1,
     "urpx:hasTimeBracket": [time_bracket(
         "cpau:e4tou-demand-tb-summer-peak", "cpau:e4tou-season-summer",
         "weekdayDays", "16:00:00", "21:00:00",
         include_holidays=False, include_non_holidays=True,
     )]},
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e4tou-demand-period-summer-max",
     "urpx:name": "Summer Max Demand", "urpx:touPeriodNumber": 2,
     "urpx:hasTimeBracket": [time_bracket(
         "cpau:e4tou-demand-tb-summer-max", "cpau:e4tou-season-summer",
         "allDays", "00:00:00", "00:00:00",
         include_holidays=True, include_non_holidays=True,
     )]},
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e4tou-demand-period-winter-peak",
     "urpx:name": "Winter Demand Peak", "urpx:touPeriodNumber": 3,
     "urpx:hasTimeBracket": [time_bracket(
         "cpau:e4tou-demand-tb-winter-peak", "cpau:e4tou-season-winter",
         "weekdayDays", "16:00:00", "21:00:00",
         include_holidays=False, include_non_holidays=True,
     )]},
    {"@type": "urpx:TOUPeriod", "@id": "cpau:e4tou-demand-period-winter-max",
     "urpx:name": "Winter Max Demand", "urpx:touPeriodNumber": 4,
     "urpx:hasTimeBracket": [time_bracket(
         "cpau:e4tou-demand-tb-winter-max", "cpau:e4tou-season-winter",
         "allDays", "00:00:00", "00:00:00",
         include_holidays=True, include_non_holidays=True,
     )]},
]

demand_tou_schedule = {
    "@type": "urpx:TOUSchedule", "@id": "cpau:e4tou-demand-tou-schedule",
    "urpx:name": "E-4 TOU Demand schedule",
    "urpx:referencesMetricInput": {"@id": "cpau:e4tou-mi-demand"},
    "urpx:hasCalendar": {"@id": "cpau:e4tou-holidays"},
    "urpx:hasTOUTier": [{
        "@type": "urpx:TOUTier", "@id": "cpau:e4tou-demand-tou-tier-1",
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
        "urpx:referencesMetricInput": {"@id": "cpau:e4tou-mi-energy"},
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
        "urpx:referencesMetricInput": {"@id": "cpau:e4tou-mi-demand"},
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
    (1, "cpau:e4tou-season-summer", "summer-peak"),
    (2, "cpau:e4tou-season-summer", "summer-mid-peak"),
    (3, "cpau:e4tou-season-summer", "summer-off-peak"),
    (4, "cpau:e4tou-season-winter", "winter-peak"),
    (5, "cpau:e4tou-season-winter", "winter-mid-peak"),
    (6, "cpau:e4tou-season-winter", "winter-off-peak"),
]
for period_num, season_id, label in energy_specs:
    energy_pds.append(pd_energy(
        f"cpau:e4tou-pd-energy-commodity-{label}",
        f"Energy Commodity {label.replace('-', ' ').title()}",
        "cpau:e4tou-ledger-energy-commodity", period_num, season_id))
    energy_pds.append(pd_energy(
        f"cpau:e4tou-pd-energy-distribution-{label}",
        f"Energy Distribution {label.replace('-', ' ').title()}",
        "cpau:e4tou-ledger-energy-distribution", period_num, season_id))
    energy_pds.append(pd_energy(
        f"cpau:e4tou-pd-energy-public-benefits-{label}",
        f"Energy Public Benefits {label.replace('-', ' ').title()}",
        "cpau:e4tou-ledger-energy-public-benefits", period_num, season_id))

# Demand PDs: 2 components × 2 demand-types (peak/max) × 2 seasons = 8
demand_pds = []
demand_specs = [
    (1, "cpau:e4tou-season-summer", "summer-peak", "peak"),
    (2, "cpau:e4tou-season-summer", "summer-max", "max"),
    (3, "cpau:e4tou-season-winter", "winter-peak", "peak"),
    (4, "cpau:e4tou-season-winter", "winter-max", "max"),
]
for period_num, season_id, label, kind in demand_specs:
    demand_pds.append(pd_demand(
        f"cpau:e4tou-pd-demand-commodity-{label}",
        f"Demand Commodity {label.replace('-', ' ').title()}",
        "cpau:e4tou-ledger-demand-commodity", period_num, season_id, kind))
    demand_pds.append(pd_demand(
        f"cpau:e4tou-pd-demand-distribution-{label}",
        f"Demand Distribution {label.replace('-', ' ').title()}",
        "cpau:e4tou-ledger-demand-distribution", period_num, season_id, kind))

# Customer Charge PD
customer_charge_pd = {
    "@type": "urpx:PriceDefinition", "@id": "cpau:e4tou-pd-customer-charge",
    "urpx:name": "Customer Charge",
    "urpx:chargeType": {"@id": "urpx:serviceMetered"},
    "urpx:chargeCategory": {"@id": "urpx:serviceCharge"},
    "urpx:billPortion": {"@id": "urpx:supplyPortion"},
    "urpx:baseQuantity": "1",
    "urpx:hasCalculationMethod": {
        "@type": "urpx:CalculationMethod", "@id": "cpau:e4tou-pd-customer-charge-cm",
        "urpx:intervalDuration": "P1M",
    },
    "urpx:referencesLedger": {"@id": "cpau:e4tou-ledger-service"},
}

all_pds = energy_pds + demand_pds + [customer_charge_pd]

# ============================================================================
# Prices — unitPrice values from Section C of the PDF
# ============================================================================
PRICE_VALUES = {
    # Energy summer
    "cpau:e4tou-pd-energy-commodity-summer-peak":         "0.17208",
    "cpau:e4tou-pd-energy-distribution-summer-peak":      "0.02817",
    "cpau:e4tou-pd-energy-public-benefits-summer-peak":   "0.00604",
    "cpau:e4tou-pd-energy-commodity-summer-mid-peak":     "0.14181",
    "cpau:e4tou-pd-energy-distribution-summer-mid-peak":  "0.02817",
    "cpau:e4tou-pd-energy-public-benefits-summer-mid-peak": "0.00604",
    "cpau:e4tou-pd-energy-commodity-summer-off-peak":     "0.10662",
    "cpau:e4tou-pd-energy-distribution-summer-off-peak":  "0.02817",
    "cpau:e4tou-pd-energy-public-benefits-summer-off-peak": "0.00604",
    # Energy winter
    "cpau:e4tou-pd-energy-commodity-winter-peak":         "0.12096",
    "cpau:e4tou-pd-energy-distribution-winter-peak":      "0.02775",
    "cpau:e4tou-pd-energy-public-benefits-winter-peak":   "0.00604",
    "cpau:e4tou-pd-energy-commodity-winter-mid-peak":     "0.09547",
    "cpau:e4tou-pd-energy-distribution-winter-mid-peak":  "0.02775",
    "cpau:e4tou-pd-energy-public-benefits-winter-mid-peak": "0.00604",
    "cpau:e4tou-pd-energy-commodity-winter-off-peak":     "0.06590",
    "cpau:e4tou-pd-energy-distribution-winter-off-peak":  "0.02775",
    "cpau:e4tou-pd-energy-public-benefits-winter-off-peak": "0.00604",
    # Demand summer
    "cpau:e4tou-pd-demand-commodity-summer-peak":         "9.82",
    "cpau:e4tou-pd-demand-distribution-summer-peak":      "19.07",
    "cpau:e4tou-pd-demand-commodity-summer-max":          "1.30",
    "cpau:e4tou-pd-demand-distribution-summer-max":       "19.07",
    # Demand winter
    "cpau:e4tou-pd-demand-commodity-winter-peak":         "1.31",
    "cpau:e4tou-pd-demand-distribution-winter-peak":      "11.91",
    "cpau:e4tou-pd-demand-commodity-winter-max":          "1.31",
    "cpau:e4tou-pd-demand-distribution-winter-max":       "11.91",
    # Customer
    "cpau:e4tou-pd-customer-charge":                       "126.24",
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
    "@type": "urpx:BillingModel", "@id": "cpau:e4tou-billing-model",
    "urpx:hasLedger": ledgers,
    "urpx:hasPriceDefinition": all_pds,
    "urpx:hasTOUSchedule": [energy_tou_schedule, demand_tou_schedule],
}

plan_elements = {
    "@type": "urpx:PlanElements", "@id": "cpau:e4tou-plan-elements",
    "urpx:hasSeasons": [season_summer, season_winter],
    "urpx:hasHolidayCalendar": holiday_calendar,
    "urpx:hasMetricInput": [mi_energy, mi_demand, mi_meter_count],
    "urpx:hasBillingModel": billing_model,
}

prices_block = {
    "@type": "urpx:Prices", "@id": "cpau:e4tou-prices",
    "urpx:hasPriceSet": [{
        "@type": "urpx:PriceSet", "@id": "cpau:e4tou-price-set",
        "urpx:hasPrice": prices_list,
    }],
}

data_source_reference = {
    "@type": "urpx:DataSourceReference", "@id": "cpau:e4tou-dsr",
    "urpx:name": "CPAU Schedule E-4 TOU (effective 2025-07-01)",
    "urpx:fileName": "e-4-tou-effective-2025-07-01.pdf",
    "urpx:url": "https://www.paloalto.gov/files/assets/public/v/5/utilities/rates-schedules-for-utilities/commercial-utility-rates/e-4-tou-effective-2025-07-01.pdf",
    "urpx:mediaType": {"@id": "urpx:applicationPdf"},
    "urpx:dataSourceType": {"@id": "urpx:utilityWebsiteSource"},
    "urpx:dateRetrieved": "2026-04-29",
}

publishing_org = {
    "@type": "urpx:Organization", "@id": "org:utility-cpau",
    "urpx:legalName": "City of Palo Alto Utilities",
    "urpx:eiaId": "3203",
    "urpx:organizationType": {"@id": "urpx:municipalOrganization"},
}

rpv = {
    "@type": "urpx:RatePlanVersion", "@id": "cpau:e-4-tou-2025-07-01",
    "urpx:version": "1.0",
    "urpx:effectiveDateTime": "2025-07-01T00:00:00",
    "urpx:description": (
        "CPAU Schedule E-4 TOU (Medium Non-Residential Electric Time of Use Service), "
        "effective 2025-07-01. Voluntary opt-in rate for demand-metered Secondary "
        "Electric Service customers with sustained demand 500–1000 kW. Two seasons; "
        "three TOU periods for energy (Peak / Mid-Peak / Off-Peak); two demand "
        "windows (Peak Demand within the energy peak window, plus Max Demand at "
        "any time). Holiday-aware (US federal holidays observed by CA utilities). "
        "Modeled in v1: eligibility, seasons, TOU windows, energy + demand pricing, "
        "monthly customer charge. NOT modeled in v1 (deferred): Section D.5 Primary "
        "Voltage Discount (2.5% for >2 kV service), Section D.7 Standby Charge "
        "(non-utility on-site generation), Section D.4 12-month minimum commitment."
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
    "@type": "urpx:RatePlan", "@id": "cpau:e-4-tou",
    "urpx:name": "Medium Non-Residential Electric Time of Use Service",
    "urpx:ratePlanUniqueIdentifier": "CPAU-E-4-TOU",
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
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(all_pds)} PDs, {len(prices_list)} prices)")


if __name__ == "__main__":
    main()
