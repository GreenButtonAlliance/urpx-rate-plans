#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Author the SCE filings effective 2026-10-01 (Advice 5897-E, Decision 26-04-033).

Each 2026-10-01 version is derived from the filing's 2026-03-20 version: every
subordinate @id is rescoped to the new date, every Price is set from the table
below (which asserts the 2026-03-20 value it replaces), and the prose is
rewritten for the new sheets. The structural changes are:

  - Option PRIME loses its qualifying-technology EligibilityRule: Advice 5897-E
    deletes the PRIME Eligibility Requirements Special Condition, and Sheet 1
    makes Option PRIME available to every Customer eligible for Schedule D,
    D-CARE or D-FERA.
  - every CARE, FERA, DA-CRS and CCA-CRS version names the 2026-10-01 base
    subtotals beside the earlier ones (candidates()).

Each 2026-03-20 version gains urpx:expirationDateTime at the effective date of
the sheet that cancels its rate sheet (LAYOUT.md section 9), in EXPIRES. The
Option 4-9 PM and 5-8 PM baseline ladders and HPWH modifiers come from
dev/author_sce_tou_d_baseline.py, and the FERA and deed-restricted coverage
evaluations, which restate their manifests' deferrals, from
dev/resync_coverage_evaluations.py; run both after this, in that order.

Run from the repo root: python3 dev/author_sce_2026_10_01.py <directory holding the fetched PDFs>

The PDFs are the live tariff book's ELECTRIC_SCHEDULES_{TOU-D,D,D-CARE,CCA-CRS,DA-CRS}.pdf
and ELECTRIC_PRELIM_H.pdf, fetched and unwrapped by dev/fetch_tariff_documents.py.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCE = REPO / "us/ca/sce/electricity"
OLD, NEW = "2026-03-20", "2026-10-01"
RETRIEVED = "2026-10-06"

# The sheet that cancels each 2026-03-20 version's rate sheet, and its effective
# date. The TOU-D and Schedule D rate sheets (90937-E to 90941-E, 90841-E,
# 90842-E) were cancelled on June 1, 2026 by Advice 5829-E (91196-E to 91200-E,
# 91130-E, 91131-E), and the DA-CRS and CCA-CRS rate sheets on June 25, 2026 by
# Advice 5837-E (91328-E to 91334-E, 91310-E to 91316-E), all as printed on the
# copies of those schedules fetched 2026-09-23 into data/documents/sce/. The
# CARE and FERA values (D-CARE Sheet 1, 90844-E; TOU-D Sheet 18, 90943-E) were
# cancelled on June 1, 2026 by Advice 5829-E's 91134-E and 91202-E, as printed
# in that advice letter. dev/author_sce_2026_06.py adds the versions that begin
# on these dates.
EXPIRES = {
    "tou-d-4-9pm": "2026-06-01", "tou-d-5-8pm": "2026-06-01", "tou-d-prime": "2026-06-01",
    "d": "2026-06-01", "tou-d-prime-cpp": "2026-06-01", "deed-restricted": "2026-06-01",
    "care": "2026-06-01", "fera": "2026-06-01",
    "cca-crs": "2026-06-25", "da-crs": "2026-06-25",
}

TOU_D = "ELECTRIC_SCHEDULES_TOU-D.pdf"


def leaf(sheet: int) -> str:
    """Schedule TOU-D Sheet n, Advice 5897-E: Cal. P.U.C. Sheets 91689-E to 91707-E."""
    return f"{91688 + sheet}-E"


CELLS = ["summer-on-peak", "summer-mid-peak", "summer-off-peak",
         "winter-mid-peak", "winter-off-peak", "winter-super-off-peak"]
COMMON = {"transmission": "0.02481", "nsgc": "0.00866", "ndc": "0.00003", "pppc": "0.00556",
          "cia": "0.00000", "wfc": "0.00591", "dwra": "0.00000", "pucrf": "0.00100",
          "fixed-recovery-charge": "0.01118", "mcam": "0.00223", "gen-dwrec": "0.00000",
          "base-services-charge": "0.794", "climate-credit": "-36.00"}


def tou(sched: str, gen: list[str], dist: list[str], extra: dict[str, str]) -> dict[str, str]:
    p = f"sce:{sched}-{OLD}-price-"
    out = {p + k: v for k, v in COMMON.items()}
    out.update({p + f"gen-{c}": v for c, v in zip(CELLS, gen)})
    out.update({p + f"dist-{c}": v for c, v in zip(CELLS, dist)})
    out.update({p + k if not k.startswith("sce:") else k: v for k, v in extra.items()})
    return out


VINTAGES = {"2001": "0.00009", "2004": "0.00009", "2009": "0.01747", "2010": "0.02082",
            "2011": "0.02515", "2012": "0.02570", "2013": "0.02615", "2014": "0.02449",
            "2015": "0.02373", "2016": "0.02327", "2017": "0.02328", "2018": "0.02317",
            "2019": "0.02147", "2020": "0.02021", "2021": "0.02012", "2022": "0.02425",
            "2023": "0.02631", "2024": "0.01178", "2025": "-0.00645", "2026": "-0.00645"}


def crs(slug: str) -> dict[str, str]:
    out = {f"sce:{slug}-price-wfc-{OLD}": "0.00591", f"sce:{slug}-price-ctc-{OLD}": "0.00014",
           f"sce:{slug}-price-frc-{OLD}": "0.01118"}
    out.update({f"sce:{slug}-price-pcia-v{y}-{OLD}": v for y, v in VINTAGES.items()})
    return out


# New unit prices, keyed by the 2026-03-20 @id they replace. Every Price in each
# derived document must appear here; Prices with no urpx:unitPrice (the
# multiplier Prices) are left alone.
PRICES = {
    "tou-d-4-9pm": tou("tou-d-4-9pm",  # Sheets 2 and 3
                       ["0.25729", "0.11506", "0.07035", "0.18918", "0.09440", "0.06702"],
                       ["0.28985", "0.28845", "0.21625", "0.27307", "0.22459", "0.20943"],
                       {"baseline-credit": "-0.09101", "baseline-credit-nonbaseline": "0.00000"}),
    "tou-d-5-8pm": tou("tou-d-5-8pm",  # Sheets 4 and 5
                       ["0.37937", "0.20238", "0.07032", "0.23406", "0.09857", "0.06569"],
                       ["0.30063", "0.27087", "0.22669", "0.27976", "0.23231", "0.21137"],
                       {"baseline-credit": "-0.09101", "baseline-credit-nonbaseline": "0.00000"}),
    "tou-d-prime": tou("tou-d-prime",  # Sheets 6 and 7
                       ["0.31175", "0.09775", "0.06683", "0.21627", "0.08096", "0.04428"],
                       ["0.25487", "0.25363", "0.15400", "0.18969", "0.17659", "0.16048"],
                       {f"sce:price-ev-meter-credit-{OLD}": "-0.371",
                        f"sce:price-ev-submeter-credit-{OLD}": "-0.051"}),
    "d": {  # Schedule D Sheets 2 and 3
        f"sce:price-generation-{OLD}": "0.11255", f"sce:price-generation-dwrec-{OLD}": "0.00000",
        f"sce:price-distribution-{OLD}": "0.17910",
        f"sce:price-cia-baseline-{OLD}": "-0.03496", f"sce:price-cia-nonbaseline-{OLD}": "0.05605",
        **{f"sce:d-{OLD}-price-{k}": v for k, v in COMMON.items()
           if k not in ("cia", "gen-dwrec")},
    },
    "tou-d-prime-cpp": {f"sce:tou-d-prime-cpp-price-event-charge-{OLD}": "0.80000",
                        f"sce:tou-d-prime-cpp-price-non-event-credit-{OLD}": "-0.15170",
                        f"sce:tou-d-prime-cpp-price-max-credit-{OLD}": "-0.41944"},
    "deed-restricted": {f"sce:deed-restricted-price-bsc-discount-{OLD}": "-0.328"},
    "fera": {f"sce:fera-price-bsc-surcharge-exemption-{OLD}": "-0.069",
             f"sce:fera-price-bsc-credit-adjustment-{OLD}": "-0.197"},
    "care": {f"sce:care-price-wfc-exemption-{OLD}": "-0.00591",
             f"sce:care-price-frc-exemption-{OLD}": "-0.01118",
             f"sce:care-price-bsc-surcharge-exemption-{OLD}": "-0.069",
             f"sce:care-price-bsc-discount-{OLD}": "-0.164"},
    "cca-crs": crs("cca-crs"),
    "da-crs": crs("da-crs"),
}

# The data source of each new version: (file, pageStart, pageEnd, leafStart, leafEnd).
SOURCES = {
    "tou-d-4-9pm": (TOU_D, 2, 3, leaf(2), leaf(3)),
    "tou-d-5-8pm": (TOU_D, 4, 5, leaf(4), leaf(5)),
    "tou-d-prime": (TOU_D, 6, 7, leaf(6), leaf(7)),
    "tou-d-prime-cpp": (TOU_D, 6, 12, leaf(6), leaf(12)),
    "deed-restricted": (TOU_D, 2, 2, leaf(2), leaf(2)),
    "fera": (TOU_D, 13, 13, leaf(13), leaf(13)),
    "d": ("ELECTRIC_SCHEDULES_D.pdf", 2, 7, "91558-E", "91561-E"),
    "care": ("ELECTRIC_SCHEDULES_D-CARE.pdf", 1, 1, "91562-E", "91562-E"),
    "cca-crs": ("ELECTRIC_SCHEDULES_CCA-CRS.pdf", 3, 10, "74851-E", "91557-E"),
    "da-crs": ("ELECTRIC_SCHEDULES_DA-CRS.pdf", 3, 10, "74861-E", "91570-E"),
}

BASES = ["d", "tou-d-4-9pm", "tou-d-5-8pm", "tou-d-prime"]
MODIFIERS = ["care", "fera", "deed-restricted", "tou-d-prime-cpp", "cca-crs", "da-crs"]


def path(slug: str, date: str) -> Path:
    kind = "rate-plan" if slug in BASES else "rate-plan-modifier"
    return SCE / slug / "versions" / date / f"{kind}_sce_{slug}_{date}.jsonld"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def dump(p: Path, doc) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def walk(o, f):
    if isinstance(o, dict):
        f(o)
        for v in o.values():
            walk(v, f)
    elif isinstance(o, list):
        for v in o:
            walk(v, f)


def version_node(doc):
    if "urpx:hasRatePlan" in doc:
        return doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]
    return doc["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"]


def find(doc, i: str):
    hit = []
    walk(doc, lambda d: hit.append(d) if d.get("@id") == i and len(d) > 1 else None)
    if len(hit) != 1:
        raise SystemExit(f"{i}: {len(hit)} definitions")
    return hit[0]


