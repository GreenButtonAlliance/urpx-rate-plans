#!/usr/bin/env python3
"""Compute corpus coverage of California residential utility customers.

Walks the ca/<class>/<utility>/<schedule>/versions/<date>/ tree, matches
each modeled rate plan against dev/coverage-estimates.toml, and reports:

  - Per-utility: residential customers, modeled tariffs, covered count, %
  - Statewide: total residential, total covered, overall coverage %
  - Largest unmodeled targets (prioritization signal)

Also emits reports/coverage.md as a human-readable summary suitable for
linking from README.md.

Usage:
    source ~/env/py/p3newa/bin/activate
    python dev/coverage.py                  # print to stdout
    python dev/coverage.py --write-report   # also write reports/coverage.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # Python 3.10 and earlier
from collections import defaultdict
from dataclasses import dataclass, field

REPO_ROOT = Path(__file__).resolve().parent.parent
ESTIMATES_PATH = REPO_ROOT / "dev" / "coverage-estimates.toml"
REPORT_PATH = REPO_ROOT / "reports" / "coverage.md"
CORPUS_ROOT = REPO_ROOT / "ca"


@dataclass
class ModeledTariff:
    utility: str
    schedule: str
    versions: list[str] = field(default_factory=list)
    is_modifier: bool = False


@dataclass
class UtilityCoverage:
    utility_id: str
    name: str
    util_class: str
    total_residential: int
    modeled_tariffs: list[str] = field(default_factory=list)
    unmodeled_tariffs: list[str] = field(default_factory=list)
    covered_count: int = 0

    @property
    def coverage_pct(self) -> float:
        if self.total_residential == 0:
            return 0.0
        return 100.0 * self.covered_count / self.total_residential


def discover_modeled_tariffs() -> dict[tuple[str, str], ModeledTariff]:
    """Walk ca/.../versions/.../rate-plan_*.jsonld; return {(util, sched): info}."""
    found: dict[tuple[str, str], ModeledTariff] = {}
    for jsonld in CORPUS_ROOT.rglob("rate-plan*_*.jsonld"):
        parts = jsonld.relative_to(CORPUS_ROOT).parts
        # parts: (class, utility, schedule, "versions", date, filename)
        if len(parts) < 6 or parts[3] != "versions":
            continue
        util = parts[1]
        sched = parts[2]
        date = parts[4]
        is_modifier = jsonld.name.startswith("rate-plan-modifier_")
        key = (util, sched)
        if key not in found:
            found[key] = ModeledTariff(util, sched, is_modifier=is_modifier)
        found[key].versions.append(date)
    for tariff in found.values():
        tariff.versions.sort()
    return found


def load_estimates() -> dict:
    with ESTIMATES_PATH.open("rb") as f:
        return tomllib.load(f)


def compute_coverage(
    estimates: dict,
    modeled: dict[tuple[str, str], ModeledTariff],
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


def render_markdown(
    coverage: list[UtilityCoverage],
    total_residential: int,
    total_covered: int,
    modeled: dict[tuple[str, str], ModeledTariff],
) -> str:
    pct = 100.0 * total_covered / total_residential if total_residential else 0.0
    lines: list[str] = []
    lines.append("# CA Residential Tariff Corpus Coverage")
    lines.append("")
    lines.append(
        "Auto-generated by `dev/coverage.py` from `dev/coverage-estimates.toml`. "
        "Do not edit by hand — refine the estimates TOML and re-run."
    )
    lines.append("")
    lines.append("## Statewide")
    lines.append("")
    lines.append(f"- Total residential customers tracked: **{total_residential:,}**")
    lines.append(f"- Customers covered by modeled tariffs: **{total_covered:,}**")
    lines.append(f"- Coverage: **{pct:.1f}%**")
    lines.append("")
    lines.append("## Per-utility")
    lines.append("")
    lines.append(
        "| Utility | Class | Residential | Covered | % | Modeled tariffs |"
    )
    lines.append("|---|---|---:|---:|---:|---|")
    for cov in coverage:
        modeled_str = ", ".join(cov.modeled_tariffs) if cov.modeled_tariffs else "—"
        lines.append(
            f"| {cov.name} | {cov.util_class} | {cov.total_residential:,} | "
            f"{cov.covered_count:,} | {cov.coverage_pct:.1f}% | {modeled_str} |"
        )
    lines.append("")

    # Prioritization: largest unmodeled-customer pools.
    lines.append("## Largest unmodeled customer pools")
    lines.append("")
    lines.append(
        "Sorted by number of residential customers without a modeled default. "
        "Top of list = highest-leverage modeling work."
    )
    lines.append("")
    unmodeled = [c for c in coverage if c.coverage_pct < 99.5]
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
    lines.append("| Utility | Schedule | Type | Versions |")
    lines.append("|---|---|---|---|")
    for (util, sched), info in sorted(modeled.items()):
        kind = "modifier" if info.is_modifier else "rate-plan"
        lines.append(f"| {util} | {sched} | {kind} | {', '.join(info.versions)} |")
    lines.append("")
    return "\n".join(lines)


def render_text(
    coverage: list[UtilityCoverage],
    total_residential: int,
    total_covered: int,
) -> str:
    pct = 100.0 * total_covered / total_residential if total_residential else 0.0
    lines = []
    lines.append("=" * 78)
    lines.append("CA RESIDENTIAL TARIFF CORPUS COVERAGE")
    lines.append("=" * 78)
    lines.append(f"Total residential customers tracked:  {total_residential:>12,}")
    lines.append(f"Covered by modeled tariffs:           {total_covered:>12,}")
    lines.append(f"Statewide coverage:                       {pct:>6.1f}%")
    lines.append("")
    lines.append(
        f"{'Utility':<48}{'Class':<6}{'Residential':>13}"
        f"{'Covered':>11}{'%':>7}"
    )
    lines.append("-" * 85)
    for cov in coverage:
        lines.append(
            f"{cov.name[:46]:<48}{cov.util_class:<6}"
            f"{cov.total_residential:>13,}{cov.covered_count:>11,}"
            f"{cov.coverage_pct:>6.1f}%"
        )
    lines.append("")
    lines.append("Top unmodeled customer pools (largest first):")
    unmodeled = [c for c in coverage if c.coverage_pct < 99.5]
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
    modeled = discover_modeled_tariffs()
    coverage, total_res, total_cov = compute_coverage(estimates, modeled)

    print(render_text(coverage, total_res, total_cov))

    if args.write_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        md = render_markdown(coverage, total_res, total_cov, modeled)
        REPORT_PATH.write_text(md)
        print(f"\nWrote Markdown report to {REPORT_PATH.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
