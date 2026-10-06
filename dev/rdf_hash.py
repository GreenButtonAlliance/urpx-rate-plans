#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""A sha256 of a JSON-LD document's RDF content, not of its bytes.

Two documents that state the same triples hash the same, however their JSON is
indented, ordered or keyed, and whatever their blank nodes are labeled. A change
to any IRI, literal or datatype changes the hash.

Method:
  1. Parse the JSON-LD with rdflib against a fixed base IRI (BASE), so a
     relative IRI resolves the same wherever the file sits on disk.
  2. rdflib.compare.to_canonical_graph, which relabels blank nodes
     deterministically from the graph's structure (rdflib's RGDA1 algorithm).
  3. Serialize as N-Triples, sort the lines, join them with "\\n" and take the
     sha256 of the UTF-8 bytes.

Literals keep their lexical form: xsd:decimal "1.50" and "1.5" hash differently.

URDNA2015 via pyld would also do; pyld is not in dev/requirements.txt and rdflib
is, so this uses rdflib. The two do not produce the same hash, and a recorded
hash is only comparable with one computed by this function.

Run: python3 dev/rdf_hash.py FILE...   prints "<sha256>  <file>" per file
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from rdflib import Graph
from rdflib.compare import to_canonical_graph

BASE = "urn:x-rdf-hash:base/"


def graph_of(text: str) -> Graph:
    g = Graph()
    g.parse(data=text, format="json-ld", publicID=BASE)
    return g


def rdf_sha256_text(text: str) -> str:
    """The canonical RDF hash of a JSON-LD document given as text."""
    canonical = to_canonical_graph(graph_of(text))
    lines = sorted(
        line for line in canonical.serialize(format="nt").splitlines() if line.strip()
    )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def rdf_sha256(path: Path) -> str:
    """The canonical RDF hash of a JSON-LD file."""
    return rdf_sha256_text(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    for name in argv:
        print(f"{rdf_sha256(Path(name))}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
