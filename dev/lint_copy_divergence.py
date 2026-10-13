#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Fail when one node's copies disagree about anything unexplained.

dev/normalize_copies.py compares a FIXED LIST of properties across copies and
reconciles them. This is the other half: it compares EVERY property and
reconciles nothing, because the failure it exists for is a copy that differs in
a property nobody thought to put on a list.

THE CASE THAT MOTIVATED IT. cpau:e-nse-1-2025-09-01 had two definitions that
agreed on everything except urpx:applicableToRatePlanVersion, which only the
inlined copy carried. That was an artifact: commit 60e85a9 replaced the sibling
E-HRA block wholesale from its authority, dropping the same property there, and
did not touch the E-NSE-1 block. The survivor read as a deliberate claim for
five months. The copy-agreement lint could not see it, because that property is
deliberately NOT on its list: a property whose ABSENCE is meaningful cannot be
compared for agreement without first deciding what absence means, and that is
the open question this corpus is not entitled to settle in a lint.

So this one does not decide anything. It reports that two files disagree and
stops, which is the part a person should read.

WHY IT IS NOT DROWNED BY FALSE POSITIVES. Of the nodes that appear in more than
one file, the ones that diverge are plan or modifier identities whose copies
nest different versions of themselves. That is structural
and correct, so it is EXEMPTED BY DERIVATION rather than by an allowlist: the
exemption holds only while each copy nests the version whose own filing it sits
in. A plan copy nesting somebody else's version is not exempt and never was.

Exit 0 clean, 1 an unexplained divergence, 3 refused.

Run from repo root:  python3 dev/lint_copy_divergence.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
VERSION_CONTAINERS = ("urpx:hasRatePlanVersion", "urpx:hasRatePlanModifierVersion")


def typed_nodes(path: Path):
    doc = json.loads(path.read_text())
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("@id") and "@type" in node:
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(doc.get("@graph", [doc]))
    return found


def version_ids(value) -> set[str]:
    items = value if isinstance(value, list) else [value]
    return {i.get("@id") for i in items if isinstance(i, dict) and i.get("@id")}


def main() -> int:
    # corpus.all_filing_jsonld() rather than a glob rooted on "us": the root
    # belongs to COUNTRY_ROOTS, and a second country would have been invisible here.
    files = corpus.all_filing_jsonld()
    if not files:
        print("REFUSING: no filing JSON-LD under us/; nothing to compare.", file=sys.stderr)
        return 3

    occurrences: dict[str, list[tuple[str, dict]]] = collections.defaultdict(list)
    # Which version @ids does each FILE define in its own right? Used to decide
    # whether a differing version container is this copy nesting its own.
    defines: dict[str, set[str]] = {}
    for path in files:
        rel = str(path.relative_to(REPO))
        nodes = typed_nodes(path)
        defines[rel] = {n["@id"] for n in nodes if "Version" in str(n.get("@type", ""))}
        for node in nodes:
            occurrences[node["@id"]].append((rel, node))

    multi = {k: v for k, v in occurrences.items() if len(v) > 1}
    if not multi:
        print("REFUSING: no node appears in more than one file, so this "
              "comparison has no second side.", file=sys.stderr)
        return 3

    unexplained: list[str] = []
    exempted = 0
    for iri, entries in sorted(multi.items()):
        keys: set[str] = set()
        for _rel, node in entries:
            keys |= set(node)
        for key in sorted(keys):
            values = {json.dumps(corpus.canonical_value(node.get(key)), sort_keys=True)
                      for _rel, node in entries}
            if len(values) == 1:
                continue
            if key in VERSION_CONTAINERS and all(
                version_ids(node.get(key)) <= defines.get(rel, set())
                for rel, node in entries
            ):
                # Each copy nests only versions its own file defines. Structural.
                exempted += 1
                continue
            unexplained.append(
                f"{iri} disagrees on {key} across {len(entries)} file(s):\n"
                + "\n".join(f"      {rel}: {json.dumps(node.get(key), sort_keys=True)[:160]}"
                            for rel, node in entries)
            )

    compared = sum(len(v) for v in multi.values())
    if unexplained:
        print(f"copy divergence: {len(unexplained)} unexplained disagreement(s) "
              f"over {len(multi)} multi-file node(s)", file=sys.stderr)
        for u in unexplained:
            print(f"  ✗ {u}", file=sys.stderr)
        print("\n  These are not reconciled here on purpose. Read the history of the "
              "differing line: an inlined copy that survived a wholesale block "
              "replacement looks identical to a deliberate claim.", file=sys.stderr)
        return 1

    print(f"copy divergence: clean ({len(multi)} node(s) in more than one file, "
          f"{compared} occurrence(s) compared over every property, "
          f"{exempted} structural version-container difference(s) exempted by derivation)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
