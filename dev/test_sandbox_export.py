#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Tests for dev/export_sandbox.py and dev/check_sandbox_drift.py.

Exports PG&E E-TOU-C (both versions and their medical baseline modifiers) into a
minimal stand-in for a urpx-data-sandbox checkout under a temporary directory,
checks the tree, README, pull request body and [[sandbox]] record it produces,
then drives the drift check through each of its states against copies. Nothing
outside the temporary directory is written and nothing is fetched.

Run: python3 dev/test_sandbox_export.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402
import export_sandbox as X  # noqa: E402

DRIFT = REPO / "dev" / "check_sandbox_drift.py"
SCHEDULE = Path("us/ca/pge/electricity/e-tou-c")
DOCS = {
    "rate-plan_pge_e-tou-c_2026-03-01.jsonld",
    "rate-plan-modifier_pge_e-tou-c-medical-baseline_2026-03-01.jsonld",
    "rate-plan_pge_e-tou-c_2026-03-27.jsonld",
    "rate-plan-modifier_pge_e-tou-c-medical-baseline_2026-03-27.jsonld",
    "rate-plan_pge_e-tou-c_2026-06-01.jsonld",
    "rate-plan-modifier_pge_e-tou-c-medical-baseline_2026-06-01.jsonld",
}
# pge_rule-19_2023-03-23.pdf is vendored in every version directory and exported once.
PDFS = {"pge_e-tou-c_2026-03-01.pdf", "pge_e-tou-c_2026-03-27.pdf", "pge_e-tou-c_2026-06-01.pdf",
        "pge_rule-19_2023-03-23.pdf"}
COMMODITY_PATH = "submissions/us/us-ca/pge/electric"
SHA = "0123456789abcdef0123456789abcdef01234567"

# The sandbox's .github/PULL_REQUEST_TEMPLATE.md, as of its commit 55c7e5a.
# REUSE-IgnoreStart
PR_TEMPLATE = """\
<!-- SPDX-FileCopyrightText: The URPX Authors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

## Submission

**Utility:**

**Jurisdiction (utility and state):**

**Source document reference:** (vendor the document itself in this pull request, not only a link; state where it is placed and its capture date)

**Declared URPX version:** (the version this submission targets; gate 1 validates against that version's shapes)

**Built from a real, published dataset?** yes / no. If no, describe how the data was constructed.

**Effective dates:** (when the rate plan itself took effect)

**Service-period dates:** (the period the data covers, if different from the effective dates)

## Checklist

- [ ] The dataset lives under `submissions/<country>/<state>/<utility>/<commodity>/`.
- [ ] The source document is vendored alongside the dataset.
- [ ] The dataset declares the URPX version it targets.
- [ ] This is a dataset submission, not a proposed change to the ontology or SHACL shapes.

By opening this pull request you confirm the submission is licensed under the Community Data License Agreement - Permissive 2.0 (CDLA-Permissive-2.0), and that nothing in this repository is reviewed for data content, completeness, or accuracy beyond conformance to the declared URPX version.
"""
# REUSE-IgnoreEnd

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok or not detail else ': ' + detail}")
    if not ok:
        failures.append(name)


def make_sandbox(root: Path) -> Path:
    (root / "submissions").mkdir(parents=True)
    (root / ".github").mkdir()
    (root / ".github" / "PULL_REQUEST_TEMPLATE.md").write_text(PR_TEMPLATE)
    (root / "README.md").write_text("# urpx-data-sandbox\n")
    return root


def make_corpus(root: Path) -> Path:
    """A copy of the E-TOU-C schedule and PG&E's utility.toml under root/us/."""
    shutil.copytree(REPO / SCHEDULE, root / SCHEDULE)
    shutil.copyfile(REPO / "us/ca/pge/utility.toml", root / "us/ca/pge/utility.toml")
    return root


def drift(corpus_root: Path, sandbox: Path | None, env_path: str | None = None):
    env = dict(os.environ)
    env.pop("URPX_SANDBOX_CHECKOUT", None)
    if env_path is not None:
        env["PATH"] = env_path
    cmd = [sys.executable, str(DRIFT), "--root", str(corpus_root)]
    if sandbox is not None:
        cmd += ["--sandbox", str(sandbox)]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def reported(out: str, state: str, doc: str | None = None) -> int:
    """How many lines report `state`, for `doc` when given."""
    name = re.escape(doc) if doc else r"\S+"
    pat = re.compile("^  " + re.escape(state) + " +" + name + r"(  \(|$)")
    return sum(1 for line in out.splitlines() if pat.match(line))