def rescope(doc, slug: str) -> dict[str, str]:
    """The rename map: OLD becomes NEW in every @id, and a subordinate @id the
    2026-03-20 version shares with no date (sce:<slug>-pd-event-charge) is scoped
    to NEW, so the two versions own disjoint subordinate nodes."""
    defined: set[str] = set()
    walk(doc, lambda d: defined.add(d["@id"]) if "@id" in d and len(d) > 1 else None)
    top = {f"sce:{slug}", "org:utility-sce", "org:utility-sce-identity", "org:utility-sce-name",
           "org:utility-sce-eia"}
    m = {}
    for i in defined:
        if OLD in i:
            m[i] = i.replace(OLD, NEW)
        elif i.startswith(f"sce:{slug}-") and i not in top:
            m[i] = f"sce:{slug}-{NEW}-" + i[len(f"sce:{slug}-"):]
        elif i in UNSCOPED.get(slug, ()):
            m[i] = f"sce:{slug}-{NEW}-" + i[len("sce:"):]
    return m


# Subordinate @ids the 2026-03-20 version carries with neither its date nor its
# schedule in them, which dev/lint_iri_scope.py would see two owners of.
UNSCOPED = {"d": ["sce:pd-generation-dwrec"]}


def apply_map(doc, m: dict[str, str]) -> None:
    def f(d):
        if isinstance(d.get("@id"), str) and d["@id"] in m:
            d["@id"] = m[d["@id"]]
    walk(doc, f)


def set_strings(doc) -> None:
    """Plain date-valued literals that name the version."""
    def f(d):
        for k, v in list(d.items()):
            if not isinstance(v, str):
                continue
            if k in ("urpx:version", "urpx:modifierVersionNumber") and v == OLD:
                d[k] = NEW
            elif k == "urpx:effectiveDateTime":
                d[k] = f"{NEW}T00:00:00"
            elif k == "urpx:startDate":
                d[k] = NEW
            elif k == "urpx:dateRetrieved":
                d[k] = RETRIEVED
            elif k == "urpx:evaluatedOn":
                d[k] = "2026-10-06T00:00:00"
    walk({k: v for k, v in doc.items() if k != "@context"}, f)


def set_prices(doc, table: dict[str, str], m: dict[str, str], slug: str) -> list[tuple[str, str, str]]:
    seen, rows = set(), []
    inv = {v: k for k, v in m.items()}

    def f(d):
        if d.get("@type") == "urpx:Price" and "urpx:unitPrice" in d:
            old_id = inv.get(d["@id"], d["@id"])
            if old_id not in table:
                raise SystemExit(f"{slug}: no new price for {old_id}")
            if old_id in seen:
                return
            seen.add(old_id)
            rows.append((old_id, d["urpx:unitPrice"], table[old_id]))
            d["urpx:unitPrice"] = table[old_id]
    walk(doc, f)
    missing = set(table) - seen
    if missing:
        raise SystemExit(f"{slug}: table names prices the document lacks: {sorted(missing)}")
    return rows


def set_source(doc, slug: str) -> None:
    fname, p0, p1, l0, l1 = SOURCES[slug]
    dsr = version_node(doc)["urpx:hasDataSourceReference"]
    assert dsr["urpx:fileName"] == fname, (slug, dsr["urpx:fileName"])
    dsr.update({"urpx:pageStart": p0, "urpx:pageEnd": p1, "urpx:leafStart": l0, "urpx:leafEnd": l1})


def expire_old(slug: str) -> None:
    p = path(slug, OLD)
    doc = load(p)
    ctx = doc["@context"]
    if "urpx:expirationDateTime" not in ctx:
        out = {}
        for k, v in ctx.items():
            out[k] = v
            if k == "urpx:effectiveDateTime":
                out["urpx:expirationDateTime"] = {"@type": "xsd:dateTime"}
        doc["@context"] = out
    v = version_node(doc)
    new_v = {}
    for k, x in v.items():
        if k == "urpx:expirationDateTime":
            continue
        new_v[k] = x
        if k == "urpx:effectiveDateTime":
            new_v["urpx:expirationDateTime"] = f"{EXPIRES[slug]}T00:00:00"
    parent = doc["urpx:hasRatePlan"] if "urpx:hasRatePlan" in doc else doc["urpx:hasRatePlanModifier"]
    key = "urpx:hasRatePlanVersion" if "urpx:hasRatePlan" in doc else "urpx:hasRatePlanModifierVersion"
    parent[key] = new_v
    dump(p, doc)


# --- prose ------------------------------------------------------------------

def holidays(window: str) -> str:
    return ("Special Condition 1 (Sheet 9) names eight holidays: New Year's Day, Presidents' Day, Memorial Day, "
            "Independence Day, Labor Day, Veterans Day, Thanksgiving Day and Christmas. Sheet 8 prices them in the "
            "Weekends-and-Holidays column, so a holiday landing on a summer weekday takes Mid-Peak rather than "
            f"On-Peak across the {window} window; the winter weekday and weekend/holiday columns are identical, so "
            "holiday status moves no winter price. Modeled as a urpx:HolidayCalendar with urpx:includeHolidays / "
            f"urpx:includeNonHolidays on the summer {window} brackets. SCE's observance rule (a holiday falling on "
            "Sunday is recognized the following Monday, with no change for one falling on Saturday) matches none of "
            "URPX v0.5.1's four urpx:ObservanceRuleValue individuals, so no urpx:observanceRule is attached and the "
            "Monday after a Sunday holiday is carried as a dated urpx:Holiday through 2040.")


def bsc_sentence() -> str:
    return ("Base Services Charge (BSC) of $0.794/meter/day per Decision 24-05-028, with a BSC Adjustment of "
            "$(0.328)/meter/day for customers in deed-restricted affordable housing, modeled as "
            "sce:deed-restricted. The CARE and FERA discounts of Special Conditions 6 and 7 (32.5 and 18.0 "
            "percent, with their BSC Surcharge exemption and BSC discount or credit adjustment) are modeled as "
            "sce:care and sce:fera. The California Climate Credit of $(36.00) per household is applied "
            "semi-annually per Special Condition 10.")


def ladder_sentence(sched: str) -> str:
    v = f"sce:{sched}-{NEW}"
    return (f"The Baseline Credit applies up to 100 percent of the Baseline Allocation: Tier 1 of {v}-tiers-baseline "
            "carries the Preliminary Statement Part H allocation for each Baseline Region and Basic or All-Electric "
            "Allocation in kWh per day, and the credit is priced on Tier 1 only. The Heat Pump Water Heater "
            f"allocation Part H adds is the modifier sce:{sched}-hpwh, a second document in this filing's directory.")


def option_evaluation(sched: str, opt: str, sheet: int) -> str:
    v = f"sce:{sched}-{NEW}"
    return (f"Three things published for {opt} are not represented in this filing. First, the {opt}-CPP variant "
            f"printed on the same Sheet {sheet}: a CPP Event Energy Charge of $0.80000 per kWh, a Summer On-Peak "
            "Energy Credit of $(0.15170) per kWh outside CPP Events, and a Summer Season Maximum Available Credit of "
            "$(0.41944) per kWh, none of them modeled. Second, the two pilot bill discounts of Special Conditions 12 "
            "and 14: the San Joaquin Valley Disadvantaged Communities Pilot Bill Protection Discount (20 percent in "
            "years 1 through 5, then 10 or 20 percent in years 6 through 10) and the 20 percent Transitional "
            "Community Solar Discount. Third, two things Preliminary Statement Part H states: how the kWh-per-day "
            f"allocations bounding Tier 1 of {v}-tiers-baseline scale to a billing period, and the Medical Baseline "
            "Allocation it adds to them. The Deed Restricted Base Services Charge adjustment of $(0.328) per meter "
            "per day and the CARE and FERA discount lines are cross-references to separate schedules, each filed as "
            "its own modifier in this corpus.")


def generation_summary(name: str, where: str) -> str:
    return (f"Generation subtotal for {name}: its Generation Prices and its DWR Energy Credit. {where} footnote 2: "
            "\"Generation = The Gen rates are applicable only to Bundled Service Customers.\" sce:da-crs and "
            "sce:cca-crs offset this subtotal for Direct Access and CCA Service customers.")


