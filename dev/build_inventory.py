#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Build a per-utility schedule inventory: what schedules exist, from any source.

A schedule inventory answers "what is there to model", which is a different
question from "what does this filing say" and needs a different kind of source.
MIDAS is one source and not the best one, so this is organized around a list of
sources, one adapter each, and a utility can draw on several.

  data/inventories/<utility>.json   one file per utility, tracked. Each schedule
                                    carries which source named it and when, so a
                                    schedule that only one weak source knows
                                    about is visible as exactly that.

TWO KINDS OF SOURCE, AND THE DISTINCTION IS LOAD-BEARING. An *inventory* source
is authoritative about which schedules exist: PG&E's tariff book lists its
electric schedules and that list is the answer. An *observed* source merely
names things it saw, at whatever granularity it happens to use, and may not
share a key space with the inventory at all.

Unioning the two over-counts badly. On 2026-09-23 PG&E's tariff book named 104
schedules and the MIDAS feed named 118 things, but only 12 of those were the same
schedule spelled differently (`A1` for `A-1`); 96 were rate options *within* a schedule
(`A10P` is Primary under Schedule A-10, `AG-FBP` is one of dozens under AG); and
10 matched nothing, several being CEC test entries. Treating that as a union
yielded 216 schedules for a utility that published 104.

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
import http.cookiejar
import json
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import utilities  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "data" / "inventories"
UA = {"User-Agent": "urpx-rate-plans/1.0 (+https://github.com/grid-coordination/urpx-rate-plans)"}

# MIDAS party segment -> utility directory. Only segments whose feed names a
# schedule rather than a composition appear here; see midas() for why, and
# dev/utilities.py for why that narrower view is a named accessor.
MIDAS_SEGMENTS = utilities.bundled_segment_utility()


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


SCE_HUB = ("https://www.sce.com/regulatory/regulatory-information/"
           "tariff-books/rates-pricing-choices")
SCE_SITE = "https://edisonintl.sharepoint.com/teams/Public/TM2"


