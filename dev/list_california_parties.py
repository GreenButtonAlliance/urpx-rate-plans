#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
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
definition, so each utility.toml states its own utility_class and it can be
corrected there.

Run from repo root:  python3 dev/list_california_parties.py
"""
from __future__ import annotations

import collections
import json
import re
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402
import utilities  # noqa: E402
DB = REPO / "data" / "midas" / "midas.sqlite"
LOOKUPS = REPO / "data" / "midas" / "lookups"

def _kind() -> dict[str, tuple[str, str, str]]:
    """MIDAS organization name -> (directory, class, who delivers).

    Built from the per-utility utility.toml manifests, which is where the three
    pieces now live: midas_party_names, utility_class and delivered_by. This was a
    twenty-entry literal here, and it was the third place the regulatory class was
    written down.

    "who delivers" is rendered for a reader, so a self-delivering party reads
    "itself" and an aggregator names the utility whose wires carry it, by that
    utility's own short_name rather than by its slug.
    """
    out = {}
    for slug, u in utilities.ALL.items():
        if u.delivered_by:
            carrier = utilities.ALL[u.delivered_by]
            delivers = carrier.short_name or u.delivered_by
        else:
            delivers = "itself"
        for name in u.midas_party_names:
            out[name] = (slug, u.utility_class, delivers)
    corpus.require_nonempty(out, "MIDAS party names in the utility manifests")
    return out


KIND = _kind()

# The three regulatory classes come from dev/utilities.py; Alert and GHG are
# not classes of seller at all but signal kinds this report also lists.
KIND_LABEL = {**utilities.CLASS_LABEL, "alert": "Alert", "ghg": "GHG"}

# MIDAS carries signals that are not rates and have no seller. They are parties
# in the feed all the same, so they are rows here rather than a footnote, with a
# kind that says what they are. Keyed on SignalType, which is what actually
# distinguishes them; the party lookup calls both "Test Signal", which they are
# not: the Flex Alert is a production CAISO conservation call.
SIGNAL_PARTY = {
    "California Independent System Operator Flex Alert":
        ("caiso", "alert", "California Independent System Operator", "https://www.caiso.com"),
    "Greenhouse Gas Emissions":
        ("sgip", "ghg", "SGIP realtime marginal emissions", "https://www.energy.ca.gov"),
}
# Research feeds and upload fixtures: real rows in the feed, not organizations.
# Matched by pattern rather than by name. The first version listed names, and
# missed "MIDAS FlexAlert Test Signal - Energy Code" because it knew only the
# "- Energy" spelling; a rule that enumerates its exceptions keeps missing one.
# Whatever this excludes is listed in the report, so the rule is never silent.
NOT_A_PARTY_PATTERN = re.compile(r"\b(Test|Research|Signal|Unspecified)\b", re.I)
# The residue the pattern cannot see: names that say nothing about being a feed.
NOT_A_PARTY_NAMES = {"CalFlexHub", "SGIP"}


def is_a_party(name: str) -> bool:
    return bool(name) and name not in NOT_A_PARTY_NAMES and not NOT_A_PARTY_PATTERN.search(name)


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
    excluded = collections.Counter()

    # MIDAS is not only a rate feed. It carries three signal types, and only one
    # of them is rates: the other two are greenhouse-gas emissions and the CAISO
    # Flex Alert, a voluntary conservation call. Excluding by signal type is the
    # rule; excluding by party name was a proxy for it that kept missing cases.
    signal_rows = []
    other_signals = collections.Counter()
    for st, n in c.execute("SELECT signal_type, COUNT(*) FROM rate "
                           "WHERE signal_type IS NOT NULL AND signal_type != 'Electricity Rates' "
                           "GROUP BY 1"):
        other_signals[st] = n

    for seg, n, urls in c.execute(
            "SELECT substr(rid,6,4), COUNT(*), COUNT(DISTINCT rate_plan_url) FROM rate "
            "WHERE signal_type = 'Electricity Rates' GROUP BY 1"):
        e = look["energy"].get(seg[2:], {})
        d = look["distribution"].get(seg[:2], {})
        name = (e.get("Description") or d.get("Description") or "").strip()
        if not is_a_party(name):
            if name:
                excluded[name] += n
            continue
        if name not in KIND:
            unknown[name] += n
            continue
        a = agg[name]
        a["segs"].add(seg)
        a["n"] += n
        a["site"] = a["site"] or (e.get("URL") or d.get("URL") or "").strip()
    for st, (slug_, kind_, label, site) in SIGNAL_PARTY.items():
        n = c.execute("SELECT COUNT(*) FROM rate WHERE signal_type = ?", (st,)).fetchone()[0]
        if not n:
            continue
        segs = sorted({r[0] for r in c.execute(
            "SELECT DISTINCT substr(rid,6,4) FROM rate WHERE signal_type = ?", (st,))})
        signal_rows.append({"organization": label, "utility": slug_, "kind": kind_,
                            "delivered_by": "not delivered", "segments": segs,
                            "identifiers": n, "rate_links": 0, "site": site,
                            "filings_modeled": False})

    for seg, url in c.execute("SELECT substr(rid,6,4), rate_plan_url FROM rate "
                              "WHERE rate_plan_url IS NOT NULL GROUP BY 1,2"):
        e = look["energy"].get(seg[2:], {})
        d = look["distribution"].get(seg[:2], {})
        name = (e.get("Description") or d.get("Description") or "").strip()
        if name in agg:
            agg[name]["urls"].add(url)

    # Which utilities have filings. This tested for an `electricity/` directory
    # under a hardcoded us/ca root, so it answered "has a carrier directory"
    # rather than "has a filing", and a second country or commodity would not
    # have been seen at all.
    modeled = set(corpus.utilities_with_filings())

    rows = []
    for name, a in agg.items():
        slug, kind, delivers = KIND[name]
        rows.append({"organization": name, "utility": slug, "kind": kind,
                     "delivered_by": delivers, "segments": sorted(a["segs"]),
                     "identifiers": a["n"], "rate_links": len(a["urls"]),
                     "site": a["site"], "filings_modeled": slug in modeled})
    rows.extend(signal_rows)
    order = {"iou": 0, "pou": 1, "cca": 2, "alert": 3, "ghg": 4}
    rows.sort(key=lambda r: (order.get(r["kind"], 9), -r["identifiers"]))

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
    sellers = [r for r in rows if r["kind"] in ("iou", "pou", "cca")]
    signals = len(rows) - len(sellers)
    o += [f"{len(sellers)} organizations sell electricity here: {nm} have filings in this corpus "
          f"and {len(sellers) - nm} have a directory and a discovery manifest only. "
          f"{signals} further rows are signals MIDAS carries that are not rates and have no "
          f"seller, so they have no directory. Per-segment identifier counts and document "
          f"links are in [midas-catalog.md](./midas-catalog.md). They are not a size ranking: an "
          f"identifier names a composition, so a publisher that spells overlays into the name "
          f"carries far more of them than one that does not.", "",
          "**Kind is asserted, not derived.** MIDAS carries no classification. It distinguishes "
          "these only accidentally, through whether the distribution half of a party segment "
          "names a utility or reads `XX` for unspecified, which is a good signal and not a "
          "definition. The mapping lives in `dev/list_california_parties.py`.", "",
          "A community choice aggregator sells generation over an investor-owned utility's "
          "wires, so one of its customers is billed a composition: the aggregator's generation "
          "rate with the utility's delivery. Both halves have to be modeled to price a bill.", "",
          "**IOU** investor-owned utility, **POU** publicly owned utility, "
         "**CCA** community choice aggregator. **Alert** and **GHG** are signals "
         "MIDAS carries that are not rates and have no seller.", "",
         "| Organization | Kind | `utility` | Segment | Delivered by | Filings |",
          "|---|---|---|---|---|---|"]
    for r in rows:
        o.append(f"| [{r['organization']}]({r['site']}) | {KIND_LABEL[r['kind']]} | "
                 f"`{r['utility']}` | {', '.join('`'+s+'`' for s in r['segments'])} | "
                 f"{r['delivered_by']} | {'yes' if r['filings_modeled'] else 'none yet'} |")
    if excluded:
        o += ["", "## Excluded as not an organization", "",
              "Party segments naming a research feed or an upload fixture rather than a "
              "seller of electricity. Listed so the exclusion rule can be checked rather "
              "than trusted.", ""]
        for name, n in excluded.most_common():
            o.append(f"- {name} ({n:,} identifier{'' if n == 1 else 's'})")
    if unknown:
        o += ["", "## In the feed, not yet classified", "",
              "Named organizations with no entry in the mapping. Each is a party this report "
              "cannot place, and the omission is listed rather than silently dropped.", ""]
        for name, n in unknown.most_common():
            o.append(f"- {name} ({n:,} identifier{'' if n == 1 else 's'})")
    (REPO / "reports" / "california-parties.md").write_text("\n".join(o) + "\n")
    print(f"wrote reports/california-parties.md: {len(rows)} organizations, {tot:,} identifiers, "
          f"{nm} with filings, {len(unknown)} unclassified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
