#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Remodel the three NBT export-credit filings so one export price applies per
ledger at any instant.

Each NBT filing priced its Energy Export Credit grid as thousands of Prices on
one Ledger, told apart only by a Price-level urpx:referencesTouPeriod (one of 48
hour-by-day-type periods) and a Price-level urpx:hasApplicabilityRule carrying
urpx:month and a CustomOperandNode vintage condition. A ledger is summed, these
are mutually exclusive, and clj-urpx reads neither discriminator.

The new shape, per filing:

  Seasons     twelve single-month urpx:Season nodes on the version's own
              PlanElements, since a modifier's season is read from its own
              urpx:hasSeasons.
  TOU         one urpx:TOUSchedule on the BillingModel, referencing the export
              MetricInput, with one TOUTier holding 576 TOUPeriods: month by
              day type by hour. Period n = (month-1)*48 + (24 if weekend) +
              hour + 1. Each has one TimeBracket naming its month's Season and
              the day type the old bracket carried. The old hour-23 brackets
              ended at 23:59:59, which under
              half-open containment left 23:59:59 to midnight matching no
              bracket; the new ones end at 00:00:00, which wraps midnight.
  Vintage     one urpx:ProfileAlternatives with one ProfileAlternative per
              vintage, its condition the same customConditionProperty and
              stringValue the old Price-level rules compared. Prices sit in one
              urpx:PriceSetAlternatives, one PriceSetAlternative per vintage, on
              the pattern of us/ca/sce/electricity/cca-crs/versions/2026-03-20/.
  Binding     an integer urpx:touPeriodNumber on each Price. Price-level
              urpx:referencesTouPeriod and urpx:hasApplicabilityRule are gone
              from every export Price.

Price @ids, names, unit prices and start dates are carried over untouched.

ACC PLUS. The single 2025-vintage ACC Plus Prices conditioned on "NBT
Interconnection Vintage Year = 2025", alone or ANDed with a customer-class
predicate. They move into the alternative for that vintage ("2025" for PG&E,
"NBT25" for SCE), and the vintage comparison leaves their rule. A rule left
with no condition is removed; a rule left with the customer-class comparison
keeps it as its root node. SDG&E carries no ACC Plus Price.

THE SELF-CHECK IS A SET COMPARISON, NOT A COUNT. Before writing, every export
cell is read from the old document, resolving rules and periods by @id, as
{(ledger, vintage, month, day type, hour) -> (price @id, name, unit price, start
date, PriceDefinition)}, and the same map is read back out of the new structure
by following touPeriodNumber to its period, bracket and Season, and the
enclosing PriceSetAlternative to its ProfileAlternative's condition. Any
difference aborts the file. So do: a Price @id set that changed, a cell priced
twice, two periods sharing a number, and an (month, day type, hour) instant no
bracket covers, which clj-urpx would answer silently by admitting every Price.

HOLIDAYS. Each tariff prices the Energy Export Credit by weekday against
weekend/holiday, so a weekday holiday takes that hour's weekend value. For the
filings in HOLIDAY_FILINGS a second step flags every weekday bracket
urpx:includeHolidays false and gives every weekend TOUPeriod a second bracket,
day type urpx:weekdayDays with urpx:includeNonHolidays false, same Season and
hour. sce:nbt and sdge:nbt declare no calendar: which days are holidays comes
from the base plan's urpx:HolidayCalendar. pge:nbt's base, pge:e-elec, carries
none, so the step also puts OWN_CALENDARS' calendar on pge:nbt's PlanElements.

The holiday step's self-check is also a set comparison: the Price set (@id,
name, unit price, start date, PriceDefinition, period number, vintage) and the
TOUPeriod set (@id, name, number) must be identical before and after, the new
document with the added brackets, flags and calendar removed must equal the old
one, a filing in OWN_CALENDARS must carry exactly that calendar, and
every (month, hour, day class) for the four classes weekday, weekday holiday,
weekend and weekend holiday must match exactly one bracket, a weekday holiday
landing on that hour's weekend period.

A filing already in the new shape is left alone, and one already carrying its
holiday brackets is too. Rerun against the previous revision to reproduce:

    git show <rev>:<path> > <path> && python3 dev/remodel_nbt.py

Usage:
    python3 dev/remodel_nbt.py [--dry-run]
