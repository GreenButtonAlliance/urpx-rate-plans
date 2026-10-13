#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""One-off: offset SCE Generation for Direct Access and CCA Service customers.

Each SCE residential base filing dated 2026-03-20 gains a generation
urpx:PriceSummary naming its Generation Prices and its DWR Energy Credit, the
components its Rates table footnote 2 makes "applicable only to Bundled Service
Customers". sce:da-crs and sce:cca-crs each gain one Ledger, PriceDefinition and
Price carrying urpx:multiplier -1 over those four summaries, read disjunctively.

Summary members are gated to the instant by the base plan's own TOU periods, so
one Price offsets whichever generation cell is live. A urpx:basedOnPrice naming
a single generation Price is valued statically and offsets one cell at every
instant, and names a Price absent from the other three bases.

Takes the repository root. Refuses to run twice.
"""
from __future__ import annotations

import json
import pathlib
import sys

DATE = "2026-03-20"
CELLS = ["summer-on-peak", "summer-mid-peak", "summer-off-peak",
         "winter-mid-peak", "winter-off-peak", "winter-super-off-peak"]

# base -> (PriceSet holding its generation Prices, members, footnote citation)
BASES = {
    "d": ("sce:ps-energy-charges-2026-03-20",
          ["sce:price-generation-2026-03-20", "sce:price-generation-dwrec-2026-03-20"],
          "Schedule D Sheet 2 (Cal. P.U.C. Sheet 90841-E) footnote 2: \"Generation = The Generation rates are applicable only to Bundled Service Customers.\""),
}
for _b, _sheet, _leaf in [("tou-d-4-9pm", 2, "90937-E"),
                          ("tou-d-5-8pm", 4, "90939-E"),
                          ("tou-d-prime", 6, "90941-E")]:
    BASES[_b] = (f"sce:{_b}-{DATE}-ps-generation-charges",
                 [f"sce:{_b}-{DATE}-price-gen-{c}" for c in CELLS] + [f"sce:{_b}-{DATE}-price-gen-dwrec"],
                 f"Schedule TOU-D Sheet {_sheet} (Cal. P.U.C. Sheet {_leaf}) footnote 2: \"Generation = The Gen rates are applicable only to Bundled Service Customers.\"")


def summary_id(base: str) -> str:
    return f"sce:{base}-{DATE}-summary-generation"


MODIFIERS = {
    "da-crs": ("Direct Access",
               "Schedule D Sheet 6 (90638-E) Special Condition 4.b and Schedule TOU-D Sheet 20 (90676-E) Special Condition 11.b: Direct Access Customers \"purchase energy from an Energy Service Provider\" and are billed for Delivery Service plus \"the applicable charges as shown in Schedule DA-CRS\"."),
    "cca-crs": ("CCA Service",
                "Schedule D Sheet 6 (90638-E) Special Condition 4.c and Schedule TOU-D Sheet 21 (91040-E) Special Condition 11.c: CCA Service Customers are billed for \"Delivery Service as displayed in this Rate Schedule and Generation charges determined by the CCA plus the applicable charges as shown in Schedule CCA-CRS\"."),
}


def walk(o, f):
    if isinstance(o, dict):
        f(o)
        for v in o.values():
            walk(v, f)
    elif isinstance(o, list):
        for v in o:
            walk(v, f)


def load(p: pathlib.Path):
    return json.loads(p.read_text())


def dump(p: pathlib.Path, g) -> None:
    p.write_text(json.dumps(g, indent=2, ensure_ascii=False) + "\n")


def add_summary(root: pathlib.Path, base: str) -> None:
    ps_id, members, cite = BASES[base]
    p = root / f"us/ca/sce/electricity/{base}/versions/{DATE}/rate-plan_sce_{base}_{DATE}.jsonld"
    g = load(p)
    found = []
    present = set()

    def visit(o):
        if "@id" in o:
            present.add(o["@id"])
        if o.get("@id") == ps_id:
            found.append(o)
    walk(g, visit)
    if len(found) != 1:
        sys.exit(f"{p}: expected one PriceSet {ps_id}, found {len(found)}")
    if summary_id(base) in present:
        sys.exit(f"{p}: {summary_id(base)} already present")
    if missing := [m for m in members if m not in present]:
        sys.exit(f"{p}: members absent: {missing}")
    found[0].setdefault("urpx:hasPriceSummary", []).append({
        "@type": "urpx:PriceSummary",
        "@id": summary_id(base),
        "urpx:name": f"Generation subtotal for {base.upper()}: its Generation Prices and its DWR Energy Credit. {cite} sce:da-crs and sce:cca-crs offset this subtotal for Direct Access and CCA Service customers.",
        "urpx:includesPrice": [{"@id": m} for m in members],
    })
    dump(p, g)


def add_offset(root: pathlib.Path, mod: str) -> None:
    service, cite = MODIFIERS[mod]
    p = root / f"us/ca/sce/electricity/{mod}/versions/{DATE}/rate-plan-modifier_sce_{mod}_{DATE}.jsonld"
    g = load(p)
    g["@context"].setdefault("urpx:multiplier", {"@type": "xsd:decimal"})
    v = g["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"]
    bm = v["urpx:hasPlanElements"]["urpx:hasBillingModel"]
    ledger = f"sce:{mod}-ledger-oat-generation"
    pd = f"sce:{mod}-pd-oat-generation-offset"
    price = f"sce:{mod}-price-oat-generation-offset-{DATE}"
    if any(l["@id"] == ledger for l in bm["urpx:hasLedger"]):
        sys.exit(f"{p}: {ledger} already present")
    mi = bm["urpx:hasLedger"][0]["urpx:referencesMetricInput"]["@id"]
    bm["urpx:hasLedger"].append({
        "@type": "urpx:Ledger",
        "@id": ledger,
        "urpx:name": f"{mod.upper()} offset of the base plan's SCE Generation",
        "urpx:ledgerType": {"@id": "urpx:supplyLedger"},
        "urpx:referencesMetricInput": {"@id": mi},
    })
    bm["urpx:hasPriceDefinition"].append({
        "@type": "urpx:PriceDefinition",
        "@id": pd,
        "urpx:name": f"Offset of the base plan's SCE Generation and DWR Energy Credit, which a {service} customer does not take from SCE",
        "urpx:chargeType": {"@id": "urpx:creditEnergy"},
        "urpx:chargeCategory": {"@id": "urpx:discount"},
        "urpx:billPortion": {"@id": "urpx:supplyPortion"},
        "urpx:referencesLedger": {"@id": ledger},
    })
    v["urpx:hasPrices"]["urpx:hasPrice"].append({
        "@type": "urpx:Price",
        "@id": price,
        "urpx:name": f"Offset of the generation subtotal of whichever SCE residential base plan the customer is on. {cite}",
        "urpx:referencesPriceDefinition": {"@id": pd},
        "urpx:startDate": DATE,
        "urpx:multiplier": "-1",
        "urpx:basedOnPrice": [{"@id": summary_id(b)} for b in BASES],
    })
    dump(p, g)


def main(argv: list[str]) -> int:
    root = pathlib.Path(argv[1] if len(argv) > 1 else ".").resolve()
    for b in BASES:
        add_summary(root, b)
    for m in MODIFIERS:
        add_offset(root, m)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
