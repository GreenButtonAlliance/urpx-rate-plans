#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Mine MIDAS rate metadata. Per-record durability, deterministic export.

MIDAS is California's price server, not a tariff source. Its value series are
discarded on read and never stored. What is mined is the metadata around a Rate
Identification Number, and above all RatePlan_Url, which points at the utility's
own tariff document.

TWO STORES, FOR TWO DIFFERENT JOBS.

  data/midas/midas.sqlite   the working store. Untracked. One row per
                            identifier, written inside a transaction as each
                            record arrives, so an interrupted run loses at most
                            the record in flight rather than the run.

  data/midas/rins.jsonl     the committed artifact. Sorted by identifier with
                            sorted keys, exported from the database. Deterministic:
                            the same database exports the same bytes.

The split is the point. Mining 74,000 identifiers is tens of thousands of HTTP
calls over hours and wants per-record durability; a tracked file wants stable
bytes and a readable diff. Rewriting a 24 MB file every few hundred records to
get durability is quadratic I/O and still loses the tail on a crash.

IDEMPOTENCE. Every row carries the LastUpdated MIDAS reported when it was
fetched. A run asks the listing for current values, fetches only identifiers the
database has never seen or whose LastUpdated has moved, and exports. A run with
nothing to do writes byte-identical bytes.

The payload's LastUpdated is the only change key available: responses carry no
Last-Modified, no ETag and no Cache-Control, and conditional requests are
ignored, with If-Modified-Since and If-None-Match both answered 200 rather
than 304.

v2.0 is unauthenticated. The 401 from the old token endpoint was a v1.0
artifact; v2.0 went live 2026-06-22 and withdrew v1.0 that day.

    python3 dev/mine_midas.py                 # resume, mine everything left
    python3 dev/mine_midas.py --limit 500     # bounded run
    python3 dev/mine_midas.py --export-only   # re-export without fetching
    python3 dev/mine_midas.py --status        # what is left, no network
