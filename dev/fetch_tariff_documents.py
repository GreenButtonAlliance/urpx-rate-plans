#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Fetch the tariff documents our sources link to, and record what happened to each.

Two kinds of source name a document. A utility's own tariff book names one per
schedule, which is the complete set. MIDAS carries a RatePlan_Url per rate
identifier, most absent, some pointing at a rates landing page, a few at the
utility's own document. Both feed this, because a document is what a filing is
modeled from and it does not matter who pointed at it. Provenance is recorded in
the same shape a filing's tariff.toml uses: url, sha256, retrieved_on,
media_type.

DEAD LINKS ARE RECORDED, NOT DROPPED. Most of the linked documents cannot be
fetched at all, and that is a finding about the feed rather than an error to
skip past. Every URL gets a row whatever happens to it, so the manifest says how
much of the feed's own linking actually resolves.

WHAT IS AND IS NOT COMMITTED. The documents land in data/documents/, which
is gitignored: they are public records but they belong to no filing yet, and a
staging area of unmodeled PDFs is not corpus content. What is committed is
data/midas/documents.json, the provenance manifest. When one of these is
modeled, its PDF moves into the filing directory with its own tariff.toml, which
is where a source document is meant to live.

IDEMPOTENCE, AND WHAT retrieved_on MEANS HERE. A run sends the stored ETag and
Last-Modified as If-None-Match and If-Modified-Since. A 304, or a 200 whose
bytes hash to what is already stored, leaves the row untouched, so a run that
finds nothing new writes byte-identical bytes and `git diff` is empty. The cost
is that `retrieved_on` means "when these bytes were first seen" rather than
"when this was last checked": stamping every run would churn the file on every
run and make a no-op look like a change. The same reasoning governs the MIDAS
mine itself (LAYOUT.md section 10b).

    python3 dev/fetch_tariff_documents.py            # fetch what is new or changed
    python3 dev/fetch_tariff_documents.py --recheck  # ignore stored validators
    python3 dev/fetch_tariff_documents.py --status   # what is known, no network
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "midas" / "midas.sqlite"
OUT = REPO / "data" / "documents"
MANIFEST = REPO / "data" / "documents.json"
UA = {"User-Agent": "urpx-tariffs/1.0 (+https://github.com/grid-coordination/urpx-rate-plans)"}

# Same rule the catalog uses, so the two reports cannot disagree about what
# counts as a document.
IS_DOC = re.compile(r"\.(pdf|xlsx?|docx?|ashx)(\?|$)", re.I)

# MIDAS party segment -> utility directory, for documents only MIDAS names.
SEGMENT_UTILITY = {"PGPG": "pge", "PGXX": "pge", "SCSC": "sce", "SCXX": "sce",
                   "SDSD": "sdge", "SDXX": "sdge", "LALA": "ladwp", "SMSM": "smud"}


def owner(named_by: list[str]) -> str:
    """Which utility's document this is.

    An inventory origin already says ("pge:a-1"); a MIDAS origin gives a party
    segment that has to be decoded. Unattributed is a real answer, not a bug:
    it means a source named a document without saying whose it is.
    """
    for o in named_by:
        who, _, rest = o.partition(":")
        if who != "midas":
            return who
        if rest in SEGMENT_UTILITY:
            return SEGMENT_UTILITY[rest]
    return "unattributed"


def normalize(url: str) -> tuple[str, str]:
    """Identity of the document behind a URL.

    PG&E publishes the same tariff at pge.com and www.pge.com, and escapes a
    space in some filenames and not others, so the raw URL over-counts.
    """
    p = urllib.parse.urlparse(url.lower())
    return (p.netloc.removeprefix("www."),
            urllib.parse.unquote(p.path).replace(" ", ""))


def _links():
    """(url, origin, weight) from every source that names a document."""
    if DB.exists():
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        for rid, url in c.execute("SELECT rid, rate_plan_url FROM rate "
                                  "WHERE rate_plan_url IS NOT NULL AND rate_plan_url != ''"):
            yield url, f"midas:{rid[5:9]}", 1
    inv = REPO / "data" / "inventories"
    for f in sorted(inv.glob("*.json")) if inv.exists() else []:
        d = json.loads(f.read_text())
        for sch, rec in d["schedules"].items():
            for src, body in rec.get("sources", {}).items():
                if body.get("document_url"):
                    yield body["document_url"], f"{d['utility']}:{sch}", 0


