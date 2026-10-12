#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Negative tests for the discount-subtotal lint's SCE generation rule and its
SCL suburban multiplier rule.

Each case copies the four 2026-03-20 SCE residential bases, sce:care and
sce:da-crs (or the SCL RTS filings and scl:residential-suburban) into a
temporary `us/` tree, alters them, and asserts the lint's verdict on the copy.

Run: python3 dev/test_discount_summaries.py
"""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "lint_discount_summaries", REPO / "dev" / "lint_discount_summaries.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

LINT = REPO / "dev" / "lint_discount_summaries.py"
DATE = "2026-03-20"
BASES = ["d", "tou-d-4-9pm", "tou-d-5-8pm", "tou-d-prime"]
PGE_GENERATION = [("e-1", "2026-03-01"), ("e-1", "2026-06-01"),
                  ("e-elec", "2026-01-01"), ("e-elec", "2026-03-27"), ("e-elec", "2026-06-01"), ("e-elec", "2026-08-28"),
                  ("e-tou-c", "2026-03-01"), ("e-tou-c", "2026-03-27"), ("e-tou-c", "2026-06-01"),
                  ("e-tou-d", "2026-03-27"), ("e-tou-d", "2026-06-01"), ("ev2", "2026-03-27"), ("ev2", "2026-06-01")]
MODIFIERS = ["care", "da-crs"]
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}{': ' + detail if detail else ''}")
        failures.append(name)


def originals() -> dict[str, dict]:
    docs = {}
    for b in BASES:
        docs[b] = json.loads(corpus.filing_path("sce", b, DATE).read_text())
    for m in MODIFIERS:
        docs[m] = json.loads(corpus.filing_path("sce", m, DATE, "rate-plan-modifier").read_text())
    return docs


def lay_out(tmp: Path, docs: dict[str, dict]) -> list[Path]:
    """Write `docs` where utility_of() can read the utility off the path."""
    out = []
    for name, doc in docs.items():
        kind = "rate-plan-modifier" if name in MODIFIERS else "rate-plan"
        p = tmp / "us" / "ca" / "sce" / "electricity" / name / "versions" / DATE / \
            f"{kind}_sce_{name}_{DATE}.jsonld"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc))
        out.append(p)
    return out


def node(x, nid: str):
    if isinstance(x, dict):
        if x.get("@id") == nid and "@type" in x:
            return x
        for v in x.values():
            r = node(v, nid)
            if r is not None:
                return r
    elif isinstance(x, list):
        for v in x:
            r = node(v, nid)
            if r is not None:
                return r
    return None


def problems(tmp: Path, docs: dict[str, dict]) -> list[dict]:
    return L.check(lay_out(tmp, docs))[0]


def summary_problem(ps: list[dict], sid: str):
    return next((p for p in ps if p.get("summary") == sid and "missing" in p), None)


GEN = "sce:tou-d-4-9pm-2026-03-20-summary-generation"
DWREC = "sce:tou-d-4-9pm-2026-03-20-price-gen-dwrec"
OFFSET = "sce:da-crs-price-oat-generation-offset-2026-03-20"


def test_clean(tmp: Path) -> None:
    print("\nThe copies as committed")
    ps = problems(tmp / "clean", originals())
    check("the four bases, sce:care and sce:da-crs are clean", ps == [], json.dumps(ps)[:400])
    members = L.expected_generation(corpus.filing_path("sce", "tou-d-4-9pm", DATE))
    check("the generation rule yields six Generation Prices and the DWR Energy Credit",
          len(members) == 7 and DWREC in members, str(members))
    check("on Schedule D it yields Generation and the DWR Energy Credit",
          sorted(L.expected_generation(corpus.filing_path("sce", "d", DATE))) ==
          ["sce:price-generation-2026-03-20", "sce:price-generation-dwrec-2026-03-20"])


def test_membership(tmp: Path) -> None:
    print("\nMembership of a generation subtotal")
    docs = originals()
    s = node(docs["tou-d-4-9pm"], GEN)
    s["urpx:includesPrice"] = [m for m in s["urpx:includesPrice"] if m["@id"] != DWREC]
    p = summary_problem(problems(tmp / "drop", docs), GEN)
    check("dropping the DWR Energy Credit FAILS, naming it missing",
          p is not None and p["missing"] == [DWREC] and p["unexpected"] == [], str(p))

    docs = originals()
    extra = "sce:tou-d-4-9pm-2026-03-20-price-dist-summer-on-peak"
    node(docs["tou-d-4-9pm"], GEN)["urpx:includesPrice"].append({"@id": extra})
    p = summary_problem(problems(tmp / "extra", docs), GEN)
    check("adding a Distribution Price FAILS, naming it unexpected",
          p is not None and p["unexpected"] == [extra] and p["missing"] == [], str(p))

    docs = originals()
    sid = "sce:tou-d-4-9pm-2026-03-20-summary-discountable"
    s = node(docs["tou-d-4-9pm"], sid)
    s["urpx:includesPrice"] = [m for m in s["urpx:includesPrice"] if m["@id"] != DWREC]
    p = summary_problem(problems(tmp / "care", docs), sid)
    check("the CARE subtotal is still held to the CARE rule",
          p is not None and p["missing"] == [DWREC], str(p))


def test_candidates(tmp: Path) -> None:
    print("\nCandidates of a generation offset")
    docs = originals()
    price = node(docs["da-crs"], OFFSET)
    price["urpx:basedOnPrice"] = [c for c in price["urpx:basedOnPrice"] if c["@id"] != GEN]
    ps = [p for p in problems(tmp / "cand", docs) if p.get("discount") == OFFSET]
    check("an offset omitting one base's generation subtotal FAILS, naming only it",
          len(ps) == 1 and ps[0].get("missing_candidates") == [GEN], str(ps))

    docs = originals()
    ps = [p for p in problems(tmp / "nocare", docs) if p.get("discount") == OFFSET]
    check("an offset is not asked for the CARE or FERA subtotals", ps == [], str(ps))


def test_arithmetic(tmp: Path) -> None:
    print("\nArithmetic over a generation subtotal")
    docs = originals()
    dup = copy.deepcopy(node(docs["tou-d-4-9pm"], "sce:tou-d-4-9pm-2026-03-20-price-gen-summer-on-peak"))
    dup["@id"] = "ex:gen-summer-on-peak-twice"
    ps_node = node(docs["tou-d-4-9pm"], "sce:tou-d-4-9pm-2026-03-20-ps-generation-charges")
    ps_node["urpx:hasPrice"].append(dup)
    node(docs["tou-d-4-9pm"], GEN)["urpx:includesPrice"].append({"@id": dup["@id"]})
    ps = problems(tmp / "dup", docs)
    check("one PriceDefinition named twice FAILS under DEFINITIONS",
          any(p.get("definition") == "sce:tou-d-4-9pm-2026-03-20-pd-gen-summer-on-peak"
              and p.get("summary") == GEN for p in ps), json.dumps(ps)[:400])
    check("and the offset over it FAILS as double-counted",
          any(p.get("kind") == "double-counted" and p.get("discount") == OFFSET for p in ps))


SCL_DATES = ["2026-01-01", "2027-01-01"]
SCL_ENERGY = "scl:residential-suburban-2026-01-01-price-shoreline-franchise-tax-energy"


def scl_originals() -> dict[tuple[str, str], dict]:
    docs = {}
    for d in SCL_DATES:
        docs[("rts", d)] = json.loads(corpus.filing_path("scl", "rts", d).read_text())
        docs[("residential-suburban", d)] = json.loads(corpus.filing_path(
            "scl", "residential-suburban", d, "rate-plan-modifier").read_text())
    return docs


def scl_problems(tmp: Path, docs: dict[tuple[str, str], dict]) -> list[dict]:
    out = []
    for (name, d), doc in docs.items():
        kind = "rate-plan" if name == "rts" else "rate-plan-modifier"
        p = tmp / "us" / "wa" / "scl" / "electricity" / name / "versions" / d / f"{kind}_scl_{name}_{d}.jsonld"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc))
        out.append(p)
    return L.check(out)[0]


def test_scl(tmp: Path) -> None:
    print("\nSCL suburban franchise and tax multipliers")
    ps = scl_problems(tmp / "scl-clean", scl_originals())
    check("RTS 2026 and 2027 and their modifier versions are clean", ps == [], json.dumps(ps)[:400])

    docs = scl_originals()
    sid, base = "scl:rts-2026-01-01-summary-energy", "scl:rts-2026-01-01-price-base-service-charge"
    node(docs[("rts", "2026-01-01")], sid)["urpx:includesPrice"].append({"@id": base})
    p = summary_problem(scl_problems(tmp / "scl-base", docs), sid)
    check("the per-day Base Service Charge in the energy subtotal FAILS, naming it unexpected",
          p is not None and p["unexpected"] == [base] and p["missing"] == [], str(p))

    docs = scl_originals()
    node(docs[("residential-suburban", "2026-01-01")], SCL_ENERGY)["urpx:basedOnPrice"] = [
        {"@id": "scl:rts-2027-01-01-summary-energy"}]
    ps = [p for p in scl_problems(tmp / "scl-year", docs) if p.get("discount") == SCL_ENERGY]
    check("a 2026 multiplier based on the 2027 subtotal FAILS as another year's",
          len(ps) == 1 and ps[0].get("wrong_year") == ["scl:rts-2027-01-01-summary-energy"], str(ps))


def test_corpus() -> None:
    print("\nThe live corpus")
    p = subprocess.run([sys.executable, str(LINT)], capture_output=True, text=True)
    check("the lint passes the corpus", p.returncode == 0, (p.stdout + p.stderr)[-400:])
    sums = {sid for f in corpus.all_filing_jsonld() for sid in L.Filing(Path(f)).summaries
            if sid.endswith(L.GENERATION)}
    sce = {f"sce:{b}-{d}-summary-generation" for b in BASES for d in (DATE, "2026-06-01", "2026-10-01")}
    pge = {f"pge:{b}-{d}-summary-generation" for b, d in PGE_GENERATION}
    check("it finds the SCE generation subtotals, four bases at three dates, and the 13 PG&E ones",
          sums == sce | pge, str(sorted(sums)))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        test_clean(Path(tmp))
        test_membership(Path(tmp))
        test_candidates(Path(tmp))
        test_arithmetic(Path(tmp))
        test_scl(Path(tmp))
    test_corpus()
    print()
    if failures:
        print(f"{len(failures)} failure(s): {', '.join(failures)}")
        raise SystemExit(1)
    print("discount-subtotal lint: every generation and SCL guard fired and the corpus stayed clean")