def sce_tariff_book(offline: bool):
    """SCE's live tariff book, enumerated from its SharePoint folders.

    SCE publishes no HTML page listing its schedules: its own sitemap carries
    neither a PDF nor a SharePoint URL. What it does publish is six anonymous
    SharePoint share links on the hub page below, five of them rate-class
    folders of per-schedule PDFs.

    The folders are anonymously readable but not anonymously scrapable in the
    obvious way. Following a `:f:` share link sets an anonymous FedAuth cookie
    scoped to THAT share, and only then does the folder's file API answer. The
    cookie jar therefore has to be fresh per share link; reusing one from
    another share returns 403.

    DO NOT ENUMERATE THIS FROM THE RENDERED PAGE. The SharePoint file list is
    virtualized and pages at 30 rows. Scraping the DOM of the Other Rates folder
    yields only its first 30 files, alphabetically A through E, and looks complete:
    scrolling adds nothing, an 8000px viewport adds nothing, and sorting
    descending returns a different 30. Every count here is checked against the
    folder's own ItemCount for exactly that reason.

    What this enumerates is DOCUMENTS, not rate plans. One PDF can carry several
    plans this corpus models separately: ELECTRIC_SCHEDULES_TOU-D.pdf is the
    source for tou-d-4-9pm, tou-d-5-8pm, tou-d-prime and tou-d-prime-cpp. So
    SCE's inventory is coarser than the corpus, and the report's list of
    schedules modeled but unnamed by any source is where that shows up.
    """
    if offline:
        return
    ua = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"}
    hub = urllib.request.urlopen(
        urllib.request.Request(SCE_HUB, headers=dict(ua)), timeout=60).read().decode(
            "utf-8", "replace")
    links = [(re.sub(r"<[^>]+>", "", m.group(2)).strip(), m.group(1)) for m in re.finditer(
        r'<a[^>]*href="(https://edisonintl\.sharepoint\.com/:f:/t/Public/TM2/[^"]+)"[^>]*>(.*?)</a>',
        hub, re.S | re.I)]
    if not links:
        print(f"REFUSING: {SCE_HUB} carried no SharePoint folder links. The page "
              f"loaded, so the link shape changed; writing an empty inventory would "
              f"read as 'SCE publishes nothing'.", file=sys.stderr)
        raise SystemExit(3)

    total = 0
    for label, share in links:
        op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def api(path, sel):
            q = urllib.parse.quote(root, safe="/")
            u = f"{SCE_SITE}/_api/web/GetFolderByServerRelativeUrl('{q}'){path}?$select={sel}&$top=5000"
            return json.loads(op.open(urllib.request.Request(
                u, headers={**ua, "Accept": "application/json;odata=nometadata"}),
                timeout=60).read())

        r = op.open(urllib.request.Request(share, headers=dict(ua)), timeout=60)
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(r.geturl()).query)
        if "id" not in qs:
            continue
        root = qs["id"][0]
        meta = api("", "ItemCount,Name")
        files = api("/Files", "Name,ServerRelativeUrl")["value"]
        if meta.get("ItemCount") is not None and meta["ItemCount"] != len(files):
            print(f"REFUSING: folder '{label}' reports ItemCount "
                  f"{meta['ItemCount']} but the file listing returned {len(files)}. "
                  f"A partial listing is the failure mode this check exists for.",
                  file=sys.stderr)
            raise SystemExit(3)
        for f in files:
            m = re.match(r"^ELECTRIC_SCHEDULES_(.+)\.pdf$", f["Name"], re.I)
            if not m:
                continue
            total += 1
            yield "sce", slug(m.group(1)), {
                "code": m.group(1),
                "document_url": "https://edisonintl.sharepoint.com"
                                + urllib.parse.quote(f["ServerRelativeUrl"]),
                "rate_class": label,
                # Recorded because the document is not fetchable without it: the
                # share sets the anonymous cookie that authorizes the download.
                "share_url": share,
                "server_relative_url": f["ServerRelativeUrl"],
                "source": "sce-tariff-book",
            }
    if not total:
        print("REFUSING: the SCE folders held no ELECTRIC_SCHEDULES_*.pdf files.",
              file=sys.stderr)
        raise SystemExit(3)


sce_tariff_book.kind = "inventory"

SDGE_API = ("https://scg-uofa-api-prd-hzczb4hja0g6dcfv.a03.azurefd.net/"
            "scg-uofa-wpubtm-prd")


def sdge_tariff_portal(offline: bool):
    """SDG&E's regulatory tariff portal, read through the JSON API behind it.

    tariffsprd.sdge.com is a single-page app; this is the service it calls. It
    is the best of the three inventory surfaces in this file: a stable JSON
    contract rather than a regex over href attributes, no browser, no cookie, no
    paging, and it states which schedules are closed.

    `history` returns every schedule ever published and `tariffs` only those
    currently in force. Closed status is taken from membership in the latter
    rather than from TARF_STATUS_CD, because the two disagree: 100 rows are
    marked Active while only 99 appear in `tariffs`, the odd one being TOU-DR-E2,
    which is Active and whose rate group is nonetheless "Retired".

    The two kinds of schedule are served by different endpoints, and asking the
    wrong one gives a 404 rather than an error worth reading: `tariff` serves
    only what is in force, `historical` serves a named year. A closed schedule
    is recorded at the last year it was published, which is the version that was
    in force when it closed.

    `TARF_YEARS` is not exhaustive. DR-TOU lists 2000 onward, and 1999 returns a
    real tariff sheet. Years genuinely outside the range 404, so the list is a
    lower bound on what is available rather than the whole of it.
    """
    if offline:
        return

    def get(path):
        return json.loads(urllib.request.urlopen(urllib.request.Request(
            f"{SDGE_API}/{path}", headers={"User-Agent": "urpx-rate-plans/1.0",
                                           "Accept": "application/json"}),
            timeout=60).read())

    q = "utilId=SDGE&bookId=ELEC&sectId=ELEC-SCHEDS"
    history = get(f"history?{q}")
    current = {r["TARF_ID"] for r in get(f"tariffs?{q}")}
    if not history or not current:
        print("REFUSING: the SDG&E tariff API returned nothing. Writing an empty "
              "inventory would read as 'SDG&E publishes nothing'.", file=sys.stderr)
        raise SystemExit(3)
    for row in history:
        code = (row.get("TARF_ID") or "").strip()
        if not code:
            continue
        rec = {
            "code": code,
            "name": (row.get("TARF_NAME") or "").strip(),
            "status": "current" if code in current else "closed",
            "rate_class": (row.get("TARF_RATEGROUP") or "").strip(),
            "source": "sdge-tariff-portal",
        }
        years = sorted(row.get("TARF_YEARS") or [])
        if years:
            rec["years"] = years
        if row.get("TARF_KEY") is not None:
            if rec["status"] == "current":
                rec["document_url"] = (f"{SDGE_API}/tariff/?utilId=SDGE&bookId=ELEC"
                                       f"&tarfKey={row['TARF_KEY']}")
            elif years:
                # /tariff/ serves only what is in force: every closed schedule
                # 404s there. /historical/ serves them, keyed by year. The last
                # year published is the version that was in force when the
                # schedule closed, which is the one document per schedule this
                # store holds, matching how it treats every other publisher.
                rec["document_url"] = (f"{SDGE_API}/historical/?utilId=SDGE&bookId=ELEC"
                                       f"&tarfKey={row['TARF_KEY']}&tarfYear={years[-1]}")
                rec["document_year"] = years[-1]
        yield "sdge", slug(code), rec


