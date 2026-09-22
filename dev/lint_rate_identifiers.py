#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Refuse a MIDAS rate identifier whose party segment occurs in no MIDAS record.

The corpus cites CEC MIDAS Rate Identification Numbers as provenance notes on
the prices they attest. Nothing checked their shape, and five of the twenty-four
were malformed for months: the SDG&E net-billing filing cites
`USCA-XXSD-NB00/NB23/NB24/NB25/NB26-0000`, recorded by
scripts/extract-sdge-nbt-eec-values.py as a "Generation EEC" family. There is no
such family. The generation component is not published separately at all; where
it is needed it must be derived by subtracting the delivery-only rate from the
bundled one, which is the method this corpus already records for SCE and then
contradicted for SDG&E. See doc/midas-rins-and-service-arrangements.md.

WHY THE CHECK IS HERE AND NOT IN clj-urpx. `urpx:RatePlanIdentifier` models
`skos:notation` as a plain string, so a malformed notation validates exactly as
a correct one does, and no consumer can tell them apart. The grammar that does
tell them apart is not part of URPX: it is read off a California snapshot this
repository holds, and a general-purpose validator has no reason to carry it.

THE GRAMMAR IS DERIVED, NEVER DECLARED. Every attested prefix and party segment
is read out of reports/midas-coverage.json at run time. A list written into this
file would be a second place the truth lives, and it would go stale the moment
the snapshot is refreshed. If the snapshot is absent, unreadable, or yields no
party segments, this REFUSES: a check that cannot find its own reference data
has compared nothing, and reporting that as a pass is how this repository has
accumulated gates that verify nothing.

TWO FINDINGS, DELIBERATELY NOT MERGED, because they are not equally strong:

  FAIL    the identifier violates the FORMAT: it does not split into four
          dash-separated groups, or its prefix is not one the snapshot ever
          publishes. Format is decidable from any sample.

          An unattested PARTY SEGMENT is deliberately NOT a failure, and that is
          a correction. This check first failed the five USCA-XXSD-NB*-0000 on
          the reasoning that no snapshot segment begins "XX", so "XX"-first must
          be malformed. That reasoning does not hold. The absence falls on the
          RATE CODE, not the segment: both USCA-XXSD-NB##-0000 and their
          USCA-SDXX-NB##-0000 siblings are absent, 5 of 5 on each side, and
          5,204 of the snapshot's 5,207 rate codes are numeric while the NB
          family is not. The segment reads coherently as the mirror of the
          delivery-only code, which is how a generation-only series would have to
          be written; scripts/build-midas-coverage-report.py queries
          DistributionCode=XX and labels it "CCA generation index"; and the
          strings are not composed here at all, being read out of the RIN column
          of SDG&E's own MIDAS-format upload ZIPs. So the snapshot's segment set
          is a SAMPLE, not a grammar, and failing on it would assert that a
          months-old snapshot enumerates what MIDAS can issue.

  REPORT  the identifier is well formed but does not appear in the snapshot.
          That is a statement about the snapshot's contents, and the snapshot is
          dated and cannot currently be refreshed (the MIDAS token endpoint
          returns 401 to the stored credentials). "Absent from a months-old
          snapshot" is not "does not exist", so failing the gate on it would
          make the gate depend on the freshness of a file nobody can refresh.

Identifiers are found by scanning every file of every filing directory, not by
reading a list and not by looking in one property. They live in `urpx:name` free
text today; that is an observation this file prints, not an assumption it makes.

Exit codes: 0 clean, 1 a violation, 3 the harness could not answer.

Usage:
    python3 dev/lint_rate_identifiers.py [--json] [--snapshot PATH]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

MIDAS = REPO / "reports" / "midas-coverage.json"

# The candidate-token shape, deliberately looser than any real identifier: four
# dash-separated alphanumeric groups. It decides what gets CHECKED, never what
# passes. Anchoring it on "USCA" instead would make a wrong prefix invisible,
# and matching the exact group widths would make a wrong width invisible, which
# is the shape of the defect this file exists to catch. Measured over the corpus
# as it stands: 24 distinct tokens, 0 false positives.
TOKEN = re.compile(r"\b[A-Z][A-Z0-9]{1,7}(?:-[A-Z0-9]{2,8}){3}\b")

# Files in a filing directory that hold no text to scan.
BINARY_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".xlsx", ".xls"}


class Refuse(SystemExit):
    """Refusing to report a verdict. Never a silent pass."""

    def __init__(self, msg: str):
        super().__init__("REFUSING: " + msg)


