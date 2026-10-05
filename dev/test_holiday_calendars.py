#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Negative tests for the holiday-calendar lint.

Each case copies a real filing into a temporary tree with the same
<utility>/<schedule>/versions/<date> shape, alters it, and asserts the lint's
verdict on the copy. Every guard is made to fire, and each spared shape is
checked to stay spared.

Run: python3 dev/test_holiday_calendars.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "lint_holiday_calendars", REPO / "dev" / "lint_holiday_calendars.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

LINT = REPO / "dev" / "lint_holiday_calendars.py"
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}{': ' + detail if detail else ''}")
        failures.append(name)


def copy_filing(tmp: Path, utility: str, schedule: str, date: str) -> Path:
    src = corpus.filing_dir(utility, schedule, date)
    dst = tmp / src.relative_to(REPO)
    dst.mkdir(parents=True)
    for p in src.iterdir():
        if p.suffix in (".jsonld", ".toml"):
            shutil.copy(p, dst / p.name)
    return dst


def edit_documents(d: Path, fn) -> None:
    for p in sorted(d.glob("*.jsonld")):
        doc = json.loads(p.read_text())
        p.write_text(json.dumps(fn(doc)))


def strip_keys(node, keys: set):
    if isinstance(node, dict):
        return {k: strip_keys(v, keys) for k, v in node.items() if k not in keys}
    if isinstance(node, list):
        return [strip_keys(x, keys) for x in node]
    return node


def map_calendars(node, fn):
    if isinstance(node, dict):
        return {k: (fn(v) if k == "urpx:hasHolidayCalendar" else map_calendars(v, fn))
                for k, v in node.items()}
    if isinstance(node, list):
        return [map_calendars(x, fn) for x in node]
    return node


def drop_deferral(d: Path, needle: str) -> None:
    """Remove the one deferral containing needle. Each deferral in these manifests
    sits on its own line, so the line is dropped and the result re-read to prove it."""
    t = d / "tariff.toml"
    before = corpus.load_toml(t)["modeling"]["deferrals"]
    t.write_text("".join(l for l in t.read_text().splitlines(keepends=True) if needle not in l))
    after = corpus.load_toml(t)["modeling"]["deferrals"]
    assert len(after) == len(before) - 1, "deferral to drop not found on one line"


def add_deferral(d: Path, text: str) -> None:
    t = d / "tariff.toml"
    before = corpus.load_toml(t)["modeling"]["deferrals"]
    src = t.read_text()
    if "deferrals = []" in src:
        src = src.replace("deferrals = []", f"deferrals = [{json.dumps(text)}]", 1)
    else:
        src = src.replace("deferrals = [", f"deferrals = [\n {json.dumps(text)},", 1)
    t.write_text(src)
    assert len(corpus.load_toml(t)["modeling"]["deferrals"]) == len(before) + 1


def status(d: Path) -> str:
    return L.check_filing(d)["status"]


def status_with(d: Path, base: Path) -> str:
    """The verdict on d with base's documents standing in for the corpus bases."""
    return L.check_filing(d, bases=L.base_index(sorted(base.glob("rate-plan_*.jsonld"))))["status"]


def cli(*dirs: Path) -> int:
    return subprocess.run([sys.executable, str(LINT), "--filing", *map(str, dirs)],
                          capture_output=True, text=True).returncode


def test_patterns() -> None:
    print("\nHOLIDAY_RULE: what counts as a stated holiday rule")
    rule = lambda s: [m for m in L.rule_matches(s) if not m[2]]
    spared = lambda s: [m for m in L.rule_matches(s) if m[2]]
    for s in ("On-peak 4 p.m. to 9 p.m. weekdays excluding holidays",
              "weekends/holidays midnight-2pm",
              "Weekend/Holiday table",
              "98 F on non-holiday weekdays",
              "Off-Peak overnight + weekends + holidays + non-summer",
              "6 AM to 10 AM is Super Off-Peak on a weekend or holiday"):
        check(f"rule: {s[:44]!r}", bool(rule(s)))
    for s in ("every day including weekends and holidays",
              "callable any hour, including holidays and weekends"):
        check(f"spared: {s[:44]!r}", not rule(s) and bool(spared(s)))
    for s in ("The eight holidays listed in Special Condition 1 have no rate consequence",
              "Holiday-aware (US federal holidays observed by CA utilities)"):
        check(f"no rule: {s[:44]!r}", not L.rule_matches(s))