def load_targets() -> dict[str, dict]:
    if not DB.exists() and not (REPO / "data" / "inventories").exists():
        print("REFUSING: neither a mined MIDAS store nor an inventory exists, so nothing "
              "names a document. Run dev/mine_midas.py or dev/build_inventory.py first.",
              file=sys.stderr)
        raise SystemExit(3)
    seen: dict[str, dict] = {}
    groups: dict[tuple[str, str], str] = {}
    for url, origin, weight in _links():
        if not IS_DOC.search(url):
            continue
        key = normalize(url)
        # Several URLs can name one document. Fetch the one the most identifiers
        # point at, and record the others as aliases rather than fetching twice.
        seen.setdefault(url, {"url": url, "identifiers": 0, "segments": set(),
                              "key": key, "inventory": False})
        seen[url]["identifiers"] += weight
        seen[url]["segments"].add(origin)
        if weight == 0:
            seen[url]["inventory"] = True
    # Prefer the spelling a utility's own tariff book uses as the one to fetch;
    # MIDAS writes pge.com where the book writes www.pge.com for the same file.
    for url, d in sorted(seen.items(), key=lambda kv: (not kv[1]["inventory"],
                                                       -kv[1]["identifiers"], kv[0])):
        groups.setdefault(d["key"], url)
    for url, d in seen.items():
        d["canonical"] = groups[d["key"]]
        d["segments"] = sorted(d["segments"])
    if not seen:
        print("REFUSING: the store holds no document links at all, which would "
              "write an empty manifest that reads as 'the feed links nothing'.",
              file=sys.stderr)
        raise SystemExit(3)
    return seen


