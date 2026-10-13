#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Tests for dev/gate-steps.toml: it names every gate step and nothing else.

Every `note` step in dev/gate.sh appears as a [[gate]] entry whose modes are
the gate.sh branches that run it, and every dev/check_all.py STEPS entry as a
[[check_all]] entry; every entry names a real step. Then the selection for a
set of changed paths, and the refusals of dev/gate.sh --changed.

Run: python3 dev/test_gate_steps.py
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import check_all  # noqa: E402
import gate_steps  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok or not detail else ': ' + detail}")
    if not ok:
        failures.append(name)


NOTE = re.compile(r'(?<![\w-])note "([^"]+)"')


def gate_sh_steps(text: str) -> dict[str, set[str]]:
    """Each `note` key in dev/gate.sh, with the modes whose branch reaches it,
    directly or through the functions it calls."""
    functions = {
        m.group(1): m.group(2)
        for m in re.finditer(r"^(\w+)\(\) \{\n(.*?)^\}", text, re.S | re.M)
    }
    branches = {
        mode: m.group(1)
        for mode in sorted(gate_steps.MODES)
        for m in [re.search(rf"^--{mode}\)\n(.*?)^    ;;", text, re.S | re.M)]
        if m
    }
    steps: dict[str, set[str]] = {}
    for mode, body in branches.items():
        reached, frontier = [body], [body]
        called: set[str] = set()
        while frontier:
            chunk = frontier.pop()
            for fn, fn_body in functions.items():
                if fn not in called and re.search(rf"^\s*{fn}\s*$", chunk, re.M):
                    called.add(fn)
                    reached.append(fn_body)
                    frontier.append(fn_body)
        for chunk in reached:
            for key in NOTE.findall(chunk):
                steps.setdefault(key, set()).add(mode)
    unreached = set(NOTE.findall(text)) - set(steps)
    for key in unreached:
        steps[key] = set()
    return steps


