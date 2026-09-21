#!/usr/bin/env python3
"""MIDAS RIN coverage gap analysis.

For every MIDAS-published Rate Identification Number (RIN) under the three CA
IOUs, classify whether the rate is covered by:

  - the URPX corpus (a urpx:RatePlan or urpx:RatePlanModifier in this repo
    that semantically corresponds to the RIN)
  - the grid-coordination price server's GridX feed (a feed-based program
    that publishes the same rate via CAISO Day-Ahead Market)
  - neither (a gap)

For each gap, the downstream decision is URPX modeling vs MIDAS fetcher.

Strategy:
  1. HistoricalList → enumerate every RID per (DistributionCode, EnergyCode)
  2. ValueData?QueryType=alldata → fetch each RID's RateName + AltRateName +
     RateType + Sector metadata (concurrent — uses a small thread pool)
  3. Classify each by matching RateName/AltRateName against known URPX
     schedules and known GridX feed prefixes

Outputs:
  reports/midas-coverage.json  — machine-readable, every RID classified
  reports/midas-coverage.md    — human-readable summary tables

Runtime: roughly 5-10 minutes (~2,500 RIDs × ~0.3s per metadata call with
8-thread concurrency).
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(str(Path(__file__).resolve().parent.parent))
OUT_JSON = REPO / "reports" / "midas-coverage.json"
OUT_MD = REPO / "reports" / "midas-coverage.md"

MIDAS_API = "https://midasapi.energy.ca.gov/api"

# Enumeration spec: (distribution_code, energy_code, label)
# Each combo surfaces a distinct rate scope.
ENUMERATE = [
    # PG&E
    ("PG", "PG", "PG&E bundled"),
    ("PG", "XX", "PG&E CCA-served (delivery-only)"),
    ("XX", "PG", "PG&E CCA generation index"),
    # SCE
    ("SC", "SC", "SCE bundled"),
    ("SC", "XX", "SCE CCA-served (delivery-only)"),
    ("XX", "SC", "SCE CCA generation index"),
    # SDG&E
    ("SD", "SD", "SDG&E bundled"),
    ("SD", "XX", "SDG&E CCA-served (delivery-only)"),
    ("XX", "SD", "SDG&E CCA generation index"),
]

# GridX feeds as published by the price server (per
# ~/projects/grid/repo/price-server-user-guide/README.md as of 2026-05-29).
# Matched case-insensitively against MIDAS AltRateName / RateName tokens.
GRIDX_FEEDS = {
    "PG&E": [
        "EELEC", "BEV1", "BEV2P", "BEV2S", "B6", "B10P", "B10S",
        "B19P", "B19S", "B20P", "B20S",
        "AG-A1", "AG-A2", "AGBP", "AGBS", "AGCP", "AGCS",
    ],
    "SCE": [
        "TOU-PRIME", "TOU-D-49", "TOU-D-58", "TOU-EV-8",
        "TOU-EV-9P", "TOU-EV-9S", "TOU-EV-9ST",
        "TOU-GS-1", "TOU-GS-2", "TOU-GS-3",
        "TOU-PA-2", "TOU-PA-3",
        "TOU-8ST", "TOU-8P", "TOU-8S",
    ],
}

# Headers of URPX-modeled schedules per utility — derived from corpus
# directory structure (ca/iou/{utility}/{schedule}/). Case-insensitive
# substring match against RateName / AltRateName.
URPX_SCHEDULES = {}


def discover_urpx_schedules() -> dict[str, list[str]]:
    """Walk ca/iou/ and ca/pou/ to find every modeled schedule slug per utility."""
    out: dict[str, set[str]] = defaultdict(set)
    for klass in ("iou", "pou"):
        klass_root = REPO / "ca" / klass
        if not klass_root.is_dir():
            continue
        for util in klass_root.iterdir():
            if not util.is_dir():
                continue
            for sched in util.iterdir():
                if sched.is_dir() and sched.name != "utility.toml":
                    out[util.name.lower()].add(sched.name.lower())
    return {k: sorted(v) for k, v in out.items()}


TOKEN_LIFETIME_SEC = 480  # refresh every 8 min (~80% of MIDAS's ~10-min lifetime)


class TokenManager:
    """Thread-safe token getter with auto-refresh. MIDAS tokens expire after
    ~10 min; with the corpus at ~5,000 RIDs at ~7 req/s, runs exceed that —
    the manager refreshes proactively before expiry, and on demand after a 401.
    """

    def __init__(self):
        self._token = None
        self._issued_at = 0
        self._lock = threading.Lock()

    def _refresh(self):
        creds = base64.b64encode(
            f"{os.environ['MIDAS_USERNAME']}:{os.environ['MIDAS_PASSWORD']}".encode()
        ).decode()
        req = urllib.request.Request(
            f"{MIDAS_API}/Token", headers={"Authorization": f"Basic {creds}"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            self._token = r.headers.get("Token")
        self._issued_at = time.time()

    def get(self) -> str:
        with self._lock:
            if self._token is None or (time.time() - self._issued_at) > TOKEN_LIFETIME_SEC:
                self._refresh()
            return self._token

    def force_refresh(self) -> str:
        with self._lock:
            self._refresh()
            return self._token


_TM = TokenManager()


def get_token() -> str:
    """Legacy single-shot accessor for the enumeration phase."""
    return _TM.get()


def list_rids(token: str, dist: str, enr: str) -> list[str]:
    """Return unique RIDs from HistoricalList for one (distribution, energy)."""
    req = urllib.request.Request(
        f"{MIDAS_API}/HistoricalList?DistributionCode={dist}&EnergyCode={enr}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    return sorted({
        e["RateID"] for e in data
        if e.get("RateID", "").endswith("-0000")  # skip -TEST entries
        and not e["RateID"].startswith(("USCA-FLEX-", "USCA-SGIP-"))  # exclude regulatory signals
    })


def fetch_meta(token_ignored, rid: str) -> dict:
    """Get RateName/RateType/Sector for one RID with token auto-refresh.

    The first parameter is unused; kept for call-site compatibility. Each
    call goes through the shared TokenManager, which refreshes proactively
    before expiry and on demand after a 401 retry.
    """
    for attempt in range(2):
        token = _TM.get() if attempt == 0 else _TM.force_refresh()
        try:
            req = urllib.request.Request(
                f"{MIDAS_API}/ValueData?ID={rid}&QueryType=alldata",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.load(r)
            return {
                "rid": rid,
                "RateName": d.get("RateName") or "",
                "AltRateName1": d.get("AltRateName1") or "",
                "AltRateName2": d.get("AltRateName2") or "",
                "RateType": d.get("RateType") or "",
                "Sector": d.get("Sector") or "",
                "EndUse": d.get("EndUse") or "",
            }
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 0:
                continue
            return {"rid": rid, "error": f"HTTP Error {e.code}: {e.reason}"}
        except Exception as e:
            return {"rid": rid, "error": str(e)[:120]}
    return {"rid": rid, "error": "exhausted retries"}


def utility_from_rid(rid: str) -> str:
    """Map USCA-XXYY-... → utility tag based on distribution+energy code."""
    parts = rid.split("-")
    if len(parts) < 3 or parts[0] != "USCA":
        return "OTHER"
    code = parts[1]
    if "PG" in code:
        return "PG&E"
    if "SC" in code:
        return "SCE"
    if "SD" in code:
        return "SDG&E"
    return "OTHER"


def _normalize(s: str) -> str:
    """Lowercase, strip whitespace + hyphens + underscores. MIDAS RateNames
    appear in both compact ("EELEC") and hyphenated ("E-ELEC") forms across
    the AltRateName fields; this normalizes both sides for comparison."""
    return s.lower().replace("-", "").replace(" ", "").replace("_", "")


def schedule_matches(slug: str, ratename: str) -> bool:
    """Strict prefix match with digit-boundary protection.

    A URPX schedule slug matches a MIDAS RateName iff the normalized slug
    is a prefix of the normalized RateName AND the next character is not
    a digit. The digit-boundary rule prevents e.g. URPX `e-1` from
    matching MIDAS RateName `E19` (E-19 is a different schedule).

    Examples:
      ("ev2", "EV2A")  → True   (continuation char is letter, OK)
      ("ev2", "BEV2")  → False  (does not start with EV2)
      ("e-1", "E19P")  → False  (continuation digit — different schedule)
      ("e-1", "E-1-A") → True   (continuation char is letter)
      ("dr",  "TOUDR") → False  (does not start with DR)
    """
    s = _normalize(slug)
    n = _normalize(ratename)
    if not s or not n.startswith(s):
        return False
    rest = n[len(s):]
    return rest == "" or not rest[0].isdigit()


def classify(meta: dict, urpx_schedules: dict[str, list[str]]) -> dict:
    """Classify one RID's coverage status."""
    rid = meta["rid"]
    utility = utility_from_rid(rid)
    sector = meta.get("Sector", "")

    util_slug = {"PG&E": "pge", "SCE": "sce", "SDG&E": "sdge"}.get(utility, "")
    urpx_corpus = urpx_schedules.get(util_slug, [])

    candidates = [
        meta.get("RateName", ""),
        meta.get("AltRateName1", ""),
        meta.get("AltRateName2", ""),
    ]
    candidates = [c for c in candidates if c]

    # URPX match: prefer the longest URPX slug that matches (handles nested
    # cases like both `tou-d` and `tou-d-prime` being in the corpus).
    urpx_match = None
    for sched in sorted(urpx_corpus, key=len, reverse=True):
        if any(schedule_matches(sched, c) for c in candidates):
            urpx_match = sched
            break

    # GridX match: same digit-boundary rule.
    gridx_match = None
    for feed in sorted(GRIDX_FEEDS.get(utility, []), key=len, reverse=True):
        if any(schedule_matches(feed, c) for c in candidates):
            gridx_match = feed
            break

    # Sector → human-readable
    sector_label = sector if sector else "unspecified"

    # Gap classification
    if urpx_match and gridx_match:
        status = "covered-both"
    elif urpx_match:
        status = "covered-urpx"
    elif gridx_match:
        status = "covered-gridx"
    else:
        status = f"gap-{sector_label.lower().replace(' ', '-') or 'unknown-sector'}"

    return {
        "rid": rid,
        "utility": utility,
        "rate_name": meta.get("RateName", ""),
        "alt_name": meta.get("AltRateName1", ""),
        "rate_type": meta.get("RateType", ""),
        "sector": sector,
        "status": status,
        "urpx_match": urpx_match,
        "gridx_match": gridx_match,
    }


