#!/usr/bin/env python3
"""Single-command sanity check: run every generator + lint, detect drift.

Useful as a pre-commit gate or in CI: catches the case where someone edited
a tariff.toml or jsonld file but forgot to regenerate a derived report.

Steps:
  1. Run each generator (coverage, pairings export, scenario cost models,
     ready-for-use list).
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

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus

REPO = Path(__file__).resolve().parent.parent


# The single source of truth for which generators and lints run. The pre-commit
# hook invokes this file with --generators-only rather than keeping its own list,
# because two lists drift: this one carried backfill_modeling and lint_consistency
# that the hook lacked, while the hook carried coverage.py that this one lacked,
# which is why backfill output had never been committed.
#
# backfill_modeling is NOT here, and must not be added back. Everything in this
# list tabulates: it reads the corpus and writes a report. backfill_modeling is
# the one script that carried a judgment, a hand-written table of per-filing
# deferrals, and it stamped that table over the [modeling] block in 45 of the 72
# manifests every time this ran. LAYOUT.md 4.4 and the add-a-filing workflow at
# step 7 put that assessment in tariff.toml, authored by whoever modeled the
# filing against its source PDF. So the script was reverting the authored answer
# to whatever was true when its table was written, which is how the manifests
# went stale while the models moved on. It was a one-time bootstrap; it has run.
#
# list_scenario_cost_models meets that same bar. It enumerates what the corpus
# can serve and reads servability off the recorded baseline; it holds no table
# of its own, deriving supersession, compatibility and the alternative
# nominations from the corpus, from dev/baseline/marginal-rates.edn and from
# dev/validate_v020.clj, and refusing rather than reporting when an input is
# missing or a baseline row cannot be attributed. list_ready_for_use now reads
# that same enumeration instead of carrying a second walk of its own.
# test_scenario_cost_models sits beside them because a guard is worth nothing until it
# has been made to fire, and that file fires every one of them against a
# deliberately broken input.
#
# list_rate_identifiers meets the same bar. It tabulates the MIDAS identifiers
# the corpus cites, keyed to the compositions dev/scenario_cost_models.py enumerates,
# and holds no list of identifiers of its own: the enumeration is whatever the
# corpus asserts, the RIN grammar is read off reports/midas-coverage.json, and
# it refuses when an input is missing or a citation is unattributable. It also
# refuses if a RIN is ever lifted into a urpx:RatePlanIdentifier or
# urpx:RatePlanModifierIdentifier, which is the decision that report records.
# test_rate_identifiers fires every one of those guards against broken input.
#
# check_generated regenerates every document that has Clojure source under src/
# and requires each to equal its committed file byte for byte. In the pre-commit
# hook it runs in the checkout of the index, so it judges the staged tree.
# test_dsl_validation requires each invalid fixture under dev/fixtures/dsl/ to
# fail to load with an error naming its file, line and bad values.
#
# build_catalog writes catalog/, the DCAT catalog of the corpus, and refuses
# rather than writes when any filing cannot be summarized. The pre-commit hook
# stages catalog/ beside reports/.
STEPS: list[tuple[str, list[str]]] = [
    ("coverage",                    ["python3", "dev/coverage.py", "--write-report"]),
    ("list_modifier_base_pairings", ["python3", "dev/list_modifier_base_pairings.py"]),
    ("list_scenario_cost_models",   ["python3", "dev/list_scenario_cost_models.py"]),
    ("list_ready_for_use",          ["python3", "dev/list_ready_for_use.py"]),
    ("list_version_continuity",     ["python3", "dev/list_version_continuity.py"]),
    ("list_rate_identifiers",       ["python3", "dev/list_rate_identifiers.py"]),
    ("list_rate_plans_to_model",    ["python3", "dev/list_rate_plans_to_model.py"]),
    ("build_catalog",               ["python3", "dev/build_catalog.py"]),
    ("lint_modifier_coverage",      ["python3", "dev/lint_modifier_coverage.py"]),
    ("lint_consistency",            ["python3", "dev/lint_consistency.py"]),
    ("lint_cross_filing",           ["python3", "dev/lint_cross_filing.py"]),
    ("lint_copy_divergence",        ["python3", "dev/lint_copy_divergence.py"]),
    ("lint_utility_manifests",      ["python3", "dev/lint_utility_manifests.py"]),
    ("lint_gaps_agree",             ["python3", "dev/lint_gaps_agree.py"]),
    ("lint_declared_versions",      ["python3", "dev/lint_declared_versions.py"]),
    ("lint_prose_structure",        ["python3", "dev/lint_prose_structure.py"]),
    ("lint_holiday_calendars",      ["python3", "dev/lint_holiday_calendars.py"]),
    ("lint_price_layer_conditions", ["python3", "dev/lint_price_layer_conditions.py"]),
    ("lint_price_cells",            ["python3", "dev/lint_price_cells.py"]),
    ("lint_decimal_literals",       ["python3", "dev/lint_decimal_literals.py"]),
    ("coverage_evaluations",        ["python3", "dev/resync_coverage_evaluations.py", "--check"]),
    ("test_shacl_gate",             ["clojure", "-M", "-m", "test-shacl-gate"]),
    ("test_scenario_cost_models",   ["python3", "dev/test_scenario_cost_models.py"]),
    ("test_prose_structure",        ["python3", "dev/test_prose_structure.py"]),
    ("test_rate_identifiers",       ["python3", "dev/test_rate_identifiers.py"]),
    ("test_holiday_calendars",      ["python3", "dev/test_holiday_calendars.py"]),
    ("test_price_layer_conditions", ["python3", "dev/test_price_layer_conditions.py"]),
    ("test_price_cells",            ["python3", "dev/test_price_cells.py"]),
    ("test_decimal_literals",       ["python3", "dev/test_decimal_literals.py"]),
    ("test_discount_summaries",     ["python3", "dev/test_discount_summaries.py"]),
    ("test_rdf_hash",               ["python3", "dev/test_rdf_hash.py"]),
    ("test_sandbox_export",         ["python3", "dev/test_sandbox_export.py"]),
    ("test_fetch_unwrap",           ["python3", "dev/test_fetch_unwrap.py"]),
    ("test_build_catalog",          ["python3", "dev/test_build_catalog.py"]),
    ("test_cross_filing",           ["python3", "dev/test_cross_filing.py"]),
    ("check_generated",             ["python3", "dev/check_generated.py"]),
    ("test_dsl_validation",         ["clojure", "-M", "-m", "test-dsl-validation"]),
    ("test_resolution_coverage",    ["clojure", "-M", "-m", "test-resolution-coverage"]),
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
    for tp in corpus.tariff_tomls():
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


MIDAS_REPORTS = [REPO / "reports" / "midas-coverage.json", REPO / "reports" / "midas-coverage.md"]
MIDAS_STALE_DAYS = 30


def report_midas_staleness() -> None:
    """Print how old the MIDAS coverage report is. Never fails, never fetches.

    scripts/build-midas-coverage-report.py is NOT in STEPS on purpose: it reads
    data/midas/midas.sqlite, the untracked store dev/mine_midas.py writes, which
    a checkout of the index does not have. It makes no network calls and needs
    no credentials, but its input is only as fresh as the last mine.

    But leaving it out entirely is how it went four months stale without anyone
    noticing, which is the same silence the corpus-coverage generator sat in. So
    the age is printed on every full run. Refresh deliberately:

        python3 dev/mine_midas.py && python3 scripts/build-midas-coverage-report.py
    """
    import datetime
    print()
    print("=== MIDAS coverage report age ===")
    for f in MIDAS_REPORTS:
        if not f.exists():
            print(f"  MISSING  {f.relative_to(REPO)}")
            continue
        age = (datetime.datetime.now() - datetime.datetime.fromtimestamp(f.stat().st_mtime)).days
        flag = "  STALE, refresh it" if age > MIDAS_STALE_DAYS else ""
        print(f"  {age:4d} days  {f.relative_to(REPO)}{flag}")


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

    if not generators_only:
        report_midas_staleness()

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
