#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Add the PG&E versions effective 2026-06-01 and 2026-08-28.

Two advice letters moved the modeled residential schedules after the newest
versions this corpus held:

  7921-E  2026-06-01  D.26-04-036: Sheet 1 of E-1 and Sheet 2 of E-TOU-C,
                      E-TOU-D, EV2 and E-ELEC reissued with the California
                      Climate Credit, ($36.18) per household, restored and moved
                      to the August and September bill cycles. No other value on
                      those sheets moved.
  7975-E  2026-08-28  Clean-up: E-ELEC Sheet 1 (an NBT customer moved to the
                      PURPA Compliant tariff over a contractor's prevailing wage
                      violation may stay on E-ELEC without a qualifying
                      technology) and NBT Sheets 1, 5, 12, 24, 32 and 37.

Each new version is derived from the newest held one. Subordinate @ids the
version owns are re-dated or scoped to it (LAYOUT.md section 6); nodes owned by
an inlined modifier version (the vintage PCIA) are kept, and that modifier
version names the new base version in urpx:applicableToRatePlanVersion, because
no vintage PCIA sheet was reissued. Every modeled price is reconciled to the
sheets in force on its date (components to the published totals) before
anything is written. Each predecessor ends at the effective date of the sheet
that cancels it.

The second documents in the E-1 and E-TOU-C directories follow: the E-1
income-tier modifier gains a 2026-06-01 version here, and the Medical Baseline
modifiers are written by dev/author_pge_medical_baseline.py, which is run
after this script. D-CARE and E-FERA name the new base versions' subtotals and
exempted Prices.

Run from the repo root with the fetched documents directory, then the ladder,
Medical Baseline and coverage-evaluation generators:
    python3 dev/author_pge_2026.py <dir holding the ELEC_SCHEDS_*.pdf fetched 2026-10-07>
    python3 dev/author_pge_e_tou_c_baseline.py
    python3 dev/author_pge_medical_baseline.py
    python3 dev/resync_coverage_evaluations.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import rescope_iris as rescope  # noqa: E402

PGE = REPO / "us/ca/pge/electricity"
JUN, AUG = "2026-06-01", "2026-08-28"
TODAY = "2026-10-07"
BOOK = "https://www.pge.com/tariffs/assets/pdf/tariffbook/"

# (schedule, source version, new version, file name in the fetched directory)
STEPS = [
    ("e-1", "2026-03-01", JUN, "ELEC_SCHEDS_E-1.pdf"),
    ("e-tou-c", "2026-03-27", JUN, "ELEC_SCHEDS_E-TOU-C.pdf"),
    ("e-tou-d", "2026-03-27", JUN, "ELEC_SCHEDS_E-TOU-D.pdf"),
    ("ev2", "2026-03-27", JUN, "ELEC_SCHEDS_EV2__Sch_.pdf"),
    ("e-elec", "2026-03-27", JUN, "ELEC_SCHEDS_E-ELEC.pdf"),
    ("e-elec", JUN, AUG, "ELEC_SCHEDS_E-ELEC.pdf"),
    ("nbt", "2025-10-17", AUG, "ELEC_SCHEDS_NBT.pdf"),
]
BASES = ["e-1", "e-elec", "e-tou-c", "e-tou-d", "ev2"]
URL = {"e-1": "ELEC_SCHEDS_E-1.pdf", "e-tou-c": "ELEC_SCHEDS_E-TOU-C.pdf",
       "e-tou-d": "ELEC_SCHEDS_E-TOU-D.pdf", "ev2": "ELEC_SCHEDS_EV2 (Sch).pdf",
       "e-elec": "ELEC_SCHEDS_E-ELEC.pdf", "nbt": "ELEC_SCHEDS_NBT.pdf"}
NAME = {"e-1": "E-1", "e-tou-c": "E-TOU-C", "e-tou-d": "E-TOU-D", "ev2": "EV2", "e-elec": "E-ELEC",
        "nbt": "NBT"}
# Bytes first seen: data/documents.json records every one of these on 2026-09-23
# except E-1, which PG&E reassembled on 2026-09-28 (same text, new bytes).
RETRIEVED = {"e-1": TODAY}

# The rate sheet each version's predecessor is ended by: (sheet, leaf, cancels).
CANCEL = {
    ("e-1", JUN): (1, "61362-E", "61247-E"),
    ("e-tou-c", JUN): (2, "61364-E", "61249-E"),
    ("e-tou-d", JUN): (2, "61365-E", "61250-E"),
    ("ev2", JUN): (2, "61374-E", "61256-E"),
    ("e-elec", JUN): (2, "61363-E", "61248-E"),
    ("e-elec", AUG): (1, "61545-E", "61116-E"),
    ("nbt", AUG): (1, "61546-E", "60433-E"),
}

AL = {
    JUN: {"@type": "urpx:SourcePublication", "@id": "pge:al-7921-e",
          "urpx:name": "PG&E Advice Letter 7921-E", "urpx:filingNumber": "7921-E",
          "urpx:issuingAuthority": "California Public Utilities Commission",
          "urpx:publicationType": {"@id": "urpx:tariffSupplement"},
          "urpx:description": ("PG&E Advice Letter 7921-E under CPUC Decision D.26-04-036, reissuing Sheet 1 of "
                               "Schedule E-1 and Sheet 2 of Schedules E-TOU-C, E-TOU-D, EV2 and E-ELEC effective "
                               "2026-06-01 to state the California Climate Credit as a semi-annual payment in the "
                               "August and September bill cycles."),
          "urpx:effectiveDate": "2026-06-01", "urpx:dateReceived": "2026-06-01"},
    AUG: {"@type": "urpx:SourcePublication", "@id": "pge:al-7975-e",
          "urpx:name": "PG&E Advice Letter 7975-E", "urpx:filingNumber": "7975-E",
          "urpx:issuingAuthority": "California Public Utilities Commission",
          "urpx:publicationType": {"@id": "urpx:tariffSupplement"},
          "urpx:description": ("PG&E Advice Letter 7975-E, Clean-Up of Electric Tariffs, a Tier 1 submittal "
                               "effective on submittal, 2026-08-28, pending final disposition. It reissues Sheet 1 "
                               "of Schedule E-ELEC and Sheets 1, 5, 12, 24, 32 and 37 of Schedule NBT; it states "
                               "that it increases no rate or charge."),
          "urpx:effectiveDate": "2026-08-28", "urpx:dateReceived": "2026-08-28"},
}
RC_JUN = {"@type": "urpx:RateCase", "@id": "pge:rc-d-26-04-036", "urpx:caseNumber": "D.26-04-036",
          "urpx:name": "CPUC Decision D.26-04-036",
          "urpx:description": ("Decision Ordering Immediate Improvements to the California Climate Credit, "
                               "Rulemaking 25-07-013, adopted April 30, 2026. The url is the proposed decision the "
                               "CPUC's announcement of the vote links as the proposal approved."),
          "urpx:url": "https://docs.cpuc.ca.gov/PublishedDocs/Published/G000/M605/K823/605823091.PDF"}
