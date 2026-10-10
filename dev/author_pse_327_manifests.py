#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""One-off: copy the source PDFs into us/wa/pse/electricity/327/versions/<date>/ and
write each directory's tariff.toml.

Takes the repository root and a directory holding the PDFs as fetched, under
the publisher's filenames: elec_sch_327.pdf plus the supplemental schedules
dev/author_pse_307_manifests.py reads (elec_sch_111.pdf, ...,
utc_ue-250648_doc4.pdf). The URLs are in each tariff.toml's [source].

    python3 dev/author_pse_327_manifests.py . <download-dir>
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from author_pse_307 import PSE, RETRIEVED, RIDERS, UTC129  # noqa: E402
from author_pse_307_manifests import ADVICE, q, sha  # noqa: E402

REPO = Path(sys.argv[1])
SRC = Path(sys.argv[2])

STRUCTURE_NOTE = """
## Structure

Schedule 327 is a RatePlan, not a modifier on Schedule 7 or on Schedule 307.
Sheet 327-A prices its own Basic Charge ("Basic Charge: $7.49 single phase or
$17.99 three phase") and its own Time-of-Use Energy Charge, "an amount equal
to the sum of the Peak Energy Charge, Off-Peak Energy Charge, and Super
Off-Peak Energy Charge", and the Summary Sheet notes "Sch 327 Energy Charge
replaces the Sch 7 Energy Charge". TERMINATION BY CUSTOMER reads "A Customer
may change to Schedule 7", which is leaving one schedule for another. Schedule
7 enters only through AVAILABILITY and APPLICABILITY, in the words Schedule
307 uses. Schedule 307 is named on Schedule 327 only in the sheet 327-B BILL
PROTECTION paragraph, which lists 307, 317 and 327 as the schedules of the
ended pilot.

Super Off-Peak is not a fourth period on a Schedule 307 structure. Every
sheet 327-A price differs from the corresponding sheet 307-A price (Winter
Peak $0.503575 against $0.532445, Summer Peak $0.271839 against $0.335186,
Off-Peak $0.127088 Winter and $0.122055 Summer against $0.108197 in both
seasons), Summer Peak is 7am-10am and 5pm-8pm where Schedule 307's is 5pm-8pm,
and Off-Peak ends at 11pm. Each Schedule 327 customer is billed entirely under
sheet 327-A; no Schedule 307 price reaches the bill.

The sheet 327-C ADJUSTMENTS sentence is sheet 307-C's word for word. The
supplemental schedules each print a rate under a heading naming Schedules 7,
307, 317 and 327 (or 7, 307 and 327), the same rate Schedule 307 carries, and
each is carried as a Price on this plan as on Schedule 307. Schedule 141PFG
prints only a rate headed "THROUGH APRIL 30, 2025"; its text sets its rates
to zero from May 1, 2025, and zero is what is carried. Schedule 141Z
terminated September 30, 2023 and is not carried. Schedule 7BDR, available
to "Customers taking Electric Service on any of the following schedules: 7,
307, 317, and 327", is listed in applicable_modifiers. Each source PDF is
committed here and its sha256 is in [source]; the PriceDefinition of each
supplemental schedule's rate carries a urpx:hasDataSourceReference naming the
publisher's filename and the sheet.
"""

HOLIDAYS_NOTE = """
## Holidays

Sheet 327-B lists the same eleven legal holidays as sheet 307-B and states no
rule for one falling on a weekend. Per LAYOUT.md section 4.4 the approving
state's law governs: RCW 1.16.050
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
through 2040. Holidays move only the weekday Peak hours (7am-10am, 5pm-8pm)
to Off-Peak; Super Off-Peak is 11pm-7am every day, holiday or not.
"""


