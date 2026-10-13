#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Generate reports/version-continuity.{md,edn}: what periods can this corpus price?

Every urpx:RatePlanVersion states when it takes effect. A superseded one also
states when it stopped, as urpx:expirationDateTime, giving the half-open span
[effective, expiration) that clj-urpx's version-covers? implements. Laid end to
end per plan identity, those spans are the periods a consumer can get a price
for, and the holes between them are the periods it cannot.

WHY A GAP IS NOT A FAILURE HERE. A gap means a utility changed rates and this
corpus did not capture the document that made the change. It is backlog, not an
incident: the superseded sheets stay published in the utility's historical
archive (see us/ca/sce/utility.toml), so a gap is closed by fetching a document
that still exists, on whatever schedule suits. Reporting it as a breakage would
make a standing, recoverable condition look like an emergency every run, and a
gate that cries wolf gets bypassed.

BEFORE THE FIRST CAPTURED VERSION. Every plan and modifier identity states
urpx:initialEffectiveDate, when the schedule itself began. From then until its
earliest captured version the identity existed and this corpus holds no version
of it, so a consumer asking for a price there gets no answer and should know
why: the schedule was in force and was not modeled, which differs from an
instant before the schedule existed. These periods are listed apart from gaps
because they reach back years, sometimes decades, and are not a backfill queue.

WHAT IS A FAILURE is an OVERLAP: two versions of one plan both in force at one
instant. Nothing can resolve that without picking arbitrarily, and no tariff
means it. That refuses.

WHAT ACTUALLY PREVENTS GAPS is neither, and this report carries it as a column:
how long since each filing's source was last checked. Gaps are created by
sampling the filing stream more slowly than utilities file into it, and that
number is the only leading indicator available without a network fetch. A gap
report tells you what you already lost; the age column tells you where you are
about to lose the next one.

Run from repo root:  python3 dev/list_version_continuity.py
"""
from __future__ import annotations

import collections
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scenario_cost_models as A
import corpus

REPO = Path(__file__).resolve().parent.parent

IDENTITY_TYPES = {"urpx:RatePlan", "urpx:RatePlanModifier"}


def expiration_of(version: dict) -> str | None:
    """urpx:expirationDateTime as written, or None. Read from the version's own
    filing: a bundled copy is not authority for when a version ended."""
    home = version.get("home")
    if not home:
        return None
    doc = json.loads((REPO / home).read_text())
    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("@id") == version["id"] and "urpx:expirationDateTime" in node:
                found.append(node["urpx:expirationDateTime"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(doc.get("@graph", [doc]))
    if len(set(found)) > 1:
        raise A.Refuse(
            f"{version['id']} states {len(set(found))} different "
            f"urpx:expirationDateTime values in its own filing: {sorted(set(found))}."
        )
    return found[0] if found else None


def source_checked_on(version: dict) -> str | None:
    """The newest retrieved_on in the filing's manifest, or None."""
    home = version.get("home")
    if not home:
        return None
    manifest = (REPO / home).parent / "tariff.toml"
    if not manifest.exists():
        return None
    data = corpus.load_toml(manifest)
    dates: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if "retrieved_on" in node:
                dates.append(str(node["retrieved_on"]))
            for value in node.values():
                walk(value)

    walk(data.get("source", {}))
    return max(dates) if dates else None


def initial_effective_dates() -> dict[str, str]:
    """urpx:initialEffectiveDate of every urpx:RatePlan and urpx:RatePlanModifier
    identity, by @id. Refuses when two filings state different dates for one
    identity, because then the start of its uncaptured period is unknown."""
    stated: dict[str, set[str]] = collections.defaultdict(set)
    for path in corpus.all_filing_jsonld():
        with path.open() as fp:
            doc = json.load(fp)
        for node in A.walk(doc):
            if IDENTITY_TYPES & A.types_of(node) and "urpx:initialEffectiveDate" in node:
                value = node["urpx:initialEffectiveDate"]
                stated[node["@id"]].add(day(value.get("@value") if isinstance(value, dict) else value))
    for iri, dates in stated.items():
        if len(dates) > 1:
            raise A.Refuse(f"{iri} states {len(dates)} different urpx:initialEffectiveDate values: {sorted(dates)}.")
    return {iri: dates.pop() for iri, dates in stated.items()}


