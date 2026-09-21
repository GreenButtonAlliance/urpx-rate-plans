#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Corpus discovery, in one place.

Every generator, lint and validator finds filings through this module. They used
to carry their own globs: fourteen of them across nine files, all hardcoding the
`ca/<class>/<utility>/<schedule>/versions/<date>/` depth. The restructure to
`us/<subdivision>/<utility>/<carrier>/…` changed that depth, and a stale glob does
not fail, it returns nothing, which every caller then reports as success over an
empty corpus.

So the globs here are depth-INDEPENDENT. A filing is any directory matching
`**/versions/<date>/` that holds a tariff.toml, and `versions/` appears nowhere
else in the repository. The next restructure changes nothing here.

`require_nonempty` exists because an empty result is the dangerous case, not the
loud one. Call it before reporting a verdict.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Top-level country directories. Adding a country means adding it here, nowhere else.
COUNTRY_ROOTS = ("us",)


def _glob(pattern: str) -> list[Path]:
    out: list[Path] = []
    for root in COUNTRY_ROOTS:
        out.extend((REPO / root).glob(pattern))
    return sorted(out)


def filing_dirs() -> list[Path]:
    """Every per-filing directory (the one holding tariff.toml)."""
    return [p.parent for p in _glob("**/versions/*/tariff.toml")]


def tariff_tomls() -> list[Path]:
    return _glob("**/versions/*/tariff.toml")


def rate_plan_files() -> list[Path]:
    """Base RatePlan filings only."""
    return _glob("**/versions/*/rate-plan_*.jsonld")


def modifier_files() -> list[Path]:
    """Standalone RatePlanModifier filings only."""
    return _glob("**/versions/*/rate-plan-modifier_*.jsonld")


def all_filing_jsonld() -> list[Path]:
    """Both of the above."""
    return sorted(rate_plan_files() + modifier_files())


def utility_tomls() -> list[Path]:
    return _glob("*/*/utility.toml")


def parse_filing_path(path: Path) -> tuple[str, str, str]:
    """(utility, schedule, date) for any path inside a filing directory.

    Anchored on the `versions` segment rather than counted from either end:
        …/<country>/<subdivision>/<utility>/<carrier>/<schedule>/versions/<date>/…

    Positional indices are how this broke. The restructure that added the `us/`
    level left four callers reading `parts[2]`, `parts[3]`, `parts[5]` against
    the old shape, so they silently read the carrier as the schedule and the
    literal string "versions" as the date, and `coverage.py`'s guard rejected
    every file in the corpus while its generator exited 0. The globs in this
    module were made depth-independent after a restructure broke fourteen of
    them; the indices never were.
    """
    parts = path.resolve().relative_to(REPO).parts
    try:
        i = parts.index("versions")
    except ValueError:
        raise ValueError(f"not inside a filing directory (no 'versions' segment): {path}")
    if i < 3 or i + 1 >= len(parts):
        raise ValueError(f"malformed filing path: {path}")
    return parts[i - 3], parts[i - 1], parts[i + 1]


def utility_of(path: Path) -> str:
    """The utility slug for a corpus path."""
    return parse_filing_path(path)[0]


def require_nonempty(items, what: str) -> None:
    """Refuse to report a verdict over an empty corpus.

    A restructure that breaks discovery makes every check pass trivially. That
    reads as success and is the opposite of it.
    """
    if not items:
        raise SystemExit(
            f"ERROR: corpus discovery found no {what}. Either the tree moved and "
            f"dev/corpus.py was not updated, or this is not the repository root. "
            f"Refusing to report a result over an empty corpus."
        )
