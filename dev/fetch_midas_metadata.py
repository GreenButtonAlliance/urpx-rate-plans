#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Mine MIDAS rate metadata into a reusable, idempotently updatable store.

MIDAS IS A PRICE SERVER, NOT A TARIFF SOURCE. Its value streams belong to a
price server and are deliberately not stored here. What this mines is the
METADATA around a Rate Identification Number: what the rate is called, what
composition the identifier names, and above all where the tariff document is.

WHAT IT KEEPS, per RIN, from the v2.0 RateInfo header:

    RateName        the plan, shared across an identifier family
    AltRateName1/2  the composition, e.g. "E-TOU-D-CARE" against "E-TOU-D"
    RatePlan_Url    a link to the utility's own tariff document
    RateType        one of MIDAS's ten codes
    Sector          Res / Com / Ind / Agr / All and EV variants
    EndUse          scoped end use where one is declared
    API_Url         the publisher's own live endpoint
    LastUpdated     the change key this store is kept idempotent by

ValueInformation, the price series, is discarded on read and never stored.

TWO CALLS, TWO COSTS. `GET /ValueData?SignalType=0` returns every identifier in
one response with its Description and LastUpdated: cheap, complete, and the work
queue. `GET /ValueData?ID=<rin>&QueryType=alldata` returns one header: the
valuable half, and one HTTP call each. So the store grows incrementally and a
run is bounded by --max-detail rather than trying the whole feed at once.

IDEMPOTENCE is the property to protect, and it is testable rather than asserted:
run twice with nothing changed upstream and the second run writes byte-identical
files, so `git diff` is empty. That holds because every record is keyed by RIN,
written in sorted order with sorted keys, and re-fetched only when MIDAS reports
a LastUpdated this store has not already recorded. Deleting the store and
rebuilding it converges on the same bytes for the same upstream state.

NO HTTP PROVENANCE EXISTS, checked rather than assumed. Responses carry only
content-length, content-type, server and an envoy timing header: no
Last-Modified, no ETag, no Cache-Control, no Age. Conditional requests are
ignored, with both If-Modified-Since and If-None-Match answered 200 rather than
304. So there is no transport-level way to ask whether anything changed, and the
payload's own LastUpdated is the only change key available. That is why this
store is keyed on it, and why a refresh still costs one full listing call.

v2.0 IS UNAUTHENTICATED. Every GET here is public; the spec marks them
`security: []`. The old token endpoint returning 401 was a v1.0 artifact, not a
credential problem: v2.0 went live 2026-06-22 and v1.0 was withdrawn that day.

Run from repo root:
    python3 dev/fetch_midas_metadata.py --max-detail 200
    python3 dev/fetch_midas_metadata.py --max-detail 0     # census only, no detail
    python3 dev/fetch_midas_metadata.py --segments PGPG,SCSC --max-detail 500
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STORE = REPO / "data" / "midas"
RINS = STORE / "rins.jsonl"
CENSUS = STORE / "census.json"
LOOKUPS = STORE / "lookups"

API = "https://midasapi.energy.ca.gov/api/ValueData"
UA = "urpx-tariffs metadata miner (github.com/grid-coordination/urpx-rate-plans)"

# Kept from the RateInfo header, in this order. ValueInformation is not here
# on purpose: prices are a price server's business, not a tariff corpus's.
FIELDS = ["RateID", "RateName", "AltRateName1", "AltRateName2", "RateType",
          "Sector", "EndUse", "RatePlan_Url", "API_Url", "SignupCloseDate",
          "SignalType", "Description", "LastUpdated"]


def get(params: dict, timeout: int = 120):
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def load_store() -> dict[str, dict]:
    if not RINS.exists():
        return {}
    out = {}
    for line in RINS.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec["RateID"]] = rec
    return out


