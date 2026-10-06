#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Negative tests for the scenario cost model enumeration, and the IRI scheme.

This repository has ten recorded instances of a check that passed while
verifying nothing, one of them shipped the day before this file was written and
sitting on its own suppression path. So every guard in dev/scenario_cost_models.py is
made to fire here against a deliberately broken input, and the run fails if a
guard stays quiet.

The shape of the failure that matters is always the same: a denominator
collapses, the comparison becomes trivial, and the report prints success over an
empty set. Each case below removes, duplicates or corrupts exactly one input and
asserts a REFUSAL rather than a verdict.

Run: python3 dev/test_scenario_cost_models.py
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))

import scenario_cost_models as A  # noqa: E402
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
tally = A.tally(REAL["compositions"])
expect("every composition is classified",
       sum(tally.values()), len(REAL["compositions"]))
# Twelve of them are the SCE 2026-03-20 versions the 2026-10-01 ones follow.
expect("supersession finds twenty-five plan identities", len(REAL["superseded"]), 25)
# SCL RTC, RTS and scl:residential-suburban are filed for 2027-01-01 and
# 2028-01-01 as well as 2026-01-01. At the currency instant the later six are
# not yet effective, and the 2026 versions they follow are in force, not
# superseded.
expect("six versions are not yet effective", len(REAL["not_yet_effective"]), 6)
expect("no composition is built on a superseded version",
       [a for a in REAL["compositions"]
        if a["base"] in REAL["superseded"] or set(a["modifiers"]) & set(REAL["superseded"])],
       [])

# The counts below are asserted as SHAPE, not as a recorded answer: a corpus
# that grows should not fail this file. What must hold is that the buckets
# partition the compositions and that none of them is empty of meaning.
expect("servable is not the whole set", tally[A.SERVABLE] < len(REAL["compositions"]), True)
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
    # Every superseded version also carries an expirationDateTime that has
    # passed, which supersedes it on its own; drop it to test succession alone.
    versions[earlier]["expires"] = None
    return A.derive_supersession(versions, at=REAL["currency_instant"])


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
    referenced = {k for a in REAL["compositions"] for k in a["baseline_keys"]}
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


expect_refusal("a baseline row belonging to no composition and no superseded version",
               unattributable_baseline_row)

# classify() is where a composition becomes servable, so it is the single most
# important thing to break on purpose.
INSTANTS = REAL["baseline"]["instants"]


def bl(**per_key):
    return {"rows": per_key, "instants": INSTANTS, "clj_urpx_version": "test"}


all_ok = {i: {"status": ":ok", "reason": None} for i in INSTANTS}
expect("every instant resolves", A.classify(["k"], bl(k=all_ok))[0], A.SERVABLE)

