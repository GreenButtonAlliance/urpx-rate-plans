#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Author the SCE versions in force from June 2026 until October 1, 2026.

Advice 5829-E cancelled the 2026-03-20 rate sheets of Schedules TOU-D and D
effective June 1, 2026, along with D-CARE Sheet 1 and the CARE, FERA and DRAH
Special Conditions of Schedule TOU-D. Advice 5837-E reissued Schedule TOU-D's
Special Conditions, CCA-CRS and DA-CRS Sheets 4 to 10, D-CARE Sheet 1 and
Schedule MB-E effective June 25, 2026, leaving every value this corpus prices
on the June 1 sheets unchanged. Each filing therefore gains one version, from
the date its 2026-03-20 (or, for medical-baseline, 2025-10-01) rate sheet was
cancelled until October 1, 2026:

  2026-06-01  tou-d-4-9pm, tou-d-5-8pm, tou-d-prime, tou-d-prime-cpp,
              deed-restricted, fera, d, care
  2026-06-25  cca-crs, da-crs, medical-baseline

The source of each is the live tariff book as fetched 2026-09-23 into
data/documents/sce/. The June 1 values are also checked against Advice
5829-E's own copies of the sheets, which hold the June 1 sheets that the
June 25 reissue cancelled (91134-E, 91201-E, 91202-E, 91203-E).

Run from the repo root, after dev/author_sce_2026_10_01.py and before
dev/author_sce_tou_d_baseline.py and dev/resync_coverage_evaluations.py:

    python3 dev/author_sce_2026_06.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import author_sce_2026_10_01 as A  # noqa: E402

REPO, SCE = A.REPO, A.SCE
PRIOR = "2026-03-20"
OCT = "2026-10-01"
RETRIEVED = "2026-09-23"
DOCS = REPO / "data" / "documents" / "sce"

JUNE = {s: "2026-06-01" for s in ("tou-d-4-9pm", "tou-d-5-8pm", "tou-d-prime", "tou-d-prime-cpp",
                                  "deed-restricted", "fera", "d", "care")}
JUNE.update({"cca-crs": "2026-06-25", "da-crs": "2026-06-25"})
MB_OLD, MB_NEW = "2025-10-01", "2026-06-25"

# Advice 5829-E's sheet numbers (June 1, 2026) and Advice 5837-E's (June 25),
# as printed in the 2026-09-23 copy of each schedule.
TOU_D_LEAF = {1: "91354-E", 2: "91196-E", 3: "91197-E", 4: "91198-E", 5: "91199-E", 6: "91200-E",
              7: "91355-E", 8: "91356-E", 9: "91357-E", 10: "91358-E", 11: "91359-E", 12: "91360-E",
              13: "91361-E", 14: "91362-E", 15: "91363-E", 16: "91364-E", 17: "91365-E", 18: "91366-E",
              19: "91367-E"}
TOU_D = "ELECTRIC_SCHEDULES_TOU-D.pdf"
SOURCES = {
    "tou-d-4-9pm": (TOU_D, 2, 3), "tou-d-5-8pm": (TOU_D, 4, 5), "tou-d-prime": (TOU_D, 6, 7),
    "tou-d-prime-cpp": (TOU_D, 6, 12), "deed-restricted": (TOU_D, 2, 2), "fera": (TOU_D, 13, 13),
}
OTHER_SOURCES = {
    "d": ("ELECTRIC_SCHEDULES_D.pdf", 2, 7, "91130-E", "91133-E"),
    "care": ("ELECTRIC_SCHEDULES_D-CARE.pdf", 1, 1, "91322-E", "91322-E"),
    "cca-crs": ("ELECTRIC_SCHEDULES_CCA-CRS.pdf", 3, 10, "74851-E", "91316-E"),
    "da-crs": ("ELECTRIC_SCHEDULES_DA-CRS.pdf", 3, 10, "74861-E", "91334-E"),
    "medical-baseline": ("ELECTRIC_SCHEDULES_MB-E.pdf", 1, 1, "91346-E", "91346-E"),
}
FILING_ID = {"2026-06-01": "SCE-AL-5829-E", "2026-06-25": "SCE-AL-5837-E"}

CELLS = A.CELLS
COMMON = {"transmission": "0.02481", "nsgc": "0.00829", "ndc": "0.00003", "pppc": "0.00171",
          "cia": "0.00000", "wfc": "0.00591", "dwra": "0.00000", "pucrf": "0.00100",
          "fixed-recovery-charge": "0.00619", "mcam": "0.00223", "gen-dwrec": "0.00000",
          "base-services-charge": "0.794", "climate-credit": "-36.00"}


def tou(sched, gen, dist, extra):
    p = f"sce:{sched}-{PRIOR}-price-"
    out = {p + k: v for k, v in COMMON.items()}
    out.update({p + f"gen-{c}": v for c, v in zip(CELLS, gen)})
    out.update({p + f"dist-{c}": v for c, v in zip(CELLS, dist)})
    out.update({(p + k if not k.startswith("sce:") else k): v for k, v in extra.items()})
    return out


def crs(slug):
    """The June 25 Domestic row repeats the 2026-03-20 values."""
    vint = {"2001": "0.00009", "2004": "0.00009", "2009": "0.01742", "2010": "0.02077", "2011": "0.02508",
            "2012": "0.02563", "2013": "0.02608", "2014": "0.02443", "2015": "0.02367", "2016": "0.02321",
            "2017": "0.02322", "2018": "0.02311", "2019": "0.02141", "2020": "0.02015", "2021": "0.02007",
            "2022": "0.02419", "2023": "0.02624", "2024": "0.01175", "2025": "-0.00644", "2026": "-0.00644"}
    out = {f"sce:{slug}-price-wfc-{PRIOR}": "0.00591", f"sce:{slug}-price-ctc-{PRIOR}": "0.00014",
           f"sce:{slug}-price-frc-{PRIOR}": "0.00619"}
    out.update({f"sce:{slug}-price-pcia-v{y}-{PRIOR}": v for y, v in vint.items()})
    return out


PRICES = {
    "tou-d-4-9pm": tou("tou-d-4-9pm",  # Sheets 2 and 3 (91196-E, 91197-E)
                       ["0.25321", "0.13326", "0.07396", "0.17956", "0.10245", "0.08452"],
                       ["0.28981", "0.28981", "0.23095", "0.28981", "0.23095", "0.20978"],
                       {"baseline-credit": "-0.10099", "baseline-credit-nonbaseline": "0.00000"}),
    "tou-d-5-8pm": tou("tou-d-5-8pm",  # Sheets 4 and 5 (91198-E, 91199-E)
                       ["0.41155", "0.21138", "0.06298", "0.27579", "0.09965", "0.07016"],
                       ["0.29049", "0.29049", "0.24056", "0.29049", "0.24056", "0.21352"],
                       {"baseline-credit": "-0.10099", "baseline-credit-nonbaseline": "0.00000"}),
    "tou-d-prime": tou("tou-d-prime",  # Sheets 6 and 7 (91200-E; 91201-E, then 91355-E)
                       ["0.29667", "0.10558", "0.07049", "0.26489", "0.05958", "0.05958"],
                       ["0.25449", "0.25449", "0.15474", "0.25982", "0.14500", "0.14500"],
                       {f"sce:price-ev-meter-credit-{PRIOR}": "-0.461",
                        f"sce:price-ev-submeter-credit-{PRIOR}": "-0.152"}),
    "d": {  # Schedule D Sheets 2 and 3 (91130-E, 91131-E)
        f"sce:price-generation-{PRIOR}": "0.11761", f"sce:price-generation-dwrec-{PRIOR}": "0.00000",
        f"sce:price-distribution-{PRIOR}": "0.18015",
        f"sce:price-cia-baseline-{PRIOR}": "-0.03737", f"sce:price-cia-nonbaseline-{PRIOR}": "0.06362",
        **{f"sce:d-{PRIOR}-price-{k}": v for k, v in COMMON.items() if k not in ("cia", "gen-dwrec")},
    },
    "tou-d-prime-cpp": {f"sce:tou-d-prime-cpp-price-event-charge-{PRIOR}": "0.80000",
                        f"sce:tou-d-prime-cpp-price-non-event-credit-{PRIOR}": "-0.15170",
                        f"sce:tou-d-prime-cpp-price-max-credit-{PRIOR}": "-0.58794"},
    "deed-restricted": {f"sce:deed-restricted-price-bsc-discount-{PRIOR}": "-0.327"},
    "fera": {f"sce:fera-price-bsc-surcharge-exemption-{PRIOR}": "-0.069",
             f"sce:fera-price-bsc-credit-adjustment-{PRIOR}": "-0.197"},
    "care": {f"sce:care-price-wfc-exemption-{PRIOR}": "-0.00591",
             f"sce:care-price-frc-exemption-{PRIOR}": "-0.00619",
             f"sce:care-price-bsc-surcharge-exemption-{PRIOR}": "-0.069",
             f"sce:care-price-bsc-discount-{PRIOR}": "-0.168"},
    "cca-crs": crs("cca-crs"),
    "da-crs": crs("da-crs"),
    "medical-baseline": {f"sce:medical-baseline-price-wfc-exemption-{MB_OLD}": "-0.00591"},
}


