#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Tests for the shared price cell lint.

Each case copies a real filing into a temporary directory, alters it, and
asserts the lint's verdict on the copy.

Run: python3 dev/test_price_cells.py
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

spec = importlib.util.spec_from_file_location("lint_price_cells", REPO / "dev" / "lint_price_cells.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

LINT = REPO / "dev" / "lint_price_cells.py"
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}{': ' + detail if detail else ''}")
        failures.append(name)


def document(utility: str, schedule: str, date: str, kind: str = "rate-plan") -> dict:
    return json.loads(corpus.filing_path(utility, schedule, date, kind).read_text())


def write(tmp: Path, name: str, doc: dict) -> Path:
    p = tmp / name
    p.write_text(json.dumps(doc))
    return p


def nodes(x, t: str):
    if isinstance(x, dict):
        if x.get("@type") == t:
            yield x
        for v in x.values():
            yield from nodes(v, t)
    elif isinstance(x, list):
        for v in x:
            yield from nodes(v, t)


def shared(*paths: Path) -> list[dict]:
    return L.run(list(paths), whole_corpus=False)["shared"]


def cli(*paths: Path) -> int:
    return subprocess.run([sys.executable, str(LINT), "--file", *map(str, paths)],
                          capture_output=True, text=True).returncode


LOW_USE = "smud:nem1-price-credit-tod-low-use-tou"


def nem1_collided() -> dict:
    """NEM1 as it was: each tod-low-use credit on the tod-5-8pm credit's definition."""
    doc = document("smud", "nem1", "2021-09-17", "rate-plan-modifier")
    for p in nodes(doc, "urpx:Price"):
        if p["@id"].startswith(LOW_USE):
            p["urpx:referencesPriceDefinition"] = {"@id": f"smud:nem1-pd-net-credit-tou{p['@id'][-1]}"}
    return doc


def low_use(doc: dict):
    return [p for p in nodes(doc, "urpx:Price") if p["@id"].startswith(LOW_USE)]


def test_nem1(tmp: Path) -> None:
    print("\nSMUD NEM1 credits")
    p = write(tmp, "nem1.jsonld", document("smud", "nem1", "2021-09-17", "rate-plan-modifier"))
    check("NEM1 as committed shares no cell", shared(p) == [], str(shared(p)))
    check("CLI exits 0 on it", cli(p) == 0)

    q = write(tmp, "nem1-collided.jsonld", nem1_collided())
    f = shared(q)
    check("both R-TOD bases' credits on one definition FAIL, once per definition",
          sorted(x["cell"][0] for x in f) == [f"smud:nem1-pd-net-credit-tou{n}" for n in range(1, 6)]
          and all(len(x["prices"]) == 2 for x in f), str(f))
    check("CLI exits 1 on it", cli(q) == 1)

    doc = nem1_collided()
    for p in low_use(doc):
        p["urpx:startDate"] = "2022-01-01"
    check("a different start passes", shared(write(tmp, "nem1-start.jsonld", doc)) == [])

    doc = nem1_collided()
    for p in low_use(doc):
        p["urpx:serviceTierNumber"] = 2
    check("a different tier passes", shared(write(tmp, "nem1-tier.jsonld", doc)) == [])

    doc = nem1_collided()
    for p in low_use(doc):
        p["urpx:touPeriodNumber"] = 9
    check("a different period on the Price passes", shared(write(tmp, "nem1-period.jsonld", doc)) == [])

    doc = nem1_collided()
    for p in nodes(doc, "urpx:Price"):
        p.pop("urpx:startDate", None)
    check("no start on either counts as the same start, and FAILS",
          len(shared(write(tmp, "nem1-nostart.jsonld", doc))) == 5)

    for set_start, n in (("2021-09-17", 5), ("2022-01-01", 0)):
        doc = nem1_collided()
        prices = doc["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"]["urpx:hasPrices"]
        moved = [p for p in prices["urpx:hasPrice"] if p["@id"].startswith(LOW_USE)]
        prices["urpx:hasPrice"] = [p for p in prices["urpx:hasPrice"] if p not in moved]
        for p in moved:
            p.pop("urpx:startDate")
        prices["urpx:hasPriceSet"] = [{"@type": "urpx:PriceSet", "@id": "ex:ps",
                                       "urpx:startDate": set_start, "urpx:hasPrice": moved}]
        got = shared(write(tmp, f"nem1-set-{set_start}.jsonld", doc))
        check(f"a Price inheriting start {set_start} from its PriceSet gives {n} finding(s)",
              len(got) == n, str(got))

    doc = nem1_collided()
    prices = doc["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"]["urpx:hasPrices"]
    prices["urpx:hasPrice"] += copy.deepcopy(prices["urpx:hasPrice"])
    f = shared(write(tmp, "nem1-twice.jsonld", doc))
    check("the same Price @id read twice in a version is one Price",
          len(f) == 5 and all(len(x["prices"]) == 2 for x in f), str(f))

    p = write(tmp, "nem1-only-twice.jsonld", document("smud", "nem1", "2021-09-17", "rate-plan-modifier"))
    doc = json.loads(p.read_text())
    prices = doc["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"]["urpx:hasPrices"]
    prices["urpx:hasPrice"] += copy.deepcopy(prices["urpx:hasPrice"])
    check("and a Price repeated by @id alone does not share a cell with itself",
          shared(write(tmp, "nem1-only-twice.jsonld", doc)) == [])


