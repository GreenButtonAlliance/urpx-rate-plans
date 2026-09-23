#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Every clj-urpx version named in prose must be the one deps.edn pins.

WHY THIS EXISTS. Fifty-seven filing manifests described consumer behaviour as of
clj-urpx 0.25.0 while deps.edn pinned 0.31.0, in 128 separate mentions, for six
releases. Nothing noticed, because nothing compared the two. The claims are not
decoration: they are the reason a deferral exists at all, of the form "the gate is
inert at clj-urpx X, so building it would charge every customer". A stale version
there is a claim about a release nobody runs.

WHAT IT DOES NOT DO. It does not check that the CLAIM is true, only that the
version named is the one in use. Whether 0.31.0 still evaluates no
ConditionExpression is a question for the library's source, and the answer is
recorded beside each claim when it is verified. This check exists so that the next
bump cannot silently invalidate 128 sentences: it turns a question nobody asks
into one the gate asks on every run.

A DATED OBSERVATION IS THE POINT. The alternative spelling, "the pinned consumer",
never goes stale and never says anything either: it stays true across a bump that
changes the behaviour it describes. Naming the version makes the sentence
checkable, and this file is what checks it.

Run from the repo root:  python3 dev/lint_consumer_version.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

DEPS = REPO / "deps.edn"
COORD = "energy.grid-coordination/clj-urpx"

# The version must follow the library name with nothing between but whitespace and
# a comparison word. Measured over the corpus, the forms in use are "clj-urpx X"
# (213) and "clj-urpx <= X" (1).
#
# The connector is deliberately narrow. A looser one that merely skipped ahead
# matched "clj-urpx (URPX v0.5.1)" 71 times and reported the ONTOLOGY version as a
# stale consumer version. Two different products' versions sit next to each other
# in this prose, so proximity alone does not identify which is which.
MENTION = re.compile(r"clj-urpx\s*(?:[<>]=?|\u2264|\u2265|at|version)?\s*v?(\d+\.\d+\.\d+)")


def _shown(path: Path) -> str:
    """Repo-relative where possible. Building the message must not be able to throw:
    an error path that raises turns a clear refusal into a traceback."""
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def pinned() -> str:
    if not DEPS.exists():
        raise SystemExit(f"ERROR: {_shown(DEPS)} is missing, so there is no "
                         f"pinned version to compare against and every mention would "
                         f"pass. Refusing.")
    text = DEPS.read_text()
    m = re.search(re.escape(COORD) + r"\s*\{\s*:mvn/version\s+\"([^\"]+)\"", text)
    if not m:
        raise SystemExit(f"ERROR: {_shown(DEPS)} does not pin {COORD} in a "
                         f"shape this can read, so nothing can be compared. Refusing "
                         f"rather than reporting clean.")
    return m.group(1)


# A version named as history is not a claim about the pin. "since clj-urpx 0.26.0
# the omission is no longer silent" stays true forever and must not be bumped;
# "clj-urpx 0.26.0 evaluates no ConditionExpression" is a present-tense claim and
# must name the pin. The difference is the connector, so only these are exempt.
# Note "at clj-urpx X" is NOT here: the corpus uses it for the present tense
# ("declarative at clj-urpx X").
HISTORICAL = re.compile(r"(?:since|as of|before|prior to|after|until|landed in|"
                        r"introduced in|added in|fixed in)\s+$", re.I)


def scan() -> list[tuple[Path, int, str]]:
    """(path, line number, version) for every clj-urpx version named as current.

    A historical reference is skipped, not bumped. Getting this wrong in either
    direction is bad: bumping a "since 0.26.0" rewrites history into a falsehood,
    and exempting too much lets a present-tense claim rot, which is the whole
    failure this file exists to catch.
    """
    out = []
    targets = list(corpus.tariff_tomls()) + list(corpus.utility_tomls())
    targets += sorted((REPO / "doc").glob("*.md"))
    targets += [REPO / n for n in ("README.md", "LAYOUT.md", "MODELING-GAPS.md",
                                   "CONTRIBUTING.md")]
    for path in targets:
        if not path.exists():
            continue
        for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            for m in MENTION.finditer(line):
                if HISTORICAL.search(line[max(0, m.start() - 16):m.start()]):
                    continue
                out.append((path, i, m.group(1)))
    return out


def main() -> int:
    want = pinned()
    mentions = scan()
    # An empty result is the dangerous case: it means the pattern stopped matching,
    # not that the corpus stopped making claims. Refuse rather than report clean.
    corpus.require_nonempty(mentions, "clj-urpx version mentions in prose")

    wrong = [(p, i, v) for p, i, v in mentions if v != want]
    files = {p for p, _, _ in mentions}
    if wrong:
        print(f"clj-urpx version: {len(wrong)} stale mention(s) in "
              f"{len({p for p, _, _ in wrong})} file(s); deps.edn pins {want}\n",
              file=sys.stderr)
        for p, i, v in wrong[:40]:
            print(f"  {p.relative_to(REPO)}:{i}: names {v}", file=sys.stderr)
        if len(wrong) > 40:
            print(f"  ... and {len(wrong) - 40} more", file=sys.stderr)
        print(f"\n  These are behavioural claims, not version numbers: each one says what "
              f"the\n  consumer does, and a deferral usually rests on it. Re-verify the claim "
              f"against\n  {want} before changing the number, because the behaviour may have "
              f"changed too.", file=sys.stderr)
        return 1

    print(f"clj-urpx version: clean ({len(mentions)} mention(s) in {len(files)} file(s), "
          f"all naming {want}, the version deps.edn pins)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