# The D.26-03-013 url the corpus carried answers 404; this is the issued decision.
RC_MAR_URL = "https://docs.cpuc.ca.gov/PublishedDocs/Published/G000/M603/K306/603306591.PDF"

CLIMATE_CREDIT = "-36.18"
CC_MONTHS = ["--08", "--09"]

# Published totals on the sheets in force on 2026-06-01, $ per kWh; checked
# against the sheet text and against the sum of the modeled components.
PUBLISHED = {
    "e-tou-c": {"summer-peak": "0.52240", "summer-off-peak": "0.39940",
                "winter-peak": "0.39757", "winter-off-peak": "0.36757", "baseline-credit": "0.08140"},
    "e-tou-d": {"summer-peak": "0.47708", "summer-off-peak": "0.34212",
                "winter-peak": "0.38747", "winter-off-peak": "0.34886"},
    "ev2": {"summer-peak": "0.53809", "summer-part-peak": "0.42760", "summer-off-peak": "0.22558",
            "winter-peak": "0.41099", "winter-part-peak": "0.39428", "winter-off-peak": "0.22558"},
    "e-elec": {"summer-peak": "0.55214", "summer-part-peak": "0.39026", "summer-off-peak": "0.33358",
               "winter-peak": "0.32063", "winter-part-peak": "0.29854", "winter-off-peak": "0.28468"},
    "e-1": {"t1": "0.32561", "t2": "0.40702", "t2c": "0.40702"},
}
BSC = ["0.19713", "0.39688", "0.79343"]
COMMON = ["price-" + k for k in (
    "transmission", "transmission-adj", "reliability", "public-purpose", "nuclear", "ctc",
    "energy-cost-recovery", "wildfire-fund", "wildfire-hardening", "recovery-bond",
    "recovery-bond-credit", "bundled-pcia", "pcia", "new-sys-gen")]


# --- io ----------------------------------------------------------------------

def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def dump(p: Path, doc) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def walk(o, f):
    if isinstance(o, dict):
        f(o)
        for k, v in o.items():
            if k != "@context":
                walk(v, f)
    elif isinstance(o, list):
        for v in o:
            walk(v, f)


def find(o, i):
    hit = []
    walk(o, lambda d: hit.append(d) if d.get("@id") == i and len(d) > 1 else None)
    return hit[0] if hit else None


def is_base(slug: str) -> bool:
    return slug in BASES


def doc_path(slug: str, date: str, stem: str | None = None) -> Path:
    stem = stem or slug
    kind = "rate-plan" if stem in BASES else "rate-plan-modifier"
    return PGE / slug / "versions" / date / f"{kind}_pge_{stem}_{date}.jsonld"


def package(doc):
    return doc["@graph"][0] if "@graph" in doc else doc


def version_node(doc):
    p = package(doc)
    if "urpx:hasRatePlan" in p:
        return p["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]
    return p["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --- sheets ------------------------------------------------------------------

def pdftext(p: Path) -> list[str]:
    t = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True, check=True).stdout
    return [x for x in t.split("\f") if x.strip()]


MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July",
                                      "August", "September", "October", "November", "December"], 1)}


def sheets(p: Path) -> list[dict]:
    out = []
    for n, page in enumerate(pdftext(p), 1):
        leaf = re.search(r"(?:Original|Revised)\s+Cal\. P\.U\.C\. Sheet No\.\s+(\d+-E)", page)
        canc = re.search(r"Cancelling\s+(?:Original|Revised)?\s*Cal\. P\.U\.C\. Sheet No\.\s+(\d+-E)", page)
        al = re.search(r"Advice\s+(\d+-E(?:-[A-Z])?)", page)
        eff = re.search(r"Effective\s+([A-Z][a-z]+) (\d+), (\d{4})", page)
        num = re.search(r"Sheet (\d+)\s*$", page, re.M)
        out.append({"page": n, "leaf": leaf.group(1), "cancels": canc.group(1) if canc else None,
                    "al": al.group(1), "sheet": int(num.group(1)) if num else n,
                    "eff": f"{eff.group(3)}-{MONTHS[eff.group(1)]:02d}-{int(eff.group(2)):02d}", "text": page})
    return out


# --- reconciliation ------------------------------------------------------------

def money(v: str) -> str:
    d = Decimal(v)
    return f"(${abs(d)})" if d < 0 else f"${d}"


def modeled(doc) -> dict[str, str]:
    """Base-version Prices by descriptor (the @id after the version stem)."""
    v = version_node(doc)
    vid = v["@id"]
    out = {}

    def f(d):
        if d.get("@type") == "urpx:Price" and "urpx:unitPrice" in d:
            local = d["@id"].split(":", 1)[1]
            key = local[len(vid.split(":", 1)[1]) + 1:] if local.startswith(vid.split(":", 1)[1] + "-") else local
            out[key] = d["urpx:unitPrice"]
    walk(v["urpx:hasPrices"], f)
    return out


def reconcile(slug: str, date: str, doc, sh: list[dict]) -> list[str]:
    errs = []
    text = "\n".join(s["text"] for s in sh)
    p = modeled(doc)
    pub = PUBLISHED[slug]
    for k, val in pub.items():
        if f"${val}" not in text and f"(${val})" not in text:
            errs.append(f"{slug} {date}: published {k} {val} not on the sheets")
    for v in BSC:
        if f"${v}" not in text:
            errs.append(f"{slug} {date}: Base Services Charge {v} not on the sheets")
    if "($36.18)" not in text or "August and" not in text:
        errs.append(f"{slug} {date}: Climate Credit ($36.18), August and September, not on the sheets")
    common = sum(Decimal(p[k]) for k in COMMON if k in p)
    if slug == "e-1":
        base = Decimal(p["price-generation"]) + Decimal(p["price-distribution"]) + common
        for season in ("summer", "winter"):
            for t in ("t1", "t2", "t2c"):
                got = base + Decimal(p[f"price-cia-{season}-{t}"])
                if got != Decimal(pub[t]):
                    errs.append(f"e-1 {date} {season} {t}: components {got} != published {pub[t]}")
    else:
        for cell, total in pub.items():
            if cell == "baseline-credit":
                continue
            got = Decimal(p[f"price-gen-{cell}"]) + Decimal(p[f"price-dist-{cell}"]) + common
            if slug == "e-tou-c":
                got += Decimal(p["price-cia-t2"])
                t1 = got - Decimal(p["price-cia-t2"]) + Decimal(p["price-cia-t1"])
                if t1 != Decimal(total) - Decimal(pub["baseline-credit"]):
                    errs.append(f"e-tou-c {date} {cell}: baseline usage {t1} != {total} - {pub['baseline-credit']}")
            if got != Decimal(total):
                errs.append(f"{slug} {date} {cell}: components {got} != published {total}")
    for k, val in p.items():
        if k.startswith("price-base-charge") or k == "price-climate-credit":
            continue
        if Decimal(val) == 0:
            if "$0.00000" not in text:
                errs.append(f"{slug} {date}: {k} 0.00000 not on the sheets")
        elif money(val) not in text:
            errs.append(f"{slug} {date}: {k} {val} not printed on the sheets")
    if p.get("price-climate-credit") != CLIMATE_CREDIT:
        errs.append(f"{slug} {date}: climate credit is {p.get('price-climate-credit')}")
    return errs