"""
from __future__ import annotations

import argparse
import collections
import json
import queue
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STORE = REPO / "data" / "midas"
DB = STORE / "midas.sqlite"
RINS = STORE / "rins.jsonl"
CENSUS = STORE / "census.json"
LOOKUPS = STORE / "lookups"

API = "https://midasapi.energy.ca.gov/api/ValueData"
UA = "urpx-rate-plans metadata miner (github.com/grid-coordination/urpx-rate-plans)"

COLS = ["rid", "rate_name", "alt_rate_name_1", "alt_rate_name_2", "rate_type",
        "sector", "end_use", "rate_plan_url", "api_url", "signup_close_date",
        "signal_type", "description", "last_updated"]
# MIDAS header field -> our column. SystemTime_UTC is deliberately absent: it
# changes on every call and would put a diff in every export.
FROM_API = {"rid": "RateID", "rate_name": "RateName", "alt_rate_name_1": "AltRateName1",
            "alt_rate_name_2": "AltRateName2", "rate_type": "RateType", "sector": "Sector",
            "end_use": "EndUse", "rate_plan_url": "RatePlan_Url", "api_url": "API_Url",
            "signup_close_date": "SignupCloseDate", "signal_type": "SignalType",
            "description": "Description"}


def connect() -> sqlite3.Connection:
    STORE.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("PRAGMA journal_mode=WAL")       # survive an interrupted write
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute(f"CREATE TABLE IF NOT EXISTS rate ({', '.join(f'{x} TEXT' for x in COLS)}, "
              f"fetched_at TEXT, PRIMARY KEY (rid))")
    return c


def get(params: dict, timeout: int = 120):
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def export(c: sqlite3.Connection) -> int:
    """Deterministic: sorted rows, sorted keys, one per line."""
    rows = c.execute(f"SELECT {', '.join(COLS)} FROM rate ORDER BY rid").fetchall()
    body = "\n".join(json.dumps(dict(zip(COLS, r)), sort_keys=True, ensure_ascii=False)
                     for r in rows)
    RINS.write_text(body + ("\n" if body else ""))
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap fetches this run; 0 means no cap")
    ap.add_argument("--workers", type=int, default=8,
                    help="concurrent detail fetches; latency-bound, so this is the throughput knob")
    ap.add_argument("--export-only", action="store_true")
    ap.add_argument("--status", action="store_true", help="report progress without any network call")
    ap.add_argument("--progress", type=int, default=500, help="log every N fetches")
    args = ap.parse_args()

    c = connect()
    have = dict(c.execute("SELECT rid, last_updated FROM rate").fetchall())

    if args.status:
        withurl = c.execute("SELECT COUNT(*) FROM rate WHERE rate_plan_url IS NOT NULL").fetchone()[0]
        print(f"stored {len(have)} identifiers, {withurl} with a RatePlan_Url")
        return 0
    if args.export_only:
        print(f"exported {export(c)} records to {RINS.relative_to(REPO)}")
        return 0

    try:
        listing = get({"SignalType": 0})
    except urllib.error.URLError as e:
        print(f"REFUSING: the identifier listing could not be read: {e}", file=sys.stderr)
        return 3
    rates = listing.get("Rates") or []
    if not rates:
        print("REFUSING: the listing returned no identifiers. An empty answer and a "
              "feed with nothing in it are indistinguishable here, and treating the "
              "first as the second would report a stale store as current.", file=sys.stderr)
        return 3

    live = {r["RateID"]: r.get("LastUpdated") for r in rates}
    # An identifier the store has never seen is always fetched, whatever the
    # listing says about it. Comparing have.get(rid) != lu alone silently
    # excludes forever any row whose LastUpdated is null: None != None is
    # False, so it never enters todo and no run ever picks it up. Exactly one
    # row in the feed is like that, USCA-FLEX-ALRT-0000, and the shortfall read
    # as a rounding difference between 74,097 and 74,096.
    todo = sorted(rid for rid, lu in live.items() if rid not in have or have[rid] != lu)
    if args.limit:
        todo = todo[: args.limit]

    seg = collections.Counter(r.split("-")[1] for r in live if r.count("-") >= 2)
    CENSUS.write_text(json.dumps({
        "endpoint": API,
        "identifiers": len(live),
        "party_segments": dict(sorted(seg.items(), key=lambda kv: (-kv[1], kv[0]))),
        "sub_identifiers": dict(sorted(collections.Counter(
            r.split("-")[3] for r in live if r.count("-") >= 3).items(),
            key=lambda kv: (-kv[1], kv[0]))),
        "non_numeric_rate_codes": sum(
            1 for r in live if r.count("-") >= 3 and not r.split("-")[2].isdigit()),
        "signal_types": dict(sorted(collections.Counter(
            r.get("SignalType") for r in rates).items(), key=lambda kv: (-kv[1], str(kv[0])))),
    }, indent=2, sort_keys=True) + "\n")

    LOOKUPS.mkdir(parents=True, exist_ok=True)
    for name in ["Country", "Daytype", "Distribution", "Enduse", "Energy",
                 "Location", "Ratetype", "Sector", "State", "Unit"]:
        try:
            payload = get({"LookupTable": name})
        except Exception:  # noqa: BLE001
            continue
        rows = payload.get("data") if isinstance(payload, dict) else payload
        if rows:
            (LOOKUPS / f"{name.lower()}.json").write_text(
                json.dumps(rows, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    print(f"feed {len(live)} identifiers; stored {len(have)}; to fetch {len(todo)} "
          f"with {args.workers} workers", flush=True)

    # FETCH CONCURRENTLY, WRITE FROM ONE THREAD. Round-trip latency dominates:
    # serially this ran at 1.3/s, which is fifteen hours for the feed. The
    # server's own processing is milliseconds, so the wait is almost entirely
    # network and a small pool recovers it without leaning on a public service.
    # Writes stay on the main thread, so SQLite sees a single writer and the
    # one-transaction-per-record durability is unchanged.
    done = failed = 0
    started = time.time()

    def fetch(rid):
        for attempt in range(3):
            try:
                d = get({"ID": rid, "QueryType": "alldata"}, timeout=60)
                if isinstance(d, dict) and d.get("RateID"):
                    return rid, d
                return rid, None
            except Exception:  # noqa: BLE001
                if attempt == 2:
                    return rid, None
                time.sleep(0.5 * (attempt + 1))
        return rid, None

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for rid, d in pool.map(fetch, todo):
            if d is None:
                failed += 1
                continue
            vals = [d.get(FROM_API[k]) for k in COLS if k != "last_updated"]
            with c:
                c.execute(f"INSERT OR REPLACE INTO rate ({', '.join(COLS)}, fetched_at) "
                          f"VALUES ({', '.join('?' * (len(COLS) + 1))})",
                          (*vals, live[rid], time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
            done += 1
            if done % args.progress == 0:
                rate = done / max(1e-9, time.time() - started)
                left = (len(todo) - done) / max(1e-9, rate)
                print(f"  {done}/{len(todo)}  {rate:.1f}/s  ~{left/60:.0f} min left  "
                      f"({failed} failed)", flush=True)

    n = export(c)
    withurl = c.execute("SELECT COUNT(*) FROM rate WHERE rate_plan_url IS NOT NULL").fetchone()[0]
    print(f"fetched {done}, failed {failed}; store holds {n}, {withurl} with a RatePlan_Url")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
