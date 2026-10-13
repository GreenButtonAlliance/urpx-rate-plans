#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Add the SCE NBT version effective 2025-06-02 (Advice 5497-E).

Advice 5497-E reissues Sheet 6 (89868-E, cancelling 87507-E: the EEC Vintage
Year is that of the Interconnection Request date when the Original PTO Date is
after June 30, 2024) and Sheet 34 (89869-E, cancelling 87704-E: a NEM or NEM-ST
customer moved to NBT whose system grows by more than 10 percent or 1 kW begins
a new 9-year legacy period). No price moved.

The version is derived from the 2025-04-23 version. Every subordinate @id is
scoped to the new version (LAYOUT.md section 6), the MetricSpecification kept
shared. The source is the live tariff book held at
data/documents/sce/ELECTRIC_SCHEDULES_NBT.pdf, copied into the filing
directory. The script refuses unless that book carries the two 2025-06-02
sheets, no sheet effective later, and the 2025 ACC Plus row the model prices,
and unless every Price of the new version equals its 2025-04-23 counterpart.

The 2025-04-23 version ends at 2025-06-02, the effective date of the sheets
that cancel two it models. The MIDAS RIN citations move to the new version,
since dev/list_rate_identifiers.py refuses one on a superseded version.

tariff.toml and README.md of the new filing are authored by hand.

Run from the repo root:
    python3 dev/author_sce_nbt_2025_06_02.py
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import rescope_iris as rescope  # noqa: E402

SRC, DATE, TODAY = "2025-04-23", "2025-06-02", "2026-10-11"
RETRIEVED = "2026-09-23"  # data/documents.json first saw these bytes then
NBT = REPO / "us/ca/sce/electricity/nbt/versions"
BOOK = REPO / "data/documents/sce/ELECTRIC_SCHEDULES_NBT.pdf"
BOOK_SHA = "f99d38000593434cfdaf4491cffe7f881c4774040bd61f275ef6de6f9fc03e81"
URL = ("https://edisonintl.sharepoint.com/teams/Public/TM2/Shared%20Documents/Public/Regulatory/"
       "Tariff-SCE%20Tariff%20Books/Electric/Schedules/Other%20Rates/ELECTRIC_SCHEDULES_NBT.pdf")
# (sheet, leaf, cancels) that Advice 5497-E reissued effective 2025-06-02.
REISSUED = [(6, "89868-E", "87507-E"), (34, "89869-E", "87704-E")]
ACC_PLUS_2025 = {"non-equity": "-0.024", "equity": "-0.056"}
RIN_NOTE = re.compile(r" \(MIDAS RIN: [^)]*\)")
CURIE = re.compile(r"sce:[A-Za-z0-9_.-]*[A-Za-z0-9]")

MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
                                      "Nov", "Dec"], 1)}

DESCRIPTION_ADD = (
    " Advice 5497-E, effective 2025-06-02, reissued Sheet 6 (Cal. P.U.C. Sheet No. 89868-E), which assigns a"
    " Customer whose Original PTO Date is after June 30, 2024 the EEC Vintage Year of the date its"
    " Interconnection Request was submitted, and Sheet 34 (89869-E), under which a NEM or NEM-ST Customer moved"
    " to this Schedule whose modifications or repairs increase system size by more than 10 percent or 1 kW"
    " begins a new 9-year legacy period from the PTO date of the modification. No price changed.")

EVALUATION_ADD = (
    " The EEC Vintage Year assignment rule of Rates section 3.a.ii (Sheet 6, Cal. P.U.C. Sheet No. 89868-E)"
    " and the Special Condition 7 legacy provisions (Sheet 34, 89869-E) set which vintage applies to a"
    " customer and for how long; the vintage is a selection the consumer supplies, and neither rule is"
    " represented.")


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def dump(p: Path, doc) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def doc_path(date: str) -> Path:
    return NBT / date / f"rate-plan-modifier_sce_nbt_{date}.jsonld"


def version_node(doc):
    return doc["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"]


def prices(doc) -> dict[str, str]:
    out = {}
    rescope.walk(doc, lambda d: out.__setitem__(d["@id"], d["urpx:unitPrice"])
                 if d.get("@type") == "urpx:Price" else None)
    return out


def sheets(p: Path) -> list[dict]:
    t = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True, check=True).stdout
    out = []
    for n, page in enumerate([x for x in t.split("\f") if x.strip()], 1):
        leaf = re.search(r"(?:Original|Revised)\s+Cal\. P\.U\.C\. Sheet No\.\s+(\d+-E)", page)
        canc = re.search(r"Cancelling\s+(?:Original|Revised)?\s*Cal\. P\.U\.C\. Sheet No\.\s+(\d+-E)", page)
        eff = re.search(r"Effective\s+([A-Z][a-z]{2}) (\d+), (\d{4})", page)
        out.append({"sheet": n, "leaf": leaf.group(1), "cancels": canc.group(1) if canc else None,
                    "eff": f"{eff.group(3)}-{MONTHS[eff.group(1)]:02d}-{int(eff.group(2)):02d}", "text": page})
    return out


