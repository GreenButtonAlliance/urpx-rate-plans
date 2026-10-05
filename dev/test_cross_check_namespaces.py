#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Negative tests for dev/cross_check_scenario_cost_models.py: every way the
clj-urpx namespace can be missing must FAIL the check (exit 1), never pass it.

Each case points the check at a namespace list through URPX_CROSSCHECK_NAMESPACES
(first the API namespace, then the other names probed) and asserts the exit
code and the line that names what is missing. One case asserts that
urpx.arrangements, the clj-urpx 0.35.0 name, does not load under the pin.

Run: python3 dev/test_cross_check_namespaces.py
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
CHECK = ["python3", "dev/cross_check_scenario_cost_models.py",
         "--at", "2026-07-15T17:00-07:00", "--combine", "at-most-one-modifier"]

failures: list[str] = []


def case(name: str, namespaces: str, want: str, extra_paths: str | None = None) -> None:
    env = dict(os.environ, URPX_CROSSCHECK_NAMESPACES=namespaces)
    if extra_paths:
        env["URPX_CROSSCHECK_EXTRA_PATHS"] = extra_paths
    proc = subprocess.run(CHECK, cwd=REPO, env=env, capture_output=True, text=True)
    if proc.returncode == 1 and want in proc.stdout:
        print(f"  PASS  {name}: exit 1, {want!r}")
        return
    print(f"  FAIL  {name}: exit {proc.returncode}, wanted 1 with {want!r}")
    print("        " + "\n        ".join(proc.stdout.strip().splitlines()[-4:]))
    failures.append(name)


case("neither namespace exists",
     "urpx.no-such-namespace,urpx.also-missing",
     "none of urpx.no-such-namespace, urpx.also-missing loads")
case("the API namespace is gone and another loads",
     "urpx.no-such-namespace,urpx.price",
     "urpx.no-such-namespace is absent and urpx.price loads")
case("the namespace loads without the vars the check calls",
     "urpx.price",
     "urpx.price lacks enumerate-pairs, enumerate, identity-tuple, node, rate-plans-iri, "
     "one-modifier-at-most, named-versions-add, repeated-ids-refuse")
case("the 0.35.0 namespace is gone under the pin",
     "urpx.arrangements",
     "none of urpx.arrangements loads")
with tempfile.TemporaryDirectory() as d:
    stub = pathlib.Path(d) / "urpx"
    stub.mkdir()
    (stub / "broken_stub.clj").write_text('(ns urpx.broken-stub)\n(throw (ex-info "boom" {}))\n')
    case("the namespace throws while loading", "urpx.broken-stub",
         "urpx.broken-stub IS on the classpath", extra_paths=d)

print()
if failures:
    print(f"{len(failures)} case(s) failed: {', '.join(failures)}")
    sys.exit(1)
print("every missing-namespace case fails the cross-check")