# --- derivation ---------------------------------------------------------------

def rescope(doc, slug, old, new):
    defined: set[str] = set()
    A.walk(doc, lambda d: defined.add(d["@id"]) if "@id" in d and len(d) > 1 else None)
    top = {f"sce:{slug}", "org:utility-sce", "org:utility-sce-identity", "org:utility-sce-name",
           "org:utility-sce-eia"}
    m = {}
    for i in defined:
        if old in i:
            m[i] = i.replace(old, new)
        elif i.startswith(f"sce:{slug}-") and i not in top:
            m[i] = f"sce:{slug}-{new}-" + i[len(f"sce:{slug}-"):]
        elif i in A.UNSCOPED.get(slug, ()):
            m[i] = f"sce:{slug}-{new}-" + i[len("sce:"):]
    return m


def set_strings(doc, old, new):
    def f(d):
        for k, v in list(d.items()):
            if not isinstance(v, str):
                continue
            if k in ("urpx:version", "urpx:modifierVersionNumber") and v == old:
                d[k] = new
            elif k == "urpx:effectiveDateTime":
                d[k] = f"{new}T00:00:00"
            elif k == "urpx:startDate":
                d[k] = new
            elif k == "urpx:dateRetrieved":
                d[k] = RETRIEVED
            elif k == "urpx:evaluatedOn":
                d[k] = "2026-10-06T00:00:00"
    A.walk({k: v for k, v in doc.items() if k != "@context"}, f)


def set_expiration(doc, date: str) -> None:
    ctx = doc["@context"]
    if "urpx:expirationDateTime" not in ctx:
        out = {}
        for k, v in ctx.items():
            out[k] = v
            if k == "urpx:effectiveDateTime":
                out["urpx:expirationDateTime"] = {"@type": "xsd:dateTime"}
        doc["@context"] = out
    parent = doc["urpx:hasRatePlan"] if "urpx:hasRatePlan" in doc else doc["urpx:hasRatePlanModifier"]
    key = "urpx:hasRatePlanVersion" if "urpx:hasRatePlan" in doc else "urpx:hasRatePlanModifierVersion"
    v = parent[key]
    new_v = {}
    for k, x in v.items():
        if k == "urpx:expirationDateTime":
            continue
        new_v[k] = x
        if k == "urpx:effectiveDateTime":
            new_v["urpx:expirationDateTime"] = f"{date}T00:00:00"
    parent[key] = new_v


def path(slug, date):
    kind = "rate-plan" if slug in A.BASES else "rate-plan-modifier"
    return SCE / slug / "versions" / date / f"{kind}_sce_{slug}_{date}.jsonld"


def source_of(slug):
    if slug in SOURCES:
        f, p0, p1 = SOURCES[slug]
        return f, p0, p1, TOU_D_LEAF[p0], TOU_D_LEAF[p1]
    return OTHER_SOURCES[slug]


def derive(slug, old, new, expires=OCT):
    doc = copy.deepcopy(A.load(path(slug, old)))
    m = rescope(doc, slug, old, new)
    A.apply_map(doc, m)
    set_strings(doc, old, new)
    rows = A.set_prices(doc, PRICES[slug], m, slug)
    fname, p0, p1, l0, l1 = source_of(slug)
    dsr = A.version_node(doc)["urpx:hasDataSourceReference"]
    assert dsr["urpx:fileName"] == fname, (slug, dsr["urpx:fileName"])
    dsr.update({"urpx:pageStart": p0, "urpx:pageEnd": p1, "urpx:leafStart": l0, "urpx:leafEnd": l1})
    for i, fields in prose(slug, new).items():
        node = A.find(doc, i)
        for k, v in fields.items():
            if k not in node:
                raise SystemExit(f"{slug}: {i} has no {k}")
            node[k] = v
    for i, k, a, b in edits(slug, new):
        node = A.find(doc, i)
        if node[k].count(a) != 1:
            raise SystemExit(f"{slug}: {i} {k}: {a!r} occurs {node[k].count(a)} times")
        node[k] = node[k].replace(a, b)
    if expires:
        set_expiration(doc, expires)
    else:
        A.version_node(doc).pop("urpx:expirationDateTime", None)
    A.dump(path(slug, new), doc)
    return rows


# --- prose ----------------------------------------------------------------------

def bsc_sentence():
    return ("Base Services Charge (BSC) of $0.794/meter/day per Decision 24-05-028, with a BSC Adjustment of "
            "$(0.327)/meter/day for customers in deed-restricted affordable housing, modeled as "
            "sce:deed-restricted. The CARE and FERA discounts of Special Conditions 7 and 8 (32.5 and 18.0 "
            "percent, with their BSC Surcharge exemption and BSC discount or credit adjustment) are modeled as "
            "sce:care and sce:fera. The California Climate Credit of $(36.00) per household is applied "
            "semi-annually per Special Condition 11.")


def ladder_sentence(sched, date):
    v = f"sce:{sched}-{date}"
    return (f"The Baseline Credit applies up to 100 percent of the Baseline Allocation: Tier 1 of {v}-tiers-baseline "
            "carries the Preliminary Statement Part H allocation for each Baseline Region and Basic or All-Electric "
            "Allocation in kWh per day, and the credit is priced on Tier 1 only. The Heat Pump Water Heater "
            f"allocation Part H adds is the modifier sce:{sched}-hpwh, a second document in this filing's directory.")


SHEET_NOTE = ("The rate sheets took effect June 1, 2026 (Advice 5829-E); the Special Condition sheets cited here are "
              "the June 25, 2026 reissue (Advice 5837-E), which renumbered them without changing a value modeled here.")


def option_evaluation(sched, opt, sheet, date):
    v = f"sce:{sched}-{date}"
    return (f"Three things published for {opt} are not represented in this filing. First, the {opt}-CPP variant "
            f"printed on the same Sheet {sheet}: a CPP Event Energy Charge of $0.80000 per kWh, a Summer On-Peak "
            "Energy Credit of $(0.15170) per kWh outside CPP Events, and a Summer Season Maximum Available Credit of "
            "$(0.58794) per kWh, none of them modeled. Second, the two pilot bill discounts of Special Conditions 13 "
            "and 14: the San Joaquin Valley Disadvantaged Communities Pilot Bill Protection Discount (20 percent in "
            "years 1 through 5, then 10 or 20 percent in years 6 through 10) and the 20 percent Transitional "
            "Community Solar Discount. Third, two things Preliminary Statement Part H states: how the kWh-per-day "
            f"allocations bounding Tier 1 of {v}-tiers-baseline scale to a billing period, and the Medical Baseline "
            "Allocation it adds to them. The Deed Restricted Base Services Charge adjustment of $(0.327) per meter "
            "per day and the CARE and FERA discount lines are cross-references to separate schedules, each filed as "
            "its own modifier in this corpus.")