def test_calendar_walk() -> None:
    print("\nCalendar: inline, by @id, and empty")
    hol = {"@type": "urpx:Holiday", "urpx:holidayName": "Christmas Day"}
    inline = {"@graph": [{"urpx:hasHolidayCalendar": {
        "@type": "urpx:HolidayCalendar", "urpx:hasHoliday": [hol]}}]}
    by_id = {"@graph": [{"urpx:hasHolidayCalendar": {"@id": "ex:cal"}},
                        {"@id": "ex:cal", "@type": "urpx:HolidayCalendar",
                         "urpx:hasHoliday": hol}]}
    empty = {"@graph": [{"urpx:hasHolidayCalendar": {
        "@type": "urpx:HolidayCalendar", "urpx:hasHoliday": []}}]}
    check("an inline calendar counts", L.scan_documents([inline])["holidays"] == 1)
    check("a calendar referenced by @id counts", L.scan_documents([by_id])["holidays"] == 1)
    check("a calendar with no Holiday does not count", L.scan_documents([empty])["holidays"] == 0)
    texts = L.scan_documents([{"@graph": [{"urpx:hasHolidayCalendar": {
        "@type": "urpx:HolidayCalendar", "urpx:hasHoliday": [
            dict(hol, **{"urpx:holidayRule": "weekends and holidays"})]}}]}])["texts"]
    check("text inside a calendar is not a signal", not any("weekends" in t for t in texts))