"""
from __future__ import annotations

import argparse
import calendar
import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

FILINGS = [
    "us/ca/pge/electricity/nbt/versions/2025-10-17/rate-plan-modifier_pge_nbt_2025-10-17.jsonld",
    "us/ca/sce/electricity/nbt/versions/2025-04-23/rate-plan-modifier_sce_nbt_2025-04-23.jsonld",
    "us/ca/sdge/electricity/nbt/versions/2025-01-27/rate-plan-modifier_sdge_nbt_2025-01-27.jsonld",
]

# The condition properties the old export rules compared on. Exactly one per
# filing is expected; anything else aborts.
VINTAGE_PROPS = {"NBT Interconnection Vintage Year", "NBT Vintage Label"}
# The ACC Plus Prices compare on this one, in every filing that has them.
ACC_VINTAGE_PROP = "NBT Interconnection Vintage Year"

DAYTYPES = {"urpx:weekdayDays": "weekday", "urpx:weekendDays": "weekend"}

# The ACC Plus rule names spoke about the vintage the rule no longer states.
# Rewritten here, keyed by rule @id, so the change is visible and deterministic.
ACC_RULE_NAMES = {
    "pge:nbt-2025-10-17-ar-acc-plus-low-income-2025-vintage": (
        "Applies to low-income-eligible customers. Low-income definition per Sheet 5: "
        "(a) enrolled in CARE or FERA, OR (b) resident-owner of a single-family home in a "
        "disadvantaged community per D.18-06-027, OR (c) resident of California Indian "
        "Country per D.20-12-003. The Low-Income-NBT-Eligible predicate is "
        "consumer-side-evaluable. The 2025 interconnection vintage is the enclosing "
        "PriceSetAlternative; its Low-Income value is $0.05400/kWh (Sheet 11 Table, 4x the "
        "standard Residential adder)."),
    "sce:nbt-2025-04-23-ar-acc-plus-equity-2025-vintage": (
        "Applies to Equity Customers. Equity Customer definition per Sheet 17: (a) enrolled "
        "in CARE or FERA, OR (b) resident-owner of a single-family home in a disadvantaged "
        "community per D.18-06-027, OR (c) Residential Customer in California Indian Country "
        "per D.20-12-003. The Equity Customer predicate is consumer-side-evaluable. The NBT25 "
        "vintage is the enclosing PriceSetAlternative; its Equity value is $0.056/kWh "
        "(Sheet 7 Table, roughly 2.3x the Non-Equity adder)."),
}


class Abort(SystemExit):
    def __init__(self, path: str, msg: str):
        super().__init__(f"ABORT {path}: {msg}")


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def walk(x):
    if isinstance(x, dict):
        yield x
        for k, v in x.items():
            if k != "@context":
                yield from walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from walk(v)


def lst(x):
    return [] if x is None else (x if isinstance(x, list) else [x])


def by_id(doc) -> dict[str, dict]:
    """Each @id's fullest occurrence: nodes are stated once and referenced after."""
    out: dict[str, dict] = {}
    for n in walk(doc):
        i = n.get("@id")
        if i and (i not in out or len(n) > len(out[i])):
            out[i] = n
    return out


def res(node, idx):
    if isinstance(node, dict) and "@id" in node:
        return idx.get(node["@id"], node)
    return node


def conditions(node, idx) -> list[tuple[str, str]]:
    """(customConditionProperty, stringValue) of every comparison under a node."""
    out = []
    node = res(node, idx)
    t = node.get("@type")
    if t == "urpx:ComparisonNode":
        if node["urpx:operator"]["@id"] != "urpx:equalsOperator":
            raise ValueError(f"{node.get('@id')}: operator {node['urpx:operator']['@id']}")
        left = res(node["urpx:leftOperand"], idx)
        right = res(node["urpx:rightOperand"], idx)
        out.append((left["urpx:customConditionProperty"], right["urpx:stringValue"]))
    elif t == "urpx:BooleanOperationNode":
        if node["urpx:operator"]["@id"] != "urpx:andOperator":
            raise ValueError(f"{node.get('@id')}: operator {node['urpx:operator']['@id']}")
        for o in lst(node["urpx:operandNodes"]):
            out += conditions(o, idx)
    else:
        raise ValueError(f"{node.get('@id')}: unexpected condition node {t}")
    return out


def rule_conditions(rule, idx) -> list[tuple[str, str]]:
    rule = res(rule, idx)
    cx = res(rule.get("urpx:hasConditionExpression"), idx)
    return conditions(cx["urpx:rootNode"], idx) if cx else []


def version_of(doc) -> dict:
    return doc["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"]


def ledger_of(price, idx) -> str:
    return res(price["urpx:referencesPriceDefinition"], idx)["urpx:referencesLedger"]["@id"]


def hour_of(bracket, where) -> int:
    s, e = bracket["urpx:startTime"], bracket["urpx:endTime"]
    h = int(s[:2])
    # The old hour-23 brackets end at 23:59:59, read here as the same hour.
    if s != f"{h:02d}:00:00" or e not in (f"{(h + 1) % 24:02d}:00:00", "23:59:59" if h == 23 else None):
        raise ValueError(f"{where}: bracket {s}-{e} is not one clock hour")
    return h


