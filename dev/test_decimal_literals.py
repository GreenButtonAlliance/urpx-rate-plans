#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Tests for the XSD numeric literal lint.

Each case writes a small JSON-LD fixture, or an altered copy of a real filing,
into a temporary directory and asserts the lint's verdict on it.

Run: python3 dev/test_decimal_literals.py
"""
from __future__ import annotations

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
    "lint_decimal_literals", REPO / "dev" / "lint_decimal_literals.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

LINT = REPO / "dev" / "lint_decimal_literals.py"
failures: list[str] = []

CONTEXT = {
    "urpx": "https://urpx.org/ns/ontology/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "ex": "https://example.org/",
    "urpx:unitPrice": {"@type": "xsd:decimal"},
    "price": {"@id": "urpx:unitPrice", "@type": "xsd:decimal"},
    "urpx:serviceTierNumber": {"@type": "xsd:nonNegativeInteger"},
    "ex:ratio": {"@type": "http://www.w3.org/2001/XMLSchema#double"},
}


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}{': ' + detail if detail else ''}")
        failures.append(name)


def write(tmp: Path, name: str, text: str) -> Path:
    p = tmp / name
    p.write_text(text)
    return p


def doc(*nodes: dict, context=None) -> str:
    return json.dumps({"@context": CONTEXT if context is None else context, "@graph": list(nodes)})


def lexicals(tmp: Path, name: str, text: str) -> list[str]:
    r = L.run([write(tmp, name, text)], whole_corpus=False)
    return [f["lexical"] for f in r["findings"]]


def test_fixtures(tmp: Path) -> None:
    print("Fixtures")
    valid = ["1", "-1.50", "+0.00009", ".5", "5.", "-0.00000", "0"]
    got = lexicals(tmp, "valid.jsonld",
                   doc(*({"@id": f"ex:p{i}", "urpx:unitPrice": v} for i, v in enumerate(valid))))
    check("plain decimals pass, a leading '+' included", got == [], str(got))

    bad = ["-9e-05", "1E3", "1.5e+2", " 1.5", "1.5 ", "", "-", ".", "1,000.00", "INF", "NaN", "0x1A"]
    got = lexicals(tmp, "bad.jsonld",
                   doc(*({"@id": f"ex:p{i}", "urpx:unitPrice": v} for i, v in enumerate(bad))))
    check("exponent, whitespace and other forms fail as xsd:decimal", got == bad, str(got))

    got = lexicals(tmp, "alias.jsonld", doc({"@id": "ex:p", "price": "-9e-05"}))
    check("a term aliasing a coerced property is coerced", got == ["-9e-05"], str(got))

    got = lexicals(tmp, "uncoerced.jsonld", doc({"@id": "ex:p", "ex:note": "-9e-05"}))
    check("an uncoerced string is a plain string and passes", got == [], str(got))

    got = lexicals(tmp, "explicit.jsonld", doc(
        {"@id": "ex:a", "ex:v": {"@value": "-9e-05", "@type": "xsd:decimal"}},
        {"@id": "ex:b", "ex:v": {"@value": "-0.00009", "@type": "xsd:decimal"}},
        {"@id": "ex:c", "ex:v": {"@value": "7", "@type": "http://www.w3.org/2001/XMLSchema#integer"}},
        {"@id": "ex:d", "ex:v": {"@value": "7.0", "@type": "xsd:integer"}},
        {"@id": "ex:e", "urpx:unitPrice": {"@value": "1e3", "@type": "xsd:double"}}))
    check("an explicit {@value, @type} is judged by its own @type", got == ["-9e-05", "7.0"], str(got))

    got = lexicals(tmp, "native.jsonld", doc(
        {"@id": "ex:a", "urpx:unitPrice": 9e-05},
        {"@id": "ex:b", "urpx:unitPrice": 0.5},
        {"@id": "ex:c", "urpx:unitPrice": 3},
        {"@id": "ex:d", "ex:untyped": 0.5},
        {"@id": "ex:e", "ex:ratio": 0.5}))
    check("a native fraction under xsd:decimal coercion fails; an integer, an uncoerced "
          "number and a double coercion pass", got == ["9.0E-5", "5.0E-1"], str(got))

    got = lexicals(tmp, "integer.jsonld", doc(
        {"@id": "ex:a", "urpx:serviceTierNumber": "2"},
        {"@id": "ex:b", "urpx:serviceTierNumber": "-1"},
        {"@id": "ex:c", "urpx:serviceTierNumber": "2.0"},
        {"@id": "ex:d", "urpx:serviceTierNumber": "-0"}))
    check("an integer type checks digits and its value range", got == ["-1", "2.0"], str(got))

    got = lexicals(tmp, "double.jsonld", doc(
        *({"@id": f"ex:r{i}", "ex:ratio": v}
          for i, v in enumerate(["1e3", "-1.5E-2", "INF", "+INF", "NaN", "1e", "e3", "inf"]))))
    check("xsd:double admits exponents and INF/NaN only", got == ["1e", "e3", "inf"], str(got))

    got = lexicals(tmp, "nested.jsonld", doc(
        {"@id": "ex:a", "ex:has": {"@id": "ex:b", "ex:list": {"@list": [
            {"@id": "ex:c", "urpx:unitPrice": "1e-5"}]}}},
        {"@id": "ex:d", "@context": {"ex:local": {"@type": "xsd:decimal"}}, "ex:local": "2e-5"},
        {"@id": "ex:e", "ex:local": "3e-5"}))
    check("nested nodes, @list and an embedded context are honored", got == ["1e-5", "2e-5"], str(got))

    scoped = dict(CONTEXT, **{"ex:scope": {"@context": {"ex:inner": {"@type": "xsd:decimal"}}}})
    got = lexicals(tmp, "scoped.jsonld", doc(
        {"@id": "ex:a", "ex:scope": {"@id": "ex:b", "ex:inner": "4e-5"}},
        {"@id": "ex:c", "ex:inner": "5e-5"}, context=scoped))
    check("a property-scoped context applies under its property only", got == ["4e-5"], str(got))

    p = write(tmp, "cli.jsonld", doc({"@id": "ex:p", "urpx:unitPrice": "-9e-05"}))
    rc = subprocess.run([sys.executable, str(LINT), "--file", str(p)], capture_output=True).returncode
    check("the CLI exits 1 on an ill-typed literal", rc == 1, str(rc))

    p = write(tmp, "remote.jsonld", json.dumps({"@context": "https://example.org/ctx.jsonld"}))
    rc = subprocess.run([sys.executable, str(LINT), "--file", str(p)], capture_output=True).returncode
    check("a remote @context refuses (exit 3)", rc == 3, str(rc))


def test_planted(tmp: Path) -> None:
    print("\nA real filing")
    path = corpus.filing_path("sce", "nbt", "2025-04-23", "rate-plan-modifier")
    text = path.read_text()
    check("the filing is clean", lexicals(tmp, "sce-nbt.jsonld", text) == [])
    planted = text.replace('"urpx:unitPrice": "-0.00009"', '"urpx:unitPrice": "-9e-05"', 1)
    check("the plant took", planted != text)
    got = lexicals(tmp, "sce-nbt-planted.jsonld", planted)
    check("one exponent-form unitPrice in it fails", got == ["-9e-05"], str(got))


def test_corpus() -> None:
    print("\nThe live corpus")
    p = subprocess.run([sys.executable, str(LINT)], capture_output=True, text=True)
    check("the lint passes the corpus", p.returncode == 0, p.stderr[-400:])
    r = L.run(L.documents())
    check("it judges a non-trivial number of numeric literals", r["seen"] >= 10000, str(r["seen"]))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        test_fixtures(Path(tmp))
        test_planted(Path(tmp))
    test_corpus()
    print()
    if failures:
        print(f"{len(failures)} failure(s): {', '.join(failures)}")
        raise SystemExit(1)
    print("numeric literal lint: every ill-typed form failed and every valid form passed")
