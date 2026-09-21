#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Negative fixtures for the version-dispatch harness.

The harness picks a shape set per file from that file's own @context urpx
binding, so migrated and unmigrated utilities can coexist during the waves. Its
failure mode is a silent PASS: if dispatch picks the wrong shapes, nothing is
targeted, pyshacl conforms trivially, and the run reports success. Without these
assertions the staged migration is LESS safe than a single cut.

Run: python3 dev/test_dispatch.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("vwb", REPO / "dev" / "validate-with-base.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

FX = REPO / "dev" / "fixtures"
# Hand-authored, NOT a live corpus file. An earlier version pointed at LADWP
# R-1A; wave 1 then migrated that file to v0.5.1 and three assertions silently
# degraded to trivially true. A fixture must not move under its own test.
V021_GOOD = FX / "v021-conforming.jsonld"
V051_GOOD = FX / "v051-conforming.jsonld"
V051_BAD = FX / "v051-missing-required.jsonld"

failures: list[str] = []


def check(name: str, got: str, want: str) -> None:
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: got {got}, want {want}")
    if not ok:
        failures.append(name)


def run(files, rev=None):
    """Validate, optionally FORCING a revision to simulate misdispatch."""
    if rev is None:
        status, _ = v.validate_files(files, "test", verbose=False)
        return status
    saved = v.dispatch_rev
    v.dispatch_rev = lambda _f: (rev, None)
    try:
        status, _ = v.validate_files(files, "test", verbose=False)
    finally:
        v.dispatch_rev = saved
    return status


print("Version-dispatch negative fixtures\n")

# Dispatch picks the right shapes from each file's own namespace.
check("v0.5.1 fixture, dispatched", run([V051_GOOD]), v.OK)
# Conformance is NOT the property under test and is expensive to fabricate: a
# conforming v0.2.1 RatePlan requires hasRatePlanVersion, which cascades through
# changeReason/hasPlanElements/hasPrices/publishedBy/serviceRole and onward. What
# matters is that the file is TARGETED rather than refused, which is what proves
# dispatch selected the right shapes.
check("v0.2.1 fixture, dispatched and targeted", run([V021_GOOD]), v.VIOLATIONS)

# The shapes actually bite: a missing required property is a real violation,
# not a vacuous pass.
check("v0.5.1 fixture missing urpx:name", run([V051_BAD]), v.VIOLATIONS)

# MISDISPATCH MUST REFUSE, NEVER PASS. This is the assertion the harness exists
# for. The two vocabularies use different namespaces, so the wrong shape set
# targets nothing, and "nothing targeted" must never be reported as conforming.
check("v0.5.1 file forced onto v0.2.1 shapes", run([V051_GOOD], "v0.2.1"), v.REFUSED)
check("v0.2.1 fixture forced onto v0.5.1 shapes",
      run([V021_GOOD], "origin/v0.5.1-candidate"), v.REFUSED)

# A mixed-vocabulary merged graph is refused rather than validated against
# either set, which would silently exempt half the files.
check("mixed-vocabulary set", run([V021_GOOD, V051_GOOD]), v.REFUSED)

print()
if failures:
    print(f"{len(failures)} assertion(s) failed: {', '.join(failures)}")
    sys.exit(1)
print("all dispatch assertions hold")
