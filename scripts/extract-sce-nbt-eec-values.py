#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Extract SCE NBT Energy Export Credit values from the CEC MIDAS API.

SCE publishes its NBT pricing via MIDAS as per-base-RatePlan vintage families.
For the residential NBT bound to TOU-D-PRIME, the relevant RINs are:

  USCA-SCXX-0602-0000   TOU-D-PRIME-NBT NON-VINTAGED
  USCA-SCXX-0603-0000   TOU-D-PRIME-NBT 2023 VINTAGE
  USCA-SCXX-0604-0000   TOU-D-PRIME-NBT 2024 VINTAGE
  USCA-SCXX-0605-0000   TOU-D-PRIME-NBT 2025 VINTAGE
  USCA-SCXX-0606-0000   TOU-D-PRIME-NBT 2026 VINTAGE

Each RIN's MIDAS payload includes the underlying TOU base-rate components
(Win/Sum × On/Mid/Off/SOP × Del Egy Chg) AND the NBT-specific
"Energy Export Credit Delivery" ValueName entries. This script filters to
just the EEC Delivery entries and aggregates them into a 576-cell
(month × hour × day-type) summary per vintage — using HistoricalData over
2025 (chosen as a representative full year overlapping multiple vintages'
lock-in periods).

**SCE Generation EEC is not in MIDAS** — only Delivery is published.
USCA-XXSC-* RINs don't exist in MIDAS HistoricalList (verified 2026-05-29).
Generation EEC source is TBD — likely advice-letter filings or a separate
SCE publication channel. Output records the Delivery values only.

Output: JSON with structure
  { vintage: { "rin": str, "rate_name": str,
               "values": {month: {weekday: [24], weekend: [24]}} } }
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MIDAS_API = "https://midasapi.energy.ca.gov/api"
UTC = ZoneInfo("UTC")
PT = ZoneInfo("America/Los_Angeles")

# SCE TOU-D-PRIME-NBT RINs (Delivery only)
RINS = {
    "non-vintaged": ("USCA-SCXX-0602-0000", "TOU-D-PRIME-NBT NON-VINTAGED"),
    "23":           ("USCA-SCXX-0603-0000", "TOU-D-PRIME-NBT 2023 VINTAGE"),
    "24":           ("USCA-SCXX-0604-0000", "TOU-D-PRIME-NBT 2024 VINTAGE"),
    "25":           ("USCA-SCXX-0605-0000", "TOU-D-PRIME-NBT 2025 VINTAGE"),
    "26":           ("USCA-SCXX-0606-0000", "TOU-D-PRIME-NBT 2026 VINTAGE"),
}

# DateStart format "2025-01-15", DayStart in (Monday|Tuesday|...|Sunday|Holiday)
WEEKDAY_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}
WEEKEND_DAYS = {"Saturday", "Sunday", "Holiday"}

MONTH_NUM_TO_SHORT = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
                       7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}