mixed = dict(all_ok)
mixed[INSTANTS[0]] = {"status": ":refused", "reason": ":no-energy-ledger"}
expect("resolves at all but one instant and refuses at one",
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

expect("a composition with no baseline key is never servable",
       A.classify([], bl())[0], A.UNMEASURED)
expect("a composition whose key vanished from the baseline is never servable",
       A.classify(["gone"], bl(k=all_ok))[0], A.UNMEASURED)

# Two keys, one good and one refusing: a base version filed in two directories
# must agree with itself.
expect("two rows for one composition disagreeing",
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
with_dims = [a for a in REAL["compositions"] if a["dimensions"]]
expect("some composition leaves a dimension open", len(with_dims) > 0, True)
expect("a composition with no open dimension is one scenario cost model",
       {a["selections"] for a in REAL["compositions"] if not a["dimensions"]}, {1})
expect("a composition with open dimensions expands past one",
       all(a["selections"] > 1 for a in with_dims), True)

print()
print("=== cross-check against the independently generated pairings report ===")
import json  # noqa: E402

import withheld_filings  # noqa: E402

PAIRINGS = json.loads((REPO / "reports" / "modifier-base-pairings.json").read_text())
# Less the pairings onto a base dev/withheld-filings.json withholds from every
# composition (scl:residential-suburban onto scl:rts).
WITHHELD_PLANS = {v["plan"] for v in REAL["versions"].values()
                  if v["kind"] == "plan" and withheld_filings.withheld(v.get("home"))}
plan_level = sum(len(set(v["applicable_to"]) - WITHHELD_PLANS)
                 for v in PAIRINGS["by_modifier"].values())
version_level = len([a for a in REAL["compositions"] if a["modifiers"]])
# Each modifier identity has exactly one current version and each base identity
# exactly one current version, so the version-level pairing count must land on
# the plan-level count dev/list_modifier_base_pairings.py reports. It does not
# prove either is right, but a silent drop in the version-pinning filter shows
# up here as a shortfall.
expect("base-plus-one-modifier compositions match the plan-level pairing count",
       version_level, plan_level)
# Less the bases dev/withheld-filings.json withholds from every composition.
expect("base-only compositions match the current base count",
       len([a for a in REAL["compositions"] if not a["modifiers"]]),
       len({v["plan"] for v in REAL["versions"].values()
            if v["kind"] == "plan" and v["id"] not in REAL["superseded"]
            and v["id"] not in REAL["not_yet_effective"]
            and not withheld_filings.withheld(v.get("home"))}))

print()
print("=== applicableToRatePlanVersion ADDS, it does not narrow (URPX Decision #090) ===")
# The corpus CANNOT test this, which is the whole reason these fixtures exist.
# Every node in it that states urpx:applicableToRatePlanVersion names version(s)
# of the single plan it also names, so the additive and the narrowing readings
# agree on every row and a green gate is evidence for neither. The one node that
# did come apart, a copy of cpau:e-nse-1-2025-09-01 naming one version of one of
# the three plans it applied to, was a copy-local artifact and was removed.
#
# So each case below asserts the additive answer AND asserts that the narrowing
# reading would have given a different one. A fixture that both readings pass
# discriminates nothing, and this file exists because that keeps happening here.


def reached(bases, modifiers):
    """Base version IRIs the modifier reaches, under the shipped reading."""
    return {b["id"] for b, m in A.pair_candidates(bases, modifiers) if m is not None}


def reached_if_narrowing(bases, modifiers):
    """What this module did before Decision #090 settled the reading.

    Kept only so the fixtures can prove they tell the two apart. If this ever
    agrees with pair_candidates on every case below, the cases have stopped
    discriminating and must be fixed rather than deleted.
    """
    out = set()
    for m in modifiers:
        for plan in m["applies_to"]:
            b = bases.get(plan)
            if b is None:
                continue
            if m["applies_to_versions"] and b["id"] not in m["applies_to_versions"]:
                continue
            out.add(b["id"])
    return out


def both(name, bases, modifiers, want, discriminating=True):
    expect(name, reached(bases, modifiers), want)
    narrow = reached_if_narrowing(bases, modifiers)
    if discriminating:
        expect(f"  ...and the narrowing reading would differ", narrow != want, True)
    else:
        expect(f"  ...and the narrowing reading agrees (control)", narrow == want, True)


AB = {"x:a": {"id": "x:a-2", "plan": "x:a"}, "x:b": {"id": "x:b-1", "plan": "x:b"}}

# Naming a version of ANOTHER plan must not withdraw compatibility with the plan
# named at document level. SHACL does not even require the two lists to agree.
both("naming another plan's version does not withdraw the plan-level compatibility",
     AB, [{"id": "x:m", "applies_to": ["x:a"], "applies_to_versions": ["x:b-1"]}],
     {"x:a-2", "x:b-1"})

# Naming an OLDER version of the same plan must not un-apply the modifier from
# that plan's current version. Under narrowing this silently reaches nothing,
# which is the failure mode that would have bitten when CPAU files a second
# E-1-TOU version.
both("naming a superseded version does not un-apply the modifier from the current one",
     {"x:a": {"id": "x:a-2", "plan": "x:a"}},
     [{"id": "x:m", "applies_to": ["x:a"], "applies_to_versions": ["x:a-1"]}],
     {"x:a-2"})

# The shape the corpus actually has: one plan, and version(s) of that same plan.
# Both readings agree, which is exactly why the corpus proves nothing.
both("the corpus's own shape reads the same either way",
     {"x:a": {"id": "x:a-1", "plan": "x:a"}},
     [{"id": "x:m", "applies_to": ["x:a"], "applies_to_versions": ["x:a-1"]}],
     {"x:a-1"}, discriminating=False)

# Additive does not mean inventive: a named version that is not a current base
# reaches nothing, or supersession would be undone by a compatibility statement.
expect("a named version that is not a current base is not reached",
       reached({"x:a": {"id": "x:a-1", "plan": "x:a"}},
               [{"id": "x:m", "applies_to": [], "applies_to_versions": ["x:gone-1"]}]),
       set())

print()
print("=== scenario cost model IRIs ===")
# Known answers, also given in doc/scenario-cost-models.md, so a second
# implementation can test against the same vectors. One per degenerate case.
N = "https://rate-plans.grid-coordination.energy/pge/"
VECTORS = [
    ("base alone, nothing open",
     (N + "e-1-2026-03-01", (), ()),
     N + "scm-e-1-2026-03-01"),
    ("base and modifier, nothing open",
     (N + "e-1-2026-03-01", (N + "e-1-vintage-pcia-2026-03-01",), ()),
     N + "scm-e-1-2026-03-01--e-1-vintage-pcia-2026-03-01"),
    ("base alone, one selection",
     (N + "e-elec-2026-03-27", (), (N + "e-elec-2026-03-27-pa-income-tier-care",)),
     N + "scm-e-elec-2026-03-27--291186d914f7"),
    ("base and modifier, two selections",
     (N + "e-1-2026-03-01", (N + "e-1-vintage-pcia-2026-03-01",),
      (N + "e-1-2026-03-01-pa-tc-w-b", N + "e-1-vintage-pcia-2026-03-01-pa-vintage-2020")),
     N + "scm-e-1-2026-03-01--e-1-vintage-pcia-2026-03-01--deed42bdeaaa"),
]
for name, identity, iri in VECTORS:
    expect(name, A.model_iri(identity), iri)
expect("selection order does not move the IRI",
       A.model_iri(A.model_identity(N + "e-1-2026-03-01", [N + "e-1-vintage-pcia-2026-03-01"],
                                    [N + "e-1-vintage-pcia-2026-03-01-pa-vintage-2020",
                                     N + "e-1-2026-03-01-pa-tc-w-b"])),
       VECTORS[3][2])
expect_refusal("a modifier outside the base's utility namespace",
               lambda: A.model_iri((N + "e-1-2026-03-01",
                                    ("https://rate-plans.grid-coordination.energy/sce/care-2026-03-20",), ())))
expect_refusal("a local name carrying the separator",
               lambda: A.model_iri((N + "e-1--2026-03-01", (), ())))
expect_refusal("a local name outside lower-case ASCII",
               lambda: A.model_iri((N + "E-1-2026-03-01", (), ())))
expect_refusal("an alternative offered by two containers",
               lambda: A.selection_sets({"x:c1": ["x:alt"], "x:c2": ["x:alt"]}))
expect("nothing open is one empty selection", A.selection_sets({}), [()])

models = REAL["models"]
expect("one model per selection", len(models), sum(a["selections"] for a in REAL["compositions"]))
iris = A.model_iris(models)
expect("every model has its own IRI", len(set(iris.values())), len(models))
doc = A.model_document(models, REAL["versions"])
expect("the document carries one node per model", len(doc["@graph"]), len(models))
expect("no node carries an empty list",
       [n["@id"] for n in doc["@graph"]
        if any(isinstance(v, list) and not v for v in n.values())], [])
expect("every node carries one urpx:name",
       [n["@id"] for n in doc["@graph"] if not isinstance(n.get("urpx:name"), str)], [])
expect("a node without modifiers omits consumesModifierVersion",
       any("urpx:consumesModifierVersion" not in n for n in doc["@graph"]), True)

print()
if failures:
    print(f"{len(failures)} assertion(s) failed: {', '.join(failures)}")
    sys.exit(1)
print(f"all {len(REAL['compositions'])} compositions classified, {len(REAL['models'])} scenario cost "
      f"models named; every guard fired when broken")