sdge_tariff_portal.kind = "inventory"

GPC_SITE = "https://www.georgiapower.com"
GPC_HUBS = ("/residential/rate-plans.html", "/business/rate-plans-tariffs.html")


def gpc_tariff_library(offline: bool):
    """Georgia Power's tariff library, read from its residential and business rate pages.

    Georgia Power publishes no page listing its schedules. Each tariff sheet is
    served from one folder, /content/dam/georgia-power/pdfs/tariffs/<slug>.pdf,
    and linked from the rate-plan pages that use it: the two hub pages carry the
    riders, and the pages one level below them carry the schedules (r.pdf only
    from residential-service.html). So the inventory is every link into that
    folder from the hubs and the pages they link under the same paths. The pages
    are static HTML; no browser is needed.

    Links elsewhere are not schedules and are not recorded: terms-and-conditions
    PDFs, and superseded sheets kept under residential-pdfs/ (tariffs/2025/
    tou-reo-18.pdf, and pay-by-day-tariff.pdf, which is PBD-1's 2020 revision
    where tariffs/pbd.pdf is current). The store holds the current document per
    schedule, as it does for every other publisher.

    The code is the file's stem upper-cased, which is the schedule code without
    its revision suffix: the sheet in r.pdf is headed R-31, and the suffix
    changes with every revision (us/ga/gpc/utility.toml).
    """
    if offline:
        return

    def get(path):
        return urllib.request.urlopen(urllib.request.Request(
            GPC_SITE + path, headers=dict(UA)), timeout=60).read().decode("utf-8", "replace")

    pages = {hub: get(hub) for hub in GPC_HUBS}
    below = sorted({p for body in pages.values() for p in re.findall(
        r'href="(?:https://www\.georgiapower\.com)?'
        r'(/(?:residential/rate-plans|business/rate-plans-tariffs)/[^"#?]+\.html)"', body)})
    if not below:
        print(f"REFUSING: {', '.join(GPC_SITE + h for h in GPC_HUBS)} linked no rate-plan "
              f"pages. The pages loaded, so the link shape changed; reading only the hubs "
              f"would miss every schedule and keep only the riders.", file=sys.stderr)
        raise SystemExit(3)
    for path in below:
        pages[path] = get(path)
    stems = sorted({m for body in pages.values() for m in re.findall(
        r'href="(?:https://www\.georgiapower\.com)?'
        r'/content/dam/georgia-power/pdfs/tariffs/([A-Za-z0-9_-]+)\.pdf"', body)})
    if not stems:
        print("REFUSING: the Georgia Power rate pages linked no tariff sheets. Writing an "
              "empty inventory would read as 'Georgia Power publishes nothing'.",
              file=sys.stderr)
        raise SystemExit(3)
    for stem in stems:
        yield "gpc", slug(stem), {
            "code": stem.upper(),
            "document_url": f"{GPC_SITE}/content/dam/georgia-power/pdfs/tariffs/{stem}.pdf",
            "source": "gpc-tariff-library",
        }


