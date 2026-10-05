#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Assert that this repository and clj-urpx enumerate the SAME scenario cost
models, rather than the same NUMBER of them.

Two implementations of one rule exist: dev/scenario_cost_models.py here, and
clj-urpx's urpx.arrangements, which enumerates the same set under its own name.
Equal totals over different members is the failure this repository keeps
hitting, and counting is what fails to catch it.

WHAT IS COMPARED, in three steps, each membership in both directions

  1. Compositions, open dimensions UNEXPANDED:
         #{[<base version IRI> #{<modifier version IRI> ...}] ...}
     against urpx.arrangements/arrangement-pairs.
  2. Scenario cost models, open dimensions expanded, as full identities:
         (<base version IRI>, <sorted modifier version IRIs>, <sorted alternative IRIs>)
     against urpx.arrangements/arrangements, selections reduced to their
     alternative @ids.
  3. The nodes of the committed reports/scenario-cost-models.jsonld, read back
     to identities, against step 2's set; every node's @id is re-derived from
     its identity on the way.

Step 1 runs first because a disagreement about what composes with what is
easier to read than the same disagreement multiplied by every open dimension.

Our side comes from importing dev/scenario_cost_models.py and calling
enumerate_pairs and enumerate_models, not from reading a report. A report can be
stale; the enumerator is the thing under test. Step 3 then holds the report to
it.

TWO PINNED PARAMETERS, both passed in by dev/gate.sh and both required here.
There is no default for either: a check that supplies its own instant is a check
that can quietly answer a different question than its counterpart.

  --at       the instant currency is judged at. A count is a count AT AN
             INSTANT, not a property of the corpus. See dev/gate.sh.
  --combine  the combining policy. Nothing in URPX states which modifier sets
             may sit on one base, so both sides take it as an argument. See
             COMBINE_AT_MOST_ONE_MODIFIER in dev/scenario_cost_models.py.

THE COMPARISON RUNS OR THE CHECK FAILS

  API_NAMESPACE loads, its vars present   The comparison MUST run and MUST
                                          agree. A load error, an empty result
                                          or a wrong shape FAILS.
  API_NAMESPACE absent, a successor loads FAIL. clj-urpx renamed it; this
                                          check implements the old API only.
  neither loads                           FAIL, naming every namespace tried.
  loads, a var it calls is absent         FAIL, naming the missing vars.

There is no passing state in which nothing was compared. An earlier version
passed when the namespace was absent, which was right before clj-urpx shipped
it and would be wrong after: a rename would have stopped the comparison while
the gate stayed green.

