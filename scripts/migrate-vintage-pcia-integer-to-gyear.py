#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Migrate PG&E vintage-PCIA ProfileAlternative right-operands from
urpx:integerValue (xsd:integer) to urpx:gYearValue (xsd:gYear).

Per urpx-org/urpx@4da3440 (2026-05-01), urpx:gYearValue (range xsd:gYear)
is now defined on CustomOperandNode + DatatypeOperandNode. Vintage years
are calendar years, so the gYear typing is more semantically faithful
than a bare integer.

Targets: 5 PG&E filings refactored to ProfileAlternatives in Site B
(commit 478d46d).

Per file, this script:
1. Adds "urpx:gYearValue": {"@type": "xsd:gYear"} to @context (idempotent).
2. Rewrites each ComparisonNode @id matching pge:cn-pa-vintage-{year}:
   removes urpx:integerValue from the rightOperand, adds urpx:gYearValue
   (string form of the year).
3. Rewrites hasPossibleValues entries from xsd:integer to xsd:gYear.

Idempotent: skips files where the migration is already applied.
"""
import json
import re
import sys
from pathlib import Path

CN_VINTAGE_RE = re.compile(r'^pge:cn-pa-vintage-(\d{4})$')


def add_gyear_context(data: dict) -> bool:
    ctx = data.get("@context")
    if not isinstance(ctx, dict):
        return False
    if "urpx:gYearValue" in ctx:
        return False
    ctx["urpx:gYearValue"] = {"@type": "xsd:gYear"}
    return True


def migrate_operands(node) -> int:
    """Walk the JSON-LD; for each ComparisonNode whose @id matches
    pge:cn-pa-vintage-YYYY, swap rightOperand integerValue → gYearValue.
    Returns number of substitutions made."""
    n = 0
    if isinstance(node, dict):
        cid = node.get("@id", "")
        if isinstance(cid, str):
            m = CN_VINTAGE_RE.match(cid)
            if m and node.get("@type") == "urpx:ComparisonNode":
                year = m.group(1)
                ro = node.get("urpx:rightOperand")
                if isinstance(ro, dict) and "urpx:integerValue" in ro:
                    ro.pop("urpx:integerValue")
                    ro["urpx:gYearValue"] = year
                    n += 1
        for v in node.values():
            n += migrate_operands(v)
    elif isinstance(node, list):
        for v in node:
            n += migrate_operands(v)
    return n


def migrate_possible_values(node) -> int:
    """Walk the JSON-LD; for each AlternativeDimension with the departureVintage
    URI, retype hasPossibleValues @list entries from xsd:integer → xsd:gYear
    (string form). Returns number of values retyped."""
    n = 0
    if isinstance(node, dict):
        if (node.get("@type") == "urpx:AlternativeDimension"
                and node.get("urpx:dimensionProperty", "").endswith("/departureVintage")):
            pv = node.get("urpx:hasPossibleValues")
            if isinstance(pv, dict):
                lst = pv.get("@list")
                if isinstance(lst, list):
                    for item in lst:
                        if (isinstance(item, dict)
                                and item.get("@type") == "xsd:integer"
                                and isinstance(item.get("@value"), int)):
                            item["@type"] = "xsd:gYear"
                            item["@value"] = str(item["@value"])
                            n += 1
        for v in node.values():
            n += migrate_possible_values(v)
    elif isinstance(node, list):
        for v in node:
            n += migrate_possible_values(v)
    return n


def main():
    if len(sys.argv) < 2:
        print("usage: migrate-vintage-pcia-integer-to-gyear.py <file.jsonld>", file=sys.stderr)
        sys.exit(2)
    p = Path(sys.argv[1])
    with open(p) as fh:
        data = json.load(fh)
    ctx_added = add_gyear_context(data)
    n_operands = migrate_operands(data)
    n_values = migrate_possible_values(data)
    if not (ctx_added or n_operands or n_values):
        print(f"no changes (already migrated): {p}")
        return
    with open(p, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"migrated: {p}  (ctx={ctx_added}, operands={n_operands}, possible_values={n_values})")


if __name__ == "__main__":
    main()