def cell_value(p) -> tuple:
    return (p["@id"], p["urpx:name"], p["urpx:unitPrice"], p.get("urpx:startDate"),
            p["urpx:referencesPriceDefinition"]["@id"])


def old_cells(doc, path):
    """The old shape: Price-level period and rule, resolved by @id."""
    idx = by_id(doc)
    prices = lst(version_of(doc)["urpx:hasPrices"].get("urpx:hasPrice"))
    cells: dict[tuple, tuple] = {}
    acc: dict[str, tuple] = {}
    props = set()
    for p in prices:
        conds = rule_conditions(p["urpx:hasApplicabilityRule"], idx) if "urpx:hasApplicabilityRule" in p else []
        if "urpx:referencesTouPeriod" not in p:
            acc[p["@id"]] = (ledger_of(p, idx), cell_value(p), frozenset(conds))
            continue
        rule = res(p["urpx:hasApplicabilityRule"], idx)
        months = lst(rule.get("urpx:month"))
        vint = [c for c in conds if c[0] in VINTAGE_PROPS]
        if len(months) != 1 or len(vint) != 1 or len(conds) != 1:
            raise Abort(path, f"{p['@id']}: rule {rule.get('@id')} states months {months} "
                              f"and conditions {conds}; expected one month and one vintage")
        props.add(vint[0][0])
        period = res(p["urpx:referencesTouPeriod"], idx)
        brackets = [res(b, idx) for b in lst(period["urpx:hasTimeBracket"])]
        if len(brackets) != 1 or "urpx:appliesInSeason" in brackets[0]:
            raise Abort(path, f"{period.get('@id')}: expected one unseasoned bracket")
        b = brackets[0]
        key = (ledger_of(p, idx), vint[0][1], int(months[0][2:]),
               DAYTYPES[b["urpx:dayType"]["@id"]], hour_of(b, period["@id"]))
        if key in cells:
            raise Abort(path, f"old document prices cell {key} twice")
        cells[key] = cell_value(p)
    if len(props) != 1:
        raise Abort(path, f"export rules compare on {sorted(props)}; expected exactly one property")
    return cells, acc, props.pop(), {p["@id"] for p in prices}


def new_cells(doc, path):
    """The new shape, read the way a consumer reaches it."""
    idx = by_id(doc)
    v = version_of(doc)
    pe = v["urpx:hasPlanElements"]
    seasons = {s["@id"]: s for s in lst(pe.get("urpx:hasSeasons"))}
    periods: dict[int, dict] = {}
    covered: dict[tuple, int] = {}
    for sched in lst(pe["urpx:hasBillingModel"].get("urpx:hasTOUSchedule")):
        for tier in lst(sched["urpx:hasTOUTier"]):
            for per in lst(tier["urpx:hasTOUPeriod"]):
                n = per["urpx:touPeriodNumber"]
                if n in periods:
                    raise Abort(path, f"two TOUPeriods carry touPeriodNumber {n}")
                brackets = lst(per["urpx:hasTimeBracket"])
                if len(brackets) != 1:
                    raise Abort(path, f"{per['@id']}: expected one bracket")
                b = brackets[0]
                ms = lst(seasons[b["urpx:appliesInSeason"]["@id"]]["urpx:month"])
                if len(ms) != 1:
                    raise Abort(path, f"{per['@id']}: season names {ms}")
                k = (int(ms[0][2:]), DAYTYPES[b["urpx:dayType"]["@id"]], hour_of(b, per["@id"]))
                if k in covered:
                    raise Abort(path, f"{per['@id']} and period {covered[k]} both cover {k}")
                covered[k] = n
                periods[n] = k
    gaps = [(m, d, h) for m in range(1, 13) for d in ("weekday", "weekend") for h in range(24)
            if (m, d, h) not in covered]
    if gaps:
        raise Abort(path, f"{len(gaps)} instants match no bracket, first {gaps[0]}")

    prices_node = v["urpx:hasPrices"]
    cells: dict[tuple, tuple] = {}
    acc: dict[str, tuple] = {}
    ids = {p["@id"] for p in lst(prices_node.get("urpx:hasPrice"))}
    for p in lst(prices_node.get("urpx:hasPrice")):
        acc[p["@id"]] = (ledger_of(p, idx), cell_value(p),
                         frozenset(rule_conditions(p["urpx:hasApplicabilityRule"], idx))
                         if "urpx:hasApplicabilityRule" in p else frozenset())
    for psas in lst(prices_node.get("urpx:hasPriceSetAlternatives")):
        for psa in lst(psas["urpx:hasPriceSetAlternative"]):
            alt = idx[psa["urpx:referencesProfileAlternative"]["@id"]]
            vint = rule_conditions(alt, idx)
            if len(vint) != 1:
                raise Abort(path, f"{alt['@id']}: conditions {vint}")
            for p in lst(psa["urpx:hasPrice"]):
                ids.add(p["@id"])
                if "urpx:touPeriodNumber" not in p:
                    rc = rule_conditions(p["urpx:hasApplicabilityRule"], idx) if "urpx:hasApplicabilityRule" in p else []
                    acc[p["@id"]] = (ledger_of(p, idx), cell_value(p),
                                     frozenset(rc) | {("alternative",) + vint[0]})
                    continue
                if "urpx:referencesTouPeriod" in p or "urpx:hasApplicabilityRule" in p:
                    raise Abort(path, f"{p['@id']} still carries a Price-level discriminator")
                key = (ledger_of(p, idx), vint[0][1]) + periods[p["urpx:touPeriodNumber"]]
                if key in cells:
                    raise Abort(path, f"new document prices cell {key} twice")
                cells[key] = cell_value(p)
    return cells, acc, ids


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def period_number(month: int, daytype: str, hour: int) -> int:
    return (month - 1) * 48 + (24 if daytype == "weekend" else 0) + hour + 1


