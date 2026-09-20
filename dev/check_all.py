#!/usr/bin/env python3
"""Single-command sanity check: run every generator + lint, detect drift.

Useful as a pre-commit gate or in CI: catches the case where someone edited
a tariff.toml or jsonld file but forgot to regenerate a derived report.

Steps:
  1. Run each generator (pairings export, modeling backfill, ready-for-use list).
  2. Run each lint (modifier coverage, cross-filing consistency).
  3. Validate every tariff.toml against schema/tariff-manifest.schema.json.
  4. After all of that, `git status --porcelain` should be empty: if any
     tracked file differs, that's drift — flag it.

Exit codes:
  0 — every step passed, no drift.
  1 — at least one step failed (generator/lint/schema error).
  2 — every step passed but tracked files drifted (run the generators).

  --generators-only  run step 1-2 only and stop. This is what the pre-commit
                     hook calls, so the hook does not keep a second step list.

Run from repo root:  python3 dev/check_all.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


# The single source of truth for which generators and lints run. The pre-commit
# hook invokes this file with --generators-only rather than keeping its own list,
# because two lists drift: this one carried backfill_modeling and lint_consistency
# that the hook lacked, while the hook carried coverage.py that this one lacked,
# which is why backfill output had never been committed.
STEPS: list[tuple[str, list[str]]] = [
    ("coverage",                    ["python3", "dev/coverage.py", "--write-report"]),
    ("list_modifier_base_pairings", ["python3", "dev/list_modifier_base_pairings.py"]),
    ("backfill_modeling",           ["python3", "dev/backfill_modeling.py"]),
    ("list_ready_for_use",          ["python3", "dev/list_ready_for_use.py"]),
    ("lint_modifier_coverage",      ["python3", "dev/lint_modifier_coverage.py"]),
    ("lint_consistency",            ["python3", "dev/lint_consistency.py"]),
]


def run_step(name: str, cmd: list[str]) -> tuple[bool, str, str]:
    """Returns (ok, stdout, stderr)."""
    result = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    return result.returncode == 0, result.stdout, result.stderr


def validate_schema() -> tuple[bool, str]:
    """Validate every tariff.toml against schema. Returns (ok, message)."""
    try:
        import tomli
        import jsonschema
    except ImportError as e:
        return False, f"  missing python dep: {e}"

    schema = json.loads((REPO / "schema" / "tariff-manifest.schema.json").read_text())
    errors: list[str] = []
    count = 0
    for tp in sorted(REPO.glob("ca/*/*/*/versions/*/tariff.toml")):
        count += 1
        with tp.open("rb") as fp:
            data = tomli.load(fp)
        try:
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as e:
            errors.append(f"  {tp.relative_to(REPO)}: {e.message}")
    if errors:
        return False, f"  {count} files checked, {len(errors)} invalid:\n" + "\n".join(errors)
    return True, f"  {count} tariff.toml files validate against schema"


def detect_drift() -> list[str]:
    """Returns a list of tracked files that drifted (porcelain output minus untracked)."""
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True, check=True
    )
    drifted = []
    for line in result.stdout.splitlines():
        # `git status --porcelain` format: "XY filename" — XY is two-char status.
        # Untracked files have status "??". We want everything else (M, A, D, R, etc.).
        status = line[:2]
        path = line[3:]
        if status == "??":
            continue
        drifted.append(path)
    return drifted


def main() -> int:
    generators_only = "--generators-only" in sys.argv

    print("=== Generators + lints ===")
    failures: list[tuple[str, str, str]] = []
    for name, cmd in STEPS:
        ok, out, err = run_step(name, cmd)
        marker = "✓" if ok else "✗"
        print(f"  {marker} {name}")
        if not ok:
            failures.append((name, out, err))

    if generators_only:
        # The pre-commit hook's mode: regenerate derived artifacts so they can be
        # staged into the same commit. Schema validation and the drift check are
        # deliberately skipped, because drift is what the hook is about to fix.
        if failures:
            print()
            print("=== FAILURES ===")
            for name, out, err in failures:
                print(f"\n--- {name} ---")
                if out:
                    print(out)
                if err:
                    print(err, file=sys.stderr)
            return 1
        return 0

    print()
    print("=== Schema validation ===")
    ok, msg = validate_schema()
    print(f"  {'✓' if ok else '✗'} schema validation")
    print(msg)
    if not ok:
        failures.append(("schema validation", msg, ""))

    if failures:
        print()
        print("=== FAILURES ===")
        for name, out, err in failures:
            print(f"\n--- {name} ---")
            if out:
                print(out)
            if err:
                print(err, file=sys.stderr)
        return 1

    print()
    print("=== Drift check ===")
    drifted = detect_drift()
    if drifted:
        print(f"  ✗ {len(drifted)} tracked file(s) changed since HEAD:")
        for f in drifted:
            print(f"    {f}")
        print()
        print("  One of the generators produced different output. Either:")
        print("    (a) commit the regenerated outputs (they reflect the current corpus), or")
        print("    (b) revert the source-of-truth changes that caused them.")
        return 2

    print("  ✓ no drift — all tracked files match HEAD")
    print()
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
