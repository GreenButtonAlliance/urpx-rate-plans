#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Every version named in prose must be the one actually in force.

Two authorities, because there are two versioned things and each has its own
source of truth. The CONSUMER version is pinned in deps.edn. The STANDARD version
is declared by the filings themselves, in urpx:targetURPXVersion, which is better
authority than any constant here because it is what the documents assert about
themselves.

WHY THIS EXISTS. Fifty-seven filing manifests described consumer behaviour as of
clj-urpx 0.25.0 while deps.edn pinned 0.31.0, in 128 separate mentions, for six
releases. Nothing noticed, because nothing compared the two. The claims are not
decoration: they are the reason a deferral exists at all, of the form "the gate is
inert at clj-urpx X, so building it would charge every customer". A stale version
there is a claim about a release nobody runs.

Four filing READMEs said "serialized against URPX v0.2.0" while their own JSON-LD
declared v0.5.1, and that sat for months for the same reason: the prose and the
document were never compared. One generator still emitted targetURPXVersion v0.2.0
against a corpus where every filing declared v0.5.1.

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

Run from the repo root:  python3 dev/lint_declared_versions.py
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
                        r"introduced in|added in|fixed in|through|up to|"
                        r"earlier than|no longer in)\s+$", re.I)


def scan() -> tuple[list[tuple[Path, int, str]], int]:
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
    # The FILINGS THEMSELVES, and this is the half that was missing. This check
    # swept .md and .toml only, so six CoverageClaim Evaluations kept naming
    # clj-urpx 0.25.0 through the day the manifests were corrected to 0.31.0, and
    # the gate passed on every run. A urpx:description is worse prose to get wrong
    # than a README: its reader already believes the document and has no second
    # source. Scanning the raw JSON text rather than parsed nodes is deliberate, so
    # that a version named in any property is caught, not only the ones a walker
    # knows about.
    targets += list(corpus.all_filing_jsonld())
    for path in targets:
        if not path.exists():
            continue
        for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            for m in MENTION.finditer(line):
                if HISTORICAL.search(line[max(0, m.start() - 16):m.start()]):
                    continue
                out.append((path, i, m.group(1)))
    return out, len([t for t in targets if t.exists()])


# Matched POSITIVELY, on the forms that assert what a filing targets NOW, rather
# than by exempting historical ones. An exemption list is the losing shape here:
# dev/list_california_parties.py records the same lesson in NOT_A_PARTY_PATTERN,
# that a rule enumerating its exceptions keeps missing one. It did here too. A
# first version matched every "URPX vX" and then tried to subtract history, and it
# flagged three correct sentences: "carried it through to URPX v0.2.0", "has been
# in URPX v0.2.0 since the initial release", and "URPXDocument was retired at URPX
# v0.3.0". Each is true and none is a claim about this filing's target.
#
# The cost is the opposite error: a stale claim in a phrasing not listed here goes
# unseen. That is the safer direction, because a missed claim leaves the status quo
# while a false positive pressures someone into rewriting a correct sentence.
URPX_MENTION = re.compile(
    r"(?:seriali[sz]ed|validates?|conforms?|modeled|authored|written|built)\s+"
    r"(?:clean\s+)?(?:against|to|under|for)\s+(?:the\s+)?URPX\s*[*_]{0,2}\s*v?(\d+\.\d+\.\d+)"
    r"|(?:targets?|targetURPXVersion)\s*:?\s*(?:the\s+)?URPX\s*[*_]{0,2}\s*v?(\d+\.\d+\.\d+)"
    r"|[Pp]atterns applied \(URPX\s*[*_]{0,2}\s*v?(\d+\.\d+\.\d+)",
    re.I)
URPX_TARGET = re.compile(r'"urpx:targetURPXVersion"\s*:\s*"[^"]*?/v(\d+\.\d+\.\d+)/')


def declared_urpx() -> str:
    """The URPX version the filings declare, which must be unanimous.

    Taken from urpx:targetURPXVersion rather than stated here, because the
    documents' own assertion is the authority and a constant in this file would be
    a second place for it to drift. A split corpus refuses: with two answers there
    is no single version for prose to agree with, and picking the majority would
    hide exactly the disagreement worth seeing.
    """
    seen: dict[str, list[str]] = {}
    for f in corpus.all_filing_jsonld():
        for m in URPX_TARGET.finditer(f.read_text(errors="replace")):
            seen.setdefault(m.group(1), []).append(f.name)
    if not seen:
        raise SystemExit("ERROR: no filing declares urpx:targetURPXVersion, so there is "
                         "no version for prose to be checked against. Refusing.")
    if len(seen) > 1:
        detail = "; ".join(f"{v} in {len(fs)} filing(s)" for v, fs in sorted(seen.items()))
        raise SystemExit(f"ERROR: the corpus declares more than one targetURPXVersion "
                         f"({detail}). Prose cannot be checked against a split corpus, and "
                         f"the split is the thing to fix.")
    return next(iter(seen))


def scan_urpx() -> tuple[list[tuple[Path, int, str]], int]:
    """URPX versions named as current, in filing READMEs and the top-level docs."""
    out = []
    targets = [d / "README.md" for d in corpus.filing_dirs()]
    targets += sorted((REPO / "doc").glob("*.md"))
    targets += [REPO / n for n in ("README.md", "LAYOUT.md", "MODELING-GAPS.md",
                                   "CONTRIBUTING.md")]
    for path in targets:
        if not path.exists():
            continue
        for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            for m in URPX_MENTION.finditer(line):
                ver = next(g for g in m.groups() if g)
                out.append((path, i, ver))
    return out, len([t for t in targets if t.exists()])


def report(label: str, mentions, want: str, authority: str, files_read: int) -> int:
    # The denominator here is FILES READ, not mentions found. Zero mentions was a
    # collapsed-denominator signal while filings restated the consumer version in
    # their prose; since LAYOUT.md 4.4 forbids that, zero is the state this check
    # exists to keep. Refusing on it would turn the finished job into a failure.
    # What still has to be non-empty is the set of files opened: if that is zero
    # the tree moved and nothing was compared.
    corpus.require_nonempty(range(files_read), f"{label} prose files read")
    wrong = [(p, i, v) for p, i, v in mentions if v != want]
    if wrong:
        print(f"{label} version: {len(wrong)} stale mention(s) in "
              f"{len({p for p, _, _ in wrong})} file(s); {authority} says {want}\n",
              file=sys.stderr)
        for p, i, v in wrong[:40]:
            print(f"  {_shown(p)}:{i}: names {v}", file=sys.stderr)
        if len(wrong) > 40:
            print(f"  ... and {len(wrong) - 40} more", file=sys.stderr)
        return 1
    print(f"{label} version: clean ({len(mentions)} mention(s) in "
          f"{len({p for p, _, _ in mentions})} file(s), all naming {want}, "
          f"per {authority})")
    return 0


def main() -> int:
    # Both checks always run, and the worse exit code wins. Stopping at the first
    # failure would report one stale version and hide the other, which is how a
    # corpus ends up fixing the same class of drift twice.
    hits, files = scan()
    rc = report("clj-urpx", hits, pinned(), "deps.edn", files)
    if rc:
        print(f"\n  A clj-urpx mention is a behavioural claim, not a version number: each "
              f"says\n  what the consumer does, and a deferral usually rests on it. "
              f"Re-verify the\n  claim against the pin before changing the number, because "
              f"the behaviour may\n  have changed too.", file=sys.stderr)
    uhits, ufiles = scan_urpx()
    rc |= report("URPX", uhits, declared_urpx(), "urpx:targetURPXVersion", ufiles)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