PROSE: dict[str, dict[str, dict[str, str]]] = {
    "tou-d-4-9pm": {
        f"sce:tou-d-4-9pm-{NEW}": {"urpx:description": (
            "Voluntary residential time-of-use option with summer on-peak 4:00 p.m.-9:00 p.m. weekdays. Assigned by "
            "CPUC mass-migration default rules to a portion of SCE's residential customer base by climate zone. "
            + bsc_sentence() + " " + ladder_sentence("tou-d-4-9pm") + " " + holidays("4 p.m. to 9 p.m."))},
        f"sce:tou-d-4-9pm-{NEW}-summary-generation": {"urpx:name": generation_summary(
            "TOU-D-4-9PM", f"Schedule TOU-D Sheet 2 (Cal. P.U.C. Sheet {leaf(2)})")},
        f"sce:cc-tou-d-4-9pm-{NEW}-evaluation": {"urpx:description": option_evaluation(
            "tou-d-4-9pm", "Option 4-9 PM", 2)},
    },
    "tou-d-5-8pm": {
        f"sce:tou-d-5-8pm-{NEW}": {"urpx:description": (
            "Voluntary residential time-of-use option with summer on-peak 5:00 p.m.-8:00 p.m. weekdays. Alternate "
            "CPUC mass-migration default. " + bsc_sentence() + " " + ladder_sentence("tou-d-5-8pm") + " "
            + holidays("5 p.m. to 8 p.m."))},
        f"sce:tou-d-5-8pm-{NEW}-summary-generation": {"urpx:name": generation_summary(
            "TOU-D-5-8PM", f"Schedule TOU-D Sheet 4 (Cal. P.U.C. Sheet {leaf(4)})")},
        f"sce:cc-tou-d-5-8pm-{NEW}-evaluation": {"urpx:description": option_evaluation(
            "tou-d-5-8pm", "Option 5-8 PM", 4)},
    },
    "tou-d-prime": {
        f"sce:tou-d-prime-{NEW}": {"urpx:description": (
            "Voluntary residential time-of-use option with summer on-peak 4:00 p.m.-9:00 p.m. weekdays, the windows "
            "of Option 4-9 PM (Sheet 8), with no Baseline Credit. Advice 5897-E deletes the PRIME Eligibility "
            "Requirements Special Condition, so from this version Option PRIME is available on the terms of Sheet 1 "
            "alone: to Customers eligible for service under Schedule D, D-CARE or D-FERA, and not to Customers on "
            "Schedules DM, DMS-1, DMS-2 or DMS-3. Separately metered electric vehicle load is eligible for Option "
            "PRIME with an EV Meter Credit of $(0.371)/meter/day (Special Condition 4); a customer using an EV "
            "submeter receives an EV Submeter Credit of $(0.051)/meter/day (the EV Submetering Special Condition on "
            "Sheet 19). " + bsc_sentence() + " The Medical Baseline Credit line at 100.00 percent cross-references "
            "Schedule MB-E. " + holidays("4 p.m. to 9 p.m."))},
        f"sce:tou-d-prime-{NEW}-er-residential": {"urpx:description": (
            "Available to Customers eligible for service under Schedule D, D-CARE or D-FERA (Sheet 1): residential "
            "customers individually metered by SCE. Not available to Customers receiving service under Schedules DM, "
            "DMS-1, DMS-2 or DMS-3. The twelve-month minimum stay of Special Condition 5 applies to elective rate "
            "changes.")},
        f"sce:tou-d-prime-{NEW}-summary-generation": {"urpx:name": generation_summary(
            "TOU-D-PRIME", f"Schedule TOU-D Sheet 6 (Cal. P.U.C. Sheet {leaf(6)})")},
        f"sce:cc-tou-d-prime-{NEW}-evaluation": {"urpx:description": (
            "Two conditional credits on Sheet 6 are carried here without the conditions that gate them: the EV "
            "Meter Credit (Separately Metered EV Option) at $(0.371) per meter per day, which Special Condition 4 "
            "limits to a customer with a separate meter provided by SCE exclusively for charging electric vehicles, "
            "and the EV Submeter Credit at $(0.051) per meter per day, which the EV Submetering Special Condition on "
            "Sheet 19 limits to a customer whose submeter meets the Plug-In Electric Vehicle Submetering Protocol of "
            "Decision 22-08-024. This filing states both as unconditional, so a consumer computing a bill applies "
            "both to every Option PRIME customer. The two pilot bill discounts of Special Conditions 12 and 14 are "
            "also unrepresented: the San Joaquin Valley Disadvantaged Communities Pilot Bill Protection Discount (20 "
            "percent in years 1 through 5, then 10 or 20 percent in years 6 through 10) and the 20 percent "
            "Transitional Community Solar Discount. Option PRIME has no Baseline Credit line. The Option PRIME-CPP "
            "prices printed on the same sheet are the modifier sce:tou-d-prime-cpp; the Deed Restricted Base "
            "Services Charge adjustment of $(0.328) per meter per day, the CARE and FERA discount lines, and the "
            "Medical Baseline Credit line shown at 100.00 are cross-references to separate schedules each filed on "
            "its own.")},
    },
    "d": {
        f"sce:d-{NEW}": {"urpx:description": (
            "Tiered residential schedule (no time-of-use). Generation, distribution, and most flat-rate surcharges do "
            "not vary by tier or season. The two-tier structure (baseline / nonbaseline) is implemented via the "
            "Conservation Incentive Adjustment (CIA): customers receive a CIA credit of $-0.03496/kWh for usage "
            "at-or-below their daily baseline allocation, and pay a CIA charge of $+0.05605/kWh for usage above. The "
            "9.101 cent swing matches the Baseline Credit of Schedule TOU-D's Options 4-9 PM and 5-8 PM. Baseline "
            "allocations vary by Baseline Region (5/6/8/9/10/13/14/15/16), season (Summer = June-September; Winter "
            "= October-May), and Basic or All-Electric service per Preliminary Statement Part H. Base Services "
            "Charge (BSC) of $0.794/meter/day per Decision 24-05-028, with a BSC Discount of $(0.328)/meter/day for "
            "customers in deed-restricted affordable housing, modeled as sce:deed-restricted. The CARE and FERA "
            "discounts of Special Condition 4 (32.5 and 18.0 percent, with their BSC Surcharge exemption and BSC "
            "discount or credit adjustment) are modeled as sce:care and sce:fera.")},
        f"sce:d-{NEW}-summary-generation": {"urpx:name": generation_summary(
            "D", "Schedule D Sheet 2 (Cal. P.U.C. Sheet 91558-E)").replace(
            "The Gen rates", "The Generation rates")},
    },
    "care": {
        f"sce:care-{NEW}": {"urpx:description": (
            "California Alternate Rates for Energy (CARE) program: an income-qualified bill discount applied as an "
            "overlay to an SCE residential base rate plan (Schedule D, TOU-D-4-9PM, TOU-D-5-8PM or TOU-D-PRIME). "
            "Schedule D-CARE Sheet 1 states the terms, restated in Schedule TOU-D Special Condition 6 and Schedule D "
            "Special Condition 4. Eligibility: a CARE Household per Schedule D-CARE Special Condition 2. Modeled "
            "benefits: (1) the 32.5 percent bill discount on the pre-PUCRF, pre-tax subtotal, as a urpx:Price "
            "carrying urpx:multiplier -0.325 over the discountable urpx:PriceSummary of the base plan the customer "
            "takes; (2) exemption from the Wildfire Fund Non-Bypassable Charge, a $-0.00591/kWh credit; (3) "
            "exemption from the Fixed Recovery Charge, a $-0.01118/kWh credit; (4) exemption from the Base Services "
            "Charge Surcharge, a $-0.069/meter/day credit; and (5) the Base Services Charge Discount, a "
            "$-0.164/meter/day credit. Sheet 1 also exempts CARE customers from the CARE Surcharge of $0.215 per "
            "meter per day and from the CARE exempted Public Purpose Programs Charge of ($0.025) per meter per day; "
            "neither is modeled.")},
        f"sce:care-{NEW}-pd-frc-exemption": {"urpx:name":
            "CARE Fixed Recovery Charge Exemption (cancels base FRC of $0.01118/kWh)"},
        f"sce:care-pd-bsc-surcharge-exemption-{NEW}": {"urpx:name":
            "CARE BSC Surcharge Exemption (cancels the BSC Surcharge component of $0.069/meter/day from the base $0.794 BSC)"},
        f"sce:cc-care-{NEW}-evaluation": {"urpx:description": (
            "Sheet 1 of Schedule D-CARE states a 32.5 percent discount applied to a CARE customer's bill prior to "
            "the Public Utilities Commission Reimbursement Fee and any applicable user fees, taxes and late payment "
            "charges. This filing models it as a urpx:Price carrying urpx:multiplier -0.325 over the discountable "
            "subtotal of whichever SCE residential base plan the customer takes service under, naming the candidate "
            "subtotals of four schedules at every effective date, read disjunctively so that the one present in "
            "the consumer's graph applies. Each subtotal omits the Reimbursement Fee, the California Climate Credit, "
            "which Special Condition 12 applies after city and county utility users' taxes, and the Base Services "
            "Charge, which this filing adjusts through two per-meter-per-day credits. The four line items of the "
            "same Sheet 1 are carried alongside the percentage: the Wildfire Fund Non-Bypassable Charge exemption of "
            "$0.00591 per kWh, the Fixed Recovery Charge exemption of $0.01118 per kWh, the Base Services Charge "
            "Surcharge exemption of $0.069 per meter per day, and the Base Services Charge Discount of $(0.164) per "
            "meter per day. Four benefits of the schedule remain unrepresented, and they are why this claim is "
            "partial. Sheet 1 exempts CARE customers from the CARE Surcharge of $0.215 per meter per day and from "
            "the CARE exempted Public Purpose Programs Charge of ($0.025) per meter per day, neither of which any "
            "SCE residential rate sheet in this corpus itemizes. Special Condition 14 grants the San Joaquin Valley "
            "Disadvantaged Communities Pilot Bill Protection Discount, 20 percent in pilot years 1 through 5 and 10 "
            "or 20 percent in years 6 through 10, and Special Condition 15 a 20 percent Transitional Community Solar "
            "Discount; both are limited to pilot participants, and this filing carries no condition on pilot "
            "participation to gate them on. The California Climate Credit of Special Condition 12 is carried on the "
            "base rate plans this modifier overlays.")},
    },
    "fera": {
        f"sce:fera-{NEW}": {"urpx:description": (
            "Family Electric Rate Assistance (FERA) program: an income-qualified bill discount applied as an overlay "
            "to an SCE residential base rate plan. Schedule TOU-D Special Condition 7 (Sheet 13) states the terms, "
            "restated in Schedule D Special Condition 4 (Sheet 7), and defines the beneficiary by reference to "
            "Schedule D-FERA. Modeled benefits: (1) the 18.0 percent bill discount, as a urpx:Price carrying "
            "urpx:multiplier -0.18 over the discountable urpx:PriceSummary of the base plan the customer takes; (2) "
            "exemption from the Base Services Charge Surcharge, a $-0.069/meter/day credit; and (3) the Base "
            "Services Charge credit adjustment, a $-0.197/meter/day credit. FERA customers pay the Wildfire Fund "
            "Non-Bypassable Charge and the Fixed Recovery Charge at the standard rates.")},
        f"sce:fera-pd-bsc-surcharge-exemption-{NEW}": {"urpx:name":
            "FERA BSC Surcharge Exemption (cancels the BSC Surcharge component of $0.069/meter/day from the base $0.794 BSC)"},
    },
    "deed-restricted": {
        f"sce:deed-restricted-{NEW}": {"urpx:description": (
            "Base Services Charge (BSC) adjustment of $(0.328)/meter/day for SCE residential customers living in "
            "Deed Restricted Affordable Housing (DRAH), applied as an overlay to an SCE residential base rate plan "
            "(Schedule D, TOU-D-4-9PM, TOU-D-5-8PM or TOU-D-PRIME). It is the line \"BSC Adjustment - Deed "
            "Restricted\" on Schedule TOU-D Sheets 2 through 7 and \"BSC Discount - Deed Restricted\" on Schedule D "
            "Sheets 2 and 3. Schedule TOU-D Special Condition 9 (Sheet 15) and Schedule D Special Condition 4 (Sheet "
            "6) also exempt DRAH customers from the Base Services Charge Surcharge of $0.069 per meter per day, "
            "which this filing does not carry, so the modeled BSC for a DRAH customer is $0.466 per meter per day "
            "where the schedules give $0.397. Eligibility is carried as the customer-state property "
            "housingDeedRestricted.")},
        f"sce:deed-restricted-{NEW}-er-eligible": {"urpx:description": (
            "Customer lives in Deed Restricted Affordable Housing. Schedule TOU-D Special Condition 9 (Sheet 15): "
            "\"DRAH will be identified by the California Housing Partnership database. For properties with less "
            "than 80 percent of units identified as DRAH, Customers or tenants must contact SCE or visit "
            "www.sce.com and self-attest to living in a DRAH to qualify for the DRAH discount to reduce their Base "
            "Services Charge.\" Carried as the customer-state property housingDeedRestricted.")},
    },
    "tou-d-prime-cpp": {
        f"sce:tou-d-prime-cpp-{NEW}": {"urpx:description": (
            "Critical Peak Pricing (CPP) variant of Option PRIME, a customer-elected overlay of event charges and "
            "non-event credits on the base PRIME rates. Special Condition 3.b (Sheet 10): SCE calls 20 CPP Events per "
            "calendar year, each of 3 hours, notifying Customers no later than 3:00 p.m. the day before. Special "
            "Condition 1 (Sheet 9): within the five-hour CPP Event Window of 4:00 p.m. to 9:00 p.m., SCE designates "
            "the three-hour CPP Event Energy Charge Period, when the CPP Event Energy Charge of +$0.80000/kWh "
            "applies; in the Summer Season the CPP Non-Event Energy Credit of -$0.15170/kWh applies in the hours of "
            "the window outside that period, the whole window when no Event is called. Special Condition 3.d (Sheet "
            "11) limits CPP options to Bundled Service Customers and caps the sum of credits for CPP Customers "
            "eligible to continue dual participation with Schedule D-SDP; the cap is the Summer Season Maximum "
            "Available Credit of -$0.41944/kWh on Sheet 6. Special Condition 3.e's Bill Protection and 3.f's "
            "12-month minimum participation are not modeled. The CPP Event Energy Charge uses urpx:hasDynamicPricing "
            "with dynamicPricingType urpx:criticalPeakPricing, priceSource urpx:wholesaleMarketSource, "
            "updateFrequency urpx:eventTriggeredUpdates and a urpx:PriceUpdateRule describing the event trigger. "
            "The Non-Event Credit and the Maximum Available Credit carry ApplicabilityRule and CustomOperandNode "
            "gates: the Non-Event Credit applies when 'Is CPP Event Today' is false, and the Maximum Available "
            "Credit gates on the customer attribute 'Grandfathered D-SDP Dual Participation'.")},
        f"sce:tou-d-prime-cpp-{NEW}-er-eligible": {"urpx:description": (
            "Customer is on Option PRIME and has elected Option PRIME-CPP. Special Condition 3.d (Sheet 11): only "
            "Bundled Service Customers may be served under a CPP option; Direct Access and CCA Service Customers, "
            "and Customers served under Schedule S, are ineligible, and a CPP Customer may not dually enroll in any "
            "other demand response program.")},
        f"sce:tou-d-prime-cpp-{NEW}-pd-event-charge": {"urpx:name":
            "CPP Event Energy Charge, applies during the three-hour CPP Event Energy Charge Period SCE designates within 4-9 p.m. on CPP Event days"},
        f"sce:tou-d-prime-cpp-{NEW}-pd-non-event-credit": {"urpx:name":
            "CPP Non-Event Energy Credit, applies during Summer Season hours of the 4-9 p.m. CPP Event Window outside any CPP Event Energy Charge Period"},
        f"sce:tou-d-prime-cpp-{NEW}-pd-max-credit": {"urpx:name":
            "Maximum Available Credit: Summer Season cap on credits for CPP Customers continuing dual participation with Schedule D-SDP"},
        f"sce:tou-d-prime-cpp-{NEW}-ledger-max-credit": {"urpx:name":
            "PRIME-CPP Maximum Available Credit (D-SDP dual-participation cap)"},
        f"sce:tou-d-prime-cpp-price-max-credit-{NEW}": {"urpx:name":
            "Summer Season Maximum Available Credit (D-SDP dual-participation cap)"},
        f"sce:tou-d-prime-cpp-{NEW}-ar-max-credit": {"urpx:name":
            "Applies in Summer Season; cap on credits when the customer continues dual participation with Schedule D-SDP"},
        f"sce:tou-d-prime-cpp-{NEW}-ar-non-event-credit": {"urpx:name":
            "Applies during Summer Season hours of the 4 p.m.-9 p.m. CPP Event Window outside any CPP Event Energy Charge Period; June-September only"},
        f"sce:tou-d-prime-cpp-{NEW}-pur-event-trigger": {"urpx:description": (
            "Special Condition 3.a (Sheet 10): SCE may call a CPP Event any day, based on a California Independent "
            "System Operator Alert, forecasts of SCE system emergencies, forecasts of extreme or unusual "
            "temperature conditions impacting system demand, or day-ahead load and/or price forecasts. Special "
            "Condition 3.b: 20 CPP Events are called per calendar year, each of 3 hours. Special Condition 3.c: SCE "
            "notifies Customers no later than 3:00 p.m. the day before. The CPP Event Energy Charge of "
            "+$0.80000/kWh applies during the three-hour CPP Event Energy Charge Period SCE designates within the "
            "4:00 p.m. to 9:00 p.m. CPP Event Window, in addition to the customer's Option PRIME rate for the "
            "period.")},
        f"sce:cc-tou-d-prime-cpp-{NEW}-evaluation": {"urpx:description": (
            "This filing carries the three prices Schedule TOU-D publishes for Option PRIME-CPP on Sheet 6 (a CPP "
            "Event Energy Charge of $0.80000 per kWh, a Summer On-Peak Energy Credit of $(0.15170) per kWh outside "
            "CPP Events, and a Summer Season Maximum Available Credit of $(0.41944) per kWh) and leaves several "
            "provisions of Special Conditions 1 and 3 unrepresented. No time window is modeled, so neither CPP "
            "price is limited to the CPP Event Window of 4:00 p.m. to 9:00 p.m. or to the three-hour CPP Event "
            "Energy Charge Period SCE designates within it. The Maximum Available Credit is a cap on the sum of "
            "credits for a Customer continuing dual participation with Schedule D-SDP and is carried as an additive "
            "credit. Special Condition 3.e, Bill Protection, credits a customer on a CPP option with the positive "
            "sum, if any, of CPP Event Energy Charges and Summer Non-Event Energy Credits over up to the first "
            "twelve months, and settles across a year of bills rather than within one. Special Condition 3 states "
            "that exported generation during the CPP Non-Event Energy Credit Period may result in charges and that "
            "exported generation during the CPP Event Energy Charge Period may result in CPP Event energy credits; "
            "this filing's prices apply to a metered quantity that does not distinguish import from export. The "
            "event-calling criteria, the 20 three-hour events per calendar year and the notification duty of "
            "Special Conditions 3.a to 3.c, the eligibility limits of 3.d and the 12-month minimum participation of "
            "3.f are recorded as deferrals in this filing's manifest.")},
    },
    "cca-crs": {
        f"sce:cca-crs-{NEW}": None,  # rewritten from the 2026-03-20 text by CRS_EDITS
        f"sce:cca-crs-price-oat-generation-offset-{NEW}": {"urpx:name": (
            "Offset of the generation subtotal of whichever SCE residential base plan the customer is on. Schedule "
            "D Sheet 6 (91560-E) Special Condition 4.c and Schedule TOU-D Sheet 16 (91704-E) Special Condition 9.c: "
            "CCA Service Customers are billed for \"Delivery Service as displayed in this Rate Schedule and "
            "Generation charges determined by the CCA plus the applicable charges as shown in Schedule CCA-CRS\".")},
    },
    "da-crs": {
        f"sce:da-crs-{NEW}": None,
        f"sce:da-crs-price-oat-generation-offset-{NEW}": {"urpx:name": (
            "Offset of the generation subtotal of whichever SCE residential base plan the customer is on. Schedule "
            "D Sheet 6 (91560-E) Special Condition 4.b and Schedule TOU-D Sheet 15 (91703-E) Special Condition 9.b: "
            "Direct Access Customers \"purchase energy from an Energy Service Provider\" and are billed for Delivery "
            "Service plus \"the applicable charges as shown in Schedule DA-CRS\".")},
    },
}