def ladder_check(cache: dict[str, list[dict]]) -> list[str]:
    """The baseline quantities in force on 2026-06-01 (E-TOU-C Special Condition 1,
    Sheet 5 61128-E; E-1 Special Condition 2, Sheet 4 61099-E) equal the table the
    E-TOU-C ladder is built from, and the E-1 ladder's brackets carry them."""
    import author_pge_e_tou_c_baseline as etouc  # noqa: E402
    errs = []
    for f, leaf in (("ELEC_SCHEDS_E-TOU-C.pdf", "61128-E"), ("ELEC_SCHEDS_E-1.pdf", "61099-E")):
        text = re.sub(r"\((?:R|I|T|L)\)|\|", " ", next(s for s in cache[f] if s["leaf"] == leaf)["text"])
        for t, q in etouc.QUANTITY.items():
            row = re.search(rf"^\s*{t}\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$", text, re.M)
            if not row or row.groups() != q:
                errs.append(f"{f} {leaf} territory {t}: sheet {row and row.groups()} != ladder {q}")
    e1 = load(doc_path("e-1", "2026-03-01"))
    bounds = set()
    walk(e1, lambda d: bounds.add(d["urpx:upperBound"]) if d.get("@type") == "urpx:ServiceBracket"
         and d.get("urpx:upperBound") and "t1" in d.get("@id", "") else None)
    want = {x for q in etouc.QUANTITY.values() for x in q}
    if {str(Decimal(b)) for b in bounds} != {str(Decimal(w)) for w in want}:
        errs.append(f"E-1 Tier 1 upper bounds {sorted(bounds)} != Special Condition 2 {sorted(want)}")
    return errs


# --- derivation ----------------------------------------------------------------

def rename_map(doc, slug_stem: str, src: str, date: str) -> dict[str, str]:
    """@ids the version (and its package) own: re-dated where they carry the
    version stem, else scoped to the new version. Nodes owned by another
    version (an inlined modifier) are kept."""
    old_vid = version_node(doc)["@id"]
    new_vid = old_vid.replace(src, date)
    m: dict[str, str] = {}

    def f(d, own):
        i = d.get("@id")
        if not isinstance(i, str) or len(d) <= 1 or i in m:
            return
        if own not in (None, old_vid):
            return
        t = rescope.node_type(d)
        stem = f"{slug_stem}-{src}"
        if stem in i:
            m[i] = i.replace(stem, f"{slug_stem}-{date}")
        elif t in rescope.IDENTITY_TYPES or t in rescope.KEEP_SHARED_TYPES or i.startswith("org:") \
                or t == "urpx:URPXPackage":
            return
        else:
            m[i] = rescope.new_iri(i, new_vid)
    rescope.walk_owned(doc, f)
    if len(set(m.values())) != len(m):
        raise SystemExit(f"{slug_stem} {date}: rename collides")
    return m


CURIE = re.compile(r"pge:[A-Za-z0-9_.-]*[A-Za-z0-9]")


def apply_map(doc, m: dict[str, str]) -> None:
    def f(d):
        for k, v in list(d.items()):
            if k == "@id" and isinstance(v, str) and v in m:
                d[k] = m[v]
            elif isinstance(v, str) and k != "@id" and "pge:" in v:
                d[k] = CURIE.sub(lambda x: m.get(x.group(0), x.group(0)), v)
    walk(doc, f)


def set_literals(v: dict, src: str, date: str) -> None:
    def f(d):
        for k, x in list(d.items()):
            if not isinstance(x, str):
                continue
            if k in ("urpx:version", "urpx:modifierVersionNumber") and x == src:
                d[k] = date
            elif k == "urpx:effectiveDateTime" and x.startswith(src):
                d[k] = f"{date}T00:00:00"
            elif k == "urpx:startDate" and x == src:
                d[k] = date
            elif k == "urpx:evaluatedOn":
                d[k] = f"{TODAY}T00:00:00"
    walk(v, f)
    v.pop("urpx:expirationDateTime", None)


def set_source(v: dict, slug: str, date: str, sh: list[dict], retrieved: str, pub: str | None,
               pages=None) -> None:
    dsr = v["urpx:hasDataSourceReference"]
    use = [s for s in sh if pages is None or s["page"] in pages]
    leaves = sorted(s["leaf"] for s in use)
    dsr.update({"urpx:fileName": URL[slug], "urpx:accessURL": BOOK + URL[slug].replace(" ", "%20"),
                "urpx:dateRetrieved": retrieved,
                "urpx:pageStart": min(s["page"] for s in use), "urpx:pageEnd": max(s["page"] for s in use),
                "urpx:leafStart": leaves[0], "urpx:leafEnd": leaves[-1]})
    if pub:
        dsr["urpx:sourcePublication"] = {"@id": pub}


def add_climate_credit(doc, v: dict, vid: str, date: str) -> None:
    pe = v["urpx:hasPlanElements"]
    mis = pe["urpx:hasMetricInput"]
    if not any(x["@id"] == f"{vid}-mi-household-count" for x in mis):
        mis.append({"@type": "urpx:MetricInput", "@id": f"{vid}-mi-household-count",
                    "urpx:name": "Per Household Prices",
                    "urpx:metricInputType": {"@id": "urpx:profileMetricInput"},
                    "urpx:profileMetricProperty": {"@id": "urpx:householdCount"}})
    bm = pe["urpx:hasBillingModel"]
    if not any(x["@id"] == f"{vid}-ledger-climate-credit" for x in bm["urpx:hasLedger"]):
        bm["urpx:hasLedger"].append({"@type": "urpx:Ledger", "@id": f"{vid}-ledger-climate-credit",
                                     "urpx:name": "California Climate Credit",
                                     "urpx:ledgerType": {"@id": "urpx:bundledLedger"},
                                     "urpx:referencesMetricInput": {"@id": f"{vid}-mi-household-count"}})
    pds = bm["urpx:hasPriceDefinition"]
    pds[:] = [x for x in pds if x["@id"] != f"{vid}-pd-climate-credit"]
    pds.append({"@type": "urpx:PriceDefinition", "@id": f"{vid}-pd-climate-credit",
                "urpx:name": "California Climate Credit",
                "urpx:chargeType": {"@id": "urpx:creditEnergy"},
                "urpx:chargeCategory": {"@id": "urpx:environmental"},
                "urpx:billPortion": {"@id": "urpx:bundledPortion"},
                "urpx:baseQuantity": "1",
                "urpx:hasApplicabilityRule": {"@type": "urpx:ApplicabilityRule", "urpx:month": CC_MONTHS},
                "urpx:referencesLedger": {"@id": f"{vid}-ledger-climate-credit"}})
    prices = v["urpx:hasPrices"]
    keep = [x for x in prices.get("urpx:hasPrice", []) if x["@id"] != f"{vid}-price-climate-credit"]
    prices["urpx:hasPrice"] = [{"@type": "urpx:Price", "@id": f"{vid}-price-climate-credit",
                                "urpx:referencesPriceDefinition": {"@id": f"{vid}-pd-climate-credit"},
                                "urpx:startDate": date, "urpx:name": "California Climate Credit",
                                "urpx:unitPrice": CLIMATE_CREDIT}] + keep


