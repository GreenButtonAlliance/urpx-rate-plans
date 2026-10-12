#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Author PG&E Schedule CCA-CRS 2026-01-01 and the base-plan changes it needs.

A PG&E Community Choice Aggregation customer's PG&E bill is its base plan plus
pge:cca-crs, and nothing else:

  - each of the 13 PG&E residential base versions gains a generation
    urpx:PriceSummary naming every Price in its generation PriceSet (the
    seasonal generation Prices and the Bundled PCIA), the two charges each
    base's Billing condition excludes for CCA, DA and TBS customers;
  - pge:cca-crs carries the residential Vintage PCIA of Sheets 3 to 5 as a
    ProfileAlternatives over departureVintage crossed with CARE enrollment
    (Sheet 2 row 2 exempts CARE from the Vintage PCIA, so the CARE cells carry
    no PCIA Price), plus one Price with urpx:multiplier -1 over the 13
    generation summaries, read disjunctively;
  - the inlined pge:<base>-vintage-pcia modifiers lose their CCA branch and
    serve Direct Access and Transitional Bundled Service only, and the base
    manifests' deferrals say so.

CCA-CRS Sheet 3 states that its ECRA, Wildfire Fund Charge and Ongoing CTC
"are currently reflected in each individual applicable rate schedule", and
every base prices them, so pge:cca-crs does not price them again.

Takes the repository root. Refuses to run twice. Run
dev/resync_coverage_evaluations.py afterwards.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

DATE = "2026-01-01"
V = f"pge:cca-crs-{DATE}"
URL = "https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_SCHEDS_CCA-CRS.pdf"
SHA = "f8915d31fdb7b507f71a4c7c869df582ba7712560d37d22063b8eb0967f73842"
RETRIEVED = "2026-09-23"
TODAY = "2026-10-11"

# vintage -> (residential $/kWh, CCA-CRS sheet, leaf)
PCIA = {
    2009: ("0.02973", 3, "60676-E"), 2010: ("0.03366", 3, "60676-E"),
    2011: ("0.03492", 3, "60676-E"), 2012: ("0.03676", 3, "60676-E"),
    2013: ("0.03708", 3, "60676-E"), 2014: ("0.03686", 4, "60677-E"),
    2015: ("0.03680", 4, "60677-E"), 2016: ("0.03687", 4, "60677-E"),
    2017: ("0.03661", 4, "60677-E"), 2018: ("0.03679", 4, "60677-E"),
    2019: ("0.03725", 4, "60677-E"), 2020: ("0.03632", 4, "60677-E"),
    2021: ("0.05264", 4, "60677-E"), 2022: ("0.05272", 5, "60678-E"),
    2023: ("0.05380", 5, "60678-E"), 2024: ("0.05066", 5, "60678-E"),
    2025: ("-0.01011", 5, "60678-E"), 2026: ("-0.01011", 5, "60678-E"),
}

BILLING = ("shall pay all charges shown in the Unbundling of Total Rates except for the "
           "Bundled Power Charge Indifference Adjustment and the generation charge")

# base slug -> {date: Billing-condition citation in that version's source}
BASES = {
    "e-1": {d: "Schedule E-1 Sheet 6 (Cal. P.U.C. Sheet 61101-E)" for d in ("2026-03-01", "2026-06-01")},
    "e-elec": {"2026-01-01": "Schedule E-ELEC Sheet 4 (Cal. P.U.C. Sheet 60703-E) Special Condition 4",
               **{d: "Schedule E-ELEC Sheets 4 and 5 (Cal. P.U.C. Sheets 61119-E and 61120-E) Special Condition 4"
                  for d in ("2026-03-27", "2026-06-01", "2026-08-28")}},
    "e-tou-c": {d: "Schedule E-TOU-C Sheet 8 (Cal. P.U.C. Sheet 61131-E)"
                for d in ("2026-03-01", "2026-03-27", "2026-06-01")},
    "e-tou-d": {d: "Schedule E-TOU-D Sheet 5 (Cal. P.U.C. Sheet 61138-E) Special Condition 5"
                for d in ("2026-03-27", "2026-06-01")},
    "ev2": {d: "Schedule EV2 Sheets 4 and 5 (Cal. P.U.C. Sheets 61172-E and 61173-E) Special Condition 4"
            for d in ("2026-03-27", "2026-06-01")},
}
VINTAGE_MODIFIER = {"e-1": "Sheet 6", "e-tou-c": "Sheet 8", "e-tou-d": "Sheet 5", "ev2": "Sheet 5"}