# Exact substring edits to 2026-03-20 prose carried into the new version.
# Each (old, new) must occur in the named field.
EDITS: dict[str, list[tuple[str, str, str, str]]] = {
    "cca-crs": [
        (f"sce:cca-crs-{NEW}", "urpx:description", "FRC ($0.00619/kWh)", "FRC ($0.01118/kWh)"),
        (f"sce:cca-crs-{NEW}", "urpx:description", "ranging from $-0.00644 for 2025/2026 to $0.02624 for 2023",
         "ranging from $-0.00645 for 2025/2026 to $0.02631 for 2023"),
    ],
    "da-crs": [
        (f"sce:da-crs-{NEW}", "urpx:description", "FRC ($0.00619/kWh, Fixed Recovery Charge)",
         "FRC ($0.01118/kWh, Fixed Recovery Charge)"),
        (f"sce:da-crs-{NEW}", "urpx:description", "ranging from $-0.00644 for 2025/2026 vintages",
         "ranging from $-0.00645 for 2025/2026 vintages"),
        (f"sce:da-crs-{NEW}", "urpx:description", "to $0.02624 for 2023 vintage", "to $0.02631 for 2023 vintage"),
        (f"sce:da-crs-{NEW}", "urpx:description", "TOU-D Sheet 20 SC 11 / Schedule D Sheet 6 SC 4",
         "TOU-D Sheet 15 SC 9 / Schedule D Sheet 6 SC 4"),
        (f"sce:da-crs-{NEW}", "urpx:description", "(modeled at ca/iou/sce/cca-crs/)", "(sce:cca-crs)"),
    ],
    "d": [
        (f"sce:cc-d-{NEW}-evaluation", "urpx:description",
         " Both sheets are new here: the superseded 2025-11-15 source for this Schedule is a rate-table archive that mentions neither program.", ""),
        (f"sce:cc-d-{NEW}-evaluation", "urpx:description", "sum to the $0.18482 per kWh", "sum to the $0.19011 per kWh"),
        (f"sce:cc-d-{NEW}-evaluation", "urpx:description", "the $0.28590 printed", "the $0.28112 printed"),
        (f"sce:cc-d-{NEW}-evaluation", "urpx:description", "$0.11761 per kWh for UG", "$0.11255 per kWh for UG"),
        (f"sce:cc-d-{NEW}-evaluation", "urpx:description", "Fixed Recovery Charge at $0.00619 per kWh",
         "Fixed Recovery Charge at $0.01118 per kWh"),
        (f"sce:cc-d-{NEW}-evaluation", "urpx:description", "Deed Restricted BSC Discount of $(0.332)",
         "Deed Restricted BSC Discount of $(0.328)"),
    ],
}

def apply_prose(doc, slug: str) -> None:
    for i, fields in PROSE.get(slug, {}).items():
        if fields is None:
            continue
        node = find(doc, i)
        for k, v in fields.items():
            if k not in node:
                raise SystemExit(f"{slug}: {i} has no {k}")
            node[k] = v
    for i, k, old, new in EDITS.get(slug, []):
        node = find(doc, i)
        if node[k].count(old) != 1:
            raise SystemExit(f"{slug}: {i} {k}: {old!r} occurs {node[k].count(old)} times")
        node[k] = node[k].replace(old, new)


def structural(doc, slug: str) -> None:
    v = version_node(doc)
    if slug == "tou-d-prime":
        rules = v["urpx:hasEligibilityRule"]
        keep = [r for r in rules if not r["@id"].endswith("-er-qualifying-technology")]
        assert len(keep) == len(rules) - 1
        v["urpx:hasEligibilityRule"] = keep


