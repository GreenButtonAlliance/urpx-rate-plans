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

The roots and globs are read from corpus.json at the repository root, the one
declaration of the layout that the Clojure, babashka and bash walkers also read.
They are depth-INDEPENDENT: a filing is any directory matching
`**/versions/<date>/` that holds a tariff.toml, and `versions/` appears nowhere
else in the repository. The next restructure changes nothing here.

Run as a script it is this corpus's Python walker (see corpus.json): no
arguments prints the document paths, kind names print those kinds, and --all
prints every kind as kind<TAB>path.

`require_nonempty` exists because an empty result is the dangerous case, not the
loud one. Call it before reporting a verdict.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LAYOUT = json.loads((REPO / "corpus.json").read_text())

# Top-level country directories. Adding a country means adding it to corpus.json.
COUNTRY_ROOTS = tuple(LAYOUT["roots"])


def _glob(pattern: str) -> list[Path]:
    out: list[Path] = []
    for root in COUNTRY_ROOTS:
        out.extend((REPO / root).glob(pattern))
    return sorted(out)


def paths(*kinds: str) -> list[Path]:
    """Every file of the given kinds, as corpus.json declares them; with no
    kinds, the kinds corpus.json lists as documents."""
    out: set[Path] = set()
    for kind in kinds or LAYOUT["documents"]:
        for pattern in LAYOUT["kinds"][kind]["include"]:
            out.update(_glob(pattern))
    return sorted(out)


def filing_dirs() -> list[Path]:
    """Every per-filing directory (the one holding tariff.toml)."""
    return [p.parent for p in paths("tariff-manifest")]


def tariff_tomls() -> list[Path]:
    return paths("tariff-manifest")


def rate_plan_files() -> list[Path]:
    """Base RatePlan filings only."""
    return paths("rate-plan")


def modifier_files() -> list[Path]:
    """Standalone RatePlanModifier filings only."""
    return paths("rate-plan-modifier")


def all_filing_jsonld() -> list[Path]:
    """Both of the above."""
    return sorted(rate_plan_files() + modifier_files())


def utility_tomls() -> list[Path]:
    return paths("utility-manifest")


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


def utility_dir(path: Path) -> Path:
    """The <country>/<subdivision>/<utility>/ directory holding a filing path,
    anchored on `versions` as parse_filing_path is."""
    parts = path.resolve().relative_to(REPO).parts
    parse_filing_path(path)
    return REPO.joinpath(*parts[:parts.index("versions") - 2])


def subdivision_of(path: Path) -> str:
    """The subdivision (state) code for a filing path, e.g. "ca" or "wa"."""
    return utility_dir(path).parent.name


# Manifest filenames. Spelled in one place because three different files
# spelled them, and a rename would have had to find all three.
TARIFF_MANIFEST = "tariff.toml"
UTILITY_MANIFEST = "utility.toml"

# The carrier segment. Currently always electricity; it exists so that a second
# commodity does not require a fourth spelling of the path shape.
DEFAULT_CARRIER = "electricity"


def load_toml(path) -> dict:
    """Parse a TOML file. The stdlib gained tomllib in 3.11 and this runs on 3.10,
    so the fallback lives here once instead of in each of the seven callers that
    had their own copy of the try/except.
    """
    try:
        import tomllib
    except ModuleNotFoundError:            # Python < 3.11
        import tomli as tomllib
    return tomllib.loads(Path(path).read_text())


def utilities() -> list[str]:
    """Every utility slug with a discovery manifest, filings or not."""
    return sorted({p.parent.name for p in utility_tomls()})


def utilities_with_filings() -> list[str]:
    """Only the utilities that actually have a filing."""
    return sorted(schedules_by_utility())


def schedules_by_utility() -> dict[str, set[str]]:
    """{utility slug -> every schedule slug it has a filing for}.

    Promoted from dev/list_rate_plans_to_model.py, which had the only correct
    copy. The other copy lived in scripts/build-midas-coverage-report.py and
    walked a tree deleted on 2026-09-20, so it returned {} and reported success.
    """
    out: dict[str, set[str]] = {}
    for jsonld in all_filing_jsonld():
        util, sched, _ = parse_filing_path(jsonld)
        out.setdefault(util, set()).add(sched)
    require_nonempty(out, "schedules by utility")
    return out


def is_base_rate_plan_dir(d: Path) -> bool:
    return any(d.glob("rate-plan_*.jsonld"))


def is_modifier_dir(d: Path) -> bool:
    return any(d.glob("rate-plan-modifier_*.jsonld"))


def filing_dir(utility: str, schedule: str, date: str,
               subdivision: str | None = None, country: str = "us",
               carrier: str = DEFAULT_CARRIER) -> Path:
    """Compose the path to one filing directory, and REFUSE if it is not there.

    Composition is the one direction this module could not do. Decomposition
    existed (parse_filing_path), so 29 call sites across 11 scripts spelled the
    forward path by hand, every one of them still naming the pre-2026-09-20
    `ca/<class>/<utility>/<schedule>/` shape.

    The refusal is the point, not a convenience. Those scripts write with
    `OUT.parent.mkdir(parents=True)`, so a stale path does not fail: it creates a
    tree COUNTRY_ROOTS does not walk, writes the filing into it, and prints the
    byte count. Every lint then passes over a corpus that quietly lost the file.
    Resolving through here turns that silent success into a refusal.

    With no `subdivision`, it is the one directory under `country` that holds a
    `utility` directory, so a caller does not name the state.
    """
    if subdivision is None:
        homes = sorted(p.parent.name for p in (REPO / country).glob(f"*/{utility}")
                       if p.is_dir())
        if len(homes) != 1:
            raise SystemExit(
                f"ERROR: utility {utility!r} sits under {len(homes)} subdivisions of "
                f"{country}/ ({homes}); pass subdivision= to say which.")
        subdivision = homes[0]
    d = REPO / country / subdivision / utility / carrier / schedule / "versions" / date
    if not d.is_dir():
        raise SystemExit(
            f"ERROR: no filing directory at {d.relative_to(REPO)}. Refusing rather "
            f"than creating it: a path the corpus does not already recognize is a "
            f"stale path, and writing to it loses the filing silently."
        )
    return d


def filing_path(utility: str, schedule: str, date: str, kind: str = "rate-plan",
                **kw) -> Path:
    """The JSON-LD file inside a filing directory. `kind` is rate-plan or
    rate-plan-modifier, matching the two globs above."""
    if kind not in ("rate-plan", "rate-plan-modifier"):
        raise ValueError(f"kind must be rate-plan or rate-plan-modifier, got {kind!r}")
    return filing_dir(utility, schedule, date, **kw) / \
        f"{kind}_{utility}_{schedule}_{date}.jsonld"


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


def _main(argv: list[str]) -> None:
    rel = lambda p: p.relative_to(REPO).as_posix()
    if argv == ["--all"]:
        lines = [f"{k}\t{rel(p)}" for k in LAYOUT["kinds"] for p in paths(k)]
    else:
        lines = [rel(p) for p in paths(*argv)]
    sys.stdout.write("".join(f"{line}\n" for line in sorted(lines)))


if __name__ == "__main__":
    _main(sys.argv[1:])