def generation_summary(name, where):
    return (f"Generation subtotal for {name}: its Generation Prices and its DWR Energy Credit. {where} footnote 2: "
            "\"Generation = The Gen rates are applicable only to Bundled Service Customers.\" sce:da-crs and "
            "sce:cca-crs offset this subtotal for Direct Access and CCA Service customers.")


def prose(slug, d):
    hol = A.holidays  # Sheets 8 and 9 carry the TOU periods and holidays in the June 25 copy as on October 1
    P = {
        "tou-d-4-9pm": {
            f"sce:tou-d-4-9pm-{d}": {"urpx:description": (
                "Voluntary residential time-of-use option with summer on-peak 4:00 p.m.-9:00 p.m. weekdays. "
                "Assigned by CPUC mass-migration default rules to a portion of SCE's residential customer base by "
                "climate zone. " + bsc_sentence() + " " + ladder_sentence("tou-d-4-9pm", d) + " "
                + hol("4 p.m. to 9 p.m.") + " " + SHEET_NOTE)},
            f"sce:tou-d-4-9pm-{d}-summary-generation": {"urpx:name": generation_summary(
                "TOU-D-4-9PM", "Schedule TOU-D Sheet 2 (Cal. P.U.C. Sheet 91196-E)")},
            f"sce:cc-tou-d-4-9pm-{d}-evaluation": {"urpx:description": option_evaluation(
                "tou-d-4-9pm", "Option 4-9 PM", 2, d)},
        },
        "tou-d-5-8pm": {
            f"sce:tou-d-5-8pm-{d}": {"urpx:description": (
                "Voluntary residential time-of-use option with summer on-peak 5:00 p.m.-8:00 p.m. weekdays. "
                "Alternate CPUC mass-migration default. " + bsc_sentence() + " "
                + ladder_sentence("tou-d-5-8pm", d) + " " + hol("5 p.m. to 8 p.m.") + " " + SHEET_NOTE)},
            f"sce:tou-d-5-8pm-{d}-summary-generation": {"urpx:name": generation_summary(
                "TOU-D-5-8PM", "Schedule TOU-D Sheet 4 (Cal. P.U.C. Sheet 91198-E)")},
            f"sce:cc-tou-d-5-8pm-{d}-evaluation": {"urpx:description": option_evaluation(
                "tou-d-5-8pm", "Option 5-8 PM", 4, d)},
        },
        "tou-d-prime": {
            f"sce:tou-d-prime-{d}": {"urpx:description": (
                "Voluntary residential time-of-use option with summer on-peak 4:00 p.m.-9:00 p.m. weekdays, the "
                "windows of Option 4-9 PM (Sheet 8), with no Baseline Credit. Special Condition 4 (Sheet 12) requires "
                "a Customer newly requesting Option PRIME to attest to an electric vehicle, on-site behind-the-meter "
                "energy storage, or an electric heat pump for water or space heating. Separately metered electric "
                "vehicle load is eligible for Option PRIME with an EV Meter Credit of $(0.461)/meter/day (Special "
                "Condition 5); a customer using an EV submeter receives an EV Submeter Credit of $(0.152)/meter/day "
                "(Special Condition 17, Sheet 19). " + bsc_sentence() + " The Medical Baseline Credit line at 100.00 "
                "percent cross-references Schedule MB-E. " + hol("4 p.m. to 9 p.m.") + " " + SHEET_NOTE)},
            f"sce:tou-d-prime-{d}-summary-generation": {"urpx:name": generation_summary(
                "TOU-D-PRIME", "Schedule TOU-D Sheet 6 (Cal. P.U.C. Sheet 91200-E)")},
            f"sce:cc-tou-d-prime-{d}-evaluation": {"urpx:description": (
                "Two conditional credits on Sheet 6 are carried here without the conditions that gate them: the EV "
                "Meter Credit (Separately Metered EV Option) at $(0.461) per meter per day, which Special Condition 5 "
                "limits to a customer with a separate meter provided by SCE exclusively for charging electric "
                "vehicles, and the EV Submeter Credit at $(0.152) per meter per day, which Special Condition 17 "
                "limits to a customer whose submeter meets the Plug-In Electric Vehicle Submetering Protocol of "
                "Decision 22-08-024. This filing states both as unconditional, so a consumer computing a bill "
                "applies both to every Option PRIME customer. The two pilot bill discounts of Special Conditions 13 "
                "and 14 are also unrepresented: the San Joaquin Valley Disadvantaged Communities Pilot Bill "
                "Protection Discount (20 percent in years 1 through 5, then 10 or 20 percent in years 6 through 10) "
                "and the 20 percent Transitional Community Solar Discount. Option PRIME has no Baseline Credit line. "
                "The Option PRIME-CPP prices printed on the same sheet are the modifier sce:tou-d-prime-cpp; the "
                "Deed Restricted Base Services Charge adjustment of $(0.327) per meter per day, the CARE and FERA "
                "discount lines, and the Medical Baseline Credit line shown at 100.00 are cross-references to "
                "separate schedules each filed on its own.")},
        },
        "d": {
            f"sce:d-{d}": {"urpx:description": (
                "Tiered residential schedule (no time-of-use). Generation, distribution, and most flat-rate "
                "surcharges do not vary by tier or season. The two-tier structure (baseline / nonbaseline) is "
                "implemented via the Conservation Incentive Adjustment (CIA): customers receive a CIA credit of "
                "$-0.03737/kWh for usage at-or-below their daily baseline allocation, and pay a CIA charge of "
                "$+0.06362/kWh for usage above. The 10.099 cent swing matches the Baseline Credit of Schedule "
                "TOU-D's Options 4-9 PM and 5-8 PM. Baseline allocations vary by Baseline Region "
                "(5/6/8/9/10/13/14/15/16), season (Summer = June-September; Winter = October-May), and Basic or "
                "All-Electric service per Preliminary Statement Part H. Base Services Charge (BSC) of $0.794/meter/day "
                "per Decision 24-05-028, with a BSC Discount of $(0.327)/meter/day for customers in deed-restricted "
                "affordable housing, modeled as sce:deed-restricted. The CARE and FERA discounts of Special Condition "
                "4 (32.5 and 18.0 percent, with their BSC Surcharge exemption and BSC discount or credit adjustment) "
                "are modeled as sce:care and sce:fera.")},
            f"sce:d-{d}-summary-generation": {"urpx:name": generation_summary(
                "D", "Schedule D Sheet 2 (Cal. P.U.C. Sheet 91130-E)").replace("The Gen rates", "The Generation rates")},
        },
        "care": {
            f"sce:care-{d}": {"urpx:description": (
                "California Alternate Rates for Energy (CARE) program: an income-qualified bill discount applied as "
                "an overlay to an SCE residential base rate plan (Schedule D, TOU-D-4-9PM, TOU-D-5-8PM or "
                "TOU-D-PRIME). Schedule D-CARE Sheet 1 states the terms, restated in Schedule TOU-D Special Condition "
                "7 and Schedule D Special Condition 4. Eligibility: a CARE Household per Schedule D-CARE Special "
                "Condition 2. Modeled benefits: (1) the 32.5 percent bill discount on the pre-PUCRF, pre-tax "
                "subtotal, as a urpx:Price carrying urpx:multiplier -0.325 over the discountable urpx:PriceSummary of "
                "the base plan the customer takes; (2) exemption from the Wildfire Fund Non-Bypassable Charge, a "
                "$-0.00591/kWh credit; (3) exemption from the Fixed Recovery Charge, a $-0.00619/kWh credit; (4) "
                "exemption from the Base Services Charge Surcharge, a $-0.069/meter/day credit; and (5) the Base "
                "Services Charge Discount, a $-0.168/meter/day credit. Sheet 1 also exempts CARE customers from the "
                "CARE Surcharge of $0.209 per meter per day, which is not modeled.")},
            f"sce:care-pd-bsc-surcharge-exemption-{d}": {"urpx:name":
                "CARE BSC Surcharge Exemption (cancels the BSC Surcharge component of $0.069/meter/day from the base $0.794 BSC)"},
            f"sce:cc-care-{d}-evaluation": {"urpx:description": (
                "Sheet 1 of Schedule D-CARE states a 32.5 percent discount applied to a CARE customer's bill prior to "
                "the Public Utilities Commission Reimbursement Fee and any applicable user fees, taxes and late "
                "payment charges. This filing models it as a urpx:Price carrying urpx:multiplier -0.325 over the "
                "discountable subtotal of whichever SCE residential base plan the customer takes service under, "
                "naming the candidate subtotals of four schedules at every effective date, read disjunctively so "
                "that the one present in the consumer's graph applies. Each subtotal omits the Reimbursement Fee, the "
                "California Climate Credit, which Special Condition 12 applies after city and county utility users' "
                "taxes, and the Base Services Charge, which this filing adjusts through two per-meter-per-day "
                "credits. The four line items of the same Sheet 1 are carried alongside the percentage: the Wildfire "
                "Fund Non-Bypassable Charge exemption of $0.00591 per kWh, the Fixed Recovery Charge exemption of "
                "$0.00619 per kWh, the Base Services Charge Surcharge exemption of $0.069 per meter per day, and the "
                "Base Services Charge Discount of $(0.168) per meter per day. Three benefits of the schedule remain "
                "unrepresented, and they are why this claim is partial. Sheet 1 exempts CARE customers from the CARE "
                "Surcharge of $0.209 per meter per day, which no SCE residential rate sheet in this corpus itemizes. "
                "Special Condition 14 grants the San Joaquin Valley Disadvantaged Communities Pilot Bill Protection "
                "Discount, 20 percent in pilot years 1 through 5 and 10 or 20 percent in years 6 through 10, and "
                "Special Condition 15 a 20 percent Transitional Community Solar Discount; both are limited to pilot "
                "participants, and this filing carries no condition on pilot participation to gate them on. The "
                "California Climate Credit of Special Condition 12 is carried on the base rate plans this modifier "
                "overlays.")},
        },
        "fera": {
            f"sce:fera-{d}": {"urpx:description": (
                "Family Electric Rate Assistance (FERA) program: an income-qualified bill discount applied as an "
                "overlay to an SCE residential base rate plan. Schedule TOU-D Special Condition 8 (Sheet 13) states "
                "the terms, restated in Schedule D Special Condition 4 (Sheet 7), and defines the beneficiary by "
                "reference to Schedule D-FERA. Modeled benefits: (1) the 18.0 percent bill discount, as a urpx:Price "
                "carrying urpx:multiplier -0.18 over the discountable urpx:PriceSummary of the base plan the customer "
                "takes; (2) exemption from the Base Services Charge Surcharge, a $-0.069/meter/day credit; and (3) the "
                "Base Services Charge credit adjustment, a $-0.197/meter/day credit. FERA customers pay the Wildfire "
                "Fund Non-Bypassable Charge and the Fixed Recovery Charge at the standard rates.")},
            f"sce:fera-pd-bsc-surcharge-exemption-{d}": {"urpx:name":
                "FERA BSC Surcharge Exemption (cancels the BSC Surcharge component of $0.069/meter/day from the base $0.794 BSC)"},
        },
        "deed-restricted": {
            f"sce:deed-restricted-{d}": {"urpx:description": (
                "Base Services Charge (BSC) adjustment of $(0.327)/meter/day for SCE residential customers living in "
                "Deed Restricted Affordable Housing (DRAH), applied as an overlay to an SCE residential base rate "
                "plan (Schedule D, TOU-D-4-9PM, TOU-D-5-8PM or TOU-D-PRIME). It is the line \"BSC Adjustment - Deed "
                "Restricted\" on Schedule TOU-D Sheets 2 through 7 and \"BSC Discount - Deed Restricted\" on Schedule "
                "D Sheets 2 and 3. Schedule TOU-D Special Condition 10 (Sheet 15) and Schedule D Special Condition 4 "
                "(Sheet 6) also exempt DRAH customers from the Base Services Charge Surcharge of $0.069 per meter per "
                "day, which this filing does not carry, so the modeled BSC for a DRAH customer is $0.467 per meter "
                "per day where the schedules give $0.398. Eligibility is carried as the customer-state property "
                "housingDeedRestricted.")},
            f"sce:deed-restricted-{d}-er-eligible": {"urpx:description": (
                "Customer lives in Deed Restricted Affordable Housing. Schedule TOU-D Special Condition 10 (Sheet "
                "15): \"DRAH will be identified by the California Housing Partnership database. For properties with "
                "less than 80 percent of units identified as DRAH, Customers or tenants must contact SCE or visit "
                "www.sce.com and self-attest to living in a DRAH to qualify for the DRAH discount to reduce their "
                "Base Services Charge.\" Carried as the customer-state property housingDeedRestricted.")},
        },
        "tou-d-prime-cpp": {
            f"sce:tou-d-prime-cpp-{d}": {"urpx:description": (
                "Critical Peak Pricing (CPP) variant of Option PRIME, a customer-elected overlay of event charges and "
                "non-event credits on the base PRIME rates. Special Condition 3.b (Sheet 10): a minimum of 12 and a "
                "maximum of 15 CPP Events per calendar year, notified no later than 3:00 p.m. the day before. Special "
                "Condition 1 (Sheet 9): the CPP Event Energy Charge of +$0.80000/kWh applies from 4:00 p.m. to 9:00 "
                "p.m. on summer and winter days during a CPP Event, and the CPP Non-Event Energy Credit of "
                "-$0.15170/kWh from 4:00 p.m. to 9:00 p.m. on Summer Season days when no CPP Event is occurring. "
                "Special Condition 3.d (Sheet 11) limits CPP options to Bundled Service Customers and caps the sum of "
                "credits for CPP Customers grandfathered to continue dual participation with Schedule D-SDP; the cap "
                "is the Summer Season Maximum Available Credit of -$0.58794/kWh on Sheet 6. Special Condition 3.e's "
                "Bill Protection is not modeled. The CPP Event Energy Charge uses urpx:hasDynamicPricing with "
                "dynamicPricingType urpx:criticalPeakPricing, priceSource urpx:wholesaleMarketSource, updateFrequency "
                "urpx:eventTriggeredUpdates and a urpx:PriceUpdateRule describing the event trigger. The Non-Event "
                "Credit and the Maximum Available Credit carry ApplicabilityRule and CustomOperandNode gates: the "
                "Non-Event Credit applies when 'Is CPP Event Today' is false, and the Maximum Available Credit gates "
                "on the customer attribute 'Grandfathered D-SDP Dual Participation'.")},
            f"sce:tou-d-prime-cpp-{d}-er-eligible": {"urpx:description": (
                "Customer is on Option PRIME and has elected Option PRIME-CPP. Special Condition 3.d (Sheet 11): only "
                "Bundled Service Customers may be served under a CPP option; Direct Access and CCA Service Customers, "
                "and Customers served under Schedule S, are ineligible, and a CPP Customer may not dually enroll in "
                "any other demand response program.")},
            f"sce:tou-d-prime-cpp-{d}-pd-max-credit": {"urpx:name":
                "Maximum Available Credit: Summer Season cap on credits for CPP Customers grandfathered to continue dual participation with Schedule D-SDP"},
            f"sce:tou-d-prime-cpp-{d}-ledger-max-credit": {"urpx:name":
                "PRIME-CPP Maximum Available Credit (D-SDP dual-participation cap)"},
            f"sce:tou-d-prime-cpp-price-max-credit-{d}": {"urpx:name":
                "Summer Season Maximum Available Credit (D-SDP dual-participation cap)"},
            f"sce:tou-d-prime-cpp-{d}-ar-max-credit": {"urpx:name":
                "Applies in Summer Season; cap on credits when the customer is grandfathered into dual participation with Schedule D-SDP"},
            f"sce:tou-d-prime-cpp-{d}-pur-event-trigger": {"urpx:description": (
                "Special Condition 3.a (Sheet 10): SCE may call a CPP Event any day, based on a California "
                "Independent System Operator Alert, forecasts of SCE system emergencies, forecasts of extreme or "
                "unusual temperature conditions impacting system demand, or day-ahead load and/or price forecasts. "
                "Special Condition 3.b: a minimum of 12 and a maximum of 15 CPP Events per calendar year. Special "
                "Condition 3.c: SCE notifies Customers no later than 3:00 p.m. the day before. The CPP Event Energy "
                "Charge of +$0.80000/kWh applies from 4:00 p.m. to 9:00 p.m. during a CPP Event, in addition to the "
                "customer's Option PRIME rate for the period.")},
            f"sce:cc-tou-d-prime-cpp-{d}-evaluation": {"urpx:description": (
                "This filing carries the three prices Schedule TOU-D publishes for Option PRIME-CPP on Sheet 6 (a CPP "
                "Event Energy Charge of $0.80000 per kWh, a Summer On-Peak Energy Credit of $(0.15170) per kWh "
                "outside CPP Events, and a Summer Season Maximum Available Credit of $(0.58794) per kWh) and leaves "
                "several provisions of Special Conditions 1 and 3 unrepresented. No time window is modeled, so "
                "neither CPP price is limited to 4:00 p.m. to 9:00 p.m. The Maximum Available Credit is a cap on the "
                "sum of credits for a Customer grandfathered into dual participation with Schedule D-SDP and is "
                "carried as an additive credit. Special Condition 3.e, Bill Protection, credits a customer on a CPP "
                "option with the positive sum, if any, of CPP Event Energy Charges and Summer Non-Event Energy "
                "Credits over up to the first twelve months, and settles across a year of bills rather than within "
                "one. Special Condition 3 provides no CPP credit for exported generation; this filing's prices apply "
                "to a metered quantity that does not distinguish import from export. The event-calling criteria, "
                "the 12 to 15 events per calendar year and the notification duty of Special Conditions 3.a to 3.c "
                "and the eligibility limits of 3.d are recorded as deferrals in this filing's manifest.")},
        },
        "cca-crs": {
            f"sce:cca-crs-price-oat-generation-offset-{d}": {"urpx:name": (
                "Offset of the generation subtotal of whichever SCE residential base plan the customer is on. "
                "Schedule D Sheet 6 (91132-E) Special Condition 4.c and Schedule TOU-D Sheet 16 (91364-E) Special "
                "Condition 10.c: CCA Service Customers are billed for \"Delivery Service as displayed in this Rate "
                "Schedule and Generation charges determined by the CCA plus the applicable charges as shown in "
                "Schedule CCA-CRS\".")},
        },
        "da-crs": {
            f"sce:da-crs-price-oat-generation-offset-{d}": {"urpx:name": (
                "Offset of the generation subtotal of whichever SCE residential base plan the customer is on. "
                "Schedule D Sheet 6 (91132-E) Special Condition 4.b and Schedule TOU-D Sheet 15 (91363-E) Special "
                "Condition 10.b: Direct Access Customers \"purchase energy from an Energy Service Provider\" and are "
                "billed for Delivery Service plus \"the applicable charges as shown in Schedule DA-CRS\".")},
        },
        "medical-baseline": {
            f"sce:medical-baseline-{d}": {"urpx:description": (
                "Schedule MB-E Medical Baseline Exemption: applies to any SCE residential customer who qualifies for "
                "medical baseline allocation. Sheet 1 (Cal. P.U.C. Sheet 91346-E, effective June 25, 2026 under "
                "Advice 5837-E) reads: 'Customers receiving medical baseline allocation shall be billed in "
                "accordance with the terms and conditions of their Otherwise Applicable Tariff (OAT), except that "
                "the Wildfire Fund Non-Bypassable Charge (WFC) shall not apply, and the effective Minimum Charge will "
                "be $5.00, if applicable.' Modeled here as a single line-item credit cancelling the WFC "
                "($-0.00591/kWh, the base WFC throughout this version's window). The $5.00 effective Minimum Charge "
                "is not modeled. The Medical Baseline allocation itself (additional kWh in the baseline tier per "
                "Preliminary Statement Part H) is not modeled. Eligibility: customer's `Program Enrollment` = "
                "`Medical Baseline`. applicableToRatePlan: 4 SCE residential bases (Schedule D, TOU-D-4-9PM, "
                "TOU-D-5-8PM, TOU-D-PRIME). Benefits stack independently with CARE or FERA.")},
            f"sce:cc-medical-baseline-{d}-evaluation": {"urpx:description": (
                "Schedule MB-E is a single sheet with a one-sentence Rates section, and it states two effects: the "
                "Wildfire Fund Non-Bypassable Charge shall not apply, and the effective Minimum Charge will be $5.00, "
                "if applicable. This filing models the first as a credit of $(0.00591) per kWh cancelling the base "
                "charge, and does not model the second. The $5.00 Minimum Charge is a floor on the bill rather than "
                "a per-unit price, and the sheet states no unit or period for it; no active SCE residential base "
                "sheet in June 2026 carries a residential Minimum Charge for it to replace. The Applicability "
                "sentence, which extends the schedule to all customers receiving a medical baseline allocation, "
                "also points at a benefit this filing does not carry: the additional baseline allocation itself, "
                "whose kilowatt-hour quantities live in Preliminary Statement Part H rather than on this sheet.")},
        },
    }
    return P.get(slug, {})