def test_alternatives(tmp: Path) -> None:
    print("\nPriceSetAlternatives (cpau e-3)")
    e3 = document("cpau", "e-3", "2007-07-01")
    p = write(tmp, "e3.jsonld", e3)
    pairs = {}
    for a in nodes(e3, "urpx:PriceSetAlternative"):
        for x in L.scan("e3", a):
            pairs.setdefault((x["cell"], x["start"]), set()).add(a["@id"])
    check("e-3's alternatives share cells with one another",
          any(len(v) > 1 for v in pairs.values()), str(pairs))
    check("and that passes, since two alternatives are never read together", shared(p) == [])

    doc = copy.deepcopy(e3)
    one = copy.deepcopy(next(nodes(next(nodes(doc, "urpx:PriceSetAlternative")), "urpx:Price")))
    one["@id"] = "ex:top-level"
    doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]["urpx:hasPrices"]["urpx:hasPrice"] = [one]
    f = shared(write(tmp, "e3-top.jsonld", doc))
    check("a top-level Price sharing a cell with an alternative's FAILS",
          len(f) == 1 and "ex:top-level" in f[0]["prices"], str(f))


def test_refusals(tmp: Path) -> None:
    print("\nRefusals")
    check("an empty file list refuses",
          subprocess.run([sys.executable, "-c",
                          f"import sys; sys.path.insert(0, {str(REPO / 'dev')!r}); "
                          "import lint_price_cells as L; L.run([])"],
                         capture_output=True).returncode != 0)
    p = write(tmp, "bare.jsonld", {"@type": "urpx:URPXPackage"})
    try:
        L.run([p], whole_corpus=True)
        check("a corpus with no Price refuses", False)
    except L.Refused:
        check("a corpus with no Price refuses", True)


def test_corpus() -> None:
    print("\nThe live corpus")
    p = subprocess.run([sys.executable, str(LINT)], capture_output=True, text=True)
    check("the lint passes the corpus", p.returncode == 0, p.stderr[-400:])
    r = L.run(corpus.all_filing_jsonld())
    check("it reads a non-trivial number of Prices", r["prices"] >= 1000, str(r["prices"]))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        test_nem1(Path(tmp))
        test_alternatives(Path(tmp))
        test_refusals(Path(tmp))
    test_corpus()
    print()
    if failures:
        print(f"{len(failures)} failure(s): {', '.join(failures)}")
        raise SystemExit(1)
    print("price cell lint: every guard fired and every allowed shape stayed clean")
