#!/usr/bin/env python3
"""Extract EEC values from SDG&E's published per-vintage NBT pricing CSVs.

SDG&E publishes Solar Billing Plan / NBT Energy Export Credit values as
ZIP-archived CSVs at sdge.com/solar/solar-billing-plan/export-pricing — five
ZIPs total (one per vintage NBT23 / NBT24 / NBT25 / NBT26 / NBT00). Each CSV
unrolls a 20-year hourly forecast in flat tabular form. Per CPUC Resolution
E-5301, SDG&E publishes the full 20-year ACC forecast, but only the first
9 years of each vintage are CONTRACTUAL lock-in rates; years 10-20 are
illustrative forecasts and not used for billing.

For the corpus modeling, we extract one representative value per
(vintage, component, month, day-type, hour) cell — within each lock-in
period these values are constant per cell, so the first occurrence suffices.
For NBT00 (no lock-in vintage), we use the current-year values only.

CSV schema (per Solar Billing Plan Export Rates Readme.txt):
  RIN, RateName, DateStart, TimeStart, DateEnd, TimeEnd, DayStart, DayEnd,
  ValueName, Value, Unit, RateType, Sector

  - RIN: USCA-XXSD-NBxx-0000 (Generation) or USCA-SDXX-NBxx-0000 (Delivery)
  - RateName: NBT23 / NBT24 / NBT25 / NBT26 / NBT00
  - DayStart, DayEnd: 1-7 Mon-Sun, 8 Holiday
  - ValueName: e.g. "Apr Weekday HS0" — month + Weekday/Weekend + hour-start
  - Unit: "export $/kWh"

Output: JSON file with structure:
  { vintage:
      { "generation": { "rin": "USCA-XXSD-NBxx-0000",
                        "values": {month: {weekday: [24], weekend: [24]}} },
        "delivery":   { "rin": "USCA-SDXX-NBxx-0000",
                        "values": {...} } } }
RINs are captured per (vintage, component) so each emitted urpx:Price can
carry its MIDAS Rate Identification Number for cross-reference into the CEC
MIDAS system. RIN structure: USCA-[XXSD|SDXX]-NB{vintage}-0000 (10 RINs
total across 5 vintages × 2 components).
"""

import os
import argparse
import csv
import io
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path

ZIPS = {
    "23": "LY2023 NBT Pricing Upload MIDAS.zip",
    "24": "LY2024 NBT Pricing Upload MIDAS.zip",
    "25": "LY2025 NBT Pricing Upload MIDAS.zip",
    "26": "LY2026 NBT Pricing Upload MIDAS.zip",
    "00": "CurrentYearNBTPricingUploadMIDAS.zip",  # NBT00 — no lock-in
}

# RIN component prefixes
GENERATION_PREFIX = "USCA-XXSD"  # Generation EEC
DELIVERY_PREFIX   = "USCA-SDXX"  # Delivery EEC

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

VALUE_NAME_RE = re.compile(r"^([A-Za-z]+)\s+(Weekday|Weekend)\s+HS(\d{1,2})$")


def extract_vintage(zip_path, vintage_label):
    """Extract one vintage's lock-in-period values. Returns:
      { "generation": {month: {"weekday": [24], "weekend": [24]}}, "delivery": {...} }
    """
    # cells[component] = { "rin": str, "values": {month: {daytype: [24]}} }
    cells = {
        comp: {
            "rin": None,
            "values": {m: {"weekday": [None] * 24, "weekend": [None] * 24} for m in MONTHS},
        }
        for comp in ("generation", "delivery")
    }

    rate_name_target = f"NBT{vintage_label}"

    with zipfile.ZipFile(zip_path) as zf:
        # Find the CSV (one per ZIP)
        csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(csv_name) as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig"))
            header = next(reader)
            try:
                ix_rin = header.index("RIN")
                ix_rname = header.index("RateName")
                ix_vname = header.index("ValueName")
                ix_val = header.index("Value")
            except ValueError:
                raise RuntimeError(f"unexpected header: {header}")

            for row in reader:
                if row[ix_rname] != rate_name_target:
                    continue
                rin = row[ix_rin]
                if rin.startswith(GENERATION_PREFIX):
                    component = "generation"
                elif rin.startswith(DELIVERY_PREFIX):
                    component = "delivery"
                else:
                    continue
                # Capture RIN on first sight; check it's constant for this (vintage, component)
                if cells[component]["rin"] is None:
                    cells[component]["rin"] = rin
                elif cells[component]["rin"] != rin:
                    raise RuntimeError(
                        f"RIN inconsistency for {component} in {rate_name_target}: "
                        f"saw both {cells[component]['rin']!r} and {rin!r}"
                    )
                m = VALUE_NAME_RE.match(row[ix_vname])
                if not m:
                    continue
                month_str = m.group(1)
                if month_str not in cells[component]["values"]:
                    continue
                daytype = m.group(2).lower()
                hour = int(m.group(3))
                if not (0 <= hour < 24):
                    continue
                if cells[component]["values"][month_str][daytype][hour] is None:
                    # First occurrence wins (constant within lock-in)
                    cells[component]["values"][month_str][daytype][hour] = row[ix_val]

    # Sanity check: every cell populated, RIN captured
    for comp in ("generation", "delivery"):
        if cells[comp]["rin"] is None:
            raise RuntimeError(f"no RIN captured for {comp} in {rate_name_target}")
        for m in MONTHS:
            for dt in ("weekday", "weekend"):
                for h in range(24):
                    if cells[comp]["values"][m][dt][h] is None:
                        raise RuntimeError(f"missing cell: {comp} {m} {dt} hour={h}")
    return cells


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--zip-dir",
        default=os.environ.get("URPX_SOURCE_DATA", "") + "/sdge-nbt-eec-pricing",
    )
    parser.add_argument("--out", default="/tmp/sdge-nbt-eec-values.json")
    args = parser.parse_args()

    out = {}
    for vintage, fname in ZIPS.items():
        zip_path = Path(args.zip_dir) / fname
        print(f"Extracting NBT{vintage} from {fname}...")
        out[vintage] = extract_vintage(zip_path, vintage)

    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {args.out}")
    sample = out["25"]["generation"]
    print(f"  NBT25 Generation RIN: {sample['rin']}")
    print(f"  NBT25 Generation Jan Weekend hour=0: {sample['values']['Jan']['weekend'][0]}")
    print(f"  NBT25 Delivery Jul Weekday hour=17 (5pm): {out['25']['delivery']['values']['Jul']['weekday'][17]}")
    print(f"  NBT00 Generation Aug Weekend hour=20 (8pm): {out['00']['generation']['values']['Aug']['weekend'][20]}")


if __name__ == "__main__":
    main()
