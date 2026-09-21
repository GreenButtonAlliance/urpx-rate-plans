#!/usr/bin/env python3
"""Emit per-cell Export Compensation Rate Prices into the SDG&E NBT 2025-01-27
RatePlanModifier filing.

Consumes /tmp/sdge-nbt-eec-values.json (produced by extract-sdge-nbt-eec-values.py)
and updates ca/iou/sdge/nbt/versions/2025-01-27/rate-plan-modifier_sdge_nbt_*.jsonld
in place, appending 5,760 new Price entities to urpx:hasPrice[] (576 cells per
vintage × 2 components × 5 vintages: NBT23 / NBT24 / NBT25 / NBT26 / NBT00).

Each Price carries its CEC MIDAS RIN (Rate Identification Number) in the
urpx:name field for cross-reference (e.g. "USCA-XXSD-NB25-0000" for Generation
Component vintage NBT25). 10 distinct RINs total across the 5 × 2 = 10
(vintage, component) pairs.

Vocabulary use (same as PG&E NBT build):
  - 48 unique urpx:TOUPeriod (24 hours × 2 day-types)
  - 60 unique urpx:ApplicabilityRule (12 months × 5 vintages, each carrying
    urpx:month + a vintage-gating ConditionExpression)
  - Each Price references one PriceDefinition (Generation or Delivery), one
    TOUPeriod, one ApplicabilityRule, plus negated unitPrice
"""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path

FILING_DIR = Path("ca/iou/sdge/nbt/versions/2025-01-27")
DEFAULT_VALUES_JSON = Path("/tmp/sdge-nbt-eec-values.json")
DEFAULT_JSONLD = FILING_DIR / "rate-plan-modifier_sdge_nbt_2025-01-27.jsonld"

MONTHS_LONG = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]
MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

VINTAGES = ["23", "24", "25", "26", "00"]  # NBT23 through NBT26 + NBT00 (no lock-in)
DAYTYPES = ["weekday", "weekend"]
COMPONENTS = ["generation", "delivery"]

PD_IRI = {
    "generation": "sdge:nbt-pd-export-rate-generation",
    "delivery": "sdge:nbt-pd-export-rate-delivery",
}

DAYTYPE_ENUM = {
    "weekday": "urpx:weekdayDays",
    "weekend": "urpx:weekendDays",
}


def tou_iri(hour: int, daytype: str) -> str:
    return f"sdge:nbt-tou-h{hour:02d}-{daytype}"


def ar_iri(month_idx: int, vintage: str) -> str:
    return f"sdge:nbt-ar-m{month_idx + 1:02d}-v{vintage}"


def make_tou_period(hour: int, daytype: str, tou_number: int) -> dict:
    if hour == 23:
        end_time = "23:59:59"
    else:
        end_time = f"{hour + 1:02d}:00:00"
    daytype_label = "Weekday" if daytype == "weekday" else "Weekend/Holiday"
    return {
        "@type": "urpx:TOUPeriod",
        "@id": tou_iri(hour, daytype),
        "urpx:name": f"Hour {hour:02d}:00-{end_time[:5]} {daytype_label}",
        "urpx:touPeriodNumber": tou_number,
        "urpx:hasTimeBracket": [{
            "@type": "urpx:TimeBracket",
            "@id": f"sdge:nbt-tb-h{hour:02d}-{daytype}",
            "urpx:startTime": f"{hour:02d}:00:00",
            "urpx:endTime": end_time,
            "urpx:dayType": {"@id": DAYTYPE_ENUM[daytype]},
        }],
    }


def make_applicability_rule(month_idx: int, vintage: str) -> dict:
    vintage_label = f"NBT{vintage}"
    if vintage == "00":
        descr = f"{MONTHS_LONG[month_idx]} usage for NBT00 customers (no lock-in; current-year ACC values)"
    else:
        descr = (f"{MONTHS_LONG[month_idx]} usage for {vintage_label} vintage customers "
                 f"(applications submitted in 20{vintage}; 9-year lock-in from PTO)")
    return {
        "@type": "urpx:ApplicabilityRule",
        "@id": ar_iri(month_idx, vintage),
        "urpx:name": descr,
        "urpx:month": [f"--{month_idx + 1:02d}"],
        "urpx:hasConditionExpression": {
            "@type": "urpx:ConditionExpression",
            "@id": f"sdge:nbt-cx-m{month_idx + 1:02d}-v{vintage}",
            "urpx:rootNode": {
                "@type": "urpx:ComparisonNode",
                "@id": f"sdge:nbt-cn-m{month_idx + 1:02d}-v{vintage}",
                "urpx:operator": {"@id": "urpx:equalsOperator"},
                "urpx:leftOperand": {
                    "@type": "urpx:CustomOperandNode",
                    "urpx:customConditionProperty": "NBT Vintage Label",
                },
                "urpx:rightOperand": {
                    "@type": "urpx:CustomOperandNode",
                    "urpx:stringValue": vintage_label,
                },
            },
        },
    }