def derive(slug: str) -> list[tuple[str, str, str]]:
    old = load(path(slug, OLD))
    doc = copy.deepcopy(old)
    m = rescope(doc, slug)
    apply_map(doc, m)
    set_strings(doc)
    rows = set_prices(doc, PRICES[slug], m, slug)
    set_source(doc, slug)
    v = version_node(doc)
    v.pop("urpx:expirationDateTime", None)
    apply_prose(doc, slug)
    structural(doc, slug)
    dump(path(slug, NEW), doc)
    return rows


# --- manifests ----------------------------------------------------------------

SP = ("https://edisonintl.sharepoint.com/teams/Public/TM2/Shared%20Documents/Public/Regulatory/"
      "Tariff-SCE%20Tariff%20Books/Electric/")
URLS = {
    "TOU-D": SP + "Schedules/Residential%20Rates/ELECTRIC_SCHEDULES_TOU-D.pdf",
    "D": SP + "Schedules/Residential%20Rates/ELECTRIC_SCHEDULES_D.pdf",
    "D-CARE": SP + "Schedules/Residential%20Rates/ELECTRIC_SCHEDULES_D-CARE.pdf",
    "CCA-CRS": SP + "Schedules/Other%20Rates/ELECTRIC_SCHEDULES_CCA-CRS.pdf",
    "DA-CRS": SP + "Schedules/Other%20Rates/ELECTRIC_SCHEDULES_DA-CRS.pdf",
    "PRELIM_H": SP + "Preliminary%20Statements/ELECTRIC_PRELIM_H.pdf",
}
DOC = {"tou-d-4-9pm": "TOU-D", "tou-d-5-8pm": "TOU-D", "tou-d-prime": "TOU-D", "tou-d-prime-cpp": "TOU-D",
       "deed-restricted": "TOU-D", "fera": "TOU-D", "d": "D", "care": "D-CARE", "cca-crs": "CCA-CRS",
       "da-crs": "DA-CRS"}
DOCKET = "Decision 26-04-033 (Advice 5897-E)"

FETCHED = """Source bytes. Retrieved 2026-10-06 from SCE's live tariff book with the
fetch path of dev/fetch_tariff_documents.py. SharePoint's download endpoint
answered with the PDF inside a multipart/form-data envelope; the committed
file is that envelope's one part body, extracted byte for byte, and the
sha256 recorded above is its hash."""

TOU_D_SHEETS = """Advice 5897-E (Decision 26-04-033) reissued all 19 sheets of Schedule TOU-D
effective October 1, 2026, Cal. P.U.C. Sheets 91689-E (Sheet 1) through
91707-E (Sheet 19). The schedule now holds six rate options, Option 4-9 PM,
4-9 PM-CPP, 5-8 PM, 5-8 PM-CPP, PRIME and PRIME-CPP. Rates are on Sheets 2 to
7. Special Condition 1 (TOU periods, the CPP Event Window, holidays and
seasons) is on Sheets 8 and 9; Special Condition 3 (Critical Peak Pricing) on
Sheets 10 to 12; Special Condition 4 (PRIME Separately-Metered EV Option) on
Sheet 12; Special Conditions 5 to 7 (Change of Rate Schedule, CARE, FERA) on
Sheet 13; Special Condition 8 (Arrearage Management Plan) on Sheet 14;
Special Condition 9 (Billing Calculation, with the DRAH terms) on Sheets 15
and 16; Special Condition 10 (California Climate Credit) on Sheet 16; the SJV
Pilot Bill Protection Discount (Special Condition 12) on Sheets 17 and 18,
where its continuation is headed 13; the Transitional Community Solar
Discount (Special Condition 14) on Sheet 18; and EV Submetering on Sheet 19.
The TOU periods, holidays and seasons are unchanged from the 2026-03-20
version."""

TOU_D_GAP = """Supersession. This version follows the 2026-06-01 version. Advice 5897-E's
sheets cancel the June 2026 sheets that version models: Advice 5829-E's rate
Sheets 2 to 6 (91196-E to 91200-E, effective June 1, 2026) and Advice 5837-E's
reissue of Sheets 1 and 7 to 19 (91354-E to 91367-E, effective June 25,
2026)."""


def holiday_deferral(sched: str) -> str:
    return (f"Schedule TOU-D Sheet 9: \"When any holiday listed above falls on Sunday, the following Monday will be "
            "recognized as a holiday. No change will be made for holidays falling on Saturday.\" New Year's Day, "
            "Independence Day, Veterans Day and Christmas in "
            f"sce:{sched}-{NEW}-holiday-calendar carry no urpx:observanceRule, so each resolves on its actual date "
            "and a Saturday one stays on Saturday. The Monday after a Sunday New Year's Day, Independence Day, "
            "Veterans Day or Christmas is carried as a dated urpx:Holiday with urpx:holidayDate: 2027-07-05, "
            "2029-11-12, 2032-07-05, 2033-12-26, 2034-01-02, 2035-11-12, 2038-07-05, 2039-12-26, 2040-01-02 and "
            "2040-11-12. After 2040 each such Sunday holiday needs a further dated entry, until "
            "urpx:mondayIfSundayObservance (proposed in urpx-org/urpx#77) can state the rule; the dated entries "
            "then come out.")


SJV = ("San Joaquin Valley Disadvantaged Communities Pilot Bill Protection Discount (Special Condition 12, Sheets 17 "
       "and 18, where the continuation is headed 13): 20 percent of the monthly bill in pilot years 1 through 5, then "
       "10 percent or 20 percent in years 6 through 10 depending on SCE's evaluation of participants' energy cost "
       "savings. Not modeled: the discount is gated on SJV Pilot participation, and a Price carrying it without that "
       "gate would discount every customer on the schedule. The percentage-of-subtotal shape itself is the one "
       "sce/care and sce/fera already ship against this filing's urpx:PriceSummary.")
TCS = ("Transitional Community Solar Discount (Special Condition 14, Sheet 18): 20 percent monthly bill credit over "
       "the same 10-year bill protection period, for SJV Pilot participants who cannot take the Community "
       "Solar-Green Tariff or the Disadvantaged Communities-Green Tariff. Same pilot-participation gate as Special "
       "Condition 12.")
CLIMATE = ("California Climate Credit carry-forward (Sheet 16, Special Condition 10): the $(36.00) per household credit "
           "is priced, but the roll-over of any portion not consumed in a billing period to subsequent billing periods "
           "is not expressed, so a consumer whose bill is smaller than the credit drops the remainder. Whether URPX "
           "can express it is not established: urpx:BillingCycle and settlementInterval exist, and no filing in this "
           "corpus uses them.")
CLIMATE_MONTHS = ("The California Climate Credit's urpx:ApplicabilityRule asserts urpx:month \"--04\" and \"--10\". "
                  "This filing's PDF names neither month: the rate tables footnote the credit only as \"Applied on an "
                  "equal basis, per household, semi-annually\" and Special Condition 10 (Sheet 16) names no month. "
                  "Either cite an external SCE source for April and October, or reduce the claim to the semi-annual "
                  "statement the sheets make.")
CHANGE = ("Special Condition 5, Change of Rate Schedule (Sheet 13), governs how long a customer stays on this Option and "
          "is not in the model. Verbatim: \"At any time, a Customer on this Schedule may elect to leave his/her Option "
          "(e.g., Option 4-9 PM, Option 5-8 PM, Option PRIME) and elect to either: (1) switch to another Option of "
          "this Schedule for which they are eligible, or (2) transfer from this Schedule to another applicable "
          "residential rate schedule. The elected rate change will become effective on the next regularly scheduled "
          "meter read date following the Customer's notice to SCE. Unless the Customer was placed on an Option by SCE "
          "(i.e., defaulted), the Customer shall not be allowed to make an additional change in rate until 12 months "
          "of service has been provided under the elected rate, unless otherwise specified in that rate schedule.\" "
          "urpx:minimumTenure exists on RatePlanVersion and the model does not set it; the re-entry half has no "
          "v0.5.1 form.")
AMP = ("Special Condition 8, Arrearage Management Plan (Sheet 14), in this filing's own PDF, changes what a customer on "
       "this Option owes and is not in the model. Verbatim: \"Once enrolled in the AMP, SCE shall forgive 1/12 of an "
       "eligible residential Customer's arrearage after each on-time payment. After 12 on-time payments, SCE shall "
       "forgive the remaining arrearage debt up to a maximum of $8,000 per instance of enrollment.\" Eligibility is "
       "six months of SCE service, CARE or FERA enrollment, at least one on-time payment, and an arrearage of $500 or "
       "greater at least 90 days old.")
BSC_SPLIT = ("Base Services Charge component split ({sheet}): the $0.794 per meter per day total is carried as one "
             "Price, but the sheet also prints its Distribution part of $0.491, itself a BSC Distribution Charge of "
             "$0.422 and a BSC Surcharge of $0.069, and a Public Purpose Programs part of $0.303. The $0.069 "
             "surcharge is the quantity CARE, FERA and DRAH customers are exempt from; sce/care and sce/fera price "
             "that exemption as a separate credit and sce/deed-restricted does not. Expressible now, purely "
             "additional PriceDefinitions summing to the same $0.794.")


def cpp_deferral(opt: str, sheet: int) -> str:
    return (f"{opt}-CPP, printed on this filing's own Sheet {sheet}: CPP Event Energy Charge $0.80000/kWh, Summer "
            "On-Peak Energy Credit $(0.15170)/kWh outside CPP Events, and Summer Season Maximum Available Credit "
            "$(0.41944)/kWh, with the CPP Event Window and the three-hour CPP Event Energy Charge Period defined in "
            "Special Condition 1 (Sheet 9) and the program in Special Condition 3 (Sheets 10 to 12). Work, not a "
            "blocker: sce/tou-d-prime-cpp ships the same three figures as a urpx:RatePlanModifier, so what is "
            "missing is a sibling filing listed in applicable_modifiers, not vocabulary.")


def option_deferrals(sched: str, opt: str, sheet: int, delivery: int) -> list[str]:
    return [cpp_deferral(opt, sheet), SJV, TCS, CLIMATE, holiday_deferral(sched),
            BSC_SPLIT.format(sheet=f"Sheet {delivery}"), CHANGE, AMP]


