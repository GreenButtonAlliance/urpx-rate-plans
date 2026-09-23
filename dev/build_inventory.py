#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Build a per-utility schedule inventory: what schedules exist, from any source.

A schedule inventory answers "what is there to model", which is a different
question from "what does this filing say" and needs a different kind of source.
MIDAS is one source and not the best one: it names 15 PG&E documents where PG&E's
own tariff book names 104. So this is organized around a list of sources, one
adapter each, and a utility can draw on several.

  data/inventories/<utility>.json   one file per utility, tracked. Each schedule
                                    carries which source named it and when, so a
                                    schedule that only one weak source knows
                                    about is visible as exactly that.

TWO KINDS OF SOURCE, AND THE DISTINCTION IS LOAD-BEARING. An *inventory* source
is authoritative about which schedules exist: PG&E's tariff book lists its 104
electric schedules and that list is the answer. An *observed* source merely
names things it saw, at whatever granularity it happens to use, and may not
share a key space with the inventory at all.

Unioning the two over-counts badly. PG&E's tariff book names 104 schedules and
the MIDAS feed names 118 things, but only 12 of those are the same schedule
spelled differently (`A1` for `A-1`); 96 are rate options *within* a schedule
(`A10P` is Primary under Schedule A-10, `AG-FBP` is one of dozens under AG); and
10 match nothing, several being CEC test entries. Treating that as a union
yields 216 schedules for a utility that publishes 104.

So only an inventory source creates a schedule. An observed name attaches to a
schedule it matches, and the match rule that did it is recorded so the
attachment can be audited. What matches nothing is kept in `unmatched` rather
than dropped, because an observed name with no schedule is either a gap in the
inventory or a name worth understanding. Where a utility has no inventory source
at all, its observed names are all there is, and the file says so.

IDEMPOTENCE. `first_seen` is set when a schedule is first named and never
restamped, and every other field is derived from the source, so a run that finds
nothing new rewrites byte-identical files. A schedule that a source stops naming
keeps its row and gains `last_absent`, because a tariff withdrawn is a fact
worth keeping rather than a row to delete.

    python3 dev/build_inventory.py              # all sources
    python3 dev/build_inventory.py --source midas   # one source, no network
    python3 dev/build_inventory.py --offline    # skip every networked source
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "data" / "inventories"
UA = {"User-Agent": "urpx-tariffs/1.0 (+https://github.com/grid-coordination/urpx-rate-plans)"}

# MIDAS party segment -> utility directory. Only segments whose feed names a
# schedule rather than a composition appear here; see midas() for why.
MIDAS_SEGMENTS = {"PGPG": "pge", "SCSC": "sce", "SDSD": "sdge",
                  "LALA": "ladwp", "SMSM": "smud"}


def matchkey(code: str) -> str:
    """Punctuation-insensitive key. PG&E's book writes A-1 where MIDAS writes A1."""
    return re.sub(r"[^a-z0-9]", "", urllib.parse.unquote(code).lower())