def fetch(url: str, prior: dict | None, recheck: bool) -> dict:
    """One document. Never raises: an unreachable host is a result, not a crash."""
    req = urllib.request.Request(url, headers=dict(UA))
    if prior and not recheck:
        if prior.get("etag"):
            req.add_header("If-None-Match", prior["etag"])
        if prior.get("last_modified"):
            req.add_header("If-Modified-Since", prior["last_modified"])
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            h = r.headers
            out = {"status": r.status, "bytes": len(body),
                   "sha256": hashlib.sha256(body).hexdigest(),
                   "media_type": (h.get("Content-Type") or "").split(";")[0].strip() or None,
                   "etag": h.get("ETag"), "last_modified": h.get("Last-Modified"),
                   "final_url": r.url if r.url != url else None}
            # A 200 of text/html at a URL ending .pdf is a redirect to an error
            # page wearing a document's clothes. Three SMUD links do exactly
            # this, so content type decides, not the extension or the status.
            if out["media_type"] and not out["media_type"].startswith(
                    ("application/pdf", "application/vnd", "application/msword",
                     "application/octet-stream")):
                out["outcome"] = "not-a-document"
                out["note"] = (f"served {out['media_type']}"
                               + (f", redirected to {r.url}" if out["final_url"] else ""))
                return out
            out["outcome"] = "fetched"
            out["_body"] = body
            return out
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return {"outcome": "unchanged", "status": 304}
        return {"outcome": "http-error", "status": e.code, "note": e.reason}
    except Exception as e:  # noqa: BLE001
        return {"outcome": "unreachable", "note": f"{type(e).__name__}: {e}"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recheck", action="store_true",
                    help="ignore stored ETag/Last-Modified and fetch every document")
    ap.add_argument("--status", action="store_true", help="report the manifest, no network")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    targets = load_targets()
    prior = {}
    if MANIFEST.exists():
        prior = {d["url"]: d for d in json.loads(MANIFEST.read_text())["documents"]}

    if args.status:
        if not prior:
            print("no manifest yet; run without --status")
            return 0
        by = collections.Counter(d.get("state", "?") for d in prior.values())
        print(f"{len(prior)} URL(s) recorded: " + ", ".join(f"{k} {v}" for k, v in by.most_common()))
        return 0

    canonical = [u for u, d in targets.items() if d["canonical"] == u]
    print(f"{len(targets)} document URL(s), {len(canonical)} distinct after normalizing; "
          f"fetching with {args.workers} workers", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    results: dict[str, dict] = {}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for url, res in zip(canonical, pool.map(
                lambda u: fetch(u, prior.get(u), args.recheck), canonical)):
            t, p = targets[url], prior.get(url, {})
            body = res.pop("_body", None)
            # `state` is a fact about the document, not about this run: a row
            # must not change merely because the second run got a 304 where the
            # first got a 200. Without this the manifest churned once on the
            # fetched -> unchanged transition and read as a run log.
            row = {"url": url, "identifiers": t["identifiers"], "named_by": t["segments"]}

            if res["outcome"] == "unchanged" or (
                    res["outcome"] == "fetched" and p.get("sha256") == res["sha256"]):
                # Carry the prior row forward untouched so a no-op run is a no-op
                # in git too. See the docstring on what retrieved_on means.
                row.update({k: v for k, v in p.items()
                            if k in ("sha256", "retrieved_on", "media_type", "bytes",
                                     "etag", "last_modified", "file", "final_url", "note")})
                row["state"] = "have-document"
                # The layout can change under a document that never does. Move
                # the file rather than leaving the manifest pointing at a path
                # that no longer exists.
                if row.get("file"):
                    name = Path(row["file"]).name
                    want = f"data/documents/{owner(t['segments'])}/{name}"
                    if row["file"] != want:
                        src, dst = REPO / row["file"], REPO / want
                        if src.exists():
                            dst.parent.mkdir(parents=True, exist_ok=True)
                            src.replace(dst)
                        row["file"] = want
            elif res["outcome"] == "fetched":
                name = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name
                name = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "document"
                rel = f"{owner(t['segments'])}/{name}"
                (OUT / rel).parent.mkdir(parents=True, exist_ok=True)
                (OUT / rel).write_bytes(body)
                row.update({"sha256": res["sha256"], "retrieved_on": today,
                            "media_type": res["media_type"], "bytes": res["bytes"],
                            "etag": res["etag"], "last_modified": res["last_modified"],
                            "file": f"data/documents/{rel}"})
                row["state"] = "have-document"
                if res.get("final_url"):
                    row["final_url"] = res["final_url"]
            else:
                row["state"] = res["outcome"]
                row.update({k: v for k, v in res.items() if k in ("status", "note")})
                # Keep what a previous run managed to get, so one bad day does
                # not erase a document that was fetched successfully before.
                for k in ("sha256", "retrieved_on", "media_type", "bytes", "file"):
                    if p.get(k):
                        row.setdefault(k, p[k])
                if p.get("sha256"):
                    row["note"] = (row.get("note", "") +
                                   f" (a copy from {p['retrieved_on']} is retained)").strip()
            results[url] = row

    for url, t in targets.items():
        if url not in results:
            results[url] = {"url": url, "identifiers": t["identifiers"],
                            "named_by": t["segments"], "state": "alias",
                            "alias_of": t["canonical"]}

    docs = sorted(results.values(), key=lambda d: d["url"])
    MANIFEST.write_text(json.dumps(
        {"generator": "dev/fetch_tariff_documents.py",
         "note": ("Provenance for the tariff documents MIDAS links to. The documents "
                  "themselves are gitignored under data/documents/; this file is "
                  "the tracked record. retrieved_on is when these bytes were first "
                  "seen, not when the URL was last checked."),
         "documents": docs}, indent=2, sort_keys=True) + "\n")

    by = collections.Counter(d["state"] for d in docs)
    print("  " + ", ".join(f"{k} {v}" for k, v in by.most_common()))
    ok = sum(1 for d in docs if d.get("sha256"))
    print(f"wrote {MANIFEST.relative_to(REPO)}: {len(docs)} URL(s), {ok} with a document in hand")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