def walk(o, f):
    if isinstance(o, dict):
        f(o)
        for v in o.values():
            walk(v, f)
    elif isinstance(o, list):
        for v in o:
            walk(v, f)


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def dump(p: Path, g) -> None:
    p.write_text(json.dumps(g, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def summary_id(base: str, date: str) -> str:
    return f"pge:{base}-{date}-summary-generation"


def base_path(root: Path, base: str, date: str) -> Path:
    return root / f"us/ca/pge/electricity/{base}/versions/{date}/rate-plan_pge_{base}_{date}.jsonld"


# --- base plans: generation summaries ---------------------------------------

def add_summary(root: Path, base: str, date: str) -> None:
    p = base_path(root, base, date)
    g = load(p)
    found = []

    def visit(o):
        if o.get("@type") == "urpx:RatePlanVersion" and o.get("@id") == f"pge:{base}-{date}":
            def inner(x):
                if x.get("@type") == "urpx:PriceSet" and any(
                        re.search(r"price-gen|price-generation", pr["@id"]) for pr in x.get("urpx:hasPrice", [])):
                    found.append(x)
            walk(o, inner)
    walk(g, visit)
    if len(found) != 1:
        sys.exit(f"{p}: expected one generation PriceSet, found {len(found)}")
    ps = found[0]
    if any(s["@id"] == summary_id(base, date) for s in ps.get("urpx:hasPriceSummary", [])):
        sys.exit(f"{p}: {summary_id(base, date)} already present")
    members = [pr["@id"] for pr in ps["urpx:hasPrice"]]
    gen = [m for m in members if re.search(r"price-gen", m)]
    pcia = [m for m in members if re.search(r"pcia", m)]
    if len(pcia) != 1 or len(gen) + 1 != len(members):
        sys.exit(f"{p}: generation PriceSet holds {members}, expected generation Prices and one Bundled PCIA")
    ps.setdefault("urpx:hasPriceSummary", []).append({
        "@type": "urpx:PriceSummary",
        "@id": summary_id(base, date),
        "urpx:name": (f"Generation subtotal for {base.upper()}: its generation Prices and its Bundled Power "
                      f"Charge Indifference Adjustment. {BASES[base][date]}: Direct Access and Community Choice "
                      f"Aggregation Generation Service Customers \"{BILLING}\". pge:cca-crs offsets this "
                      "subtotal for Community Choice Aggregation customers."),
        "urpx:includesPrice": [{"@id": m} for m in members],
    })
    dump(p, g)


# --- inlined vintage-PCIA modifiers: DA and TBS only -------------------------

def vintage_evaluation(base: str) -> str:
    sheet = VINTAGE_MODIFIER[base]
    return (f"This modifier carries the eighteen vintage Power Charge Indifference Adjustment rates published on "
            f"Schedule {base.upper()} {sheet}, from $0.02973 per kWh for the 2009 vintage to a credit of $0.01011 "
            "per kWh for the 2025 and 2026 vintages, gated on a residential customer taking Direct Access or "
            "Transitional Bundled Service. Community Choice Aggregation customers take the same eighteen rates "
            f"from pge:cca-crs. {sheet} states that Direct Access and Transitional Bundled Service customers pay "
            "every charge in the Unbundling of Total Rates except the Bundled Power Charge Indifference Adjustment "
            "and the generation charge, and nothing in this modifier removes the base plan's generation Prices or "
            "its Bundled PCIA, so a consumer applying the base plan together with this modifier charges a Direct "
            "Access or Transitional Bundled Service customer PG&E generation and both the bundled and the vintaged "
            "adjustment. Three further charges the same sheet directs these customers to are absent because they "
            "live in other schedules: the franchise fee surcharge under Schedule E-FFS for Direct Access "
            "customers, the short-term commodity prices under Schedule TBCC for Transitional Bundled Service "
            "customers, and the exemptions set out in Schedule DA CRS.")


def narrow_vintage(root: Path, base: str) -> None:
    mv = None
    for date in BASES[base]:
        p = base_path(root, base, date)
        g = load(p)
        hits = []

        def visit(o):
            if o.get("@type") == "urpx:RatePlanModifierVersion" and o["@id"].startswith(f"pge:{base}-vintage-pcia-"):
                hits.append(o)
        walk(g, visit)
        if not hits:
            continue
        for v in hits:
            mv = v["@id"]
            rules = v["urpx:hasEligibilityRule"]
            er = [r for r in rules if r["@id"] == f"{mv}-er-cca-da-tbs"]
            if len(er) != 1:
                sys.exit(f"{p}: {mv}-er-cca-da-tbs absent; already narrowed?")
            r = er[0]
            r["@id"] = f"{mv}-er-da-tbs"
            r["urpx:name"] = "Generation service: DA or TBS"
            r["urpx:description"] = ("Vintaged PCIA under this modifier applies to customers taking Direct Access "
                                     "service or Transitional Bundled Service. Community Choice Aggregation "
                                     "customers take it from pge:cca-crs.")
            cx = r["urpx:hasConditionExpression"]
            cx["@id"] = f"{mv}-cx-da-tbs"
            bn = cx["urpx:rootNode"]
            bn["@id"] = f"{mv}-bn-da-tbs-or"
            before = len(bn["urpx:operandNodes"])
            bn["urpx:operandNodes"] = [n for n in bn["urpx:operandNodes"] if n["@id"] != f"{mv}-cn-program-cca"]
            if len(bn["urpx:operandNodes"]) != before - 1:
                sys.exit(f"{p}: no CCA operand on {mv}")
            old = ("applied to Transitional Bundled Service (TBS), Community Choice Aggregation (CCA), and Direct "
                   "Access (DA) customers")
            if old not in v["urpx:description"]:
                sys.exit(f"{p}: unexpected description on {mv}")
            v["urpx:description"] = (v["urpx:description"].replace(
                old, "applied to Transitional Bundled Service (TBS) and Direct Access (DA) customers")
                + " Community Choice Aggregation (CCA) customers take the same rates from pge:cca-crs.")
            ev = v["urpx:hasCoverageClaim"].get("urpx:explainedBy")
            if ev is not None:
                ev["urpx:description"] = vintage_evaluation(base)
        dump(p, g)
    if mv is None:
        sys.exit(f"no pge:{base}-vintage-pcia found")


# --- base manifests ----------------------------------------------------------

def da_tbs_deferral(base: str, date: str) -> str:
    cite = BASES[base][date]
    s = summary_id(base, date)
    if base in VINTAGE_MODIFIER:
        return (f"{cite}: Direct Access and Transitional Bundled Service customers '{BILLING}', paying their "
                f"Vintaged PCIA instead. pge:{base}-vintage-pcia is gated on DA and TBS and adds the vintaged rate, "
                "but nothing removes this version's generation Prices or its Bundled PCIA Price, so base plus "
                f"pge:{base}-vintage-pcia still charges a DA or TBS customer PG&E generation and both the bundled "
                "and the vintaged PCIA. The DA and TBS offset waits on Schedule DA-CRS. Community Choice "
                f"Aggregation customers are priced by base plus pge:cca-crs, whose multiplier -1 Price offsets {s}.")
    return (f"{cite}: Direct Access and Transitional Bundled Service customers '{BILLING}', paying their Vintaged "
            "PCIA instead. Neither half is modeled for them: no modifier carries this schedule's vintage table for "
            "DA or TBS, and nothing removes this version's generation Prices or its Bundled PCIA Price, so this "
            "base charges a DA or TBS customer PG&E generation and the bundled PCIA. The DA and TBS treatment waits "
            "on Schedule DA-CRS. Community Choice Aggregation customers are priced by base plus pge:cca-crs, which "
            "carries the vintage rates from Schedule CCA-CRS Sheets 3 to 5 and whose multiplier -1 Price offsets "
            f"{s}.")


def e_elec_vintage_deferral(date: str) -> str:
    where = ("Sheet 4 Special Condition 4 (Cal. P.U.C. Sheet 60703-E)" if date == "2026-01-01"
             else "Sheet 5 (AL 7846-E, leaf 61120-E)")
    return (f"{where} prices the Vintaged Power Charge Indifference Adjustment as 18 per-kWh rates, 2009 Vintage "
            "$0.02973 through 2026 Vintage $(0.01011), payable by DA, CCA and TBS customers. For CCA customers the "
            "same 18 rates are carried by pge:cca-crs, from Schedule CCA-CRS Sheets 3 to 5. For DA and TBS "
            "customers they are not modeled; this version's only PCIA Price is the Bundled PCIA at $(0.01011). "
            "Expressible as an inline modifier gated on DA and TBS, as pge:e-tou-c-vintage-pcia is.")


# prefix of the deferral each manifest replaces, by base
REPLACED = {
    "e-1": ["Direct Access, CCA and Transitional Bundled Service customers do not pay"],
    "e-elec": ["DA / CCA / TBS component exclusion", "Special Condition 4 (Sheets 4 and 5) prices Direct Access"],
    "e-tou-c": ["Sheet 8 (Cal. P.U.C. Sheet 61131-E) directs CCA", "Sheet 8: CCA, Direct Access"],
    "e-tou-d": ["Special Condition 5 (Sheet 5, Cal. P.U.C. Sheet No. 61138-E): DA, CCA and TBS"],
    "ev2": ["DA, CCA and TBS customers are still charged"],
}
E_ELEC_VINTAGE = ["Vintaged PCIA table, Sheet 4 Special Condition 4", "Sheet 5 (AL 7846-E, leaf 61120-E) prices the Vintaged"]


def edit_manifest(root: Path, base: str, date: str) -> None:
    import tomli
    p = root / f"us/ca/pge/electricity/{base}/versions/{date}/tariff.toml"
    text = p.read_text(encoding="utf-8")
    m = tomli.loads(text)["modeling"]
    if "cca-crs" in m["applicable_modifiers"]:
        sys.exit(f"{p}: cca-crs already applicable")
    swaps = [(REPLACED[base], da_tbs_deferral(base, date))]
    if base == "e-elec":
        swaps.append((E_ELEC_VINTAGE, e_elec_vintage_deferral(date)))
    for prefixes, new in swaps:
        olds = [d for d in m["deferrals"] if any(d.startswith(x) for x in prefixes)]
        if len(olds) != 1:
            sys.exit(f"{p}: expected one deferral starting {prefixes}, found {len(olds)}")
        enc = toml_str(olds[0])
        if text.count(enc) != 1:
            sys.exit(f"{p}: deferral not found verbatim")
        text = text.replace(enc, toml_str(new))
    anchor = "applicable_modifiers = [\n"
    if text.count(anchor) != 1:
        sys.exit(f"{p}: applicable_modifiers not in multi-line form")
    text = text.replace(anchor, anchor + ' "cca-crs",\n')
    tomli.loads(text)
    p.write_text(text, encoding="utf-8")


def edit_readmes(root: Path) -> None:
    for p in sorted(root.glob("us/ca/pge/electricity/*/versions/*/README.md")):
        t = p.read_text(encoding="utf-8")
        n = t.replace("vintage-conditional PCIA prices for CCA/DA/TBS customers",
                      "vintage-conditional PCIA prices for DA/TBS customers (CCA customers: pge:cca-crs)")
        if n != t:
            p.write_text(n, encoding="utf-8")


# --- pge:cca-crs -------------------------------------------------------------

def check_sheets(pdf: Path) -> None:
    """Every PCIA value is the Residential row of its sheet in the committed PDF."""
    for sheet in (3, 4, 5):
        t = subprocess.run(["pdftotext", "-layout", "-f", str(sheet), "-l", str(sheet), str(pdf), "-"],
                           capture_output=True, text=True, check=True).stdout
        rows = [l for l in t.splitlines() if l.strip().startswith("Residential")]
        cells = [c.replace("$", "").replace("(", "-").replace(")", "")
                 for r in rows for c in re.findall(r"\(?\$\d\.\d{5}\)?", r)]
        want = [v for y, (v, s, _) in sorted(PCIA.items()) if s == sheet]
        if sheet == 3:
            cells = cells[3:]  # after the ECRA, Wildfire Fund Charge and Ongoing CTC
        if cells != want:
            sys.exit(f"Sheet {sheet} Residential PCIA {cells} != {want}")
    t = subprocess.run(["pdftotext", "-layout", "-f", "3", "-l", "3", str(pdf), "-"],
                       capture_output=True, text=True, check=True).stdout
    res = next(l for l in t.splitlines() if l.strip().startswith("Residential"))
    if re.findall(r"\$\d\.\d{5}", res)[:3] != ["$0.00002", "$0.00591", "$0.00027"]:
        sys.exit("Sheet 3 Residential ECRA, Wildfire Fund Charge, Ongoing CTC moved")


def check_bases_carry_crs(root: Path) -> None:
    """Sheet 3's ECRA, WFC and CTC equal each base's own Prices, so the base carries them."""
    want = {"Energy Cost Recovery": "0.00002", "Wildfire Fund": "0.00591", "Competition Transition": "0.00027"}
    for base, dates in BASES.items():
        for date in dates:
            g = load(base_path(root, base, date))
            pds, prices = {}, []

            def visit(o):
                if o.get("@type") == "urpx:PriceDefinition":
                    pds[o["@id"]] = o.get("urpx:name", "")
                if o.get("@type") == "urpx:Price":
                    prices.append(o)
            walk(g, visit)
            for key, val in want.items():
                hit = [pr.get("urpx:unitPrice") for pr in prices
                       if key.lower() in (pr.get("urpx:name", "") + " " + pds.get(
                           pr.get("urpx:referencesPriceDefinition", {}).get("@id"), "")).lower()]
                if val not in hit:
                    sys.exit(f"{base} {date}: no {key} Price at {val} ({hit})")


def cmp(i: str, op: str, left: dict, right: dict) -> dict:
    return {"@type": "urpx:ComparisonNode", "@id": i, "urpx:operator": {"@id": op},
            "urpx:leftOperand": {"@id": f"{i}-left-operand", **left},
            "urpx:rightOperand": {"@id": f"{i}-right-operand", **right}}


def enrollment(i: str, op: str, program: str) -> dict:
    return cmp(i, op, {"@type": "urpx:ObjectOperandNode", "urpx:conditionProperty": {"@id": "urpx:hasProgramEnrollment"}},
               {"@type": "urpx:ObjectOperandNode", "urpx:referencesValue": {"@id": program}})


def vintage_cmp(i: str, y: int) -> dict:
    return cmp(i, "urpx:equalsOperator",
               {"@type": "urpx:CustomOperandNode", "urpx:customConditionProperty": "departureVintage"},
               {"@type": "urpx:CustomOperandNode", "urpx:gYearValue": str(y)})


def alternative(y: int, care: bool) -> dict:
    a = f"{V}-pa-v{y}" + ("-care" if care else "")
    name = (f"PCIA vintage {y}, CARE (exempt from the Vintage PCIA, Sheet 2 row 2)" if care
            else f"PCIA vintage {y}, not CARE")
    return {
        "@type": "urpx:ProfileAlternative", "@id": a, "urpx:name": name,
        "urpx:hasConditionExpression": {
            "@type": "urpx:ConditionExpression", "@id": f"{a}-condition-expression",
            "urpx:rootNode": {
                "@type": "urpx:BooleanOperationNode", "@id": f"{a}-root-node",
                "urpx:operator": {"@id": "urpx:andOperator"},
                "urpx:operandNodes": [
                    vintage_cmp(f"{a}-vintage", y),
                    enrollment(f"{a}-care" if care else f"{a}-not-care",
                               "urpx:equalsOperator" if care else "urpx:notEqualsOperator", "pge:program-care"),
                ]}}}


def build(root: Path, programs: list[dict], org: dict) -> dict:
    bases = [(b, d) for b, ds in BASES.items() for d in ds]
    mi = f"{V}-mi-energy"
    ledger = lambda k, n, t: {"@type": "urpx:Ledger", "@id": f"{V}-ledger-{k}", "urpx:name": n,
                              "urpx:ledgerType": {"@id": t}, "urpx:referencesMetricInput": {"@id": mi}}
    years = sorted(PCIA)
    alts = [alternative(y, care) for y in years for care in (False, True)]
    psas = [{
        "@type": "urpx:PriceSetAlternative", "@id": f"{V}-psa-pcia-v{y}",
        "urpx:referencesProfileAlternative": {"@id": f"{V}-pa-v{y}"},
        "urpx:hasPrice": [{
            "@type": "urpx:Price", "@id": f"{V}-price-pcia-v{y}",
            "urpx:referencesPriceDefinition": {"@id": f"{V}-pd-pcia"},
            "urpx:startDate": DATE,
            "urpx:name": f"Vintage PCIA, {y} vintage, Residential: Schedule CCA-CRS Sheet {PCIA[y][1]} (Cal. P.U.C. Sheet {PCIA[y][2]})",
            "urpx:unitPrice": PCIA[y][0],
        }],
    } for y in years]
    deferrals = DEFERRALS
    evaluation = ("This filing does not carry everything its source document states. {n} parts are deferred, "
                  "listed here in the same words as the filing's tariff.toml [modeling].deferrals so the two "
                  "records cannot drift.").format(n=len(deferrals)) + " " + " ".join(
        f"({i}) {' '.join(d.split())}" for i, d in enumerate(deferrals, 1))
    version = {
        "@type": "urpx:RatePlanModifierVersion", "@id": V,
        "urpx:modifierVersionNumber": DATE,
        "urpx:changeReason": {"@id": "urpx:rateCase"},
        "urpx:description": DESCRIPTION,
        "urpx:effectiveDateTime": f"{DATE}T00:00:00",
        "urpx:priceCurrency": "USD",
        "urpx:commodity": {"@id": "urpx:electricity"},
        "urpx:serviceRole": {"@id": "urpx:bundledServiceRole"},
        "urpx:applicableToRatePlan": [{"@id": f"pge:{b}"} for b in BASES],
        "urpx:hasDataSourceReference": {
            "@type": "urpx:DataSourceReference", "urpx:fileName": "ELEC_SCHEDS_CCA-CRS.pdf",
            "urpx:mediaType": {"@id": "urpx:applicationPdf"}, "urpx:accessURL": URL,
            "urpx:dateRetrieved": RETRIEVED, "urpx:dataSourceType": {"@id": "urpx:utilityWebsiteSource"},
            "urpx:pageStart": 1, "urpx:pageEnd": 6, "urpx:leafStart": "52000-E", "urpx:leafEnd": "58892-E",
            "urpx:sourcePublication": {"@id": "pge:al-7797-e"},
        },
        "urpx:hasEligibilityRule": [
            {"@type": "urpx:EligibilityRule", "@id": f"{V}-er-residential", "urpx:name": "Residential customer",
             "urpx:description": "This filing carries the Residential row of Sheets 3 to 5.",
             "urpx:hasConditionExpression": {
                 "@type": "urpx:ConditionExpression", "@id": f"{V}-cx-residential",
                 "urpx:rootNode": cmp(f"{V}-cn-residential", "urpx:equalsOperator",
                                      {"@type": "urpx:ObjectOperandNode", "urpx:conditionProperty": {"@id": "urpx:hasCustomerKind"}},
                                      {"@type": "urpx:ObjectOperandNode", "urpx:referencesValue": {"@id": "urpx:residentialKind"}})}},
            {"@type": "urpx:EligibilityRule", "@id": f"{V}-er-cca", "urpx:name": "Community Choice Aggregation service",
             "urpx:description": "Sheet 1 APPLICABILITY: \"This schedule and the applicable components of the Community Choice Aggregation (CCA) Cost Responsibility Surcharge (CRS) apply to all customers who take CCA service, unless otherwise set forth in the Special Conditions, below.\"",
             "urpx:hasConditionExpression": {
                 "@type": "urpx:ConditionExpression", "@id": f"{V}-cx-cca",
                 "urpx:rootNode": enrollment(f"{V}-cn-cca", "urpx:equalsOperator", "pge:program-cca")}},
        ],
        "urpx:hasPlanElements": {
            "@type": "urpx:PlanElements", "@id": f"{V}-plan-elements",
            "urpx:hasMetricInput": [{
                "@type": "urpx:MetricInput", "@id": mi, "urpx:name": "kWh Energy Consumption",
                "urpx:metricInputType": {"@id": "urpx:measuredMetricInput"},
                "urpx:hasMetricSpecification": {"@type": "urpx:MetricSpecification", "@id": f"{V}-ms-energy",
                                                "urpx:measurementKind": {"@id": "urpx:energy"},
                                                "urpx:unitOfMeasure": {"@id": "urpx:kWh"}}}],
            "urpx:hasProfileAlternatives": {
                "@type": "urpx:ProfileAlternatives", "@id": f"{V}-pa-vintage-care",
                "urpx:name": "PCIA vintage year crossed with CARE enrollment",
                "urpx:hasAlternativeDimensions": {
                    "@type": "urpx:AlternativeDimensions", "@id": f"{V}-pa-vintage-care-alternative-dimensions",
                    "urpx:hasAlternativeDimension": [
                        {"@type": "urpx:AlternativeDimension", "urpx:dimensionDisplayName": "PCIA Vintage Year",
                         "urpx:customDimensionProperty": "departureVintage",
                         "urpx:hasPossibleValues": {"@list": [{"@value": str(y), "@type": "xsd:gYear"} for y in years]}},
                        {"@type": "urpx:AlternativeDimension", "urpx:dimensionDisplayName": "Program Enrollment",
                         "urpx:dimensionProperty": "https://urpx.org/ns/ontology/hasProgramEnrollment",
                         "urpx:hasPossibleValues": {"@list": [{"@id": "pge:program-care"}]}},
                    ]},
                "urpx:hasProfileAlternative": alts,
            },
            "urpx:hasBillingModel": {
                "@type": "urpx:BillingModel", "@id": f"{V}-plan-elements-billing-model",
                "urpx:hasLedger": [
                    ledger("pcia", "CCA-CRS Vintage Power Charge Indifference Adjustment", "urpx:bundledLedger"),
                    ledger("oat-generation", "CCA-CRS offset of the base plan's PG&E generation and Bundled PCIA", "urpx:supplyLedger"),
                ],
                "urpx:hasPriceDefinition": [
                    {"@type": "urpx:PriceDefinition", "@id": f"{V}-pd-pcia", "urpx:name": "Vintage PCIA",
                     "urpx:chargeType": {"@id": "urpx:strandedCosts"}, "urpx:chargeCategory": {"@id": "urpx:adjustment"},
                     "urpx:billPortion": {"@id": "urpx:deliveryPortion"}, "urpx:referencesLedger": {"@id": f"{V}-ledger-pcia"}},
                    {"@type": "urpx:PriceDefinition", "@id": f"{V}-pd-oat-generation-offset",
                     "urpx:name": "Offset of the base plan's PG&E generation and Bundled PCIA, which a CCA customer does not pay PG&E",
                     "urpx:chargeType": {"@id": "urpx:creditEnergy"}, "urpx:chargeCategory": {"@id": "urpx:discount"},
                     "urpx:billPortion": {"@id": "urpx:supplyPortion"}, "urpx:referencesLedger": {"@id": f"{V}-ledger-oat-generation"}},
                ],
            },
        },
        "urpx:hasPrices": {
            "@type": "urpx:Prices", "@id": f"{V}-prices",
            "urpx:hasPrice": [{
                "@type": "urpx:Price", "@id": f"{V}-price-oat-generation-offset",
                "urpx:name": ("Offset of the generation subtotal of whichever PG&E residential base plan the customer "
                              f"is on. Each base's Billing condition: CCA Generation Service Customers \"{BILLING}\" "
                              "(Schedule E-1 Sheet 6, E-ELEC Special Condition 4, E-TOU-C Sheet 8, E-TOU-D Special "
                              "Condition 5, EV2 Special Condition 4)."),
                "urpx:referencesPriceDefinition": {"@id": f"{V}-pd-oat-generation-offset"},
                "urpx:startDate": DATE,
                "urpx:multiplier": "-1",
                "urpx:basedOnPrice": [{"@id": summary_id(b, d)} for b, d in bases],
            }],
            "urpx:hasPriceSetAlternatives": [{
                "@type": "urpx:PriceSetAlternatives", "@id": f"{V}-psa-pcia-by-vintage",
                "urpx:name": "Vintage PCIA, varies by PCIA vintage year; CARE customers exempt",
                "urpx:referencesProfileAlternatives": {"@id": f"{V}-pa-vintage-care"},
                "urpx:hasPriceSetAlternative": psas,
            }],
        },
        "urpx:offeredBy": org,
        "urpx:forRatePlanModifier": {"@id": "pge:cca-crs"},
        "urpx:hasCoverageClaim": {
            "@id": f"pge:cc-cca-crs-{DATE}", "@type": "urpx:CoverageClaim",
            "urpx:completenessResult": {"@id": "urpx:partial"}, "urpx:selfContained": True,
            "urpx:explainedBy": {"@type": "urpx:Evaluation", "@id": f"pge:cc-cca-crs-{DATE}-evaluation",
                                 "urpx:evaluationKind": {"@id": "urpx:coverageEvaluation"},
                                 "urpx:description": evaluation, "urpx:evaluatedOn": f"{TODAY}T00:00:00"},
        },
    }
    context = {
        "urpx": "https://urpx.org/ns/ontology/", "xsd": "http://www.w3.org/2001/XMLSchema#",
        "org": "https://rate-plans.grid-coordination.energy/organizations/",
        "pge": "https://rate-plans.grid-coordination.energy/pge/",
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "urpx:unitPrice": {"@type": "xsd:decimal"}, "urpx:multiplier": {"@type": "xsd:decimal"},
        "urpx:effectiveDate": {"@type": "xsd:date"}, "urpx:effectiveDateTime": {"@type": "xsd:dateTime"},
        "urpx:initialEffectiveDate": {"@type": "xsd:date"}, "urpx:startDate": {"@type": "xsd:date"},
        "urpx:dimensionProperty": {"@type": "xsd:anyURI"}, "urpx:pageStart": {"@type": "xsd:integer"},
        "urpx:pageEnd": {"@type": "xsd:integer"}, "urpx:accessURL": {"@type": "xsd:anyURI"},
        "urpx:dateRetrieved": {"@type": "xsd:date"}, "urpx:dateReceived": {"@type": "xsd:date"},
        "urpx:gYearValue": {"@type": "xsd:gYear"}, "urpx:targetURPXVersion": {"@type": "xsd:anyURI"},
        "urpx:evaluatedOn": {"@type": "xsd:dateTime"},
    }
    al = {"@type": "urpx:SourcePublication", "@id": "pge:al-7797-e", "urpx:name": "PG&E Advice Letter 7797-E",
          "urpx:filingNumber": "7797-E", "urpx:issuingAuthority": "California Public Utilities Commission",
          "urpx:publicationType": {"@id": "urpx:tariffSupplement"},
          "urpx:effectiveDate": "2026-01-01", "urpx:dateReceived": "2025-12-30"}
    return {
        "@context": context,
        "@graph": [
            {"@type": "urpx:URPXPackage", "@id": f"pge:doc-cca-crs-{DATE}",
             "urpx:targetURPXVersion": "https://github.com/urpx-org/urpx/raw/v0.5.1/ontology/urpx-ontology.ttl",
             "urpx:hasRatePlanModifier": {
                 "@type": "urpx:RatePlanModifier", "@id": "pge:cca-crs", "urpx:name": "Schedule CCA-CRS",
                 "urpx:modifierUniqueIdentifier": "CCA-CRS", "urpx:initialEffectiveDate": DATE,
                 "urpx:timezoneIdentifier": "America/Los_Angeles",
                 "urpx:hasRatePlanModifierVersion": version}},
            *programs,
            al,
        ],
    }


DESCRIPTION = (
    "Schedule CCA-CRS, Community Choice Aggregation Cost Responsibility Surcharge, for a residential customer "
    "taking CCA service, applied over the customer's PG&E residential base plan (E-1, E-ELEC, E-TOU-C, E-TOU-D or "
    "EV2). A CCA customer's PG&E price is the base plan plus this modifier and nothing else. Sheet 1 names four "
    "components: the Energy Cost Recovery Amount, the Ongoing Competition Transition Charge, the Wildfire Fund "
    "Charge and the Power Charge Indifference Adjustment. Sheet 3 states that its rates \"are currently reflected "
    "in each individual applicable rate schedule and are consolidated below\", and every base prices the first "
    "three in its Unbundling of Total Rates at the Sheet 3 Residential values ($0.00002, $0.00027 and $0.00591 per "
    "kWh), so this modifier carries only the Vintage PCIA. Its eighteen Residential vintage rates, 2009 through "
    "2026, are mutually exclusive: a urpx:ProfileAlternatives crosses the departureVintage attribute with CARE "
    "enrollment, and only the non-CARE cells carry a Price, because Sheet 2 row 2 exempts CARE customers from the "
    "Vintage PCIA. Each base's Billing condition excludes the generation charge and the Bundled PCIA for CCA "
    "customers; a Price carrying urpx:multiplier -1 over that base's generation urpx:PriceSummary removes both. "
    "Generation from the CCA itself is priced by the CCA and is outside this filing. Direct Access and "
    "Transitional Bundled Service customers take the vintage rates from the inlined pge:<base>-vintage-pcia "
    "modifiers.")

DEFERRALS = [
    "Sheet 2 Applicability and Exemption table rows 3 and 4 and Special Conditions 2 and 3 (Sheet 6): CCA customers who are former Continuous DA customers (row 3) are exempt from the ECRA, the DWR Bond Charge and the Vintage PCIA, and former Returning Continuous DA customers (row 4) from the ECRA and the DWR Bond Charge; Special Condition 2 states \"Customers that have taken Direct Access (DA) or CCA service continually since February 1, 2001, are exempt from the Wildfire Fund Charge and PCIA portions of the CCA CRS.\" Not modeled: the eligibility rule tests CCA enrollment only, the ECRA and Wildfire Fund Charge Prices these customers are exempt from are in the base plan, and the Vintage PCIA Prices here carry no continuous-service condition. Expressible as a further dimension of the vintage container, as CARE is, for the PCIA half; the base-side half needs offsets of the base's ECRA and Wildfire Fund Charge Prices.",
    "Wildfire Fund Charge exemption for CARE and Medical Baseline CCA customers, Special Condition 1 (Sheet 6): \"California Alternate Rates for Energy (CARE) and medical baseline customers that take CCA service are exempt from paying the Wildfire Fund Charge.\" The charge is a base-plan Price. pge:d-care offsets it for CARE customers and pge:e-1-medical-baseline and pge:e-tou-c-medical-baseline for Medical Baseline customers on those schedules, so a CARE or Medical Baseline CCA customer composes the base with two modifiers, this one and that one.",
    "Medical Baseline Vintage PCIA, Sheet 2 row 2 against Special Condition 1 (Sheet 6). Sheet 2 row 2 (Cal. P.U.C. Sheet 47286-E, effective May 6, 2021) marks \"CCA Medical Baseline or CARE\" Exempt from the Vintage PCIA. Special Condition 1 (Cal. P.U.C. Sheet 58892-E, effective January 24, 2025) governs Medical Baseline: \"Prior to January 1, 2022 Medical Baseline customers were exempt from the PCIA portion of the CCA CRS. For any CCA that begins serving residential customers on or after January 1, 2022, Medical Baseline customers of that CCA will not receive the PCIA exemption. For CCAs that are serving residential customers as of the date PG&E begins charging the PCIA to medical baseline customers, the full PCIA amount will be phased-in over a period of 4 years. The applicable PCIA obligation expressed as a percentage of the full otherwise applicable PCIA obligation will be 25% in the first year, 50% in the second year, 75% in the third year, and 100% in the fourth year.\" This filing charges a Medical Baseline customer the full Vintage PCIA. The phase-in percentages are not modeled: the sheet does not state the date PG&E began charging the PCIA to Medical Baseline customers, and the percentage depends on it and on when the customer's CCA began serving residential customers, which URPX carries no attribute for. Special Condition 1 is silent on CARE, so the Sheet 2 row 2 CARE exemption stands and is modeled.",
    "PCIA vintage determination, Sheet 1: \"If any of these occur in the first six months of the calendar year (e.g. 2010), the CCA customers are assigned the CRS for the prior year (i.e. 2009 vintage). If the commitment by the CCA occurs July 1 or later, the CCA customers are assigned the CRS for the current year (2010 vintage in this example).\" Special Condition 5 (Sheet 6) keeps a continuously served customer's vintage across changes of commodity service provider. This filing takes departureVintage as a supplied customer attribute; the rules that set and retain it define the attribute rather than gate a Price, and v0.5.1 has no vocabulary that derives an operand.",
    "Sheets 3 to 5 price twelve customer classes (Residential, Small, Medium and Large Commercial, Streetlights, Standby, Agriculture, E-20T/B-20T, E-20P/B-20P, E-20S/B-20S, BEV1, BEV2); this filing carries the Residential row, the class of every base plan urpx:applicableToRatePlan names.",
]


def write_filing(root: Path, src_pdf: Path) -> None:
    d = root / f"us/ca/pge/electricity/cca-crs/versions/{DATE}"
    if d.exists():
        sys.exit(f"{d} already exists")
    if hashlib.sha256(src_pdf.read_bytes()).hexdigest() != SHA:
        sys.exit(f"{src_pdf}: sha256 is not {SHA}")
    check_sheets(src_pdf)
    check_bases_carry_crs(root)
    g = load(base_path(root, "e-tou-c", "2026-06-01"))
    programs = [n for n in g["@graph"] if n.get("@id") in ("pge:program-care", "pge:program-cca")]
    org = []
    walk(g, lambda o: org.append(o) if o.get("@id") == "org:utility-pge" and "urpx:legalName" in o else None)
    d.mkdir(parents=True)
    shutil.copyfile(src_pdf, d / f"pge_cca-crs_{DATE}.pdf")
    dump(d / f"rate-plan-modifier_pge_cca-crs_{DATE}.jsonld", build(root, programs, org[0]))
    lines = [
        "# Identity --------------------------------------------------------------------",
        'utility = "pge"', 'schedule = "cca-crs"', f'effective_date = "{DATE}"', "",
        "# Source ----------------------------------------------------------------------",
        "[source]", f'url = "{URL}"', f'sha256 = "{SHA}"', f'retrieved_on = "{RETRIEVED}"',
        'media_type = "application/pdf"', 'filing_type = "advice-letter"', 'filing_id = "PGE-AL-7797-E"', "",
        "# Regulatory ------------------------------------------------------------------",
        "[regulator]", 'authority = "puc"', "",
        "# Extraction ------------------------------------------------------------------",
        "[extraction]", 'tool = "mineru"', 'tool_version = "3.2.3"', f'extracted_on = "{TODAY}"',
        'notes = """', NOTES.strip(), '"""', "",
        "# Validation ------------------------------------------------------------------",
        "[validation]", "shacl_passed = true", 'validator = "clj-shacl + clj-urpx (URPX v0.5.1)"',
        f'validated_on = "{TODAY}"', "",
        "# Modeling -------------------------------------------------------------------",
        "[modeling]", "complete = false", "deferrals = [", *[" " + toml_str(x) + "," for x in DEFERRALS], "]", "",
        "# Review ----------------------------------------------------------------------",
        "[review]", 'status = "draft"',
        "notes = " + toml_str("Authored by dev/author_pge_cca_crs.py, which checks every Vintage PCIA value against the Residential row of its sheet in the committed PDF and the Sheet 3 ECRA, Wildfire Fund Charge and Ongoing CTC against each base's own Prices."),
        "",
    ]
    text = "\n".join(lines)
    import tomli
    tomli.loads(text)
    (d / "tariff.toml").write_text(text, encoding="utf-8")


NOTES = """
Source bytes. data/documents/pge/ELEC_SCHEDS_CCA-CRS.pdf, fetched 2026-09-23 by
dev/fetch_tariff_documents.py; PG&E's server still reported Last-Modified
Wed, 31 Dec 2025 23:18:32 GMT and the same length on 2026-10-11.

Sheets in force. Sheet 1 (52000-E, Advice 6413-E) effective November 22, 2021;
Sheet 2 (47286-E, Advice 5932-E) effective May 6, 2021; Sheets 3 to 5 (60676-E
to 60678-E, Advice 7797-E) effective January 1, 2026; Sheet 6 (58892-E,
Advice 7432-E) effective January 24, 2025. This version is dated by its newest
sheets. The schedule states no date of first introduction, so
urpx:initialEffectiveDate carries this version's date, as pge:d-care does.

Reading. MinerU 3.2.3 (pipeline backend) misplaces cells in the Sheet 4 table
(its Residential row shows $0.03608, the Small Commercial 2016 value), so the
Residential row was read from pdftotext -layout, and dev/author_pge_cca_crs.py
checks every Vintage PCIA value against it.

What the base plans carry. Sheet 3: "The rates listed below are currently
reflected in each individual applicable rate schedule and are consolidated
below to increase the visibility of the CRS rates across customer classes and
vintages." The Residential ECRA ($0.00002), Wildfire Fund Charge ($0.00591)
and Ongoing CTC ($0.00027) equal the Prices of every base version this
modifier applies to, and the eighteen Residential Vintage PCIA rates equal the
vintage tables of Schedules E-1, E-ELEC, E-TOU-C, E-TOU-D and EV2.
"""


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    write_filing(root, root / "data/documents/pge/ELEC_SCHEDS_CCA-CRS.pdf")
    for base, dates in BASES.items():
        for date in dates:
            add_summary(root, base, date)
            edit_manifest(root, base, date)
        if base in VINTAGE_MODIFIER:
            narrow_vintage(root, base)
    edit_readmes(root)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
