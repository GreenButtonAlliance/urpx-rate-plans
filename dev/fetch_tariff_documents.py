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
    python3 dev/fetch_tariff_documents.py --unwrap F # unwrap a hand-fetched file
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import http.cookiejar
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import utilities  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "midas" / "midas.sqlite"
OUT = REPO / "data" / "documents"
MANIFEST = REPO / "data" / "documents.json"
UA = {"User-Agent": "urpx-rate-plans/1.0 (+https://github.com/grid-coordination/urpx-rate-plans)"}
# SharePoint refuses the polite identifier; it serves a browser string.
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"}

# Used ONLY on links this corpus is guessing about, which means MIDAS's
# RatePlan_Url: most of those point at a landing page, so an extension is the
# only signal that one is a document. It must NOT be applied to a URL an
# inventory source supplied, because such a source has already asserted the URL
# is that schedule's document, and SDG&E serves every one of its documents
# from an extensionless path (/tariff/?tarfKey=N). Applying this rule to those
# excluded all of them while the run still reported success.
IS_DOC = re.compile(r"\.(pdf|xlsx?|docx?|ashx)(\?|$)", re.I)

# MIDAS party segment -> utility directory, for documents only MIDAS names.
SEGMENT_UTILITY = utilities.segment_utility()


SP_HOST = "edisonintl.sharepoint.com"
_sessions: dict[str, urllib.request.OpenerDirector] = {}
_sessions_lock = threading.Lock()


def sharepoint_session(share_url: str) -> urllib.request.OpenerDirector:
    """An opener authorized for one SharePoint share.

    Opening a `:f:` share link sets an anonymous FedAuth cookie scoped to that
    share, and nothing under it is readable without one. The jar must be fresh
    per share: a cookie from a different share returns 403. Cached per share so
    that fetching a folder's files opens it once rather than once per file.
    """
    with _sessions_lock:
        op = _sessions.get(share_url)
        if op is not None:
            return op
    op = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.open(urllib.request.Request(share_url, headers=dict(BROWSER_UA)), timeout=60).read()
    with _sessions_lock:
        _sessions[share_url] = op
    return op


def content_key(body: bytes) -> str | None:
    """A change key for a document whose bytes are not stable.

    SDG&E regenerates its PDFs per request: fetching one URL three times gives
    three different sha256 values, differing in four bytes deep inside a
    compressed stream, with the length moving by one. The text is identical
    every time. So the bytes cannot say whether a document changed and the text
    can.

    Returns None when the text cannot be extracted, which makes the caller fall
    back to comparing bytes rather than treating every document as unchanged.
    """
    exe = shutil.which("pdftotext")
    if not exe or body[:5] != b"%PDF-":
        return None
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(body)
        f.flush()
        try:
            out = subprocess.run([exe, "-q", f.name, "-"], capture_output=True, timeout=120)
        except (subprocess.SubprocessError, OSError):
            return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return hashlib.sha256(out.stdout).hexdigest()


class EnvelopeError(ValueError):
    """Bytes that begin like a multipart envelope but do not parse as one."""


def unwrap_multipart(body: bytes) -> bytes:
    """SharePoint returns the file inside a multipart/form-data envelope.

    Both the download endpoint and the file API answer 200 with bytes that begin
    with a boundary marker rather than %PDF-. Hashing those would record the
    envelope, and the envelope's boundary changes per response, so the sha256
    would differ on every fetch of an unchanged document.

    The document is the one part's body: everything after the blank line ending
    the part headers and before the CRLF that opens the closing delimiter
    (RFC 2046 section 5.1.1). That includes any end-of-line after the PDF's
    %%EOF; the part's Content-Length counts it. The first version cut at the
    last %%EOF and dropped those bytes. Bytes that do not begin with "--" are
    returned unchanged; an envelope that does not parse as exactly one part, or
    whose body disagrees with its Content-Length, raises EnvelopeError.
    """
    if not body.startswith(b"--"):
        return body
    eol = body.find(b"\r\n")
    boundary = body[2:eol] if eol > 2 else b""
    if not boundary or len(boundary) > 70:
        raise EnvelopeError("no boundary on the first line")
    head_end = body.find(b"\r\n\r\n", eol)
    if head_end < 0:
        raise EnvelopeError("the part headers never end")
    headers = {}
    for line in body[eol + 2:head_end].split(b"\r\n"):
        name, sep, value = line.partition(b":")
        if not sep:
            raise EnvelopeError(f"malformed part header {line[:60]!r}")
        headers[name.strip().lower()] = value.strip()
    start = head_end + 4
    delimiter = b"\r\n--" + boundary
    end = body.find(delimiter, start)
    if end < 0:
        raise EnvelopeError("no closing boundary")
    if body[end + len(delimiter):end + len(delimiter) + 2] != b"--":
        raise EnvelopeError("more than one part")
    if body[end + len(delimiter) + 2:].strip(b"\r\n") != b"":
        raise EnvelopeError("bytes after the closing boundary")
    part = body[start:end]
    if b"content-length" in headers and int(headers[b"content-length"]) != len(part):
        raise EnvelopeError(f"part is {len(part)} bytes against Content-Length "
                            f"{headers[b'content-length'].decode()}")
    return part