def day(stamp) -> str:
    return str(stamp)[:10]


def build(as_of: datetime.datetime | None = None) -> dict:
    """Source ages count days to the date of `as_of`, the currency instant from
    dev/currency-instant.json unless given, so the report is a function of the
    tree and not of the day it runs."""
    as_of = as_of or A.currency_instant()
    as_of_day = as_of.date()
    versions = A.collect_versions()
    A.require_nonempty_versions(versions) if hasattr(A, "require_nonempty_versions") else None
    if not versions:
        raise A.Refuse("no version nodes in the corpus; nothing to lay end to end.")

    by_plan: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for v in versions.values():
        by_plan[(v["kind"], v["plan"])].append(v)

    initial = initial_effective_dates()
    plans, gaps, overlaps, uncaptured = [], [], [], []
    for (kind, plan), members in sorted(by_plan.items()):
        members = sorted(members, key=lambda m: m["effective"])
        spans = []
        for m in members:
            checked = source_checked_on(m)
            spans.append({
                "version": m["id"],
                "from": day(m["effective"]),
                "to": day(expiration_of(m)) if expiration_of(m) else None,
                "source_checked": checked,
                "source_age_days": max(0, (as_of_day - datetime.date.fromisoformat(checked)).days)
                                   if checked else None,
            })
        for earlier, later in zip(spans, spans[1:]):
            if earlier["to"] is None:
                overlaps.append({
                    "plan": plan, "kind": kind,
                    "earlier": earlier["version"], "later": later["version"],
                    "why": "the earlier version states no urpx:expirationDateTime, "
                           "so it never ends and runs under its own successor",
                })
            elif earlier["to"] > later["from"]:
                overlaps.append({
                    "plan": plan, "kind": kind,
                    "earlier": earlier["version"], "later": later["version"],
                    "why": f"{earlier['version']} runs to {earlier['to']}, after "
                           f"{later['version']} takes effect {later['from']}",
                })
            elif earlier["to"] < later["from"]:
                gaps.append({
                    "plan": plan, "kind": kind,
                    "after": earlier["version"], "before": later["version"],
                    "from": earlier["to"], "to": later["from"],
                    "days": (datetime.date.fromisoformat(later["from"])
                             - datetime.date.fromisoformat(earlier["to"])).days,
                })
        began = initial.get(plan)
        if began and began < spans[0]["from"]:
            uncaptured.append({
                "plan": plan, "kind": kind, "from": began, "to": spans[0]["from"],
                "before": spans[0]["version"],
            })
        plans.append({"plan": plan, "kind": kind, "spans": spans})

    return {"plans": plans, "gaps": gaps, "overlaps": overlaps,
            "before_first_version": uncaptured, "as_of": as_of.isoformat()}