def changed_refusals() -> None:
    """dev/gate.sh --changed in a throwaway repository holding only the files it
    reads before running a step: each case exits before any step would run."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "dev").mkdir()
        for name in ("gate.sh", "gate_steps.py", "gate-steps.toml", "currency-instant.json"):
            shutil.copy2(REPO / "dev" / name, root / "dev" / name)

        def git(*args: str) -> None:
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.org",
                            "-c", "core.hooksPath=/dev/null", *args],
                           cwd=root, env=env, check=True, capture_output=True)

        def gate(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(["bash", "dev/gate.sh", "--changed", *args],
                                  cwd=root, env=env, capture_output=True, text=True)

        git("init", "-q", "-b", "main")
        git("add", "-A")
        git("commit", "-q", "--no-verify", "-m", "base")
        r = gate()
        check("no change since main exits 0 without running a step",
              r.returncode == 0 and "nothing to check" in r.stdout
              and "Clojure consumer path" not in r.stdout, r.stdout + r.stderr)
        r = gate("no-such-base")
        check("an unknown base refuses", r.returncode == 3 and "REFUSED" in r.stderr, r.stderr)
        r = gate("main", "extra")
        check("a second argument refuses", r.returncode == 3, r.stderr)
        table = root / "dev" / "gate-steps.toml"
        table.write_text(table.read_text() + "# an edit\n")
        r = gate()
        check("a working-tree change refuses", r.returncode == 3 and "REFUSED" in r.stderr, r.stderr)
        git("add", "-A")
        r = gate()
        check("a staged change refuses", r.returncode == 3 and "REFUSED" in r.stderr, r.stderr)


def main() -> int:
    table = gate_steps.load()
    gate_entries = {e["note"]: e for e in table.get("gate", [])}
    check_entries = {e["name"] for e in table.get("check_all", [])}

    print("=== dev/gate.sh ===")
    sh = gate_sh_steps((REPO / "dev" / "gate.sh").read_text())
    check("gate.sh has steps in every mode",
          all(any(mode in m for m in sh.values()) for mode in gate_steps.MODES))
    for key, modes in sorted(sh.items()):
        if key not in gate_entries:
            check(f"{key!r} is in the table", False, "a gate.sh step the table does not name")
            continue
        declared = set(gate_entries[key]["modes"])
        check(f"{key!r} modes", declared == modes,
              f"table says {sorted(declared)}, gate.sh runs it in {sorted(modes)}")
    for key in sorted(set(gate_entries) - set(sh)):
        check(f"{key!r} is a gate.sh step", False, "the table names a step gate.sh does not have")
    check("table keys carry no shell variable", not any("$" in k for k in gate_entries))
    check("table keys are unique", len(gate_entries) == len(table.get("gate", [])))

    print("=== dev/check_all.py ===")
    names = [name for name, _ in check_all.STEPS]
    for name in sorted(set(names) - check_entries):
        check(f"{name!r} is in the table", False, "a check_all.py step the table does not name")
    for name in sorted(check_entries - set(names)):
        check(f"{name!r} is a check_all.py step", False, "the table names a step check_all.py does not have")
    check("every check_all.py step is in the table and nothing else", set(names) == check_entries)
    check("check_all keys are unique", len(check_entries) == len(table.get("check_all", [])))

    print("=== selection ===")
    nbt, xc, scm = "NBT export cells", "Scenario cost models: clj-urpx cross-check", "Scenario cost models: SHACL"
    vd = "Version-dispatch and shape-exception negative fixtures"
    slow = {nbt, xc, scm}
    pf, sd = "Per-file diagnostic (informational)", "Sandbox drift (informational)"
    utilities = ["cpau", "pge", "sce"]
    cases = [
        ("an NBT filing",
         ["us/ca/sce/electricity/nbt/versions/2025-04-23/rate-plan-modifier_sce_nbt_2025-04-23.jsonld"],
         {vd, sd}, ["sce"]),
        ("a non-NBT SCE modifier filing",
         ["us/ca/sce/electricity/care/versions/2026-03-20/rate-plan-modifier_sce_care_2026-03-20.jsonld"],
         {vd, sd}, ["sce"]),
        ("a PG&E base filing",
         ["us/ca/pge/electricity/e-1/versions/2026-03-01/rate-plan_pge_e-1_2026-03-01.jsonld"],
         {nbt, vd, sd}, ["pge"]),
        ("a PG&E modifier filing and its manifest",
         ["us/ca/pge/electricity/d-care/versions/2026-03-01/rate-plan-modifier_pge_d-care_2026-03-01.jsonld",
          "us/ca/pge/electricity/d-care/versions/2026-03-01/tariff.toml"],
         {vd}, ["pge"]),
        ("a CPAU manifest", ["us/ca/cpau/electricity/e-1/versions/2025-07-01/tariff.toml"],
         {nbt, xc, vd, pf}, ["cpau"]),
        ("deps.edn", ["deps.edn"], {sd}, utilities),
        ("the corpus walker", ["dev/corpus.py"], {nbt, sd}, utilities),
        ("the recorded SHACL baseline", ["dev/baseline/corpus.json"], slow | {pf, sd}, utilities),
        ("the shape exceptions", ["dev/shape-exceptions.json"], {nbt, xc, sd}, utilities),
        ("the currency instant", ["dev/currency-instant.json"], {nbt, scm, pf, sd}, []),
        ("the gate itself", ["dev/gate-steps.toml"], set(), utilities),
        ("a dev/ lint", ["dev/lint_price_cells.py"], slow | {pf, sd}, []),
        ("a .md file", ["LAYOUT.md"], slow | {vd, pf, sd}, []),
        ("nothing", [], slow | {vd, pf, sd}, []),
    ]
    for name, paths, want_skipped, want_utilities in cases:
        got = set(gate_steps.skipped(table, paths))
        check(f"{name}: skipped", got == want_skipped, f"got {sorted(got)}")
        got_u = gate_steps.utilities(table, "Baseline", paths, utilities)
        check(f"{name}: utilities", got_u == want_utilities, f"got {got_u}")
    check("a step the table does not name is never skipped",
          "No such step" not in gate_steps.skipped(table, []))

    print("=== check_all selection ===")
    every = [e["name"] for e in table.get("check_all", [])]
    untriggered = {e["name"] for e in table.get("check_all", []) if not e.get("triggers")}
    check("some check_all steps have no triggers", bool(untriggered))
    manifest = "us/ca/cpau/electricity/e-1/versions/2025-07-01/tariff.toml"
    filing = "us/ca/pge/electricity/e-1/versions/2026-03-01/rate-plan_pge_e-1_2026-03-01.jsonld"
    ca_cases = [
        # (name, paths, must select, must skip)
        ("nothing", [], untriggered, set(every) - untriggered),
        ("a .md file", ["LAYOUT.md"], untriggered, set(every) - untriggered),
        ("a manifest", [manifest],
         {"lint_prose_structure", "build_catalog", "coverage_evaluations", "check_generated"},
         {"lint_price_cells", "test_shacl_gate", "test_dsl_validation"}),
        ("a JSON-LD filing", [filing],
         {"lint_price_cells", "check_generated", "list_modifier_base_pairings"},
         {"test_shacl_gate", "test_dsl_validation", "test_resolution_coverage"}),
        ("DSL source", ["src/rate_plans/gen.clj"],
         {"check_generated", "test_dsl_validation"}, {"lint_price_cells", "test_shacl_gate"}),
        ("deps.edn", ["deps.edn"],
         {"test_shacl_gate", "test_resolution_coverage", "list_scenario_cost_models"},
         {"lint_price_cells"}),
        ("a generator's output", ["reports/coverage.md"], {"coverage"}, {"build_catalog"}),
        ("a dev/ lint", ["dev/lint_price_cells.py"], set(every), set()),
        ("the gate itself", ["dev/gate.sh"], set(every), set()),
    ]
    for name, paths, want, not_want in ca_cases:
        got = set(gate_steps.check_all_selected(table, paths))
        check(f"{name}: check_all selects", want <= got, f"missing {sorted(want - got)}")
        check(f"{name}: check_all skips", not (not_want & got), f"selected {sorted(not_want & got)}")

    print("=== dev/gate.sh --changed refusals ===")
    changed_refusals()

    print()
    if failures:
        print(f"FAIL: {len(failures)} check(s) failed")
        return 1
    print("all gate-steps checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
