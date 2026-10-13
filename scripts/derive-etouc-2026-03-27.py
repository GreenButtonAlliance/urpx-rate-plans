#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""
Derive ca/iou/pge/e-tou-c/versions/2026-03-27/rate-plan_pge_e-tou-c_2026-03-27.jsonld
from the existing 2026-03-01 filing.

What changes (per Sheet 2 reissue under AL 7869-E / D.26-03-013):
  - Base RPV effective date: 2026-03-01 → 2026-03-27
  - California Climate Credit removed entirely (Sheet 2 deletes it)
  - TariffPublication: AL 7846-E (still issues the modifier) +
    AL 7869-E (new, issues the base RPV with hasRateCase D.26-03-013)
  - RateCase pge:rc-d-26-03-013 added to @graph
  - Base RPV gets hasRateCase pointing at the new RateCase
  - Vintage PCIA modifier: stays at the 2026-03-01 effective date
    (AL 7869-E did not republish E-TOU-C's PCIA sheets)
  - Base-RPV Price startDate values: 2026-03-01 → 2026-03-27
  - Vintage-PCIA Price startDate values: stay at 2026-03-01

URLs unchanged; new sha256 captured in tariff.toml.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "ca/iou/pge/e-tou-c/versions/2026-03-01/rate-plan_pge_e-tou-c_2026-03-01.jsonld"
OUT = ROOT / "ca/iou/pge/e-tou-c/versions/2026-03-27/rate-plan_pge_e-tou-c_2026-03-27.jsonld"


def main():
    data = json.loads(SRC.read_text())
    graph = data["@graph"]

    # ── 1. Replace single-AL TariffPublication with TWO entries (one per AL)
    new_entities = []
    for n in graph:
        if n.get("@id") == "pge:al-7846-e":
            # Modifier-only: drop hasRatePlan, keep hasRatePlanModifier; keep
            # 2026-03-01 effectiveDate / dateReceived (this AL issued the modifier).
            new_al7846 = {
                "@type": "urpx:TariffPublication",
                "@id": "pge:al-7846-e",
                "urpx:name": "PG&E Advice Letter 7846-E",
                "urpx:filingNumber": "7846-E",
                "urpx:issuingAuthority": "California Public Utilities Commission",
                "urpx:publicationType": {"@id": "urpx:regulatoryFiling"},
                "urpx:effectiveDate": "2026-03-01",
                "urpx:dateReceived": "2026-02-27",
                "urpx:hasRatePlanModifier": {"@id": "pge:e-tou-c-vintage-pcia"},
            }
            new_al7869 = {
                "@type": "urpx:TariffPublication",
                "@id": "pge:al-7869-e",
                "urpx:name": "PG&E Advice Letter 7869-E",
                "urpx:filingNumber": "7869-E",
                "urpx:issuingAuthority": "California Public Utilities Commission",
                "urpx:publicationType": {"@id": "urpx:regulatoryFiling"},
                "urpx:description": "CPUC Decision D.26-03-013 — Sheet 2 reissue removing the California Climate Credit",
                "urpx:effectiveDate": "2026-03-27",
                "urpx:dateReceived": "2026-03-27",
                "urpx:hasRatePlan": {"@id": "pge:e-tou-c"},
            }
            new_rate_case = {
                "@type": "urpx:RateCase",
                "@id": "pge:rc-d-26-03-013",
                "urpx:caseNumber": "D.26-03-013",
                "urpx:name": "CPUC Decision D.26-03-013",
                "urpx:url": "https://docs.cpuc.ca.gov/PublishedDocs/Published/G000/M999/K999/26-03-013.PDF",
            }
            new_entities.extend([new_al7846, new_al7869, new_rate_case])
        else:
            new_entities.append(n)
    graph[:] = new_entities

    # ── 2. Mutate the RatePlan / RatePlanVersion (base RPV)
    rate_plan = next(n for n in graph if n.get("@type") == "urpx:RatePlan")
    rpv = rate_plan["urpx:hasRatePlanVersion"]

    # Change RPV @id and effective date
    rpv["@id"] = "pge:e-tou-c-2026-03-27"
    rpv["urpx:effectiveDateTime"] = "2026-03-27T00:00:00"
    rpv["urpx:hasRateCase"] = {"@id": "pge:rc-d-26-03-013"}

    # Update description to reflect new effective date and climate-credit removal
    rpv["urpx:description"] = (
        "Voluntary residential TOU schedule with summer/winter peak (4-9 p.m. all days) and off-peak periods. "
        "Customers pay a daily base services charge that varies by income tier (CARE / FERA / standard). "
        "Baseline credit and Conservation Incentive Adjustment apply per a territory/code/season matrix — "
        "modeled separately as RatePlanModifier (grid-coordination/urpx-rate-plans#2, blocked on urpx-org/urpx#11). "
        "Vintage PCIA for CCA/DA/TBS customers is modeled as a sibling RatePlanModifier in this file. "
        "Compared to the 2026-03-01 version: California Climate Credit removed (Sheet 2 reissued under AL 7869-E / D.26-03-013, sheet 61249-E)."
    )

    # Update DataSourceReference TariffBookReference to mention sheet 2's new leaf
    dsr = rpv.get("urpx:hasDataSourceReference", {})
    tbr = dsr.get("urpx:hasTariffBookReference", {})
    if tbr:
        # The book mixes leaves now: Sheet 1 still 61124-E, Sheet 2 now 61249-E,
        # Sheets 3-10 unchanged. Range covers extracted scope.
        tbr["urpx:leafEnd"] = "61249-E"  # the highest leaf in the new composite

    # Update retrieved date on DataSourceReference
    if "urpx:dateRetrieved" in dsr:
        dsr["urpx:dateRetrieved"] = "2026-04-28"

    # ── 3. Remove climate-credit MetricInput (mi-household-count)
    pe = rpv["urpx:hasPlanElements"]
    pe["urpx:hasMetricInput"] = [
        mi for mi in pe.get("urpx:hasMetricInput", [])
        if mi.get("@id") != "pge:mi-household-count"
    ]

    # ── 4. Remove climate-credit Ledger from BillingModel
    bm = pe["urpx:hasBillingModel"]
    bm["urpx:hasLedger"] = [
        led for led in bm.get("urpx:hasLedger", [])
        if led.get("@id") != "pge:ledger-climate-credit"
    ]

    # ── 5. Remove climate-credit PriceDefinition from BillingModel
    bm["urpx:hasPriceDefinition"] = [
        pd for pd in bm.get("urpx:hasPriceDefinition", [])
        if pd.get("@id") != "pge:pd-climate-credit"
    ]

    # ── 6. Remove climate-credit Price from base-RPV hasPrices.hasPrice
    prices = rpv["urpx:hasPrices"]
    prices["urpx:hasPrice"] = [
        p for p in prices.get("urpx:hasPrice", [])
        if p.get("@id") != "pge:price-climate-credit"
    ]
    # Also remove from any PriceSets (the climate credit was a top-level Price,
    # not in a PriceSet, so this is defensive only)
    for ps in prices.get("urpx:hasPriceSet", []):
        ps["urpx:hasPrice"] = [
            p for p in ps.get("urpx:hasPrice", [])
            if p.get("@id") != "pge:price-climate-credit"
        ]

    # ── 7. Update startDate on every base-RPV Price (top-level + PriceSet members)
    for p in prices.get("urpx:hasPrice", []):
        if p.get("urpx:startDate") == "2026-03-01":
            p["urpx:startDate"] = "2026-03-27"
    for ps in prices.get("urpx:hasPriceSet", []):
        if ps.get("urpx:startDate") == "2026-03-01":
            ps["urpx:startDate"] = "2026-03-27"
        for p in ps.get("urpx:hasPrice", []):
            if p.get("urpx:startDate") == "2026-03-01":
                p["urpx:startDate"] = "2026-03-27"

    # ── 8. Vintage PCIA modifier: NO changes. Stays at 2026-03-01.
    #    (RPMV @id, effective date, applicableToRatePlan, all PCIA Price startDates.)

    # Write
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
