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

import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(str(Path(__file__).resolve().parent.parent))
# scripts/ is not on the path that reaches dev/, so nothing here could import the
# shared discovery module. That is why this file carried its own corpus walk, and
# why the walk went stale unnoticed.
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402
import utilities  # noqa: E402

OUT_JSON = REPO / "reports" / "midas-coverage.json"
OUT_MD = REPO / "reports" / "midas-coverage.md"

# The mined feed. This report used to be built from ~2,500 live authenticated
# calls taking 5-10 minutes; the same rows are already here, fetched by
# dev/mine_midas.py from the UNauthenticated listing. Reading them locally is
# reproducible, needs no credentials, and is not slower than the store is stale.
STORE = REPO / "data" / "midas" / "midas.sqlite"
LOOKUPS = REPO / "data" / "midas" / "lookups"

# Party segments in scope: every segment belonging to a utility this corpus
# models, read from dev/utilities.py rather than spelled out here.
#
# This is wider than the list it replaces. That named only the three
# investor-owned utilities, so LADWP and SMUD were absent from the report even
# though both are modeled here, and their coverage had never been measured.
#
# It also drops three combos the old list carried: XXPG, XXSC and XXSD, the
# "CCA generation index" for an investor-owned utility. Those are not omissions.
# Each returns zero rows out of the whole 74,097-identifier feed, because an
# XX-first segment names a generation-only seller and an investor-owned utility
# sells its generation over its own wires. The 32 NB-code identifiers MIDAS does
# carry on XX-first segments all belong to community choice aggregators.
SEGMENT_UTILITY = utilities.segment_utility()

# GridX feeds as published by the price server (per
# https://github.com/grid-coordination/price-server-user-guide README.md as of
# 2026-05-29).
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

def discover_urpx_schedules() -> dict[str, list[str]]:
    """Every modeled schedule slug per utility, from dev/corpus.py.

    The previous version walked `ca/iou/` and `ca/pou/`, removed by the
    2026-09-20 restructure. It did not fail. `if not klass_root.is_dir():
    continue` swallowed the absence, so it returned {}, main() printed
    "0 across 0 utilities", and classify() could then never reach covered-urpx:
    a refresh would have silently erased 648 covered-urpx and 106 covered-both
    rows while exiting 0. It was wrong by two levels, not one, since the
    restructure also inserted the carrier segment.

    corpus.schedules_by_utility() refuses over an empty corpus instead.
    """
    return {u: sorted(s) for u, s in corpus.schedules_by_utility().items()}


def lookup(name: str) -> dict[str, str]:
    """A MIDAS lookup table as {UploadCode -> Description}, matched case-blind.

    MIDAS emits sector codes rather than labels, so without this the status
    strings degrade from `gap-commercial` to `gap-com` and stop being comparable
    to earlier runs. Case-blind because the feed carries both `All` and `ALL`
    while only `All` is a documented UploadCode.
    """
    path = LOOKUPS / f"{name}.json"
    if not path.exists():
        raise SystemExit(
            f"ERROR: {path.relative_to(REPO)} is missing, so sector and rate-type "
            f"codes cannot be resolved to labels and every status string would read "
            f"as a raw code. Refusing rather than emitting one."
        )
    return {str(r["UploadCode"]).lower(): r["Description"]
            for r in json.loads(path.read_text()) if r.get("UploadCode")}


def read_store() -> list[dict]:
    """Every in-scope identifier and its metadata, from the mined feed.

    Reproduces what the authenticated HistoricalList + ValueData pair returned,
    from rows fetched by dev/mine_midas.py off the same endpoint. The two filters
    are the originals: the `-0000` location suffix (the only other bulk suffix is
    `-TEST`), and the two regulatory-signal prefixes. `signal_type` makes the
    second one redundant for these segments, and it is kept anyway because it
    costs nothing and states the intent.
    """
    if not STORE.exists():
        raise SystemExit(
            f"ERROR: no mined feed at {STORE.relative_to(REPO)}. Run "
            f"dev/mine_midas.py first; refusing to report coverage over no rates."
        )
    sector_label, ratetype_label = lookup("sector"), lookup("ratetype")
    segs = sorted(SEGMENT_UTILITY)
    con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    rows = con.execute(
        f"""SELECT rid, rate_name, alt_rate_name_1, alt_rate_name_2, rate_type,
                   sector, end_use
              FROM rate
             WHERE substr(rid, 6, 4) IN ({",".join("?" * len(segs))})
               AND rid LIKE '%-0000'
               AND signal_type = 'Electricity Rates'
               AND rid NOT LIKE 'USCA-FLEX-%'
               AND rid NOT LIKE 'USCA-SGIP-%'
             ORDER BY rid""", segs).fetchall()
    out = [{"rid": r[0], "RateName": r[1] or "", "AltRateName1": r[2] or "",
            "AltRateName2": r[3] or "",
            "RateType": ratetype_label.get(str(r[4] or "").lower(), r[4] or ""),
            "Sector": sector_label.get(str(r[5] or "").lower(), r[5] or ""),
            "EndUse": r[6] or ""} for r in rows]
    corpus.require_nonempty(out, "MIDAS identifiers in scope")
    return out



