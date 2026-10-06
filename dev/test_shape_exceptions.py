#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Fixtures for SHAPE_EXCEPTIONS in dev/validate-with-base.py.

Each exception drops results the v0.5.1 shapes report on a term proposed in an
open urpx-org/urpx pull request. Its failure mode is dropping too much: a result
the proposal would NOT remove disappears too, and the gate goes quiet on a real
defect. So most cases here are negatives: data the proposal itself rejects, or
that has nothing to do with it, must still fail.

The shapes are the v0.5.1 revision the corpus dispatches to; each fixture is
validated with pyshacl and the exception applied to its results.

Run: python3 dev/test_shape_exceptions.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import rdflib
from pyshacl import validate

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("vwb", REPO / "dev" / "validate-with-base.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

REV = v.URPX_NAMESPACE_REVS[v.NEW_URPX_NS]
SHAPES = v.load_graph(v.SHAPES_PATH, REV)
ONTOLOGY = v.load_graph(v.ONTOLOGY_PATH, REV)

PREFIX = """
@prefix urpx: <https://urpx.org/ns/ontology/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix ex: <https://example.org/> .
"""

# A rate plan's ladder tier, the target every adjusting bracket below names.
TARGET = """
ex:target a urpx:ServiceTier ; urpx:serviceTierNumber 1 ;
    urpx:hasServiceBracket ex:target-b .
ex:target-b a urpx:ServiceBracket ;
    urpx:lowerBound "0"^^xsd:decimal ; urpx:lowerBoundOperator urpx:greaterThanOrEqualOperator ;
    urpx:upperBound "10.0"^^xsd:decimal ; urpx:upperBoundOperator urpx:lessThanOrEqualOperator .
"""


def host(*brackets: str, tier_number: bool = False, price_definition: bool = False) -> str:
    """A modifier billing model hosting `brackets` (Turtle bodies) in one tier."""
    names = [f"ex:b{i}" for i in range(len(brackets))]
    out = ["ex:bm a urpx:BillingModel ; urpx:hasServiceTiers ex:sts ."]
    if price_definition:
        out.append("ex:bm urpx:hasPriceDefinition ex:pd . ex:pd a urpx:PriceDefinition .")
    out.append("ex:sts a urpx:ServiceTiers ; urpx:hasServiceTier ex:host .")
    out.append("ex:host a urpx:ServiceTier ; urpx:hasServiceBracket " + ", ".join(names) + " .")
    if tier_number:
        out.append("ex:host urpx:serviceTierNumber 1 .")
    for n, body in zip(names, brackets):
        out.append(f"{n} a urpx:ServiceBracket ; {body} .")
    return "\n".join(out)


ADJUST = 'urpx:adjustsServiceTier ex:target ; urpx:upperBoundOffset "1.9"^^xsd:decimal'

failures: list[str] = []


def run(ttl: str, shapes: rdflib.Graph = SHAPES):
    g = rdflib.Graph().parse(data=PREFIX + ttl, format="turtle")
    _, results, _ = validate(g, shacl_graph=shapes, ont_graph=ONTOLOGY, advanced=True)
    keys = v.violation_keys(results)
    kept, removed = v.except_proposed_terms(keys, g, shapes)
    return keys, kept, removed


def short(keys):
    return sorted({(f.rsplit("/", 1)[-1], p.rsplit("/", 1)[-1], c.rsplit("#", 1)[-1]) for f, p, c in keys})


def check(name: str, ok: bool, detail="") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if not ok and detail else ""))
    if not ok:
        failures.append(name)


def kept_on(kept, focus: str, path: str, comp: str) -> bool:
    return any(f.endswith("/" + focus) and p.endswith(path) and c.endswith(comp) for f, p, c in kept)


print(f"Shape exceptions, against URPX {REV}\n")

# Positive: what urpx-org/urpx#80 admits, and v0.5.1 rejects, is dropped whole.
keys, kept, removed = run(TARGET + host(ADJUST, 'urpx:adjustsServiceTier ex:target ; urpx:lowerBoundOffset "2.6"^^xsd:decimal'))
check("v0.5.1 rejects an adjusting bracket (fixture is live)", bool(keys), short(keys))
check("#80-conforming host: every result excepted", kept == [] and removed.get("BOUND_OFFSET_EXCEPTION") == len(keys), short(kept))

