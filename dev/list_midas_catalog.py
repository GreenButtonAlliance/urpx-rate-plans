#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Generate reports/midas-catalog.{md,edn}: what California publishes, and what we model.

Reads the mined MIDAS metadata in `data/midas/` and answers three questions a
corpus that intends to cover California has to answer before it can:

  WHO PUBLISHES. Every party in the feed, decoded from the two halves of the
  party segment through the Distribution and Energy lookup tables, with how many
  identifiers each carries and whether this corpus models it. That is the list
  of utilities and community choice aggregators that exist.

  WHAT DOCUMENTS BACK THEM. Distinct `RatePlan_Url` values, how many identifiers
  each backs, and whether the link is a document or a landing page. Identifiers
  outnumber documents heavily, so this is the set of things that would actually
  have to be read.

  WHAT TO MODEL NEXT. Candidates ranked by how many identifiers a single
  document backs, since one tariff document covering many identifiers is the
  cheapest coverage available.

This report describes a THIRD PARTY'S catalog. It asserts nothing about our
filings and writes nothing into `us/`. A party appearing here is not a
commitment to model it.

Run from repo root:  python3 dev/list_midas_catalog.py
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STORE = REPO / "data" / "midas"

# Party segments this corpus already models, by utility directory under us/ca/.
MODELED = {"PGPG": "pge", "PGXX": "pge", "SCSC": "sce", "SCXX": "sce",
           "SDSD": "sdge", "SDXX": "sdge", "LALA": "ladwp", "SMSM": "smud"}
# Research, test and signal segments: real rows, not tariffs to model.
NOT_TARIFFS = {"CFCF", "TSTS", "TSXX", "HPHP", "FLEX"}


def load():
    rins = STORE / "rins.jsonl"
    if not rins.exists():
        print("REFUSING: no mined store at data/midas/rins.jsonl. "
              "Run dev/mine_midas.py first.", file=sys.stderr)
        raise SystemExit(3)
    recs = [json.loads(l) for l in rins.read_text().splitlines() if l.strip()]
    if not recs:
        print("REFUSING: the mined store is empty, so every count below would be "
              "zero and would read as 'California publishes nothing'.", file=sys.stderr)
        raise SystemExit(3)
    look = {}
    for name in ("distribution", "energy"):
        f = STORE / "lookups" / f"{name}.json"
        look[name] = {r["UploadCode"]: r for r in json.loads(f.read_text())} if f.exists() else {}
    census = json.loads((STORE / "census.json").read_text()) if (STORE / "census.json").exists() else {}
    return recs, look, census


def is_document(url: str) -> bool:
    """A link to a specific document rather than a rates landing page."""
    return bool(re.search(r"\.(pdf|xlsx?|docx?|ashx)(\?|$)", url, re.I))


def is_malformed(url: str) -> bool:
    """MIDAS ships some links with a doubled scheme, e.g. https://https//HOST/path."""
    return bool(re.search(r"https?://https?//", url, re.I))