CC_SENTENCE = ("The California Climate Credit, ($36.18) per household as a semi-annual payment in the August and "
               "September bill cycles, is {where}, priced in calendar months --08 and --09 on a "
               "urpx:householdCount MetricInput.")


def graph_nodes(doc, nodes: list[dict]) -> None:
    g = doc["@graph"]
    ids = {n.get("@id") for n in g}
    for n in nodes:
        if n["@id"] in ids:
            g[[x.get("@id") for x in g].index(n["@id"])] = copy.deepcopy(n)
        else:
            g.append(copy.deepcopy(n))


def drop_unreferenced_publications(doc) -> None:
    refs = set()
    walk(package(doc), lambda d: refs.add(d["@id"]) if len(d) == 1 and "@id" in d else None)
    doc["@graph"] = [n for i, n in enumerate(doc["@graph"])
                     if i == 0 or n.get("@type") not in ("urpx:SourcePublication", "urpx:RateCase")
                     or n["@id"] in refs]


# Version descriptions: (old fragment, new fragment), each required to match once.
DESCRIPTION = {
    ("e-1", JUN): [("", None)],
    ("e-tou-c", JUN): [(" Compared to the 2026-03-01 version: California Climate Credit removed (Sheet 2 reissued "
                        "under AL 7869-E / D.26-03-013, sheet 61249-E).",
                        " Compared to the 2026-03-27 version: Sheet 2 (61364-E) is reissued under AL 7921-E / "
                        "D.26-04-036 with the California Climate Credit restored, in the August and September bill "
                        "cycles; no other price moved.")],
    ("e-tou-d", JUN): [],
    ("ev2", JUN): [("No baseline credit, no Conservation Incentive Adjustment, no climate credit.",
                    "No baseline credit and no Conservation Incentive Adjustment.")],
    ("e-elec", JUN): [("Reissued under PG&E Advice Letter 7869-E (CPUC Decision D.26-03-013) effective 2026-03-27. "
                       "Substantive change from the 2026-01-01 version: income-tiered base services charge "
                       "introduced (CARE/FERA/Tier-3 with same values as E-TOU-C / E-TOU-D / EV2 / E-1); California "
                       "Climate Credit removed; minor energy-rate updates per Sheet 2 + Sheet 3.",
                       "Sheet 2 (61363-E) reissued under PG&E Advice Letter 7921-E (CPUC Decision D.26-04-036) "
                       "effective 2026-06-01, restoring the California Climate Credit in the August and September "
                       "bill cycles; no other price moved from the 2026-03-27 version. Base Services Charge by "
                       "income tier: $0.19713 (Tier 1, CARE), $0.39688 (Tier 2, FERA), $0.79343 (Tier 3).")],
    ("e-elec", AUG): [("Sheet 2 (61363-E) reissued under PG&E Advice Letter 7921-E (CPUC Decision D.26-04-036) "
                       "effective 2026-06-01, restoring the California Climate Credit in the August and September "
                       "bill cycles; no other price moved from the 2026-03-27 version.",
                       "Sheet 1 (61545-E) reissued under PG&E Advice Letter 7975-E effective 2026-08-28: a "
                       "residential customer billed on the Net Billing Tariff who is transitioned to the PURPA "
                       "Compliant tariff over a contractor's willful prevailing wage violation may stay on this "
                       "schedule without a qualifying technology. Prices are those of Sheet 2 (61363-E, Advice "
                       "7921-E, effective 2026-06-01), unchanged from the 2026-06-01 version.")],
}

PURPA_LEAF_NAME = "PURPA Compliant tariff, transitioned from NBT under Special Condition 10"


def eelec_purpa(v: dict, vid: str) -> None:
    er = next(r for r in v["urpx:hasEligibilityRule"] if r["@id"].endswith("-er-qualifying-technology"))
    er["urpx:name"] = ("Qualifying electric technology: storage, EV, heat pump, NBT enrollment, or a former NBT "
                       "customer moved to the PURPA Compliant tariff")
    er["urpx:description"] = er["urpx:description"].replace(
        "the NBT condition is therefore included as a fourth OR-leaf.",
        "the NBT condition is therefore included as a fourth OR-leaf. Sheet 1 (61545-E): \"If a NBT residential "
        "customer is transitioned to the PURPA Compliant tariff due to a willful prevailing wage violation by "
        "their contractor, that customer may continue to be served under this rate schedule without the "
        "technology requirements.\" That is a fifth OR-leaf, enrollment in the PURPA Compliant tariff, which "
        "names the prevailing wage transition in its value.")
    root = er["urpx:hasConditionExpression"]["urpx:rootNode"]
    leaves = root["urpx:operandNodes"]
    n = f"{vid}-cn-purpa"
    if not any(x["@id"] == n for x in leaves):
        leaves.append({"@type": "urpx:ComparisonNode", "@id": n,
                       "urpx:operator": {"@id": "urpx:equalsOperator"},
                       "urpx:leftOperand": {"@type": "urpx:CustomOperandNode", "@id": f"{n}-left-operand",
                                            "urpx:customConditionProperty": "Program Enrollment"},
                       "urpx:rightOperand": {"@type": "urpx:CustomOperandNode", "@id": f"{n}-right-operand",
                                             "urpx:stringValue": ("PURPA Compliant tariff (transitioned from NBT "
                                                                  "over a contractor's willful prevailing wage "
                                                                  "violation)")}})


def extend_pcia(doc, base_vid: str) -> list[str]:
    """The inlined vintage PCIA version names base_vid; returns its @id."""
    p = package(doc)
    out = []
    mod = p.get("urpx:hasRatePlanModifier")
    if not mod or not mod["@id"].endswith("-vintage-pcia"):
        return out
    mv = mod["urpx:hasRatePlanModifierVersion"]
    appv = mv["urpx:applicableToRatePlanVersion"]
    appv = appv if isinstance(appv, list) else [appv]
    if base_vid not in [x["@id"] for x in appv]:
        appv.append({"@id": base_vid})
    mv["urpx:applicableToRatePlanVersion"] = sorted(appv, key=lambda x: x["@id"])
    out.append(mv["@id"])
    return out