def unwrap_files(paths: list[str]) -> int:
    """Unwrap committed or downloaded files in place, for documents fetched by hand.

    SCE documents fetched with the curl recipe in us/ca/sce/utility.toml arrive
    wrapped exactly as the fetcher's do. A file that is already a PDF is left
    alone. Refuses, changing nothing, if a result is not a PDF.
    """
    out = []
    for p in paths:
        raw = Path(p).read_bytes()
        try:
            pdf = unwrap_multipart(raw)
        except EnvelopeError as e:
            print(f"REFUSING: {p}: {e}", file=sys.stderr)
            return 3
        if pdf[:5] != b"%PDF-" or not pdf.rstrip(b"\r\n").endswith(b"%%EOF"):
            print(f"REFUSING: {p}: not a PDF after unwrapping", file=sys.stderr)
            return 3
        out.append((p, raw, pdf))
    for p, raw, pdf in out:
        if pdf is raw:
            print(f"{p}: already a PDF, sha256 {hashlib.sha256(raw).hexdigest()}")
            continue
        Path(p).write_bytes(pdf)
        print(f"{p}: envelope sha256 {hashlib.sha256(raw).hexdigest()} ({len(raw)} bytes) -> "
              f"PDF sha256 {hashlib.sha256(pdf).hexdigest()} ({len(pdf)} bytes)")
    return 0


def filename(url: str, target: dict, res: dict) -> str:
    """What to call the file on disk.

    A publisher that puts the document's name in the URL gets to keep it:
    ELEC_SCHEDS_E-TOU-C.pdf says what it is. SDG&E puts nothing there. Every one
    of its documents is served from /tariff/ or /historical/ with the identity
    in the query string, so the basename is the same for every one of them.

    The test is whether the basename carries a file extension, not whether it is
    one of a list of known-generic words. The first version listed "tariff",
    "download", "index", "view" and "file", which covered /tariff/ and then let
    all 60 documents from /historical/ overwrite each other as historical.pdf.
    A rule that has to enumerate the failures will keep missing one.
    """
    name = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name
    if not Path(name).suffix:
        sched = next((o.split(":", 1)[1] for o in target["segments"]
                      if ":" in o and not o.startswith("midas:")), None)
        if sched:
            # A year distinguishes editions of one schedule, so a schedule whose
            # archive is later fetched in full does not collapse to one file.
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            year = (q.get("tarfYear") or [None])[0]
            name = f"{sched}-{year}.pdf" if year else f"{sched}.pdf"
    if not Path(name).suffix and (res.get("media_type") or "").endswith("pdf"):
        name += ".pdf"
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) or "document"


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


def normalize(url: str) -> tuple[str, str, str]:
    """Identity of the document behind a URL.

    PG&E publishes the same tariff at pge.com and www.pge.com, and escapes a
    space in some filenames and not others, so the raw URL over-counts.

    The query string is part of the identity. SDG&E serves every schedule from
    one path and distinguishes them only by tarfKey, so dropping the query
    collapsed all 158 of its documents onto a single key and fetched one.
    """
    p = urllib.parse.urlparse(url.lower())
    return (p.netloc.removeprefix("www."),
            urllib.parse.unquote(p.path).replace(" ", ""),
            urllib.parse.urlencode(sorted(urllib.parse.parse_qsl(p.query))))


def _links():
    """(url, origin, weight) from every source that names a document."""
    if DB.exists():
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        for rid, url in c.execute("SELECT rid, rate_plan_url FROM rate "
                                  "WHERE rate_plan_url IS NOT NULL AND rate_plan_url != ''"):
            yield url, f"midas:{rid[5:9]}", 1, None, None
    inv = REPO / "data" / "inventories"
    for f in sorted(inv.glob("*.json")) if inv.exists() else []:
        d = json.loads(f.read_text())
        for sch, rec in d["schedules"].items():
            for src, body in rec.get("sources", {}).items():
                # also_named holds schedules whose code reduced to a directory
                # name already taken. They are real documents and were being
                # skipped because only the winning record was read.
                for b in [body, *body.get("also_named", [])]:
                    if b.get("document_url"):
                        yield (b["document_url"], f"{d['utility']}:{sch}", 0,
                               b.get("share_url"), b.get("server_relative_url"))


