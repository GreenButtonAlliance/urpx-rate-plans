#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Which gate steps a set of changed paths selects, from dev/gate-steps.toml.

  python3 dev/gate_steps.py skipped < paths
      the `note` key of each corpus-scope step that has triggers and that no
      path matches, one per line. dev/gate.sh --fast skips exactly these, so a
      step missing from the table runs.
  python3 dev/gate_steps.py utilities KEY < paths
      the utilities whose per-utility trigger for step KEY some path matches,
      space separated.

Paths are read one per line, as `git diff --name-only` prints them.
Exit 3 when the table cannot be read or is malformed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import tomli

REPO = Path(__file__).resolve().parent.parent
TABLE = REPO / "dev" / "gate-steps.toml"
SCOPES = {"corpus", "per-utility"}
# A change to the gate itself selects every step for every utility.
GATE_ITSELF = re.compile(r"^dev/(gate\.sh|gate-steps\.toml|gate_steps\.py)$")
MODES = {"fast", "full"}


def load(path: Path = TABLE) -> dict:
    """The table, with every entry's fields checked."""
    with path.open("rb") as fp:
        table = tomli.load(fp)
    for kind, key in (("gate", "note"), ("check_all", "name")):
        for entry in table.get(kind, []):
            if not isinstance(entry.get(key), str):
                raise ValueError(f"[[{kind}]] entry without a {key}: {entry}")
            if entry.get("scope") not in SCOPES:
                raise ValueError(f"{entry[key]!r}: scope must be one of {sorted(SCOPES)}")
            if kind == "gate":
                modes = entry.get("modes")
                if not modes or not set(modes) <= MODES:
                    raise ValueError(f"{entry[key]!r}: modes must be a non-empty subset of {sorted(MODES)}")
            for pattern in entry.get("triggers", []):
                re.compile(pattern.replace("{utility}", "u"))
            if entry["scope"] == "per-utility" and not entry.get("triggers"):
                raise ValueError(f"{entry[key]!r}: a per-utility step needs triggers naming {{utility}}")
    return table


def matches(patterns: list[str], paths: list[str]) -> bool:
    return any(re.search(p, path) for p in patterns for path in paths)


def gate_itself(paths: list[str]) -> bool:
    return any(GATE_ITSELF.search(path) for path in paths)


def skipped(table: dict, paths: list[str]) -> list[str]:
    if gate_itself(paths):
        return []
    return [
        e["note"]
        for e in table.get("gate", [])
        if e["scope"] == "corpus" and e.get("triggers") and not matches(e["triggers"], paths)
    ]


def corpus_utilities() -> list[str]:
    """Utilities present in the corpus, via the shared discovery module."""
    sys.path.insert(0, str(REPO / "dev"))
    import corpus

    return sorted({corpus.utility_of(f) for f in corpus.all_filing_jsonld()})


def utilities(table: dict, key: str, paths: list[str], everyone: list[str]) -> list[str]:
    entry = next((e for e in table.get("gate", []) if e["note"] == key), None)
    if entry is None or entry["scope"] != "per-utility":
        raise ValueError(f"{key!r} is not a per-utility step in {TABLE.name}")
    if gate_itself(paths):
        return list(everyone)
    return [
        u
        for u in everyone
        if matches([p.replace("{utility}", re.escape(u)) for p in entry["triggers"]], paths)
    ]


def main(argv: list[str]) -> int:
    paths = [line for line in sys.stdin.read().splitlines() if line]
    try:
        table = load()
        if argv[1:] == ["skipped"]:
            print("\n".join(skipped(table, paths)))
        elif len(argv) == 3 and argv[1] == "utilities":
            print(" ".join(utilities(table, argv[2], paths, corpus_utilities())))
        else:
            print(__doc__, file=sys.stderr)
            return 3
    except (OSError, ValueError, re.error, tomli.TOMLDecodeError) as e:
        print(f"REFUSED: {TABLE.relative_to(REPO)}: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