def sync_pcia(slug: str) -> None:
    """Every copy of a vintage PCIA version node is the same node."""
    copies = {}
    for p in sorted((PGE / slug / "versions").glob(f"*/rate-plan_pge_{slug}_*.jsonld")):
        d = load(p)
        mod = package(d).get("urpx:hasRatePlanModifier")
        if mod and mod["@id"].endswith("-vintage-pcia"):
            mv = mod["urpx:hasRatePlanModifierVersion"]
            copies.setdefault(mv["@id"], set()).update(x["@id"] for x in (
                mv["urpx:applicableToRatePlanVersion"] if isinstance(mv["urpx:applicableToRatePlanVersion"], list)
                else [mv["urpx:applicableToRatePlanVersion"]]))
    for p in sorted((PGE / slug / "versions").glob(f"*/rate-plan_pge_{slug}_*.jsonld")):
        d = load(p)
        mod = package(d).get("urpx:hasRatePlanModifier")
        if mod and mod["@id"].endswith("-vintage-pcia"):
            mv = mod["urpx:hasRatePlanModifierVersion"]
            mv["urpx:applicableToRatePlanVersion"] = [{"@id": i} for i in sorted(copies[mv["@id"]])]
            dump(p, d)


def derive(slug: str, src: str, date: str, sh: list[dict], stem: str | None = None):
    stem = stem or slug
    doc = load(doc_path(slug, src, stem))
    m = rename_map(doc, stem, src, date)
    apply_map(doc, m)
    v = version_node(doc)
    set_literals(v, src, date)
    vid = v["@id"]
    if "@graph" in doc:
        package(doc)["@id"] = package(doc)["@id"].replace(src, date)
    else:
        doc["@id"] = doc["@id"].replace(src, date)
    return doc, v, vid, m


def base_version(slug, src, date, sh, retrieved):
    doc, v, vid, m = derive(slug, src, date, sh)
    pub = AL[date]["@id"]
    set_source(v, slug, date, sh, retrieved, pub)
    if date == JUN:
        v["urpx:changeReason"] = {"@id": "urpx:regulatoryOrder"}
        v["urpx:hasRateCase"] = {"@id": "pge:rc-d-26-04-036"}
        add_climate_credit(doc, v, vid, date)
        graph_nodes(doc, [AL[JUN], RC_JUN])
    else:
        v["urpx:changeReason"] = {"@id": "urpx:correction"}
        graph_nodes(doc, [AL[JUN], AL[AUG], RC_JUN])
        if slug == "e-elec":
            eelec_purpa(v, vid)
    d = v["urpx:description"]
    for old, new in DESCRIPTION.get((slug, date), []):
        if new is None:
            continue
        if d.count(old) != 1:
            raise SystemExit(f"{slug} {date}: description fragment not found once: {old[:60]}")
        d = d.replace(old, new)
    where = "in this version" if slug != "e-elec" or date == JUN else "in this version, as in the 2026-06-01 one"
    sentence = CC_SENTENCE.format(where=where)
    if sentence not in d and CC_SENTENCE.format(where="in this version") not in d:
        d = d.rstrip() + " " + sentence
    elif date == AUG:
        d = d.replace(CC_SENTENCE.format(where="in this version"), sentence)
    v["urpx:description"] = d.replace(f"_{src}.jsonld", f"_{date}.jsonld")
    extend_pcia(doc, vid)
    if slug == "e-1":  # the income-tier modifier gains a version of its own (income_tier below)
        v["urpx:hasModifierVersionOptions"] = [
            {"@id": x["@id"].replace(f"pge:e-1-income-tier-{src}", f"pge:e-1-income-tier-{date}")}
            for x in v["urpx:hasModifierVersionOptions"]]
    drop_unreferenced_publications(doc)
    return doc, m


def income_tier(sh, src: str = "2026-03-01", date: str = JUN):
    doc, v, vid, m = derive("e-1", src, date, sh, stem="e-1-income-tier")
    v["urpx:applicableToRatePlanVersion"] = [{"@id": f"pge:e-1-{date}"}]
    set_source(v, "e-1", date, sh, RETRIEVED["e-1"], AL[JUN]["@id"], pages={1})
    v["urpx:changeReason"] = {"@id": "urpx:regulatoryOrder"}
    v["urpx:description"] = v["urpx:description"].replace("(Cal. P.U.C. Sheet 61247-E)",
                                                          "(Cal. P.U.C. Sheet 61362-E)")
    if "61362-E" not in v["urpx:description"]:
        raise SystemExit("income tier description: sheet citation not rewritten")
    return doc, m


def nbt_version(sh, src="2025-10-17", date=AUG):
    doc, v, vid, m = derive("nbt", src, date, sh)
    set_source(v, "nbt", date, sh, "2026-09-23", None)
    v["urpx:changeReason"] = {"@id": "urpx:correction"}
    text = "\n".join(x["text"] for x in sh)
    for seg, val in (("residential", "-0.01320"), ("low-income", "-0.05400")):
        got = find(doc, f"{vid}-price-acc-plus-{seg}-vintage-{2025}")["urpx:unitPrice"]
        if got != val or val[1:] not in text:
            raise SystemExit(f"nbt {date}: ACC Plus {seg} {got} against Sheet 11 {val}")
    ev = v["urpx:hasCoverageClaim"]["urpx:explainedBy"]
    old = "the four exclusions Sheet 11 attaches to the adder"
    if old not in ev["urpx:description"]:
        raise SystemExit("nbt evaluation: exclusions sentence not found")
    ev["urpx:description"] = ev["urpx:description"].replace(old, "the four exclusions Sheets 11 and 12 attach to "
                                                                 "the adder")
    return doc, m


# --- expirations, candidates ---------------------------------------------------

def expire(path: Path, until: str) -> None:
    doc = load(path)
    ctx = doc["@context"]
    if "urpx:expirationDateTime" not in ctx:
        out = {}
        for k, x in ctx.items():
            out[k] = x
            if k == "urpx:effectiveDateTime":
                out["urpx:expirationDateTime"] = {"@type": "xsd:dateTime"}
        out.setdefault("urpx:expirationDateTime", {"@type": "xsd:dateTime"})
        doc["@context"] = out
    v = version_node(doc)
    new_v = {}
    for k, x in v.items():
        if k == "urpx:expirationDateTime":
            continue
        new_v[k] = x
        if k == "urpx:effectiveDateTime":
            new_v["urpx:expirationDateTime"] = f"{until}T00:00:00"
    p = package(doc)
    if "urpx:hasRatePlan" in p:
        p["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"] = new_v
    else:
        p["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"] = new_v
    dump(path, doc)


CANDIDATES = {  # modifier: descriptors of the base Prices or subtotals its Prices name
    "d-care": ["summary-care-discountable", "price-wildfire-fund", "price-wildfire-hardening",
               "price-recovery-bond", "price-recovery-bond-credit"],
    "e-fera": ["summary-fera-discountable", "price-wildfire-hardening", "price-recovery-bond",
               "price-recovery-bond-credit"],
}


