#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Tests for dev/rdf_hash.py: what keeps the canonical RDF hash and what moves it.

Run: python3 dev/test_rdf_hash.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from rdflib import Graph

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
from rdf_hash import rdf_sha256, rdf_sha256_text  # noqa: E402

DOC = REPO / "us/ca/pge/electricity/e-tou-c/versions/2026-03-01/rate-plan_pge_e-tou-c_2026-03-01.jsonld"
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok or not detail else ': ' + detail}")
    if not ok:
        failures.append(name)


def first_unit_price(node):
    """The first dict carrying urpx:unitPrice, searched depth first."""
    if isinstance(node, dict):
        if "urpx:unitPrice" in node:
            return node
        node = list(node.values())
    if isinstance(node, list):
        for v in node:
            found = first_unit_price(v)
            if found is not None:
                return found
    return None


def main() -> int:
    text = DOC.read_text()
    doc = json.loads(text)
    base = rdf_sha256(DOC)
    check("hash is 64 hex digits", len(base) == 64 and all(c in "0123456789abcdef" for c in base))
    check("hash is stable across calls", rdf_sha256_text(text) == base)

    check("compact JSON keeps the hash",
          rdf_sha256_text(json.dumps(doc, separators=(",", ":"))) == base)
    check("sorted keys and other indentation keep the hash",
          rdf_sha256_text(json.dumps(doc, sort_keys=True, indent=1)) == base)
    reordered = dict(reversed(list(doc.items())))
    reordered["@graph"] = list(reversed(doc["@graph"]))
    check("reversed key and @graph order keep the hash",
          rdf_sha256_text(json.dumps(reordered, indent=4)) == base)

    g = Graph()
    g.parse(data=text, format="json-ld")
    check("the same triples written by another serializer keep the hash",
          rdf_sha256_text(g.serialize(format="json-ld")) == base)

    blank = {"@context": {"ex": "http://example.org/"},
             "@graph": [{"@id": "ex:s", "ex:p": {"@id": "_:a"}},
                        {"@id": "_:a", "ex:q": "v", "ex:r": {"@id": "_:b"}},
                        {"@id": "_:b", "ex:q": "w"}]}
    relabeled = json.loads(json.dumps(blank).replace("_:a", "_:zz9").replace("_:b", "_:k"))
    unlabeled = {"@context": blank["@context"],
                 "@id": "ex:s", "ex:p": {"ex:q": "v", "ex:r": {"ex:q": "w"}}}
    h = rdf_sha256_text(json.dumps(blank))
    check("blank node labels do not matter", rdf_sha256_text(json.dumps(relabeled)) == h)
    check("labeled and unlabeled blank nodes hash alike", rdf_sha256_text(json.dumps(unlabeled)) == h)

    changed = json.loads(text)
    price = first_unit_price(changed["@graph"])
    price["urpx:unitPrice"] = str(float(price["urpx:unitPrice"]) + 0.01)
    check("changing a price changes the hash", rdf_sha256_text(json.dumps(changed)) != base)

    added = json.loads(text)
    added["@graph"].append({"@id": "pge:test-node", "urpx:name": "added"})
    check("adding a triple changes the hash", rdf_sha256_text(json.dumps(added)) != base)

    renamed = json.loads(json.dumps(blank).replace("ex:q", "ex:qq"))
    check("changing a predicate changes the hash", rdf_sha256_text(json.dumps(renamed)) != h)

    def price(v):
        return json.dumps({"@context": {"ex": "http://example.org/",
                                        "xsd": "http://www.w3.org/2001/XMLSchema#"},
                           "@id": "ex:s",
                           "ex:price": {"@value": v, "@type": "xsd:decimal"}})
    check("a negative zero hashes as zero",
          rdf_sha256_text(price("-0.00000")) == rdf_sha256_text(price("0.00000")))
    check("a negative zero keeps its scale",
          rdf_sha256_text(price("-0.00000")) != rdf_sha256_text(price("0.0")))
    check("a negative nonzero value keeps its sign",
          rdf_sha256_text(price("-0.00001")) != rdf_sha256_text(price("0.00001")))

    print(f"{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