def edits(slug, d):
    if slug == "d":
        e = f"sce:cc-d-{d}-evaluation"
        return [
            (e, "urpx:description", " Both sheets are new here: the superseded 2025-11-15 source for this Schedule is a rate-table archive that mentions neither program.", ""),
            (e, "urpx:description", "sum to the $0.18482 per kWh", "sum to the $0.18453 per kWh"),
            (e, "urpx:description", "the $0.28590 printed", "the $0.28552 printed"),
            (e, "urpx:description", "Deed Restricted BSC Discount of $(0.332)", "Deed Restricted BSC Discount of $(0.327)"),
        ]
    if slug == "cca-crs":
        return []
    if slug == "da-crs":
        return [(f"sce:da-crs-{d}", "urpx:description", "TOU-D Sheet 20 SC 11 / Schedule D Sheet 6 SC 4",
                 "TOU-D Sheet 15 SC 10 / Schedule D Sheet 6 SC 4"),
                (f"sce:da-crs-{d}", "urpx:description", "(modeled at ca/iou/sce/cca-crs/)", "(sce:cca-crs)")]
    return []


# --- manifests --------------------------------------------------------------------

TOU_D_JUNE = """The 2026-09-23 copy of Schedule TOU-D holds Advice 5829-E's rate sheets, Sheets
2 to 6 (91196-E to 91200-E), effective June 1, 2026, and Advice 5837-E's
reissue of every other sheet (91354-E, 91355-E to 91367-E), effective June 25,
2026. Advice 5829-E's own copies of the sheets the June 25 reissue cancelled
(Sheet 7, 91201-E; Sheet 18, 91202-E, the CARE and FERA Special Conditions;
Sheet 20, 91203-E, the DRAH terms) print the same values as their June 25
successors, so the values modeled here held from June 1 to September 30, 2026.
Advice 5837-E renumbered the Special Conditions: TOU periods, holidays and
seasons in Special Condition 1 (Sheets 8 and 9); Critical Peak Pricing in
Special Condition 3 (Sheets 10 and 11); PRIME eligibility in Special
Conditions 4 and 5 (Sheet 12); Change of Rate Schedule, CARE and FERA in
Special Conditions 6 to 8 (Sheet 13); the Arrearage Management Plan in Special
Condition 9 (Sheet 14); Billing Calculation, with the DRAH terms, in Special
Condition 10 (Sheets 15 and 16); the California Climate Credit in Special
Condition 11 (Sheet 16); the SJV Pilot and Transitional Community Solar
discounts in Special Conditions 13 and 14 (Sheets 17 and 18); EV Submetering
in Special Condition 17 (Sheet 19). The TOU periods, holidays and seasons are
those of the 2026-03-20 version."""