def candidates(new_bases: list[str]) -> None:
    for mod, date in (("d-care", "2026-03-01"), ("e-fera", JUN)):
        p = doc_path(mod, date)
        doc = load(p)
        touched = set()

        def f(d):
            if d.get("@type") != "urpx:Price" or "urpx:basedOnPrice" not in d:
                return
            ids = [x["@id"] for x in d["urpx:basedOnPrice"]]
            for desc in CANDIDATES[mod]:
                if all(i.endswith("-" + desc) for i in ids):
                    for b in new_bases:
                        i = f"{b}-{desc}"
                        if i not in ids:
                            ids.append(i)
                    d["urpx:basedOnPrice"] = [{"@id": i} for i in sorted(ids)]
                    touched.add(desc)
        walk(doc, f)
        if touched != set(CANDIDATES[mod]):
            raise SystemExit(f"{mod}: candidate Prices found {sorted(touched)}")
        dump(p, doc)


# --- manifests -----------------------------------------------------------------

def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def wrap(text: str) -> str:
    import textwrap
    return "\n".join(textwrap.wrap(" ".join(text.split()), 78, break_long_words=False, break_on_hyphens=False))


def sheet_lines(sh: list[dict]) -> str:
    return "\n".join(f" Sheet {s['sheet']}: {s['leaf']}, Advice {s['al']}, effective {s['eff']}" for s in sh)


CHANGE = {
    JUN: ("Advice 7921-E (Decision D.26-04-036), effective 2026-06-01, reissues Sheet {n} ({leaf}, cancelling "
          "{canc}) to state the California Climate Credit, ($36.18) per household, as a semi-annual payment in "
          "the August and September bill cycles. The {src} version carries no Climate Credit, because Advice "
          "7869-E paused it from 2026-03-27. No other value on that sheet changed, "
          "and every other sheet is the one the {src} version's document carries."),
    AUG: ("Advice 7975-E (Clean-Up of Electric Tariffs, Tier 1, effective on submittal 2026-08-28, pending final "
          "disposition) reissues Sheet {n} ({leaf}, cancelling {canc}).{what} It states that it increases no rate "
          "or charge."),
}
WHAT = {
    "e-elec": (" The Sheet 1 change adds: 'If a NBT residential customer is transitioned to the PURPA Compliant "
               "tariff due to a willful prevailing wage violation by their contractor, that customer may continue "
               "to be served under this rate schedule without the technology requirements', and names Schedule "
               "S/SB where Schedule S stood. The eligibility rule gains that fifth OR-leaf; no price moved from "
               "the 2026-06-01 version."),
    "nbt": (" It also reissues Sheets 5, 12, 24, 32 and 37 and folds in Advices 7155-E and 7155-E-A, approved "
            "2026-08-24 effective 2024-07-01, which revised Sheets 4, 10, 11 and 33 (now 59899-E, 59900-E, "
            "57255-E and 59902-E): Sheet 5 footnote 3 on verifying a disadvantaged-community resident-owner, Sheet 10 "
            "splitting export rates into generation and delivery components with unbundled customers receiving "
            "only the delivery components from PG&E, Sheet 24 on sizing a facility against 1 MW, Sheet 32 on "
            "a new 9-year legacy period after a modification moves a NEM or NEM2 system to NBT, and Sheet 37's "
            "interconnection forms. No value this filing models moved: the ACC Plus table on Sheet 11 prints "
            "the same ten figures, and the Export Compensation Rate cells come from PG&E's published price "
            "sheets, which no sheet here restates."),
}


def notes(slug: str, src: str, date: str, sh: list[dict], recon: str) -> str:
    n, leaf, canc = CANCEL[(slug, date)]
    parts = [
        f"Source bytes. {BOOK}{URL[slug]} as served on {TODAY}; "
        + ("PG&E reassembled the document on 2026-09-28 with the same text, so these bytes are new and "
           "data/documents.json records them." if slug == "e-1" else
           "the bytes equal data/documents/pge/" + URL[slug].replace(' (Sch)', '__Sch_') + ", first retrieved "
           "2026-09-23 (data/documents.json)."),
        "Sheets in force on " + date + ":\n" + sheet_lines(sh),
        *([("Sheet 1 in force on 2026-06-01 is 61116-E (Advice 7846-E), printed in the 2026-03-27 directory's "
            "document; the document vendored here is the current one, whose Sheet 1 is the 2026-08-28 reissue "
            "61545-E and whose other sheets are those in force on 2026-06-01.")]
          if (slug, date) == ("e-elec", JUN) else []),
        CHANGE[date].format(n=n, leaf=leaf, canc=canc, src=src, what=WHAT.get(slug, "")).replace(
            "The 2026-03-01 version carries no Climate Credit, because Advice 7869-E paused it from 2026-03-27.",
            "The 2026-03-01 version carries no Climate Credit: its document's Sheet 1 is 61247-E, Advice "
            "7869-E, effective 2026-03-27, which paused it."),
        recon,
        f"Supersession. Sheet {n} ({leaf}) cancels {canc}, the sheet of the {src} version it replaces, "
        f"effective {date}; the {src} version ends there.",
        f"Derived from the {src} version by dev/author_pge_2026.py.",
    ]
    return "\n\n".join(p if p.startswith("Sheets in force") else wrap(p) for p in parts)


def rewrite_deferrals(slug: str, date: str, deferrals: list[str], m: dict[str, str]) -> list[str]:
    out = []
    for t in deferrals:
        t = CURIE.sub(lambda x: m.get(x.group(0), x.group(0)), t)
        for sib in ("medical-baseline", "income-tier"):
            t = re.sub(rf"(pge:{re.escape(slug)}-{sib}-|_pge_{re.escape(slug)}-{sib}_)\d{{4}}-\d{{2}}-\d{{2}}",
                       lambda x: x.group(1) + date, t)
        t = t.replace("The Medical Baseline half is not modeled, and no PG&E Medical Baseline schedule is modeled.",
                      "The Medical Baseline half is not modeled for this schedule; pge:e-1-medical-baseline and "
                      "pge:e-tou-c-medical-baseline carry it for Schedules E-1 and E-TOU-C only.")
        t = DEFERRAL_EDITS.get((slug, date), lambda s: s)(t)
        if t:
            out.append(t)
    return out + ADD_DEFERRALS.get((slug, date), [])


def _eelec_jun(t: str) -> str | None:
    if t.startswith("Sheet 3 (AL 7846-E, leaf 61118-E) prices the New System Generation Charge"):
        return None  # the model carries 0.00000, reconciled below
    return t.replace("Sheet 2 (AL 7869-E, leaf 61248-E)", "Sheet 2 (AL 7921-E, leaf 61363-E)")


def _eelec_aug(t: str) -> str:
    return t


def _ev2(t: str) -> str:
    # pge:e-elec-2026-03-27 carries the charge at 0.00000, as Sheet 3 prints it.
    return t.replace(" The corpus carries it where it is nonzero, at $0.00792 per kWh on pge/e-elec 2026-03-27.", "")


def _e1(t: str) -> str:
    return t.replace("Sheet 1, 61247-E)", "Sheet 1, 61362-E)").replace("Sheet 1 (61247-E)", "Sheet 1 (61362-E)")