def load_targets() -> dict[str, dict]:
    if not DB.exists() and not (REPO / "data" / "inventories").exists():
        print("REFUSING: neither a mined MIDAS store nor an inventory exists, so nothing "
              "names a document. Run dev/mine_midas.py or dev/build_inventory.py first.",
              file=sys.stderr)
        raise SystemExit(3)
    seen: dict[str, dict] = {}
    groups: dict[tuple[str, str], str] = {}
    # Counted from the inventory files themselves, NOT from _links(), so that
    # anything dropping documents anywhere in between is caught. Counting from
    # the same pipeline being checked makes the guard vacuous: the first
    # version did that and passed while 158 documents went missing.
    named_by_inventory = collections.Counter()
    inv = REPO / "data" / "inventories"
    for f in sorted(inv.glob("*.json")) if inv.exists() else []:
        d = json.loads(f.read_text())
        named_by_inventory[d["utility"]] += sum(
            1 for rec in d["schedules"].values()
            for body in rec.get("sources", {}).values() if body.get("document_url"))

    for url, origin, weight, share, srv in _links():
        if weight and not IS_DOC.search(url):
            # A guess, and it does not look like a document. Inventory-supplied
            # URLs are never filtered here; see the note on IS_DOC.
            continue
        key = normalize(url)
        # Several URLs can name one document. Fetch the one the most identifiers
        # point at, and record the others as aliases rather than fetching twice.
        seen.setdefault(url, {"url": url, "identifiers": 0, "segments": set(),
                              "key": key, "inventory": False,
                              "share_url": share, "server_relative_url": srv})
        seen[url]["identifiers"] += weight
        seen[url]["segments"].add(origin)
        if share and not seen[url].get("share_url"):
            seen[url]["share_url"] = share
            seen[url]["server_relative_url"] = srv
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
        print("REFUSING: no source names a document at all, which would write an "
              "empty manifest that reads as 'nothing publishes documents'.",
              file=sys.stderr)
        raise SystemExit(3)
    # A utility whose inventory names documents must reach the fetch list. This
    # exists because SDG&E's 158 silently did not, and the run still printed a
    # success line naming a plausible total.
    for util, n in named_by_inventory.items():
        if not n:
            # An inventory can legitimately name no document at all: SMUD's
            # schedules come from an observed feed that carries no link.
            continue
        got = sum(1 for d in seen.values()
                  if any(o.startswith(f"{util}:") for o in d["segments"]))
        if not got:
            print(f"REFUSING: {util}'s inventory names {n} document(s) and none "
                  f"reached the fetch list. Continuing would report success "
                  f"having fetched nothing for it.", file=sys.stderr)
            raise SystemExit(3)
    return seen