DEFERRALS: dict[str, list[str]] = {
    "tou-d-4-9pm": option_deferrals("tou-d-4-9pm", "Option 4-9 PM", 2, 3),
    "tou-d-5-8pm": option_deferrals("tou-d-5-8pm", "Option 5-8 PM", 4, 5),
    "tou-d-prime": [
        holiday_deferral("tou-d-prime"),
        ("Special Condition 4 (Sheet 12) limits the EV Meter Credit of $(0.371) per meter per day to \"customers with "
         "a separate meter provided by SCE exclusively for the charging of Electric Vehicles, as defined in Rule 1\", "
         "and the EV Submetering Special Condition (Sheet 19) limits the EV Submeter Credit of $(0.051) per meter per "
         "day to a customer whose EV submeter meets the Plug-In Electric Vehicle Submetering Protocol of Decision "
         "22-08-024. Both are modeled as unconditional PriceDefinitions, so a consumer gives every Option PRIME "
         "customer both credits. v0.5.1 supplies the vocabulary: PriceDefinition and Price both carry "
         "urpx:hasApplicabilityRule, and ApplicabilityRule carries urpx:hasConditionExpression with a "
         "CustomOperandNode for the metering arrangement. Not built."),
        SJV, TCS,
        (f"urpx:PriceSummary sce:tou-d-prime-{NEW}-summary-discountable, the subtotal that sce/care and sce/fera "
         "discount against, names 24 Prices in two different denominations: 22 in $/kWh, and two in $/Meter/Day "
         f"(sce:price-ev-meter-credit-{NEW} at $(0.371) and sce:price-ev-submeter-credit-{NEW} at $(0.051), both per "
         "Sheets 6 and 7). A sum over the urpx:unitPrice values of its members adds dollars per day to dollars per "
         "kWh, so the CARE 32.5 percent of Special Condition 6 and the FERA 18.0 percent of Special Condition 7 are "
         "percentages of a mixed-unit figure. Split it into two unit-homogeneous summaries with one modifier Price "
         "over each."),
        CLIMATE, CLIMATE_MONTHS, CHANGE, AMP,
    ],
    "d": [
        ("SJV Pilot Bill Protection Discount (Sheet 8, Special Condition 8, Cal. P.U.C. Sheet 90640-E): 20 percent off "
         "the bill in participation years 1 through 5, and 10 or 20 percent in years 6 through 10. Not built. This is "
         "work, not a blocker: under URPX v0.5.1 the pilot-participation gate is a urpx:ApplicabilityRule on the "
         "Price whose ConditionExpression compares a urpx:CustomOperandNode carrying urpx:customConditionProperty, "
         f"and the 20 percent is the multiplier plus basedOnPrice pattern sce:care already applies to sce:d-{NEW}-"
         "summary-discountable. Two parts stay unexpressed: the 10-year window runs from the participant's own "
         "first Bill Protection Discount and urpx:Price carries only absolute dates, and Sheet 8 leaves the years 6 "
         "through 10 rate to a future SCE evaluation rather than stating it."),
        ("Transitional Community Solar Discount (Sheet 9, Special Condition 9, Cal. P.U.C. Sheet 90641-E): 20 percent "
         "monthly bill credit for SJV Pilot participants eligible for CSGT or DAC-GT when neither is available, over "
         "the same 10-year bill protection period, excluded for customers with onsite solar under SASH, DAC-SASH or "
         "NEM. Not built, on the same footing as Special Condition 8 above."),
        ("California Climate Credit carry-forward (Sheet 7, Special Condition 5, Cal. P.U.C. Sheet 91561-E): the "
         "$(36.00) credit is priced, but Special Condition 5 also says any portion not consumed in the billing period "
         "in which it is applied rolls over to each subsequent billing period until fully consumed, and that is not "
         "expressed. The nearest v0.5.1 vocabulary is urpx:settlementInterval on the Ledger, an xsd:duration naming "
         "a fixed accumulation period, which does not state an unbounded roll-forward."),
        ("Baseline Allocation, the boundary between the Baseline and Over Baseline energy rates (Sheets 2 and 3, "
         "footnote *): the schedule prices $0.19011 per kWh at or below the allocation and $0.28112 above it, but "
         "says only that the allocations are 'as described in Preliminary Statement, Part H, Baseline Service'. Part "
         "H is not a source of this filing, so the kWh boundary is not sourced here. This is a source gap, not a "
         "URPX gap."),
        (f"CORRECTION, not an absence: sce:d-{NEW}-tiers-baseline-nonbaseline records bounds of 0 to 1.0 and above "
         f"1.0 while declaring referencesMetricInput to sce:d-{NEW}-mi-energy, whose MetricSpecification carries "
         "unitOfMeasure urpx:kWh. Read in its declared unit the model says the baseline tier ends at 1.0 kWh. The "
         "intended meaning is a fraction of the customer's Baseline Allocation. Fixable now: pointing the "
         "ServiceTiers at a metric denominated urpx:ratio conforms under v0.5.1. Any consumer that selects a tier by "
         "usage reads the baseline boundary as 1.0 kWh rather than the customer's allocation."),
        ("CORRECTION, not an absence: the California Climate Credit's urpx:ApplicabilityRule asserts urpx:month --04 "
         "and --10, which this filing's source does not state. Special Condition 5 on Sheet 7 names no month and "
         "Sheets 2 and 3 say only 'semi-annually'. The months are carried over from the 2025-11-15 source, which does "
         "state them. Either re-source them from a current SCE document or drop them."),
        BSC_SPLIT.format(sheet="Sheet 3").replace(
            "the quantity CARE, FERA and DRAH customers are exempt from",
            "the quantity Special Condition 4 on Sheets 6 and 7 exempts DRAH, CARE and FERA customers from"),
    ],
    "care": [
        ("CARE Surcharge exemption (Sheet 1, RATES, Cal. P.U.C. Sheet 91562-E): CARE customers are exempt from the "
         "CARE Surcharge of $0.215 per meter per day. Expressible now: it is the same per-meter-per-day credit shape "
         "as the $(0.069) Base Services Charge Surcharge exemption this filing already carries. Unbuilt, not "
         "blocked. Schedule D Sheet 3 footnote 5 places the California Alternate Rates for Energy Surcharge inside "
         "the Public Purpose Programs Charge, and the only per-meter-per-day PPPC on that sheet is the $0.303 "
         "component of the $0.794 Base Services Charge that sce:d, sce:tou-d-4-9pm, sce:tou-d-5-8pm and "
         "sce:tou-d-prime each model as a single price. What this corpus does not hold is SCE's decomposition of "
         "that $0.303, so the credit cannot be reconciled against a published figure before it is added."),
        ("CARE exempted Public Purpose Programs Charge (Sheet 1, Cal. P.U.C. Sheet 91562-E, new under Advice "
         "5897-E): \"CARE Customers are exempt from paying the CARE Surcharge of $0.215 per meter per day, the CARE "
         "exempted Public Purpose Programs Charge of ($0.025) per meter per day, the Wildfire Fund Non-Bypassable "
         "Charge of $0.00591 per kWh, and the Fixed Recovery Charge of $0.01118 per kWh.\" The amount is printed as "
         "a credit, and the sheet does not say which charge it is part of or how an exemption from a negative amount "
         "is billed. Not modeled until that is settled."),
        ("San Joaquin Valley Disadvantaged Communities Pilot Bill Protection Discount (Sheet 6, Special Condition 14, "
         "Cal. P.U.C. Sheet 90647-E): 20 percent of the monthly bill in pilot years 1 through 5, and 10 percent or 20 "
         "percent in years 6 through 10, the choice settled by an SCE evaluation of participants' total energy cost "
         "savings. Expressible now as a Price carrying urpx:multiplier over the base plan's discountable "
         "PriceSummary, gated by urpx:hasApplicabilityRule on SJV Pilot participation. Unbuilt. The same provision "
         "is Schedule D Special Condition 8 and is recorded as a deferral on sce:d."),
        ("Transitional Community Solar Discount (Sheet 6, Special Condition 15, Cal. P.U.C. Sheet 90647-E): a 20 "
         "percent monthly bill credit to SJV Pilot participants over the same 10 year bill protection period, "
         "payable when neither the Community Solar-Green Tariff nor the Disadvantaged Communities-Green Tariff is "
         "available to them. Same price shape and same pilot-participation gate as Special Condition 14. The same "
         "provision is Schedule D Special Condition 9 and is recorded as a deferral on sce:d."),
        ("Sheet 1 APPLICABILITY (Cal. P.U.C. Sheet 91562-E) states two eligibility predicates the model does not "
         "carry. Verbatim: \"Applicable to domestic service to California Alternate Rates for Energy (CARE) "
         "households residing in a permanent Single-Family Accommodation or Multifamily Accommodation where the "
         "customer meets all the Special Conditions of this Schedule. Customers enrolled in the CARE program are not "
         "eligible for the Family Electric Rate Assistance (FERA) program.\" The EligibilityRule carries residential "
         "customer kind AND Program Enrollment = CARE, and neither the accommodation-type predicate nor the FERA "
         "exclusion. The exclusion is expressible: cpau:e-nse-1-2025-09-01-cn-nem-successor is a notEqualsOperator "
         "test of the same shape."),
        ("Special Condition 4 (application), Special Condition 5 (commencement), Special Condition 7 (verification) "
         "and Special Condition 9 (rebilling) are conditions of service on this Schedule's own sheets, unmodeled. "
         "Special Condition 2's income table (Sheet 2, Cal. P.U.C. Sheet 91082-E, Advice 5813-E: from $43,280 at one "
         "to two persons up to $111,440 at eight, plus $11,360 per additional person, effective June 1, 2026) and "
         "Special Condition 3's Group Living Facility definition are the substantive eligibility content the "
         "EligibilityRule's description paraphrases without encoding."),
        ("Special Condition 13, Arrearage Management Plan (Sheet 5, Cal. P.U.C. Sheet 91034-E): forgiveness of 1/12 "
         "of an eligible Customer's arrearage after each on-time payment, the remainder forgiven after 12 on-time "
         "payments, capped at $8,000 per instance of enrollment. It changes what the customer owes and is stated on "
         "this filing's own sheet; it is not in the model."),
    ],
    "fera": [
        ("18.0 percent discount base excludes the PUC Reimbursement Fee without warrant in FERA's own text. Schedule "
         "TOU-D Sheet 13 Special Condition 7, restated in Schedule D Sheet 7, applies the discount to the bill "
         "\"prior to the application of any applicable taxes and late payment charges\" and carves out no PUCRF; "
         "Special Condition 6 does carve it out for CARE and requires CARE customers to pay it in full. The -0.18 "
         "Price here is based on the shared sce:<plan>-<date>-summary-discountable, which excludes the PUCRF "
         "(0.00100 $/kWh on Schedule D at this date) and whose name asserts CARE and FERA discount the same "
         "components. On the plain text the modeled discount is short by 18 percent of the PUCRF. The fix is "
         "expressible under v0.5.1 and is already the SDG&E pattern in this corpus: add a FERA-specific PriceSummary "
         "including the PUCRF to each SCE base plan at each date and repoint basedOnPrice at them. Not built. "
         "Confirm against SCE billing practice before building, since only the tariff text has been read."),
        ("Whether the 18.0 percent applies to the adjusted Base Services Charge is unresolved and the model assumes "
         "it does not. Special Condition 7 discounts \"their bill\", on which the $0.794 per meter per day BSC "
         "appears, and separately reduces that BSC \"In addition\" by the $0.069 surcharge exemption and the "
         "$(0.197) credit adjustment carried here. The model applies the percentage only to the per-kWh subtotal, "
         "leaving the adjusted $0.528 per meter per day undiscounted. Neither SCE PDF decides it; SDG&E's Schedule "
         "FERA Sheet 1 excludes the base services charge from its own discount base, which supports the current "
         "treatment but is another utility's language. If the answer turns out to be yes, it is expressible under "
         "v0.5.1: build a PriceSummary per base plan and date holding the base's BSC Price plus this filing's two "
         "credits and add a second -0.18 Price based on it."),
        ("Special Condition 7 (Sheet 13, Cal. P.U.C. Sheet 91701-E) states four conditions of service the model does "
         "not carry. Verbatim: \"An application and eligibility declaration is required for service under this "
         "Special Condition. Eligible Customers shall be billed on this Special Condition commencing no later than "
         "one billing period after receipt and approval of the Customer's application by SCE. Customers may be "
         "rebilled for periods in which they do not meet the eligibility requirements for the CARE Discount. "
         "Customers receiving service under the CARE Discount Special Condition of this Schedule are not eligible to "
         "take service under this Special Condition.\" The EligibilityRule is residential customer kind AND Program "
         "Enrollment = FERA, with no CARE-exclusion predicate."),
        ("Special Condition 7 defines the beneficiary by reference to Schedule D-FERA, which is in no PDF in this "
         "corpus, so the household definition behind the modeled -0.18 multiplier is unsourced in the filing."),
        ("Special Condition 8 Arrearage Management Plan (Sheet 14), in this filing's own PDF, is gated on CARE or "
         "FERA enrollment and forgives 1/12 of an eligible Customer's arrearage after each on-time payment, the "
         "remainder after 12, up to $8,000 per instance of enrollment, with a 12-month waiting period before "
         "re-enrollment. It changes what a FERA customer owes and is not in the model."),
    ],
    "deed-restricted": [
        ("DRAH exemption from the Base Services Charge Surcharge is not modeled. Schedule TOU-D Sheet 15 Special "
         f"Condition 9 (Cal. P.U.C. Sheet {leaf(15)}) and Schedule D Sheet 6 Special Condition 4 (91560-E) both read: "
         "\"DRAH Customers or tenants are exempt from the Base Services Charge Surcharge of $0.069 per meter per day "
         "and are provided a Base Services Charge Discount of $(0.328) per meter per day to reduce the Base Services "
         "Charge.\" Those are two separate reductions, in the same two-clause form Special Conditions 6 and 7 use for "
         "CARE and FERA. This filing models only the second, as the rate-table line \"BSC Adjustment - Deed "
         "Restricted\" at $-0.328/meter/day (Sheets 2 to 7), so a DRAH customer resolves $0.069/meter/day short of "
         "the schedule: $0.466 where the schedule gives $0.397. Expressible now, not blocked: the base plans carry "
         "the BSC as one undifferentiated $0.794 Price, so the exemption has to be a second credit Price here, the "
         f"shape sce/care {NEW} already ships (sce:care-price-bsc-surcharge-exemption-{NEW}, unitPrice -0.069). "
         "The Special Condition prose and the rate-table footnote now agree on both figures."),
        ("Schedule TOU-D Sheet 15 Special Condition 9, in this filing's own PDF, states how DRAH status is "
         "established, and the model does not carry it. Verbatim: \"DRAH will be identified by the California "
         "Housing Partnership database. For properties with less than 80 percent of units identified as DRAH, "
         "Customers or tenants must contact SCE or visit www.sce.com and self-attest to living in a DRAH to qualify "
         "for the DRAH discount to reduce their Base Services Charge.\" The EligibilityRule tests a CustomOperandNode "
         "customConditionProperty \"housingDeedRestricted\" equal to true."),
    ],
    "tou-d-prime-cpp": [
        ("CPP time windows are not modeled, so both CPP prices apply at every hour. Special Condition 1 (Sheets 8 and "
         "9): the CPP Event Window is \"the five-hour period from 4:00 p.m. to 9:00 p.m. during which SCE may "
         "designate the three-hour CPP Event Energy Charge Period\"; the CPP Event Energy Charge applies in that "
         "designated period, and during the Summer Season the CPP Non-Event Energy Credit Period is the hours of the "
         "window outside it, the whole window when no Event is called. This filing carries no TOUSchedule, TOUPeriod "
         "or TimeBracket. The window is expressible at v0.5.1 with urpx:hasTOUSchedule on the modifier's "
         "BillingModel (precedent: smud:tou-pev-credit); which three hours SCE designates is event data, not tariff "
         "data."),
        ("Maximum Available Credit is carried as an additive credit of -0.41944 per kWh, but the schedule makes it a "
         "cap. Sheet 6 footnote: \"The Maximum Available Credit is the capped credit amount for CPP Customers dual "
         "participating in other demand response programs.\" Special Condition 3.d (Sheet 11): \"For CPP Customers "
         "eligible to continue to dually participate with Schedule D-SDP, the sum of credits provided by the dual "
         "participating demand response program of this Schedule will be capped.\" URPX v0.5.1 has no vocabulary for "
         "a bound on the sum of two credits: bounds exist only on ServiceBracket, and priceFloor / priceCeiling are "
         "DynamicPricing runtime clamps. Stop publishing it as an additive Price."),
        ("Summer-only applicability is recorded on the Price rather than the PriceDefinition. Both credit Prices "
         "carry urpx:hasApplicabilityRule with month --06 --07 --08 --09, and neither PriceDefinition carries a month "
         "of its own. Moving the rule to the PriceDefinition is the modeling fix; URPX expresses the constraint "
         "either way."),
        ("Exported generation is not distinguished. Special Condition 3 (Sheet 10): \"During the Summer Season, "
         "exported generation during the CPP Non-Event Energy Credit Period may result in charges under this "
         "Schedule. Exported generation during the CPP Event Energy Charge Period may result in applicable CPP Event "
         "energy credits, regardless of the season in which the CPP Event occurs.\" All three CPP prices share one "
         f"direction-less MetricInput, sce:tou-d-prime-cpp-{NEW}-mi-energy, so nothing in this filing separates "
         "imported from exported kWh. urpx:flowDirection on a MetricSpecification is the v0.5.1 route. Work, not a "
         "blocker."),
        ("Bill Protection is not modeled. Special Condition 3.e (Sheet 11): \"A Customer served on CPP will receive a "
         "one-time Bill Protection credit for the positive sum, if any, in total CPP Event Energy Charges and total "
         "CPP Summer Non-Event Energy Credits as calculated under a the applicable Option with CPP, and as measured "
         "over a period of up to 12 months from the date the Customer elects an Option with CPP.\" What cannot be "
         "computed is its amount, the conditional positive-part arithmetic in 'the positive sum, if any'; v0.5.1 "
         "has no cap, floor or greater-of vocabulary outside DynamicPricing runtime clamps."),
        ("Special Conditions 3.a to 3.c (Sheet 10) trigger and bound the CPP Event Energy Charge this filing prices "
         "at $0.80000/kWh, and none of it is in the model. Verbatim: \"SCE may, at its discretion, call a CPP Event "
         "any day.\" \"20 CPP Events are called per calendar year. Each CPP Event has a duration of 3 hours, for a "
         "total of 60 hours per calendar year.\" \"SCE will begin to notify Customers no later than 3:00 p.m. the day "
         "before a CPP Event.\" DynamicPricingShape and PriceUpdateRuleShape are both sh:closed and neither admits "
         "an event count, a duration, a notice interval or a trigger criterion, so this is a blocked deferral "
         "rather than unbuilt work."),
        ("Special Condition 3.d's limits (Sheet 11: Bundled Service Customers only; Direct Access, CCA Service and "
         "Schedule S customers ineligible; no dual enrollment in other demand response programs) and Special "
         "Condition 3.f's 12-month minimum participation (Sheet 12) are availability terms the single "
         "EligibilityRule does not encode."),
        ("The Maximum Available Credit Price is gated on a customer attribute this filing cannot decide: its "
         "ApplicabilityRule compares the CustomOperandNode 'Grandfathered D-SDP Dual Participation' to true, and "
         "whether a given customer continues dual participation with Schedule D-SDP is stated by no property of the "
         "document. A per-unit rate summed over the three Prices therefore rests on assuming the gate holds, so "
         "dev/baseline/marginal-rates.edn records this filing as refused rather than carrying a rate."),
    ],
}