def write(date, expires):
    d = REPO / f"us/wa/pse/electricity/327/versions/{date}"
    d.mkdir(parents=True, exist_ok=True)
    base_local = d / f"pse_327_{date}.pdf"
    shutil.copyfile(SRC / "elec_sch_327.pdf", base_local)
    lines = ["# Identity --------------------------------------------------------------------",
             'utility = "pse"', 'schedule = "327"', f'effective_date = "{date}"', "",
             "# Source ----------------------------------------------------------------------",
             "# One sub-table per committed PDF. Each rider PDF is the whole schedule as PSE",
             "# publishes it; the sheet carrying the Schedule 327 rate is named in the",
             "# PriceDefinition's urpx:hasDataSourceReference.",
             "[source]", 'landing_page = "https://www.pse.com/en/pages/rates/electric-tariffs-and-rules"', ""]

    def block(name, url, local, filing_id, filing_type="tariff-schedule"):
        lines.extend([f"  [source.{name}]", f"  url = {q(url)}", f'  sha256 = "{sha(local)}"',
                      f'  retrieved_on = "{RETRIEVED}"', '  media_type = "application/pdf"',
                      f'  filing_type = "{filing_type}"'])
        if filing_id:
            lines.append(f"  filing_id = {q(filing_id)}")
        lines.append("")

    block("base", PSE + "elec_sch_327.pdf", base_local, "PSE Advice No. 2025-39")
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
                local2 = d / "pse_129_2026-10-01.pdf"
                shutil.copyfile(SRC / "elec_sch_129.pdf", local2)
                lines.append("  # 25th Revision of Sheet 129-B, effective 2026-10-01, cancels the 24th")
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
              "# Docket of the Schedule 327 sheets. Each rider sheet's footer names its own",
              "# advice number, and where it has one, its own docket.",
              "[regulator]", 'authority = "puc"', 'docket = "UE-250725"', "",
              "# Extraction ------------------------------------------------------------------",
              "[extraction]", 'tool = "pdftotext"', 'tool_version = "26.09.0"', f'extracted_on = "{RETRIEVED}"',
              'notes = """' + notes + '"""', "",
              "# Validation ------------------------------------------------------------------",
              "[validation]", "shacl_passed = true", 'validator = "clj-shacl + clj-urpx (URPX v0.5.1)"',
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
    "Sheet 327-A prices the Basic Charge at \"$7.49 single phase or $17.99 three phase\". Only the single-phase $7.49 is carried, as a Price with no condition, so it applies to every customer and a three-phase customer's monthly charge is $10.50 low.",
    "Schedule 81 (Tax Adjustment) increases \"the rates and charges named in this tariff\" by the effect of a municipal tax that varies by jurisdiction, from 2.136 percent to 9.119 percent in the Sheet 81 tables. Not carried; the Summary Sheet also excludes it (\"Rates in this summary include the effect of all supplemental rate schedules except Schedule 81\"). A bill inside a taxing jurisdiction resolves low by that percentage of every charge.",
    "Sheet 327-B BILL PROTECTION: an annual bill credit, for low-income Customers selected for bill protection in the pilot that ended September 30, 2025, of Energy Charge costs more than 10 percent above what Schedule 7 would have charged. Not carried. It reaches only those pilot participants, and its value is a bill recomputed under Schedule 7, which no Price here can state.",
    "Exemptions in the supplemental schedules are not carried: neither Schedule 111 rate applies to a Customer taking optional Schedule 139 service or registered as a National Security Entity, and Schedule 141A does not apply to a Customer who took Schedule 139 service on or before that schedule's original effective date. Both rates are carried as Prices with no condition, so such a customer resolves $0.009637 per kWh low on Schedule 111 (whose net rate is a credit) and $0.002010 per kWh high on Schedule 141A.",
    "Native American Heritage Day is carried as dated urpx:Holiday entries for each year from this version's year through 2040. Sheet 327-B defines it as \"The Friday immediately following the fourth Thursday in November\", which a rule of the form \"Fourth Friday in November\" gets wrong in years when November 1 is a Friday, so no rule string is carried. Each year after 2040 needs a further dated entry.",
]

if __name__ == "__main__":
    for date, exp in (("2026-05-01", "2026-10-01"), ("2026-10-01", None)):
        write(date, exp)