def _shown(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# The reference data
# ---------------------------------------------------------------------------

def load_grammar(path: Path = MIDAS) -> dict:
    """Read the attested prefixes and party segments off the MIDAS snapshot.

    Every refusal below is a collapsed denominator: the file is gone, holds no
    identifiers, or holds identifiers that yield no structure. In each case the
    comparison has no second side and "clean" would mean "nothing was compared".
    """
    path = Path(path)
    if not path.exists():
        raise Refuse(
            f"{_shown(path)} is missing, so there is no record of which party "
            f"segments MIDAS publishes and every identifier in the corpus would "
            f"pass on the strength of an absent file."
        )
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise Refuse(f"{_shown(path)} could not be read as JSON: {e}")
    if not isinstance(data, dict):
        raise Refuse(f"{_shown(path)} is not a JSON object, so it carries no rids.")

    rids = [r for r in (data.get("rids") or []) if isinstance(r, dict) and r.get("rid")]
    errors = [e for e in (data.get("errors") or []) if isinstance(e, dict) and e.get("rid")]
    if not rids:
        raise Refuse(
            f"{_shown(path)} carries no rate identifiers, so no grammar can be "
            f"read off it and well-formedness would be asserted rather than derived."
        )

    prefixes: collections.Counter = collections.Counter()
    segments: collections.Counter = collections.Counter()
    unparsed = 0
    for r in rids:
        parts = str(r["rid"]).split("-")
        if len(parts) != 4:
            unparsed += 1
            continue
        prefixes[parts[0]] += 1
        segments[parts[1]] += 1

    # Fewer than two distinct segments is not a grammar. One segment would make
    # every corpus identifier outside it fail on a sample of one, and zero
    # segments would make every identifier pass; neither is a measurement.
    if len(segments) < 2:
        raise Refuse(
            f"{_shown(path)} yields {len(segments)} distinct party segment(s) "
            f"across {len(rids)} identifier(s) ({unparsed} did not parse into four "
            f"dash-separated groups). With fewer than two the segment carries no "
            f"observable structure, and calling a corpus identifier well formed "
            f"would be asserting the format rather than deriving it."
        )

    known = {str(r["rid"]) for r in rids} | {str(e["rid"]) for e in errors}
    return {
        "path": _shown(path),
        "generated_at": data.get("generated_at_utc") or "(unrecorded)",
        "records": len(rids),
        "unparsed": unparsed,
        "errored": len(errors),
        "prefixes": dict(prefixes),
        "segments": dict(segments),
        "known": known,
    }


# ---------------------------------------------------------------------------
# What the corpus asserts
# ---------------------------------------------------------------------------

def _scan_json(doc, sites: list) -> None:
    """Record (property, node type) for every identifier-shaped token in a document."""

    def rec(node, prop: str, types: tuple) -> None:
        if isinstance(node, dict):
            t = node.get("@type")
            here = tuple(t) if isinstance(t, list) else ((t,) if t else types)
            for k, v in node.items():
                rec(v, k, here)
        elif isinstance(node, list):
            for v in node:
                rec(v, prop, types)
        elif isinstance(node, str):
            for tok in TOKEN.findall(node):
                where = f"{prop} on {'/'.join(str(x) for x in types) or 'an untyped node'}"
                sites.append((tok, where))

    rec(doc, "(document root)", ())


def _scan_text(text: str, sites: list) -> None:
    for n, line in enumerate(text.splitlines(), 1):
        for tok in TOKEN.findall(line):
            sites.append((tok, f"line {n}"))


def scan_corpus(dirs=None) -> dict:
    """Every identifier-shaped token in every file of every filing directory.

    Not a list of filings, not a list of properties, not a list of identifiers.
    Discovery is dev/corpus.py's, so it survives the next restructure; within a
    filing every file is read, so an identifier that moves out of `urpx:name`
    is still found and its new home is what gets printed.
    """
    dirs = list(corpus.filing_dirs()) if dirs is None else [Path(d) for d in dirs]
    if not dirs:
        raise Refuse(
            "corpus discovery found no filing directories, so this would report "
            "a clean result over an empty corpus. Either the tree moved and "
            "dev/corpus.py was not updated, or this is not the repository root."
        )

    found: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    files_read = 0
    filings_citing: set[str] = set()
    for d in sorted(dirs):
        for f in sorted(d.rglob("*")):
            if not f.is_file() or f.suffix.lower() in BINARY_SUFFIXES:
                continue
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            files_read += 1
            if not TOKEN.search(text):
                continue
            sites: list = []
            if f.suffix.lower() == ".jsonld" or f.suffix.lower() == ".json":
                try:
                    _scan_json(json.loads(text), sites)
                except ValueError:
                    # Unparseable JSON is somebody else's failure to report; this
                    # check still has to see the identifiers it holds.
                    _scan_text(text, sites)
            else:
                _scan_text(text, sites)
            rel = _shown(f)
            for tok, where in sites:
                found[tok][(rel, where)] += 1
            if sites:
                filings_citing.add(_shown(d))

    if not found:
        raise Refuse(
            f"no rate identifier appears anywhere in the {len(dirs)} filing "
            f"director{'y' if len(dirs) == 1 else 'ies'} scanned "
            f"({files_read} file(s) read), so this would check nothing and "
            f"report it as clean."
        )
    return {
        "identifiers": {k: dict(v) for k, v in found.items()},
        "filings": len(dirs),
        "filings_citing": sorted(filings_citing),
        "files_read": files_read,
        "occurrences": sum(sum(v.values()) for v in found.values()),
    }


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------

def classify(rin: str, grammar: dict) -> dict:
    """Structure first, then presence. The two are reported separately."""
    parts = rin.split("-")
    problems = []
    if len(parts) != 4:
        problems.append("does not split into four dash-separated groups")
    else:
        prefix, segment = parts[0], parts[1]
        if prefix not in grammar["prefixes"]:
            problems.append(
                f"prefix {prefix!r} occurs in none of the "
                f"{grammar['records']:,} published records"
            )
    return {
        "rin": rin,
        "well_formed": not problems,
        "problems": problems,
        "in_snapshot": rin in grammar["known"],
        # Reported alongside absence, never failed on. See the module docstring.
        "segment_unattested": (
            len(parts) == 4 and parts[1] not in grammar["segments"]
        ),
        "segment": parts[1] if len(parts) == 4 else None,
    }


def build(snapshot: Path = MIDAS, dirs=None) -> dict:
    grammar = load_grammar(snapshot)
    scan = scan_corpus(dirs)
    verdicts = [classify(r, grammar) for r in sorted(scan["identifiers"])]
    return {
        "grammar": grammar,
        "scan": scan,
        "verdicts": verdicts,
        "failing": [v for v in verdicts if not v["well_formed"]],
        "reported": [v for v in verdicts if v["well_formed"] and not v["in_snapshot"]],
        "corroborated": [v for v in verdicts if v["well_formed"] and v["in_snapshot"]],
    }


def render(d: dict) -> None:
    g, s = d["grammar"], d["scan"]
    fail, rep, ok = d["failing"], d["reported"], d["corroborated"]

    print(f"MIDAS rate identifiers: {len(fail)} malformed, {len(rep)} uncorroborated, "
          f"{len(ok)} corroborated")
    print()
    # Denominators first, every run. A clean run that does not say what it
    # measured is indistinguishable from a clean run that measured nothing.
    print(f"  reference   {g['path']} generated {g['generated_at']}")
    print(f"              {g['records']:,} published records"
          + (f", {g['errored']} that errored on fetch" if g["errored"] else "")
          + (f", {g['unparsed']} unparsable" if g["unparsed"] else ""))
    print(f"              {len(g['prefixes'])} prefix(es) attested: "
          + ", ".join(f"{k} ({v:,})" for k, v in sorted(g["prefixes"].items())))
    print(f"              {len(g['segments'])} party segment(s) attested: "
          + ", ".join(f"{k} ({v:,})" for k, v in sorted(g["segments"].items())))
    print(f"  corpus      {s['filings']} filing(s) scanned, {s['files_read']:,} file(s) read")
    print(f"              {len(s['identifiers'])} distinct identifier(s) in "
          f"{len(s['filings_citing'])} filing(s), {s['occurrences']:,} occurrence(s)")
    print(f"  checked     {len(d['verdicts'])} identifier(s) against "
          f"{len(g['segments'])} attested party segment(s)")
    print()

    def sites(v):
        for (f, where), n in sorted(s["identifiers"][v["rin"]].items()):
            print(f"        {f}")
            print(f"            {where}, {n:,} occurrence(s)")

    if fail:
        print(f"FAIL  {len(fail)} identifier(s) use a component MIDAS has never published:")
        for v in fail:
            print(f"    {v['rin']}")
            for p in v["problems"]:
                print(f"        {p}")
            sites(v)
        print()
        print("    This is a structural finding, not a freshness one: it does not depend")
        print("    on the snapshot being current. Fixing it means establishing what the")
        print("    corpus meant to cite, not editing the string into a shape that passes.")
        print("    See doc/midas-rins-and-service-arrangements.md.")
        print()

    if rep:
        print(f"report  {len(rep)} identifier(s) are well formed but appear in no snapshot record:")
        for v in rep:
            print(f"    {v['rin']}")
            sites(v)
        print()
        print(f"    Reported, not failed. The snapshot is dated {g['generated_at']} and")
        print("    cannot be refreshed at present: the MIDAS token endpoint returns 401 to")
        print("    the stored credentials. Absent from a months-old snapshot is not")
        print("    evidence that an identifier does not exist, so the gate does not turn")
        print("    on it.")
        print()

    if ok:
        print(f"ok  {len(ok)} identifier(s) are well formed and appear in the snapshot:")
        print("    " + ", ".join(v["rin"] for v in ok))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--snapshot", default=str(MIDAS),
                    help="MIDAS coverage snapshot to derive the grammar from")
    args = ap.parse_args(argv)

    try:
        d = build(Path(args.snapshot))
    except SystemExit as e:  # Refuse, and corpus.py's own refusals
        print(str(e) if str(e) else "REFUSING: no result", file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001 - refusing is a distinct outcome
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps({
            "generated_at": d["grammar"]["generated_at"],
            "records": d["grammar"]["records"],
            "segments": d["grammar"]["segments"],
            "identifiers": d["verdicts"],
            "occurrences": d["scan"]["occurrences"],
        }, indent=2))
    else:
        render(d)
    return 1 if d["failing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