ADVICE = """Advice letters. ELECTRIC_5829-E.pdf (sha256
a5dc33e4ccd6b1dcf2d82bf6b33867ce1cf2d97f19d897ba93c8d9796cc93733) and
ELECTRIC_5837-E.pdf (sha256
44858dad74d4b648cbc31bf4a42590fd0e9063e7f734b94855375f779390ad6b), retrieved
2026-10-06 from SCE's Approved Electric advice letter folder
(https://edisonintl.sharepoint.com/teams/Public/TM2/Shared%20Documents/Public/Regulatory/Filings-Advice%20Letters/Approved/Electric/),
state their sheets' effective dates (June 1, 2026 and June 25, 2026). They are
cited, not vendored."""

TRUNCATED = """Source bytes. This is data/documents/sce/{name} as retrieved 2026-09-23 by
dev/fetch_tariff_documents.py. The unwrapper then in use cut the multipart
part at its last %%EOF and dropped the end-of-line that closes it, and SCE
reissued the document effective 2026-10-01, so the part as served cannot be
fetched again; the committed file and the sha256 above are those bytes, one
end-of-line short of the response."""

EXACT = """Source bytes. This is data/documents/sce/{name} as retrieved 2026-09-23, its
final end-of-line restored on 2026-10-06 from a fetch of the unchanged
document by dev/fetch_tariff_documents.py, so the committed file is the
response's multipart part body byte for byte."""