# Negative: a bracket carrying a bound AND an offset. #80's fourth branch
# forbids bounds and its other three forbid the new terms, so it fails there.
keys, kept, _ = run(TARGET + host(ADJUST + ' ; urpx:lowerBound "0"^^xsd:decimal ; '
                                  'urpx:lowerBoundOperator urpx:greaterThanOrEqualOperator'))
check("bound plus offset keeps its closed-shape result", kept_on(kept, "b0", "adjustsServiceTier", "ClosedConstraintComponent"), short(kept))

# Negative: two targets (#80 sets sh:maxCount 1).
keys, kept, _ = run(TARGET + "ex:target2 a urpx:ServiceTier ; urpx:serviceTierNumber 2 ."
                    + host(ADJUST + " ; urpx:adjustsServiceTier ex:target2"))
check("two targets are not excepted", kept_on(kept, "b0", "adjustsServiceTier", "ClosedConstraintComponent"), short(kept))

# Negative: a target that is itself a host (self-reference, #80's sh:node).
keys, kept, _ = run(host('urpx:adjustsServiceTier ex:host ; urpx:upperBoundOffset "1.9"^^xsd:decimal'))
check("a bracket adjusting its own host is not excepted", kept_on(kept, "b0", "adjustsServiceTier", "ClosedConstraintComponent"), short(kept))

# Negative: an offset that is a string (#80 types offsets xsd:decimal).
keys, kept, _ = run(TARGET + host('urpx:adjustsServiceTier ex:target ; urpx:upperBoundOffset "1.9"'))
check("a string offset is not excepted", kept_on(kept, "b0", "upperBoundOffset", "ClosedConstraintComponent"), short(kept))

# Negative: a tier with no serviceTierNumber whose brackets are ordinary ones.
# #80 admits a numberless tier only when every bracket in it adjusts.
keys, kept, _ = run(TARGET + "ex:plain a urpx:ServiceTier ; urpx:hasServiceBracket ex:plain-b ."
                    "ex:plain-b a urpx:ServiceBracket ; urpx:lowerBound \"0\"^^xsd:decimal ; "
                    "urpx:lowerBoundOperator urpx:greaterThanOrEqualOperator .")
check("a numberless tier with ordinary brackets keeps its minCount result",
      kept_on(kept, "plain", "serviceTierNumber", "MinCountConstraintComponent"), short(kept))

# Negative: a billing model with no price definition and no adjusting bracket.
keys, kept, _ = run("ex:bm a urpx:BillingModel .")
check("an empty billing model keeps its minCount result",
      kept_on(kept, "bm", "hasPriceDefinition", "MinCountConstraintComponent"), short(kept))

# Negative: an unrelated closed-shape result on an adjusting bracket.
keys, kept, _ = run(TARGET + host(ADJUST + ' ; urpx:name "x"'))
check("an unrelated property on an adjusting bracket still fails",
      kept_on(kept, "b0", "name", "ClosedConstraintComponent"), short(kept))

# urpx-org/urpx#71: daysOfWeek is excepted on a TimeBracket only.
keys, kept, removed = run("ex:tb a urpx:TimeBracket ; urpx:daysOfWeek urpx:monday .")
check("daysOfWeek on a TimeBracket is excepted",
      not kept_on(kept, "tb", "daysOfWeek", "ClosedConstraintComponent") and removed.get("DAYS_OF_WEEK_EXCEPTION", 0) >= 1,
      short(kept))
keys, kept, _ = run(TARGET + "ex:sb a urpx:ServiceBracket ; urpx:daysOfWeek urpx:monday ; "
                    "urpx:lowerBound \"0\"^^xsd:decimal ; urpx:lowerBoundOperator urpx:greaterThanOrEqualOperator .")
check("daysOfWeek on a ServiceBracket is not excepted",
      kept_on(kept, "sb", "daysOfWeek", "ClosedConstraintComponent"), short(kept))

# Switch-off: shapes that name an entry's terms make it drop nothing.
defining = rdflib.Graph()
for t in SHAPES:
    defining.add(t)
defining.add((rdflib.BNode(), v.SH.path, v.URPX.adjustsServiceTier))
keys, kept, removed = run(TARGET + host(ADJUST), shapes=defining)
check("shapes defining #80's terms switch BOUND_OFFSET_EXCEPTION off",
      "BOUND_OFFSET_EXCEPTION" not in removed and kept == keys and bool(keys), str(removed))

print()
if failures:
    print(f"{len(failures)} shape-exception assertion(s) failed")
    sys.exit(1)
print("all shape-exception assertions hold")