def _nbt(t: str) -> str:
    t = t.replace("The four Sheet 11 exclusions from the ACC Plus adder", "The four exclusions from the ACC Plus adder "
                  "that Sheets 11 and 12 list")
    return t.replace(
        "may not start a new legacy period under NBT and get no 9-year legacy treatment.",
        "may not start a new legacy period under NBT and get no 9-year legacy treatment, and the Sheet 32 rule "
        "(61550-E) that a NEM or NEM2 customer moved to NBT by a modification or repair exceeding its tariff's "
        "threshold begins a new 9-year legacy period from the modification's PTO date.")


DEFERRAL_EDITS = {("e-elec", JUN): _eelec_jun, ("e-elec", AUG): _eelec_aug, ("e-1", JUN): _e1, ("nbt", AUG): _nbt, ("ev2", JUN): _ev2}
ADD_DEFERRALS = {
    ("nbt", AUG): [
        "Sheet 10 (59900-E, Advice 7155-E-A, effective 2024-07-01): 'Bundled customers are eligible to receive "
        "both generation components and delivery components from PG&E, while unbundled customers will only "
        "receive delivery components from PG&E.' The Generation and Delivery Export Compensation Rate Prices "
        "carry no condition on bundled service, so a Direct Access or Community Choice Aggregation customer "
        "composing this modifier is credited the generation component PG&E does not pay it. Expressible as "
        "a condition on pge:program-cca, pge:program-da and pge:program-tbs over the Generation Prices, or as "
        "a urpx:ProfileAlternative for bundled against unbundled service.",
    ],
}


def write_manifest(slug: str, src: str, date: str, sh: list[dict], pdf: Path, deferrals: list[str],
                   recon: str) -> None:
    d = PGE / slug / "versions" / date
    old = tomllib.loads((PGE / slug / "versions" / src / "tariff.toml").read_text(encoding="utf-8"))
    al = "7921-E" if date == JUN else "7975-E"
    docket = "D.26-04-036" if date == JUN else "Advice 7975-E (Clean-Up of Electric Tariffs, effective 2026-08-28)"
    if slug == "e-elec" and date == AUG:
        docket = "D.26-04-036 (Sheet 2, Advice 7921-E); Advice 7975-E (Sheet 1, effective 2026-08-28)"
    retrieved = RETRIEVED.get(slug, "2026-09-23")
    multi = "base" in old["source"]
    src_lines = [f'url = "{BOOK}{URL[slug]}"', f'sha256 = "{sha(pdf)}"', f'retrieved_on = "{retrieved}"',
                 'media_type = "application/pdf"', 'filing_type = "advice-letter"', f'filing_id = "PGE-AL-{al}"']
    lines = ["# Identity --------------------------------------------------------------------",
             'utility = "pge"', f'schedule = "{slug}"', f'effective_date = "{date}"', "",
             "# Source ----------------------------------------------------------------------", "[source]"]
    if multi:
        r19 = old["source"]["rule_19"]
        lines += ["", "  [source.base]", *["  " + x for x in src_lines], "",
                  "  # Electric Rule 19: the Standard Medical Baseline Quantity the second document in this",
                  "  # directory adds to the baseline ladder.",
                  "  [source.rule_19]", f'  url = "{r19["url"]}"', f'  sha256 = "{r19["sha256"]}"',
                  f'  retrieved_on = "{r19["retrieved_on"]}"', '  media_type = "application/pdf"',
                  '  filing_type = "advice-letter"', '  filing_id = "PGE-AL-6865-E"', "",
                  "# Regulatory ------------------------------------------------------------------",
                  "[regulator]", "  [regulator.base]", '  authority = "puc"', f"  docket = {toml_str(docket)}", "",
                  "  [regulator.rule_19]", '  authority = "puc"', '  docket = "D.22-11-033"', ""]
    else:
        lines += src_lines + ["", "# Regulatory ------------------------------------------------------------------",
                              "[regulator]", 'authority = "puc"', f"docket = {toml_str(docket)}", ""]
    lines += ["# Extraction ------------------------------------------------------------------",
              "[extraction]", 'tool = "manual-diff"', f'extracted_on = "{TODAY}"', 'notes = """',
              notes(slug, src, date, sh, recon), '"""', "",
              "# Validation ------------------------------------------------------------------",
              "[validation]", "shacl_passed = true", 'validator = "pyshacl + clj-urpx (URPX v0.5.1)"',
              f'validated_on = "{TODAY}"', "",
              "# Modeling -------------------------------------------------------------------",
              "[modeling]", f"complete = {'true' if old['modeling']['complete'] else 'false'}", "deferrals = [",
              *[" " + toml_str(x) + "," for x in deferrals], "]"]
    mods = old["modeling"].get("applicable_modifiers")
    if mods is not None:
        lines += ["applicable_modifiers = [", *[f' "{x}",' for x in mods], "]"]
    lines += ["", "# Review ----------------------------------------------------------------------", "[review]",
              'status = "draft"',
              "notes = " + toml_str(f"Derived from the {src} version by dev/author_pge_2026.py; see [extraction] "
                                    "notes for the sheets in force, what moved and the reconciliation."), ""]
    text = "\n".join(lines)
    tomllib.loads(text)
    (d / "tariff.toml").write_text(text, encoding="utf-8")


def recon_text(slug: str, date: str) -> str:
    if slug == "nbt":
        return ("Reconciliation. The ACC Plus adder Prices are Sheet 11's 2025 row as credits (-0.01320 "
                "Residential, -0.05400 Residential Low Income); the Export Compensation Rate cells are carried over from the 2025-10-17 "
                "version, whose source is PG&E's published price sheets rather than this schedule.")
    pub = PUBLISHED[slug]
    if slug == "e-1":
        body = (f"Generation, Distribution, the all-usage components and the Conservation Incentive Adjustment "
                f"of each tier sum to the Sheet 1 totals {pub['t1']}, {pub['t2']} and {pub['t2c']}")
    elif slug == "e-tou-c":
        body = ("in each of the four season and period cells, generation, distribution, the all-usage "
                "components and the Tier 2 Conservation Incentive Adjustment sum to the Sheet 2 Total Usage rate ("
                + ", ".join(v for k, v in pub.items() if k != "baseline-credit")
                + "), and the Tier 1 adjustment gives that rate less the Baseline Credit of $0.08140")
    else:
        body = ("in each season and period cell, generation, distribution and the all-usage components sum to the "
                "Sheet 2 total (" + ", ".join(dict.fromkeys(pub.values())) + ")")
    return ("Reconciliation. " + body[0].upper() + body[1:] + ". Every modeled per-kWh price is printed on the "
            "sheets in force, as are the Base Services Charges (0.19713, 0.39688, 0.79343) and the ($36.18) "
            "Climate Credit.")


STALE_NSGC = ' "Sheet 3 (AL 7846-E, leaf 61118-E) prices the New System Generation Charge'


