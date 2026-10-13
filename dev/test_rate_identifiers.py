#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Negative tests for the rate-identifier attestation map.

This repository has ten recorded instances of a check that passed while
verifying nothing, so every guard in dev/list_rate_identifiers.py is made to
fire here against a deliberately broken input, and the run fails if a guard
stays quiet.

Two of these guards exist because the first draft of the generator got the
answer wrong in exactly the way they now catch. It matched a vintage label
against the keyed composition's dimension IRIs and reported one hit, because
pge:e-elec-2026-03-27-pa-income-tier carries the digits 2026 in its version
date. And it matched "CCA" against a punctuation-stripped alt_name, turning
SDG&E's "TOUDR - C CARE" into "toudrccare" and putting 53 bundled records in the
delivery-only bucket. Both are asserted here against the real snapshot.

Run: python3 dev/test_rate_identifiers.py
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))

import list_rate_identifiers as R  # noqa: E402

failures: list[str] = []


def expect_refusal(name: str, fn) -> None:
    try:
        fn()
    except SystemExit as e:
        if "REFUSING" in str(e):
            print(f"  PASS  {name}: refused")
            return
        print(f"  FAIL  {name}: exited, but not as a refusal: {str(e)[:120]}")
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


# ---------------------------------------------------------------------------
# Fixtures: the smallest corpus and snapshot that produce a verdict at all
# ---------------------------------------------------------------------------

FILE = "us/ca/xx/electricity/nbt/versions/2025-01-01/rate-plan-modifier_xx_nbt_2025-01-01.jsonld"

GOOD_DOC = {
    "@type": "urpx:URPXPackage",
    "urpx:hasRatePlanModifier": {
        "@type": "urpx:RatePlanModifier",
        "urpx:hasVersion": {
            "@type": "urpx:RatePlanModifierVersion",
            "@id": "xx:nbt-2025-01-01",
            "urpx:hasPrice": [{
                "@type": "urpx:Price",
                "@id": "xx:nbt-price-v23-del-h00",
                "urpx:name": "DEMO-NBT 2023 VINTAGE Delivery Component "
                             "(MIDAS RIN: USCA-XYXX-0001-0000) — January weekday",
                "urpx:referencesPriceDefinition": {"@id": "xx:nbt-pd-delivery"},
                "urpx:hasApplicabilityRule": {
                    "@type": "urpx:ApplicabilityRule",
                    "@id": "xx:nbt-ar-v23",
                    "urpx:hasConditionExpression": {
                        "@type": "urpx:ConditionExpression",
                        "urpx:rootNode": {
                            "@type": "urpx:ComparisonNode",
                            "urpx:leftOperand": {
                                "@type": "urpx:CustomOperandNode",
                                "urpx:customConditionProperty": "NBT Vintage Label",
                            },
                            "urpx:rightOperand": {
                                "@type": "urpx:CustomOperandNode",
                                "urpx:stringValue": "NBT23",
                            },
                        },
                    },
                },
            }],
        },
    },
}

# Two distinct first halves and two distinct second halves, because a snapshot
# with fewer carries no observable structure and derive_grammar() refuses over
# it. The fixture has to clear the bar the real snapshot clears.
GOOD_RIDS = [
    {"rid": "USCA-XYXX-0001-0000", "utility": "XY", "rate_name": "DEMO-NBT 2023 VINTAGE",
     "alt_name": "DEMO"},
    {"rid": "USCA-XYXY-0001-0000", "utility": "XY", "rate_name": "DEMO-NBT 2023 VINTAGE",
     "alt_name": "DEMO"},
    {"rid": "USCA-ZWZW-0002-0000", "utility": "ZW", "rate_name": "OTHER", "alt_name": "OTHER"},
]


def _alternative_doc() -> dict:
    """GOOD_DOC with the vintage moved off the Price and onto a
    urpx:ProfileAlternative, the shape the NBT filings now carry."""
    doc = copy.deepcopy(GOOD_DOC)
    version = doc["urpx:hasRatePlanModifier"]["urpx:hasVersion"]
    price = version.pop("urpx:hasPrice")[0]
    cx = price.pop("urpx:hasApplicabilityRule")["urpx:hasConditionExpression"]
    version["urpx:hasProfileAlternatives"] = {
        "@type": "urpx:ProfileAlternatives", "@id": "xx:nbt-pa-vintage",
        "urpx:hasProfileAlternative": [{
            "@type": "urpx:ProfileAlternative", "@id": "xx:nbt-pa-vintage-nbt23",
            "urpx:hasConditionExpression": cx}]}
    version["urpx:hasPriceSetAlternatives"] = [{
        "@type": "urpx:PriceSetAlternatives", "@id": "xx:nbt-psa",
        "urpx:referencesProfileAlternatives": {"@id": "xx:nbt-pa-vintage"},
        "urpx:hasPriceSetAlternative": [{
            "@type": "urpx:PriceSetAlternative", "@id": "xx:nbt-psa-nbt23",
            "urpx:referencesProfileAlternative": {"@id": "xx:nbt-pa-vintage-nbt23"},
            "urpx:hasPrice": [price]}]}]
    return doc