Exit codes follow dev/gate.sh: 0 green, 1 a disagreement or a broken contract,
3 refused (this side could not produce an answer at all).
"""
from __future__ import annotations

import argparse
import datetime
import os
import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import scenario_cost_models as scm  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent
PROBE = REPO / "dev" / "cross_check_scenario_cost_models.clj"
EMITTED = "reports/scenario-cost-models.jsonld"

# The clj-urpx 0.35.0 API this check calls, and the name it moves to in 0.36.0.
# The successor is only probed for, to say what happened when API_NAMESPACE is
# gone; its API is not implemented here.
API_NAMESPACE = "urpx.arrangements"
SUCCESSOR_NAMESPACES = ["urpx.scenario-cost-model"]

# Test hooks. Each run with one set announces itself in the output, so neither
# can disarm the check without saying so. EXTRA_PATHS_ENV only ADDS classpath
# entries, for a stub. NAMESPACES_ENV replaces API_NAMESPACE and the successors
# with a comma-separated list, first the API namespace; pointing it at a
# namespace that does not exist must fail the check.
EXTRA_PATHS_ENV = "URPX_CROSSCHECK_EXTRA_PATHS"
NAMESPACES_ENV = "URPX_CROSSCHECK_NAMESPACES"


def namespaces() -> list[str]:
    override = os.environ.get(NAMESPACES_ENV)
    if override:
        names = [n.strip() for n in override.split(",") if n.strip()]
        if names:
            return names
    return [API_NAMESPACE, *SUCCESSOR_NAMESPACES]

REGRESSION, REFUSED = 1, 3


class Refused(SystemExit):
    def __init__(self, msg: str):
        super().__init__(REFUSED)
        self.msg = msg


def fail(headline: str, *body: str) -> int:
    print(f"  FAIL  {headline}")
    for line in body:
        print(f"        {line}")
    return REGRESSION


def refuse(headline: str, *body: str) -> int:
    print(f"  REFUSING  {headline}")
    for line in body:
        print(f"            {line}")
    return REFUSED


def our_pairs(at: datetime.datetime, combine: str) -> dict:
    """The pairs dev/scenario_cost_models.py enumerates, at the pinned instant."""
    try:
        return scm.enumerate_pairs(at, combine=combine)
    except SystemExit as e:  # scm.Refuse
        # scm.Refuse already prefixes "REFUSING: "; do not say it twice.
        raise Refused(str(e).removeprefix("REFUSING: "))


def run_probe(at: str, combine: str) -> tuple[list[str], str, int]:
    """Ask clj-urpx, via dev/cross_check_scenario_cost_models.clj."""
    if shutil.which("clojure") is None:
        raise Refused("clojure is not on PATH, so the clj-urpx side cannot be asked.")
    cmd = ["clojure"]
    extra = os.environ.get(EXTRA_PATHS_ENV)
    if extra:
        paths = ["dev"] + [p for p in extra.split(os.pathsep) if p]
        cmd += ["-Sdeps", "{:paths [" + " ".join(f'"{p}"' for p in paths) + "]}"]
    cmd += ["-M", str(PROBE.relative_to(REPO)), at, combine, *namespaces()]
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("XC-")]
    return lines, (proc.stderr or "").strip(), proc.returncode


def parse_probe(lines: list[str]) -> tuple[str, str, set, dict]:
    state, detail, pairs = None, "", set()
    end = None
    models: dict = {"rows": set(), "end": None, "error": None, "lines": 0}
    for ln in lines:
        if ln.startswith("XC-MODELS-ERROR "):
            models["error"] = ln[len("XC-MODELS-ERROR "):]
            continue
        if ln.startswith("XC-MODEL\t"):
            _, base, mods, alts = ln.split("\t", 3)
            models["rows"].add(scm.model_identity(
                base, [m for m in mods.split(",") if m], [a for a in alts.split(",") if a]))
            models["lines"] += 1
            continue
        if ln.startswith("XC-MODELS-END "):
            models["end"] = int(ln[len("XC-MODELS-END "):])
            continue
        if ln.startswith("XC-STATE "):
            rest = ln[len("XC-STATE "):]
            state, _, detail = rest.partition(" ")
        elif ln.startswith("XC-PAIR\t"):
            _, base, mods = ln.split("\t", 2)
            pairs.add((base, frozenset(m for m in mods.split(",") if m)))
        elif ln.startswith("XC-END "):
            end = int(ln[len("XC-END "):])
    if state == "pairs" and end is None:
        # A truncated stream is not an agreement. Without the terminator there
        # is no way to tell a short answer from a killed process.
        state = "truncated"
    return state or "no-state", detail, pairs, models


def describe_models(tag: str, models: set, limit: int = 12) -> list[str]:
    out = []
    for base, mods, alts in sorted(models)[:limit]:
        out.append(f"{tag} {base}  +  {', '.join(mods) or '(no modifier)'}  /  "
                   f"{', '.join(alts) or '(no selection)'}")
    if len(models) > limit:
        out.append(f"{tag} ... and {len(models) - limit} more")
    return out


def emitted_models() -> set:
    """The identities the committed reports/scenario-cost-models.jsonld carries,
    read back off its nodes, with every node's @id re-derived from its identity."""
    import json

    path = REPO / EMITTED
    if not path.exists():
        raise Refused(f"{EMITTED} is missing; run dev/list_scenario_cost_models.py.")
    doc = json.loads(path.read_text())
    prefixes = doc.get("@context") or {}
    out = set()
    for node in doc.get("@graph") or []:
        ids = lambda k: [x["@id"] for x in (node.get(k) or [])]  # noqa: E731
        identity = scm.model_identity(node["urpx:consumesVersion"]["@id"],
                                      ids("urpx:consumesModifierVersion"),
                                      ids("urpx:selectsProfileAlternative"))
        absolute = tuple([scm.expand_iri(identity[0], prefixes),
                          tuple(scm.expand_iri(m, prefixes) for m in identity[1]),
                          tuple(scm.expand_iri(a, prefixes) for a in identity[2])])
        if scm.expand_iri(node["@id"], prefixes) != scm.model_iri(absolute):
            raise Refused(f"{EMITTED}: {node['@id']} is not the IRI its own identity derives.")
        out.add(identity)
    if not out:
        raise Refused(f"{EMITTED} carries no node.")
    return out