def render_md(d: dict) -> str:
    o = ["# Version continuity", "",
         "Auto-generated by `dev/list_version_continuity.py`. Do not edit by hand.", ""]
    gap_days = sum(g["days"] for g in d["gaps"])
    o += [f"**{len(d['gaps'])} gap(s)** totalling {gap_days} day(s), "
          f"**{len(d['overlaps'])} overlap(s)**, over {len(d['plans'])} plan identities.", ""]
    o += ["A version spans `[effective, expiration)`. A **gap** is a period no version of a plan",
          "covers: a utility changed rates and this corpus never captured the document that did it.",
          "That is backlog, not breakage. The superseded sheets stay published in the utility's",
          "historical archive, so a gap closes by fetching a document that still exists.",
          "",
          "An **overlap** is two versions of one plan in force at once. Nothing resolves that",
          "without choosing arbitrarily, and no tariff means it. That fails the gate.",
          "",
          "**Source checked** is the newest `retrieved_on` in the filing's manifest, and **Age** is the",
          f"days from it to {d['as_of']}, the currency instant in `dev/currency-instant.json`, and 0",
          "for a source retrieved after that instant.",
          "Gaps come from sampling the filing stream more slowly than utilities file into it,",
          "so that column, not the gap list, is the number that predicts the next one.", ""]

    if d["overlaps"]:
        o += ["## Overlaps", "", "| Plan | Earlier | Later | Why |", "|---|---|---|---|"]
        for x in d["overlaps"]:
            o.append(f"| `{x['plan']}` | `{x['earlier']}` | `{x['later']}` | {x['why']} |")
        o.append("")

    if d["gaps"]:
        o += ["## Gaps", "", "| Plan | From | To | Days | After | Before |", "|---|---|---|---:|---|---|"]
        for g in sorted(d["gaps"], key=lambda x: -x["days"]):
            o.append(f"| `{g['plan']}` | {g['from']} | {g['to']} | {g['days']} | "
                     f"`{g['after']}` | `{g['before']}` |")
        o.append("")

    if d["before_first_version"]:
        o += ["## Before the first captured version", "",
              "The schedule was in force from its `urpx:initialEffectiveDate` and this corpus holds no",
              "version for that period, so it has no price there. An instant before that date is",
              "before the schedule existed.", "",
              "| Plan | Kind | From | To | Before |", "|---|---|---|---|---|"]
        for u in d["before_first_version"]:
            o.append(f"| `{u['plan']}` | {u['kind']} | {u['from']} | {u['to']} | `{u['before']}` |")
        o.append("")

    o += ["## Coverage by plan", "",
          "| Plan | Version | From | To | Source checked | Age (days) |",
          "|---|---|---|---|---|---:|"]
    for p in d["plans"]:
        for s in p["spans"]:
            o.append(f"| `{p['plan']}` | `{s['version']}` | {s['from']} | "
                     f"{s['to'] or 'open'} | {s['source_checked'] or 'unrecorded'} | "
                     f"{s['source_age_days'] if s['source_age_days'] is not None else ''} |")
    return "\n".join(o) + "\n"


def render_edn(d: dict) -> str:
    def edn(x):
        if x is None: return "nil"
        if isinstance(x, bool): return "true" if x else "false"
        if isinstance(x, int): return str(x)
        if isinstance(x, str): return json.dumps(x)
        if isinstance(x, list): return "[" + " ".join(edn(i) for i in x) + "]"
        if isinstance(x, dict):
            return "{" + " ".join(f":{k.replace('_','-')} {edn(v)}" for k, v in x.items()) + "}"
        return json.dumps(str(x))
    o = [";; Auto-generated by dev/list_version_continuity.py. Do not edit by hand.",
         ";; A version spans [effective, expiration). A gap is backlog (fetch the archived",
         ";; document); an overlap is a modeling error and fails the gate. A before-first-version",
         ";; period runs from a plan's urpx:initialEffectiveDate to its earliest captured version.", ""]
    o.append(edn(d))
    return "\n".join(o) + "\n"


def main() -> int:
    try:
        d = build()
    except A.Refuse as e:
        print(f"REFUSING: {e}", file=sys.stderr)
        return 3
    (REPO / "reports" / "version-continuity.md").write_text(render_md(d))
    (REPO / "reports" / "version-continuity.edn").write_text(render_edn(d))
    gap_days = sum(g["days"] for g in d["gaps"])
    ages = [s["source_age_days"] for p in d["plans"] for s in p["spans"]
            if s["source_age_days"] is not None]
    oldest = max(ages) if ages else None
    print(f"wrote reports/version-continuity.{{md,edn}}: {len(d['gaps'])} gap(s) "
          f"over {gap_days} day(s), {len(d['overlaps'])} overlap(s), "
          f"oldest source check {oldest} days")
    if d["overlaps"]:
        for x in d["overlaps"]:
            print(f"  OVERLAP {x['plan']}: {x['why']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