def test_export(tmp: Path) -> None:
    print("export, commodity layout")
    sb = make_sandbox(tmp / "sb-commodity")
    sub = X.export([REPO / SCHEDULE], sb, "commodity")
    target = sb / COMMODITY_PATH
    check("lands at the sandbox's documented depth", sub.rel_path == COMMODITY_PATH, sub.rel_path)
    names = {p.name for p in target.iterdir()}
    check("writes every document, every PDF and a README",
          names == DOCS | PDFS | {"README.md"}, str(sorted(names)))
    check("copies every document byte for byte",
          all((target / p.name).read_bytes() == p.read_bytes()
              for p in (REPO / SCHEDULE).glob("versions/*/*.jsonld")))
    readme = (target / "README.md").read_text()
    for needle, what in [
        ("Pacific Gas and Electric Company", "the utility's name from utility.toml"),
        ("California (`us-ca`)", "the jurisdiction"),
        ("https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_SCHEDS_E-TOU-C.pdf", "the source URL"),
        ("2026-04-26", "the first capture date"),
        ("2026-04-28", "the second capture date"),
        ("0.5.1", "the declared URPX version"),
        ("Built from a real, published dataset:** yes", "the real-dataset answer"),
        ("from 2026-03-01, until 2026-03-27", "the superseded version's service period"),
        ("[repository README](../../../../../README.md)", "the disclaimer link"),
        # REUSE-IgnoreStart
        ("SPDX-License-Identifier: Apache-2.0", "the README license header"),
        # REUSE-IgnoreEnd
    ]:
        check(f"README carries {what}", needle in readme)
    check("README's disclaimer link resolves", (target / "../../../../../README.md").resolve().is_file())
    check("README has no em-dash", "\u2014" not in readme)

    body = X.pr_body(sub, PR_TEMPLATE, "commodity")
    check("PR body fills every field", "(the version this submission targets" not in body
          and "yes / no" not in body and "**Utility:** Pacific Gas and Electric Company (PG&E)" in body)
    check("PR body drops the template's SPDX comment", "SPDX" not in body)
    check("PR body names where each PDF is placed",
          all(f"`{COMMODITY_PATH}/{p}`" in body for p in PDFS))
    check("PR body ticks all four checklist items", body.count("- [x] ") == 4)
    try:
        X.pr_body(sub, PR_TEMPLATE.replace("**Effective dates:**", "**Dates:**"), "commodity")
        check("a template missing a field is refused", False)
    except X.ExportError:
        check("a template missing a field is refused", True)

    print("export, schedule layout")
    sb2 = make_sandbox(tmp / "sb-schedule")
    sub2 = X.export([REPO / SCHEDULE / "versions/2026-03-01", REPO / SCHEDULE / "versions/2026-03-27",
                     REPO / SCHEDULE / "versions/2026-06-01"], sb2, "schedule")
    t2 = sb2 / sub2.rel_path
    check("adds the schedule level", sub2.rel_path == COMMODITY_PATH + "/e-tou-c", sub2.rel_path)
    check("writes the same files", {p.name for p in t2.iterdir()} == DOCS | PDFS | {"README.md"})
    link = "../" * 6 + "README.md"
    check("disclaimer link resolves one level deeper",
          link in (t2 / "README.md").read_text() and (t2 / link).resolve().is_file())
    check("PR body leaves the depth checklist item unticked",
          X.pr_body(sub2, PR_TEMPLATE, "schedule").count("- [x] ") == 3)

    print("export refusals")
    (target / "someone-elses.jsonld").write_text("{}")
    try:
        X.export([REPO / SCHEDULE], sb, "commodity")
        check("refuses a target holding files it does not write", False)
    except X.ExportError:
        check("refuses a target holding files it does not write", True)
    X.export([REPO / SCHEDULE], sb, "commodity", replace=True)
    check("--replace clears the target first", not (target / "someone-elses.jsonld").exists())
    try:
        X.export([REPO / SCHEDULE, REPO / "us/ca/pge/electricity/e-elec"], make_sandbox(tmp / "sb3"), "schedule")
        check("schedule layout refuses two schedules", False)
    except X.ExportError:
        check("schedule layout refuses two schedules", True)


