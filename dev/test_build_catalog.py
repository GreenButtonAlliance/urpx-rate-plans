#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Tests for dev/build_catalog.py.

Each failure case runs the generator in a temporary copy holding the walker,
the generator, the catalog schema and three filings (PG&E E-TOU-C 2026-03-01
with two documents and 2026-03-27, and CPAU E-1-TOU 2026-01-01 with three
sources),
breaks one thing, and requires a non-zero exit whose output names the file. The
last case reads the committed catalog with SPARQL and requires the filings it
dates as current at dev/currency-instant.json to be the ones
dev/scenario_cost_models.py derives.

Run: python3 dev/test_build_catalog.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))

COPY = [
    "corpus.json",
    "dev/corpus.py",
    "dev/utilities.py",
    "dev/build_catalog.py",
    "catalog/corpus.schema.json",
    "us/ca/pge/utility.toml",
    "us/ca/pge/electricity/e-tou-c/versions/2026-03-01",
    "us/ca/pge/electricity/e-tou-c/versions/2026-03-27",
    "us/ca/cpau/utility.toml",
    "us/ca/cpau/electricity/e-1-tou/versions/2026-01-01",
]
ETOUC = "us/ca/pge/electricity/e-tou-c/versions"
E1TOU = "us/ca/cpau/electricity/e-1-tou/versions/2026-01-01"

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok or not detail else ': ' + detail}")
    if not ok:
        failures.append(name)


def tree(tmp: Path) -> Path:
    root = tmp / "repo"
    for item in COPY:
        src, dst = REPO / item, root / item
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("extracted"))
        else:
            shutil.copy2(src, dst)
    return root


def run(root: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "dev/build_catalog.py", *args], cwd=root,
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def fails_naming(name: str, root: Path, args: tuple, *needles: str) -> None:
    before = (root / "catalog/corpus.jsonld").read_bytes() if (root / "catalog/corpus.jsonld").exists() else None
    rc, out = run(root, *args)
    missing = [n for n in needles if n not in out]
    check(name, rc != 0 and not missing, f"exit {rc}, output lacks {missing}: {out.strip()[-400:]}")
    if args == ():
        after = (root / "catalog/corpus.jsonld").read_bytes() if (root / "catalog/corpus.jsonld").exists() else None
        check(f"{name}: nothing written", before == after)


def main() -> int:
    print("dev/build_catalog.py")
    with tempfile.TemporaryDirectory() as t:
        root = tree(Path(t))
        rc, out = run(root)
        check("a sound tree builds", rc == 0 and "(3 filings)" in out, out.strip())
        rc, out = run(root, "--check")
        check("and checks clean", rc == 0, out.strip())

        manifest = root / E1TOU / "tariff.toml"
        text = manifest.read_text()
        manifest.write_text(re.sub(r'(?m)^\s*retrieved_on = "2026-04-30"\n', "", text, count=1))
        fails_naming("a [source] entry without retrieved_on fails", root, (),
                     f"{E1TOU}/tariff.toml", "retrieved_on")
        manifest.write_text(re.sub(r"(?m)^complete = .*\n", "", text))
        fails_naming("a manifest without [modeling].complete fails", root, (),
                     f"{E1TOU}/tariff.toml", "[modeling].complete")
        manifest.write_text(text)

        doc = root / ETOUC / "2026-03-27/rate-plan_pge_e-tou-c_2026-03-27.jsonld"
        good = doc.read_bytes()
        doc.write_text('{"@context": {"urpx": "https://urpx.org/ns/ontology/"}, "@graph": [')
        fails_naming("an unparseable document fails", root, (), doc.relative_to(root).as_posix(),
                     "does not parse")
        doc.write_bytes(good)

        pdf = root / ETOUC / "2026-03-27/pge_e-tou-c_2026-03-27.pdf"
        good = pdf.read_bytes()
        pdf.write_bytes(good + b"\n")
        fails_naming("a vendored PDF whose sha256 no [source] declares fails", root, (),
                     pdf.relative_to(root).as_posix(), "sha256")
        pdf.write_bytes(good)

        nse = root / E1TOU / "cpau_e-nse-1_2025-09-01.pdf"
        nse_bytes = nse.read_bytes()
        nse.unlink()
        fails_naming("a [source] entry with no file fails", root, (),
                     f"{E1TOU}/tariff.toml", "no vendored file has the sha256")
        cited = re.sub(r'(?m)^(  sha256 = "c07362c5[0-9a-f]+"\n)', r'\1  vendored = false\n', text, count=1)
        manifest.write_text(cited)
        rc, out = run(root)
        check("a [source] entry with vendored = false and no file builds",
              rc == 0 and "(3 filings)" in out, out.strip())
        nse.write_bytes(nse_bytes)
        fails_naming("a [source] entry with vendored = false whose file is present fails", root, (),
                     f"{E1TOU}/tariff.toml", "vendored = false")
        manifest.write_text(text)
        rc, out = run(root)
        check("and restoring the entry builds", rc == 0, out.strip())

        shutil.rmtree(root / ETOUC / "2026-03-27")
        fails_naming("a removed filing fails --check", root, ("--check",),
                     f"in the committed catalog, not in the corpus: ../{ETOUC}/2026-03-27/")
        rc, out = run(root)
        check("and a rebuild drops it", rc == 0 and "(2 filings)" in out, out.strip())

    current_agrees()
    print()
    if failures:
        print(f"{len(failures)} failed: {failures}")
        return 1
    print("All catalog tests passed.")
    return 0


CURRENT = """
PREFIX dcat: <http://www.w3.org/ns/dcat#>
PREFIX dcterms: <http://purl.org/dc/terms/>
SELECT ?path WHERE {
  ?filing a dcat:Dataset ; dcat:inSeries ?schedule ; dcterms:identifier ?path ;
          dcterms:temporal ?t .
  ?t dcat:startDate ?start .
  FILTER (?start <= ?at)
  FILTER NOT EXISTS { ?t dcat:endDate ?end . FILTER (?end <= ?at) }
  FILTER NOT EXISTS {
    ?later dcat:inSeries ?schedule ; dcterms:temporal/dcat:startDate ?s2 .
    FILTER (?s2 > ?start && ?s2 <= ?at)
  }
}"""


def current_agrees() -> None:
    """The committed catalog's dates give the same current filings as the
    reports, judged by each filing's own (primary) version."""
    import corpus
    import scenario_cost_models as S
    from rdflib import XSD, Graph, Literal

    at = S.currency_instant()
    local = Literal(at.astimezone(S.CORPUS_ZONE).replace(tzinfo=None).isoformat(), datatype=XSD.dateTime)
    catalog = REPO / "catalog" / "corpus.jsonld"
    g = Graph()
    g.parse(catalog, format="json-ld", publicID=catalog.as_uri())
    from_catalog = {str(r.path) for r in g.query(CURRENT, initBindings={"at": local})}

    versions = S.collect_versions()
    gone = S.derive_supersession(versions, at) | S.not_yet_effective(versions, at)
    from_reports = set()
    for vid, v in versions.items():
        if vid in gone or not v["home"]:
            continue
        home = REPO / v["home"]
        _u, schedule, _d = corpus.parse_filing_path(home)
        if v["slug"] == schedule:
            from_reports.add(home.parent.relative_to(REPO).as_posix())
    check(f"SPARQL over the catalog finds the {len(from_reports)} current filings the reports derive",
          from_catalog == from_reports,
          f"catalog only {sorted(from_catalog - from_reports)}, reports only {sorted(from_reports - from_catalog)}")


if __name__ == "__main__":
    raise SystemExit(main())