def describe(tag: str, pairs: set, limit: int = 12) -> list[str]:
    out = []
    for base, mods in sorted(pairs, key=lambda p: (p[0], sorted(p[1])))[:limit]:
        out.append(f"{tag} {base}  +  {', '.join(sorted(mods)) or '(base alone)'}")
    if len(pairs) > limit:
        out.append(f"{tag} ... and {len(pairs) - limit} more")
    return out


class Parser(argparse.ArgumentParser):
    """A missing --at or --combine is a refusal, not argparse's exit 2. In this
    repository's gate 2 means tracked-file drift, and a check invoked wrongly has
    not measured drift; it has failed to run."""

    def error(self, message):
        sys.exit(refuse(f"{message}.", self.format_usage().strip()))


def main() -> int:
    ap = Parser(description=__doc__.splitlines()[0])
    ap.add_argument("--at", required=True,
                    help="ISO 8601 instant with an offset, e.g. 2026-07-15T17:00-07:00")
    ap.add_argument("--combine", required=True,
                    help="the combining policy, e.g. at-most-one-modifier")
    args = ap.parse_args()

    try:
        at = datetime.datetime.fromisoformat(args.at)
    except ValueError:
        return refuse(f"--at {args.at!r} is not an ISO 8601 date-time.")
    if at.tzinfo is None:
        return refuse(
            f"--at {args.at!r} carries no offset.",
            "Both sides must mean the same moment; a naive literal does not.")

    pinned = scm._pinned_clj_urpx_version()
    print(f"  instant  {at.isoformat()}   (pinned; changing it is a change in two repositories)")
    print(f"  policy   {args.combine}   (pinned; nothing in URPX states one)")
    print(f"  clj-urpx {pinned}   (deps.edn)")
    for env in (EXTRA_PATHS_ENV, NAMESPACES_ENV):
        if os.environ.get(env):
            print(f"  SIMULATION: {env}={os.environ[env]} is set.")
            print("  This run is a test of the check, not a measurement of the corpus.")
    api = namespaces()[0]

    ours = our_pairs(at, args.combine)
    mine = ours["pairs"]
    if not mine:
        return refuse("dev/scenario_cost_models.py enumerated no composition at all.")
    over = sorted(f"{b} + {sorted(m)}" for b, m in mine if len(m) > 1)
    if over:
        return fail(
            f"our own pairs violate the pinned policy {args.combine!r}: "
            f"{len(over)} carry more than one modifier.",
            *over[:5],
            "The policy name no longer describes this enumerator. Settle it with clj-urpx.")
    print(f"  ours     {len(mine)} pairs "
          f"({sum(1 for _, m in mine if not m)} base alone, "
          f"{sum(1 for _, m in mine if len(m) == 1)} base plus one modifier); "
          f"{len(ours['superseded'])} versions superseded, "
          f"{len(ours['not_yet_effective'])} not yet effective at this instant")

    lines, stderr, rc = run_probe(args.at, args.combine)
    state, detail, theirs, their_models = parse_probe(lines)

    if state == "ns-absent":
        return fail(
            f"none of {detail.replace(',', ', ')} loads with clj-urpx {pinned} (deps.edn).",
            f"{api} is the API this check calls. Nothing was compared, and that is a",
            "failure: the namespace was renamed or removed, or the classpath is wrong.")
    if state == "ns-renamed":
        return fail(
            f"{api} is absent and {detail} loads: clj-urpx renamed the namespace.",
            "This check implements the old API only. Port dev/cross_check_scenario_cost_models.clj",
            "to the new one in the same change that moves the clj-urpx pin.")
    if state == "ns-load-error":
        return fail(
            f"{api} IS on the classpath in clj-urpx {pinned} and threw while loading.",
            detail)
    if state == "ns-present-var-absent":
        return fail(
            f"clj-urpx {pinned} ships {api} without a var this check calls.",
            detail,
            "The contract is the var, not the namespace. Their API moved; settle the",
            "new entrypoint with clj-urpx and update dev/cross_check_scenario_cost_models.clj.")
    if state == "documents-error":
        return fail("the corpus would not load on the clj-urpx side.", detail)
    if state == "call-error":
        return fail(
            f"{api}/arrangement-pairs threw when called in clj-urpx {pinned}.",
            detail,
            "The document form this passes is an assumption of ours; see the comment in",
            "dev/cross_check_scenario_cost_models.clj. Either way the comparison did not happen.")
    if state == "shape-error":
        return fail("arrangement-pairs did not return a set of [base #{modifiers}] pairs.", detail)
    if state == "truncated":
        return fail("the clj-urpx side started emitting pairs and did not finish.",
                    f"exit {rc}", stderr[-400:] if stderr else "")
    if state != "pairs":
        return fail(
            "the clj-urpx side produced no state at all, so nothing was compared.",
            f"exit {rc}", stderr[-400:] if stderr else "(no stderr)")

    # ACTIVE from here on: every path must either agree or fail.
    if not theirs:
        return fail(
            "arrangement-pairs returned an empty set.",
            "Present but producing nothing is a failure. An empty set agrees with",
            "nothing and must never read as a pass.")
    bad = sorted(f"{b} + {sorted(m)}" for b, m in theirs if len(m) > 1)
    if bad:
        return fail(
            f"clj-urpx returned pairs that violate the pinned policy {args.combine!r}.",
            *bad[:5],
            "Either their default combining policy moved or the name no longer means",
            "the same thing on both sides. That is a coordinated decision, not a diff.")

    print(f"  theirs   {len(theirs)} pairs")
    ours_only = mine - theirs
    theirs_only = theirs - mine
    if ours_only or theirs_only:
        body = [f"ours only:   {len(ours_only)} (we enumerate them, clj-urpx does not)",
                f"theirs only: {len(theirs_only)} (clj-urpx enumerates them, we do not)"]
        body += describe("ours  ", ours_only)
        body += describe("theirs", theirs_only)
        return fail(
            f"the two enumerations disagree ({len(mine)} ours, {len(theirs)} theirs).",
            *body)
    print(f"  agreed   {len(mine)} pairs, identical membership in both directions")

    # The same comparison with open dimensions expanded: one scenario cost model
    # per selection, compared as full identities. Then the committed document's
    # nodes against the same set, so the count clj-price-server reads off the
    # artifact is the count both enumerators arrive at.
    if their_models["error"]:
        return fail(f"{api}/arrangements could not be asked.", their_models["error"])
    if their_models["end"] is None:
        return fail("the clj-urpx side did not finish emitting arrangements.",
                    f"exit {rc}", stderr[-400:] if stderr else "")
    theirs_m = their_models["rows"]
    if their_models["end"] != their_models["lines"] or len(theirs_m) != their_models["end"]:
        return fail(
            f"clj-urpx returned {their_models['end']} arrangements, printed "
            f"{their_models['lines']}, of which {len(theirs_m)} are distinct identities.")
    try:
        mine_m = scm.enumerate_models(at, combine=args.combine)
    except SystemExit as e:
        raise Refused(str(e).removeprefix("REFUSING: "))
    print(f"  ours     {len(mine_m)} scenario cost models (open dimensions expanded)")
    print(f"  theirs   {len(theirs_m)} arrangements ({api}/arrangements)")
    if mine_m != theirs_m:
        return fail(
            f"the expanded enumerations disagree ({len(mine_m)} ours, {len(theirs_m)} theirs).",
            f"ours only:   {len(mine_m - theirs_m)}", f"theirs only: {len(theirs_m - mine_m)}",
            *describe_models("ours  ", mine_m - theirs_m),
            *describe_models("theirs", theirs_m - mine_m))
    print(f"  agreed   {len(mine_m)} scenario cost models, identical identities in both directions")
    emitted = emitted_models()
    if emitted != mine_m:
        return fail(
            f"{EMITTED} carries {len(emitted)} nodes; the enumeration at this instant is "
            f"{len(mine_m)}.",
            f"in the document only:    {len(emitted - mine_m)}",
            f"in the enumeration only: {len(mine_m - emitted)}",
            *describe_models("document", emitted - mine_m),
            *describe_models("enum    ", mine_m - emitted),
            "The document is current by succession; the enumeration is current at the pinned",
            "instant. A version filed for a later date separates them: regenerate, or move the",
            "instant in both repositories together.")
    print(f"  emitted  {len(emitted)} nodes in {EMITTED}, the same identities, every @id re-derived")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as e:
        sys.exit(refuse(e.msg))