def june_notes(slug, d):
    if slug in A.TOU_D_FAMILY:
        n = [TOU_D_JUNE]
    elif slug == "d":
        n = ["""Advice 5829-E reissued Schedule D Sheets 2, 3, 6 and 7 (91130-E to 91133-E)
effective June 1, 2026; Sheets 1, 4, 5, 8 and 9 are unchanged since
November 15, 2025."""]
    elif slug == "care":
        n = ["""Schedule D-CARE as of 2026-09-23: Sheet 1 (91322-E, Advice 5837-E) effective
June 25, 2026, which cancels 91134-E (Advice 5829-E) effective June 1, 2026;
both print the CARE Surcharge at $0.209, the WFC at $0.00591, the FRC at
$0.00619, the BSC Surcharge at $0.069 and the BSC Discount at $(0.168).
Sheet 2 (91082-E, Advice 5813-E, the Special Condition 2 income limits)
effective June 1, 2026; Sheet 4 (91323-E) effective June 25, 2026; Sheets 3,
5 and 6 unchanged."""]
    elif slug in ("cca-crs", "da-crs"):
        n = ["""Advice 5837-E reissued Sheets 4 to 10 effective June 25, 2026. The Domestic
row carries the same 23 values as the 2026-03-20 version; other rate groups
moved."""]
    else:
        n = ["""Advice 5837-E reissued Schedule MB-E Sheet 1 (91346-E) effective June 25,
2026, adding "if applicable" to the $5.00 effective Minimum Charge; the WFC
exemption is unchanged."""]
    n.append(f"Supersession. This version begins at the effective date of the sheet that cancels the "
             f"{'2025-10-01' if slug == 'medical-baseline' else PRIOR} version's rate sheet and "
             + (f"ends at {OCT}, when Advice 5897-E's sheets cancel its own." if slug != "medical-baseline"
                else "is open."))
    return n


def write_manifest(slug, d, rows, old_date, exact):
    old = A.load_toml(SCE / slug / "versions" / old_date / "tariff.toml")
    pdf = SCE / slug / "versions" / d / f"sce_{slug}_{d}.pdf"
    url = old["source"]["base"]["url"] if "base" in old["source"] else old["source"]["url"]
    fid = FILING_ID[d]
    name = source_of(slug)[0]
    parts = [(EXACT if exact else TRUNCATED).format(name=name)] + june_notes(slug, d)
    if slug != "medical-baseline" and slug not in ("cca-crs", "da-crs"):
        parts.append(ADVICE)
    parts.append(f"Price changes from the {old_date} version, $ (per kWh unless a per-day\ncharge):\n"
                 + (A.price_lines(rows).replace(f"-{old_date}", "") or " none"))
    notes = "\n\n".join(A.wrap(p) if not p.startswith("Price changes") else p for p in parts)
    defs = DEFERRALS[slug](d) if callable(DEFERRALS.get(slug)) else DEFERRALS[slug]
    mods = old["modeling"].get("applicable_modifiers")
    lines = [
        "# Identity --------------------------------------------------------------------",
        'utility = "sce"', f'schedule = "{slug}"', f'effective_date = "{d}"', "",
        "# Source ----------------------------------------------------------------------",
        "[source]", f'url = "{url}"', f'sha256 = "{A.sha(pdf)}"', f'retrieved_on = "{RETRIEVED}"',
        'media_type = "application/pdf"', 'filing_type = "advice-letter"', f'filing_id = "{fid}"', "",
        "# Regulatory ------------------------------------------------------------------",
        "[regulator]", 'authority = "puc"', f'docket = "Advice {fid[7:]}"', "",
        "# Extraction ------------------------------------------------------------------",
        "[extraction]", 'tool = "manual"', 'extracted_on = "2026-10-06"', 'notes = """', notes, '"""', "",
        "# Validation ------------------------------------------------------------------",
        "[validation]", "shacl_passed = true", 'validator = "clj-shacl + clj-urpx (URPX v0.5.1)"',
        'validated_on = "2026-10-06"', "",
        "# Modeling -------------------------------------------------------------------",
        "[modeling]", "complete = false", "deferrals = [", *[" " + A.toml_str(x) + "," for x in defs], "]",
    ]
    if mods is not None:
        lines += ["applicable_modifiers = [", *[f' "{m}",' for m in mods], "]"]
    lines += ["", "# Review ----------------------------------------------------------------------",
              "[review]", 'status = "draft"',
              "notes = " + A.toml_str(f"Derived from the {old_date} version by dev/author_sce_2026_06.py: every "
                                      "Price reconciled to the June 2026 sheets, prose and citations rewritten "
                                      "for them. See [extraction] notes."), ""]
    text = "\n".join(lines)
    A.load_toml_text(text)
    (SCE / slug / "versions" / d / "tariff.toml").write_text(text, encoding="utf-8")


# --- deferrals --------------------------------------------------------------------

def holiday_deferral(sched, d):
    return A.holiday_deferral(sched).replace(f"-{A.NEW}-", f"-{d}-")


SJV = A.SJV.replace("(Special Condition 12, Sheets 17 and 18, where the continuation is headed 13)",
                    "(Special Condition 13, Sheets 17 and 18)").replace("Special Condition 12.", "Special Condition 13.")
TCS = A.TCS.replace("Same pilot-participation gate as Special Condition 12.",
                    "Same pilot-participation gate as Special Condition 13.")
CLIMATE = A.CLIMATE.replace("(Sheet 16, Special Condition 10)", "(Sheet 16, Special Condition 11)")
CLIMATE_MONTHS = A.CLIMATE_MONTHS.replace("Special Condition 10 (Sheet 16)", "Special Condition 11 (Sheet 16)")
CHANGE = A.CHANGE.replace("Special Condition 5, Change of Rate Schedule", "Special Condition 6, Change of Rate Schedule")
AMP = A.AMP.replace("Special Condition 8, Arrearage", "Special Condition 9, Arrearage")
BSC_SPLIT = ("Base Services Charge component split ({sheet}): the $0.794 per meter per day total is carried as one "
             "Price, but the sheet also prints its Distribution part of $0.429, itself a BSC Distribution Charge of "
             "$0.360 and a BSC Surcharge of $0.069, and a Public Purpose Programs part of $0.365. The $0.069 "
             "surcharge is the quantity CARE, FERA and DRAH customers are exempt from; sce/care and sce/fera price "
             "that exemption as a separate credit and sce/deed-restricted does not. Expressible now, purely "
             "additional PriceDefinitions summing to the same $0.794.")