def utility_from_rid(rid: str) -> str:
    """Map USCA-<segment>-... to a utility display name, or OTHER.

    Keyed on the whole four-character segment, not a substring of it. The
    previous version asked `"PG" in code`, which is the same answer for these
    segments but would also claim any future segment merely containing those two
    letters. The display form rather than the slug because `rids[].utility` is
    read by two downstream generators in this spelling.
    """
    parts = rid.split("-")
    if len(parts) < 3 or parts[0] != "USCA":
        return "OTHER"
    slug = SEGMENT_UTILITY.get(parts[1])
    return utilities.BY_SLUG[slug].short_name if slug else "OTHER"


# Display name back to slug, so classify() does not carry a third copy of the
# utility list. Derived from the same table utility_from_rid() reads.
SHORT_NAME_SLUG = {u.short_name: u.slug for u in utilities.BY_SLUG.values()}


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

    util_slug = SHORT_NAME_SLUG.get(utility, "")
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
    urpx_schedules = discover_urpx_schedules()
    print(f"URPX-modeled schedules: {sum(len(v) for v in urpx_schedules.values())} "
          f"across {len(urpx_schedules)} utilities "
          f"({', '.join(sorted(urpx_schedules))})")

    metas = read_store()
    by_seg = Counter(m["rid"][5:9] for m in metas)
    print(f"In scope: {len(metas):,} identifiers over "
          f"{len(SEGMENT_UTILITY)} party segment(s)")
    for seg in sorted(SEGMENT_UTILITY):
        print(f"  {seg} ({SEGMENT_UTILITY[seg]}): {by_seg.get(seg, 0):,}")

    classified = [classify(m, urpx_schedules) for m in metas]
    print(f"Classified: {len(classified):,}")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w") as f:
        json.dump({
            "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "data/midas/midas.sqlite",
            "urpx_corpus_scope": urpx_schedules,
            "gridx_feeds": GRIDX_FEEDS,
            "party_segments": SEGMENT_UTILITY,
            "total_unique_rids": len(classified),
            # Kept for the consumers that read it. An offline run has no fetch to
            # fail, so this is empty by construction rather than by luck; the 18
            # entries the last authenticated run left here were RIDs that 404'd.
            "errors": [],
            "rids": classified,
        }, f, indent=2)
    print(f"Wrote {OUT_JSON}")

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

    # A utility whose modeled schedules are present but whose MIDAS RateNames do
    # not use schedule identifiers produces gap rows that mean something else
    # entirely. Measured per utility rather than asserted, so the reader sees the
    # denominator; without this the table reads as "almost nothing is modeled".
    lines.append("## How to read the gap counts")
    lines.append("")
    lines.append("A `gap-*` row means no modeled schedule slug and no GridX feed code "
                 "matched this identifier's RateName or AltRateName. Matching is a "
                 "strict prefix comparison with a digit boundary, so it is quiet rather "
                 "than wrong when a publisher does not name rates by schedule.")
    lines.append("")
    lines.append("| Utility | Identifiers | Matched a modeled schedule | Publishes a Sector |")
    lines.append("|---|---:|---:|---:|")
    for u in utilities.ordered():
        ul = [r for r in rows if r["utility"] == u.short_name]
        if not ul:
            continue
        matched = sum(1 for r in ul if r["urpx_match"])
        sectored = sum(1 for r in ul if r.get("sector"))
        lines.append(f"| {u.short_name} | {len(ul):,} | {matched:,} | {sectored:,} |")
    lines.append("")
    lines.append("Where the matched column is near zero the limit is naming, not "
                 "modeling. LADWP publishes no Sector on any identifier and its RINs "
                 "enumerate load-factor and power-factor cells rather than schedules, "
                 "so its count is not comparable to a schedule count. SMUD names "
                 "residential rates in forms the prefix rule cannot reach: "
                 "`USCA-SMSM-TOD5-0000` carries RateName \"Time-of-Day 5-8PM\", which "
                 "is this corpus's `tod-5-8pm`, spelled out rather than as the "
                 "schedule code. That is one known instance, left unmatched here "
                 "rather than bridged by an alias table.")
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
    for util in [u.short_name for u in utilities.ordered()] + ["OTHER"]:
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
