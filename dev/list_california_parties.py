#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Generate reports/california-parties.md: every party selling electricity in the CEC feed.

One row per organization, not per party segment, because an organization can
appear under several: Ava sells over both PG&E and its own legacy East Bay code,
Valley Clean Energy under `PGVC` and `XXVC`.

Columns are what someone needs to find a tariff: the MIDAS segment, the
directory name this corpus uses, how the party sells, and whether anything is
modeled yet.

CLASSIFICATION is asserted here rather than derived, because MIDAS does not
carry one. An investor-owned utility, a publicly owned utility and a community
choice aggregator are different regulatory animals and the feed only distinguishes
them accidentally, through whether the distribution half of a segment names a
utility or reads `XX` for unspecified. That accident is a good signal and not a
definition, so the mapping is stated in KIND below and can be corrected.

Run from repo root:  python3 dev/list_california_parties.py
"""
from __future__ import annotations

import collections
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "midas" / "midas.sqlite"
LOOKUPS = REPO / "data" / "midas" / "lookups"

# organization name in the MIDAS Energy table -> (directory, kind, who delivers)
KIND = {
    "Pacific Gas and Electric":                    ("pge", "iou", "itself"),
    "Southern California Edison":                  ("sce", "iou", "itself"),
    "San Diego Gas and Electric":                  ("sdge", "iou", "itself"),
    "LADWP":                                       ("ladwp", "pou", "itself"),
    "Sacramento Municipal Utility District":       ("smud", "pou", "itself"),
    "Banning":                                     ("banning", "pou", "itself"),
    "San Diego Community Power":                   ("sdcp", "cca", "SDG&E"),
    "San Jose Clean Energy":                       ("sjce", "cca", "PG&E"),
    "Clean Power Alliance of Southern California": ("cleanpoweralliance", "cca", "SCE"),
    "Valley Clean Energy":                         ("vce", "cca", "PG&E"),
    "WestLight Energy":                            ("pce", "cca", "PG&E"),
    "Ava Community Energy":                        ("ebce", "cca", "PG&E"),
    "Clean Energy Alliance":                       ("cea", "cca", "SDG&E"),
    "Sonoma Clean Power":                          ("scp", "cca", "PG&E"),
    "Central Coast Community Energy":              ("3ce", "cca", "PG&E"),
    "Silicon Valley Clean Energy":                 ("svce", "cca", "PG&E"),
    "Pioneer Community Energy":                    ("pioneer", "cca", "PG&E"),
    "Orange County Power Authority":                ("ocpa", "cca", "SCE"),
    "Clean Power San Francisco":                   ("cleanpowersf", "cca", "PG&E"),
    "Marin Clean Energy":                          ("mce", "cca", "PG&E"),
}
KIND_LABEL = {"iou": "investor-owned", "pou": "publicly owned", "cca": "community choice"}
# Research feeds and upload fixtures. Real rows, not parties.
NOT_A_PARTY = {"CalFlexHub Research", "CalFlexHub", "Test", "HP-Flex Research",
               "MIDAS FlexAlert Test Signal - Energy", "MIDAS FlexAlert Test Signal - Dist",
               "MIDAS GHG Test Signal - Energy Code", "SGIP", "Unspecified"}


def main() -> int:
    if not DB.exists():
        print("REFUSING: no mined store. Run dev/mine_midas.py first.", file=sys.stderr)
        return 3
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    look = {n: {r["UploadCode"]: r for r in json.loads((LOOKUPS / f"{n}.json").read_text())}
            for n in ("distribution", "energy") if (LOOKUPS / f"{n}.json").exists()}
    if not look:
        print("REFUSING: the Distribution and Energy lookup tables are missing, so a "
              "segment cannot be decoded to an organization and every row would read "
              "as unknown.", file=sys.stderr)
        return 3

    agg = collections.defaultdict(lambda: {"segs": set(), "n": 0, "urls": set(), "site": ""})
    unknown = collections.Counter()
    for seg, n, urls in c.execute(
            "SELECT substr(rid,6,4), COUNT(*), COUNT(DISTINCT rate_plan_url) FROM rate GROUP BY 1"):
        e = look["energy"].get(seg[2:], {})
        d = look["distribution"].get(seg[:2], {})
        name = (e.get("Description") or d.get("Description") or "").strip()
        if not name or name in NOT_A_PARTY:
            continue
        if name not in KIND:
            unknown[name] += n
            continue
        a = agg[name]
        a["segs"].add(seg)
        a["n"] += n
        a["site"] = a["site"] or (e.get("URL") or d.get("URL") or "").strip()
    for seg, url in c.execute("SELECT substr(rid,6,4), rate_plan_url FROM rate "
                              "WHERE rate_plan_url IS NOT NULL GROUP BY 1,2"):
        e = look["energy"].get(seg[2:], {})
        d = look["distribution"].get(seg[:2], {})
        name = (e.get("Description") or d.get("Description") or "").strip()
        if name in agg:
            agg[name]["urls"].add(url)

    modeled = {p.name for p in (REPO / "us" / "ca").iterdir()
               if p.is_dir() and (p / "electricity").exists()}

    rows = []
    for name, a in agg.items():
        slug, kind, delivers = KIND[name]
        rows.append({"organization": name, "utility": slug, "kind": kind,
                     "delivered_by": delivers, "segments": sorted(a["segs"]),
                     "identifiers": a["n"], "rate_links": len(a["urls"]),
                     "site": a["site"], "filings_modeled": slug in modeled})
    rows.sort(key=lambda r: (r["kind"] != "iou", r["kind"] != "pou", -r["identifiers"]))

    # MIDAS is a live feed, so every count here is point-in-time. The as-of
    # comes from when the rows were fetched, not from when this ran: re-running
    # the generator against an old store must not restate the date.
    first, last = c.execute("SELECT MIN(fetched_at), MAX(fetched_at) FROM rate").fetchone()
    asof = (last or "")[:10]
    span = "" if first[:10] == asof else f", mined {first[:10]} to {asof}"

    o = ["# Parties selling electricity in California", "",
         "Auto-generated by `dev/list_california_parties.py` from the mined CEC MIDAS feed "
         "in `data/midas/`. Do not edit by hand.", "",
         f"**Every count below is as of {asof}**{span}. MIDAS is a live feed: parties "
         "appear, rename and withdraw, and identifier counts move daily.", ""]
    tot = sum(r["identifiers"] for r in rows)
    nm = sum(1 for r in rows if r["filings_modeled"])
    o += [f"{len(rows)} organizations carrying {tot:,} rate identifiers. {nm} have filings in "
          f"this corpus; {len(rows) - nm} have a directory and a discovery manifest only.", "",
          "**Kind is asserted, not derived.** MIDAS carries no classification. It distinguishes "
          "these only accidentally, through whether the distribution half of a party segment "
          "names a utility or reads `XX` for unspecified, which is a good signal and not a "
          "definition. The mapping lives in `dev/list_california_parties.py`.", "",
          "A community choice aggregator sells generation over an investor-owned utility's "
          "wires, so one of its customers is billed a composition: the aggregator's generation "
          "rate with the utility's delivery. Both halves have to be modeled to price a bill.", "",
          "| Kind | Organization | `utility` | Segment | Delivered by | Identifiers | Rate links | Filings |",
          "|---|---|---|---|---|---:|---:|---|"]
    for r in rows:
        o.append(f"| {KIND_LABEL[r['kind']]} | [{r['organization']}]({r['site']}) | "
                 f"`{r['utility']}` | {', '.join('`'+s+'`' for s in r['segments'])} | "
                 f"{r['delivered_by']} | {r['identifiers']:,} | {r['rate_links'] or '—'} | "
                 f"{'yes' if r['filings_modeled'] else 'none yet'} |")
    if unknown:
        o += ["", "## In the feed, not yet classified", "",
              "Named organizations with no entry in the mapping. Each is a party this report "
              "cannot place, and the omission is listed rather than silently dropped.", ""]
        for name, n in unknown.most_common():
            o.append(f"- {name} ({n:,} identifiers)")
    (REPO / "reports" / "california-parties.md").write_text("\n".join(o) + "\n")
    print(f"wrote reports/california-parties.md: {len(rows)} organizations, {tot:,} identifiers, "
          f"{nm} with filings, {len(unknown)} unclassified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