def slug(value: str) -> str:
    return value.lower().replace(" ", "-")


def comparison(cid: str, prop: str, value: str) -> dict:
    return {
        "@type": "urpx:ComparisonNode",
        "@id": cid,
        "urpx:operator": {"@id": "urpx:equalsOperator"},
        "urpx:leftOperand": {"@type": "urpx:CustomOperandNode", "@id": f"{cid}-left-operand",
                             "urpx:customConditionProperty": prop},
        "urpx:rightOperand": {"@type": "urpx:CustomOperandNode", "@id": f"{cid}-right-operand",
                              "urpx:stringValue": value},
    }


def acc_alternative(vintages: list[str], year: str, path: str) -> str:
    """The vintage value an ACC Plus 'NBT Interconnection Vintage Year = <year>'
    condition names, in the filing's own vintage vocabulary."""
    for cand in (year, f"NBT{year[2:]}"):
        if cand in vintages:
            return cand
    raise Abort(path, f"ACC Plus vintage year {year} matches none of {vintages}")


def remodel(doc, path: str) -> dict:
    old_idx = by_id(doc)
    v = version_of(doc)
    vid = v["@id"]
    pe = v["urpx:hasPlanElements"]
    bm = pe["urpx:hasBillingModel"]
    prices = lst(v["urpx:hasPrices"]["urpx:hasPrice"])

    export_mi = {l["urpx:referencesMetricInput"]["@id"] for l in lst(bm["urpx:hasLedger"])}
    if len(export_mi) != 1:
        raise Abort(path, f"ledgers reference {sorted(export_mi)}; expected one export MetricInput")
    mi = export_mi.pop()

    # Vintages in order of first appearance, and the property they compare on.
    vintages: list[str] = []
    prop = None
    cell_of: dict[str, tuple] = {}
    for p in prices:
        if "urpx:referencesTouPeriod" not in p:
            continue
        rule = res(p["urpx:hasApplicabilityRule"], old_idx)
        (prop_, val), = rule_conditions(rule, old_idx)
        prop = prop or prop_
        if val not in vintages:
            vintages.append(val)
        b = res(lst(res(p["urpx:referencesTouPeriod"], old_idx)["urpx:hasTimeBracket"])[0], old_idx)
        cell_of[p["@id"]] = (val, int(lst(rule["urpx:month"])[0][2:]),
                             DAYTYPES[b["urpx:dayType"]["@id"]], hour_of(b, p["@id"]),
                             b["urpx:dayType"]["@id"])
    daytype_iri = {c[2]: c[4] for c in cell_of.values()}

    # Seasons.
    season_id = {m: f"{vid}-season-m{m:02d}" for m in range(1, 13)}
    seasons = [{"@type": "urpx:Season", "@id": season_id[m],
                "urpx:seasonName": calendar.month_name[m], "urpx:month": [f"--{m:02d}"]}
               for m in range(1, 13)]

    # One schedule, one tier, 576 periods.
    periods = []
    for m in range(1, 13):
        for d in ("weekday", "weekend"):
            for h in range(24):
                tag = f"m{m:02d}-h{h:02d}-{d}"
                periods.append({
                    "@type": "urpx:TOUPeriod",
                    "@id": f"{vid}-tou-period-{tag}",
                    "urpx:name": f"{calendar.month_name[m]} {d} {h:02d}:00-{(h + 1) % 24:02d}:00",
                    "urpx:touPeriodNumber": period_number(m, d, h),
                    "urpx:hasTimeBracket": [{
                        "@type": "urpx:TimeBracket",
                        "@id": f"{vid}-time-bracket-{tag}",
                        "urpx:startTime": f"{h:02d}:00:00",
                        "urpx:endTime": f"{(h + 1) % 24:02d}:00:00",
                        "urpx:appliesInSeason": {"@id": season_id[m]},
                        "urpx:dayType": {"@id": daytype_iri[d]},
                    }],
                })
    schedule = {
        "@type": "urpx:TOUSchedule",
        "@id": f"{vid}-tou-export",
        "urpx:referencesMetricInput": {"@id": mi},
        "urpx:hasTOUTier": [{
            "@type": "urpx:TOUTier",
            "@id": f"{vid}-tou-tier-export-hourly",
            "urpx:tierSourceName": "Energy Export Credit hour, by month and day type",
            "urpx:touTierNumber": 1,
            "urpx:hasTOUPeriod": periods,
        }],
    }

    # Vintage dimension.
    pa_id = f"{vid}-pa-vintage"
    alt_id = {val: f"{pa_id}-{slug(val)}" for val in vintages}
    profile_alternatives = {
        "@type": "urpx:ProfileAlternatives",
        "@id": pa_id,
        "urpx:name": f"NBT export compensation vintage ({prop}), fixed for the customer's lock-in period",
        "urpx:hasAlternativeDimensions": {
            "@type": "urpx:AlternativeDimensions",
            "@id": f"{pa_id}-alternative-dimensions",
            "urpx:hasAlternativeDimension": [{
                "@type": "urpx:AlternativeDimension",
                "@id": f"{vid}-ad-vintage",
                "urpx:dimensionDisplayName": prop,
                "urpx:customDimensionProperty": prop,
                "urpx:hasPossibleValues": {"@list": list(vintages)},
            }],
        },
        "urpx:hasProfileAlternative": [{
            "@type": "urpx:ProfileAlternative",
            "@id": alt_id[val],
            "urpx:name": f"{prop} {val}",
            "urpx:hasConditionExpression": {
                "@type": "urpx:ConditionExpression",
                "@id": f"{vid}-cx-pa-vintage-{slug(val)}",
                "urpx:rootNode": comparison(f"{vid}-cn-pa-vintage-{slug(val)}", prop, val),
            },
        } for val in vintages],
    }

    # Prices into their alternative.
    by_vintage: dict[str, list] = {val: [] for val in vintages}
    for p in prices:
        q = copy.deepcopy(p)
        if p["@id"] in cell_of:
            val, m, d, h, _ = cell_of[p["@id"]]
            del q["urpx:referencesTouPeriod"], q["urpx:hasApplicabilityRule"]
            q["urpx:touPeriodNumber"] = period_number(m, d, h)
            by_vintage[val].append(q)
            continue
        rule = res(p["urpx:hasApplicabilityRule"], old_idx)
        conds = rule_conditions(rule, old_idx)
        years = [c[1] for c in conds if c[0] == ACC_VINTAGE_PROP]
        if len(years) != 1:
            raise Abort(path, f"{p['@id']} is no export cell and states no single vintage year: {conds}")
        rest = [c for c in conds if c[0] != ACC_VINTAGE_PROP]
        if not rest:
            del q["urpx:hasApplicabilityRule"]
        else:
            if len(rest) != 1:
                raise Abort(path, f"{p['@id']}: more than one non-vintage condition {rest}")
            cx = rule["urpx:hasConditionExpression"]
            root = cx["urpx:rootNode"]
            keep = [o for o in lst(root.get("urpx:operandNodes"))
                    if rule_conditions({"urpx:hasConditionExpression": {"urpx:rootNode": o}}, old_idx) == rest]
            if root.get("@type") != "urpx:BooleanOperationNode" or len(keep) != 1:
                raise Abort(path, f"{rule['@id']}: cannot isolate the non-vintage comparison")
            new_rule = copy.deepcopy(rule)
            new_rule["urpx:name"] = ACC_RULE_NAMES[rule["@id"]]
            new_rule["urpx:hasConditionExpression"]["urpx:rootNode"] = copy.deepcopy(keep[0])
            q["urpx:hasApplicabilityRule"] = new_rule
        by_vintage[acc_alternative(vintages, years[0], path)].append(q)

    psas = {
        "@type": "urpx:PriceSetAlternatives",
        "@id": f"{vid}-psa-export-by-vintage",
        "urpx:name": f"Export compensation, varies by NBT vintage ({prop})",
        "urpx:referencesProfileAlternatives": {"@id": pa_id},
        "urpx:hasPriceSetAlternative": [{
            "@type": "urpx:PriceSetAlternative",
            "@id": f"{vid}-psa-export-{slug(val)}",
            "urpx:referencesProfileAlternative": {"@id": alt_id[val]},
            "urpx:hasPrice": by_vintage[val],
        } for val in vintages],
    }

    new = copy.deepcopy(doc)
    nv = version_of(new)
    npe = nv["urpx:hasPlanElements"]
    rebuilt = {}
    for k, val in npe.items():
        rebuilt[k] = val
        if k == "urpx:hasMetricInput":
            rebuilt["urpx:hasSeasons"] = seasons
            rebuilt["urpx:hasProfileAlternatives"] = profile_alternatives
    npe.clear()
    npe.update(rebuilt)
    npe["urpx:hasBillingModel"]["urpx:hasTOUSchedule"] = [schedule]
    np_ = nv["urpx:hasPrices"]
    del np_["urpx:hasPrice"]
    np_["urpx:hasPriceSetAlternatives"] = [psas]
    return new


