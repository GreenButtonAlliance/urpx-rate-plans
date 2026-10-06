#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""One-off: copy the source PDFs into us/wa/pse/electricity/307/versions/<date>/ and
write each directory's tariff.toml.

Takes the repository root and a directory holding the PDFs as fetched, under
the publisher's filenames (elec_sch_307.pdf, elec_sch_111.pdf, ...) plus the
UTC docket document for the 24th Revision of Sheet 129-B as
utc_ue-250648_doc4.pdf. The URLs are in each tariff.toml's [source].

    python3 dev/author_pse_307_manifests.py . <download-dir>
"""
import hashlib
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from author_pse_307 import RIDERS, PSE, UTC129, RETRIEVED  # noqa: E402

REPO = Path(sys.argv[1])
SRC = Path(sys.argv[2])

ADVICE = {  # advice number in the footer of the sheet carrying the residential rate
    "95": "2025-32 (Sheet 95) and 2025-32 (Sheet 95-E.3)", "95A": "2026-15", "111": "2025-54", "120": "2026-05",
    "129D": None, "137": "2024-45", "140": "2026-16", "141A": "2025-57", "141CEI": "2025-03",
    "141COL": "2025-61", "141N": "2025-03", "141PFG": "2025-03", "141R": "2025-03", "141TEP": "2026-09",
    "141TEX": "2025-24", "141WFP": "2026-07", "142": "2026-10", "194": "2025-36",
}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


HOLIDAYS_NOTE = """
## Holidays

