#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Tests for the cross-filing lint.

Each case copies real filings, or writes a small fixture, into a corpus-shaped
tree in a temporary directory, breaks one thing, and asserts the lint's verdict.

Run: python3 dev/test_cross_filing.py
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
    "lint_cross_filing", REPO / "dev" / "lint_cross_filing.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

LINT = REPO / "dev" / "lint_cross_filing.py"
failures: list[str] = []

# A base plan and the modifier its own PDF prices, filed in the base's directory.
BASE = corpus.filing_path("sce", "tou-d-4-9pm", "2025-11-15")
MODIFIER = BASE.parent / "rate-plan-modifier_sce_tou-d-4-9pm-hpwh_2025-11-15.jsonld"
DIR = Path("us/ca/sce/electricity/tou-d-4-9pm/versions/2025-11-15")


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}{': ' + detail if detail else ''}")
        failures.append(name)


def tree(tmp: Path, name: str, files: dict[str, object]) -> tuple[Path, list[Path]]:
    """A corpus-shaped tree under tmp/name; files maps a path relative to it to a
    parsed document."""
    root = tmp / name
    out = []
    for rel, doc in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc))
        out.append(p)
    return root, out


def whys(tmp: Path, name: str, files: dict[str, object], check_name: str | None = None) -> list[str]:
    root, paths = tree(tmp, name, files)
    r = L.run([(p, L.kind_of(p)) for p in paths], root, whole_corpus=False)
    return [f["why"] for f in r["findings"] if check_name in (None, f["check"])]


def real(path: Path) -> dict:
    return json.loads(path.read_text())


def pair() -> dict[str, object]:
    return {str(DIR / BASE.name): real(BASE), str(DIR / MODIFIER.name): real(MODIFIER)}


def top(doc: dict, has: str) -> dict:
    return L.one(L.package_of(doc)[has])


def fixture(*nodes: dict) -> dict:
    return {"@context": {"urpx": "https://urpx.org/ns/ontology/",
                         "sce": "https://rate-plans.grid-coordination.energy/sce/"},
            "@graph": list(nodes)}


def test_references(tmp: Path) -> None:
    print("References")
    got = whys(tmp, "clean", pair())
    check("a base and the modifier filed with it are clean", got == [], str(got))

    got = whys(tmp, "alone", {str(DIR / MODIFIER.name): real(MODIFIER)}, "references")
    check("the modifier without its base leaves the base plan unresolved",
          any(w.endswith("/sce/tou-d-4-9pm, which no filing defines") for w in got), str(got[:3]))

    files = pair()
    rp = top(files[str(DIR / BASE.name)], "urpx:hasRatePlan")
    rp["urpx:planned"] = {"@id": "sce:no-such-node"}
    got = whys(tmp, "planted", files)
    check("one planted dangling reference is the one finding",
          got == [f"references {L.IRI_ROOT}sce/no-such-node, which no filing defines"], str(got))

    got = whys(tmp, "outside", {"x.jsonld": fixture(
        {"@id": "sce:a", "urpx:p": [{"@id": "urpx:SomeTerm"}, {"@id": "https://example.org/x"},
                                     {"@id": "urn:x:y"}]})}, "references")
    check("urpx: terms and IRIs outside the corpus namespace are not checked", got == [], str(got))

    got = whys(tmp, "unbound", {"x.jsonld": fixture({"@id": "sce:a", "urpx:p": {"@id": "zzz:b"}})},
               "references")
    check("an @id whose prefix is unbound is a finding",
          got == ["@id 'zzz:b' uses a prefix the @context does not bind"], str(got))

    got = whys(tmp, "typed", {"x.jsonld": fixture(
        {"@id": "sce:a", "urpx:p": [{"@id": "sce:b"}, {"@id": "sce:c"}]},
        {"@id": "sce:b", "@type": "urpx:Prices"},
        {"@id": "sce:c"})}, "references")
    check("an @id with @type alone defines; a bare @id does not",
          got == [f"references {L.IRI_ROOT}sce/c, which no filing defines"], str(got))

    root, paths = tree(tmp, "coerced", {"x.jsonld": dict(
        fixture({"@id": "sce:a"}), **{"@context": {"sce:ref": {"@type": "@id"}}})})
    rc = subprocess.run([sys.executable, str(LINT), "--root", str(root), "--file", *map(str, paths)],
                        capture_output=True).returncode
    check("a term coerced to @id refuses (exit 3)", rc == 3, str(rc))

    root, paths = tree(tmp, "embedded", {"x.jsonld": fixture(
        {"@id": "sce:a", "urpx:p": {"@context": {}, "@id": "sce:b"}})})
    rc = subprocess.run([sys.executable, str(LINT), "--root", str(root), "--file", *map(str, paths)],
                        capture_output=True).returncode
    check("an embedded @context refuses (exit 3)", rc == 3, str(rc))


