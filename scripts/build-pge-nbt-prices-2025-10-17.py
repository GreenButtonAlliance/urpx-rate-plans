#!/usr/bin/env python3
"""Emit per-cell Export Compensation Rate Prices into the PG&E NBT 2025-10-17
RatePlanModifier filing.

Consumes /tmp/pge-nbt-eec-values.json (produced by extract-nbt-eec-values.py)
and updates ca/iou/pge/nbt/versions/2025-10-17/rate-plan-modifier_pge_nbt_*.jsonld
in place, appending 4,608 new Price entities to urpx:hasPrice[] (576 cells per
vintage × 2 components × 4 vintages = 4,608).

Vocabulary use:
  - 48 unique urpx:TOUPeriod (24 hours × 2 day-types), defined inline at the
    first Price that references each one; subsequent Prices reference by @id.
  - 48 unique urpx:ApplicabilityRule (12 months × 4 vintages), each carrying
    urpx:month + a vintage-gating ConditionExpression. Defined inline at first
    use; subsequent references use @id.
  - Each Price references one of the 2 existing PriceDefinitions (Generation
    or Delivery), one TOUPeriod, and one ApplicabilityRule, plus the unitPrice
    (negated — credits are negative-polarity, matching the ACC Plus pattern).

Iteration order: (vintage, daytype, hour, month, component). This drives which
Price hosts each first-use inline definition for deterministic output.
"""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from decimal import Decimal
from pathlib import Path

FILING_DIR = Path("ca/iou/pge/nbt/versions/2025-10-17")
DEFAULT_VALUES_JSON = Path("/tmp/pge-nbt-eec-values.json")
DEFAULT_JSONLD = FILING_DIR / "rate-plan-modifier_pge_nbt_2025-10-17.jsonld"

# When the corpus repo isn't named "urpx-rate-plans", REPO_ROOT will be wrong.
# Allow override via flag if needed.

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]

VINTAGES = ["2023", "2024", "2025", "2026"]
DAYTYPES = ["weekday", "weekend"]
COMPONENTS = ["produced", "delivered"]

PD_IRI = {
    "produced": "pge:nbt-pd-export-rate-generation",
    "delivered": "pge:nbt-pd-export-rate-delivery",
}

DAYTYPE_ENUM = {
    "weekday": "urpx:weekdayDays",
    "weekend": "urpx:weekendDays",
}


def tou_iri(hour: int, daytype: str) -> str:
    return f"pge:nbt-tou-h{hour:02d}-{daytype}"


def ar_iri(month_idx: int, vintage: str) -> str:
    # month_idx is 0-based
    return f"pge:nbt-ar-m{month_idx + 1:02d}-v{vintage}"


def make_tou_period(hour: int, daytype: str, tou_number: int) -> dict:
    # rdflib's xsd:time parser rejects "24:00:00" (XSD 1.0 strict 0-23 hours), so
    # encode the last hour's window as 23:00:00-23:59:59. Other hours use the
    # half-open [hh:00, (hh+1):00) convention.
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
            "@id": f"pge:nbt-tb-h{hour:02d}-{daytype}",
            "urpx:startTime": f"{hour:02d}:00:00",
            "urpx:endTime": end_time,
            "urpx:dayType": {"@id": DAYTYPE_ENUM[daytype]},
        }],
    }


def make_applicability_rule(month_idx: int, vintage: str) -> dict:
    return {
        "@type": "urpx:ApplicabilityRule",
        "@id": ar_iri(month_idx, vintage),
        "urpx:name": f"{MONTHS[month_idx]} usage for NBT customers with {vintage} interconnection vintage (9-year lock-in from PTO)",
        "urpx:month": [f"--{month_idx + 1:02d}"],
        "urpx:hasConditionExpression": {
            "@type": "urpx:ConditionExpression",
            "@id": f"pge:nbt-cx-m{month_idx + 1:02d}-v{vintage}",
            "urpx:rootNode": {
                "@type": "urpx:ComparisonNode",
                "@id": f"pge:nbt-cn-m{month_idx + 1:02d}-v{vintage}",
                "urpx:operator": {"@id": "urpx:equalsOperator"},
                "urpx:leftOperand": {
                    "@type": "urpx:CustomOperandNode",
                    "urpx:customConditionProperty": "NBT Interconnection Vintage Year",
                },
                "urpx:rightOperand": {
                    "@type": "urpx:CustomOperandNode",
                    "urpx:stringValue": vintage,
                },
            },
        },
    }


