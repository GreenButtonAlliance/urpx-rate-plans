#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Negative tests for the price-layer condition lint.

Each case copies a real filing's documents into a temporary directory, alters
them, and asserts the lint's verdict on the copy. Every guard is made to fire,
and each place a condition may live is checked to stay clean.

Run: python3 dev/test_price_layer_conditions.py
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
    "lint_price_layer_conditions", REPO / "dev" / "lint_price_layer_conditions.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

LINT = REPO / "dev" / "lint_price_layer_conditions.py"
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


def rule(rid: str) -> dict:
    return {"@type": "urpx:ApplicabilityRule", "@id": rid,
            "urpx:hasConditionExpression": {
                "@type": "urpx:ConditionExpression", "@id": f"{rid}-cx",
                "urpx:rootNode": {
                    "@type": "urpx:ComparisonNode", "@id": f"{rid}-cn",
                    "urpx:operator": {"@id": "urpx:equalsOperator"},
                    "urpx:leftOperand": {"@type": "urpx:CustomOperandNode", "@id": f"{rid}-l",
                                         "urpx:customConditionProperty": "planted"},
                    "urpx:rightOperand": {"@type": "urpx:CustomOperandNode", "@id": f"{rid}-r",
                                          "urpx:stringValue": "x"}}}}


def failing(*paths: Path, **kw) -> dict:
    return L.failing(L.run(list(paths), whole_corpus=False, **kw))


def cli(*paths: Path) -> int:
    return subprocess.run([sys.executable, str(LINT), "--file", *map(str, paths)],
                          capture_output=True, text=True).returncode


def test_planted(tmp: Path) -> None:
    print("\nPlanted conditions on a converted filing (cpau e-3)")
    e3 = document("cpau", "e-3", "2007-07-01")
    p = write(tmp, "e3.jsonld", e3)
    check("e-3 as converted carries no price-layer condition", failing(p) == {}, str(failing(p)))
    check("CLI passes it", cli(p) == 0)
    alts = list(nodes(e3, "urpx:ProfileAlternative"))
    owners = [f["owner"][0] for f in L.scan("e3", e3)]
    check("its four ProfileAlternatives own 16 CustomOperandNodes, none of them price-layer",
          len(alts) == 4 and owners.count("urpx:ProfileAlternative") == 16, str(owners))

    for t, name in (("urpx:Price", "Price"), ("urpx:PriceSetAlternative", "PriceSetAlternative"),
                    ("urpx:PriceDefinition", "PriceDefinition")):
        doc = copy.deepcopy(e3)
        next(nodes(doc, t))["urpx:hasApplicabilityRule"] = rule(f"ex:planted-{name}")
        q = write(tmp, f"e3-{name}.jsonld", doc)
        f = failing(q)
        check(f"a rule planted on a {name} FAILS, attributed to cpau:e-3-2007-07-01",
              list(f) == ["cpau:e-3-2007-07-01"] and len(f["cpau:e-3-2007-07-01"]) == 2, str(f))
        check(f"CLI exits 1 on the {name} case", cli(q) == 1)

    doc = copy.deepcopy(e3)
    doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]["urpx:hasPrices"]["urpx:hasPriceSet"] = [{
        "@type": "urpx:PriceSet", "@id": "ex:ps",
        "urpx:hasApplicabilityGroup": {"@type": "urpx:ApplicabilityGroup", "@id": "ex:ag",
                                       "urpx:hasConditionExpression":
                                           rule("ex:ag-r")["urpx:hasConditionExpression"]}}]
    q = write(tmp, "e3-priceset.jsonld", doc)
    check("an ApplicabilityGroup on a PriceSet, the shape e-3 had, FAILS",
          len(failing(q).get("cpau:e-3-2007-07-01", {})) == 2, str(failing(q)))

    doc = copy.deepcopy(e3)
    next(nodes(doc, "urpx:RatePlanVersion"))["urpx:hasEligibilityRule"] = [
        dict(rule("ex:elig"), **{"@type": "urpx:EligibilityRule"})]
    q = write(tmp, "e3-eligibility.jsonld", doc)
    check("a condition on an EligibilityRule passes", failing(q) == {}, str(failing(q)))

    doc = copy.deepcopy(e3)
    next(nodes(doc, "urpx:Price"))["urpx:hasApplicabilityRule"] = rule("ex:x")
    q = write(tmp, "e3-allowed.jsonld", doc)
    check("an allowlisted version's price-layer condition passes",
          failing(q, allowlist={"cpau:e-3-2007-07-01": "test"}) == {})


def test_stale(tmp: Path) -> None:
    print("\nAllowlist entries")
    p = write(tmp, "rsmart.jsonld", document("pge", "e-rsmart", "2025-10-31", "rate-plan-modifier"))
    r = L.run([p], whole_corpus=False, check_stale=True,
              allowlist={"pge:e-rsmart-2025-10-31": "x"})
    check("e-rsmart's entry is live (4 operands)", r["stale"] == {} and
          len(r["layer"]["pge:e-rsmart-2025-10-31"]) == 4, str(r["stale"]))
    doc = document("pge", "e-rsmart", "2025-10-31", "rate-plan-modifier")
    for price in nodes(doc, "urpx:Price"):
        price.pop("urpx:hasApplicabilityRule", None)
    q = write(tmp, "rsmart-clean.jsonld", doc)
    r = L.run([q], whole_corpus=False, check_stale=True, allowlist={"pge:e-rsmart-2025-10-31": "x"})
    check("an entry whose version no longer carries one is STALE",
          "pge:e-rsmart-2025-10-31" in r["stale"], str(r["stale"]))
    r = L.run([p], whole_corpus=False, check_stale=True,
              allowlist={"pge:e-rsmart-2025-10-31": "x", "ex:gone-2020-01-01": "x"})
    check("an entry naming a version no document defines is STALE",
          list(r["stale"]) == ["ex:gone-2020-01-01"], str(r["stale"]))


def test_refusals(tmp: Path) -> None:
    print("\nRefusals")
    check("an empty file list refuses",
          subprocess.run([sys.executable, "-c",
                          f"import sys; sys.path.insert(0, {str(REPO / 'dev')!r}); "
                          "import lint_price_layer_conditions as L; L.run([])"],
                         capture_output=True).returncode != 0)
    p = write(tmp, "bare.jsonld", {"@type": "urpx:URPXPackage"})
    try:
        L.run([p], whole_corpus=True)
        check("a corpus with no CustomOperandNode refuses", False)
    except L.Refused:
        check("a corpus with no CustomOperandNode refuses", True)


def test_corpus() -> None:
    print("\nThe live corpus")
    p = subprocess.run([sys.executable, str(LINT)], capture_output=True, text=True)
    check("the lint passes the corpus", p.returncode == 0, p.stderr[-400:])
    r = L.run(corpus.all_filing_jsonld())
    check("exactly the two allowlisted versions carry price-layer conditions",
          sorted(r["layer"]) == sorted(L.ALLOWLIST), str(sorted(r["layer"])))
    check("it scans a non-trivial number of CustomOperandNodes", r["found"] >= 500, str(r["found"]))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        test_planted(Path(tmp))
        test_stale(Path(tmp))
        test_refusals(Path(tmp))
    test_corpus()
    print()
    if failures:
        print(f"{len(failures)} failure(s): {', '.join(failures)}")
        raise SystemExit(1)
    print("price-layer condition lint: every guard fired and every allowed place stayed clean")