gpc_tariff_library.kind = "inventory"


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


SOURCES = {"pge-tariff-book": pge_tariff_book,
           "sce-tariff-book": sce_tariff_book,
           "sdge-tariff-portal": sdge_tariff_portal,
           "gpc-tariff-library": gpc_tariff_library,
           "midas": midas}


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
    collisions: dict[str, list[dict]] = collections.defaultdict(list)
    ran: set[str] = set()
    for name in chosen:
        fn, produced = SOURCES[name], 0
        for util, sch, rec in fn(args.offline):
            if not sch:
                continue
            produced += 1
            if fn.kind == "inventory":
                cur = inventory[util].setdefault(sch, {"schedule": sch, "sources": {}})
                src = rec.pop("source")
                held = cur["sources"].get(src)
                # Two different schedule codes can slug to one directory name:
                # SDG&E publishes both 20/20 and 20-20, and both become "20-20".
                # Overwriting loses one silently, which is the failure this
                # whole file is built to avoid, so the loser is kept alongside.
                if held is not None and held.get("code") != rec.get("code"):
                    collisions[util].append({"slug": sch, "source": src,
                                             "codes": sorted({held.get("code"),
                                                              rec.get("code")})})
                    held.setdefault("also_named", []).append(rec)
                else:
                    cur["sources"][src] = rec
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
    # Its sources_run and slug collisions are carried too: no source of this run
    # read it, and dropping or restamping them would rewrite every other
    # utility's file on a one-source run, losing the record of why a schedule
    # carries also_named.
    carried_sources: dict[str, list[str]] = {}
    for f in sorted(OUT.glob("*.json")) if OUT.exists() else []:
        prior_doc = json.loads(f.read_text())
        util = prior_doc["utility"]
        if util in have_inventory or not prior_doc.get("has_inventory_source"):
            continue
        for sch, rec in prior_doc["schedules"].items():
            rec.pop("observed", None)   # re-attached below from this run
            inventory[util][sch] = rec
        have_inventory.add(util)
        carried_sources[util] = prior_doc.get("sources_run", sorted(ran))
        if prior_doc.get("slug_collisions"):
            collisions[util] = prior_doc["slug_collisions"]
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
               "sources_run": carried_sources.get(util, sorted(ran)),
               "has_inventory_source": has_inv,
               "note": ("What schedules this utility is known to publish, and which source "
                        "said so. first_seen is never restamped, so a run that finds nothing "
                        "new writes identical bytes."
                        if has_inv else
                        "NO INVENTORY SOURCE. Every schedule here is an observed name from a "
                        "feed, not a list this utility published, so the set is neither "
                        "complete nor guaranteed to be at schedule granularity."),
               "schedules": out}
        if collisions.get(util):
            doc["slug_collisions"] = collisions[util]
            doc["slug_collisions_note"] = (
                "Distinct schedule codes that reduce to the same directory name. "
                "The first is the schedule row; the others are kept on it under "
                "also_named so none is lost.")
        if unmatched.get(util):
            doc["unmatched"] = sorted(unmatched[util], key=lambda r: r["code"])
            doc["unmatched_note"] = ("Observed names that matched no schedule in the "
                                     "inventory. Each is either a gap in the inventory or a "
                                     "name this corpus does not yet understand.")
        path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        print(f"wrote {path.relative_to(REPO)}: {len(out)} schedule(s)"
              + (f", {len(collisions[util])} slug collision(s)" if collisions.get(util) else "")
              + (f", {len(unmatched[util])} unmatched" if unmatched.get(util) else "")
              + ("" if has_inv else "  [no inventory source]"))
    print(f"{total_new} newly named schedule(s) across {len(inventory)} utility(ies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