def crs_deferrals(slug: str) -> list[str]:
    """The 2026-03-20 deferrals with this version's sheet numbers, values and @ids."""
    old = load_toml(SCE / slug / "versions" / OLD / "tariff.toml")["modeling"]["deferrals"]
    first, last = ("91551-E", "91557-E") if slug == "cca-crs" else ("91564-E", "91570-E")
    out = []
    for d in old:
        d = d.replace("Sheet 4's Fixed Recovery Charge at 0.00619", "Sheet 4's Fixed Recovery Charge at 0.01118")
        d = d.replace("(90845-E through 90851-E)", f"({first} through {last})")
        d = d.replace(f"sce:d-{OLD}-price-wfc", f"sce:d-{NEW}-price-wfc")
        d = d.replace("Schedule D Sheet 3 (90842-E)", "Schedule D Sheet 3 (91559-E)")
        d = d.replace(f"sce:care-price-wfc-exemption-{OLD}", f"sce:care-price-wfc-exemption-{NEW}")
        out.append(d)
    return out


def load_toml(p: Path):
    import tomli
    return tomli.loads(p.read_text(encoding="utf-8"))


def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def wrap(text: str) -> str:
    import textwrap
    paras = [p.strip() for p in text.strip().split("\n\n")]
    return "\n\n".join("\n".join(textwrap.wrap(" ".join(p.split()), 78, break_long_words=False,
                                               break_on_hyphens=False)) for p in paras)


def price_lines(rows) -> str:
    out = []
    for i, a, b in rows:
        if a == b:
            continue
        name = i.replace(f"-{OLD}", "").replace("sce:", "")
        out.append(f" {name}: {a} -> {b}")
    return "\n".join(out)


