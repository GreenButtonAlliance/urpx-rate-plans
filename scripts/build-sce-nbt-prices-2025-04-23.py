#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Emit per-cell Export Compensation Rate Delivery Prices into the SCE NBT
2025-04-23 RatePlanModifier filing.

Consumes /tmp/sce-nbt-eec-values.json (produced by extract-sce-nbt-eec-values.py)
and updates ca/iou/sce/nbt/versions/2025-04-23/rate-plan-modifier_sce_nbt_*.jsonld
in place, appending up to 2,880 Price entities (5 vintages × 576 cells)
for the Delivery Component only. Generation Component is deferred — SCE does
NOT publish Generation EEC via MIDAS (USCA-XXSC-* RINs don't exist; only the
Delivery USCA-SCXX-* family is published).

Each Price carries its MIDAS RIN in urpx:name for cross-reference. SCE uses
per-base-RatePlan RIN families — TOU-D-PRIME-NBT codes 0602-0606 for
residential. For NBT26 vintage, only Jan-May data may be populated as of
extraction time (the script emits whatever cells the extractor populated).

Preserves the existing 2 ACC Plus 2025-vintage Prices on re-run.
"""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path

FILING_DIR = Path(__file__).resolve().parent.parent / "ca/iou/sce/nbt/versions/2025-04-23"
DEFAULT_VALUES_JSON = Path("/tmp/sce-nbt-eec-values.json")
DEFAULT_JSONLD = FILING_DIR / "rate-plan-modifier_sce_nbt_2025-04-23.jsonld"

MONTHS_LONG = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]
MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Vintage labels — SCE has "non-vintaged" plus 23/24/25/26
VINTAGE_ORDER = ["non-vintaged", "23", "24", "25", "26"]
DAYTYPES = ["weekday", "weekend"]

PD_IRI = {
    "delivery": "sce:nbt-pd-export-rate-delivery",
    "generation": "sce:nbt-pd-export-rate-generation",
}

DAYTYPE_ENUM = {
    "weekday": "urpx:weekdayDays",
    "weekend": "urpx:weekendDays",
}


def vintage_slug(v: str) -> str:
    return "nv" if v == "non-vintaged" else v


def vintage_label(v: str) -> str:
    return "non-vintaged" if v == "non-vintaged" else f"NBT{v}"


def tou_iri(hour: int, daytype: str) -> str:
    return f"sce:nbt-tou-h{hour:02d}-{daytype}"


def ar_iri(month_idx: int, vintage: str) -> str:
    return f"sce:nbt-ar-m{month_idx + 1:02d}-v{vintage_slug(vintage)}"


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
            "@id": f"sce:nbt-tb-h{hour:02d}-{daytype}",
            "urpx:startTime": f"{hour:02d}:00:00",
            "urpx:endTime": end_time,
            "urpx:dayType": {"@id": DAYTYPE_ENUM[daytype]},
        }],
    }


def make_applicability_rule(month_idx: int, vintage: str) -> dict:
    vlabel = vintage_label(vintage)
    if vintage == "non-vintaged":
        descr = f"{MONTHS_LONG[month_idx]} usage for non-vintaged NBT customers (no lock-in; current-year ACC values)"
    else:
        descr = (f"{MONTHS_LONG[month_idx]} usage for SCE NBT vintage {vlabel} customers "
                 f"(PTO in 20{vintage}; 9-year lock-in on TOU-D-PRIME-NBT export Delivery)")
    return {
        "@type": "urpx:ApplicabilityRule",
        "@id": ar_iri(month_idx, vintage),
        "urpx:name": descr,
        "urpx:month": [f"--{month_idx + 1:02d}"],
        "urpx:hasConditionExpression": {
            "@type": "urpx:ConditionExpression",
            "@id": f"sce:nbt-cx-m{month_idx + 1:02d}-v{vintage_slug(vintage)}",
            "urpx:rootNode": {
                "@type": "urpx:ComparisonNode",
                "@id": f"sce:nbt-cn-m{month_idx + 1:02d}-v{vintage_slug(vintage)}",
                "urpx:operator": {"@id": "urpx:equalsOperator"},
                "urpx:leftOperand": {
                    "@type": "urpx:CustomOperandNode",
                    "urpx:customConditionProperty": "NBT Vintage Label",
                },
                "urpx:rightOperand": {
                    "@type": "urpx:CustomOperandNode",
                    "urpx:stringValue": vlabel,
                },
            },
        },
    }


def emit_prices(values: dict) -> list[dict]:
    tou_defined = set()
    ar_defined = set()
    tou_counter = 0
    prices = []
    skipped = 0

    for vintage in VINTAGE_ORDER:
        if vintage not in values:
            continue
        v_data = values[vintage]
        rate_name = v_data["rate_name"]
        scxx_rin = v_data["rin"]
        scsc_rin = v_data.get("scsc_rin")
        delivery_vals = v_data["values"]
        generation_vals = v_data.get("generation_values")
        for daytype in DAYTYPES:
            for hour in range(24):
                for month_idx in range(12):
                    month_short = MONTHS_SHORT[month_idx]
                    for component in ("delivery", "generation"):
                        comp_vals = delivery_vals if component == "delivery" else generation_vals
                        if comp_vals is None:
                            continue
                        raw_val = comp_vals[month_short][daytype][hour]
                        if raw_val is None:
                            skipped += 1
                            continue
                        signed_val = "0.000000" if float(raw_val) == 0 else f"-{raw_val}"
                        comp_label = "Delivery" if component == "delivery" else "Generation"
                        # RIN attribution: Delivery = SCXX directly; Generation = derived from
                        # SCSC (combined) − SCXX (delivery), so we cite both source RINs
                        rin_note = scxx_rin if component == "delivery" else f"{scsc_rin} − {scxx_rin}"
                        comp_slug = "del" if component == "delivery" else "gen"
                        price = OrderedDict([
                            ("@type", "urpx:Price"),
                            ("@id",
                             f"sce:nbt-price-v{vintage_slug(vintage)}-{comp_slug}-m{month_idx + 1:02d}-h{hour:02d}-{daytype}"),
                            ("urpx:referencesPriceDefinition", {"@id": PD_IRI[component]}),
                            ("urpx:startDate",
                             "2026-01-01" if vintage == "non-vintaged" else f"20{vintage}-01-01"),
                            ("urpx:name",
                             f"{rate_name} {comp_label} Component (MIDAS RIN: {rin_note}) — "
                             f"{MONTHS_LONG[month_idx]} {daytype}, "
                             f"{hour:02d}:00-{(hour + 1) % 24:02d}:00 PT"),
                            ("urpx:unitPrice", signed_val),
                        ])
                        tou_key = (hour, daytype)
                        if tou_key not in tou_defined:
                            tou_defined.add(tou_key)
                            tou_counter += 1
                            price["urpx:referencesTouPeriod"] = make_tou_period(hour, daytype, tou_counter)
                        else:
                            price["urpx:referencesTouPeriod"] = {"@id": tou_iri(hour, daytype)}
                        ar_key = (month_idx, vintage)
                        if ar_key not in ar_defined:
                            ar_defined.add(ar_key)
                            price["urpx:hasApplicabilityRule"] = make_applicability_rule(month_idx, vintage)
                        else:
                            price["urpx:hasApplicabilityRule"] = {"@id": ar_iri(month_idx, vintage)}
                        prices.append(price)
    if skipped:
        print(f"  skipped {skipped} cells with no MIDAS data (NBT26 partial-year coverage)")
    return prices


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--values", type=Path, default=DEFAULT_VALUES_JSON)
    parser.add_argument("--jsonld", type=Path, default=DEFAULT_JSONLD)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    values = json.load(args.values.open())
    print(f"Loaded values for vintages: {sorted(values.keys())}")

    doc = json.load(args.jsonld.open(), object_pairs_hook=OrderedDict)

    # Add xsd:time typing for startTime/endTime
    ctx = doc.get("@context", {})
    if "urpx:startTime" not in ctx:
        ctx["urpx:startTime"] = {"@type": "xsd:time"}
    if "urpx:endTime" not in ctx:
        ctx["urpx:endTime"] = {"@type": "xsd:time"}

    prices_container = doc["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"]["urpx:hasPrices"]
    existing = prices_container["urpx:hasPrice"]
    # Preserve ACC Plus prices, strip any previously-emitted Delivery/Generation cells
    existing = [p for p in existing if "acc-plus" in p.get("@id", "") and "-del-" not in p.get("@id", "") and "-gen-" not in p.get("@id", "")]
    print(f"Preserved Prices (ACC Plus): {len(existing)}")

    new_prices = emit_prices(values)
    print(f"Generated new Delivery Prices: {len(new_prices)}")
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