def build():
    recs, look, census = load()
    parties = collections.defaultdict(lambda: {"n": 0, "urls": collections.Counter()})
    for r in recs:
        rid = r["rid"]
        if rid.count("-") < 3:
            continue
        seg = rid.split("-")[1]
        p = parties[seg]
        p["n"] += 1
        if r.get("rate_plan_url"):
            p["urls"][r["rate_plan_url"]] += 1

    rows = []
    for seg, p in parties.items():
        d = look["distribution"].get(seg[:2], {})
        e = look["energy"].get(seg[2:], {})
        rows.append({
            "segment": seg,
            "distribution": d.get("Description", "?").strip(),
            "supplier": e.get("Description", "?").strip(),
            "site": (e.get("URL") or d.get("URL") or "").strip(),
            "identifiers": p["n"],
            "documents": len(p["urls"]),
            "modeled_as": MODELED.get(seg),
            "kind": "not-a-tariff" if seg in NOT_TARIFFS else
                    ("modeled" if seg in MODELED else "unmodeled"),
        })
    rows.sort(key=lambda r: (-r["identifiers"], r["segment"]))

    docs = collections.Counter()
    doc_party = collections.defaultdict(set)
    for seg, p in parties.items():
        if seg in NOT_TARIFFS:
            continue
        for u, k in p["urls"].items():
            docs[u] += k
            doc_party[u].add(seg)
    catalog = [{"url": u, "identifiers": k, "segments": sorted(doc_party[u]),
                "is_document": is_document(u),
                "modeled": all(s in MODELED for s in doc_party[u])}
               for u, k in docs.most_common()]

    return {"rows": rows, "catalog": catalog, "records": len(recs),
            "feed_identifiers": census.get("identifiers"),
            # The feed changes during a mine that takes hours, so exact equality
            # would report a finished mine as partial forever. Within 0.1% is done.
            "complete": (census.get("identifiers") is None
                         or abs(census["identifiers"] - len(recs)) <= max(5, census["identifiers"] // 1000))}


def render_md(d) -> str:
    o = ["# MIDAS catalog: what California publishes", "",
         "Auto-generated by `dev/list_midas_catalog.py` from `data/midas/`. Do not edit by hand.", ""]
    if not d["complete"]:
        o += [f"> **Partial.** {d['records']:,} of {d['feed_identifiers']:,} identifiers mined so far. "
              f"Counts below are of what has been mined, not of the feed.", ""]
    unmod = [r for r in d["rows"] if r["kind"] == "unmodeled"]
    nmod = len([r for r in d["rows"] if r["kind"] == "modeled"])
    ntest = len([r for r in d["rows"] if r["kind"] == "not-a-tariff"])
    o += [f"{d['records']:,} identifiers over {len(d['rows'])} party segments. "
          f"{nmod} {'segment is' if nmod == 1 else 'segments are'} modeled here, "
          f"{len(unmod)} {'is' if len(unmod) == 1 else 'are'} not, and {ntest} "
          f"{'is a research or test signal' if ntest == 1 else 'are research or test signals'} "
          f"rather than tariffs.", "",
         "A party segment is two codes, the distribution utility and the energy supplier, "
         "decoded through the MIDAS `Distribution` and `Energy` lookup tables. `Unspecified` "
         "distribution means a generation-only identifier, which is how a community choice "
         "aggregator appears.", "",
         "## Parties", "",
         "| Segment | Distribution | Supplier | Identifiers | Documents | In this corpus |",
         "|---|---|---|---:|---:|---|"]
    for r in d["rows"]:
        here = f"`us/ca/{r['modeled_as']}`" if r["modeled_as"] else (
            "not a tariff" if r["kind"] == "not-a-tariff" else "**not modeled**")
        o.append(f"| `{r['segment']}` | {r['distribution']} | {r['supplier']} | "
                 f"{r['identifiers']:,} | {r['documents']} | {here} |")
    o += ["", "## Documents worth reading first", "",
          "One tariff document backs many identifiers, so the cheapest coverage is the "
          "document that backs the most. A landing page is listed as such: it is a place to "
          "look, not a thing to model.", "",
          "| Identifiers | Kind | Segments | Link |", "|---:|---|---|---|"]
    for c in d["catalog"][:40]:
        if c["modeled"]:
            continue
        o.append(f"| {c['identifiers']:,} | {'document' if c['is_document'] else 'landing page'} | "
                 f"{', '.join('`'+s+'`' for s in c['segments'][:4])} | <{c['url']}> |")
    return "\n".join(o) + "\n"


def render_edn(d) -> str:
    def edn(x):
        if x is None: return "nil"
        if isinstance(x, bool): return "true" if x else "false"
        if isinstance(x, int): return str(x)
        if isinstance(x, str): return json.dumps(x)
        if isinstance(x, list): return "[" + " ".join(edn(i) for i in x) + "]"
        if isinstance(x, dict):
            return "{" + " ".join(f":{k.replace('_','-')} {edn(v)}" for k, v in x.items()) + "}"
        return json.dumps(str(x))
    return (";; Auto-generated by dev/list_midas_catalog.py. Do not edit by hand.\n"
            ";; A third party's catalog. Asserts nothing about this corpus's filings.\n\n"
            + edn(d) + "\n")


def main() -> int:
    d = build()
    (REPO / "reports" / "midas-catalog.md").write_text(render_md(d))
    (REPO / "reports" / "midas-catalog.edn").write_text(render_edn(d))
    unmod = [r for r in d["rows"] if r["kind"] == "unmodeled"]
    docs = [c for c in d["catalog"] if c["is_document"]]
    pages = [c for c in d["catalog"] if not c["is_document"]]
    nolink = sum(r["identifiers"] for r in unmod if r["documents"] == 0)
    print(f"wrote reports/midas-catalog.{{md,edn}}: {d['records']:,} identifiers"
          f"{'' if d['complete'] else ' (PARTIAL)'}, {len(d['rows'])} segments, "
          f"{len(unmod)} unmodeled")
    print(f"  documents {len(docs)}, landing pages {len(pages)}, "
          f"{nolink:,} identifiers on unmodeled parties with no link at all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
