#!/usr/bin/env python3
"""Compute corpus coverage of residential utility customers, per state and in total.

Walks the us/<subdivision>/<utility>/<carrier>/<schedule>/versions/<date>/ tree, matches
each modeled rate plan against dev/coverage-estimates.toml, and reports:

  - Totals: residential customers tracked, covered, coverage %, per state and overall
  - Per state, per utility: residential customers, modeled rate plans, covered count, %
  - Per state, largest unmodeled targets (prioritization signal)

Also emits reports/coverage.md as a human-readable summary suitable for
linking from README.md.

Usage:
    python dev/coverage.py                  # print to stdout
    python dev/coverage.py --write-report   # also write reports/coverage.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from collections import defaultdict
from dataclasses import dataclass, field

REPO_ROOT = Path(__file__).resolve().parent.parent
ESTIMATES_PATH = REPO_ROOT / "dev" / "coverage-estimates.toml"
REPORT_PATH = REPO_ROOT / "reports" / "coverage.md"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus  # noqa: E402

@dataclass
class ModeledRatePlan:
    utility: str
    schedule: str
    versions: list[str] = field(default_factory=list)
    is_modifier: bool = False
    state: str = ""           # the <subdivision> directory, e.g. "ca"


@dataclass
class UtilityCoverage:
    utility_id: str
    name: str
    util_class: str
    state: str
    total_residential: int
    modeled_tariffs: list[str] = field(default_factory=list)
    unmodeled_tariffs: list[str] = field(default_factory=list)
    covered_count: int = 0

    @property
    def coverage_pct(self) -> float:
        if self.total_residential == 0:
            return 0.0
        return 100.0 * self.covered_count / self.total_residential


def discover_modeled_rate_plans() -> dict[tuple[str, str], ModeledRatePlan]:
    """Every modeled base plan and modifier, as {(utility, schedule): info}."""
    found: dict[tuple[str, str], ModeledRatePlan] = {}
    # Discovery and decomposition both through dev/corpus.py. This used to hold
    # its own root and its own rglob, which is how it came to count path segments
    # against the pre-`us/` layout: the guard then rejected every file in the
    # corpus and this generator reported 0.0% coverage while exiting 0.
    for jsonld in corpus.all_filing_jsonld():
        try:
            util, sched, date = corpus.parse_filing_path(jsonld)
        except ValueError:
            continue
        is_modifier = jsonld.name.startswith("rate-plan-modifier_")
        key = (util, sched)
        if key not in found:
            found[key] = ModeledRatePlan(util, sched, is_modifier=is_modifier,
                                         state=corpus.subdivision_of(jsonld))
        elif not is_modifier:
            # A schedule is a base plan if it has a base plan, whatever else sits
            # beside it. One directory holds both: PG&E E-1 2026-03-01 packages
            # the base with its income-tier modifier. This flag used to be set by
            # whichever of the two the walk reached first, so it was decided by
            # filesystem order. That read as correct only because the order happened
            # to favor the base; under any sorted order "rate-plan-modifier_" comes
            # before "rate-plan_" ("-" sorts below "_"), the schedule was recorded as
            # a modifier, and it dropped out of the coverage arithmetic: statewide
            # 90.8% became 62.2% and PG&E 100% became 22%, with nothing failing.
            found[key].is_modifier = False
        found[key].versions.append(date)
    for plan in found.values():
        plan.versions.sort()
    # A generator that matches nothing must refuse, not exit 0. This function
    # returned {} for months after the us/ restructure moved the segments its
    # indices counted on, and every signal downstream agreed: the report said
    # 0.0% coverage, check_all.py reported success on exit status, and the
    # pre-commit hook printed a tick because the empty output never changed.
    corpus.require_nonempty(found, "modeled rate plans (coverage discovery)")
    return found


def load_estimates() -> dict:
    return corpus.load_toml(ESTIMATES_PATH)


def check_states(estimates: dict, modeled: dict[tuple[str, str], ModeledRatePlan]) -> None:
    """Refuse unless every utility names a declared state, and the state agrees
    with the directory its filings sit under.

    A missing state would drop a utility from every per-state section; a wrong
    one would count its customers toward another state's coverage.
    """
    declared = estimates.get("state", {})
    states_of: dict[str, set[str]] = {}
    for (util, _), info in modeled.items():
        states_of.setdefault(util, set()).add(info.state)
    for util_id, d in estimates.get("utility", {}).items():
        st = d.get("state")
        if st not in declared:
            raise SystemExit(
                f"ERROR: [utility.{util_id}] in {ESTIMATES_PATH.name} has state "
                f"{st!r}, which has no [state.<code>] table. Every utility names one.")
        on_disk = states_of.get(util_id, set())
        if on_disk and on_disk != {st}:
            raise SystemExit(
                f"ERROR: [utility.{util_id}] says state {st!r} but its filings sit "
                f"under {sorted(on_disk)}.")


def compute_coverage(
    estimates: dict,
    modeled: dict[tuple[str, str], ModeledRatePlan],
) -> tuple[list[UtilityCoverage], int, int]:
    """Return (per-utility coverage list, total residential, total covered)."""
    utilities = estimates.get("utility", {})
    out: list[UtilityCoverage] = []
    total_residential = 0
    total_covered = 0

    modeled_by_util: dict[str, set[str]] = defaultdict(set)
    for (util, sched), info in modeled.items():
        # Modifier filings (e-eec-1, e-hra, e-2-g, etc.) extend a base plan;
        # they don't independently "cover" customers — coverage attaches to
        # the base RatePlan. Skip modifiers for coverage accounting.
        if info.is_modifier:
            continue
        modeled_by_util[util].add(sched)

    for util_id, util_data in utilities.items():
        total = util_data.get("total_residential", 0)
        total_residential += total
        cov = UtilityCoverage(
            utility_id=util_id,
            name=util_data.get("name", util_id),
            util_class=util_data.get("class", "?"),
            state=util_data["state"],
            total_residential=total,
        )
        tariffs = util_data.get("tariffs", {})
        modeled_for_util = modeled_by_util.get(util_id, set())

        for sched, t_data in tariffs.items():
            count = _estimate_count(t_data, total)
            if sched in modeled_for_util:
                cov.modeled_tariffs.append(sched)
                cov.covered_count += count
            else:
                cov.unmodeled_tariffs.append(sched)

        # If a modeled schedule isn't listed in tariffs[], list it as
        # "modeled but unestimated" so the user knows to add an entry.
        for sched in sorted(modeled_for_util):
            if sched not in tariffs:
                cov.modeled_tariffs.append(f"{sched} (no estimate)")

        total_covered += cov.covered_count
        out.append(cov)

    out.sort(key=lambda c: c.total_residential, reverse=True)
    return out, total_residential, total_covered


def _estimate_count(tariff_data: dict, util_total: int) -> int:
    if "estimated_residential_customers" in tariff_data:
        return int(tariff_data["estimated_residential_customers"])
    share = tariff_data.get("share_of_residential")
    if share is not None:
        return int(util_total * float(share))
    return 0


def _pct(covered: int, total: int) -> float:
    return 100.0 * covered / total if total else 0.0


def by_state(coverage: list[UtilityCoverage], estimates: dict) -> list[tuple[str, str, list[UtilityCoverage]]]:
    """[(code, name, utilities)] for every declared state, largest first."""
    names = {code: d.get("name", code.upper()) for code, d in estimates.get("state", {}).items()}
    groups: dict[str, list[UtilityCoverage]] = {code: [] for code in names}
    for cov in coverage:
        groups[cov.state].append(cov)
    out = [(code, names[code], groups[code]) for code in names]
    out.sort(key=lambda g: (-sum(c.total_residential for c in g[2]), g[0]))
    return out


def _state_note(utils: list[UtilityCoverage]) -> str:
    """Why a state reads 0%, when the reason is that nothing is modeled yet."""
    if not any(c.modeled_tariffs for c in utils):
        return "no filings yet, so 0% by construction"
    return ""


def render_markdown(
    coverage: list[UtilityCoverage],
    total_residential: int,
    total_covered: int,
    modeled: dict[tuple[str, str], ModeledRatePlan],
    estimates: dict,
) -> str:
    states = by_state(coverage, estimates)
    lines: list[str] = []
    lines.append("# Residential Rate Plan Coverage")
    lines.append("")
    lines.append(
        "Auto-generated by `dev/coverage.py` from `dev/coverage-estimates.toml`. "
        "Do not edit by hand — refine the estimates TOML and re-run."
    )
    lines.append("")
    lines.append("## Totals")
    lines.append("")
    lines.append("| State | Residential | Covered | Coverage | Note |")
    lines.append("|---|---:|---:|---:|---|")
    for code, name, utils in states:
        res = sum(c.total_residential for c in utils)
        cov = sum(c.covered_count for c in utils)
        lines.append(f"| {name} | {res:,} | {cov:,} | {_pct(cov, res):.1f}% | {_state_note(utils)} |")
    lines.append(f"| **All states** | **{total_residential:,}** | **{total_covered:,}** | "
                 f"**{_pct(total_covered, total_residential):.1f}%** | |")
    lines.append("")

    for code, name, utils in states:
        res = sum(c.total_residential for c in utils)
        covd = sum(c.covered_count for c in utils)
        lines.append(f"## {name}")
        lines.append("")
        lines.append(f"- Total residential customers tracked: **{res:,}**")
        lines.append(f"- Customers covered by modeled rate plans: **{covd:,}**")
        note = _state_note(utils)
        lines.append(f"- Coverage: **{_pct(covd, res):.1f}%**" + (f" ({note})" if note else ""))
        lines.append("")
        lines.append("### Per-utility")
        lines.append("")
        lines.append(
            "| Utility | Class | Residential | Covered | % | Modeled tariffs |"
        )
        lines.append("|---|---|---:|---:|---:|---|")
        for cov in utils:
            modeled_str = ", ".join(cov.modeled_tariffs) if cov.modeled_tariffs else "—"
            lines.append(
                f"| {cov.name} | {cov.util_class} | {cov.total_residential:,} | "
                f"{cov.covered_count:,} | {cov.coverage_pct:.1f}% | {modeled_str} |"
            )
        lines.append("")

        # Prioritization: largest unmodeled-customer pools.
        lines.append("### Largest unmodeled customer pools")
        lines.append("")
        lines.append(
            "Sorted by number of residential customers without a modeled default. "
            "Top of list = highest-leverage modeling work."
        )
        lines.append("")
        unmodeled = [c for c in utils if c.coverage_pct < 99.5]
        unmodeled.sort(key=lambda c: c.total_residential - c.covered_count, reverse=True)
        lines.append("| Utility | Uncovered customers | Existing modeled | Notes |")
        lines.append("|---|---:|---|---|")
        for cov in unmodeled[:10]:
            gap = cov.total_residential - cov.covered_count
            modeled_str = ", ".join(cov.modeled_tariffs) if cov.modeled_tariffs else "(none)"
            lines.append(f"| {cov.name} | {gap:,} | {modeled_str} | |")
        lines.append("")

    # All modeled filings (including modifiers).
    lines.append("## All modeled filings")
    lines.append("")
    lines.append("| State | Utility | Schedule | Type | Versions |")
    lines.append("|---|---|---|---|---|")
    for (util, sched), info in sorted(modeled.items()):
        kind = "modifier" if info.is_modifier else "rate-plan"
        lines.append(f"| {info.state.upper()} | {util} | {sched} | {kind} | "
                     f"{', '.join(info.versions)} |")
    lines.append("")
    return "\n".join(lines)


def render_text(
    coverage: list[UtilityCoverage],
    total_residential: int,
    total_covered: int,
    estimates: dict,
) -> str:
    lines = []
    lines.append("=" * 78)
    lines.append("RESIDENTIAL TARIFF CORPUS COVERAGE")
    lines.append("=" * 78)
    lines.append(f"Total residential customers tracked:  {total_residential:>12,}")
    lines.append(f"Covered by modeled rate plans:        {total_covered:>12,}")
    lines.append(f"Coverage, all states:                     {_pct(total_covered, total_residential):>6.1f}%")
    for code, name, utils in by_state(coverage, estimates):
        res = sum(c.total_residential for c in utils)
        covd = sum(c.covered_count for c in utils)
        note = _state_note(utils)
        lines.append("")
        lines.append(f"{name.upper()}: {covd:,} of {res:,} residential customers, "
                     f"{_pct(covd, res):.1f}%" + (f" ({note})" if note else ""))
        lines.append(
            f"{'Utility':<48}{'Class':<6}{'Residential':>13}"
            f"{'Covered':>11}{'%':>7}"
        )
        lines.append("-" * 85)
        for cov in utils:
            lines.append(
                f"{cov.name[:46]:<48}{cov.util_class:<6}"
                f"{cov.total_residential:>13,}{cov.covered_count:>11,}"
                f"{cov.coverage_pct:>6.1f}%"
            )
        lines.append("")
        lines.append("Top unmodeled customer pools (largest first):")
        unmodeled = [c for c in utils if c.coverage_pct < 99.5]
        unmodeled.sort(key=lambda c: c.total_residential - c.covered_count, reverse=True)
        for cov in unmodeled[:8]:
            gap = cov.total_residential - cov.covered_count
            modeled_str = ", ".join(cov.modeled_tariffs) if cov.modeled_tariffs else "(none)"
            lines.append(f"  {cov.name[:42]:<44}{gap:>10,}  modeled: {modeled_str}")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--write-report",
        action="store_true",
        help=f"Also write Markdown summary to {REPORT_PATH.relative_to(REPO_ROOT)}",
    )
    args = p.parse_args()

    estimates = load_estimates()
    modeled = discover_modeled_rate_plans()
    check_states(estimates, modeled)
    coverage, total_res, total_cov = compute_coverage(estimates, modeled)

    print(render_text(coverage, total_res, total_cov, estimates))

    if args.write_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        md = render_markdown(coverage, total_res, total_cov, modeled, estimates)
        REPORT_PATH.write_text(md)
        print(f"\nWrote Markdown report to {REPORT_PATH.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
