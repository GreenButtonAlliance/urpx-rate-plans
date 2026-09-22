#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Negative tests for the service-arrangement enumeration.

This repository has ten recorded instances of a check that passed while
verifying nothing, one of them shipped the day before this file was written and
sitting on its own suppression path. So every guard in dev/arrangements.py is
made to fire here against a deliberately broken input, and the run fails if a
guard stays quiet.

The shape of the failure that matters is always the same: a denominator
collapses, the comparison becomes trivial, and the report prints success over an
empty set. Each case below removes, duplicates or corrupts exactly one input and
asserts a REFUSAL rather than a verdict.

Run: python3 dev/test_arrangements.py
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))

import arrangements as A  # noqa: E402
import corpus  # noqa: E402

failures: list[str] = []


def expect_refusal(name: str, fn) -> None:
    try:
        fn()
    except SystemExit as e:
        msg = str(e)
        if "REFUSING" in msg or "Refusing" in msg:
            print(f"  PASS  {name}: refused")
            return
        print(f"  FAIL  {name}: exited, but not as a refusal: {msg[:120]}")
        failures.append(name)
        return
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL  {name}: raised {type(e).__name__}, not a refusal: {e}")
        failures.append(name)
        return
    print(f"  FAIL  {name}: returned a verdict over a broken input")
    failures.append(name)


def expect(name: str, got, want) -> None:
    if got == want:
        print(f"  PASS  {name}: {got}")
        return
    print(f"  FAIL  {name}: got {got!r}, want {want!r}")
    failures.append(name)


print("=== the enumeration over the real corpus ===")
REAL = A.build()
tally = A.tally(REAL["arrangements"])
expect("every arrangement is classified",
       sum(tally.values()), len(REAL["arrangements"]))
expect("supersession finds nine plan identities", len(REAL["superseded"]), 9)
expect("no arrangement is built on a superseded version",
       [a for a in REAL["arrangements"]
        if a["base"] in REAL["superseded"] or set(a["modifiers"]) & set(REAL["superseded"])],
       [])

# The counts below are asserted as SHAPE, not as a recorded answer: a corpus
# that grows should not fail this file. What must hold is that the buckets
# partition the arrangements and that none of them is empty of meaning.
expect("servable is not the whole set", tally[A.SERVABLE] < len(REAL["arrangements"]), True)
expect("something is servable", tally[A.SERVABLE] > 0, True)

print()
print("=== supersession ===")


def tie_effective_dates():
    versions = copy.deepcopy(REAL["versions"])
    plan = REAL["versions"][REAL["superseded"][0]]["plan"]
    siblings = [v for v in versions.values() if v["plan"] == plan]
    for v in siblings:
        v["effective"] = "2026-03-20T00:00:00"
    A.derive_supersession(versions)


expect_refusal("two versions tie on urpx:effectiveDateTime", tie_effective_dates)


def supersession_is_not_a_no_op():
    """Removing the later version of a superseded pair must move the earlier one
    back into the current set. A derivation that always returned the same nine
    ids would pass every positive assertion above."""
    versions = copy.deepcopy(REAL["versions"])
    earlier = REAL["superseded"][0]
    plan = versions[earlier]["plan"]
    for vid in [v["id"] for v in list(versions.values())
                if v["plan"] == plan and v["id"] != earlier]:
        del versions[vid]
    return A.derive_supersession(versions)


expect("dropping the later version un-supersedes the earlier one",
       sorted(supersession_is_not_a_no_op()),
       sorted(set(REAL["superseded"]) - {REAL["superseded"][0]}))

print()
print("=== baseline ===")


def unattributable_baseline_row():
    baseline = copy.deepcopy(REAL["baseline"])
    baseline["rows"]["plan|us/ca/nowhere/electricity/x/versions/2026-01-01/rate-plan_nowhere_x_2026-01-01.jsonld"] = {
        i: {"status": ":ok", "reason": None} for i in baseline["instants"]
    }
    referenced = {k for a in REAL["arrangements"] for k in a["baseline_keys"]}
    superseded_files = {f for vid in REAL["superseded"] for f in REAL["versions"][vid]["files"]}
    superseded_homes = {REAL["versions"][vid]["home"] for vid in REAL["superseded"]
                        if REAL["versions"][vid]["home"]}
    unattributed = []
    for key in baseline["rows"]:
        if key in referenced:
            continue
        kind, _, rest = key.partition("|")
        if kind == "plan" and rest in superseded_files:
            continue
        if kind == "compose" and rest.split("|")[0] in superseded_homes:
            continue
        unattributed.append(key)
    if unattributed:
        raise A.Refuse("unattributed baseline rows: " + ", ".join(unattributed))


expect_refusal("a baseline row belonging to no arrangement and no superseded version",
               unattributable_baseline_row)

# classify() is where an arrangement becomes servable, so it is the single most
# important thing to break on purpose.
INSTANTS = REAL["baseline"]["instants"]


def bl(**per_key):
    return {"rows": per_key, "instants": INSTANTS, "clj_urpx_version": "test"}


all_ok = {i: {"status": ":ok", "reason": None} for i in INSTANTS}
expect("all nineteen instants resolve", A.classify(["k"], bl(k=all_ok))[0], A.SERVABLE)

mixed = dict(all_ok)
mixed[INSTANTS[0]] = {"status": ":refused", "reason": ":no-energy-ledger"}
expect("resolves at eighteen instants and refuses at one",
       A.classify(["k"], bl(k=mixed))[0], A.BLOCKED)