def self_check(old, new, path: str) -> str:
    o_cells, o_acc, prop, o_ids = old_cells(old, path)
    n_cells, n_acc, n_ids = new_cells(new, path)
    if o_ids != n_ids:
        raise Abort(path, f"Price @ids changed: lost {sorted(o_ids - n_ids)[:3]}, "
                          f"gained {sorted(n_ids - o_ids)[:3]}")
    if o_cells != n_cells:
        diff = sorted(set(o_cells.items()) ^ set(n_cells.items()))
        raise Abort(path, f"{len(diff)} export cells differ, first {diff[0]}")
    vintages = sorted({k[1] for k in o_cells})
    for pid, (led, val, conds) in o_acc.items():
        nled, nval, nconds = n_acc[pid]
        year = [c[1] for c in conds if c[0] == ACC_VINTAGE_PROP][0]
        expect = (conds - {(ACC_VINTAGE_PROP, year)}) | {
            ("alternative", prop, acc_alternative(vintages, year, path))}
        if (led, val, expect) != (nled, nval, nconds):
            raise Abort(path, f"{pid}: ACC Plus price moved incorrectly: {conds} -> {nconds}")
    if set(o_acc) != set(n_acc):
        raise Abort(path, "ACC Plus Price set changed")
    ledgers = sorted({k[0] for k in o_cells})
    return (f"{len(o_cells)} export cells identical over {len(ledgers)} ledgers and "
            f"{len(vintages)} vintages ({', '.join(vintages)}); {len(o_acc)} ACC Plus "
            f"Prices moved into their vintage; {len(o_ids)} Price @ids unchanged")


