#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Check MODELING-GAPS.md against the per-filing deferrals it summarises.

The same fact is written down twice in this corpus. A filing records what it
could not model in its own `tariff.toml [modeling].deferrals`, written while
someone was actually trying to model the thing. MODELING-GAPS.md states the
corpus-wide view, written earlier and revisited rarely. Nothing compared them,
and on 2026-09-23 they had disagreed for two days: three entries were listed as
inexpressible while the filings they named said, in their own words,
"Expressible under v0.5.1 ... This is work, not a blocker", "Buildable now with
no new vocabulary", and "which is wrong as written".

Two things are checked, both deliberately narrow, because a claim about a
standard is a judgement and a lint that second-guesses it would cry wolf.

  1. Every filing a "cannot express" bullet names must exist. A bullet that
     bites a schedule nobody can find is stale.
  2. Every "cannot express" bullet must be backed by at least one deferral, in
     a filing it names, that asserts an upstream gap. If every deferral in
     every named filing says the thing is expressible, the bullet is
     unsupported by the corpus it claims to describe. That is exactly the
     shape of the 2026-09-23 divergence.

What is NOT checked: whether a gap is real. Only whether the two places that
record it still agree.

Exit 0 clean, 1 on any violation.
"""
from __future__ import annotations

import pathlib
import re
import sys


REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402
import utilities  # noqa: E402
GAPS = REPO / "MODELING-GAPS.md"
FIRST_LIST = "## We have not found a way to express these"
SECOND_LIST = "## Not yet modeled"

# A deferral asserting the standard is short of something. Phrasings vary
# because these are written by hand, one filing at a time; the set grew when
# "genuinely missing upstream" turned out to be how the EV2 manifest says it.
GAP_CLAIM = re.compile(
    r"not expressible|cannot be expressed|no way to express|has no expression"
    r"|missing upstream|names no |no standard named|not available in v0\.5\.1", re.I)

# A deferral asserting the opposite, which is what makes a bullet suspect.
BUILDABLE_CLAIM = re.compile(
    r"expressible under|buildable now|shacl[- ]conforms|conforms against"
    r"|work, not a blocker|wrong as written", re.I)

# Display name -> slug for every utility with filings, from the utility.toml
# manifests, so a utility in a new state is matched without editing this file.
UTIL_SLUG = {u.short_name: u.slug for u in utilities.ordered()}


def deferrals() -> dict[tuple[str, str], list[str]]:
    """(utility, schedule) -> its deferral texts."""
    out: dict[tuple[str, str], list[str]] = {}
    # Discovery and decomposition both through dev/corpus.py. The glob here
    # hardcoded the subdivision and the carrier, so a filing outside us/ca or a
    # second commodity would have been skipped silently; the key was read with
    # indices counted from the end, which survives an inserted level at the front
    # by accident rather than by design.
    for f in corpus.tariff_tomls():
        key = tuple(corpus.parse_filing_path(f)[:2])   # utility, schedule
        d = corpus.load_toml(f)
        out.setdefault(key, []).extend(
            " ".join(str(x).split()) for x in ((d.get("modeling") or {}).get("deferrals") or []))
    return out


def named_filings(bullet: str, known: dict) -> set[tuple[str, str]]:
    """Filings a bullet names, matched as "<utility> <schedule>".

    Matching the schedule token alone is wrong: a bullet citing CPAU Section
    D.7.a would match SCE's Schedule D. The utility has to be adjacent.
    """
    found: set[tuple[str, str]] = set()
    for u, util_slug in UTIL_SLUG.items():
        for m in re.finditer(re.escape(u) + r"\s+([A-Za-z][A-Za-z0-9-]{0,24})", bullet):
            slug = m.group(1).lower().rstrip(".,;:")
            key = (util_slug, slug)
            if key in known:
                found.add(key)
    return found


def main() -> int:
    if not GAPS.exists():
        print(f"REFUSING: {GAPS.name} is missing, so there is nothing to compare "
              f"the filings against.", file=sys.stderr)
        return 1
    text = GAPS.read_text()
    for marker in (FIRST_LIST, SECOND_LIST):
        if marker not in text:
            print(f"REFUSING: {GAPS.name} has no section starting {marker!r}. The "
                  f"headings changed, and comparing against the wrong section would "
                  f"pass while checking nothing.", file=sys.stderr)
            return 1

    section = text[text.index(FIRST_LIST):text.index(SECOND_LIST)]
    bullets = [l for l in section.split("\n") if l.startswith("- ")]
    if not bullets:
        print("REFUSING: the inexpressible list is empty, so every check below "
              "would pass without comparing anything.", file=sys.stderr)
        return 1

    known = deferrals()
    if not known:
        print("REFUSING: no tariff.toml carries a [modeling] section.", file=sys.stderr)
        return 1

    problems: list[str] = []
    for b in bullets:
        thread = re.search(r"(?:discussions|issues)/(\d+)", b)
        tag = f"#{thread.group(1)}" if thread else b[2:42]
        named = named_filings(b, known)
        if not named:
            problems.append(f"{tag}: names no filing in this corpus, so nothing "
                            f"anchors the claim to anything that can be checked")
            continue
        backed = {k for k in named if any(GAP_CLAIM.search(t) for t in known[k])}
        if not backed:
            says_yes = sorted(f"{u}/{s}" for u, s in named
                              if any(BUILDABLE_CLAIM.search(t) for t in known[(u, s)]))
            problems.append(
                f"{tag}: listed as inexpressible, but no deferral in the filing(s) it "
                f"names ({', '.join(f'{u}/{s}' for u, s in sorted(named))}) asserts an "
                f"upstream gap"
                + (f"; these assert the opposite: {', '.join(says_yes)}" if says_yes else ""))

    if problems:
        print(f"modeling gaps: {len(problems)} problem(s)\n", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        print("\nMODELING-GAPS.md and a filing's [modeling].deferrals record the same\n"
              "fact. When they disagree the filing is usually right, because it was\n"
              "written while someone was modelling the thing.", file=sys.stderr)
        return 1

    n = sum(len(v) for v in known.values())
    print(f"modeling gaps: clean ({len(bullets)} inexpressible claim(s), each backed by "
          f"a deferral in a filing it names, over {n} deferral(s) in {len(known)} schedule(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