def slug(code: str) -> str:
    """Directory name for a schedule code, matching LAYOUT.md section 3."""
    s = urllib.parse.unquote(code).strip().lower()
    s = re.sub(r"\(sch\)", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def pge_tariff_book(offline: bool):
    """PG&E's electric tariff book index: the complete list of its schedules.

    This is a schedule inventory in the sense of LAYOUT.md section 5: it says
    which schedules exist, which is what bounds the modeling backlog. The
    directory it serves from is not listable (it 404s); this index page is the
    entry point.
    """
    if offline:
        return
    url = "https://www.pge.com/tariffs/en.html"
    body = urllib.request.urlopen(urllib.request.Request(url, headers=dict(UA)),
                                  timeout=60).read()
    hrefs = sorted(set(re.findall(rb'href="([^"]*ELEC_SCHEDS_[^"]*\.pdf)"', body)))
    if not hrefs:
        print(f"REFUSING: {url} named no schedules. The page loaded, so either the "
              f"link shape changed or the wrong page was served; writing an empty "
              f"inventory would read as 'PG&E publishes nothing'.", file=sys.stderr)
        raise SystemExit(3)
    for href in hrefs:
        h = href.decode()
        name = h.rsplit("/", 1)[-1]
        code = urllib.parse.unquote(name[len("ELEC_SCHEDS_"):-len(".pdf")]).replace("(Sch)", "").strip()
        yield "pge", slug(code), {
            "code": code,
            "document_url": urllib.parse.urljoin(url, h),
            "source": "pge-tariff-book",
        }


pge_tariff_book.kind = "inventory"


def midas(offline: bool):
    """Schedule names the CEC MIDAS feed carries, for the parties that name one.

    Which field holds the schedule differs by party, and for a community choice
    aggregator no field does. SDG&E puts the schedule in RateName (77 distinct)
    and the composition in AltRateName1 (2,689). SCE is the other way around.
    San Diego Community Power has 17,442 distinct RateName values and zero
    AltRateName1, one per composition, so the feed names no schedule at all for
    it and this source contributes nothing rather than inventing 17,442.
    """
    db = REPO / "data" / "midas" / "midas.sqlite"
    if not db.exists():
        return
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    # The field that carries schedule identity, per segment, chosen by which one
    # has few enough distinct values to be a schedule rather than a composition.
    for seg, util in MIDAS_SEGMENTS.items():
        counts = c.execute(
            "SELECT COUNT(DISTINCT rate_name), COUNT(DISTINCT alt_rate_name_1), COUNT(*) "
            "FROM rate WHERE substr(rid,6,4)=?", (seg,)).fetchone()
        n_name, n_alt, total = counts
        if not total:
            continue
        field = "rate_name" if (n_name and n_name <= n_alt or not n_alt) else "alt_rate_name_1"
        # A field with nearly as many values as there are rows is naming the
        # composition, not the schedule.
        if (n_name if field == "rate_name" else n_alt) > max(400, total // 4):
            continue
        rows = c.execute(
            f"SELECT {field}, COUNT(*), MIN(rate_plan_url), MIN(sector) FROM rate "
            f"WHERE substr(rid,6,4)=? AND {field} IS NOT NULL AND {field} != '' "
            f"GROUP BY 1", (seg,))
        for code, n, url, sector in rows:
            rec = {"code": code, "source": "midas", "midas_identifiers": n,
                   "midas_field": field}
            if url:
                rec["document_url"] = url
            if sector:
                rec["sector"] = sector
            yield util, slug(code), rec


midas.kind = "observed"


SOURCES = {"pge-tariff-book": pge_tariff_book, "midas": midas}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", action="append", choices=sorted(SOURCES),
                    help="run only these sources (default: all)")
    ap.add_argument("--offline", action="store_true", help="skip networked sources")
    ap.add_argument("--rebuild", action="store_true",
                    help="drop schedules no source names this run, instead of retaining "
                         "them. Retention is right for a withdrawn tariff and wrong after "
                         "a run that wrote bad rows, and only a person can tell which.")
    args = ap.parse_args()

    chosen = args.source or sorted(SOURCES)
    today = datetime.date.today().isoformat()

    inventory: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    observed: dict[str, list[tuple[str, dict]]] = collections.defaultdict(list)
    ran: set[str] = set()
    for name in chosen:
        fn, produced = SOURCES[name], 0
        for util, sch, rec in fn(args.offline):
            if not sch:
                continue
            produced += 1
            if fn.kind == "inventory":
                cur = inventory[util].setdefault(sch, {"schedule": sch, "sources": {}})
                cur["sources"][rec.pop("source")] = rec
            else:
                observed[util].append((sch, rec))
        if produced:
            ran.add(name)
        skipped = args.offline and getattr(fn, "networked", fn.kind == "inventory")
        print(f"  {name} ({fn.kind}): {produced} mention(s)"
              + (" (skipped, offline)" if skipped and not produced else ""))

    if not inventory and not observed:
        print("REFUSING: no source produced anything, so every inventory would be "
              "emptied. Nothing was written.", file=sys.stderr)
        return 3

    # Attach each observed name to a schedule, recording which rule matched so
    # the attachment can be checked. Exact beats prefix; nothing else is tried,
    # because a looser rule would silently mis-attach (MIDAS writes TOUC for
    # what the book calls E-TOU-C, and guessing that is not this script's job).
    unmatched: dict[str, list[dict]] = collections.defaultdict(list)
    have_inventory = {u for u, d in inventory.items() if d}

    # An inventory source that did not run this time must not demote a utility
    # to having none. --offline skips the networked ones, and without this the
    # observed names would be written as if they were the inventory: PG&E went
    # from its 104 published schedules to 216 observed names on one --offline
    # run. Carry the stored inventory forward and attach against that instead.
    for f in sorted(OUT.glob("*.json")) if OUT.exists() else []:
        prior_doc = json.loads(f.read_text())
        util = prior_doc["utility"]
        if util in have_inventory or not prior_doc.get("has_inventory_source"):
            continue
        for sch, rec in prior_doc["schedules"].items():
            rec.pop("observed", None)   # re-attached below from this run
            inventory[util][sch] = rec
        have_inventory.add(util)
        print(f"  {util}: carried forward {len(prior_doc['schedules'])} stored schedule(s); "
              f"no inventory source ran")
    for util, names in observed.items():
        byk = {}
        for sch, rec in inventory.get(util, {}).items():
            for src in rec["sources"].values():
                byk[matchkey(src["code"])] = sch
        for sch, rec in names:
            k = matchkey(rec["code"])
            hit, how = byk.get(k), "exact"
            if hit is None:
                cands = [b for b in byk if len(b) >= 2 and k.startswith(b)]
                if cands:
                    hit, how = byk[max(cands, key=len)], "variant-of"
            if hit is None:
                if util in have_inventory:
                    unmatched[util].append(rec | {"match": "none"})
                else:
                    # No inventory source for this utility, so an observed name
                    # is the only evidence the schedule exists.
                    cur = inventory[util].setdefault(sch, {"schedule": sch, "sources": {}})
                    cur["sources"][rec.pop("source")] = rec | {"match": "no-inventory-source"}
                continue
            tgt = inventory[util][hit].setdefault("observed", [])
            tgt.append(rec | {"match": how})

    OUT.mkdir(parents=True, exist_ok=True)
    total_new = 0
    for util, schedules in sorted(inventory.items()):
        path = OUT / f"{util}.json"
        prior = json.loads(path.read_text())["schedules"] if path.exists() else {}
        out = {}
        for sch, rec in sorted(schedules.items()):
            p_ = prior.get(sch, {})
            rec["first_seen"] = p_.get("first_seen", today)
            if not p_:
                total_new += 1
            if rec.get("observed"):
                rec["observed"] = sorted(rec["observed"], key=lambda r: r["code"])
            out[sch] = rec
        # A schedule a source has stopped naming is kept, flagged rather than
        # deleted: a withdrawn tariff is a fact, and its filings stay valid for
        # the window they covered.
        for sch, p_ in prior.items():
            if sch not in out and not args.rebuild:
                p_.setdefault("last_absent", today)
                out[sch] = p_
        has_inv = util in have_inventory
        doc = {"utility": util, "generator": "dev/build_inventory.py",
               "sources_run": sorted(ran),
               "has_inventory_source": has_inv,
               "note": ("What schedules this utility is known to publish, and which source "
                        "said so. first_seen is never restamped, so a run that finds nothing "
                        "new writes identical bytes."
                        if has_inv else
                        "NO INVENTORY SOURCE. Every schedule here is an observed name from a "
                        "feed, not a list this utility published, so the set is neither "
                        "complete nor guaranteed to be at schedule granularity."),
               "schedules": out}
        if unmatched.get(util):
            doc["unmatched"] = sorted(unmatched[util], key=lambda r: r["code"])
            doc["unmatched_note"] = ("Observed names that matched no schedule in the "
                                     "inventory. Each is either a gap in the inventory or a "
                                     "name this corpus does not yet understand.")
        path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        print(f"wrote {path.relative_to(REPO)}: {len(out)} schedule(s)"
              + (f", {len(unmatched[util])} unmatched" if unmatched.get(util) else "")
              + ("" if has_inv else "  [no inventory source]"))
    print(f"{total_new} newly named schedule(s) across {len(inventory)} utility(ies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