# ---------------------------------------------------------------------------
# Holidays
# ---------------------------------------------------------------------------

# Filings whose weekday holidays price at the weekend value.
HOLIDAY_FILINGS = {
    "us/ca/pge/electricity/nbt/versions/2025-10-17/rate-plan-modifier_pge_nbt_2025-10-17.jsonld",
    "us/ca/sce/electricity/nbt/versions/2025-04-23/rate-plan-modifier_sce_nbt_2025-04-23.jsonld",
    "us/ca/sdge/electricity/nbt/versions/2025-01-27/rate-plan-modifier_sdge_nbt_2025-01-27.jsonld",
}
HOLIDAY_FLAGS = ("urpx:includeHolidays", "urpx:includeNonHolidays")
WEEKDAY, WEEKEND = "urpx:weekdayDays", "urpx:weekendDays"
HOLIDAY_SUFFIX = "-weekday-holiday"

# A calendar the step puts on the modifier itself, for a filing whose base
# carries none. Schedule NBT names no holidays; "weekends/holidays" (Sheet 6,
# Sheet 10 step 3) takes PG&E's TOU definition, stated identically in E-TOU-D,
# E-19, E-20, A-10, EV and S: "New Year's Day, President's Day, Memorial Day,
# Independence Day, Labor Day, Veterans Day, Thanksgiving Day, and Christmas
# Day. The dates will be those on which the holidays are legally observed."
# "Legally observed" is California Government Code section 6701: a Sunday
# January 1, July 4, November 11 or December 25 moves to Monday, and of the
# Saturday ones only November 11 moves, to Friday. Veterans Day therefore
# carries urpx:nearestWeekdayObservance and the other three
# urpx:actualDateObservance, which leaves their Sunday-to-Monday shift
# unmodeled (a tariff.toml deferral). Names, rules and observance are
# pge:holidays-e-tou-d's.
_ACTUAL, _NEAREST = "urpx:actualDateObservance", "urpx:nearestWeekdayObservance"
_PGE_HOLIDAYS = (
    ("new-years-day", "New Year's Day", "January 1 (legally observed)", _ACTUAL),
    ("presidents-day", "President's Day", "Third Monday in February", None),
    ("memorial-day", "Memorial Day", "Last Monday in May", None),
    ("independence-day", "Independence Day", "July 4 (legally observed)", _ACTUAL),
    ("labor-day", "Labor Day", "First Monday in September", None),
    ("veterans-day", "Veterans Day", "November 11 (legally observed)", _NEAREST),
    ("thanksgiving", "Thanksgiving Day", "Fourth Thursday in November", None),
    ("christmas", "Christmas Day", "December 25 (legally observed)", _ACTUAL),
)