def docs(doc=None) -> list[tuple[str, dict]]:
    return [(FILE, copy.deepcopy(doc if doc is not None else GOOD_DOC))]


def midas(rids=None, errors=None) -> dict:
    rids = copy.deepcopy(GOOD_RIDS if rids is None else rids)
    return {"generated_at": "2026-05-30T00:00:00Z", "rids": rids,
            "index": {r["rid"]: r for r in rids},
            "errors": {e["rid"]: e for e in (errors or [])}}


def attestation(**over) -> dict:
    a = R.group_attestations(R.extract_occurrences(docs()))[0]
    a.update({"base_slug": "demo", "compositions": [], "utility": "xx"})
    a.update(over)
    return a


print("=== the fixture itself produces a verdict, or none of the rest means anything ===")
BASE = attestation()
expect("the fixture parses to one attestation", BASE["rins"], ["USCA-XYXX-0001-0000"])
expect("the fixture's vintage is read off the rule", BASE["conditions"],
       (("NBT Vintage Label", "NBT23"),))
expect("the fixture is confirmed against the fixture snapshot",
       R.classify(BASE, midas())[0], R.CONFIRMED)

print()
print("=== the MIDAS snapshot ===")
expect_refusal("a missing snapshot",
               lambda: R.load_midas(REPO / "reports" / "no-such-file.json"))

with tempfile.TemporaryDirectory() as _d:
    tmp = Path(_d) / "midas-coverage.json"
    tmp.write_text(json.dumps({"rids": []}))
    expect_refusal("a snapshot with no identifiers", lambda: R.load_midas(tmp))
    tmp.write_text(json.dumps({"rids": [{"rid": "USCA-XYXX-0001-0000", "rate_name": ""},
                                        {"rid": "USCA-XYXY-0001-0000", "rate_name": None}]}))
    expect_refusal("a snapshot where no identifier has a rate_name", lambda: R.load_midas(tmp))

print()
print("=== the derived grammar ===")
expect_refusal("one identifier is not a structure",
               lambda: R.derive_grammar([GOOD_RIDS[0]]))
expect_refusal("a snapshot whose provider segments never vary",
               lambda: R.derive_grammar([
                   {"rid": "USCA-XYXY-0001-0000"}, {"rid": "USCA-XYXY-0002-0000"}]))
GRAMMAR = R.derive_grammar(GOOD_RIDS)
expect("a segment half the snapshot never shows is not well formed",
       R.well_formed("USCA-ZZXX-0001-0000", GRAMMAR)[0], False)
expect("a sub code the snapshot never shows is not well formed",
       R.well_formed("USCA-XYXX-0001-9999", GRAMMAR)[0], False)
expect("the fixture's own identifier is well formed",
       R.well_formed("USCA-XYXX-0001-0000", GRAMMAR)[0], True)

print()
print("=== where an identifier is allowed to appear ===")
notation = copy.deepcopy(GOOD_DOC)
notation["urpx:hasRatePlanModifier"]["urpx:hasIdentifier"] = {
    "@type": "urpx:RatePlanModifierIdentifier",
    "@id": "xx:nbt-rin",
    "urpx:scheme": {"@id": "urpx:caMidasRinScheme"},
    "skos:notation": "USCA-XYXX-0001-0000",
}
expect_refusal("an identifier lifted into a skos:notation",
               lambda: R.extract_occurrences(docs(notation)))

print()
print("=== an unattributable citation ===")


def _price(doc):
    return doc["urpx:hasRatePlanModifier"]["urpx:hasVersion"]["urpx:hasPrice"][0]


unparsable = copy.deepcopy(GOOD_DOC)
_price(unparsable)["urpx:name"] = "Delivery Component USCA-XYXX-0001-0000 January"
expect_refusal("a citation with no (MIDAS RIN: ...) block",
               lambda: R.extract_occurrences(docs(unparsable)))

