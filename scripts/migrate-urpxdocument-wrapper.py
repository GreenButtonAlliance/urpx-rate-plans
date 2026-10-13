#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Restructure corpus filings to URPXDocument-wrapped shape.

URPX v0.2.0 (Decision #103) introduced urpx:URPXDocument as a top-level
wrapper carrying urpx:targetURPXVersion. The upstream pattern (per
test-cases/pge-e-elec-2026-01-01/) replaces the legacy '@graph: [RatePlan]'
shape with:

    {
      "@context": {... + urpx:targetURPXVersion: xsd:anyURI ...},
      "@type": "urpx:URPXDocument",
      "@id": "<prefix>:doc-<schedule>-<date>",
      "urpx:targetURPXVersion": "<v0.2.0 ontology URL>",
      "urpx:hasRatePlan": {<RatePlan or RatePlanModifier>}
    }

This migration is idempotent — already-migrated files (top-level
@type=urpx:URPXDocument) are skipped.

Usage:
    python scripts/migrate-urpxdocument-wrapper.py [--dry-run] [paths...]

Without paths, walks ca/ in the repository root.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
URPX_V020_URL = "https://github.com/urpx-org/urpx/raw/v0.2.0/ontology/urpx-ontology.ttl"


def derive_doc_id(prefix: str, schedule: str, date: str) -> str:
    return f"{prefix}:doc-{schedule}-{date}"


def detect_prefix(graph_entry: dict, context: dict) -> str:
    """Pick the namespace prefix from the inner resource's @id (e.g. 'pge', 'cpau')."""
    inner_id = graph_entry.get("@id", "")
    if ":" in inner_id:
        return inner_id.split(":", 1)[0]
    raise ValueError(f"cannot derive prefix from @id={inner_id!r}")


def parse_filing_path(path: Path) -> tuple[str, str]:
    """ca/<class>/<utility>/<schedule>/versions/<date>/rate-plan*.jsonld → (schedule, date)"""
    parts = path.parts
    versions_idx = parts.index("versions")
    schedule = parts[versions_idx - 1]
    date = parts[versions_idx + 1]
    return schedule, date


def add_target_urpx_version_to_context(context: dict) -> dict:
    """Insert urpx:targetURPXVersion: {@type: xsd:anyURI} into context if absent."""
    if "urpx:targetURPXVersion" in context:
        return context
    new_ctx = OrderedDict(context)
    new_ctx["urpx:targetURPXVersion"] = {"@type": "xsd:anyURI"}
    return new_ctx


def migrate(doc: dict, schedule: str, date: str) -> dict:
    """Apply the URPXDocument-wrapper transformation. Returns the new doc."""
    if doc.get("@type") == "urpx:URPXDocument":
        return doc  # already migrated

    if "@graph" not in doc:
        raise ValueError("filing has no @graph; cannot migrate")
    graph = doc["@graph"]
    if len(graph) != 1:
        raise ValueError(
            f"filing has {len(graph)} @graph entries; migration assumes 1"
        )

    inner = graph[0]
    inner_type = inner.get("@type")
    if inner_type == "urpx:RatePlan":
        wrapper_predicate = "urpx:hasRatePlan"
    elif inner_type == "urpx:RatePlanModifier":
        wrapper_predicate = "urpx:hasRatePlanModifier"
    else:
        raise ValueError(f"unexpected inner @type={inner_type!r}")

    prefix = detect_prefix(inner, doc.get("@context", {}))
    doc_id = derive_doc_id(prefix, schedule, date)

    new_doc = OrderedDict()
    new_doc["@context"] = add_target_urpx_version_to_context(doc["@context"])
    new_doc["@type"] = "urpx:URPXDocument"
    new_doc["@id"] = doc_id
    new_doc["urpx:targetURPXVersion"] = URPX_V020_URL
    new_doc[wrapper_predicate] = inner
    return new_doc


def discover_filings(roots: list[Path]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".jsonld":
            out.append(root)
        else:
            out.extend(sorted(root.rglob("rate-plan*.jsonld")))
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("paths", nargs="*", type=Path, help="Filings or directories to migrate")
    p.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = p.parse_args()

    roots = args.paths or [REPO_ROOT / "ca"]
    filings = discover_filings(roots)
    if not filings:
        print("No filings found.")
        return 1

    print(f"Migrating {len(filings)} filings (dry_run={args.dry_run})")
    migrated, already, errors = 0, 0, 0
    for path in filings:
        try:
            doc = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            print(f"  ✗ {path.relative_to(REPO_ROOT)}: invalid JSON — {e}")
            errors += 1
            continue

        if doc.get("@type") == "urpx:URPXDocument":
            already += 1
            continue

        schedule, date = parse_filing_path(path)
        try:
            new_doc = migrate(doc, schedule, date)
        except ValueError as e:
            print(f"  ✗ {path.relative_to(REPO_ROOT)}: {e}")
            errors += 1
            continue

        if not args.dry_run:
            path.write_text(json.dumps(new_doc, indent=2, ensure_ascii=False) + "\n")
        rel = path.relative_to(REPO_ROOT)
        print(f"  ✓ {rel}  (doc_id={new_doc['@id']})")
        migrated += 1

    print(f"\nDone: {migrated} migrated, {already} already-migrated, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