def _calendar(version_id: str, holidays) -> dict:
    return {
        "@type": "urpx:HolidayCalendar",
        "@id": f"{version_id}-holidays",
        "urpx:hasHoliday": [
            {"@type": "urpx:Holiday", "@id": f"{version_id}-holiday-{slug_}",
             "urpx:holidayName": name, "urpx:holidayRule": rule,
             **({"urpx:observanceRule": {"@id": obs}} if obs else {})}
            for slug_, name, rule, obs in holidays],
    }


OWN_CALENDARS = {
    "us/ca/pge/electricity/nbt/versions/2025-10-17/rate-plan-modifier_pge_nbt_2025-10-17.jsonld":
        _calendar("pge:nbt-2025-10-17", _PGE_HOLIDAYS),
}


def export_periods(doc) -> list[dict]:
    pe = version_of(doc)["urpx:hasPlanElements"]
    return [per for sched in lst(pe["urpx:hasBillingModel"].get("urpx:hasTOUSchedule"))
            for tier in lst(sched["urpx:hasTOUTier"]) for per in lst(tier["urpx:hasTOUPeriod"])]


def is_holiday_bracket(b: dict) -> bool:
    return b.get("urpx:includeNonHolidays") is False


def has_holidays(doc) -> bool:
    if "urpx:hasHolidayCalendar" in version_of(doc)["urpx:hasPlanElements"]:
        return True
    return any(k in b for per in export_periods(doc) for b in lst(per["urpx:hasTimeBracket"])
               for k in HOLIDAY_FLAGS)


def strip_holidays(doc) -> dict:
    """The document with the holiday step undone."""
    out = copy.deepcopy(doc)
    version_of(out)["urpx:hasPlanElements"].pop("urpx:hasHolidayCalendar", None)
    for per in export_periods(out):
        per["urpx:hasTimeBracket"] = [
            {k: v for k, v in b.items() if k not in HOLIDAY_FLAGS}
            for b in lst(per["urpx:hasTimeBracket"]) if not is_holiday_bracket(b)]
    return out


def add_holidays(doc, path: str) -> dict:
    new = copy.deepcopy(doc)
    if path in OWN_CALENDARS:
        version_of(new)["urpx:hasPlanElements"]["urpx:hasHolidayCalendar"] = copy.deepcopy(OWN_CALENDARS[path])
    for per in export_periods(new):
        brackets = lst(per["urpx:hasTimeBracket"])
        if len(brackets) != 1:
            raise Abort(path, f"{per['@id']}: expected one bracket before the holiday step")
        b = brackets[0]
        day = b["urpx:dayType"]["@id"]
        if day == WEEKDAY:
            b["urpx:includeHolidays"] = False
            b["urpx:includeNonHolidays"] = True
        elif day == WEEKEND:
            if not b["@id"].endswith("-weekend"):
                raise Abort(path, f"{b['@id']}: weekend bracket @id does not end -weekend")
            brackets.append({
                "@type": "urpx:TimeBracket",
                "@id": b["@id"][: -len("-weekend")] + HOLIDAY_SUFFIX,
                "urpx:startTime": b["urpx:startTime"],
                "urpx:endTime": b["urpx:endTime"],
                "urpx:appliesInSeason": copy.deepcopy(b["urpx:appliesInSeason"]),
                "urpx:dayType": {"@id": WEEKDAY},
                "urpx:includeHolidays": True,
                "urpx:includeNonHolidays": False,
            })
            per["urpx:hasTimeBracket"] = brackets
        else:
            raise Abort(path, f"{b['@id']}: day type {day}")
    return new


def price_set(doc) -> set:
    idx = by_id(doc)
    out = set()
    for psas in lst(version_of(doc)["urpx:hasPrices"].get("urpx:hasPriceSetAlternatives")):
        for psa in lst(psas["urpx:hasPriceSetAlternative"]):
            alt = psa["urpx:referencesProfileAlternative"]["@id"]
            for p in lst(psa["urpx:hasPrice"]):
                out.add(cell_value(p) + (p.get("urpx:touPeriodNumber"), alt, ledger_of(p, idx)))
    return out


