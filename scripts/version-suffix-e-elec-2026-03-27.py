#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Rename collision-affected subordinate IRIs in PG&E E-ELEC 2026-03-27 to be
version-distinct from the 2026-01-01 sibling, in preparation for adding
urpx:supersedes pge:e-elec-2026-01-01.

Per URI identity: a single IRI must denote a single resource. When the 2026-03-27
reissue substantively changed (a) the eligibility ConditionExpression operands
and (b) the per-component distribution rates, the resources whose semantics
diverged from 2026-01-01 cannot continue to share IRIs with their predecessors.

Rename scheme:
  pge:<descriptor>  →  pge:e-elec-2026-03-27-<descriptor>

The 2026-01-01 file is left untouched (its IRIs are the canonical "old" version).
Only the 2026-03-27 file is rewritten.

Idempotent (skips rename if @id already starts with pge:e-elec-2026-03-27-).
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "ca" / "iou" / "pge" / "e-elec" / "versions" / "2026-03-27" / "rate-plan_pge_e-elec_2026-03-27.jsonld"

VERSION_TAG = "e-elec-2026-03-27"

# IRIs to version-suffix: those whose content differs from the 2026-01-01 sibling.
# Discovered via:
#   - @id-less content fingerprint comparison (catches Price value updates,
#     PriceSet membership changes, PriceDefinition wiring changes)
#   - SHACL validation focus-node analysis (catches ComparisonNodes whose
#     blank-node operand subtrees differ — not visible in the fingerprint diff
#     because blank-node JSON serializes equal even when underlying RDF differs)
COLLIDING_IRIS = [
    # ComparisonNodes (different operands per version)
    "pge:cn-ev-charging",
    "pge:cn-heat-pump",
    "pge:cn-nbt",
    "pge:cn-residential",
    "pge:cn-storage",
    # PriceDefinition (different hasCalculationMethod wiring)
    "pge:pd-base-charge",
    # Prices (different unitPrice values per Sheet 3 reissue)
    "pge:price-dist-summer-off-peak",
    "pge:price-dist-summer-part-peak",
    "pge:price-dist-summer-peak",
    "pge:price-dist-winter-off-peak",
    "pge:price-dist-winter-part-peak",
    "pge:price-dist-winter-peak",
    "pge:price-public-purpose",
    "pge:price-recovery-bond",
    "pge:price-recovery-bond-credit",
    "pge:price-transmission-adj",
    "pge:price-wildfire-hardening",
    # PriceSets (different hasPrice membership; their child Prices' content
    # differs so the containers themselves diverge by transitivity)
    "pge:ps-adjustment-charges",
    "pge:ps-distribution-charges",
    # Ancestors of the renamed ComparisonNodes — their content references the
    # renamed children, so by transitivity they also collide on content with
    # the 2026-01-01 siblings.
    "pge:bn-qualifying-technology-or",   # BooleanOperationNode wrapping cn-nbt/heat-pump/ev-charging/storage
    "pge:cx-qualifying-technology",      # ConditionExpression wrapping the BooleanOperationNode above
    "pge:cx-residential",                # ConditionExpression wrapping cn-residential
    "pge:er-qualifying-technology",      # EligibilityRule wrapping cx-qualifying-technology
    "pge:er-residential",                # EligibilityRule wrapping cx-residential
]


def build_rename_map():
    """pge:foo → pge:e-elec-2026-03-27-foo for each colliding IRI."""
    out = {}
    for old in COLLIDING_IRIS:
        prefix, descriptor = old.split(":", 1)
        new = f"{prefix}:{VERSION_TAG}-{descriptor}"
        out[old] = new
    return out


def rename_in_node(node, rename_map):
    """Walk node tree; rewrite both @id self-declarations and @id references."""
    n = 0
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "@id" and isinstance(v, str) and v in rename_map:
                node[k] = rename_map[v]
                n += 1
            else:
                n += rename_in_node(v, rename_map)
    elif isinstance(node, list):
        for v in node:
            n += rename_in_node(v, rename_map)
    return n


def main():
    rename_map = build_rename_map()
    with open(TARGET) as fh:
        data = json.load(fh)

    # Idempotency check: if any colliding @id already has the version tag, skip.
    sample_old = COLLIDING_IRIS[0]
    sample_new = rename_map[sample_old]

    def already_renamed(node):
        if isinstance(node, dict):
            if node.get("@id") == sample_new:
                return True
            return any(already_renamed(v) for v in node.values())
        if isinstance(node, list):
            return any(already_renamed(v) for v in node)
        return False

    if already_renamed(data):
        print(f"already renamed (skipping): {TARGET}")
        return

    n = rename_in_node(data, rename_map)
    with open(TARGET, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"renamed {n} @id references in {TARGET}")
    print(f"  {len(COLLIDING_IRIS)} distinct IRIs version-suffixed:")
    for old in COLLIDING_IRIS:
        print(f"    {old:<45} → {rename_map[old]}")


if __name__ == "__main__":
    main()
