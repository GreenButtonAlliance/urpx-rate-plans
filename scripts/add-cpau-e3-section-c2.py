#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Add CPAU E-3 Section C.2 (with-interval-meter TOU buyback) to the existing
E-3 RatePlanVersion.

Section C.2 adds:
- 5-period TOU schedule (Summer Peak/Mid-Peak/Off-Peak; Winter Peak/Off-Peak)
  with windows that DIFFER from CPAU E-4 TOU / E-7 TOU (this is per Section C.2)
- 7 PriceDefinitions: 5 energy (one per TOU period) + 2 capacity (Firm-only,
  Peak periods only)
- Per-PriceSet ApplicabilityGroup gating on hasIntervalMeter (true for the new
  C.2 PriceSet; false for the existing C.1 PriceSet, which gets a new
  ApplicabilityGroup added)
- HolidayCalendar (E-3 didn't previously need one)

Operates on: ca/pou/cpau/e-3/versions/2007-07-01/rate-plan_cpau_e-3_2007-07-01.jsonld

Idempotent: skips if the new TOUSchedule is already present.
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "ca" / "pou" / "cpau" / "e-3" / "versions" / "2007-07-01" / "rate-plan_cpau_e-3_2007-07-01.jsonld"

# CPAU observes 8 federal holidays (matches E-4 TOU and E-7 TOU calendars)
HOLIDAY_CALENDAR = {
    "@type": "urpx:HolidayCalendar",
    "@id": "cpau:e3-holidays",
    "urpx:hasHoliday": [
        {"@type": "urpx:Holiday", "@id": "cpau:e3-holiday-new-years",
         "urpx:holidayName": "New Year's Day", "urpx:holidayRule": "January 1 (legally observed)"},
        {"@type": "urpx:Holiday", "@id": "cpau:e3-holiday-presidents",
         "urpx:holidayName": "Presidents' Day", "urpx:holidayRule": "Third Monday in February"},
        {"@type": "urpx:Holiday", "@id": "cpau:e3-holiday-memorial",
         "urpx:holidayName": "Memorial Day", "urpx:holidayRule": "Last Monday in May"},
        {"@type": "urpx:Holiday", "@id": "cpau:e3-holiday-independence",
         "urpx:holidayName": "Independence Day", "urpx:holidayRule": "July 4 (legally observed)"},
        {"@type": "urpx:Holiday", "@id": "cpau:e3-holiday-labor",
         "urpx:holidayName": "Labor Day", "urpx:holidayRule": "First Monday in September"},
        {"@type": "urpx:Holiday", "@id": "cpau:e3-holiday-veterans",
         "urpx:holidayName": "Veterans Day", "urpx:holidayRule": "November 11 (legally observed)"},
        {"@type": "urpx:Holiday", "@id": "cpau:e3-holiday-thanksgiving",
         "urpx:holidayName": "Thanksgiving Day", "urpx:holidayRule": "Fourth Thursday in November"},
        {"@type": "urpx:Holiday", "@id": "cpau:e3-holiday-christmas",
         "urpx:holidayName": "Christmas Day", "urpx:holidayRule": "December 25 (legally observed)"},
    ],
}


def time_bracket(suffix, start, end, season, day_type, include_holidays, include_non_holidays=None):
    out = {
        "@type": "urpx:TimeBracket",
        "@id": f"cpau:e3-tou-tb-{suffix}",
        "urpx:startTime": start,
        "urpx:endTime": end,
        "urpx:appliesInSeason": {"@id": f"cpau:e3-season-{season}"},
        "urpx:dayType": {"@id": f"urpx:{day_type}"},
        "urpx:includeHolidays": include_holidays,
    }
    if include_non_holidays is not None:
        out["urpx:includeNonHolidays"] = include_non_holidays
    return out


# Section C.2 TOU windows:
#   Summer Peak: 12 noon to 6 PM Mon-Fri (except holidays)
#   Summer Mid-Peak: 8 AM to 12 noon AND 6 PM to 9 PM Mon-Fri (except holidays)
#   Summer Off-Peak: 9 PM to 8 AM Mon-Fri + holidays + weekends
#   Winter Peak: 8 AM to 9 PM Mon-Fri (except holidays)
#   Winter Off-Peak: 9 PM to 8 AM Mon-Fri + holidays + weekends
TOU_SCHEDULE = {
    "@type": "urpx:TOUSchedule",
    "@id": "cpau:e3-tou-schedule",
    "urpx:name": "E-3 Section C.2 buyback TOU schedule",
    "urpx:referencesMetricInput": {"@id": "cpau:e3-mi-energy-export"},
    "urpx:hasCalendar": {"@id": "cpau:e3-holidays"},
    "urpx:hasTOUTier": [{
        "@type": "urpx:TOUTier",
        "@id": "cpau:e3-tou-tier-1",
        "urpx:touTierNumber": 1,
        "urpx:hasTOUPeriod": [
            {
                "@type": "urpx:TOUPeriod",
                "@id": "cpau:e3-tou-period-summer-peak",
                "urpx:name": "Summer Peak (Section C.2)",
                "urpx:touPeriodNumber": 1,
                "urpx:hasTimeBracket": [
                    time_bracket("summer-peak", "12:00:00", "18:00:00",
                                 "summer", "weekdayDays", False, True),
                ],
            },
            {
                "@type": "urpx:TOUPeriod",
                "@id": "cpau:e3-tou-period-summer-mid-peak",
                "urpx:name": "Summer Mid-Peak (Section C.2)",
                "urpx:touPeriodNumber": 2,
                "urpx:hasTimeBracket": [
                    time_bracket("summer-mid-peak-morning", "08:00:00", "12:00:00",
                                 "summer", "weekdayDays", False, True),
                    time_bracket("summer-mid-peak-evening", "18:00:00", "21:00:00",
                                 "summer", "weekdayDays", False, True),
                ],
            },
            {
                "@type": "urpx:TOUPeriod",
                "@id": "cpau:e3-tou-period-summer-off-peak",
                "urpx:name": "Summer Off-Peak (Section C.2)",
                "urpx:touPeriodNumber": 3,
                "urpx:hasTimeBracket": [
                    time_bracket("summer-off-peak-night", "00:00:00", "08:00:00",
                                 "summer", "weekdayDays", False, True),
                    time_bracket("summer-off-peak-late-evening", "21:00:00", "00:00:00",
                                 "summer", "weekdayDays", False, True),
                    time_bracket("summer-off-peak-weekday-holiday", "00:00:00", "00:00:00",
                                 "summer", "weekdayDays", True, False),
                    {
                        "@type": "urpx:TimeBracket",
                        "@id": "cpau:e3-tou-tb-summer-off-peak-weekend",
                        "urpx:startTime": "00:00:00",
                        "urpx:endTime": "00:00:00",
                        "urpx:appliesInSeason": {"@id": "cpau:e3-season-summer"},
                        "urpx:dayType": {"@id": "urpx:weekendDays"},
                    },
                ],
            },
            {
                "@type": "urpx:TOUPeriod",
                "@id": "cpau:e3-tou-period-winter-peak",
                "urpx:name": "Winter Peak (Section C.2)",
                "urpx:touPeriodNumber": 4,
                "urpx:hasTimeBracket": [
                    time_bracket("winter-peak", "08:00:00", "21:00:00",
                                 "winter", "weekdayDays", False, True),
                ],
            },
            {
                "@type": "urpx:TOUPeriod",
                "@id": "cpau:e3-tou-period-winter-off-peak",
                "urpx:name": "Winter Off-Peak (Section C.2)",
                "urpx:touPeriodNumber": 5,
                "urpx:hasTimeBracket": [
                    time_bracket("winter-off-peak-night", "00:00:00", "08:00:00",
                                 "winter", "weekdayDays", False, True),
                    time_bracket("winter-off-peak-late-evening", "21:00:00", "00:00:00",
                                 "winter", "weekdayDays", False, True),
                    time_bracket("winter-off-peak-weekday-holiday", "00:00:00", "00:00:00",
                                 "winter", "weekdayDays", True, False),
                    {
                        "@type": "urpx:TimeBracket",
                        "@id": "cpau:e3-tou-tb-winter-off-peak-weekend",
                        "urpx:startTime": "00:00:00",
                        "urpx:endTime": "00:00:00",
                        "urpx:appliesInSeason": {"@id": "cpau:e3-season-winter"},
                        "urpx:dayType": {"@id": "urpx:weekendDays"},
                    },
                ],
            },
        ],
    }],
}


def energy_pd(suffix, period_name, season, tou_num):
    """5 energy buyback PriceDefinitions, one per TOU period."""
    return {
        "@type": "urpx:PriceDefinition",
        "@id": f"cpau:e3-pd-c2-energy-{suffix}",
        "urpx:name": f"Energy Buyback {period_name} (Section C.2 with interval meter)",
        "urpx:chargeType": {"@id": "urpx:creditEnergy"},
        "urpx:chargeCategory": {"@id": "urpx:discount"},
        "urpx:billPortion": {"@id": "urpx:bundledPortion"},
        "urpx:appliesInSeason": {"@id": f"cpau:e3-season-{season}"},
        "urpx:touPeriodNumber": tou_num,
        "urpx:referencesLedger": {"@id": "cpau:e3-ledger-energy-buyback"},
        "urpx:referencesMetricInput": {"@id": "cpau:e3-mi-energy-export"},
    }


def firm_capacity_pd(suffix, period_name, season, tou_num):
    """2 firm-capacity PriceDefinitions, Peak periods only."""
    return {
        "@type": "urpx:PriceDefinition",
        "@id": f"cpau:e3-pd-c2-firm-capacity-{suffix}",
        "urpx:name": f"Firm Capacity Credit {period_name} (Section C.2 with interval meter)",
        "urpx:chargeType": {"@id": "urpx:creditGeneration"},
        "urpx:chargeCategory": {"@id": "urpx:discount"},
        "urpx:billPortion": {"@id": "urpx:bundledPortion"},
        "urpx:appliesInSeason": {"@id": f"cpau:e3-season-{season}"},
        "urpx:touPeriodNumber": tou_num,
        "urpx:hasApplicabilityGroup": {
            "@type": "urpx:ApplicabilityGroup",
            "@id": f"cpau:e3-ag-c2-firm-power-{suffix}",
            "urpx:name": "Firm power customers only",
            "urpx:hasConditionExpression": {
                "@type": "urpx:ConditionExpression",
                "@id": f"cpau:e3-cx-c2-firm-power-{suffix}",
                "urpx:rootNode": {
                    "@type": "urpx:ComparisonNode",
                    "@id": f"cpau:e3-cn-c2-firm-power-{suffix}",
                    "urpx:operator": {"@id": "urpx:equalsOperator"},
                    "urpx:leftOperand": {
                        "@type": "urpx:CustomOperandNode",
                        "urpx:customConditionProperty": "powerType",
                    },
                    "urpx:rightOperand": {
                        "@type": "urpx:CustomOperandNode",
                        "urpx:stringValue": "Firm",
                    },
                },
            },
        },
        "urpx:baseQuantity": "1",
        "urpx:hasCalculationMethod": {
            "@type": "urpx:CalculationMethod",
            "@id": f"cpau:e3-pd-c2-firm-capacity-{suffix}-cm",
            "urpx:intervalDuration": "P1M",
        },
        "urpx:referencesLedger": {"@id": "cpau:e3-ledger-firm-capacity-credit"},
        "urpx:referencesMetricInput": {"@id": "cpau:e3-mi-firm-capacity"},
    }


NEW_PDS = [
    energy_pd("summer-peak", "Summer Peak", "summer", 1),
    energy_pd("summer-mid-peak", "Summer Mid-Peak", "summer", 2),
    energy_pd("summer-off-peak", "Summer Off-Peak", "summer", 3),
    energy_pd("winter-peak", "Winter Peak", "winter", 4),
    energy_pd("winter-off-peak", "Winter Off-Peak", "winter", 5),
    firm_capacity_pd("summer-peak", "Summer Peak", "summer", 1),
    firm_capacity_pd("winter-peak", "Winter Peak", "winter", 4),
]


def applicability_group(suffix, has_meter):
    """Build an ApplicabilityGroup gating on hasIntervalMeter == has_meter."""
    return {
        "@type": "urpx:ApplicabilityGroup",
        "@id": f"cpau:e3-ag-{suffix}",
        "urpx:name": f"Customers {'with' if has_meter else 'without'} interval meter",
        "urpx:hasConditionExpression": {
            "@type": "urpx:ConditionExpression",
            "@id": f"cpau:e3-cx-{suffix}",
            "urpx:rootNode": {
                "@type": "urpx:ComparisonNode",
                "@id": f"cpau:e3-cn-{suffix}",
                "urpx:operator": {"@id": "urpx:equalsOperator"},
                "urpx:leftOperand": {
                    "@type": "urpx:CustomOperandNode",
                    "urpx:customConditionProperty": "hasIntervalMeter",
                },
                "urpx:rightOperand": {
                    "@type": "urpx:CustomOperandNode",
                    "urpx:booleanValue": has_meter,
                },
            },
        },
    }


# Section C.2 prices:
#   Firm Summer Off-Peak:    $0.07152/kWh
#   Firm Summer Mid-Peak:    $0.08824/kWh
#   Firm Summer Peak:        $4.32/kW + $0.09566/kWh
#   Firm Winter Off-Peak:    $0.07361/kWh
#   Firm Winter Peak:        $4.32/kW + $0.08595/kWh
#   Non-Firm: same kWh rates, no capacity credit
NEW_PRICES = [
    {"@type": "urpx:Price", "@id": "cpau:e3-price-c2-energy-summer-peak",
     "urpx:name": "Energy Buyback Summer Peak (Section C.2)",
     "urpx:referencesPriceDefinition": {"@id": "cpau:e3-pd-c2-energy-summer-peak"},
     "urpx:startDate": "2007-07-01", "urpx:unitPrice": "0.09566"},
    {"@type": "urpx:Price", "@id": "cpau:e3-price-c2-energy-summer-mid-peak",
     "urpx:name": "Energy Buyback Summer Mid-Peak (Section C.2)",
     "urpx:referencesPriceDefinition": {"@id": "cpau:e3-pd-c2-energy-summer-mid-peak"},
     "urpx:startDate": "2007-07-01", "urpx:unitPrice": "0.08824"},
    {"@type": "urpx:Price", "@id": "cpau:e3-price-c2-energy-summer-off-peak",
     "urpx:name": "Energy Buyback Summer Off-Peak (Section C.2)",
     "urpx:referencesPriceDefinition": {"@id": "cpau:e3-pd-c2-energy-summer-off-peak"},
     "urpx:startDate": "2007-07-01", "urpx:unitPrice": "0.07152"},
    {"@type": "urpx:Price", "@id": "cpau:e3-price-c2-energy-winter-peak",
     "urpx:name": "Energy Buyback Winter Peak (Section C.2)",
     "urpx:referencesPriceDefinition": {"@id": "cpau:e3-pd-c2-energy-winter-peak"},
     "urpx:startDate": "2007-07-01", "urpx:unitPrice": "0.08595"},
    {"@type": "urpx:Price", "@id": "cpau:e3-price-c2-energy-winter-off-peak",
     "urpx:name": "Energy Buyback Winter Off-Peak (Section C.2)",
     "urpx:referencesPriceDefinition": {"@id": "cpau:e3-pd-c2-energy-winter-off-peak"},
     "urpx:startDate": "2007-07-01", "urpx:unitPrice": "0.07361"},
    {"@type": "urpx:Price", "@id": "cpau:e3-price-c2-firm-capacity-summer-peak",
     "urpx:name": "Firm Capacity Credit Summer Peak (Section C.2)",
     "urpx:referencesPriceDefinition": {"@id": "cpau:e3-pd-c2-firm-capacity-summer-peak"},
     "urpx:startDate": "2007-07-01", "urpx:unitPrice": "4.32"},
    {"@type": "urpx:Price", "@id": "cpau:e3-price-c2-firm-capacity-winter-peak",
     "urpx:name": "Firm Capacity Credit Winter Peak (Section C.2)",
     "urpx:referencesPriceDefinition": {"@id": "cpau:e3-pd-c2-firm-capacity-winter-peak"},
     "urpx:startDate": "2007-07-01", "urpx:unitPrice": "4.32"},
]


def find(node, predicate):
    if predicate(node):
        return node
    if isinstance(node, dict):
        for v in node.values():
            r = find(v, predicate)
            if r is not None: return r
    elif isinstance(node, list):
        for v in node:
            r = find(v, predicate)
            if r is not None: return r
    return None


def main():
    with open(TARGET) as fh:
        data = json.load(fh)

    # Idempotency check
    if find(data, lambda n: isinstance(n, dict) and n.get("@id") == "cpau:e3-tou-schedule"):
        print(f"already added (skipping): {TARGET}")
        return

    # Locate the PlanElements + BillingModel + Prices containers
    plan_elements = find(data, lambda n: isinstance(n, dict) and n.get("@id") == "cpau:e3-plan-elements")
    billing_model = find(data, lambda n: isinstance(n, dict) and n.get("@id") == "cpau:e3-billing-model")
    prices_container = find(data, lambda n: isinstance(n, dict) and n.get("@id") == "cpau:e3-prices")
    existing_price_set = find(data, lambda n: isinstance(n, dict) and n.get("@id") == "cpau:e3-price-set")
    assert plan_elements and billing_model and prices_container and existing_price_set

    # 1. Insert HolidayCalendar in PlanElements (preserve key order: insert after hasSeasons)
    new_pe = {}
    for k, v in plan_elements.items():
        new_pe[k] = v
        if k == "urpx:hasSeasons":
            new_pe["urpx:hasHolidayCalendar"] = HOLIDAY_CALENDAR
    plan_elements.clear()
    plan_elements.update(new_pe)

    # 2. Append 7 new PriceDefinitions to BillingModel.hasPriceDefinition
    billing_model["urpx:hasPriceDefinition"].extend(NEW_PDS)

    # 3. Append hasTOUSchedule to BillingModel (after hasPriceDefinition)
    billing_model["urpx:hasTOUSchedule"] = [TOU_SCHEDULE]

    # 4. Refactor existing PriceSet: rename + add ApplicabilityGroup gating on hasIntervalMeter=false
    # Insert hasApplicabilityGroup before hasPrice for readability
    existing_price_set["urpx:name"] = "Section C.1 prices (without interval meter)"
    new_eps = {}
    inserted = False
    for k, v in existing_price_set.items():
        if k == "urpx:hasPrice" and not inserted:
            new_eps["urpx:hasApplicabilityGroup"] = applicability_group("without-interval-meter", False)
            inserted = True
        new_eps[k] = v
    if not inserted:
        new_eps["urpx:hasApplicabilityGroup"] = applicability_group("without-interval-meter", False)
    existing_price_set.clear()
    existing_price_set.update(new_eps)

    # 5. Append a new PriceSet to Prices.hasPriceSet for the with-interval-meter case
    new_price_set = {
        "@type": "urpx:PriceSet",
        "@id": "cpau:e3-price-set-c2",
        "urpx:name": "Section C.2 prices (with interval meter, TOU)",
        "urpx:hasApplicabilityGroup": applicability_group("with-interval-meter", True),
        "urpx:hasPrice": NEW_PRICES,
    }
    prices_container["urpx:hasPriceSet"].append(new_price_set)

    with open(TARGET, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"added Section C.2 to: {TARGET}")
    print(f"  +1 HolidayCalendar (8 holidays)")
    print(f"  +1 TOUSchedule (5 TOUPeriods, 12 TimeBrackets)")
    print(f"  +{len(NEW_PDS)} PriceDefinitions ({sum(1 for p in NEW_PDS if 'energy' in p['@id'])} energy + {sum(1 for p in NEW_PDS if 'firm-capacity' in p['@id'])} firm-capacity)")
    print(f"  +1 ApplicabilityGroup on existing PriceSet (without-interval-meter)")
    print(f"  +1 new PriceSet with ApplicabilityGroup + {len(NEW_PRICES)} Prices")


if __name__ == "__main__":
    main()
