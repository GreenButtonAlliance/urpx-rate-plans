#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Author the PG&E Medical Baseline modifiers for Schedules E-1 and E-TOU-C.

PG&E Electric Rule 19, Part A: "The Standard Medical Baseline Quantity is 16.438
kWh per day (approximately) year-round." E-1 Special Condition 7 and E-TOU-C
Special Condition 5 add it to the baseline quantity (Code B plus it is Code M,
Code H plus it is Code S) "to increase the maximum level of usage subject to
baseline (Tier 1) rates". Each base version whose ladder it moves gains, as a
second document in its directory, one version of a modifier whose adjusting
brackets (urpx-org/urpx#80) add:

  - 16.438 to Tier 1's upper bound and Tier 2's lower bound, and
  - 65.752, four times 16.438, to Tier 2's upper bound and Tier 2 Continued's
    lower bound, because Tier 2 ends at four times the baseline quantity and
    the medical quantity is part of it.

The quantity is the same in every territory, code and season, so the brackets
name a tier and nothing else: four on E-TOU-C, whose three tiers carry season on
their brackets, and eight on E-1, whose six tiers are season-specific. Rule 19
gives 16.438 as the hand-calculation figure and says automated billing uses the
unrounded quotient 6,000 / 365; the modifiers carry 16.438, the figure printed.

Each version also carries the Wildfire Fund Charge exemption as a Price at
urpx:multiplier -1 over its base version's Wildfire Fund Charge Price, the shape
pge:d-care uses.

Rule 19 is vendored in each base version's directory and is a second [source] in
its manifest. The manifests' deferrals on the medical quantities and the medical
half of the Wildfire Fund exemption are replaced.

Re-running is safe: the modifiers are rewritten from the tables below each time.

Run from the repo root: python3 dev/author_pge_medical_baseline.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PGE = REPO / "us/ca/pge/electricity"

STANDARD = "16.438"
FOUR_TIMES = "65.752"
RULE_19_URL = "https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_RULES_19.pdf"
RULE_19_PDF = "pge_rule-19_2023-03-23.pdf"
RULE_19_RETRIEVED = "2026-10-07"
EVALUATED_ON = "2026-10-07T00:00:00"


class Target:
    def __init__(self, sched, date, adjust, sheets):
        self.sched, self.date, self.adjust, self.sheets = sched, date, adjust, sheets

    @property
    def dir(self) -> Path:
        return PGE / self.sched / "versions" / self.date

    @property
    def base(self) -> Path:
        return self.dir / f"rate-plan_pge_{self.sched}_{self.date}.jsonld"

    @property
    def path(self) -> Path:
        return self.dir / f"rate-plan-modifier_pge_{self.sched}-medical-baseline_{self.date}.jsonld"

    @property
    def bv(self) -> str:
        return f"pge:{self.sched}-{self.date}"

    @property
    def m(self) -> str:
        return f"pge:{self.sched}-medical-baseline"

    @property
    def v(self) -> str:
        return f"{self.m}-{self.date}"


def etou_c_adjust(bv: str) -> list[tuple[str, str, str]]:
    """(tier @id, offset property, offset) for E-TOU-C's three-tier ladder."""
    return [(f"{bv}-tier-baseline-t1", "urpx:upperBoundOffset", STANDARD),
            (f"{bv}-tier-baseline-t2", "urpx:lowerBoundOffset", STANDARD),
            (f"{bv}-tier-baseline-t2", "urpx:upperBoundOffset", FOUR_TIMES),
            (f"{bv}-tier-baseline-t2c", "urpx:lowerBoundOffset", FOUR_TIMES)]


def e1_adjust(bv: str) -> list[tuple[str, str, str]]:
    # The 2026-03-01 version's six tiers predate version scoping (pge:tier-summer-t1);
    # later versions scope them to the version.
    stem = "pge:" if bv == "pge:e-1-2026-03-01" else f"{bv}-"
    out = []
    for season in ("summer", "winter"):
        out += [(f"{stem}tier-{season}-t1", "urpx:upperBoundOffset", STANDARD),
                (f"{stem}tier-{season}-t2", "urpx:lowerBoundOffset", STANDARD),
                (f"{stem}tier-{season}-t2", "urpx:upperBoundOffset", FOUR_TIMES),
                (f"{stem}tier-{season}-t2c", "urpx:lowerBoundOffset", FOUR_TIMES)]
    return out


E1_SHEETS = {
    "name": "E-1",
    "sc": "Special Condition 7 (Sheet 5, Cal. P.U.C. Sheet 61100-E)",
    "sc_baseline": "Special Condition 2",
    "wfc": "Sheet 1, Cal. P.U.C. Sheet 61247-E, and Special Condition 12, Sheet 7, Cal. P.U.C. Sheet 61102-E",
    "ladder": ("Sheet 1 prints Tier 2 as \"Tier 2 Usage (101% - 400% of Baseline)\" and Tier 2 Continued as "
               "\"Over 400% of Baseline\"."),
}
ETOUC_SHEETS = {
    "name": "E-TOU-C",
    "sc": "Special Condition 5 (Sheet 6, Cal. P.U.C. Sheet 61129-E)",
    "sc_baseline": "Special Condition 1",
    "wfc": "Sheet 1, Cal. P.U.C. Sheet 61124-E, and Special Condition 11, Sheet 10, Cal. P.U.C. Sheet 61133-E",
    "ladder": ("The base version's ladder ends Tier 2 at four times the Special Condition 1 quantity, the Tier 2 "
               "that Schedule E-1 prints as \"Tier 2 Usage (101% - 400% of Baseline)\"; no E-TOU-C sheet states "
               "the 400 percent figure, which the base version's manifest records as a deferral."),
}

# Sheet 1 of E-1 was reissued 2026-06-01 (Advice 7921-E) as 61362-E.
E1_SHEETS_0601 = dict(E1_SHEETS, wfc=E1_SHEETS["wfc"].replace("61247-E", "61362-E"))

TARGETS = [
    Target("e-1", "2026-03-01", e1_adjust, E1_SHEETS),
    Target("e-1", "2026-06-01", e1_adjust, E1_SHEETS_0601),
    Target("e-tou-c", "2026-03-01", etou_c_adjust, ETOUC_SHEETS),
    Target("e-tou-c", "2026-03-27", etou_c_adjust, ETOUC_SHEETS),
    Target("e-tou-c", "2026-06-01", etou_c_adjust, ETOUC_SHEETS),
]


def ref(i: str) -> dict:
    return {"@id": i}


def find(x, i):
    if isinstance(x, dict):
        if x.get("@id") == i:
            return x
        for v in x.values():
            r = find(v, i)
            if r is not None:
                return r
    elif isinstance(x, list):
        for v in x:
            r = find(v, i)
            if r is not None:
                return r
    return None


def description(t: Target) -> str:
    s = t.sheets
    n = len(t.adjust(t.bv))
    shape = ("one per season for each of the four bounds, because each of the six base tiers is season-specific"
             if t.sched == "e-1" else
             "one for each of the four bounds, because the base tiers carry season on their own brackets")
    return (
        "PG&E Electric Rule 19, Part A: \"The Standard Medical Baseline Quantity is 16.438 kWh per day "
        f"(approximately) year-round.\" Schedule {s['name']} {s['sc']}: \"Standard medical quantities are added "
        f"to the baseline usage from {s['sc_baseline']} to increase the maximum level of usage subject to baseline "
        "(Tier 1) rates.\" Its heading names the two results: Code M, Basic Plus Medical Quantities, is Code B "
        "plus the medical quantity, and Code S, All-Electric Plus Medical Quantities, is Code H plus it. "
        f"This version adds 16.438 kWh per day to the Tier 1 upper bound and the Tier 2 lower bound of {t.bv}, "
        "and 65.752 kWh per day, four times 16.438, to the Tier 2 upper bound and the Tier 2 Continued lower "
        "bound, because Tier 2 ends at four times the baseline quantity and the medical quantity is part of the "
        f"baseline. {s['ladder']} The quantity is the "
        f"same in every baseline territory, code and season, so each of the {n} urpx:ServiceBracket here names "
        f"one base tier with urpx:adjustsServiceTier and no territory, code or season, {shape}; the Code B or "
        "Code H cell selected on the base decides which bound moves. Rule 19 Part A also states that \"The "
        "Standard Medical Baseline Quantity used for automated billing is calculated using the unrounded quotient "
        "of the following equation: 6,000 kWh per year divided by 365 days. Any billing that requires hand "
        "calculations will use 16.438 kWh per day.\" The quotient (16.438356...) has no terminating decimal "
        "form, so this version carries 16.438, the figure Rule 19 prints. Customers receiving a medical baseline "
        f"allowance do not pay the Wildfire Fund Charge ({s['wfc']}: the charge \"applies to all retail sales, "
        "excluding CARE and Medical Baseline sales\"), so this version also carries an exemption Price at "
        f"urpx:multiplier -1 over {t.bv}-price-wildfire-fund, the shape pge:d-care uses. urpx:adjustsServiceTier, "
        "urpx:lowerBoundOffset and urpx:upperBoundOffset are proposed in urpx-org/urpx#80 and are in no URPX "
        "release.")


def evaluation(t: Target) -> str:
    return (
        "Rule 19 Part F's Additional Medical Baseline Quantities, which PG&E assigns case by case in increments "
        "of 16.438 kWh per day, are not carried: this version adds one Standard Medical Baseline Quantity. The "
        "offsets are kWh per day, as are the bounds they adjust, and this document does not state how a "
        "consumer scales either to a billing period. The adjusting brackets name the tier @ids of "
        f"{t.bv}, so a later version of the schedule needs its own version of this modifier. A customer on both "
        "CARE and Medical Baseline is exempt from the Wildfire Fund Charge once, but pge:d-care and this modifier "
        "each carry a -1 multiple of the same Price, so a composition holding both would credit it twice; the "
        "one-modifier composition policy in this repository never builds that composition.")


def modifier(t: Target) -> dict:
    base = json.loads(t.base.read_text(encoding="utf-8"))
    bversion = base["@graph"][0]["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]
    ctx = dict(base["@context"])
    for k, typ in (("urpx:lowerBoundOffset", "xsd:decimal"), ("urpx:upperBoundOffset", "xsd:decimal"),
                   ("urpx:multiplier", "xsd:decimal"), ("urpx:pageStart", "xsd:integer"),
                   ("urpx:pageEnd", "xsd:integer")):
        ctx.setdefault(k, {"@type": typ})
    for k in ("urpx:lowerBound", "urpx:upperBound"):
        ctx.pop(k, None)
    window = {k: bversion[k] for k in ("urpx:effectiveDateTime", "urpx:expirationDateTime") if k in bversion}
    v = t.v
    spec = {"@type": "urpx:MetricSpecification", "@id": f"{v}-ms-energy",
            "urpx:measurementKind": ref("urpx:energy"), "urpx:unitOfMeasure": ref("urpx:kWh")}
    for tier, _, _ in t.adjust(t.bv):
        if find(base, tier) is None:
            raise SystemExit(f"{t.bv}: tier {tier} not found")
    wfc = f"{t.bv}-price-wildfire-fund"
    if find(base, wfc) is None:
        raise SystemExit(f"{t.bv}: {wfc} not found")
    brackets = []
    for tier, prop, offset in t.adjust(t.bv):
        local = tier.split(":", 1)[1].replace(f"{t.sched}-{t.date}-", "")
        bound = "upper" if prop == "urpx:upperBoundOffset" else "lower"
        brackets.append({"@type": "urpx:ServiceBracket", "@id": f"{v}-bracket-{local}-{bound}",
                         "urpx:adjustsServiceTier": ref(tier), prop: offset})
    cx = f"{v}-cx-eligible"
    return {
        "@context": ctx,
        "@type": "urpx:URPXPackage",
        "@id": f"pge:doc-{t.sched}-medical-baseline-{t.date}",
        "urpx:targetURPXVersion": base["@graph"][0]["urpx:targetURPXVersion"],
        "urpx:hasRatePlanModifier": {
            "@type": "urpx:RatePlanModifier",
            "@id": t.m,
            "urpx:name": f"Schedule {t.sheets['name']} Standard Medical Baseline Quantity (Electric Rule 19)",
            "urpx:modifierUniqueIdentifier": f"{t.sheets['name']}-MEDICAL-BASELINE",
            "urpx:initialEffectiveDate": "2023-03-23",
            "urpx:timezoneIdentifier": "America/Los_Angeles",
            "urpx:hasRatePlanModifierVersion": {
                "@type": "urpx:RatePlanModifierVersion",
                "@id": v,
                "urpx:version": t.date,
                "urpx:modifierVersionNumber": t.date,
                "urpx:changeReason": ref("urpx:rateCase"),
                "urpx:description": description(t),
                **window,
                "urpx:priceCurrency": "USD",
                "urpx:commodity": ref("urpx:electricity"),
                "urpx:serviceRole": ref("urpx:bundledServiceRole"),
                "urpx:applicableToRatePlan": [ref(f"pge:{t.sched}")],
                "urpx:hasDataSourceReference": {
                    "@type": "urpx:DataSourceReference",
                    "@id": f"{v}-data-source-reference",
                    "urpx:fileName": "ELEC_RULES_19.pdf",
                    "urpx:mediaType": ref("urpx:applicationPdf"),
                    "urpx:accessURL": RULE_19_URL,
                    "urpx:dateRetrieved": RULE_19_RETRIEVED,
                    "urpx:dataSourceType": ref("urpx:utilityWebsiteSource"),
                    "urpx:pageStart": 1, "urpx:pageEnd": 3,
                    "urpx:leafStart": "55539-E", "urpx:leafEnd": "55541-E"},
                "urpx:hasEligibilityRule": [{
                    "@type": "urpx:EligibilityRule",
                    "@id": f"{v}-er-eligible",
                    "urpx:name": "Customer certified for Medical Baseline under Electric Rule 19",
                    "urpx:description": (
                        "Rule 19 Part B: \"To qualify for a Standard Medical Baseline Quantity, you must certify "
                        "in writing that you or a full-time resident in your home is\" dependent on a life-support "
                        "device used in the home, a paraplegic, hemiplegic or quadriplegic person or a multiple "
                        "sclerosis patient with special heating or cooling needs, a person being treated for a "
                        "life-threatening illness or with a compromised immune system with special heating or "
                        "cooling needs, or a scleroderma patient with special heating needs, with other conditions "
                        "reviewed individually. Part C sets recertification every four years for a permanent "
                        "condition and every two years otherwise. Carried as one enrollment condition, as "
                        "sce:medical-baseline carries it."),
                    "urpx:hasConditionExpression": {
                        "@type": "urpx:ConditionExpression", "@id": cx,
                        "urpx:rootNode": {
                            "@type": "urpx:ComparisonNode", "@id": f"{cx}-root-node",
                            "urpx:operator": ref("urpx:equalsOperator"),
                            "urpx:leftOperand": {"@type": "urpx:CustomOperandNode",
                                                 "@id": f"{cx}-root-node-left-operand",
                                                 "urpx:customConditionProperty": "Program Enrollment"},
                            "urpx:rightOperand": {"@type": "urpx:CustomOperandNode",
                                                  "@id": f"{cx}-root-node-right-operand",
                                                  "urpx:stringValue": "Medical Baseline"}}}}],
                "urpx:hasPlanElements": {
                    "@type": "urpx:PlanElements",
                    "@id": f"{v}-plan-elements",
                    "urpx:hasMetricInput": [{
                        "@type": "urpx:MetricInput", "@id": f"{v}-mi-energy",
                        "urpx:name": "kWh Energy Consumption",
                        "urpx:metricInputType": ref("urpx:measuredMetricInput"),
                        "urpx:hasMetricSpecification": spec}],
                    "urpx:hasBillingModel": {
                        "@type": "urpx:BillingModel",
                        "@id": f"{v}-plan-elements-billing-model",
                        "urpx:hasServiceTiers": [{
                            "@type": "urpx:ServiceTiers", "@id": f"{v}-tiers-medical",
                            "urpx:referencesMetricInput": ref(f"{v}-mi-energy"),
                            "urpx:hasServiceTier": [{
                                "@type": "urpx:ServiceTier", "@id": f"{v}-tier-medical-host",
                                "urpx:name": (f"Standard Medical Baseline Quantity, added to the {t.sheets['name']} "
                                              "baseline ladder"),
                                "urpx:hasServiceBracket": brackets}]}],
                        "urpx:hasLedger": [{
                            "@type": "urpx:Ledger", "@id": f"{v}-ledger-wildfire-fund-exemption",
                            "urpx:name": "Medical Baseline Wildfire Fund Charge exemption",
                            "urpx:ledgerType": ref("urpx:bundledLedger"),
                            "urpx:referencesMetricInput": ref(f"{v}-mi-energy")}],
                        "urpx:hasPriceDefinition": [{
                            "@type": "urpx:PriceDefinition", "@id": f"{v}-pd-wildfire-fund-exemption",
                            "urpx:name": "Medical Baseline Wildfire Fund Charge exemption",
                            "urpx:chargeType": ref("urpx:creditEnergy"),
                            "urpx:chargeCategory": ref("urpx:discount"),
                            "urpx:billPortion": ref("urpx:bundledPortion"),
                            "urpx:referencesLedger": ref(f"{v}-ledger-wildfire-fund-exemption")}]}},
                "urpx:hasPrices": {
                    "@type": "urpx:Prices", "@id": f"{v}-prices",
                    "urpx:hasPrice": [{
                        "@type": "urpx:Price", "@id": f"{v}-price-wildfire-fund-exemption",
                        "urpx:name": f"Medical Baseline Wildfire Fund Charge exemption: the negative of {wfc}",
                        "urpx:referencesPriceDefinition": ref(f"{v}-pd-wildfire-fund-exemption"),
                        "urpx:multiplier": "-1",
                        "urpx:basedOnPrice": [ref(wfc)],
                        "urpx:startDate": t.date}]},
                "urpx:offeredBy": copy.deepcopy(bversion["urpx:offeredBy"]),
                "urpx:forRatePlanModifier": ref(t.m),
                "urpx:hasCoverageClaim": {
                    "@id": f"pge:cc-{t.sched}-medical-baseline-{t.date}", "@type": "urpx:CoverageClaim",
                    "urpx:completenessResult": ref("urpx:partial"),
                    "urpx:selfContained": False,
                    "urpx:explainedBy": {
                        "@type": "urpx:Evaluation", "@id": f"pge:cc-{t.sched}-medical-baseline-{t.date}-evaluation",
                        "urpx:evaluationKind": ref("urpx:coverageEvaluation"),
                        "urpx:description": evaluation(t),
                        "urpx:evaluatedOn": EVALUATED_ON}}}}}


# --- base documents and manifests --------------------------------------------

def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def replace_deferral(text: str, prefix: str, new: list[str]) -> str:
    lines = text.split("\n")
    hits = [i for i, line in enumerate(lines) if line.startswith(" " + toml_str(prefix)[:-1])]
    if not hits:
        if all((" " + toml_str(n) + ",") in lines for n in new):
            return text
        raise SystemExit(f"deferral not found: {prefix[:60]}")
    lines[hits[0]:hits[0] + 1] = [" " + toml_str(n) + "," for n in new]
    return "\n".join(lines)


ADDITIONAL = (
    "Rule 19 Part F: \"If PG&E finds that you need more than the standard 16.438 kWh per day, it will increase your "
    "daily Medical Baseline Quantity. In determining how many Additional Quantities you will be assigned, PG&E will "
    "round its calculation of your total daily kWh medical needs up to the nearest increment of 16.438 kWh.\" "
    "{m} carries one Standard Medical Baseline Quantity. An additional quantity is a per-customer multiple PG&E "
    "assigns, so it is a customer attribute rather than a tariff figure; it is expressible as further adjusting "
    "brackets once a multiple is chosen, and nothing in this corpus chooses one.")

WFC_0301 = (
    "Sheet 1 and Special Condition 11 (Sheet 10, Cal. P.U.C. Sheet 61133-E) exempt CARE and Medical Baseline sales "
    "from the Wildfire Fund Charge. The Medical Baseline half is pge:e-tou-c-medical-baseline-2026-03-01, whose "
    "exemption Price is urpx:multiplier -1 over this version's Wildfire Fund Charge Price. The CARE half is not "
    "carried for this version: pge:d-care's exemption names the 2026-03-27 version's Price, not this one's, so a "
    "CARE customer under this version is priced $0.00591 per kWh.")


WFC_EVAL_OLD = (
    "The Wildfire Fund Charge exemption: Sheet 1 states that customers receiving a medical baseline allowance do not "
    "pay this charge and Special Condition 11 excludes CARE and medical baseline sales from it, but the filing carries "
    "the $0.00591 per kWh charge with no applicability condition, so it is priced for every customer.")
WFC_EVAL_NEW = (
    "The CARE half of the Wildfire Fund Charge exemption: Special Condition 11 excludes CARE and medical baseline "
    "sales from the charge, and the medical baseline half is pge:e-tou-c-medical-baseline-2026-03-01, but "
    "pge:d-care's exemption names the 2026-03-27 version's Price, so a CARE customer under this version is priced "
    "$0.00591 per kWh.")


def review_note(t: Target) -> str:
    return (f" The Standard Medical Baseline Quantity of Electric Rule 19 (Code M and Code S) and the Medical "
            f"Baseline Wildfire Fund Charge exemption are {t.m}, a second document in this directory, whose "
            f"adjusting brackets (urpx-org/urpx#80) move this version's tier bounds; Rule 19 is vendored here as "
            f"{RULE_19_PDF}.")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def manifest(t: Target) -> None:
    p = t.dir / "tariff.toml"
    text = p.read_text(encoding="utf-8")
    pdf = t.dir / RULE_19_PDF
    if "[source.rule_19]" not in text:
        s0 = text.index("[source]\n")
        s1 = text.index("\n\n", s0)
        body = "\n".join("  " + line for line in text[s0 + len("[source]\n"):s1].splitlines())
        text = (text[:s0] + "[source]\n\n  [source.base]\n" + body + "\n\n"
                "  # Electric Rule 19: the Standard Medical Baseline Quantity the second document in this\n"
                "  # directory adds to the baseline ladder.\n"
                "  [source.rule_19]\n"
                f"  url = {toml_str(RULE_19_URL)}\n"
                f'  sha256 = "{sha256(pdf)}"\n'
                f'  retrieved_on = "{RULE_19_RETRIEVED}"\n'
                '  media_type = "application/pdf"\n'
                '  filing_type = "advice-letter"\n'
                '  filing_id = "PGE-AL-6865-E"' + text[s1:])
        r0 = text.index("[regulator]\n")
        r1 = text.index("\n\n", r0)
        body = "\n".join("  " + line for line in text[r0 + len("[regulator]\n"):r1].splitlines())
        text = (text[:r0] + "[regulator]\n  [regulator.base]\n" + body + "\n\n"
                "  [regulator.rule_19]\n"
                '  authority = "puc"\n'
                '  docket = "D.22-11-033"' + text[r1:])
    add = ADDITIONAL.format(m=t.v)
    if (t.sched, t.date) == ("e-1", "2026-03-01"):
        text = replace_deferral(text, "Wildfire Fund Charge exemption not modeled.", [])
        text = replace_deferral(text, "Standard medical quantities are not modeled.", [add])
    elif t.date == "2026-03-01":
        text = replace_deferral(text, "Sheet 1 and Special Condition 11 (Sheet 10, Cal. P.U.C. Sheet 61133-E) exempt "
                                      "CARE and Medical Baseline sales", [WFC_0301])
        text = replace_deferral(text, "Special Condition 5 (Sheet 6, Cal. P.U.C. Sheet 61129-E) adds Code M", [add])
    else:
        text = replace_deferral(text, "Sheet 1 and Special Condition 11 (Sheet 10) exempt CARE and Medical Baseline "
                                      "customers", [add])
    text = text.replace(' "medical-baseline",\n', f' "{t.sched}-medical-baseline",\n')
    marker = '\nnotes = "'
    i = text.index(marker, text.index("[review]"))
    end = text.index('"\n', i + len(marker))
    note = review_note(t)
    if note not in text[i:end]:
        text = text[:end] + note + text[end:]
    p.write_text(text, encoding="utf-8")


def base_prose(t: Target) -> None:
    doc = json.loads(t.base.read_text(encoding="utf-8"))
    version = doc["@graph"][0]["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]
    sentence = (f" The Standard Medical Baseline Quantity of Electric Rule 19 (Code M and Code S) is the modifier "
                f"{t.m}, a second document in this filing's directory.")
    if sentence not in version["urpx:description"]:
        version["urpx:description"] += sentence
    if (t.sched, t.date) == ("e-tou-c", "2026-03-01"):
        ev = version["urpx:hasCoverageClaim"]["urpx:explainedBy"]
        ev["urpx:description"] = ev["urpx:description"].replace(WFC_EVAL_OLD, WFC_EVAL_NEW)
    t.base.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    for t in TARGETS:
        pdf = t.dir / RULE_19_PDF
        if not pdf.exists():
            if src is None:
                raise SystemExit(f"{pdf} is missing; pass the fetched ELEC_RULES_19.pdf as the first argument")
            shutil.copyfile(src, pdf)
        t.path.write_text(json.dumps(modifier(t), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        manifest(t)
        base_prose(t)
        print(f"medical {t.path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