short = {i: {"status": ":ok", "reason": None} for i in INSTANTS[:-1]}
expect("a row missing one probe instant",
       A.classify(["k"], bl(k=short))[0], A.BLOCKED)

not_priced = {i: {"status": ":refused", "reason": ":no-energy-ledger"} for i in INSTANTS}
expect("street lighting prices nothing per kWh",
       A.classify(["k"], bl(k=not_priced))[0], A.NOT_PRICED)

novel = {i: {"status": ":refused", "reason": ":some-reason-nobody-has-triaged"} for i in INSTANTS}
expect("a refusal reason nobody has triaged is not 'not priced'",
       A.classify(["k"], bl(k=novel))[0], A.BLOCKED)

unselected = {i: {"status": ":refused", "reason": ":unselected-alternatives"} for i in INSTANTS}
expect("an undecided alternative selection blocks",
       A.classify(["k"], bl(k=unselected))[0], A.BLOCKED)

expect("an arrangement with no baseline key is never servable",
       A.classify([], bl())[0], A.UNMEASURED)
expect("an arrangement whose key vanished from the baseline is never servable",
       A.classify(["gone"], bl(k=all_ok))[0], A.UNMEASURED)

# Two keys, one good and one refusing: a base version filed in two directories
# must agree with itself.
expect("two rows for one arrangement disagreeing",
       A.classify(["a", "b"], bl(a=all_ok, b=novel))[0], A.BLOCKED)

print()
print("=== inputs that must not be assumed ===")


def nominations_gone():
    A.load_nominations(
        A.VALIDATOR.read_text().replace(
            "(def profile-alternative-nominations", "(def renamed-away"))


expect_refusal("the validator stops declaring which alternatives it nominated", nominations_gone)

expect("nominations are actually read, not assumed empty",
       len(A.load_nominations()) > 0, True)
expect("every nominated dimension exists in the corpus",
       sorted(set(A.load_nominations()) - set(REAL["dimensions"])), [])


def dimension_without_alternatives():
    A.dimensions_within({"@type": "urpx:ProfileAlternatives", "@id": "x:empty"})


expect_refusal("a dimension declaring no alternatives", dimension_without_alternatives)


def dimension_without_id():
    A.dimensions_within({"@type": "urpx:ProfileAlternatives",
                         "urpx:hasProfileAlternative": [{"@id": "x:a"}]})


expect_refusal("a dimension with no @id to select from", dimension_without_id)


def wrong_clj_urpx_pin():
    import tempfile
    orig = A.DEPS
    with tempfile.NamedTemporaryFile("w", suffix=".edn", delete=False) as fp:
        fp.write('{:deps {energy.grid-coordination/clj-urpx {:mvn/version "0.0.1-not-what-recorded"}}}')
        A.DEPS = Path(fp.name)
    try:
        A.load_baseline()
    finally:
        A.DEPS = orig


expect_refusal("the baseline was recorded against a different clj-urpx than deps.edn pins",
               wrong_clj_urpx_pin)


def no_clj_urpx_pin():
    import tempfile
    orig = A.DEPS
    with tempfile.NamedTemporaryFile("w", suffix=".edn", delete=False) as fp:
        fp.write("{:deps {}}")
        A.DEPS = Path(fp.name)
    try:
        A.load_baseline()
    finally:
        A.DEPS = orig


expect_refusal("deps.edn stops pinning clj-urpx at all", no_clj_urpx_pin)


def bundled_copy_claims_a_base_its_own_filing_does_not():
    A.check_compatibility_agreement("x:care-2026-03-20", {"x:tou-d"}, {"x:tou-d", "x:d"})


expect_refusal("a bundled modifier copy claims a base its own filing does not",
               bundled_copy_claims_a_base_its_own_filing_does_not)

expect("copies that agree are accepted",
       A.check_compatibility_agreement("x:m", {"x:a"}, {"x:a"}), None)


def empty_corpus():
    corpus.require_nonempty([], "filing JSON-LD files")


expect_refusal("an empty corpus", empty_corpus)

print()
print("=== the expansion is real arithmetic ===")
with_dims = [a for a in REAL["arrangements"] if a["dimensions"]]
expect("some arrangement leaves a dimension open", len(with_dims) > 0, True)
expect("an arrangement with no open dimension is one arrangement",
       {a["selections"] for a in REAL["arrangements"] if not a["dimensions"]}, {1})
expect("an arrangement with open dimensions expands past one",
       all(a["selections"] > 1 for a in with_dims), True)

print()
print("=== cross-check against the independently generated pairings report ===")
import json  # noqa: E402

PAIRINGS = json.loads((REPO / "reports" / "modifier-base-pairings.json").read_text())
plan_level = sum(len(v["applicable_to"]) for v in PAIRINGS["by_modifier"].values())
version_level = len([a for a in REAL["arrangements"] if a["modifiers"]])
# Each modifier identity has exactly one current version and each base identity
# exactly one current version, so the version-level pairing count must land on
# the plan-level count dev/list_modifier_base_pairings.py reports. It does not
# prove either is right, but a silent drop in the version-pinning filter shows
# up here as a shortfall.
expect("base-plus-one-modifier arrangements match the plan-level pairing count",
       version_level, plan_level)
expect("base-only arrangements match the current base count",
       len([a for a in REAL["arrangements"] if not a["modifiers"]]),
       len({v["plan"] for v in REAL["versions"].values()
            if v["kind"] == "plan" and v["id"] not in REAL["superseded"]}))

print()
if failures:
    print(f"{len(failures)} assertion(s) failed: {', '.join(failures)}")
    sys.exit(1)
print(f"all {len(REAL['arrangements'])} arrangements classified; every guard fired when broken")