no_charge = copy.deepcopy(GOOD_DOC)
del _price(no_charge)["urpx:referencesPriceDefinition"]
expect_refusal("a citation on a Price naming no PriceDefinition",
               lambda: R.extract_occurrences(docs(no_charge)))

no_rule = copy.deepcopy(GOOD_DOC)
del _price(no_rule)["urpx:hasApplicabilityRule"]
expect_refusal("a citation on a Price naming no ApplicabilityRule and in no PriceSetAlternative",
               lambda: R.extract_occurrences(docs(no_rule)))

empty_rule = copy.deepcopy(GOOD_DOC)
_price(empty_rule)["urpx:hasApplicabilityRule"] = {
    "@type": "urpx:ApplicabilityRule", "@id": "xx:nbt-ar-v23"}
expect_refusal("a citation whose rule states no condition",
               lambda: R.extract_occurrences(docs(empty_rule)))

ALT = R.group_attestations(R.extract_occurrences(docs(_alternative_doc())))[0]
expect("a Price under a PriceSetAlternative takes its vintage from the ProfileAlternative",
       (ALT["conditions"], ALT["profile_alternatives"]),
       ((("NBT Vintage Label", "NBT23"),), ["xx:nbt-pa-vintage-nbt23"]))

silent_alt = _alternative_doc()
del silent_alt["urpx:hasRatePlanModifier"]["urpx:hasVersion"]["urpx:hasProfileAlternatives"][
    "urpx:hasProfileAlternative"][0]["urpx:hasConditionExpression"]
expect_refusal("a citation whose enclosing ProfileAlternative states no condition",
               lambda: R.extract_occurrences(docs(silent_alt)))

expect_refusal("a corpus citing no identifier at all",
               lambda: R.extract_occurrences([(FILE, {"@type": "urpx:URPXPackage"})]))

print()
print("=== one attestation cannot be two claims ===")
two_labels = copy.deepcopy(GOOD_DOC)
second = copy.deepcopy(_price(two_labels))
second["@id"] = "xx:nbt-price-v23-del-h01"
second["urpx:name"] = ("DEMO-NBT 2023 VINTAGE Generation Component "
                       "(MIDAS RIN: USCA-XYXX-0001-0000) — January weekday")
two_labels["urpx:hasRatePlanModifier"]["urpx:hasVersion"]["urpx:hasPrice"].append(second)
expect_refusal("two Prices in one group citing the same identifier for different charges",
               lambda: R.group_attestations(R.extract_occurrences(docs(two_labels))))

print()
print("=== keying to a composition ===")
EMPTY_MODEL = {"versions": {}, "compositions": [], "dimensions": {}}
expect_refusal("a citing filing that is no version's home",
               lambda: R.attach_compositions([attestation()], EMPTY_MODEL))

ORPHAN_MODEL = {
    "versions": {"xx:nbt-2025-01-01": {"id": "xx:nbt-2025-01-01", "home": FILE, "slug": "nbt"}},
    "compositions": [], "dimensions": {},
}
expect_refusal("a version node that takes part in no composition",
               lambda: R.attach_compositions([attestation()], ORPHAN_MODEL))

print()
print("=== the corroboration test has to land at least once ===")
expect_refusal("not one asserted identifier found in the snapshot",
               lambda: R.require_some_corroboration(
                   {"USCA-XYXX-0001-0000": {"in_midas": False}}))

print()
print("=== name agreement, each condition able to fail ===")
expect("a snapshot record with no rate_name does not agree",
       R.agreement(BASE, {"rid": "USCA-XYXX-0001-0000", "rate_name": ""})[0], False)
expect("a rate_name the corpus name does not contain does not agree",
       R.agreement(BASE, {"rid": "USCA-XYXX-0001-0000", "rate_name": "SOMETHING ELSE"})[0], False)
expect("a rate_name that does not name the base schedule does not agree",
       R.agreement(dict(BASE, base_slug="other"),
                   {"rid": "USCA-XYXX-0001-0000", "rate_name": "DEMO-NBT 2023 VINTAGE"})[0],
       False)

print()
print("=== provenance, every state reachable ===")
expect("an identifier absent from the snapshot is unresolved",
       R.classify(BASE, midas(rids=GOOD_RIDS[1:]))[0], R.UNRESOLVED)
expect("an expression over two identifiers is derived",
       R.classify(dict(BASE, rins=["USCA-XYXX-0001-0000", "USCA-XYXY-0001-0000"],
                       expression="USCA-XYXX-0001-0000 − USCA-XYXY-0001-0000"),
                  midas())[0],
       R.DERIVED)