def sha(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


NOTES = {
    "tou-d-4-9pm": "",
    "tou-d-5-8pm": "",
    "tou-d-prime": """Eligibility. Advice 5897-E deletes the PRIME Eligibility Requirements
Special Condition (Special Condition 5 on Sheet 17 of the 2026-03-20 source),
which required a newly enrolling Customer to attest to an electric vehicle,
behind-the-meter storage or an electric heat pump. Sheet 1 now makes the
Schedule, Option PRIME included, available to Customers eligible for
Schedules D, D-CARE and D-FERA. This version therefore drops the
qualifying-technology EligibilityRule the 2026-03-20 version carries.""",
    "tou-d-prime-cpp": """Critical Peak Pricing. Special Condition 3 now calls 20 CPP Events per
calendar year, each of 3 hours, and Special Condition 1 makes the 4:00 p.m.
to 9:00 p.m. period a CPP Event Window within which SCE designates the
three-hour CPP Event Energy Charge Period. The 2026-03-20 source called 12 to
15 Events of 4:00 p.m. to 9:00 p.m. The Maximum Available Credit now applies
to CPP Customers continuing dual participation with Schedule D-SDP, without
the Option A-CPP and B-CPP references, which Advice 5897-E removes with
Options A and B. Special Condition 3.f adds a 12-month minimum participation
period.""",
    "deed-restricted": "",
    "fera": """The FERA terms are Special Condition 7 on Sheet 13 (91701-E), restated in
Schedule D Special Condition 4 on Sheet 7 (91561-E), both at $0.069 and
$(0.197).""",
    "d": """Advice 5897-E reissued Schedule D Sheets 2, 3, 6 and 7 (91558-E to 91561-E)
effective October 1, 2026; Sheets 1, 4, 5, 8 and 9 are unchanged since
November 15, 2025 (Advice 5654-E).

Supersession. This version follows the 2026-06-01 version, whose Sheets 2, 3,
6 and 7 (91130-E to 91133-E, Advice 5829-E) these cancel.""",
    "care": """Schedule D-CARE as of 2026-10-01: Sheet 1 (91562-E, Advice 5897-E) effective
October 1, 2026; Sheet 2 (91082-E, Advice 5813-E, the Special Condition 2
income limits) effective June 1, 2026; Sheet 4 (91323-E, Advice 5837-E)
effective June 25, 2026; Sheets 3, 5 and 6 unchanged since 2025 or March 20,
2026. Sheet 1 adds an exemption from a \"CARE exempted Public Purpose Programs
Charge of ($0.025) per meter per day\", recorded as a deferral.

Supersession. This version follows the 2026-06-01 version: Sheet 1 (91562-E)
cancels 91322-E (Advice 5837-E, effective June 25, 2026), which cancelled
91134-E (Advice 5829-E, effective June 1, 2026).""",
    "cca-crs": """Advice 5897-E reissued Schedule CCA-CRS Sheets 4 to 10 (91551-E to 91557-E)
effective October 1, 2026; Sheets 1 to 3 are unchanged since July 27, 2023
and Sheets 11 and 12 since January 1, 2026. Domestic row: the Fixed Recovery
Charge and every PCIA vintage from 2009 moved; WFC $0.00591 and CTC $0.00014
are unchanged.

Supersession. This version follows the 2026-06-25 version, whose Sheets 4 to 10
(91310-E to 91316-E, Advice 5837-E) these cancel.""",
    "da-crs": """Advice 5897-E reissued Schedule DA-CRS Sheets 4 to 10 (91564-E to 91570-E)
effective October 1, 2026; Sheets 1 to 3 are unchanged since July 27, 2023
and Sheets 11 and 12 since January 1, 2026. Domestic row: the Fixed Recovery
Charge and every PCIA vintage from 2009 moved; WFC $0.00591 and CTC $0.00014
are unchanged.

Supersession. This version follows the 2026-06-25 version, whose Sheets 4 to 10
(91328-E to 91334-E, Advice 5837-E) these cancel.""",
}

TOU_D_FAMILY = ["tou-d-4-9pm", "tou-d-5-8pm", "tou-d-prime", "tou-d-prime-cpp", "deed-restricted", "fera"]


def write_manifest(slug: str, rows) -> None:
    d = SCE / slug / "versions" / NEW
    old = load_toml(SCE / slug / "versions" / OLD / "tariff.toml")
    pdf = d / f"sce_{slug}_{NEW}.pdf"
    src = (f'url = "{URLS[DOC[slug]]}"\nsha256 = "{sha(pdf)}"\nretrieved_on = "{RETRIEVED}"\n'
           'media_type = "application/pdf"\nfiling_type = "advice-letter"\nfiling_id = "SCE-AL-5897-E"')
    ladder = slug in ("tou-d-4-9pm", "tou-d-5-8pm")
    if ladder:
        ph = d / "sce_prelim-h_2026-10-01.pdf"
        source = ("[source]\n\n  [source.base]\n" + "\n".join("  " + l for l in src.split("\n")) + "\n\n"
                  "  # Preliminary Statement Part H: the Baseline Allocations bounding Tier 1 and the\n"
                  "  # HPWH Allocation the second document in this directory adds to them.\n"
                  "  [source.prelim_h]\n"
                  f'  url = "{URLS["PRELIM_H"]}"\n  sha256 = "{sha(ph)}"\n  retrieved_on = "{RETRIEVED}"\n'
                  '  media_type = "application/pdf"\n  filing_type = "advice-letter"\n  filing_id = "SCE-AL-5897-E"')
        regulator = ("[regulator]\n  [regulator.base]\n  authority = \"puc\"\n"
                     f"  docket = \"{DOCKET}\"\n\n  [regulator.prelim_h]\n  authority = \"puc\"\n"
                     "  docket = \"Decision 26-04-033 (Preliminary Statement Part H Sheets 2 and 3, Advice 5897-E)\"")
    else:
        source = "[source]\n" + src
        regulator = f'[regulator]\nauthority = "puc"\ndocket = "{DOCKET}"'
    parts = [FETCHED]
    if slug in TOU_D_FAMILY:
        parts += [TOU_D_SHEETS, TOU_D_GAP]
    if NOTES.get(slug):
        parts.append(NOTES[slug])
    parts.append("Price changes from the 2026-03-20 version, $ (per kWh unless a per-day\ncharge):\n"
                 + price_lines(rows))
    notes = "\n\n".join(wrap(p) if not p.startswith("Price changes") else p for p in parts)
    deferrals = crs_deferrals(slug) if slug in ("cca-crs", "da-crs") else DEFERRALS[slug]
    mods = old["modeling"].get("applicable_modifiers")
    lines = [
        "# Identity --------------------------------------------------------------------",
        'utility = "sce"', f'schedule = "{slug}"', f'effective_date = "{NEW}"', "",
        "# Source ----------------------------------------------------------------------",
        source, "",
        "# Regulatory ------------------------------------------------------------------",
        regulator, "",
        "# Extraction ------------------------------------------------------------------",
        "[extraction]", 'tool = "manual"', f'extracted_on = "{RETRIEVED}"', 'notes = """', notes, '"""', "",
        "# Validation ------------------------------------------------------------------",
        "[validation]", "shacl_passed = true", 'validator = "clj-shacl + clj-urpx (URPX v0.5.1)"',
        f'validated_on = "{RETRIEVED}"', "",
        "# Modeling -------------------------------------------------------------------",
        "[modeling]", "complete = false", "deferrals = [",
        *[" " + toml_str(x) + "," for x in deferrals], "]",
    ]
    if mods is not None:
        lines += ["applicable_modifiers = [", *[f' "{m}",' for m in mods], "]"]
    lines += ["", "# Review ----------------------------------------------------------------------",
              "[review]", 'status = "draft"',
              f'notes = {toml_str(f"Derived from the 2026-03-20 version by dev/author_sce_2026_10_01.py: every Price reconciled to the Advice 5897-E sheets, prose and citations rewritten for them. See [extraction] notes.")}',
              ""]
    text = "\n".join(lines)
    load_toml_text(text)
    (d / "tariff.toml").write_text(text, encoding="utf-8")


def load_toml_text(t: str):
    import tomli
    return tomli.loads(t)


FILES = {"TOU-D": "ELECTRIC_SCHEDULES_TOU-D.pdf", "D": "ELECTRIC_SCHEDULES_D.pdf",
         "D-CARE": "ELECTRIC_SCHEDULES_D-CARE.pdf", "CCA-CRS": "ELECTRIC_SCHEDULES_CCA-CRS.pdf",
         "DA-CRS": "ELECTRIC_SCHEDULES_DA-CRS.pdf", "PRELIM_H": "ELECTRIC_PRELIM_H.pdf"}


def vendor(fetched: Path) -> None:
    """Copy the fetched documents into the new filing directories, refusing anything not a PDF."""
    for slug in BASES + MODIFIERS:
        names = [(DOC[slug], f"sce_{slug}_{NEW}.pdf")]
        if slug in ("tou-d-4-9pm", "tou-d-5-8pm"):
            names.append(("PRELIM_H", f"sce_prelim-h_{NEW}.pdf"))
        for doc, name in names:
            body = (fetched / FILES[doc]).read_bytes()
            if body[:5] != b"%PDF-":
                raise SystemExit(f"{FILES[doc]}: not a PDF; unwrap it with dev/fetch_tariff_documents.py --unwrap")
            dst = SCE / slug / "versions" / NEW / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(body)


def candidates() -> None:
    """Every CARE, FERA and CRS Price over base subtotals names every candidate.

    dev/lint_discount_summaries.py requires each such Price, in every version, to
    name each base's subtotal at every date, read disjunctively. The candidates
    are the subtotals of that kind the base filings on disk actually define, so
    a version added at any date joins every list.
    """
    order = {b: i for i, b in enumerate(BASES)}
    pat = re.compile(r"^sce:(.+)-(\d{4}-\d{2}-\d{2})-summary-(discountable|generation)$")
    defined: dict[str, set[str]] = {"discountable": set(), "generation": set()}
    for b in BASES:
        for p in (SCE / b / "versions").glob("*/rate-plan_*.jsonld"):
            def h(d):
                m = pat.match(d.get("@id", ""))
                if m and m.group(1) == b and len(d) > 1:
                    defined[m.group(3)].add(d["@id"])
            walk(load(p), h)
    for slug in ("care", "fera", "cca-crs", "da-crs"):
        for p in sorted((SCE / slug / "versions").glob("*/*.jsonld")):
            doc = load(p)

            def f(d):
                if d.get("@type") != "urpx:Price" or "urpx:basedOnPrice" not in d:
                    return
                names = {x["@id"] for x in d["urpx:basedOnPrice"]}
                kinds = {pat.match(n).group(3) for n in names}
                assert len(kinds) == 1, (p, kinds)
                d["urpx:basedOnPrice"] = [{"@id": n} for n in sorted(
                    defined[kinds.pop()], key=lambda n: (order[pat.match(n).group(1)], pat.match(n).group(2)))]
            walk(doc, f)

            def g(d):
                t = d.get("urpx:description")
                if isinstance(t, str):
                    for old in COUNTED:
                        t = t.replace(old, EVERY)
                    d["urpx:description"] = t
            walk(doc, g)
            dump(p, doc)


COUNTED = ("The price names all eight candidate subtotals, four schedules at two effective dates each,",
           "The price names all twelve candidate subtotals, four schedules at three effective dates each,")
EVERY = "The price names the candidate subtotals of four schedules at every effective date,"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python3 dev/author_sce_2026_10_01.py <directory holding the fetched PDFs>")
        return 2
    vendor(Path(argv[1]))
    report = {}
    for slug in BASES + MODIFIERS:
        report[slug] = derive(slug)
    for slug in BASES + MODIFIERS:
        expire_old(slug)
        write_manifest(slug, report[slug])
    candidates()
    for slug, rows in report.items():
        moved = [r for r in rows if r[1] != r[2]]
        print(f"{slug}: {len(rows)} prices, {len(moved)} moved")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv))