def check_book(sh: list[dict]) -> list[str]:
    errs = []
    if hashlib.sha256(BOOK.read_bytes()).hexdigest() != BOOK_SHA:
        errs.append(f"{BOOK}: sha256 is not {BOOK_SHA}")
    for n, leaf, canc in REISSUED:
        s = sh[n - 1]
        if (s["leaf"], s["cancels"], s["eff"]) != (leaf, canc, DATE):
            errs.append(f"Sheet {n}: {s['leaf']} cancelling {s['cancels']} effective {s['eff']}")
    late = [s["sheet"] for s in sh if s["eff"] > DATE]
    if late:
        errs.append(f"sheets effective after {DATE}: {late}")
    row = re.search(r"^\s*2025\s+\$(\S+)/kWh\s+\$(\S+)/kWh", sh[6]["text"], re.M)
    if not row or ("-" + row.group(1), "-" + row.group(2)) != (ACC_PLUS_2025["non-equity"],
                                                                ACC_PLUS_2025["equity"]):
        errs.append(f"Sheet 7 2025 ACC Plus row is {row and row.groups()}")
    return errs


def rename_map(doc) -> dict[str, str]:
    old_vid = version_node(doc)["@id"]
    new_vid = old_vid.replace(SRC, DATE)
    m: dict[str, str] = {}

    def f(d, own):
        i = d.get("@id")
        if not isinstance(i, str) or len(d) <= 1 or i in m or own not in (None, old_vid):
            return
        t = rescope.node_type(d)
        if f"nbt-{SRC}" in i:
            m[i] = i.replace(f"nbt-{SRC}", f"nbt-{DATE}")
        elif t in rescope.IDENTITY_TYPES or t in rescope.KEEP_SHARED_TYPES or i.startswith("org:") \
                or t == "urpx:URPXPackage":
            return
        else:
            m[i] = rescope.new_iri(i, new_vid)
    rescope.walk_owned(doc, f)
    if len(set(m.values())) != len(m):
        raise SystemExit("rename collides")
    return m


def apply_map(doc, m: dict[str, str]) -> None:
    def f(d):
        for k, v in list(d.items()):
            if k == "@id" and isinstance(v, str) and v in m:
                d[k] = m[v]
            elif isinstance(v, str) and k != "@id" and "sce:" in v:
                d[k] = CURIE.sub(lambda x: m.get(x.group(0), x.group(0)), v)
    rescope.walk(doc, f)


def derive(sh: list[dict]):
    doc = load(doc_path(SRC))
    m = rename_map(doc)
    apply_map(doc, m)
    doc["@id"] = doc["@id"].replace(SRC, DATE)
    v = version_node(doc)
    v["urpx:version"] = v["urpx:modifierVersionNumber"] = DATE
    v["urpx:effectiveDateTime"] = f"{DATE}T00:00:00"
    v.pop("urpx:expirationDateTime", None)
    v["urpx:changeReason"] = {"@id": "urpx:changeReasonOther"}
    v["urpx:description"] += DESCRIPTION_ADD
    leaves = sorted(s["leaf"] for s in sh)
    v["urpx:hasDataSourceReference"].update({
        "urpx:accessURL": URL, "urpx:dateRetrieved": RETRIEVED, "urpx:pageStart": 1, "urpx:pageEnd": len(sh),
        "urpx:leafStart": leaves[0], "urpx:leafEnd": leaves[-1]})
    ev = v["urpx:hasCoverageClaim"]["urpx:explainedBy"]
    ev["urpx:description"] += EVALUATION_ADD
    ev["urpx:evaluatedOn"] = f"{TODAY}T00:00:00"
    return doc, m


def same_prices(old, new, m: dict[str, str]) -> list[str]:
    a, b = prices(old), prices(new)
    errs = [f"{i}: {a[i]} -> {b.get(m.get(i, i))}" for i in a if b.get(m.get(i, i)) != a[i]]
    if len(a) != len(b):
        errs.append(f"{len(a)} Prices in {SRC}, {len(b)} in {DATE}")
    for seg, val in ACC_PLUS_2025.items():
        if b.get(f"sce:nbt-{DATE}-price-acc-plus-{seg}-vintage-2025") != val:
            errs.append(f"ACC Plus {seg} is not {val}")
    return errs


def expire(doc) -> None:
    ctx = doc["@context"]
    if "urpx:expirationDateTime" not in ctx:
        out = {}
        for k, x in ctx.items():
            out[k] = x
            if k == "urpx:effectiveDateTime":
                out["urpx:expirationDateTime"] = {"@type": "xsd:dateTime"}
        doc["@context"] = out
    v = version_node(doc)
    new_v = {}
    for k, x in v.items():
        if k == "urpx:expirationDateTime":
            continue
        new_v[k] = x
        if k == "urpx:effectiveDateTime":
            new_v["urpx:expirationDateTime"] = f"{DATE}T00:00:00"
    doc["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"] = new_v


def strip_rins(doc) -> int:
    n = [0]

    def f(d):
        if d.get("@type") == "urpx:Price" and "MIDAS RIN" in d.get("urpx:name", ""):
            d["urpx:name"] = RIN_NOTE.sub("", d["urpx:name"])
            n[0] += 1
    rescope.walk(doc, f)
    return n[0]


def main() -> int:
    sh = sheets(BOOK)
    errs = check_book(sh)
    old = load(doc_path(SRC))
    new, m = derive(sh)
    errs += same_prices(old, new, m)
    if errs:
        print("\n".join(errs))
        print(f"\n{len(errs)} problem(s); nothing written.")
        return 1
    dump(doc_path(DATE), new)
    (NBT / DATE / f"sce_nbt_{DATE}.pdf").write_bytes(BOOK.read_bytes())
    expire(old)
    n = strip_rins(old)
    dump(doc_path(SRC), old)
    print(f"nbt {DATE} from {SRC}: {len(m)} @ids scoped; {SRC} ends {DATE}; {n} RIN citations moved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