def test_record_and_drift(tmp: Path) -> None:
    print("record")
    root = make_corpus(tmp / "corpus")
    sb = make_sandbox(tmp / "sb-drift")
    sub = X.export([root / SCHEDULE], sb, "commodity")
    manifests = []
    for f in sub.filings:
        m = f.dir / corpus.TARIFF_MANIFEST
        before = corpus.load_toml(m)
        X.write_record(m, X.record_for(f, sub.rel_path, SHA, "2026-10-05"))
        after = corpus.load_toml(m)
        check(f"{f.date}: record leaves the rest of the manifest alone",
              {k: v for k, v in after.items() if k != "sandbox"} == before)
        check(f"{f.date}: record names each document of the filing",
              set(after["sandbox"][0]["rdf_sha256"]) == {d.path.name for d in f.documents})
        manifests.append(m)

    import jsonschema
    schema = json.loads((REPO / "schema/tariff-manifest.schema.json").read_text())
    try:
        for m in manifests:
            jsonschema.validate(corpus.load_toml(m), schema)
        check("recorded manifests validate against the schema", True)
    except jsonschema.ValidationError as e:
        check("recorded manifests validate against the schema", False, e.message)
    bad = corpus.load_toml(manifests[0])
    bad["sandbox"][0]["rdf_sha256"] = {"x.jsonld": "not-a-hash"}
    try:
        jsonschema.validate(bad, schema)
        check("the schema rejects a malformed record", False)
    except jsonschema.ValidationError:
        check("the schema rejects a malformed record", True)

    m = manifests[0]
    text = m.read_text().replace(f'exported_on   = "2026-10-05"',
                                 f'exported_on   = "2026-10-05"\npr            = 7\nmerge_commit  = "{SHA}"')
    m.write_text(text)
    f0 = sub.filings[0]
    X.write_record(m, X.record_for(f0, sub.rel_path, "f" * 40, "2026-10-06"))
    recs = corpus.load_toml(m)["sandbox"]
    check("re-export replaces the record for the same path", len(recs) == 1, str(len(recs)))
    check("re-export keeps pr and drops merge_commit",
          recs[0].get("pr") == 7 and "merge_commit" not in recs[0] and recs[0]["exported_from"] == "f" * 40)
    X.write_record(m, {**X.record_for(f0, sub.rel_path, SHA, "2026-10-06"), "path": "submissions/x"})
    check("a second sandbox path adds a second record", len(corpus.load_toml(m)["sandbox"]) == 2)
    # Put the manifest back to one record for the drift states below.
    m.write_text(m.read_text().split("\n" + X.SANDBOX_BANNER)[0].rstrip("\n") + "\n")
    X.write_record(m, X.record_for(f0, sub.rel_path, SHA, "2026-10-05"))

    print("drift")
    target = sb / sub.rel_path
    rc, out = drift(root, sb)
    check("unchanged: exit 0", rc == 0, out)
    check("unchanged: every document reported unchanged", reported(out, "unchanged") == len(DOCS), out)

    work = tmp / "sb-work"
    shutil.copytree(sb, work)
    d = work / sub.rel_path / "rate-plan_pge_e-tou-c_2026-03-27.jsonld"
    d.write_text(json.dumps(json.loads(d.read_text()), indent=1, sort_keys=True))
    rc, out = drift(root, work)
    check("a reformatted sandbox copy is still unchanged", rc == 0, out)

    d.write_text(d.read_text().replace('"0.20782"', '"0.20783"', 1))
    rc, out = drift(root, work)
    check("changed in sandbox: exit 1", rc == 1, out)
    check("changed in sandbox: named", reported(out, "changed in sandbox", "rate-plan_pge_e-tou-c_2026-03-27.jsonld") == 1, out)

    shutil.rmtree(work)
    shutil.copytree(sb, work)
    here = root / SCHEDULE / "versions/2026-03-01/rate-plan_pge_e-tou-c_2026-03-01.jsonld"
    original = here.read_text()
    here.write_text(original.replace('"0.20782"', '"0.20783"', 1))
    rc, out = drift(root, work)
    check("changed here: exit 1", rc == 1, out)
    check("changed here: named", reported(out, "changed here", "rate-plan_pge_e-tou-c_2026-03-01.jsonld") == 1, out)
    work_doc = work / sub.rel_path / "rate-plan_pge_e-tou-c_2026-03-01.jsonld"
    work_doc.write_text(work_doc.read_text().replace('"0.20782"', '"0.20784"', 1))
    rc, out = drift(root, work)
    check("changed in both: named",
          reported(out, "changed in both", "rate-plan_pge_e-tou-c_2026-03-01.jsonld") == 1, out)
    here.write_text(original)

    (work / sub.rel_path / "rate-plan_pge_e-tou-c_2026-03-27.jsonld").unlink()
    rc, out = drift(root, work)
    check("missing in sandbox: exit 1", rc == 1, out)
    check("missing in sandbox: named",
          reported(out, "missing in sandbox",
                   "rate-plan_pge_e-tou-c_2026-03-27.jsonld") == 1, out)

    rc, out = drift(root, None, env_path="/nonexistent")
    check("unreachable: exit 3", rc == 3, out)
    check("unreachable: every document named as skipped", reported(out, "skipped") == len(DOCS), out)

    bare = make_corpus(tmp / "bare")
    rc, out = drift(bare, sb)
    check("no records: exit 0 and says so", rc == 0 and "no sandbox records" in out, out)
    rc, out = drift(tmp / "empty-root", sb)
    check("no manifests: refuses with exit 3", rc == 3, out)


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        test_export(tmp)
        test_record_and_drift(tmp)
    print(f"{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