def write_store(store: dict[str, dict]) -> None:
    """Sorted by RIN, sorted keys, one record per line. Stable by construction,
    so an unchanged store rewrites to identical bytes."""
    STORE.mkdir(parents=True, exist_ok=True)
    body = "\n".join(
        json.dumps({k: store[rid].get(k) for k in FIELDS}, sort_keys=True, ensure_ascii=False)
        for rid in sorted(store)
    )
    RINS.write_text(body + ("\n" if body else ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-detail", type=int, default=250,
                    help="cap per-RIN header fetches this run; 0 writes the census only")
    ap.add_argument("--segments", default="",
                    help="comma-separated party segments to prioritize, e.g. PGPG,SCSC")
    ap.add_argument("--delay", type=float, default=0.15, help="seconds between detail calls")
    args = ap.parse_args()

    try:
        listing = get({"SignalType": 0})
    except urllib.error.URLError as e:
        print(f"REFUSING: the identifier listing could not be read: {e}", file=sys.stderr)
        return 3
    rates = listing.get("Rates") or []
    if not rates:
        print("REFUSING: the listing returned no identifiers, so there is nothing "
              "to reconcile against and an empty store would look current.", file=sys.stderr)
        return 3

    live = {r["RateID"]: r for r in rates}

    # Census of the whole feed. Small, and it records what exists without
    # storing 74,000 rows of someone else's data.
    seg = collections.Counter(r.split("-")[1] for r in live if r.count("-") >= 2)
    sub = collections.Counter(r.split("-")[3] for r in live if r.count("-") >= 3)
    nonnum = sum(1 for r in live if r.count("-") >= 3 and not r.split("-")[2].isdigit())
    census = {
        "endpoint": API,
        "identifiers": len(live),
        "party_segments": dict(sorted(seg.items(), key=lambda kv: (-kv[1], kv[0]))),
        "sub_identifiers": dict(sorted(sub.items(), key=lambda kv: (-kv[1], kv[0]))),
        "non_numeric_rate_codes": nonnum,
        "signal_types": dict(sorted(collections.Counter(
            r.get("SignalType") for r in rates).items(), key=lambda kv: (-kv[1], str(kv[0])))),
    }

    # The lookup tables decode what a RIN is made of: Distribution and Energy
    # turn the two halves of the party segment into a named utility with a URL,
    # which is how a CCA-only identifier like XXSA resolves to San Diego
    # Community Power, and Location decodes the fourth field (0000 is All
    # Areas). Small, rarely changing, and worth holding rather than re-deriving.
    LOOKUPS.mkdir(parents=True, exist_ok=True)
    tables = {}
    for name in ["Country", "Daytype", "Distribution", "Enduse", "Energy",
                 "Location", "Ratetype", "Sector", "State", "Unit"]:
        try:
            payload = get({"LookupTable": name})
        except Exception as e:  # noqa: BLE001
            print(f"  lookup {name} failed: {type(e).__name__}", file=sys.stderr)
            continue
        rows = payload.get("data") if isinstance(payload, dict) else payload
        if not rows:
            continue
        tables[name] = len(rows)
        (LOOKUPS / f"{name.lower()}.json").write_text(
            json.dumps(rows, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    census["lookup_tables"] = dict(sorted(tables.items()))

    store = load_store()
    before = json.dumps(store, sort_keys=True)

    # What needs a detail call: never fetched, or MIDAS reports a newer
    # LastUpdated than the one recorded here. That comparison is what makes a
    # re-run cost nothing when nothing upstream moved.
    stale = [rid for rid, r in live.items()
             if rid not in store or store[rid].get("LastUpdated") != r.get("LastUpdated")]
    want = [s.strip().upper() for s in args.segments.split(",") if s.strip()]
    if want:
        stale.sort(key=lambda rid: (rid.split("-")[1] not in want, rid))
    else:
        stale.sort()

    fetched = failed = 0
    for rid in stale[: max(0, args.max_detail)]:
        try:
            d = get({"ID": rid, "QueryType": "alldata"}, timeout=60)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  detail failed for {rid}: {type(e).__name__}", file=sys.stderr)
            continue
        if not isinstance(d, dict) or not d.get("RateID"):
            failed += 1
            continue
        d.pop("ValueInformation", None)          # prices are not ours to keep
        d.pop("SystemTime_UTC", None)            # changes every call; would defeat idempotence
        # LastUpdated is served by the LISTING, not by the detail call. Taking it
        # from the detail response stored None and made every record read as
        # permanently stale, which is the bug this line exists to not have.
        rec = {k: d.get(k) for k in FIELDS}
        rec["LastUpdated"] = live[rid].get("LastUpdated")
        store[rid] = rec
        fetched += 1
        time.sleep(args.delay)

    STORE.mkdir(parents=True, exist_ok=True)
    CENSUS.write_text(json.dumps(census, indent=2, sort_keys=True) + "\n")
    write_store(store)

    changed = json.dumps(store, sort_keys=True) != before
    withurl = sum(1 for r in store.values() if r.get("RatePlan_Url"))
    print(f"census: {len(live)} identifiers, {len(seg)} party segments, "
          f"{nonnum} non-numeric rate codes")
    print(f"store : {len(store)} records ({fetched} fetched, {failed} failed this run), "
          f"{len(stale) - fetched} still stale or unfetched")
    print(f"        {withurl} carry a RatePlan_Url")
    print(f"lookups: {sum(census.get('lookup_tables', {}).values())} rows over {len(census.get('lookup_tables', {}))} tables")
    print(f"        {'store changed' if changed else 'store unchanged (idempotent re-run)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