def cpp_deferral(opt, sheet):
    return (f"{opt}-CPP, printed on this filing's own Sheet {sheet}: CPP Event Energy Charge $0.80000/kWh, Summer "
            "On-Peak Energy Credit $(0.15170)/kWh outside CPP Events, and Summer Season Maximum Available Credit "
            "$(0.58794)/kWh, with the CPP periods defined in Special Condition 1 (Sheet 9) and the program in "
            "Special Condition 3 (Sheets 10 and 11). Work, not a blocker: sce/tou-d-prime-cpp ships the same three "
            "figures as a urpx:RatePlanModifier, so what is missing is a sibling filing listed in "
            "applicable_modifiers, not vocabulary.")


def option_deferrals(sched, opt, sheet, delivery):
    return lambda d: [cpp_deferral(opt, sheet), SJV, TCS, CLIMATE, holiday_deferral(sched, d),
                      BSC_SPLIT.format(sheet=f"Sheet {delivery}"), CHANGE, AMP]


def prime_deferrals(d):
    return [
        holiday_deferral("tou-d-prime", d),
        ("Special Condition 5 (Sheet 12) limits the EV Meter Credit of $(0.461) per meter per day to \"customers with "
         "a separate meter provided by SCE exclusively for the charging of Electric Vehicles, as defined in Rule "
         "1\", and Special Condition 17 (Sheet 19) limits the EV Submeter Credit of $(0.152) per meter per day to a "
         "customer whose EV submeter meets the Plug-In Electric Vehicle Submetering Protocol of Decision 22-08-024. "
         "Both are modeled as unconditional PriceDefinitions, so a consumer gives every Option PRIME customer both "
         "credits. v0.5.1 supplies the vocabulary: PriceDefinition and Price both carry urpx:hasApplicabilityRule, "
         "and ApplicabilityRule carries urpx:hasConditionExpression with a CustomOperandNode for the metering "
         "arrangement. Not built."),
        SJV, TCS,
        (f"urpx:PriceSummary sce:tou-d-prime-{d}-summary-discountable, the subtotal that sce/care and sce/fera "
         "discount against, names 24 Prices in two different denominations: 22 in $/kWh, and two in $/Meter/Day "
         f"(sce:price-ev-meter-credit-{d} at $(0.461) and sce:price-ev-submeter-credit-{d} at $(0.152), both per "
         "Sheets 6 and 7). A sum over the urpx:unitPrice values of its members adds dollars per day to dollars per "
         "kWh, so the CARE 32.5 percent of Special Condition 7 and the FERA 18.0 percent of Special Condition 8 are "
         "percentages of a mixed-unit figure. Split it into two unit-homogeneous summaries with one modifier Price "
         "over each."),
        CLIMATE, CLIMATE_MONTHS,
        ("Special Condition 4, PRIME Eligibility Requirements (Sheet 12), is modeled inaccurately. Verbatim: "
         "\"Beginning May 1, 2019, all Customers newly requesting to take service under Option PRIME or Option "
         "PRIME-CPP effective March 20, 2020, must attest to having one or more of the following technologies to "
         "be eligible for service on Option PRIME or Option PRIME-CPP: (1) Electric Vehicle; (2) On-site "
         "behind-the-meter (BTM) energy storage system; (3) Electric heat pump system for water; and/or (4) "
         "Electric heat pump system for space heating\". The model's four-leaf OR is storageDER, evChargingDER, "
         "airSourceHeatPump and a CustomOperandNode \"Program Enrollment\" = \"Net Billing Tariff (NBT)\": the "
         "heat-pump-water-heater path is absent and the NBT leaf is in no Special Condition."),
        CHANGE, AMP,
    ]


DEFERRALS = {
    "tou-d-4-9pm": option_deferrals("tou-d-4-9pm", "Option 4-9 PM", 2, 3),
    "tou-d-5-8pm": option_deferrals("tou-d-5-8pm", "Option 5-8 PM", 4, 5),
    "tou-d-prime": prime_deferrals,
}


def _swap(texts, pairs):
    out = []
    for t in texts:
        for a, b in pairs:
            t = t.replace(a, b)
        out.append(t)
    return out


def from_october(slug, pairs):
    """The 2026-10-01 deferrals restated for June, by exact substitutions that must each apply."""
    def f(d):
        src = A.DEFERRALS[slug]
        joined = "\n".join(src)
        for a, _ in pairs:
            if a not in joined:
                raise SystemExit(f"{slug}: {a!r} is in no 2026-10-01 deferral")
        return _swap(src, pairs + [(f"-{A.NEW}", f"-{d}")])
    return f