def fetch(url: str, prior: dict | None, recheck: bool, target: dict | None = None) -> dict:
    """One document. Never raises: an unreachable host is a result, not a crash."""
    if target and target.get("share_url") and SP_HOST in url:
        return fetch_sharepoint(url, target)
    req = urllib.request.Request(url, headers=dict(UA))
    if prior and not recheck:
        if prior.get("etag"):
            req.add_header("If-None-Match", prior["etag"])
        if prior.get("last_modified"):
            req.add_header("If-Modified-Since", prior["last_modified"])
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            h = r.headers
            media_type = (h.get("Content-Type") or "").split(";")[0].strip() or None
            # An envelope can arrive from any host fronting SharePoint, so it is
            # unwrapped here too, and what is inside it is what gets judged.
            try:
                body = unwrap_multipart(raw)
            except EnvelopeError as e:
                return {"outcome": "not-a-document", "status": r.status,
                        "note": f"a multipart envelope that does not parse: {e}"}
            if body is not raw and body[:5] == b"%PDF-":
                media_type = "application/pdf"
            out = {"status": r.status, "bytes": len(body),
                   "sha256": hashlib.sha256(body).hexdigest(),
                   "media_type": media_type,
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


def fetch_sharepoint(url: str, target: dict) -> dict:
    """A document behind a SharePoint anonymous share.

    Fetching the rendered file path returns 403 even with the share cookie; the
    download endpoint is what answers, and what it answers with is wrapped.
    Neither Last-Modified nor ETag is usable here, so change detection is by
    sha256 of the unwrapped bytes.
    """
    try:
        op = sharepoint_session(target["share_url"])
        srv = target.get("server_relative_url")
        if not srv:
            srv = urllib.parse.unquote(urllib.parse.urlparse(url).path)
        dl = (f"https://{SP_HOST}/teams/Public/TM2/_layouts/15/download.aspx"
              f"?SourceUrl={urllib.parse.quote(srv)}")
        with op.open(urllib.request.Request(dl, headers=dict(BROWSER_UA)), timeout=120) as r:
            raw = r.read()
        try:
            body = unwrap_multipart(raw)
        except EnvelopeError as e:
            return {"outcome": "not-a-document", "status": 200,
                    "note": f"the download endpoint answered 200 with a multipart "
                            f"envelope that does not parse: {e}"}
        if body[:5] != b"%PDF-":
            return {"outcome": "not-a-document", "status": 200,
                    "note": "the download endpoint answered 200 with something "
                            "that is not a PDF even after unwrapping"}
        return {"outcome": "fetched", "status": 200, "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
                "media_type": "application/pdf", "etag": None,
                "last_modified": None, "final_url": None, "_body": body}
    except urllib.error.HTTPError as e:
        return {"outcome": "http-error", "status": e.code, "note": str(e.reason)}
    except Exception as e:  # noqa: BLE001
        return {"outcome": "unreachable", "note": f"{type(e).__name__}: {e}"}


def file_path_clashes(rows) -> list[str]:
    """Documents that would be written to the same path.

    Two documents must never share a file path. Both filename defects in this
    file were this invariant being violated silently: the manifest recorded 159
    SDG&E documents while the directory held one, and every printed count still
    looked right, because a count of rows is not a count of files.
    """
    claimed: dict[str, str] = {}
    out: list[str] = []
    for d in rows:
        f = d.get("file")
        if not f:
            continue
        if f in claimed and claimed[f] != d["url"]:
            out.append(f"{f} <- {claimed[f]} and {d['url']}")
        claimed[f] = d["url"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recheck", action="store_true",
                    help="ignore stored ETag/Last-Modified and fetch every document")
    ap.add_argument("--status", action="store_true", help="report the manifest, no network")
    ap.add_argument("--unwrap", nargs="+", metavar="FILE",
                    help="unwrap SharePoint multipart envelopes in these files in place, "
                         "no network; for documents fetched by hand")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    if args.unwrap:
        return unwrap_files(args.unwrap)

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
                lambda u: fetch(u, prior.get(u), args.recheck, targets.get(u)), canonical)):
            t, p = targets[url], prior.get(url, {})
            body = res.pop("_body", None)
            # `state` is a fact about the document, not about this run: a row
            # must not change merely because the second run got a 304 where the
            # first got a 200. Without this the manifest churned once on the
            # fetched -> unchanged transition and read as a run log.
            row = {"url": url, "identifiers": t["identifiers"], "named_by": t["segments"]}

            # A row is only "unchanged" if the file it claims is still there.
            # Without this a manifest can assert it holds a document that was
            # removed or overwritten, and no run would ever notice.
            on_disk = bool(p.get("file")) and (REPO / p["file"]).exists()
            same = res["outcome"] == "unchanged" and on_disk
            if res["outcome"] == "unchanged" and not on_disk:
                res = fetch(url, None, True, t)
                body = res.pop("_body", None)
            if res["outcome"] == "fetched" and not same and on_disk:
                if p.get("sha256") == res["sha256"]:
                    same = True
                else:
                    # Bytes differ. That is not the same as the document having
                    # changed: SDG&E regenerates its PDFs per request. Ask the
                    # text before believing the bytes.
                    ck = content_key(body)
                    res["content_sha256"] = ck
                    have = p.get("content_sha256")
                    if have is None and p.get("file") and ck:
                        f = REPO / p["file"]
                        if f.exists():
                            have = content_key(f.read_bytes())
                    if ck and have and ck == have:
                        same = True
            if same:
                # Carry the prior row forward untouched so a no-op run is a no-op
                # in git too. See the docstring on what retrieved_on means.
                row.update({k: v for k, v in p.items()
                            if k in ("sha256", "retrieved_on", "media_type", "bytes",
                                     "etag", "last_modified", "file", "final_url", "note",
                                     "content_sha256")})
                if res.get("content_sha256") and not row.get("content_sha256"):
                    row["content_sha256"] = res["content_sha256"]
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
                rel = f"{owner(t['segments'])}/{filename(url, t, res)}"
                (OUT / rel).parent.mkdir(parents=True, exist_ok=True)
                (OUT / rel).write_bytes(body)
                row.update({"sha256": res["sha256"], "retrieved_on": today,
                            "media_type": res["media_type"], "bytes": res["bytes"],
                            "etag": res["etag"], "last_modified": res["last_modified"],
                            "file": f"data/documents/{rel}"})
                ck = res.get("content_sha256") or content_key(body)
                if ck:
                    row["content_sha256"] = ck
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

    clashes = file_path_clashes(results.values())
    if clashes:
        print(f"REFUSING: {len(clashes)} file path(s) claimed by more than one "
              f"document, so the later fetch overwrote the earlier and the "
              f"manifest would report both as held.", file=sys.stderr)
        for c in clashes[:5]:
            print(f"  {c}", file=sys.stderr)
        return 3

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