# The four day classes, as (day type, holiday?).
DAY_CLASSES = ((WEEKDAY, False), (WEEKDAY, True), (WEEKEND, False), (WEEKEND, True))


def bracket_matches(b: dict, day: str, holiday: bool) -> bool:
    flag = "urpx:includeHolidays" if holiday else "urpx:includeNonHolidays"
    return b["urpx:dayType"]["@id"] in (day, "urpx:allDays") and b.get(flag, True) is not False


def holiday_coverage(doc, path: str) -> int:
    """Every (month, hour, day class) matches exactly one bracket, on the period
    the tariff prices: the weekday period for a non-holiday weekday, else the
    weekend period. Returns the number of instants checked."""
    seasons = {s["@id"]: s for s in lst(version_of(doc)["urpx:hasPlanElements"].get("urpx:hasSeasons"))}
    hits: dict[tuple, list[int]] = {}
    for per in export_periods(doc):
        for b in lst(per["urpx:hasTimeBracket"]):
            (m,) = lst(seasons[b["urpx:appliesInSeason"]["@id"]]["urpx:month"])
            h = hour_of(b, per["@id"])
            for day, hol in DAY_CLASSES:
                if bracket_matches(b, day, hol):
                    hits.setdefault((int(m[2:]), h, day, hol), []).append(per["urpx:touPeriodNumber"])
    n = 0
    for m in range(1, 13):
        for h in range(24):
            for day, hol in DAY_CLASSES:
                want = period_number(m, "weekday" if (day, hol) == (WEEKDAY, False) else "weekend", h)
                got = hits.get((m, h, day, hol), [])
                if got != [want]:
                    raise Abort(path, f"month {m} hour {h} {day} holiday={hol} matches periods "
                                      f"{got}, expected [{want}]")
                n += 1
    return n


def holiday_self_check(old, new, path: str) -> str:
    if has_holidays(old):
        raise Abort(path, "the holiday step's input already carries holiday flags or a calendar")
    if strip_holidays(new) != old:
        raise Abort(path, "removing the added brackets, flags and calendar does not restore the input")
    if version_of(new)["urpx:hasPlanElements"].get("urpx:hasHolidayCalendar") != OWN_CALENDARS.get(path):
        raise Abort(path, "the PlanElements calendar is not the one OWN_CALENDARS declares")
    if price_set(old) != price_set(new):
        raise Abort(path, "the Price set changed")
    pset = lambda d: {(p["@id"], p["urpx:name"], p["urpx:touPeriodNumber"]) for p in export_periods(d)}
    if pset(old) != pset(new):
        raise Abort(path, "the TOUPeriod set changed")
    added = sum(len(lst(p["urpx:hasTimeBracket"])) for p in export_periods(new)) - len(export_periods(old))
    flagged = sum(1 for p in export_periods(new) for b in lst(p["urpx:hasTimeBracket"])
                  if b.get("urpx:includeHolidays") is False)
    n = holiday_coverage(new, path)
    cal = OWN_CALENDARS.get(path)
    return (f"{len(price_set(new))} Prices and {len(pset(new))} TOUPeriods identical; "
            f"{added} weekday-holiday brackets added, {flagged} weekday brackets flagged; "
            + (f"calendar {cal['@id']} with {len(cal['urpx:hasHoliday'])} Holidays added; " if cal else "")
            + f"{n} (month, hour, day class) instants each match exactly one bracket")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    for rel in FILINGS:
        path = REPO / rel
        text = path.read_text()
        doc = json.loads(text)
        prices = version_of(doc)["urpx:hasPrices"]
        if "urpx:hasPriceSetAlternatives" in prices and not prices.get("urpx:hasPrice"):
            n_cells, _acc, _ids = new_cells(strip_holidays(doc), rel)
            print(f"{rel}: already remodeled ({len(n_cells)} export cells read back cleanly)")
            new = doc
        else:
            new = remodel(doc, rel)
            print(f"{rel}: {self_check(doc, new, rel)}")
        if rel in HOLIDAY_FILINGS:
            if has_holidays(new):
                if version_of(new)["urpx:hasPlanElements"].get("urpx:hasHolidayCalendar") != OWN_CALENDARS.get(rel):
                    raise Abort(rel, "the PlanElements calendar is not the one OWN_CALENDARS declares")
                print(f"{rel}: holidays already modeled "
                      f"({holiday_coverage(new, rel)} instants each match exactly one bracket)")
            else:
                before, new = new, add_holidays(new, rel)
                print(f"{rel}: {holiday_self_check(before, new, rel)}")
        if not args.dry_run and new is not doc:
            path.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