expect("an identifier the run could not read metadata for is derived",
       R.classify(BASE, midas(rids=GOOD_RIDS[1:],
                              errors=[{"rid": "USCA-XYXX-0001-0000", "error": "HTTP 404"}]))[0],
       R.DERIVED)
expect("an identifier whose rate_name disagrees is derived",
       R.classify(BASE, midas(rids=[dict(GOOD_RIDS[0], rate_name="UNRELATED")] + GOOD_RIDS[1:]))[0],
       R.DERIVED)

print()
print("=== the vintage check, both branches ===")
expect("a filing declaring no ProfileAlternatives cannot make a vintage selectable",
       R.vintage_is_selectable(dict(BASE, profile_alternatives=["xx:nbt-pa-vintage-nbt23"]),
                               {FILE: []}), False)
expect("a vintage a ProfileAlternative states is selectable",
       R.vintage_is_selectable(ALT, {FILE: ["NBT vintage"]}), True)
expect("a vintage a Price-level rule states is not, whatever the containers are named",
       R.vintage_is_selectable(BASE, {FILE: ["NBT23 vintage cohort"]}), False)

print()
print("=== the mirror-segment split, both branches ===")
IDS = [{"rin": "USCA-XXXY-0001-0000", "in_midas": False},
       {"rin": "USCA-XYXX-0001-0000", "in_midas": False}]
split = R.mirror_analysis(
    [{"rins": ["USCA-XXXY-0001-0000"], "price_definition": "gen"},
     {"rins": ["USCA-XYXX-0001-0000"], "price_definition": "del"}], IDS)
expect("identifiers used on different charges split by charge", split["splits_by_charge"], True)
overlap = R.mirror_analysis(
    [{"rins": ["USCA-XXXY-0001-0000"], "price_definition": "del"},
     {"rins": ["USCA-XYXX-0001-0000"], "price_definition": "del"}], IDS)
expect("identifiers used on the same charge do not", overlap["splits_by_charge"], False)
expect("no XX-first identifier means nothing to analyze",
       R.mirror_analysis([], [{"rin": "USCA-XYXY-0001-0000", "in_midas": True}])["suspect"], [])

print()
print("=== the repository scan ===")
saved = R.RIN
try:
    R.RIN = __import__("re").compile(r"NOTHING-MATCHES-THIS-[0-9]{9}")
    expect_refusal("a scan that finds no identifier in any tracked file", R.scan_repo)
finally:
    R.RIN = saved

print()
print("=== the real corpus and the real snapshot ===")
D = R.build()
t = D["tally"]
expect("every attestation is classified", sum(t.values()), len(D["attestations"]))
expect("every state is populated", sorted(k for k in R.STATES if t[k]), sorted(R.STATES))
expect("every attestation keys to at least one composition",
       [a["file"] for a in D["attestations"] if not a["compositions"]], [])
expect("no attestation cites an identifier twice",
       [a["expression"] for a in D["attestations"] if len(a["rins"]) != len(set(a["rins"]))], [])

# The structural walk and a flat text scan are two independent readings of the
# same files. A silent drop in the walk (a Price shape it stops recognizing)
# shows up here as a shortfall rather than as a smaller, greener report.
scanned = sum(s["tokens"] for s in D["sightings"]
              if s["is_filing"] and s["file"].endswith(".jsonld"))
# A Price stated in more than one place (the NBT 2025 export Prices, in both
# customer-segment cells of their vintage) is one occurrence but several copies
# of text, so the comparison is against every stated copy.
expect("the structural walk finds every token a text scan finds", D["stated_tokens"], scanned)
expect("distinct identifiers agree with the per-file scan",
       len(D["identifiers"]),
       len({r for s in D["sightings"] if s["is_filing"] and s["file"].endswith(".jsonld")
            for r in R.RIN.findall((REPO / s["file"]).read_text())}))

# The two bugs named in this file's docstring, asserted against the real data.
expect("every vintage is a selectable alternative in the filing that carries it",
       [a["expression"] for a in D["attestations"] if not a["vintage_is_selectable"]], [])
expect("no bundled record is counted as CCA-marked",
       sum(h["bundled_cca"] for h in D["segments"]["per_first_half"].values()), 0)

print()
if failures:
    print(f"{len(failures)} assertion(s) failed: {', '.join(failures)}")
    sys.exit(1)
print(f"all {len(D['attestations'])} attestations classified; every guard fired when broken")
