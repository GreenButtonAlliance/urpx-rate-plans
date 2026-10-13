#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Augment /tmp/sce-nbt-eec-values.json with Generation EEC values derived
from the difference between bundled-service combined EEC and CCA-service
Delivery-only EEC published in MIDAS:

  Generation EEC = SCSC combined "Energy Export Credit"
                 - SCXX "Energy Export Credit Delivery"

Verified empirically (2026-05-29): SCSC NBT RIN payloads carry a single
combined "Energy Export Credit" ValueName (bundled customers receive both
components); SCXX NBT RIN payloads carry only "Energy Export Credit
Delivery" (CCA customers receive Delivery only from SCE, Generation from
their CCA). The values are consistent across multiple weeks within a
vintage's lock-in period, confirming the same underlying ACC source.

This script ADDS a "generation_values" key alongside "values" (Delivery)
in each vintage entry, with the same {month: {weekday: [24], weekend: [24]}}
structure. RIN for the bundled-service SCSC family is also captured for
downstream MIDAS xref.
"""

import argparse
import json
import os
import urllib.request
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MIDAS_API = "https://midasapi.energy.ca.gov/api"
UTC = ZoneInfo("UTC")
PT = ZoneInfo("America/Los_Angeles")

# SCSC bundled-service NBT RINs (TOU-D-PRIME) — combined EEC
SCSC_RINS = {
    "non-vintaged": "USCA-SCSC-0602-0000",
    "23":           "USCA-SCSC-0603-0000",
    "24":           "USCA-SCSC-0604-0000",
    "25":           "USCA-SCSC-0605-0000",
    "26":           "USCA-SCSC-0606-0000",
}

MONTH_NUM_TO_SHORT = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
                       7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}

DEFAULT_RANGES = {
    "non-vintaged": ("2025-01-01", "2025-12-31"),
    "23": ("2025-01-01", "2025-12-31"),
    "24": ("2025-01-01", "2025-12-31"),
    "25": ("2025-01-01", "2025-12-31"),
    "26": ("2026-01-01", "2026-12-31"),
}


def get_token():
    import base64
    creds = base64.b64encode(f"{os.environ['MIDAS_USERNAME']}:{os.environ['MIDAS_PASSWORD']}".encode()).decode()
    req = urllib.request.Request(f"{MIDAS_API}/Token", method="GET",
                                  headers={"Authorization": f"Basic {creds}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.headers.get("Token")


def fetch_historical(token, rid, start, end):
    url = f"{MIDAS_API}/HistoricalData?id={rid}&startdate={start}&enddate={end}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fetch_holidays(token, energy_code="SC"):
    req = urllib.request.Request(f"{MIDAS_API}/Holiday",
                                  headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return {h["DateOfHoliday"][:10] for h in data if h.get("EnergyCode") == energy_code}


def aggregate_combined(payload, holidays):
    """Mode-aggregate 'Energy Export Credit' (combined) per cell."""
    bucket = {m: {"weekday": [Counter() for _ in range(24)],
                  "weekend": [Counter() for _ in range(24)]} for m in MONTH_NUM_TO_SHORT.values()}
    for entry in payload.get("ValueInformation") or []:
        if entry.get("ValueName") != "Energy Export Credit":
            continue
        ts = datetime.strptime(f"{entry['DateStart']} {entry['TimeStart']}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).astimezone(PT)
        pt_date = ts.strftime("%Y-%m-%d")
        daytype = "weekend" if (pt_date in holidays or ts.weekday() >= 5) else "weekday"
        m = MONTH_NUM_TO_SHORT[ts.month]
        bucket[m][daytype][ts.hour][str(entry["value"])] += 1
    cells = {m: {"weekday": [None] * 24, "weekend": [None] * 24} for m in MONTH_NUM_TO_SHORT.values()}
    for m in MONTH_NUM_TO_SHORT.values():
        for dt in ("weekday", "weekend"):
            for h in range(24):
                if bucket[m][dt][h]:
                    cells[m][dt][h] = bucket[m][dt][h].most_common(1)[0][0]
    return cells


def derive_generation(combined_cells, delivery_cells):
    """For each cell: Generation = Combined - Delivery (when both present)."""
    gen = {m: {"weekday": [None] * 24, "weekend": [None] * 24} for m in MONTH_NUM_TO_SHORT.values()}
    missing = 0
    for m in MONTH_NUM_TO_SHORT.values():
        for dt in ("weekday", "weekend"):
            for h in range(24):
                c = combined_cells[m][dt][h]
                d = delivery_cells[m][dt][h]
                if c is None or d is None:
                    missing += 1
                    continue
                gen[m][dt][h] = f"{float(c) - float(d):.6f}"
    return gen, missing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--values", type=Path, default=Path("/tmp/sce-nbt-eec-values.json"))
    args = parser.parse_args()

    existing = json.load(args.values.open())
    print(f"Loaded existing values for vintages: {sorted(existing.keys())}")

    token = get_token()
    holidays = fetch_holidays(token)
    print(f"Got token + {len(holidays)} SC holidays")

    for vintage, scsc_rid in SCSC_RINS.items():
        if vintage not in existing:
            print(f"  warn: vintage {vintage} not in existing Delivery JSON; skipping")
            continue
        start, end = DEFAULT_RANGES[vintage]
        print(f"Fetching {scsc_rid} ({existing[vintage]['rate_name']}) bundled, {start}..{end}...")
        try:
            payload = fetch_historical(token, scsc_rid, start, end)
        except urllib.error.HTTPError as e:
            print(f"  ERROR {e.code}; skipping")
            continue
        combined = aggregate_combined(payload, holidays)
        delivery = existing[vintage]["values"]
        gen, missing = derive_generation(combined, delivery)
        if missing:
            print(f"  {missing} Generation cells couldn't be derived (one or both sides missing)")
        existing[vintage]["generation_values"] = gen
        existing[vintage]["scsc_rin"] = scsc_rid

    with args.values.open("w") as f:
        json.dump(existing, f, indent=2)
    print(f"Wrote {args.values}")
    if "25" in existing and "generation_values" in existing["25"]:
        print(f"  NBT25 Generation Jul Weekday hour 17: {existing['25']['generation_values']['Jul']['weekday'][17]}")


if __name__ == "__main__":
    main()
