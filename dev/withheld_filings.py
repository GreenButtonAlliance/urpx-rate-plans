#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Filings withheld from resolution until the pinned clj-urpx can resolve them.

dev/withheld-filings.json is the one declaration. Each entry names a schedule
directory, the clj-urpx release that resolves it correctly, and why. This module
reads it for dev/scenario_cost_models.py; dev/validate_v020.clj and
dev/cross_check_scenario_cost_models.clj read the same file.

It refuses rather than withholding in two cases:

  STALE    deps.edn pins the entry's release or later. The filing can now be
           resolved, so the entry has to come out and the filing's baseline
           cells be recorded; withholding it any longer would hide it.
  ORPHAN   the entry's directory holds no filing, so it withholds nothing and
           would quietly withhold whatever later lands there.

Run it to print what is withheld:  python3 dev/withheld_filings.py

WHEN clj-urpx 0.39.0 LANDS (the SCL RTC and RTS entries)

  1. Pin it in deps.edn. This module then refuses until step 2.
  2. Remove both entries from dev/withheld-filings.json.
  3. clojure -M:validate --record-baseline, and review the diff. Only new
     plan|us/wa/scl/... rows may appear (plus whatever 0.39.0 itself moves).
     Hand-checked expected marginals for the 2026-01-01 versions, energy only
     (the per-day Base Service Charge is not in the marginal), RTC / RTS:
       Saturday 17:00 (summer- and winter-weekend-peak)    Peak      0.1610 / 0.1632
       weekday 17:00, not a holiday                        Peak      0.1610 / 0.1632
       Labor Day 17:00 and 07:00, Christmas 17:00 and 07:00 Mid-Peak 0.1409 / 0.1428
       any day 02:00 (the overnight probes)                Off-Peak  0.0805 / 0.0816
     The 2027-01-01 and 2028-01-01 versions refuse :not-yet-effective at every
     probe instant. No probe instant falls on a Sunday, so check one by hand
     (e.g. 2026-07-19 18:00 Pacific: Mid-Peak, 0.1409 / 0.1428) and a
     Monday-observed holiday (2027-07-05 18:00, on the 2027 versions: Mid-Peak,
     0.1479 / 0.1489).
  4. python3 dev/check_all.py, which regenerates the scenario cost models with
     scl:rtc and scl:rts as bases, then dev/gate.sh --full.
  5. Remove "withheld from resolution" from the SCL READMEs.
"""
from __future__ import annotations

import functools
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DECLARATION = REPO / "dev" / "withheld-filings.json"
DEPS = REPO / "deps.edn"


def _version(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", s))


def pinned_clj_urpx() -> str:
    m = re.search(r'clj-urpx\s*\{:mvn/version\s+"([^"]+)"', DEPS.read_text(), re.S)
    if not m:
        raise SystemExit(f"REFUSING: {DEPS.name} does not pin a clj-urpx version.")
    return m.group(1)


@functools.lru_cache(maxsize=None)
def entries() -> tuple[dict, ...]:
    """The declared entries, after the STALE and ORPHAN checks."""
    data = json.loads(DECLARATION.read_text())
    out = data.get("withheld") or []
    pinned = pinned_clj_urpx()
    for e in out:
        d = e["schedule_dir"]
        if _version(pinned) >= _version(e["until_clj_urpx"]):
            raise SystemExit(
                f"REFUSING: {DECLARATION.relative_to(REPO)} withholds {d} until clj-urpx "
                f"{e['until_clj_urpx']}, and deps.edn pins {pinned}. Remove the entry, record "
                f"the filing's baseline cells (clojure -M:validate --record-baseline) and "
                f"regenerate the scenario cost models (python3 dev/check_all.py)."
            )
        if not any((REPO / d).rglob("rate-plan*_*.jsonld")):
            raise SystemExit(
                f"REFUSING: {DECLARATION.relative_to(REPO)} withholds {d}, which holds no filing."
            )
    return tuple(out)


def withheld(rel_path: str | None) -> dict | None:
    """The entry withholding the repo-relative path, or None."""
    if not rel_path:
        return None
    for e in entries():
        if rel_path.startswith(e["schedule_dir"]):
            return e
    return None


if __name__ == "__main__":
    for e in entries():
        print(f"{e['schedule_dir']}  until clj-urpx {e['until_clj_urpx']}  ({e['cites']})")
    sys.exit(0)