def emit_prices(values_by_vintage: dict) -> list[dict]:
    """Emit the 4,608 Price entities, with first-use inline TOUPeriods + ARs."""
    tou_defined = set()  # set of (hour, daytype)
    ar_defined = set()   # set of (month_idx, vintage)
    tou_counter = 0
    prices = []

    for vintage in VINTAGES:
        if vintage not in values_by_vintage:
            print(f"  warning: vintage {vintage} not in values; skipping")
            continue
        v = values_by_vintage[vintage]
        for daytype in DAYTYPES:
            for hour in range(24):
                cells = v[daytype][hour]  # list of 12 month-pairs
                for month_idx in range(12):
                    cell = cells[month_idx]
                    for component in COMPONENTS:
                        raw_val = cell[component]
                        # Credit polarity — negate value (matches the ACC Plus pattern).
                        # PG&E publishes positive $/kWh-exported; we encode as
                        # negative unitPrice to indicate credit toward customer bill.
                        signed_val = "0.00000" if Decimal(raw_val) == 0 else format(-Decimal(raw_val), "f")
                        price = OrderedDict([
                            ("@type", "urpx:Price"),
                            ("@id",
                             f"pge:nbt-price-v{vintage}-{component[:3]}-m{month_idx + 1:02d}-h{hour:02d}-{daytype}"),
                            ("urpx:referencesPriceDefinition", {"@id": PD_IRI[component]}),
                            ("urpx:startDate", f"{vintage}-01-01"),
                            ("urpx:name",
                             f"NBT {'Generation' if component == 'produced' else 'Delivery'} Component — "
                             f"{vintage} vintage, {MONTHS[month_idx]} {daytype}, "
                             f"{hour:02d}:00-{(hour + 1) % 24:02d}:00 PT"),
                            ("urpx:unitPrice", signed_val),
                        ])

                        # TOUPeriod: first-use inline, otherwise @id reference
                        tou_key = (hour, daytype)
                        if tou_key not in tou_defined:
                            tou_defined.add(tou_key)
                            tou_counter += 1
                            price["urpx:referencesTouPeriod"] = make_tou_period(hour, daytype, tou_counter)
                        else:
                            price["urpx:referencesTouPeriod"] = {"@id": tou_iri(hour, daytype)}

                        # ApplicabilityRule: first-use inline
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

    doc = json.load(args.jsonld.open(), object_pairs_hook=OrderedDict)

    # Ensure @context types startTime/endTime as xsd:time — required by SHACL for TimeBracket.
    ctx = doc.get("@context", {})
    if "urpx:startTime" not in ctx:
        ctx["urpx:startTime"] = {"@type": "xsd:time"}
    if "urpx:endTime" not in ctx:
        ctx["urpx:endTime"] = {"@type": "xsd:time"}

    prices_container = doc["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"]["urpx:hasPrices"]
    existing = prices_container["urpx:hasPrice"]
    # Strip any previously-emitted per-cell Prices (keep only ACC Plus). The 2 we want
    # to keep have @ids that include "acc-plus".
    existing = [p for p in existing if "acc-plus" in p.get("@id", "")]
    print(f"Existing ACC Plus Prices (preserved): {len(existing)} (should be 2)")

    new_prices = emit_prices(values)
    print(f"Generated new Prices: {len(new_prices)} (expected 4608)")

    prices_container["urpx:hasPrice"] = existing + new_prices

    if args.dry_run:
        print(f"--dry-run; not writing.")
        return

    with args.jsonld.open("w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    print(f"Wrote {args.jsonld} (now {len(existing) + len(new_prices)} total Prices)")


if __name__ == "__main__":
    main()