def main():
    token = get_token()
    urpx_schedules = discover_urpx_schedules()
    print(f"Discovered URPX-modeled schedules: {sum(len(v) for v in urpx_schedules.values())} across {len(urpx_schedules)} utilities")

    # Enumerate RIDs
    all_rids: list[tuple[str, str, str, str]] = []  # (rid, dist, enr, label)
    for dist, enr, label in ENUMERATE:
        rids = list_rids(token, dist, enr)
        print(f"  {dist}-{enr} ({label}): {len(rids)} RIDs")
        for rid in rids:
            all_rids.append((rid, dist, enr, label))

    # Dedupe RIDs (HistoricalList can return duplicates across scopes)
    unique_rids = sorted({r[0] for r in all_rids})
    print(f"Total unique RIDs: {len(unique_rids)}")

    # Fetch metadata concurrently
    print("Fetching metadata...")
    metas: dict[str, dict] = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_meta, token, rid): rid for rid in unique_rids}
        done = 0
        for fut in as_completed(futures):
            m = fut.result()
            metas[m["rid"]] = m
            done += 1
            if done % 200 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (len(unique_rids) - done) / rate
                print(f"  {done}/{len(unique_rids)} ({rate:.1f} req/s, ETA {eta:.0f}s)")
    print(f"Fetched metadata for {len(metas)} RIDs in {time.time()-t0:.1f}s")

    # Classify
    classified = [classify(m, urpx_schedules) for m in metas.values() if "error" not in m]
    errors = [m for m in metas.values() if "error" in m]
    print(f"Classified: {len(classified)} ({len(errors)} errors)")

    # Output JSON
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w") as f:
        json.dump({
            "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "urpx_corpus_scope": urpx_schedules,
            "gridx_feeds": GRIDX_FEEDS,
            "total_unique_rids": len(unique_rids),
            "errors": errors,
            "rids": classified,
        }, f, indent=2)
    print(f"Wrote {OUT_JSON}")

    # Output Markdown summary
    write_markdown(classified, urpx_schedules)
    print(f"Wrote {OUT_MD}")


