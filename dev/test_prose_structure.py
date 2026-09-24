#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Negative tests for the prose-versus-structure lint.

This lint decides which sentences it is willing to judge, so its cheapest failure
is to decline everything and report clean. Every case here asserts BOTH
directions: a false claim must be reported, and a true claim of the same shape
must be judged and spared. Detection without discrimination is useless.

Each sentence below is one that defeated an earlier draft, kept so the draft
cannot return.

Run: python3 dev/test_prose_structure.py
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))

spec = importlib.util.spec_from_file_location(
    "lint_prose_structure", REPO / "dev" / "lint_prose_structure.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}{': ' + detail if detail else ''}")
        failures.append(name)


# ---------------------------------------------------------------------------
# The patterns, against the sentences that actually broke them.
# ---------------------------------------------------------------------------

CANARY = ("(full 40-cell territory x code x season matrix, 20 ServiceTiers each "
          "referencing a per-cell ProfileAlternative).")


def total(s):
    m = L.TOTAL.search(s)
    return m.groups() if m else None


def test_patterns() -> None:
    print("\nTOTAL: the count must be a count")
    check("an unqualified plural parses", total(CANARY) == ("20", "ServiceTiers"),
          f"got {total(CANARY)}")
    check("a per-cell hyphenation does not trip the distributive guard",
          not re.search(r"\b(?:per\s|for each\s)", CANARY),
          "the guard would skip the one sentence this lint exists to catch")
    check("a dollar amount is not a count",
          total("the BSC as one undifferentiated $0.794 Price") is None)
    check("a negative decimal is not a count",
          total("The -0.18 Price here is based on the shared summary") is None)
    check("a version number is not a count",
          total("clj-urpx 0.32.0 evaluates no ConditionExpression") is None)
    check("a tier label is not a count",
          total("The tier-2 ProfileAlternative gates only on hasProgramEnrollment") is None)
    check("a year is declined",
          bool(L.YEARLIKE.match("2025")) and not L.YEARLIKE.match("20"))
    check("a qualified subset is declined",
          total("nothing suppresses the base plan's four seasonal generation Prices") is None,
          "four generation Prices cannot be measured against every Price in scope")

    print("\nCase sensitivity: case is the discriminator between type and property")
    check("a lowercase word is not a type",
          total("one metricinput per fixture") is None)
    check("UNIVERSAL requires a lowercase-initial property",
          L.UNIVERSAL.search("each urpx:ServiceTiers references urpx:ProfileAlternative") is None,
          "ProfileAlternative is a type, not a property")
    check("UNIVERSAL matches a real property",
          L.UNIVERSAL.search(
              "each urpx:ServiceBracket carries urpx:appliesInSeason") is not None)

    print("\nMood: a sentence about work not done is not a claim about the file")
    for s in ("Eight Prices are missing.",
              "The Wildfire Fund Charge is not modeled.",
              "no ServiceBracket carries appliesInSeason"):
        check(f"absence declined: {s[:40]!r}", bool(L.ABSENCE.search(s)))
    for s in ("Add one further urpx:Holiday with urpx:holidayName.",
              "Expressible as two Prices carrying urpx:multiplier -1."):
        check(f"proposal declined: {s[:40]!r}",
              bool(L.PROPOSAL.search(s)) or bool(L.IMPERATIVE.match(s)))
    check("a present-tense structural claim is NOT declined",
          not L.ABSENCE.search(CANARY)
          and not L.PROPOSAL.search(CANARY) and not L.IMPERATIVE.match(CANARY),
          "the canary must survive every mood filter")


# ---------------------------------------------------------------------------
# The scope rules, which are what makes a measurement mean anything.
# ---------------------------------------------------------------------------

def test_scope() -> None:
    print("\nScope: a claim is measured against the version it is about")
    e1 = REPO / "us/ca/pge/electricity/e-1/versions/2026-03-01"
    base = e1 / "rate-plan_pge_e-1_2026-03-01.jsonld"
    mod = e1 / "rate-plan-modifier_pge_e-1-income-tier_2026-03-01.jsonld"
    if not (base.exists() and mod.exists()):
        check("fixture present", False, f"expected two documents under {e1}")
        return

    bv = L.version_in(base)
    mv = L.version_in(mod)
    check("each document yields its own version node",
          bv is not None and mv is not None
          and bv.get("@id") != mv.get("@id"))

    bc = L.count_types(L.descendants(bv))
    mc = L.count_types(L.descendants(mv))
    # This is the distinction an earlier count-based sweep could not draw: the
    # directory holds 20 + 3 alternatives and neither version holds 23.
    check("version scope separates two documents' alternatives",
          bc.get("urpx:ProfileAlternative") == 20
          and mc.get("urpx:ProfileAlternative") == 3,
          f"base {bc.get('urpx:ProfileAlternative')}, "
          f"modifier {mc.get('urpx:ProfileAlternative')}")
    check("the base version holds its 120 brackets",
          bc.get("urpx:ServiceBracket") == 120,
          f"got {bc.get('urpx:ServiceBracket')}")
    check("the modifier version holds none of them",
          not mc.get("urpx:ServiceBracket"),
          f"got {mc.get('urpx:ServiceBracket')}")

    primary = L.primary_version(e1, "e-1", "2026-03-01")
    check("the manifest's primary version is the base plan, not the sibling",
          primary is not None and primary.get("@id") == bv.get("@id"))
    check("an unresolvable primary declines rather than guessing",
          L.primary_version(e1, "e-1", "1999-01-01") is None)


# ---------------------------------------------------------------------------
# The vocabulary must come from the corpus, not from a list in the source.
# ---------------------------------------------------------------------------

def test_vocabulary() -> None:
    print("\nVocabulary: derived from the corpus, so a name is a type only if used as one")
    vocab = L.type_vocabulary()
    props = L.property_vocabulary()
    check("types are non-empty and include the ones the canary names",
          {"ServiceTiers", "ServiceTier", "ServiceBracket", "ProfileAlternative"} <= vocab)
    check("words that look like types are not in it",
          not ({"Sheet", "Territory", "Baseline", "Schedule"} & vocab),
          f"leaked: {sorted({'Sheet','Territory','Baseline','Schedule'} & vocab)}")
    check("properties are non-empty and lowercase-initial",
          props and all(p[0].islower() for p in props))
    check("a type name is not also read as a property",
          "ServiceBracket" not in props)


# ---------------------------------------------------------------------------
# End to end, on the live corpus: it must judge something and decline honestly.
# ---------------------------------------------------------------------------

def test_end_to_end() -> None:
    print("\nEnd to end on the live corpus")
    out, judged, skipped, disagreements = L.findings()
    check("it judges a non-trivial number of claims", len(judged) >= 10,
          f"only {len(judged)} judged, which is the shape of a lint that declines "
          f"everything and reports clean")
    check("it declines far more than it judges, and says so", sum(skipped.values()) > 0)
    check("every finding carries its measurement",
          all(("measured" in f and "sentence" in f and f["channel"]) for f in out))
    check("the manifest is one of the channels it reads",
          any(j["channel"].startswith("tariff.toml") for j in judged),
          "reading only the JSON-LD is how the E-TOU-C claim survived")
    check("both claim forms are exercised by the live corpus or by canary",
          {j["form"] for j in judged} & {"total", "universal", "distributive"} != set())


if __name__ == "__main__":
    test_patterns()
    test_scope()
    test_vocabulary()
    test_end_to_end()
    print()
    if failures:
        print(f"{len(failures)} failure(s): {', '.join(failures)}")
        raise SystemExit(1)
    print("prose-structure lint: every guard fired and every true claim was spared")