DEFERRALS["d"] = from_october("d", [
    ("Cal. P.U.C. Sheet 91561-E", "Cal. P.U.C. Sheet 91133-E"),
    ("prices $0.19011 per kWh at or below the allocation and $0.28112 above it",
     "prices $0.18453 per kWh at or below the allocation and $0.28552 above it"),
    ("Distribution part of $0.491, itself a BSC Distribution Charge of $0.422 and a BSC Surcharge of $0.069, and a "
     "Public Purpose Programs part of $0.303", "Distribution part of $0.429, itself a BSC Distribution Charge of $0.360 "
     "and a BSC Surcharge of $0.069, and a Public Purpose Programs part of $0.365"),
])
DEFERRALS["care"] = from_october("care", [
    ("(Sheet 1, RATES, Cal. P.U.C. Sheet 91562-E): CARE customers are exempt from the CARE Surcharge of $0.215",
     "(Sheet 1, RATES, Cal. P.U.C. Sheet 91322-E): CARE customers are exempt from the CARE Surcharge of $0.209"),
    ("the only per-meter-per-day PPPC on that sheet is the $0.303 component", "the only per-meter-per-day PPPC on "
     "that sheet is the $0.365 component"),
    ("decomposition of that $0.303", "decomposition of that $0.365"),
    ("Sheet 1 APPLICABILITY (Cal. P.U.C. Sheet 91562-E)", "Sheet 1 APPLICABILITY (Cal. P.U.C. Sheet 91322-E)"),
])
_care_oct = DEFERRALS["care"]
DEFERRALS["care"] = lambda d: [x for x in _care_oct(d) if not x.startswith("CARE exempted Public Purpose")]
DEFERRALS["fera"] = from_october("fera", [
    ("Schedule TOU-D Sheet 13 Special Condition 7, restated", "Schedule TOU-D Sheet 13 Special Condition 8, restated"),
    ("Special Condition 6 does carve it out for CARE", "Special Condition 7 does carve it out for CARE"),
    ("Special Condition 7 discounts \"their bill\"", "Special Condition 8 discounts \"their bill\""),
    ("Special Condition 7 (Sheet 13, Cal. P.U.C. Sheet 91701-E)", "Special Condition 8 (Sheet 13, Cal. P.U.C. Sheet 91361-E)"),
    ("Special Condition 7 defines the beneficiary", "Special Condition 8 defines the beneficiary"),
    ("Special Condition 8 Arrearage Management Plan (Sheet 14)", "Special Condition 9 Arrearage Management Plan (Sheet 14)"),
])
DEFERRALS["deed-restricted"] = from_october("deed-restricted", [
    ("Schedule TOU-D Sheet 15 Special Condition 9 (Cal. P.U.C. Sheet 91703-E) and Schedule D Sheet 6 Special Condition "
     "4 (91560-E)", "Schedule TOU-D Sheet 15 Special Condition 10 (Cal. P.U.C. Sheet 91363-E) and Schedule D Sheet 6 "
     "Special Condition 4 (91132-E)"),
    ("Base Services Charge Discount of $(0.328) per meter per day", "Base Services Charge Discount of $(0.327) per meter per day"),
    ("same two-clause form Special Conditions 6 and 7 use", "same two-clause form Special Conditions 7 and 8 use"),
    ("at $-0.328/meter/day (Sheets 2 to 7)", "at $-0.327/meter/day (Sheets 2 to 7)"),
    ("$0.466 where the schedule gives $0.397", "$0.467 where the schedule gives $0.398"),
    ("Schedule TOU-D Sheet 15 Special Condition 9, in this filing's own PDF", "Schedule TOU-D Sheet 15 Special "
     "Condition 10, in this filing's own PDF"),
    ("shape sce/care 2026-10-01 already ships", "shape sce/care 2026-06-01 already ships"),
])
DEFERRALS["tou-d-prime-cpp"] = lambda d: [
    ("CPP time windows are not modeled, so both CPP prices apply at every hour. Special Condition 1 (Sheet 9): \"CPP "
     "Event Energy Charge Periods: 4:00 p.m. to 9:00 p.m. summer and winter days during a CPP Event only. CPP "
     "Non-Event Energy Credit Periods: Summer Season days 4:00 p.m. to 9:00 p.m., when a CPP Event is not "
     "occurring.\" This filing carries no TOUSchedule, TOUPeriod or TimeBracket. Expressible at v0.5.1 with "
     "urpx:hasTOUSchedule on the modifier's BillingModel (precedent: smud:tou-pev-credit). Work, not a blocker."),
    ("Maximum Available Credit is carried as an additive credit of -0.58794 per kWh, but the schedule makes it a "
     "cap. Sheet 6 footnote: \"The Maximum Available Credit is the capped credit amount for CPP Customers dual "
     "participating in other demand response programs.\" Special Condition 3.d (Sheet 11): \"For CPP Customers "
     "grandfathered to continue to dually participate with Schedule D-SDP, the sum of credits provided by the dual "
     "participating demand response program of this Schedule will be capped.\" URPX v0.5.1 has no vocabulary for "
     "a bound on the sum of two credits. Stop publishing it as an additive Price."),
    A.DEFERRALS["tou-d-prime-cpp"][2],
    ("No CPP credit for exported generation is not modeled. Special Condition 3 (Sheet 10): \"No CPP credits will "
     "be provided for exported generation, i.e., energy produced and exported by the Customer's Generating "
     "Facility during CPP Non-Event Credit Periods.\" All three CPP prices share one direction-less MetricInput, "
     f"sce:tou-d-prime-cpp-{d}-mi-energy, so the credit is priced on imported and exported kWh alike. "
     "urpx:flowDirection on a MetricSpecification is the v0.5.1 route. Work, not a blocker."),
    A.DEFERRALS["tou-d-prime-cpp"][4].replace("Special Condition 3.e (Sheet 11)", "Special Condition 3.e (Sheet 11)"),
    ("Special Conditions 3.a to 3.c (Sheet 10) trigger and bound the CPP Event Energy Charge this filing prices at "
     "$0.80000/kWh, and none of it is in the model. Verbatim: \"SCE may, at its discretion, call a CPP Event any "
     "day.\" \"There will be a minimum of 12 CPP events and a maximum of 15 CPP Events per calendar year.\" \"SCE "
     "will begin to notify Customers no later than 3:00 p.m. the day before a CPP Event.\" DynamicPricingShape and "
     "PriceUpdateRuleShape are both sh:closed and neither admits an event count, a notice interval or a trigger "
     "criterion, so this is a blocked deferral rather than unbuilt work."),
    ("Special Condition 3.d's limits (Sheet 11: Bundled Service Customers only; Direct Access, CCA Service and "
     "Schedule S customers ineligible; no dual enrollment in other demand response programs) and the PRIME "
     "attestation of Special Condition 4 (Sheet 12) are availability terms the single EligibilityRule does not "
     "encode."),
    A.DEFERRALS["tou-d-prime-cpp"][7],
]


def crs_deferrals(slug):
    first, last = ("91310-E", "91316-E") if slug == "cca-crs" else ("91328-E", "91334-E")
    def f(d):
        out = []
        for x in A.load_toml(SCE / slug / "versions" / PRIOR / "tariff.toml")["modeling"]["deferrals"]:
            x = x.replace("(90845-E through 90851-E)", f"({first} through {last})")
            x = x.replace(f"sce:d-{PRIOR}-price-wfc", f"sce:d-2026-06-01-price-wfc")
            x = x.replace("Schedule D Sheet 3 (90842-E)", "Schedule D Sheet 3 (91131-E)")
            x = x.replace(f"sce:care-price-wfc-exemption-{PRIOR}", f"sce:care-price-wfc-exemption-2026-06-01")
            out.append(x)
        return out
    return f


DEFERRALS["cca-crs"] = crs_deferrals("cca-crs")
DEFERRALS["da-crs"] = crs_deferrals("da-crs")


def mb_deferrals(d):
    old = A.load_toml(SCE / "medical-baseline" / "versions" / MB_OLD / "tariff.toml")["modeling"]["deferrals"]
    first = ("Schedule MB-E Sheet 1 (Revised Cal. P.U.C. Sheet 91346-E) says only that \"the effective Minimum "
             "Charge will be $5.00, if applicable\", with no unit or period, and the model carries no Price for it. "
             "The June 2026 SCE base sheets carry no residential Minimum Charge for it to replace. A minimum charge "
             "is a floor on the bill, which URPX v0.5.1 has no way to state; urpx-org/urpx#76 proposes min and max "
             "value expressions.")
    second = ("The WFC exemption is transcribed as a fixed -$0.00591/kWh rather than expressed as a cancellation. "
              "It equals the base WFC throughout this version's window, but Schedule MB-E prices the removal of "
              "whatever the WFC currently is (\"the Wildfire Fund Non-Bypassable Charge (WFC) shall not apply\"), "
              "which URPX v0.5.1 states directly: a Price with multiplier -1 and basedOnPrice naming the base plan's "
              "WFC Price, composed one base at a time so each credit resolves against a single unambiguous basis.")
    assert len(old) == 2
    return [first, second]


DEFERRALS["medical-baseline"] = mb_deferrals


# --- run ----------------------------------------------------------------------------

def vendor(slug, d):
    name = source_of(slug)[0]
    body = (DOCS / name).read_bytes()
    if body[:5] != b"%PDF-":
        raise SystemExit(f"{name}: not a PDF")
    dst = SCE / slug / "versions" / d / f"sce_{slug}_{d}.pdf"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(body)
    if slug in ("tou-d-4-9pm", "tou-d-5-8pm"):
        ph = SCE / slug / "versions" / PRIOR / "sce_prelim-h_2024-08-15.pdf"
        (dst.parent / ph.name).write_bytes(ph.read_bytes())
    return body.endswith(b"%%EOF\n") or body.endswith(b"%%EOF\r\n")


def main() -> int:
    for slug, d in JUNE.items():
        exact = vendor(slug, d)
        rows = derive(slug, PRIOR, d)
        write_manifest(slug, d, rows, PRIOR, exact)
        print(f"{slug} {d}: {len(rows)} prices, {sum(1 for r in rows if r[1] != r[2])} moved")
    d = MB_NEW
    exact = vendor("medical-baseline", d)
    rows = derive("medical-baseline", MB_OLD, d, expires=None)
    write_manifest("medical-baseline", d, rows, MB_OLD, exact)
    p = path("medical-baseline", MB_OLD)
    doc = A.load(p)
    set_expiration(doc, MB_NEW)
    A.dump(p, doc)
    print(f"medical-baseline {d}: {len(rows)} prices")
    A.candidates()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
