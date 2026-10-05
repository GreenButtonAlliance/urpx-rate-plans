#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Fail a filing that states a holiday rule and carries no urpx:HolidayCalendar.

Without a calendar a holiday resolves to whatever its weekday or weekend day type
gives. Thirteen TOU filings were in that state until 03f5ec3 (URPXT-4fg), each
saying in its own prose that holidays are priced differently.

A FILING STATES A HOLIDAY RULE when either signal fires:

  STRUCTURE  a TimeBracket in any of its documents carries urpx:includeHolidays
             or urpx:includeNonHolidays. Those flags resolve against a calendar
             and against nothing else.
  TEXT       a string literal in its JSON-LD outside the urpx:HolidayCalendar and
             urpx:Holiday nodes, or its tariff.toml, matches one of HOLIDAY_RULE:
             "non-holiday", "excluding holidays", "weekends and holidays",
             "holidays and weekends" and their slash, hyphen and "or" forms. A
             match preceded within two words by "including" is spared: "every day
             including weekends and holidays" (pge:ev2) says holidays get the
             same treatment as every other day.

A FILING SATISFIES IT when one of these holds:

  CALENDAR   a document attaches urpx:hasHolidayCalendar whose calendar carries
             at least one urpx:hasHoliday, inline or by @id in the same filing.
             This holds for a RatePlanModifier as for a base plan: a modifier's
             holiday flags resolve against its own calendar when it declares one
             (pge:nbt, whose base pge:e-elec prices every day alike and carries
             none).
  INHERITED  the filing is a RatePlanModifier whose TimeBrackets carry holiday
             flags and that declares no calendar of its own, and every filing in
             the corpus of every base RatePlan its urpx:applicableToRatePlan
             names carries a calendar. Such a modifier's holidays are the base
             plan's, so a base without one, or a base IRI no filing defines,
             fails.
  DEFERRAL   the filing is a RatePlanModifier (its directory holds no
             rate-plan_*.jsonld), and a [modeling].deferrals entry itself matches
             HOLIDAY_RULE and names the calendar ("no HolidayCalendar", "no
             holiday calendar"). The filing is listed on every run so the
             decision stays visible. A base RatePlan cannot defer: one that
             states a holiday rule carries a calendar.
  ALLOWLIST  the filing is in ALLOWLIST, with the reason stated there. An entry
             that no longer fires a signal, or now carries a calendar, fails as
             stale.

A STALE DEFERRAL fails a filing that satisfies CALENDAR or INHERITED while a
[modeling].deferrals entry still says the calendar or the holiday flags are
absent, matching CALENDAR_ABSENT: "no HolidayCalendar", "no holiday calendar",
"no urpx:hasHolidayCalendar", "no holiday flag(s)", brackets carrying "urpx:dayType
alone", or "holidays are not
modeled" and its "holiday calendar is not carried" forms. Deferrals about what a
present calendar does not yet express (a Sunday-to-Monday observance, dated
Holidays still to add) name the calendar or the holidays without saying either
is absent, and pass: "SCE's Sunday-to-Monday holiday observance is not modeled"
is about the observance, not the holidays.

Exit codes: 0 clean, 1 a violation, 3 the harness could not answer.

Usage:
    python3 dev/lint_holiday_calendars.py [--verbose] [--filing DIR ...]

--filing checks the named filing directories instead of the corpus; the negative
tests in dev/test_holiday_calendars.py use it on altered copies.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

_SEP = r"\s*(?:/|-|,|&|\+|\band\b|\bor\b)\s*"
HOLIDAY_RULE = (
    ("non-holiday", re.compile(r"\bnon-?holiday", re.I)),
    ("excluding holidays", re.compile(
        r"\b(?:excluding|except(?:\s+for)?|other\s+than)\s+(?:[\w']+\s+){0,3}?holidays?\b", re.I)),
    ("weekends and holidays", re.compile(r"\bweekends?" + _SEP + r"(?:[\w']+\s+)?holidays?\b", re.I)),
    ("holidays and weekends", re.compile(r"\bholidays?" + _SEP + r"(?:[\w']+\s+)?weekends?\b", re.I)),
)
INCLUSIVE = re.compile(r"\bincluding\s+(?:[\w']+\s+){0,2}$", re.I)
NAMES_CALENDAR = re.compile(r"calendar", re.I)
CALENDAR_ABSENT = re.compile(
    r"\bno\s+(?:urpx:)?(?:HolidayCalendar|hasHolidayCalendar|holiday\s+calendar)\b"
    r"|\bno\s+holiday\s+flags?\b|\b(?:urpx:)?dayType\s+alone\b"
    r"|\b(?:holidays|holiday\s+calendar|HolidayCalendar)\s+(?:is|are)\s+not\s+(?:modeled|carried)\b",
    re.I)

HOLIDAY_FLAGS = ("urpx:includeHolidays", "urpx:includeNonHolidays")
CALENDAR_NODE_TYPES = {"urpx:HolidayCalendar", "urpx:Holiday"}

# Keyed by <utility>/<schedule>/<date>. Each entry fires a signal and is not a
# holiday rule a calendar would carry.
ALLOWLIST = {
    "pge/e-rsmart/2025-10-31":
        "Holidays enter only the SmartDay event trigger (98 F on non-holiday weekdays, "
        "105 F on holidays and weekends), which PG&E applies when it calls an event. "
        "No price or window on the modifier differs on a holiday.",
}


class Refused(Exception):
    pass


def _rate_plan_iri(doc: dict):
    plan = doc.get("urpx:hasRatePlan")
    return plan.get("@id") if isinstance(plan, dict) else None


def base_index(files=None) -> dict[str, list[tuple[str, int]]]:
    """{RatePlan IRI: [(filing key, Holiday count), ...]} over base RatePlan
    documents, the corpus by default."""
    out: dict[str, list[tuple[str, int]]] = {}
    for p in (corpus.rate_plan_files() if files is None else files):
        doc = json.loads(Path(p).read_text())
        iri = _rate_plan_iri(doc)
        if iri:
            out.setdefault(iri, []).append(
                (filing_key(Path(p).resolve().parent), scan_documents([doc])["holidays"]))
    return out


_CORPUS_BASES: dict | None = None


def corpus_bases() -> dict:
    global _CORPUS_BASES
    if _CORPUS_BASES is None:
        _CORPUS_BASES = base_index()
    return _CORPUS_BASES


def applicable_bases(docs: list) -> list[str]:
    out: list[str] = []

    def visit(node: dict, _inside: bool) -> None:
        v = node.get("urpx:applicableToRatePlan")
        for x in (v if isinstance(v, list) else [v] if v else []):
            out.append(x["@id"] if isinstance(x, dict) else x)

    for doc in docs:
        _walk(doc, visit)
    return sorted(set(out))


def filing_key(d: Path) -> str:
    """<utility>/<schedule>/<date>, anchored on the `versions` segment so a copy
    under a temporary root keys the same as the original."""
    parts = d.parts
    if "versions" not in parts:
        raise Refused(f"{d} is not a filing directory (no 'versions' segment)")
    i = len(parts) - 1 - parts[::-1].index("versions")
    if i < 3 or i + 1 >= len(parts):
        raise Refused(f"{d} is not a filing directory")
    return f"{parts[i - 3]}/{parts[i - 1]}/{parts[i + 1]}"


def rule_matches(text: str) -> list[tuple[str, str, bool]]:
    """(rule, matched text, spared) for every HOLIDAY_RULE match in text."""
    out = []
    for name, pat in HOLIDAY_RULE:
        for m in pat.finditer(text):
            spared = bool(INCLUSIVE.search(text[max(0, m.start() - 40):m.start()]))
            out.append((name, " ".join(m.group(0).split()), spared))
    return out


def _types(node: dict) -> set:
    t = node.get("@type")
    return set(t if isinstance(t, list) else [t])


def _walk(node, fn, in_calendar=False):
    if isinstance(node, dict):
        inside = in_calendar or bool(_types(node) & CALENDAR_NODE_TYPES)
        fn(node, inside)
        for k, v in node.items():
            if k != "@context":
                _walk(v, fn, inside)
    elif isinstance(node, list):
        for x in node:
            _walk(x, fn, in_calendar)


def scan_documents(docs: list) -> dict:
    texts: list[str] = []
    flags = 0
    by_id: dict[str, dict] = {}
    attached: list = []

    def visit(node: dict, inside: bool) -> None:
        nonlocal flags
        if "@id" in node:
            by_id.setdefault(node["@id"], {}).update(node)
        for k, v in node.items():
            if k in HOLIDAY_FLAGS:
                flags += 1
            if k == "urpx:hasHolidayCalendar":
                attached.extend(v if isinstance(v, list) else [v])
            if not inside and not k.startswith("@") and isinstance(v, str):
                texts.append(v)

    for doc in docs:
        _walk(doc, visit)

    holidays = 0
    for cal in attached:
        node = cal if isinstance(cal, dict) else {"@id": cal}
        if set(node) <= {"@id"}:
            node = by_id.get(node.get("@id"), {})
        h = node.get("urpx:hasHoliday") or []
        holidays += len(h if isinstance(h, list) else [h])
    return {"texts": texts, "flags": flags, "calendars": len(attached), "holidays": holidays}


def check_filing(d: Path, bases: dict | None = None) -> dict:
    toml_path = d / corpus.TARIFF_MANIFEST
    docs_paths = sorted(d.glob("rate-plan_*.jsonld")) + sorted(d.glob("rate-plan-modifier_*.jsonld"))
    if not toml_path.exists() or not docs_paths:
        raise Refused(f"{d}: expected a tariff.toml and at least one JSON-LD document")
    docs = [json.loads(p.read_text()) for p in docs_paths]
    s = scan_documents(docs)
    toml_text = toml_path.read_text()
    manifest = corpus.load_toml(toml_path)

    matches = [m for t in s["texts"] + [toml_text] for m in rule_matches(t)]
    rule = sorted({m[1].lower() for m in matches if not m[2]})
    spared = sorted({m[1].lower() for m in matches if m[2]})
    deferrals = [" ".join(str(x).split()) for x in
                 ((manifest.get("modeling") or {}).get("deferrals") or [])]
    covering = [i + 1 for i, t in enumerate(deferrals)
                if NAMES_CALENDAR.search(t) and any(not m[2] for m in rule_matches(t))]
    absent = [i + 1 for i, t in enumerate(deferrals) if CALENDAR_ABSENT.search(t)]

    is_modifier = not any(p.name.startswith("rate-plan_") for p in docs_paths)
    key = filing_key(d)
    states = bool(s["flags"] or rule)
    has_calendar = s["holidays"] > 0
    base_calendars: dict[str, list[tuple[str, int]]] = {}
    if is_modifier and s["flags"] and not has_calendar:
        idx = corpus_bases() if bases is None else bases
        base_calendars = {iri: idx.get(iri, []) for iri in applicable_bases(docs)}
    inherits = bool(base_calendars) and all(
        v and all(h > 0 for _k, h in v) for v in base_calendars.values())
    if not states:
        status = "stale-allowlist" if key in ALLOWLIST else "no-rule"
    elif has_calendar:
        status = "stale-allowlist" if key in ALLOWLIST else "calendar"
    elif key in ALLOWLIST:
        status = "allowlisted"
    elif inherits:
        status = "inherited"
    elif covering and is_modifier:
        status = "deferred"
    else:
        status = "missing"
    if status in ("calendar", "inherited") and absent:
        status = "stale-deferral"
    return {"filing": key, "status": status, "flags": s["flags"], "rule": rule,
            "spared": spared, "holidays": s["holidays"], "calendars": s["calendars"],
            "covering_deferrals": covering, "absent_deferrals": absent,
            "modifier": is_modifier,
            "base_calendars": base_calendars}


FAILING = ("missing", "stale-allowlist", "stale-deferral")


def run(dirs: list[Path], whole_corpus: bool = True) -> list[dict]:
    corpus.require_nonempty(dirs, "filing directories")
    results = [check_filing(d) for d in dirs]
    if whole_corpus and not any(r["status"] in ("calendar", "inherited") + FAILING for r in results):
        raise Refused("no filing carries a holiday calendar and none is missing one, so "
                      "the check compared nothing; the calendar walk has probably broken")
    return results


def report(results: list[dict], verbose: bool) -> int:
    by: dict[str, list[dict]] = {}
    for r in results:
        by.setdefault(r["status"], []).append(r)
    bad = [r for r in results if r["status"] in FAILING]
    for r in bad:
        if r["status"] == "missing":
            why = []
            if r["flags"]:
                why.append(f"{r['flags']} includeHolidays/includeNonHolidays flag(s)")
            if r["rule"]:
                why.append("text: " + ", ".join(repr(x) for x in r["rule"][:4]))
            lacking = [f"{iri} ({', '.join(k for k, h in v if not h) or 'no filing'})"
                       for iri, v in r["base_calendars"].items() if not v or any(not h for _k, h in v)]
            tail = (f"; its holiday flags take their dates from its base, and "
                    f"{'; '.join(lacking)} carries none" if lacking else
                    ", and no [modeling].deferrals entry records that" if r["modifier"] else
                    "; a base RatePlan cannot defer it"
                    + (f" (deferral {', '.join('#' + str(i) for i in r['covering_deferrals'])}"
                       f" would excuse a modifier)" if r["covering_deferrals"] else ""))
            print(f"MISSING  {r['filing']}: states a holiday rule ({'; '.join(why)}) and "
                  f"carries no urpx:HolidayCalendar with a urpx:Holiday{tail}", file=sys.stderr)
        elif r["status"] == "stale-deferral":
            print(f"STALE    {r['filing']}: "
                  + ("carries a urpx:HolidayCalendar" if r["holidays"] else "inherits its base's calendar")
                  + f" but deferral {', '.join('#' + str(i) for i in r['absent_deferrals'])} "
                  "still says the calendar or holiday flags are absent", file=sys.stderr)
        else:
            print(f"STALE    {r['filing']}: on ALLOWLIST but "
                  + ("now carries a calendar" if r["holidays"] else "fires no signal"),
                  file=sys.stderr)
    for r in by.get("deferred", []):
        print(f"deferred     {r['filing']} (deferral "
              f"{', '.join('#' + str(i) for i in r['covering_deferrals'])})")
    for r in by.get("inherited", []):
        print(f"inherited    {r['filing']} from "
              + ", ".join(f"{iri} ({len(v)} filing{'s' if len(v) != 1 else ''})"
                          for iri, v in r["base_calendars"].items()))
    for r in by.get("allowlisted", []):
        print(f"allowlisted  {r['filing']}: {ALLOWLIST[r['filing']]}")
    if verbose:
        for r in results:
            print(f"  {r['status']:<15} {r['filing']:<36} flags={r['flags']:<3} "
                  f"holidays={r['holidays']:<3} rule={r['rule']} spared={r['spared']}")
    summary = (f"holiday calendars: {len(by.get('calendar', []))} carry one, "
               f"{len(by.get('inherited', []))} inherit their base's, "
               f"{len(by.get('deferred', []))} deferred, {len(by.get('allowlisted', []))} "
               f"allowlisted, {len(by.get('no-rule', []))} state no holiday rule, "
               f"{len(bad)} failing, over {len(results)} filings")
    print(summary, file=sys.stderr if bad else sys.stdout)
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--filing", nargs="+", type=Path,
                    help="check these filing directories instead of the corpus")
    args = ap.parse_args(argv)
    try:
        results = (run(args.filing, whole_corpus=False) if args.filing
                   else run(corpus.filing_dirs()))
    except (Refused, SystemExit) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001 - refusing is a distinct outcome
        print(f"REFUSED: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(results, indent=2))
        return 1 if any(r["status"] in FAILING for r in results) else 0
    return report(results, args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