def write_markdown(rows: list[dict], urpx_schedules: dict[str, list[str]]):
    by_util = defaultdict(list)
    for r in rows:
        by_util[r["utility"]].append(r)

    lines = []
    lines.append("# MIDAS RIN coverage — gap analysis")
    lines.append("")
    lines.append(f"_Auto-generated by `scripts/build-midas-coverage-report.py`. Do not edit by hand. Last run: {time.strftime('%Y-%m-%d')}._")
    lines.append("")
    lines.append("Each MIDAS RIN classified as:")
    lines.append("- **covered-urpx** — a urpx:RatePlan or urpx:RatePlanModifier in this corpus semantically corresponds")
    lines.append("- **covered-gridx** — the grid-coordination price server publishes this rate via GridX/CAISO feed")
    lines.append("- **covered-both** — both")
    lines.append("- **gap-{sector}** — neither URPX nor GridX covers; the sector (Residential, Commercial, Industrial, Agricultural, Lighting) suggests which path to closure")
    lines.append("")

    # Overall summary
    lines.append("## Summary")
    lines.append("")
    status_counter = Counter(r["status"] for r in rows)
    lines.append("| Status | Count |")
    lines.append("|---|---:|")
    for status, count in sorted(status_counter.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| `{status}` | {count} |")
    lines.append(f"| **TOTAL** | **{len(rows)}** |")
    lines.append("")

    # Per-utility detail
    for util in ("PG&E", "SCE", "SDG&E", "OTHER"):
        ulist = by_util.get(util, [])
        if not ulist:
            continue
        lines.append(f"## {util}")
        lines.append("")
        sc = Counter(r["status"] for r in ulist)
        lines.append("**Coverage breakdown:**")
        lines.append("")
        lines.append("| Status | Count |")
        lines.append("|---|---:|")
        for status, count in sorted(sc.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"| `{status}` | {count} |")
        lines.append(f"| **TOTAL** | **{len(ulist)}** |")
        lines.append("")

        # Gap-only table — top gaps by sector
        gaps = [r for r in ulist if r["status"].startswith("gap-")]
        if gaps:
            lines.append(f"**Gaps** ({len(gaps)} RIDs, sorted by sector then RateName):")
            lines.append("")
            lines.append("| RID | RateName | AltRateName | Sector |")
            lines.append("|---|---|---|---|")
            for r in sorted(gaps, key=lambda x: (x.get("sector", ""), x.get("rate_name", ""), x["rid"])):
                rn = r["rate_name"][:60]
                an = (r["alt_name"] or "")[:40]
                sec = r["sector"] or "_unknown_"
                lines.append(f"| `{r['rid']}` | {rn} | `{an}` | {sec} |")
            lines.append("")

        # Covered table — for visibility
        covered = [r for r in ulist if r["status"].startswith("covered-")]
        if covered:
            lines.append(f"**Covered** ({len(covered)} RIDs):")
            lines.append("")
            lines.append("| RID | RateName | Coverage | URPX | GridX |")
            lines.append("|---|---|---|---|---|")
            for r in sorted(covered, key=lambda x: (x["status"], x.get("rate_name", ""))):
                rn = r["rate_name"][:60]
                urpx = r["urpx_match"] or "—"
                gridx = r["gridx_match"] or "—"
                lines.append(f"| `{r['rid']}` | {rn} | `{r['status']}` | {urpx} | {gridx} |")
            lines.append("")

    with OUT_MD.open("w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
