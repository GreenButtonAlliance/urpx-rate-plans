#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Tests for dev/gate-steps.toml: it names every gate step and nothing else.

Every `note` step in dev/gate.sh appears as a [[gate]] entry whose modes are
the gate.sh branches that run it, and every dev/check_all.py STEPS entry as a
[[check_all]] entry; every entry names a real step. Then the selection for a
set of staged diffs.

Run: python3 dev/test_gate_steps.py
"""
from __future__ import annotations

import re
import sys
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
    """Each `note` key in dev/gate.sh, with the modes whose branch reaches it."""
    functions = {
        m.group(1): m.group(2)
        for m in re.finditer(r"^(\w+)\(\) \{\n(.*?)^\}", text, re.S | re.M)
    }
    branches = {
        mode: m.group(1)
        for mode in ("fast", "full")
        for m in [re.search(rf"^--{mode}\)\n(.*?)^    ;;", text, re.S | re.M)]
        if m
    }
    steps: dict[str, set[str]] = {}
    for mode, body in branches.items():
        reached = [body] + [
            fn_body for fn, fn_body in functions.items() if re.search(rf"^\s*{fn}\s*$", body, re.M)
        ]
        for chunk in reached:
            for key in NOTE.findall(chunk):
                steps.setdefault(key, set()).add(mode)
    unreached = set(NOTE.findall(text)) - set(steps)
    for key in unreached:
        steps[key] = set()
    return steps


def main() -> int:
    table = gate_steps.load()
    gate_entries = {e["note"]: e for e in table.get("gate", [])}
    check_entries = {e["name"] for e in table.get("check_all", [])}

    print("=== dev/gate.sh ===")
    sh = gate_sh_steps((REPO / "dev" / "gate.sh").read_text())
    check("gate.sh has steps in both modes",
          any("fast" in m for m in sh.values()) and any("full" in m for m in sh.values()))
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
    slow = {nbt, xc, scm}
    utilities = ["cpau", "pge", "sce"]
    cases = [
        ("an NBT filing",
         ["us/ca/sce/electricity/nbt/versions/2025-04-23/rate-plan-modifier_sce_nbt_2025-04-23.jsonld"],
         set(), ["sce"]),
        ("a non-NBT SCE modifier filing",
         ["us/ca/sce/electricity/care/versions/2026-03-20/rate-plan-modifier_sce_care_2026-03-20.jsonld"],
         set(), ["sce"]),
        ("a PG&E base filing",
         ["us/ca/pge/electricity/e-1/versions/2026-03-01/rate-plan_pge_e-1_2026-03-01.jsonld"],
         {nbt}, ["pge"]),
        ("a PG&E modifier filing and its manifest",
         ["us/ca/pge/electricity/d-care/versions/2026-03-01/rate-plan-modifier_pge_d-care_2026-03-01.jsonld",
          "us/ca/pge/electricity/d-care/versions/2026-03-01/tariff.toml"],
         set(), ["pge"]),
        ("a CPAU manifest", ["us/ca/cpau/electricity/e-1/versions/2025-07-01/tariff.toml"],
         {nbt, xc}, ["cpau"]),
        ("deps.edn", ["deps.edn"], set(), utilities),
        ("the corpus walker", ["dev/corpus.py"], {nbt}, utilities),
        ("the recorded SHACL baseline", ["dev/baseline/corpus.json"], slow, utilities),
        ("the shape exceptions", ["dev/shape-exceptions.json"], {nbt, xc}, utilities),
        ("the currency instant", ["dev/currency-instant.json"], {nbt, scm}, []),
        ("the gate itself", ["dev/gate-steps.toml"], set(), utilities),
        ("a dev/ lint", ["dev/lint_price_cells.py"], slow, []),
        ("a .md file", ["LAYOUT.md"], slow, []),
        ("nothing", [], slow, []),
    ]
    for name, paths, want_skipped, want_utilities in cases:
        got = set(gate_steps.skipped(table, paths))
        check(f"{name}: skipped", got == want_skipped, f"got {sorted(got)}")
        got_u = gate_steps.utilities(table, "Baseline", paths, utilities)
        check(f"{name}: utilities", got_u == want_utilities, f"got {got_u}")
    check("a step the table does not name is never skipped",
          "No such step" not in gate_steps.skipped(table, []))

    print()
    if failures:
        print(f"FAIL: {len(failures)} check(s) failed")
        return 1
    print("all gate-steps checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