def test_copies(tmp: Path) -> None:
    print("\nCopies of real filings")
    d = copy_filing(tmp / "a", "sdge", "tou-dr1", "2026-04-01")
    check("unaltered tou-dr1 carries a calendar", status(d) == "calendar", status(d))
    check("CLI passes the unaltered copy", cli(d) == 0)

    edit_documents(d, lambda doc: strip_keys(doc, {"urpx:hasHolidayCalendar"}))
    check("tou-dr1 with its calendar removed is MISSING", status(d) == "missing", status(d))
    check("CLI exits 1 on it", cli(d) == 1)

    edit_documents(d, lambda doc: strip_keys(doc, {"urpx:includeHolidays", "urpx:includeNonHolidays"}))
    r = L.check_filing(d)
    check("with the flags removed too, the text signal alone still fails it",
          r["status"] == "missing" and r["flags"] == 0, str(r))

    d = copy_filing(tmp / "b", "sce", "tou-d-prime", "2026-03-20")
    edit_documents(d, lambda doc: map_calendars(
        doc, lambda c: dict(c, **{"urpx:hasHoliday": []})))
    check("a calendar emptied of Holidays is MISSING", status(d) == "missing", status(d))

    d = copy_filing(tmp / "c", "pge", "ev2", "2026-03-27")
    check("pge ev2 ('including weekends and holidays') states no rule",
          status(d) == "no-rule", status(d))

    d = copy_filing(tmp / "d", "pge", "nbt", "2025-10-17")
    check("pge nbt is DEFERRED by its recorded deferral", status(d) == "deferred", status(d))
    drop_deferral(d, "The 576 TimeBrackets distinguish only urpx:weekdayDays")
    check("pge nbt without that deferral is MISSING", status(d) == "missing", status(d))

    d = copy_filing(tmp / "e", "pge", "nbt", "2025-10-17")
    t = d / "tariff.toml"
    t.write_text(re.sub(r"calendar", "list", t.read_text(), flags=re.I))
    check("a holiday deferral that does not name the calendar does not cover",
          status(d) == "missing", status(d))

    d = copy_filing(tmp / "h", "sdge", "nbt", "2025-01-27")
    r = L.check_filing(d)
    check("sdge nbt, holiday-flagged with no calendar of its own, INHERITS ev-tou-5's",
          r["status"] == "inherited" and r["flags"] and list(r["base_calendars"]) == ["sdge:ev-tou-5"],
          str(r))
    check("CLI passes it", cli(d) == 0)
    base = copy_filing(tmp / "h-base", "sdge", "ev-tou-5", "2026-04-01")
    check("against an unaltered ev-tou-5 copy it still inherits",
          status_with(d, base) == "inherited", status_with(d, base))
    edit_documents(base, lambda doc: strip_keys(doc, {"urpx:hasHolidayCalendar"}))
    check("against an ev-tou-5 with no calendar it is MISSING",
          status_with(d, base) == "missing", status_with(d, base))
    r = L.check_filing(d, bases={})
    check("against no base filing at all it is MISSING", r["status"] == "missing", str(r))
    add_deferral(d, "Weekends and holidays are priced apart from weekdays, and this "
                    "filing carries no HolidayCalendar.")
    check("with no base calendar, a deferral naming the calendar still covers the modifier",
          L.check_filing(d, bases={})["status"] == "deferred")

    d = copy_filing(tmp / "i", "sce", "nbt", "2025-04-23")
    check("sce nbt INHERITS tou-d-prime's calendar", status(d) == "inherited", status(d))
    edit_documents(d, lambda doc: strip_keys(doc, {"urpx:includeHolidays", "urpx:includeNonHolidays"}))
    r = L.check_filing(d)
    check("sce nbt with its holiday flags removed is MISSING on its text signal",
          r["status"] == "missing" and r["flags"] == 0, str(r))

    d = copy_filing(tmp / "g", "sdge", "tou-dr1", "2026-04-01")
    edit_documents(d, lambda doc: strip_keys(doc, {"urpx:hasHolidayCalendar"}))
    add_deferral(d, "Weekends and holidays are priced apart from weekdays, and this "
                    "filing carries no HolidayCalendar.")
    r = L.check_filing(d)
    check("a base plan with a covering deferral and no calendar is MISSING",
          r["status"] == "missing" and r["covering_deferrals"] and not r["modifier"], str(r))
    check("CLI exits 1 on it", cli(d) == 1)

    d = copy_filing(tmp / "f", "pge", "e-rsmart", "2025-10-31")
    check("e-rsmart is ALLOWLISTED", status(d) == "allowlisted", status(d))
    edit_documents(d, lambda doc: {"@graph": [doc, {"urpx:hasHolidayCalendar": {
        "@type": "urpx:HolidayCalendar",
        "urpx:hasHoliday": {"@type": "urpx:Holiday", "urpx:holidayName": "x"}}}]})
    check("an allowlisted filing that gains a calendar is a STALE entry",
          status(d) == "stale-allowlist", status(d))
    check("CLI exits 1 on a stale entry", cli(d) == 1)

    check("CLI refuses (3) a directory that is not a filing", cli(tmp) == 3)


def test_corpus() -> None:
    print("\nThe live corpus")
    p = subprocess.run([sys.executable, str(LINT), "--json"], capture_output=True, text=True)
    check("the lint passes the corpus", p.returncode == 0, p.stderr[-400:])
    res = json.loads(p.stdout) if p.returncode in (0, 1) else []
    n = sum(r["status"] == "calendar" for r in res)
    check("it checks a non-trivial number of calendars", n >= 10, f"only {n}")
    inherited = sorted(r["filing"] for r in res if r["status"] == "inherited")
    check("sce nbt and sdge nbt inherit their bases' calendars",
          inherited == ["sce/nbt/2025-04-23", "sdge/nbt/2025-01-27"], str(inherited))


if __name__ == "__main__":
    test_patterns()
    test_calendar_walk()
    with tempfile.TemporaryDirectory() as tmp:
        test_copies(Path(tmp))
    test_corpus()
    print()
    if failures:
        print(f"{len(failures)} failure(s): {', '.join(failures)}")
        raise SystemExit(1)
    print("holiday-calendar lint: every guard fired and every spared shape was spared")