Sheet 307-B lists the eleven days the schedule treats as legal holidays and
states no rule for one falling on a weekend. Per LAYOUT.md section 4.4 the
approving state's law governs: RCW 1.16.050
(https://app.leg.wa.gov/RCW/default.aspx?cite=1.16.050), subsection (5):
"Whenever any state legal holiday: (a) Other than Sunday, falls upon a
Sunday, the following Monday is the legal holiday; or (b) Falls upon a
Saturday, the preceding Friday is the legal holiday." That is
urpx:nearestWeekdayObservance, carried on the five fixed-date holidays (New
Year's Day, Juneteenth, Independence Day, Veterans' Day, Christmas Day). The
four Monday holidays and Thanksgiving never fall on a weekend. Native
American Heritage Day is "The Friday immediately following the fourth
Thursday in November", which is not the fourth Friday when November 1 is a
Friday (2030, 2041), so it is carried as one dated urpx:Holiday per year
through 2040. Holidays move only the weekday Peak hours to Off-Peak; a
weekend is Off-Peak all day either way.

## Reading of sheet 307-A

Sheet 307-A prints the summer weekend and holiday row as "Off-Peak (12am-12pm)"
where the winter row reads "(12am-12am)". Read literally it leaves summer
weekend and holiday hours from noon to midnight with no price. The Summary
Sheet ("WEEKEND & HOLIDAYS* OFF-PEAK (12AM-12AM)" in both seasons) and
the sheet's own Off-Peak price, identical in every Off-Peak cell, support
12am-12am, which is what the model carries.
"""

STRUCTURE_NOTE = """
## Structure

Schedule 307 is a RatePlan, not a modifier on Schedule 7. Sheet 307-A prices
its own Basic Charge and a Time-of-Use Energy Charge, and the Summary Sheet
notes "Sch 307 Energy Charge replaces the Sch 7 Energy Charge"; TERMINATION
BY CUSTOMER reads "A Customer may change to Schedule 7", which is leaving one
schedule for another. Schedule 7 enters only through AVAILABILITY ("available
to a Customer eligible to receive Electric Service under Schedule 7") and
APPLICABILITY ("available on the terms and conditions set forth in Schedule
7"). The sheet 307-C ADJUSTMENTS sentence, "Rates in this Schedule are
subject to adjustment by such other schedules in this tariff as may apply",
is the sentence on Schedule 7 Sheet 7-A, differing only in capitalizing
"Schedule", so it states that the supplemental schedules apply to 307 as to 7;
it does not make 307 one of them.

The supplemental schedules each print a rate under a heading naming Schedules
7, 307, 317 and 327 (or 7, 307 and 327) and say the rate "shall be added to
the rate(s) shown on each schedule for electric service". Each is carried as
a Price on this plan, following the SDG&E TOU-DR1 precedent, which carries
Schedule EECC, DWR-BC and WF-NBC, separately published schedules that apply
to every customer on the plan, as PriceDefinitions on the base plan rather
than as RatePlanModifiers. Schedule 141PFG prints only a rate headed "THROUGH APRIL 30, 2025"; its
text sets its rates to zero from May 1, 2025, and zero is what is carried.
Schedule 141Z terminated September 30, 2023 and is not carried.
Modifiers in this corpus are reserved for what a
customer opts into or qualifies for (CARE, FERA, a CCA's PCIA); PSE's
analogue is Schedule 7BDR, listed in applicable_modifiers. Each source PDF is
committed here and its sha256 is in [source]; the PriceDefinition of each
supplemental schedule's rate carries a urpx:hasDataSourceReference naming the
publisher's filename and the sheet.
"""


def write(date, expires):
    d = REPO / f"us/wa/pse/electricity/307/versions/{date}"
    files = {}
    base_local = d / f"pse_307_{date}.pdf"
    shutil.copyfile(SRC / "elec_sch_307.pdf", base_local)
    lines = ["# Identity --------------------------------------------------------------------",
             'utility = "pse"', 'schedule = "307"', f'effective_date = "{date}"', "",
             "# Source ----------------------------------------------------------------------",
             "# One sub-table per committed PDF. Each rider PDF is the whole schedule as PSE",
             "# publishes it; the sheet carrying the Schedule 307 rate is named in the",
             "# PriceDefinition's urpx:hasDataSourceReference.",
             "[source]", 'landing_page = "https://www.pse.com/en/pages/rates/electric-tariffs-and-rules"', ""]

    def block(name, url, local, filing_id, filing_type="tariff-schedule"):
        lines.extend([f"  [source.{name}]", f"  url = {q(url)}", f'  sha256 = "{sha(local)}"',
                      f'  retrieved_on = "{RETRIEVED}"', '  media_type = "application/pdf"',
                      f'  filing_type = "{filing_type}"'])
        if filing_id:
            lines.append(f"  filing_id = {q(filing_id)}")
        lines.append("")

    block("base", PSE + "elec_sch_307.pdf", base_local, "PSE Advice No. 2025-39")
    seen = set()
    for key, sch, pdf, sheet, eff, name, val, *_ in RIDERS:
        if sch in seen:
            continue
        seen.add(sch)
        if sch == "129":
            if date == "2026-05-01":
                local = d / "pse_129_2025-10-01.pdf"
                shutil.copyfile(SRC / "utc_ue-250648_doc4.pdf", local)
                block("sch_129", UTC129, local, "PSE Advice No. 2025-34, Docket UE-250648", "advice-letter")
                # the sheet that ends this version
                local2 = d / "pse_129_2026-10-01.pdf"
                shutil.copyfile(SRC / "elec_sch_129.pdf", local2)
                lines.insert(len(lines) - 0, "  # 25th Revision of Sheet 129-B, effective 2026-10-01, cancels the 24th")
                lines.append("  # Revision carried above; it is what bounds this version's expiration.")
                block("sch_129_successor", PSE + "elec_sch_129.pdf", local2, "PSE Advice No. 2026-23")
            else:
                local = d / "pse_129_2026-10-01.pdf"
                shutil.copyfile(SRC / "elec_sch_129.pdf", local)
                block("sch_129", PSE + "elec_sch_129.pdf", local, "PSE Advice No. 2026-23")
            continue
        local = d / f"pse_{sch.lower()}_{eff}.pdf"
        shutil.copyfile(SRC / pdf, local)
        adv = ADVICE.get(sch)
        block(f"sch_{sch.lower()}", PSE + pdf, local, f"PSE Advice No. {adv}" if adv else None)

    notes = ("\nSheets read with pdftotext -layout; every value below was read off the sheet\n"
             "text and checked against the Summary Sheet (a derived document whose header\n"
             "gives the rate schedules precedence) as described in README.md.\n"
             + STRUCTURE_NOTE + HOLIDAYS_NOTE)
    if date == "2026-05-01":
        notes += """
## Dating

Dated 2026-05-01, the effective date of the newest sheets carried (95-G for
Schedule 95A, 120, 140-B, 141TEP-A and 142-H). Bounded at 2026-10-01 by the
25th Revision of Sheet 129-B, which cancels the 24th Revision carried here
(Schedule 129, $0.007550 per kWh). The 24th Revision is no longer on
pse.com; the copy committed here is PSE's filing in Docket UE-250648
(Advice No. 2025-34, received by the UTC August 27, 2025, approved by Order
01 served September 26, 2025).
"""
    else:
        notes += """
## Dating

Dated 2026-10-01, the effective date of the 25th Revision of Sheet 129-B, the
newest sheet carried. Every other residential rate is unchanged from the
2026-05-01 version.
"""
    lines += ["# Regulatory ------------------------------------------------------------------",
              "# Docket of the Schedule 307 sheets. Each rider sheet's footer names its own",
              "# advice number, and where it has one, its own docket.",
              "[regulator]", 'authority = "puc"', 'docket = "UE-250725"', "",
              "# Extraction ------------------------------------------------------------------",
              "[extraction]", 'tool = "pdftotext"', 'tool_version = "26.09.0"', f'extracted_on = "{RETRIEVED}"',
              'notes = """' + notes + '"""', "",
              "# Validation ------------------------------------------------------------------",
              "[validation]", "shacl_passed = true", 'validator = "pyshacl + clj-urpx (URPX v0.5.1)"',
              f'validated_on = "{RETRIEVED}"', "",
              "# Modeling --------------------------------------------------------------------",
              "[modeling]", "complete = false", "deferrals = ["]
    for x in DEFERRALS:
        lines.append(" " + q(x) + ",")
    lines += ["]", "applicable_modifiers = [", ' "7bdr",', "]", "",
              "# Review ----------------------------------------------------------------------",
              "[review]", 'status = "draft"', ""]
    (d / "tariff.toml").write_text("\n".join(lines))
    print("wrote", d / "tariff.toml")


DEFERRALS = [
    "Sheet 307-A prices the Basic Charge at \"$7.49 single phase or $17.99 three phase\". Only the single-phase $7.49 is carried, as a Price with no condition, so it applies to every customer and a three-phase customer's monthly charge is $10.50 low.",
    "Schedule 81 (Tax Adjustment) increases \"the rates and charges named in this tariff\" by the effect of a municipal tax that varies by jurisdiction, from 2.136 percent to 9.119 percent in the Sheet 81 tables. Not carried; the Summary Sheet also excludes it (\"Rates in this summary include the effect of all supplemental rate schedules except Schedule 81\"). A bill inside a taxing jurisdiction resolves low by that percentage of every charge.",
    "Sheet 307-B BILL PROTECTION: an annual bill credit, for low-income Customers selected for bill protection in the pilot that ended September 30, 2025, of Energy Charge costs more than 10 percent above what Schedule 7 would have charged. Not carried. It reaches only those pilot participants, and its value is a bill recomputed under Schedule 7, which no Price here can state.",
    "Exemptions in the supplemental schedules are not carried: neither Schedule 111 rate applies to a Customer taking optional Schedule 139 service or registered as a National Security Entity, and Schedule 141A does not apply to a Customer who took Schedule 139 service on or before that schedule's original effective date. Both rates are carried as Prices with no condition, so such a customer resolves $0.009637 per kWh low on Schedule 111 (whose net rate is a credit) and $0.002010 per kWh high on Schedule 141A.",
    "Native American Heritage Day is carried as dated urpx:Holiday entries for each year from this version's year through 2040. Sheet 307-B defines it as \"The Friday immediately following the fourth Thursday in November\", which a rule of the form \"Fourth Friday in November\" gets wrong in years when November 1 is a Friday, so no rule string is carried. Each year after 2040 needs a further dated entry.",
]

if __name__ == "__main__":
    for date, exp in (("2026-05-01", "2026-10-01"), ("2026-10-01", None)):
        write(date, exp)