def get_token():
    user = os.environ["MIDAS_USERNAME"]
    pw = os.environ["MIDAS_PASSWORD"]
    import base64
    creds = base64.b64encode(f"{user}:{pw}".encode()).decode()
    req = urllib.request.Request(f"{MIDAS_API}/Token", method="GET",
                                  headers={"Authorization": f"Basic {creds}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.headers.get("Token") or r.headers.get("token")


def fetch_historical(token, rid, start, end):
    """Pull HistoricalData for one RIN over a date range."""
    url = f"{MIDAS_API}/HistoricalData?id={rid}&startdate={start}&enddate={end}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fetch_holidays(token, energy_code="SC"):
    """Fetch the MIDAS holiday list for one utility. Returns set of YYYY-MM-DD strings."""
    req = urllib.request.Request(f"{MIDAS_API}/Holiday",
                                  headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    holidays = set()
    for h in data:
        if h.get("EnergyCode") != energy_code:
            continue
        d = h.get("DateOfHoliday", "")
        if d:
            holidays.add(d[:10])
    return holidays


def aggregate_eec(payload, holidays):
    """Aggregate 'Energy Export Credit Delivery' entries into a 576-cell
    (month × day-type × hour) summary using the MODE (most-frequent value)
    per cell. Mode robustly handles edge-of-period publication artifacts
    where the first/last day of a period has a transitional value."""
    # bucket[month][daytype][hour] = Counter of value strings
    from collections import Counter
    bucket = {m: {"weekday": [None] * 24, "weekend": [None] * 24} for m in MONTH_NUM_TO_SHORT.values()}
    for m in MONTH_NUM_TO_SHORT.values():
        for dt in ("weekday", "weekend"):
            for h in range(24):
                bucket[m][dt][h] = Counter()

    for entry in payload.get("ValueInformation", []) or []:
        if entry.get("ValueName") != "Energy Export Credit Delivery":
            continue
        date_str = entry["DateStart"]
        time_str = entry["TimeStart"]
        value = str(entry["value"])

        ts_utc = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        ts_pt = ts_utc.astimezone(PT)

        pt_date = ts_pt.strftime("%Y-%m-%d")
        is_holiday = pt_date in holidays
        weekday_idx = ts_pt.weekday()
        daytype = "weekend" if (is_holiday or weekday_idx >= 5) else "weekday"
        month_short = MONTH_NUM_TO_SHORT[ts_pt.month]
        hour = ts_pt.hour
        bucket[month_short][daytype][hour][value] += 1

    cells = {m: {"weekday": [None] * 24, "weekend": [None] * 24} for m in MONTH_NUM_TO_SHORT.values()}
    anomalies = []
    for m in MONTH_NUM_TO_SHORT.values():
        for dt in ("weekday", "weekend"):
            for h in range(24):
                c = bucket[m][dt][h]
                if not c:
                    continue
                most = c.most_common()
                mode_val, mode_count = most[0]
                cells[m][dt][h] = mode_val
                # Flag if mode isn't dominant (e.g. tie or near-tie)
                total = sum(c.values())
                if mode_count / total < 0.7:  # less than 70% of observations agree
                    anomalies.append((m, dt, h, mode_val, mode_count, total, dict(most[:3])))

    missing = [(m, dt, h) for m in cells for dt in ("weekday", "weekend") for h in range(24)
                if cells[m][dt][h] is None]
    return cells, anomalies, missing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--out", default="/tmp/sce-nbt-eec-values.json")
    args = parser.parse_args()

    token = get_token()
    print(f"Got MIDAS token (length {len(token)})")
    holidays = fetch_holidays(token)
    print(f"Fetched {len(holidays)} MIDAS holidays")

    # Per-vintage query date range. MIDAS publication windows per RIN
    # (empirically verified 2026-05-29):
    #   non-vintaged, 23, 24: 2024+2025 data published; use 2025 (full year, 8760 entries)
    #   25: 2025 data only (8752 entries); use 2025
    #   26: 2026 data only, partial (only ~Jan-May published as of query); use 2026
    # All lock-in values are CONSTANT within the lock-in period, so any year
    # in the published window gives the same per-cell rate.
    DEFAULT_RANGES = {
        "non-vintaged": ("2025-01-01", "2025-12-31"),
        "23": ("2025-01-01", "2025-12-31"),
        "24": ("2025-01-01", "2025-12-31"),
        "25": ("2025-01-01", "2025-12-31"),
        "26": ("2026-01-01", "2026-12-31"),
    }
    out = {}
    for vintage, (rid, rate_name) in RINS.items():
        start, end = DEFAULT_RANGES.get(vintage, (args.start, args.end))
        print(f"Fetching {rid} ({rate_name}) over {start}..{end}...")
        try:
            payload = fetch_historical(token, rid, start, end)
        except urllib.error.HTTPError as e:
            print(f"  ERROR {e.code}: {e.read()[:200]}")
            continue
        cells, anomalies, missing = aggregate_eec(payload, holidays)
        if anomalies:
            print(f"  NOTE: {len(anomalies)} cells where mode is <70% dominant (flagged but accepted)")
            for a in anomalies[:2]:
                print(f"    {a}")
        if missing:
            print(f"  WARN: {len(missing)} missing cells (expected all 576)")
            for m in missing[:5]:
                print(f"    {m}")
        else:
            print(f"  OK: all 576 cells populated")
        out[vintage] = {"rin": rid, "rate_name": rate_name, "values": cells}

    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {args.out}")
    s = out["25"]["values"]["Jul"]["weekday"][17]
    print(f"  NBT25 Delivery Jul Weekday hour=17 (5pm) sample: {s}")
    s = out["00"]["values"]["Aug"]["weekend"][20] if "00" in out else None
    s2 = out["non-vintaged"]["values"]["Aug"]["weekend"][20]
    print(f"  NBT NON-VINTAGED Delivery Aug Weekend hour=20: {s2}")


if __name__ == "__main__":
    main()
