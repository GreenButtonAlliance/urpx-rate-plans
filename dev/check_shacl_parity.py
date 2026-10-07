#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Compare the two SHACL engines result key by result key.

The gate's SHACL step runs on com.dcj/clj-shacl (dev/shacl_gate.clj); pyshacl
(dev/validate-with-base.py) stays runnable for a comparison period. This
validates the same units on both and compares, per unit, the status, the raw
(focus, path, component) keys before the shape exceptions, the keys kept after
them, and how many each exception removed. Keys are compared as multisets;
a blank-node focus is labelled differently by each engine, so those keys match
on path and component.

Units: the whole corpus merged, each utility merged, the scenario cost models
merged with the corpus at the revision dev/gate.sh pins (SCM_URPX_REV), and
every filing alone.

Exit: 0 every unit identical, 1 a difference, 3 refused (an engine produced
no answer, or there was nothing to compare). About five minutes, almost all
of it pyshacl.

Run: python3 dev/check_shacl_parity.py [--json OUT]
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from contextlib import redirect_stderr
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("vwb", REPO / "dev" / "validate-with-base.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

SCM_DOC = "reports/scenario-cost-models.jsonld"


def scm_rev() -> str:
    m = re.search(r"^SCM_URPX_REV=(\S+)$", (REPO / "dev" / "gate.sh").read_text(), re.M)
    if not m:
        raise SystemExit("REFUSED  no SCM_URPX_REV in dev/gate.sh")
    return m.group(1)


def units() -> list[dict]:
    rel = lambda p: str(p.relative_to(REPO))  # noqa: E731
    files = v.corpus_files()
    out = [{"name": "corpus", "files": [rel(f) for f in files], "extra": [], "rev": None}]
    for u in v.utilities():
        out.append({"name": u, "files": [rel(f) for f in v.corpus_files(u)], "extra": [], "rev": None})
    out.append({"name": "scenario-cost-models", "files": [rel(f) for f in files],
                "extra": [SCM_DOC], "rev": scm_rev()})
    for f in files:
        out.append({"name": "file:" + rel(f), "files": [rel(f)], "extra": [], "rev": None})
    return out


def pyshacl_unit(unit: dict) -> dict:
    captured = {}
    original = v.except_proposed_terms

    def capture(keys, data_graph, shapes_graph):
        kept, removed = original(keys, data_graph, shapes_graph)
        captured.update(raw=[list(k) for k in keys], removed=removed)
        return kept, removed

    v.except_proposed_terms = capture
    try:
        with redirect_stderr(io.StringIO()):
            status, kept = v.validate_files([REPO / f for f in unit["files"]], unit["name"],
                                            verbose=False, rev_override=unit["rev"],
                                            extra=[REPO / f for f in unit["extra"]])
    finally:
        v.except_proposed_terms = original
    return {"status": status, "raw": captured.get("raw", []),
            "kept": [list(k) for k in kept], "removed": captured.get("removed", {})}


def clj_units(spec_units: list[dict]) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        spec_path, out_path = Path(tmp) / "units.json", Path(tmp) / "out.json"
        spec_path.write_text(json.dumps(spec_units))
        r = subprocess.run(["clojure", "-M:shacl", "--dump", str(spec_path), str(out_path)],
                           cwd=REPO, capture_output=True, text=True)
        if r.returncode != 0 or not out_path.exists():
            print(r.stdout + r.stderr, file=sys.stderr)
            raise SystemExit("REFUSED  clj-shacl produced no dump")
        return json.loads(out_path.read_text())


def is_blank(focus: str) -> bool:
    """rdflib writes a blank node as its bare label, clj-shacl as _:label."""
    return focus.startswith("_:") or ":" not in focus


def as_counter(keys) -> Counter:
    """Keys as a multiset, every blank-node focus spelled `_:`. Each engine
    labels blank nodes its own way, so those keys match on path and component
    and count only."""
    return Counter(("_:" if is_blank(k[0]) else k[0], k[1], k[2]) for k in keys)


def only_in(a, b) -> list:
    return sorted((as_counter(a) - as_counter(b)).elements())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", metavar="OUT", help="also write every unit's comparison as JSON")
    args = ap.parse_args()

    spec_units = units()
    if len(spec_units) < 3:
        print("REFUSED  nothing to compare", file=sys.stderr)
        return 3
    clj = clj_units(spec_units)
    report, differing = {}, 0
    for unit in spec_units:
        name = unit["name"]
        py = pyshacl_unit(unit)
        cj = clj.get(name)
        if cj is None:
            print(f"REFUSED  clj-shacl has no result for {name}", file=sys.stderr)
            return 3
        blank = {e: sum(1 for k in d["raw"] if is_blank(k[0]))
                 for e, d in (("pyshacl", py), ("clj-shacl", cj))}
        diff = {
            "status": (py["status"], cj["status"]) if py["status"] != cj["status"] else None,
            "raw_only_pyshacl": only_in(py["raw"], cj["raw"]),
            "raw_only_clj_shacl": only_in(cj["raw"], py["raw"]),
            "kept_only_pyshacl": only_in(py["kept"], cj["kept"]),
            "kept_only_clj_shacl": only_in(cj["kept"], py["kept"]),
            "removed": (py["removed"], cj["removed"]) if py["removed"] != cj["removed"] else None,
        }
        same = not any(diff.values())
        differing += not same
        report[name] = {"same": same, "pyshacl_raw": len(py["raw"]), "clj_raw": len(cj["raw"]),
                        "kept": len(py["kept"]), "removed": py["removed"],
                        "blank_focus": blank, **diff}
        if not name.startswith("file:") or not same:
            removed = ", ".join(f"{k} {n}" for k, n in sorted(py["removed"].items()))
            print(f"{'OK  ' if same else 'DIFF'} {name}: raw {len(py['raw'])}/{len(cj['raw'])}, "
                  f"kept {len(py['kept'])}/{len(cj['kept'])}"
                  + (f", excepted {removed}" if removed else ""))
            for label in ("raw_only_pyshacl", "raw_only_clj_shacl",
                          "kept_only_pyshacl", "kept_only_clj_shacl"):
                if diff[label]:
                    paths = sorted({k[1].rsplit("/", 1)[-1] + " " + k[2].rsplit("#", 1)[-1]
                                    for k in diff[label]})
                    print(f"      {label}: {len(diff[label])} ({'; '.join(paths[:5])})")
            for label in ("status", "removed"):
                if diff[label]:
                    print(f"      {label}: pyshacl {diff[label][0]}, clj-shacl {diff[label][1]}")
    files = sum(1 for u in spec_units if u["name"].startswith("file:"))
    print(f"\n{len(spec_units) - differing}/{len(spec_units)} units identical "
          f"({files} single-file units, pyshacl/clj-shacl counts shown as a/b)")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 1 if differing else 0


if __name__ == "__main__":
    sys.exit(main())