def emit_prices(values: dict) -> list[dict]:
    """Emit Price entities with first-use inline TOUPeriods + ApplicabilityRules."""
    tou_defined = set()
    ar_defined = set()
    tou_counter = 0
    prices = []

    for vintage in VINTAGES:
        if vintage not in values:
            print(f"  warning: vintage NBT{vintage} not in extracted values; skipping")
            continue
        v_data = values[vintage]
        for component in COMPONENTS:
            rin = v_data[component]["rin"]
            comp_values = v_data[component]["values"]
            for daytype in DAYTYPES:
                for hour in range(24):
                    for month_idx in range(12):
                        month_short = MONTHS_SHORT[month_idx]
                        raw_val = comp_values[month_short][daytype][hour]
                        # Credit polarity — negate (matches PG&E NBT pattern)
                        signed_val = "0.000000" if float(raw_val) == 0 else f"-{raw_val}"
                        component_label = "Generation" if component == "generation" else "Delivery"

                        price = OrderedDict([
                            ("@type", "urpx:Price"),
                            ("@id",
                             f"sdge:nbt-price-v{vintage}-{component[:3]}-m{month_idx + 1:02d}-h{hour:02d}-{daytype}"),
                            ("urpx:referencesPriceDefinition", {"@id": PD_IRI[component]}),
                            ("urpx:startDate",
                             "2026-01-01" if vintage == "00" else f"20{vintage}-01-01"),
                            ("urpx:name",
                             f"NBT{vintage} {component_label} Component (MIDAS RIN: {rin}) — "
                             f"{MONTHS_LONG[month_idx]} {daytype}, "
                             f"{hour:02d}:00-{(hour + 1) % 24:02d}:00 PT"),
                            ("urpx:unitPrice", signed_val),
                        ])

                        # TOUPeriod first-use inline
                        tou_key = (hour, daytype)
                        if tou_key not in tou_defined:
                            tou_defined.add(tou_key)
                            tou_counter += 1
                            price["urpx:referencesTouPeriod"] = make_tou_period(hour, daytype, tou_counter)
                        else:
                            price["urpx:referencesTouPeriod"] = {"@id": tou_iri(hour, daytype)}

                        # ApplicabilityRule first-use inline
                        ar_key = (month_idx, vintage)
                        if ar_key not in ar_defined:
                            ar_defined.add(ar_key)
                            price["urpx:hasApplicabilityRule"] = make_applicability_rule(month_idx, vintage)
                        else:
                            price["urpx:hasApplicabilityRule"] = {"@id": ar_iri(month_idx, vintage)}

                        prices.append(price)

    return prices


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--values", type=Path, default=DEFAULT_VALUES_JSON)
    parser.add_argument("--jsonld", type=Path, default=DEFAULT_JSONLD)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    values = json.load(args.values.open())
    print(f"Loaded values for vintages: {sorted(values.keys())}")
    for v in sorted(values.keys()):
        for c in ("generation", "delivery"):
            print(f"  NBT{v} {c}: RIN = {values[v][c]['rin']}")

    doc = json.load(args.jsonld.open(), object_pairs_hook=OrderedDict)

    # Ensure @context already types startTime/endTime as xsd:time (added at SDG&E shell time)
    ctx = doc.get("@context", {})
    if "urpx:startTime" not in ctx:
        ctx["urpx:startTime"] = {"@type": "xsd:time"}
    if "urpx:endTime" not in ctx:
        ctx["urpx:endTime"] = {"@type": "xsd:time"}

    prices_container = doc["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"]["urpx:hasPrices"]
    existing = prices_container["urpx:hasPrice"]
    # Strip any previously-emitted per-cell Prices (idempotent re-run)
    existing = [p for p in existing if "acc-plus" in p.get("@id", "")]
    print(f"Preserved Prices (ACC Plus if any): {len(existing)}")

    new_prices = emit_prices(values)
    print(f"Generated new Prices: {len(new_prices)} (expected 5760 for 5 vintages × 1152)")

    prices_container["urpx:hasPrice"] = existing + new_prices

    if args.dry_run:
        print("--dry-run; not writing.")
        return

    with args.jsonld.open("w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    print(f"Wrote {args.jsonld} (now {len(existing) + len(new_prices)} total Prices)")


if __name__ == "__main__":
    main()