def fix_held() -> None:
    """The 2026-03-27 E-ELEC manifest says the model carries a New System
    Generation Charge of 0.00792, and the 2026-03-27 EV2 manifest repeats it; it
    carries 0.00000, as Sheet 3 prints it."""
    p = PGE / "e-elec/versions/2026-03-27/tariff.toml"
    lines = p.read_text(encoding="utf-8").split("\n")
    hit = [i for i, line in enumerate(lines) if line.startswith(STALE_NSGC)]
    doc = load(doc_path("e-elec", "2026-03-27"))
    if find(doc, "pge:e-elec-2026-03-27-price-new-sys-gen")["urpx:unitPrice"] != "0.00000":
        raise SystemExit("e-elec 2026-03-27: New System Generation Charge is not 0.00000")
    for i in reversed(hit):
        del lines[i]
    p.write_text("\n".join(lines), encoding="utf-8")
    p = PGE / "ev2/versions/2026-03-27/tariff.toml"
    p.write_text(_ev2(p.read_text(encoding="utf-8")), encoding="utf-8")


RIN_NOTE = re.compile(r" \(MIDAS RIN: USCA-[A-Z0-9-]+ [^)]*\)")
RIN_BLOCK = """# MIDAS RIN cross-reference ---------------------------------------------------
# Each Delivery Component Price carries its CEC MIDAS Rate Identification
# Number in urpx:name. PG&E E-ELEC NBT RINs:
# USCA-PGXX-3500-0000 E-ELEC + NBT23-CCA (Delivery)
# USCA-PGXX-3600-0000 E-ELEC + NBT24-CCA (Delivery)
# USCA-PGXX-3900-0000 E-ELEC + NBT25-CCA (Delivery)
# USCA-PGXX-4000-0000 E-ELEC + NBT26-CCA (Delivery)
# CCA-flavored AltRateName1 is a labeling artifact: Delivery values are
# system-wide and apply identically to Bundled and CCA customers.
# Generation Component Prices are NOT RIN-tagged: PG&E does not publish
# Generation EEC via MIDAS (USCA-XXPG family contains only SGIP and Flex
# entries). Same pattern as SCE.
# Tagging tool: scripts/tag-pge-nbt-prices-with-midas-rins.py
"""


def move_rins(old_date: str = "2025-10-17", new_date: str = AUG) -> None:
    """A MIDAS RIN attests a composition a customer takes service under today
    (dev/list_rate_identifiers.py refuses one on a superseded version), so the
    citations stay on the current NBT version only."""
    p = doc_path("nbt", old_date)
    doc = load(p)
    n = [0]

    def f(d):
        if d.get("@type") == "urpx:Price" and "MIDAS RIN" in d.get("urpx:name", ""):
            d["urpx:name"] = RIN_NOTE.sub("", d["urpx:name"])
            n[0] += 1
    walk(doc, f)
    dump(p, doc)
    t = (PGE / "nbt/versions" / old_date / "tariff.toml").read_text(encoding="utf-8")
    i = t.index("# MIDAS RIN cross-reference")
    j = t.index("# Modeling ---", i)
    t = t[:i] + (f"# MIDAS RIN citations are on the {new_date} version, which superseded this one; they\n"
                 "# were removed here because a RIN names a composition customers take today.\n\n") + t[j:]
    (PGE / "nbt/versions" / old_date / "tariff.toml").write_text(t, encoding="utf-8")
    t = (PGE / "nbt/versions" / new_date / "tariff.toml").read_text(encoding="utf-8")
    j = t.index("# Modeling ---")
    (PGE / "nbt/versions" / new_date / "tariff.toml").write_text(t[:j] + RIN_BLOCK + "\n" + t[j:], encoding="utf-8")
    tomllib.loads((PGE / "nbt/versions" / new_date / "tariff.toml").read_text(encoding="utf-8"))
    print(f"nbt {old_date}: {n[0]} RIN citations moved to {new_date}")


# --- main ----------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    fetched = Path(argv[1])
    report: list[str] = []
    out = []
    sheet_cache = {f: sheets(fetched / f) for *_r, f in STEPS}
    report += ladder_check(sheet_cache)
    staged: dict[tuple[str, str], tuple] = {}
    for slug, src, date, f in STEPS:
        sh = sheet_cache[f]
        if slug == "e-elec" and date == JUN:
            # Sheet 1 in force on 2026-06-01 is 61116-E (2026-03-01), from the 2026-03-27 document.
            held = sheets(PGE / "e-elec/versions/2026-03-27/pge_e-elec_2026-03-27.pdf")
            sh = [held[0]] + sh[1:]
        if (slug, src) in staged:  # derive from a version written in this run
            dump(doc_path(slug, src), staged[(slug, src)][0])
        if is_base(slug):
            doc, m = base_version(slug, src, date, sh, RETRIEVED.get(slug, "2026-09-23"))
            report += reconcile(slug, date, doc, sh)
        else:
            doc, m = nbt_version(sh)
        staged[(slug, date)] = (doc, m, sh, src, f)
        out.append((slug, src, date))
    # Undo the intermediate write if it happened and the run refuses.
    if report:
        if (PGE / "e-elec/versions" / JUN).exists():
            import shutil
            shutil.rmtree(PGE / "e-elec/versions" / JUN)
        print("\n".join(report))
        print(f"\n{len(report)} problem(s); nothing written.")
        return 1
    for slug, src, date in out:
        doc, m, sh, src_, f = staged[(slug, date)]
        dump(doc_path(slug, date), doc)
        pdf = PGE / slug / "versions" / date / f"pge_{slug}_{date}.pdf"
        pdf.write_bytes((fetched / f).read_bytes())
        if slug in ("e-1", "e-tou-c"):
            r19 = PGE / slug / "versions" / src / "pge_rule-19_2023-03-23.pdf"
            (pdf.parent / r19.name).write_bytes(r19.read_bytes())
        old = tomllib.loads((PGE / slug / "versions" / src / "tariff.toml").read_text(encoding="utf-8"))
        deferrals = rewrite_deferrals(slug, date, old["modeling"]["deferrals"], m)
        write_manifest(slug, src, date, sh, pdf, deferrals, recon_text(slug, date))
        expire(doc_path(slug, src), date)
        print(f"{slug} {date} from {src}")
    fix_held()
    move_rins()
    it, _ = income_tier(staged[("e-1", JUN)][2])
    dump(doc_path("e-1", JUN, "e-1-income-tier"), it)
    expire(doc_path("e-1", "2026-03-01", "e-1-income-tier"), JUN)
    for b in ("e-1", "e-tou-c", "e-tou-d", "ev2"):
        sync_pcia(b)
    candidates([f"pge:{b}-{JUN}" for b in BASES] + [f"pge:e-elec-{AUG}"])
    # The D.26-03-013 RateCase url, wherever the node is carried.
    for p in sorted(PGE.glob("*/versions/*/*.jsonld")):
        d = load(p)
        hit = False
        for n in d.get("@graph", []):
            if n.get("@id") == "pge:rc-d-26-03-013" and n.get("urpx:url") != RC_MAR_URL:
                n["urpx:url"] = RC_MAR_URL
                hit = True
        if hit:
            dump(p, d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