def test_alignment(tmp: Path) -> None:
    print("\nAlignment")
    b, m = str(DIR / BASE.name), str(DIR / MODIFIER.name)

    def altered(name: str, edit, files=None) -> list[str]:
        files = files or pair()
        edit(files)
        return whys(tmp, name, files, "alignment")

    got = altered("date", lambda f: f.update({b.replace("_2025-11-15", "_2025-11-16"): f.pop(b)}))
    check("a file name dated off its directory fails",
          "file name's date 2025-11-16 is not the directory's 2025-11-15" in got, str(got))

    got = altered("utility", lambda f: f.update({b.replace("_sce_", "_pge_"): f.pop(b)}))
    check("a file name naming another utility fails",
          "file name's utility 'pge' is not the directory's 'sce'" in got, str(got))

    got = altered("dirname", lambda f: f.update({b.replace("tou-d-4-9pm/", "tou-d-5-8pm/"): f.pop(b)}))
    check("a base plan in another schedule's directory fails",
          "slug 'tou-d-4-9pm' is not the directory's schedule 'tou-d-5-8pm'" in got, str(got))

    def set_version(f):
        L.one(top(f[b], "urpx:hasRatePlan")["urpx:hasRatePlanVersion"])["@id"] = "sce:tou-d-4-9pm-2025-11-16"
    got = altered("version", set_version)
    check("a version @id dated off its directory fails",
          got == ["version @id 'sce:tou-d-4-9pm-2025-11-16' is not sce:tou-d-4-9pm-2025-11-15"], str(got))

    got = altered("top", lambda f: top(f[b], "urpx:hasRatePlan").update({"@id": "sce:tou-d-5-8pm"}))
    check("a RatePlan @id naming another schedule fails",
          got == ["urpx:RatePlan @id 'sce:tou-d-5-8pm' is not sce:tou-d-4-9pm"], str(got))

    got = altered("package", lambda f: L.package_of(f[b]).update({"@id": "sce:doc-x"}))
    check("a package @id off the convention fails",
          got == ["package @id 'sce:doc-x' is not sce:doc-tou-d-4-9pm-2025-11-15"], str(got))

    got = altered("prefix", lambda f: f[b]["@context"].update({"sce": f"{L.IRI_ROOT}pge/"}))
    check("a utility prefix bound off the namespace fails",
          f"prefix 'sce' is not bound to {L.IRI_ROOT}sce/" in got, str(got))

    got = altered("nobase", lambda f: f.pop(b))
    check("a modifier with its own slug but no base in the directory fails",
          got == ["modifier 'tou-d-4-9pm-hpwh' sits in tou-d-4-9pm/ but the directory holds no "
                  "rate-plan_sce_tou-d-4-9pm_2025-11-15.jsonld"], str(got))

    def unapply(f):
        v = L.one(top(f[m], "urpx:hasRatePlanModifier")["urpx:hasRatePlanModifierVersion"])
        v["urpx:applicableToRatePlan"] = [{"@id": "sce:tou-d-5-8pm"}]
    got = altered("unapplied", unapply)
    check("a modifier with its own slug that does not apply to the base fails",
          got == ["modifier 'tou-d-4-9pm-hpwh' sits in tou-d-4-9pm/ but its version does not name "
                  "sce:tou-d-4-9pm in urpx:applicableToRatePlan"], str(got))

    files = {b.replace("tou-d-4-9pm", "tou-d-5-8pm"): copy.deepcopy(real(BASE)),
             m.replace("tou-d-4-9pm/", "tou-d-5-8pm/"): real(MODIFIER)}
    got = whys(tmp, "foreign", files, "alignment")
    check("a modifier whose slug does not extend the directory's schedule fails",
          "modifier slug 'tou-d-4-9pm-hpwh' neither is nor extends the directory's schedule "
          "'tou-d-5-8pm'" in got, str(got))

    root, paths = tree(tmp, "kind", {b: real(BASE)})
    r = L.run([(paths[0], "rate-plan-modifier")], root, whole_corpus=False)
    got = [f["why"] for f in r["findings"]]
    check("a file name disagreeing with the kind corpus.json found it as fails",
          "file name says rate-plan, corpus.json found it as rate-plan-modifier" in got, str(got))

    root, paths = tree(tmp, "cli", {b: real(BASE), m.replace("hpwh", "hpwh-x"): real(MODIFIER)})
    rc = subprocess.run([sys.executable, str(LINT), "--root", str(root), "--file", *map(str, paths)],
                        capture_output=True).returncode
    check("the CLI exits 1 on a misaligned filing", rc == 1, str(rc))


def test_corpus() -> None:
    print("\nThe live corpus")
    p = subprocess.run([sys.executable, str(LINT)], capture_output=True, text=True)
    check("the lint passes the corpus", p.returncode == 0, p.stderr[-400:])
    r = L.run(L.corpus_paths())
    check("it resolves a non-trivial number of references", r["referenced"] >= 1000, str(r["referenced"]))
    check("it aligns every document corpus.json lists",
          r["documents"] == len(corpus.all_filing_jsonld()), str(r["documents"]))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        test_references(Path(tmp))
        test_alignment(Path(tmp))
    test_corpus()
    print()
    if failures:
        print(f"{len(failures)} failure(s): {', '.join(failures)}")
        raise SystemExit(1)
    print("cross-filing lint: every planted break was found and the corpus is clean")
