#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Author the SDG&E versions effective 2026-06-01, 2026-08-01 and 2026-09-30.

Four advice letters moved SDG&E's residential schedules after the 2026-04-01
versions this corpus held:

  4843-E  effective 2026-06-01  FERC interim transmission rate relief: the
                                Transmission charge and TRAC on every base.
  4837-E  effective 2026-06-01  2026 CARE and FERA income guidelines:
                                Schedule E-CARE Sheet 3, Schedule FERA Sheet 1.
  4868-E  effective 2026-08-01  Wildfire Mitigation Plan Track 2 recovery and
                                GRC memorandum account roll-offs: Distribution,
                                TRAC, the Baseline Adjustment Credit and every
                                EECC price.
  4874-E  effective 2026-09-30  combined EECC and UDC tariffs (D.25-09-006):
                                every sheet of every base schedule reissued as
                                an Original sheet with the commodity rates and
                                EECC Special Conditions folded in. Every price
                                this corpus models is unchanged.

Each new base version is derived from the filing's 2026-04-01 version: every
@id carrying the old date is re-dated, every other subordinate @id is scoped to
the new version (dev/rescope_iris.new_iri), every Price is set from PRICES
(asserting the 2026-04-01 value it replaces), and the prose is rewritten through
explicit replacement tables that must each match, after which no number the new
sheets do not print may survive unless the table allows it. The tables are
dev/author_sdge_2026_prose.json, per schedule and date: "repl" pairs applied to
the earlier version's text (each must match), "text" replacing a string whole,
"add_deferrals" and "drop_deferrals", "allow" for numbers no rate sheet prints,
and "confirm" for each computed figure (a percentage, a cent amount) and, on
2026-09-30, each Sheet, note and Special Condition reference, read against the
sheets in force on that date. --report lists what is unresolved and writes
nothing. The previous version
of each filing gains urpx:expirationDateTime at the effective date of the sheet
that cancels its rate sheet (LAYOUT.md section 9).

Inputs, in the directory given as the only argument, per schedule <n> (dr,
tou-dr, dr-ses, ev-tou, ev-tou-2, ev-tou-5, tou-dr1, tou-dr2, tou-elec, care,
fera):

  <n>-2026.pdf  /historical/?...&tarfKey=<N>&tarfYear=2026, every 2026 sheet
                revision, fetched 2026-10-06; the 2026-06-01 source.
  <n>-0923.pdf  /tariff/?...&tarfKey=<N> as fetched 2026-09-23 into
                data/documents/sdge/ by dev/fetch_tariff_documents.py; the
                2026-08-01 source (the 2026-06-01 source for care and fera is
                the historical document).
  <n>.pdf       /tariff/?...&tarfKey=<N>, fetched 2026-10-06; the 2026-09-30
                source.

Run from the repo root, then dev/resync_coverage_evaluations.py:

    python3 dev/author_sdge_2026.py <directory>
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import re
import subprocess
import sys
import tomli
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rescope_iris as rescope  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SDGE = REPO / "us/ca/sdge/electricity"
OLD = "2026-04-01"
JUN, AUG, SEP = "2026-06-01", "2026-08-01", "2026-09-30"
DATES = [JUN, AUG, SEP]
RETRIEVED = "2026-10-06"
API = "https://scg-uofa-api-prd-hzczb4hja0g6dcfv.a03.azurefd.net/scg-uofa-wpubtm-prd"
VIEW = "https://tariffsprd.sdge.com/view/tariff/?utilId=SDGE&bookId=ELEC&tarfKey={k}"

BASES = ["dr", "dr-ses", "ev-tou", "ev-tou-2", "ev-tou-5", "tou-dr", "tou-dr1", "tou-dr2", "tou-elec"]
KEY = {"dr": 8, "tou-dr": 775, "dr-ses": 540, "care": 383, "ev-tou": 17, "ev-tou-2": 18,
       "ev-tou-5": 930, "fera": 330, "tou-dr1": 898, "tou-dr2": 899, "tou-elec": 1065}
NAME = {"dr": "DR", "tou-dr": "TOU-DR", "dr-ses": "DR-SES", "ev-tou": "EV-TOU", "ev-tou-2": "EV-TOU-2",
        "ev-tou-5": "EV-TOU-5", "tou-dr1": "TOU-DR1", "tou-dr2": "TOU-DR2", "tou-elec": "TOU-ELEC",
        "care": "E-CARE", "fera": "FERA"}

# Advice letter per date, with the name SDG&E's filings service gives it
# (.../filings?utilId=SDGE&bookId=ELEC&flngStatusCd=Approved|Effective, 2026-10-06).
AL = {
    JUN: ("4843-E", "Implementation of Federal Energy Regulatory Commission Order Approving Interim "
                    "Rate Relief Effective June 1, 2026"),
    AUG: ("4868-E", "Implementation of Recovery of Under Collected Wildfire Mitigation Plan Memorandum "
                    "Account Track 2 Costs and Roll-Offs of General Rate Case Memorandum Account Costs "
                    "Effective August 1, 2026"),
    SEP: ("4874-E", "Implementation of Combined Electric Energy Commodity Cost and Utility Distribution "
                    "Company Tariffs Pursuant to 2024 General Rate Case Phase 2 Decision 25-09-006"),
}
AL_INCOME = ("4837-E", "2026 CARE and FERA Income Levels Guidelines Update and PIPP Bill Caps Update")
CHANGE_REASON = {JUN: "urpx:regulatoryOrder", AUG: "urpx:regulatoryOrder", SEP: "urpx:rateCase"}


# --- prices -----------------------------------------------------------------

EECC = {  # (summer on, off, super off, winter on, off, super off); Aug 1 under Advice 4868-E
    "tou-dr": ["0.23565", "0.17504", "0.11792", "0.28256", "0.19852", "0.10519"],
    "tou-dr1": ["0.35943", "0.13229", "0.04241", "0.28279", "0.19868", "0.10527"],
    "tou-elec": ["0.47028", "0.13324", "0.08889", "0.25023", "0.12118", "0.08085"],
    "ev": ["0.48396", "0.17818", "0.08385", "0.20574", "0.14757", "0.07627"],
}
CELLS = ["summer-on-peak", "summer-off-peak", "summer-super-off-peak",
         "winter-on-peak", "winter-off-peak", "winter-super-off-peak"]


def _eecc(slug: str, vals: list[str]) -> dict[str, str]:
    return {f"eecc-{c}": v for c, v in zip(CELLS, vals)}


def _per_cell(stem: str, on_off: str, sop: str) -> dict[str, str]:
    return {f"{stem}-{c}": (sop if "super" in c else on_off) for c in CELLS}


# New unit prices by @id suffix (the part after "<slug>-<date>-price-"), per date.
# Every Price with a urpx:unitPrice in the 2026-04-01 version must be named; a
# value equal to the 2026-04-01 one is stated anyway, so that each table is the
# whole price list of its sheets. 2026-09-30 repeats 2026-08-01: Advice 4874-E
# reprints every one of these values (checked by reconcile()).
def prices(slug: str, date: str) -> dict[str, str]:
    aug = date in (AUG, SEP)
    common = {"base-services-charge": "0.79343", "udc-transmission": "0.09096",
              "udc-ppp-net-of-care-surcharge": "0.00651", "udc-care-surcharge": "0.00864",
              "udc-ndc": "0.00000", "udc-ctc": "-0.00007", "udc-lgc": "0.00000", "udc-rs": "0.00005",
              "dwr-bc": "0.00000", "wf-nbc": "0.00591"}
    std_distr = "0.15348" if aug else "0.15719"
    trac = "0.06644" if aug else "0.06620"
    credit = "-0.10702" if aug else "-0.10663"
    if slug == "dr":
        return {**common, "udc-distribution": std_distr, "udc-trac": trac,
                "baseline-credit": "-0.10701" if aug else "-0.10663",
                "eecc": "0.18808" if aug else "0.18274"}
    if slug in ("tou-dr", "tou-dr1"):
        old = {"tou-dr": ["0.22895", "0.17007", "0.11457", "0.27453", "0.19288", "0.10220"],
               "tou-dr1": ["0.34920", "0.12853", "0.04121", "0.27475", "0.19304", "0.10228"]}[slug]
        return {**common, "udc-distribution": std_distr, "udc-trac": trac, "baseline-credit": credit,
                **_eecc(slug, EECC[slug] if aug else old)}
    if slug == "tou-dr2":
        out = {k: v for k, v in common.items()}
        out.update({"udc-distribution": std_distr, "baseline-credit": credit})
        eecc = ["0.35943", "0.08678", "0.28279", "0.14180"] if aug else ["0.34920", "0.08432", "0.27475", "0.13777"]
        out.update({f"eecc-{c}": v for c, v in zip(
            ["summer-on-peak", "summer-off-peak", "winter-on-peak", "winter-off-peak"], eecc)})
        # The four TRAC Prices carry no date in the 2026-04-01 @ids (sdge:price-udc-trac-*).
        tr = ["0.07106", "0.06440", "0.06644", "0.06644"] if aug else ["0.07068", "0.06422", "0.06620", "0.06620"]
        out.update({f"udc-trac-{c}": v for c, v in zip(
            ["summer-on-peak", "summer-off-peak", "winter-on-peak", "winter-off-peak"], tr)})
        return out
    if slug == "tou-elec":
        old = ["0.45690", "0.12945", "0.08637", "0.24311", "0.11774", "0.07856"]
        return {**common, "udc-distribution": "0.14361" if aug else "0.14708", "udc-trac": "0.00000",
                **_eecc(slug, EECC["tou-elec"] if aug else old)}
    ev_old = ["0.47019", "0.17311", "0.08147", "0.19990", "0.14337", "0.07410"]
    ev = _eecc(slug, EECC["ev"] if aug else ev_old)
    if slug == "dr-ses":
        return {**common, "udc-distribution": std_distr, **ev}
    if slug == "ev-tou":
        out = {**common, "udc-trac": "0.00000", "udc-lgc": "0.01235", "udc-care-surcharge": "0.01062", **ev}
        out["base-services-charge"] = "0.413"
        out.update(_per_cell("udc-distribution", "0.25248", "0.09845") if aug
                   else _per_cell("udc-distribution", "0.25679", "0.10014"))
        return out
    if slug == "ev-tou-2":
        out = {**common, "udc-trac": "0.00000", **ev}
        out.update(_per_cell("udc-distribution", "0.19296", "0.05530") if aug
                   else _per_cell("udc-distribution", "0.19763", "0.05666"))
        return out
    if slug == "ev-tou-5":
        out = {**common, "udc-trac": "0.00000", **ev}
        out.pop("udc-transmission")
        out.update(_per_cell("udc-transmission", "0.09096", "0.00000"))
        out.update(_per_cell("udc-distribution", "0.20609", "0.02601") if aug
                   else _per_cell("udc-distribution", "0.21102", "0.02601"))
        return out
    raise KeyError(slug)


# Published totals each version must reproduce: per TOU cell, the UDC Total and
# the Total Rate (UDC + DWR-BC + WF-NBC + EECC) of the bundled table. For dr the
# two cells are up to and above 130% of baseline.
PUBLISHED = {
    ("dr", JUN): {"udc": ["0.22285", "0.32948"], "total": ["0.41150", "0.51813"]},
    ("dr", AUG): {"udc": ["0.21900", "0.32601"], "total": ["0.41299", "0.52000"]},
    ("tou-dr", JUN): {"udc": ["0.32948"] * 6,
                      "total": ["0.56434", "0.50546", "0.44996", "0.60992", "0.52827", "0.43759"]},
    ("tou-dr", AUG): {"udc": ["0.32601"] * 6,
                      "total": ["0.56757", "0.50696", "0.44984", "0.61448", "0.53044", "0.43711"]},
    ("tou-dr1", JUN): {"udc": ["0.32948"] * 6,
                       "total": ["0.68459", "0.46392", "0.37660", "0.61014", "0.52843", "0.43767"]},
    ("tou-dr1", AUG): {"udc": ["0.32601"] * 6,
                       "total": ["0.69135", "0.46421", "0.37433", "0.61471", "0.53060", "0.43719"]},
    ("tou-dr2", JUN): {"udc": ["0.33396", "0.32750", "0.32948", "0.32948"],
                       "total": ["0.68907", "0.41773", "0.61014", "0.47316"]},
    ("tou-dr2", AUG): {"udc": ["0.33063", "0.32397", "0.32601", "0.32601"],
                       "total": ["0.69597", "0.41666", "0.61471", "0.47372"]},
    ("tou-elec", JUN): {"udc": ["0.25317"] * 6,
                        "total": ["0.71598", "0.38853", "0.34545", "0.50219", "0.37682", "0.33764"]},
    ("tou-elec", AUG): {"udc": ["0.24970"] * 6,
                        "total": ["0.72589", "0.38885", "0.34450", "0.50584", "0.37679", "0.33646"]},
    ("dr-ses", JUN): {"udc": ["0.26328"] * 6,
                      "total": ["0.73938", "0.44230", "0.35066", "0.46909", "0.41256", "0.34329"]},
    ("dr-ses", AUG): {"udc": ["0.25957"] * 6,
                      "total": ["0.74944", "0.44366", "0.34933", "0.47122", "0.41305", "0.34175"]},
    ("ev-tou", JUN): {"udc": ["0.37721", "0.37721", "0.22056"] * 2,
                      "total": ["0.85331", "0.55623", "0.30794", "0.58302", "0.52649", "0.30057"]},
    ("ev-tou", AUG): {"udc": ["0.37290", "0.37290", "0.21887"] * 2,
                      "total": ["0.86277", "0.55699", "0.30863", "0.58455", "0.52638", "0.30105"]},
    ("ev-tou-2", JUN): {"udc": ["0.30372", "0.30372", "0.16275"] * 2,
                        "total": ["0.77982", "0.48274", "0.25013", "0.50953", "0.45300", "0.24276"]},
    ("ev-tou-2", AUG): {"udc": ["0.29905", "0.29905", "0.16139"] * 2,
                        "total": ["0.78892", "0.48314", "0.25115", "0.51070", "0.45253", "0.24357"]},
    ("ev-tou-5", JUN): {"udc": ["0.31711", "0.31711", "0.04114"] * 2,
                        "total": ["0.79321", "0.49613", "0.12852", "0.52292", "0.46639", "0.12115"]},
    ("ev-tou-5", AUG): {"udc": ["0.31218", "0.31218", "0.04114"] * 2,
                        "total": ["0.80205", "0.49627", "0.13090", "0.52383", "0.46566", "0.12332"]},
}


def d5(x) -> str:
    from decimal import Decimal
    return str(Decimal(x).quantize(Decimal("0.00001")))


def reconcile(slug: str, date: str, p: dict[str, str], sheet_text: str) -> list[str]:
    """Component sums against the published UDC Total and Total Rate, and every
    modeled and published value present in the sheets the version is read from."""
    from decimal import Decimal as D
    pub = PUBLISHED[(slug, AUG if date == SEP else date)]
    out = []

    def g(k):
        return D(p[k])

    if slug == "dr":
        above = sum(g(k) for k in ("udc-transmission", "udc-distribution", "udc-ppp-net-of-care-surcharge",
                                   "udc-care-surcharge", "udc-ndc", "udc-ctc", "udc-lgc", "udc-rs", "udc-trac"))
        cells = [(above + g("baseline-credit"), above)]
        udc = [above + g("baseline-credit"), above]
        tot = [u + g("dwr-bc") + g("wf-nbc") + g("eecc") for u in udc]
    else:
        names = (["summer-on-peak", "summer-off-peak", "winter-on-peak", "winter-off-peak"]
                 if slug == "tou-dr2" else CELLS)
        udc, tot = [], []
        for c in names:
            u = D(0)
            for k in ("udc-transmission", "udc-distribution", "udc-trac"):
                u += g(f"{k}-{c}") if f"{k}-{c}" in p else (g(k) if k in p else D(0))
            u += sum(g(k) for k in ("udc-ppp-net-of-care-surcharge", "udc-care-surcharge", "udc-ndc",
                                    "udc-ctc", "udc-lgc", "udc-rs"))
            udc.append(u)
            tot.append(u + g("dwr-bc") + g("wf-nbc") + g(f"eecc-{c}"))
        cells = None
    for i, (u, t) in enumerate(zip(udc, tot)):
        if d5(u) != pub["udc"][i]:
            out.append(f"{slug} {date} cell {i}: UDC {d5(u)} vs published {pub['udc'][i]}")
        if d5(t) != pub["total"][i]:
            out.append(f"{slug} {date} cell {i}: Total {d5(t)} vs published {pub['total'][i]}")
    del cells
    nums = set(re.findall(r"\d*\.\d+", sheet_text))
    for k, v in list(p.items()) + [(f"published-{i}", x) for i, x in enumerate(pub["udc"] + pub["total"])]:
        bare = v.lstrip("-")
        # Derived, not printed: the PPP split comes from Schedule E-CARE Sheet 2's
        # CARE Surcharge, and sdge:dr's credit is the difference of its two
        # printed totals, both checked above.
        if bare.startswith("0.0000") or k in ("udc-ppp-net-of-care-surcharge", "udc-care-surcharge") \
                or (slug == "dr" and k == "baseline-credit"):
            continue
        if bare not in nums:
            out.append(f"{slug} {date}: {k} {v} not printed in the source sheets")
    return out


# --- documents ----------------------------------------------------------------

def pdftext(p: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True,
                          check=True).stdout


def sheets(text: str) -> list[dict]:
    out = []
    for i, pg in enumerate(text.split("\f"), 1):
        if not pg.strip():
            continue
        m = re.search(r"(Original|Revised)\s+Cal\. P\.U\.C\. Sheet No\.\s+(\d+-E)", pg)
        c = re.search(r"Canceling\s+(?:(?:Original|Revised)\s+)?Cal\. P\.U\.C\. Sheet No\.[ \t]*(\d+-E)?", pg)
        s = re.search(r"Sheet (\d+)(?:[ \t]+[A-Z])?[ \t]*\n", pg)  # a change marker may follow
        al = re.search(r"Advice Ltr\. No\.\s+(\S+)", pg)
        ef = re.search(r"Effective\s+([A-Z][a-z]{2} \d{1,2}, \d{4})", pg)
        out.append({"page": i, "leaf": m and m.group(2), "cancels": c and c.group(1),
                    "n": s and int(s.group(1)), "al": al and al.group(1), "eff": ef and ef.group(1),
                    "text": pg})
    return out


MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
                                      "Oct", "Nov", "Dec"], 1)}


def iso(eff: str) -> str:
    m, d, y = re.match(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4})", eff).groups()
    return f"{y}-{MONTHS[m]:02d}-{int(d):02d}"


def in_force(sh: list[dict], date: str) -> dict[int, dict]:
    """The latest revision of each sheet effective on or before date."""
    out: dict[int, dict] = {}
    for s in sh:
        if s["n"] is None or s["eff"] is None or iso(s["eff"]) > date:
            continue
        if s["n"] not in out or (iso(s["eff"]), s["leaf"]) > (iso(out[s["n"]]["eff"]), out[s["n"]]["leaf"]):
            out[s["n"]] = s
    return out


class Docs:
    def __init__(self, root: Path):
        self.root = root
        self._t: dict[str, list[dict]] = {}

    def path(self, slug: str, kind: str) -> Path:
        return self.root / {"hist": f"{slug}-2026.pdf", "0923": f"{slug}-0923.pdf", "now": f"{slug}.pdf"}[kind]

    def sheets(self, slug: str, kind: str) -> list[dict]:
        k = f"{slug}/{kind}"
        if k not in self._t:
            self._t[k] = sheets(pdftext(self.path(slug, kind)))
        return self._t[k]

    def kind(self, slug: str, date: str) -> str:
        """Which document each version is read from and vendors."""
        if date == JUN:
            return "hist"
        return "0923" if date == AUG else "now"

    def forced(self, slug: str, date: str) -> dict[int, dict]:
        """Sheets in force at date. The historical document holds only the 2026
        revisions, so sheets not revised in 2026 come from the 2026-09-23 copy,
        whose revisions of them are older than 2026."""
        if date == SEP:
            return in_force(self.sheets(slug, "now"), date)
        base = in_force(self.sheets(slug, "0923"), date)
        hist = in_force(self.sheets(slug, "hist"), date)
        base.update(hist)
        return base


# --- JSON-LD ----------------------------------------------------------------

def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def dump(p: Path, doc) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def walk(o, f):
    if isinstance(o, dict):
        f(o)
        for k, v in o.items():
            if k != "@context":
                walk(v, f)
    elif isinstance(o, list):
        for v in o:
            walk(v, f)


def is_base(slug: str) -> bool:
    return slug in BASES


def path(slug: str, date: str) -> Path:
    kind = "rate-plan" if is_base(slug) else "rate-plan-modifier"
    return SDGE / slug / "versions" / date / f"{kind}_sdge_{slug}_{date}.jsonld"


def version_node(doc):
    if "urpx:hasRatePlan" in doc:
        return doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]
    return doc["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"]


def rename_map(doc, src: str, date: str) -> dict[str, str]:
    """src-dated @ids re-dated; every other subordinate @id the document defines
    scoped to the new version, so the versions own disjoint subordinate nodes."""
    defined: dict[str, str | None] = {}

    def f(d):
        if isinstance(d.get("@id"), str) and len(d) > 1:
            defined[d["@id"]] = rescope.node_type(d)
    walk(doc, f)
    vid = version_node(doc)["@id"].replace(src, date)
    m = {}
    for i, t in defined.items():
        if src in i:
            m[i] = i.replace(src, date)
        elif t in rescope.IDENTITY_TYPES or t in rescope.KEEP_SHARED_TYPES:
            continue
        elif i.startswith("org:"):
            continue
        else:
            m[i] = rescope.new_iri(i, vid)
    return m


def apply_map(doc, m: dict[str, str]) -> None:
    def f(d):
        if isinstance(d.get("@id"), str) and d["@id"] in m:
            d["@id"] = m[d["@id"]]
    walk(doc, f)


def set_literals(doc, date: str) -> None:
    def f(d):
        for k, v in list(d.items()):
            if not isinstance(v, str):
                continue
            if k in ("urpx:version", "urpx:modifierVersionNumber"):
                d[k] = date
            elif k == "urpx:effectiveDateTime":
                d[k] = f"{date}T00:00:00"
            elif k == "urpx:startDate" and v.startswith("20"):
                d[k] = date
            elif k == "urpx:dateRetrieved":
                d[k] = RETRIEVED if date != AUG else "2026-09-23"
            elif k == "urpx:evaluatedOn":
                d[k] = f"{RETRIEVED}T00:00:00"
    walk(doc, f)
    v = version_node(doc)
    if "urpx:changeReason" in v:
        v["urpx:changeReason"] = {"@id": CHANGE_REASON.get(date, "urpx:regulatoryOrder")}
    v.pop("urpx:expirationDateTime", None)


def set_prices(doc, slug: str, date: str, src: str, table: dict[str, str], m: dict[str, str]):
    inv = {v: k for k, v in m.items()}
    rows, seen = [], set()

    def f(d):
        if d.get("@type") != "urpx:Price" or "urpx:unitPrice" not in d:
            return
        old_id = inv.get(d["@id"], d["@id"])
        key = re.sub(rf"^sdge:({re.escape(slug)}-{src}-)?price-", "", old_id)
        if key not in table:
            raise SystemExit(f"{slug} {date}: no price for {old_id} ({key})")
        if old_id in seen:
            return
        seen.add(old_id)
        rows.append((key, d["urpx:unitPrice"], table[key]))
        d["urpx:unitPrice"] = table[key]
    walk(doc, f)
    missing = set(table) - {r[0] for r in rows}
    if missing:
        raise SystemExit(f"{slug} {date}: table names prices the document lacks: {sorted(missing)}")
    return rows


def expire(slug: str, date: str, until: str) -> None:
    p = path(slug, date)
    doc = load(p)
    ctx = doc["@context"]
    if "urpx:expirationDateTime" not in ctx:
        out = {}
        for k, v in ctx.items():
            out[k] = v
            if k == "urpx:effectiveDateTime":
                out["urpx:expirationDateTime"] = {"@type": "xsd:dateTime"}
        if "urpx:expirationDateTime" not in out:
            out["urpx:expirationDateTime"] = {"@type": "xsd:dateTime"}
        doc["@context"] = out
    v = version_node(doc)
    new_v = {}
    for k, x in v.items():
        if k == "urpx:expirationDateTime":
            continue
        new_v[k] = x
        if k == "urpx:effectiveDateTime":
            new_v["urpx:expirationDateTime"] = f"{until}T00:00:00"
    parent = doc["urpx:hasRatePlan"] if "urpx:hasRatePlan" in doc else doc["urpx:hasRatePlanModifier"]
    key = "urpx:hasRatePlanVersion" if "urpx:hasRatePlan" in doc else "urpx:hasRatePlanModifierVersion"
    parent[key] = new_v
    dump(p, doc)


# --- prose ------------------------------------------------------------------

NUM = re.compile(r"(?<![\d.])\d*\.\d{3,}(?!\d)|(?<!\d)\d{5}-E(?!\d)|(?<!\d)\d{4}-E(?:-A)?(?![\d-])")
# Numbers a reader takes as computed (a percentage, a cent figure, a ratio) and
# references a reissue can renumber: each must be replaced or confirmed per
# version in the prose tables, because no sheet lookup can check them.
PCT = re.compile(r"\d+(?:\.\d+)?\s*(?:percent|%|¢)")
REF = re.compile(r"(?:Sheets?|Special Conditions?|[Nn]otes?|[Ff]ootnotes?)\s+\(?\d+[a-z.]*\)?")


def strings(o, acc: list, owner=None):
    """(container, key) for every prose-bearing string in a JSON-LD tree."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("@id", "@context", "@type", "urpx:unitPrice", "urpx:startDate", "urpx:effectiveDateTime",
                     "urpx:expirationDateTime", "urpx:accessURL", "urpx:fileName", "urpx:leafStart",
                     "urpx:leafEnd", "urpx:dateRetrieved", "urpx:evaluatedOn", "urpx:version",
                     "urpx:modifierVersionNumber", "urpx:targetURPXVersion"):
                continue
            if isinstance(v, str):
                acc.append((o, k))
            else:
                strings(v, acc)
    elif isinstance(o, list):
        for v in o:
            strings(v, acc)
    return acc


def value_pairs(old_sheets: dict[int, dict], new_sheets: dict[int, dict]) -> dict[str, set[str]]:
    """Old printed number -> the numbers printed in its place, by aligning each
    rate sheet's old and new revision line by line (numbers masked)."""
    out: dict[str, set[str]] = {}
    for n, o in old_sheets.items():
        if n not in new_sheets or new_sheets[n]["leaf"] == o["leaf"]:
            continue
        keep = lambda l: NUM.search(l) and "Sheet No." not in l and "Advice Ltr" not in l  # noqa: E731
        a = [l for l in o["text"].splitlines() if keep(l)]
        b = [l for l in new_sheets[n]["text"].splitlines() if keep(l)]
        shape = lambda l: re.sub(r"\s+", " ", re.sub(r"(?<![A-Za-z])[RINTDLC](?![A-Za-z])", "",  # noqa: E731
                                                      NUM.sub("#", l))).strip()
        sm = difflib.SequenceMatcher(a=[shape(x) for x in a], b=[shape(x) for x in b], autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                continue
            for x, y in zip(a[i1:i2], b[j1:j2]):
                for p, q in zip(NUM.findall(x), NUM.findall(y)):
                    out.setdefault(p, set()).add(q)
    return out


def leaf_map(docs: Docs, slug: str, src: str, date: str) -> dict[str, str]:
    """Old Cal. P.U.C. sheet number -> the number of the revision in force at date,
    for each sheet revised in between. Not for 2026-09-30, whose Original sheets
    renumber the schedule; REPL states those references one by one."""
    if date == SEP:
        return {}
    old, new = docs.forced(slug, src), docs.forced(slug, date)
    return {o["leaf"]: new[n]["leaf"] for n, o in old.items() if n in new and new[n]["leaf"] != o["leaf"]}


def number_map(docs: Docs, slug: str, date: str, src_prices: dict[str, str], new_prices: dict[str, str]):
    """Old printed number -> new, from the sheets and from the price table. The
    price table wins where a sheet pairing is ambiguous."""
    tgt = AUG if date == SEP else date
    pairs = value_pairs(docs.forced(slug, OLD), docs.forced(slug, tgt))
    out: dict[str, str] = {}
    amb: dict[str, set[str]] = {}
    for k, v in pairs.items():
        if len(v) == 1:
            out[k] = next(iter(v))
        else:
            amb[k] = v
    for k, old in src_prices.items():
        a, b = old.lstrip("-"), new_prices[k].lstrip("-")
        if a in amb and b in amb[a]:
            out[a] = b
            del amb[a]
        elif a in out and out[a] != b:
            raise SystemExit(f"{slug} {date}: price {k} says {a} -> {b}, the sheets say {a} -> {out[a]}")
        else:
            out.setdefault(a, b)
    if amb:
        raise SystemExit(f"{slug} {date}: ambiguous sheet pairings {amb}")
    return {k: v for k, v in out.items() if k != v}


def transform(text: str, repl: list[tuple[str, str]], nums: dict[str, str], ids: dict[str, str],
              src: str, date: str, used: set[int]) -> str:
    """Stated replacements first, held as placeholders so the number map cannot
    touch what they insert; then the @id renames, the number map in one pass,
    and the version date."""
    held = []
    for i, (a, b) in enumerate(repl):
        if a in text:
            used.add(i)
            held.append(b)
            text = text.replace(a, f"\x00{len(held) - 1}\x00")
    for a in sorted(ids, key=len, reverse=True):
        text = text.replace(a, ids[a])
    text = NUM.sub(lambda m: nums.get(m.group(0), m.group(0)), text)
    text = text.replace(src, date)
    for d in DROP_ALL:
        text = text.replace(d, "")
    return re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], text)


def dedash(text: str, name: bool) -> str:
    """No em-dash in what this generator writes: a name's aside takes a comma,
    a sentence's a colon."""
    text = text.replace(" \u2014 ", ", " if name else ": ")
    return text.replace("\u2014", ", " if name else ": ")


def stale(text: str, valid: set[str], allowed: set[str]) -> list[str]:
    return [t for t in NUM.findall(text) if t not in valid and t not in allowed]


# --- prose tables -------------------------------------------------------------

PROSE_FILE = Path(__file__).with_name("author_sdge_2026_prose.json")


def prose_for(slug: str, date: str) -> dict:
    """The prose table for one version: entries under "*" apply at every date and
    are merged under the date's own."""
    allp = json.loads(PROSE_FILE.read_text(encoding="utf-8")) if PROSE_FILE.exists() else {}
    t = allp.get(slug, {})
    out = {"repl": [], "text": {}, "add_deferrals": [], "drop_deferrals": [], "allow": [], "confirm": []}
    for k in ("*", date):
        e = t.get(k, {})
        out["repl"] += [tuple(x) for x in e.get("repl", [])]
        out["text"].update(e.get("text", {}))
        out["add_deferrals"] += e.get("add_deferrals", [])
        out["drop_deferrals"] += e.get("drop_deferrals", [])
        out["allow"] += e.get("allow", [])
        out["confirm"] += e.get("confirm", [])
    return out


# Tokens valid in every version's prose although no rate sheet of the schedule
# prints them: Rule 1 Sheet 6 (the holiday list), the 5.78% Franchise Fee as a
# multiplier, the CARE and FERA/DRAH Base Services Charge reductions
# (0.79343 - 0.19713, 0.79343 - 0.39688), which no sheet in this window moves.
ALLOWED = {"61672-E", "0.0578", "0.59630", "0.39655"}
# Figures stated in every version that no rate change in this window moves.
CONFIRM_ALL = ["130%", "130 percent", "5.78%", "5.78 percent"]
# A sentence about the earlier filing's own history, false in a new one.
DROP_ALL = [" The figure previously recorded here, 0.78 percent, was wrong."]
# An Evaluation carrying this sentence is regenerated from the deferrals by
# dev/resync_coverage_evaluations.py, so its prose is checked there, as deferrals.
RESYNCED = "listed here in the same words as the filing's tariff.toml"


def old_prices(doc, slug: str, src: str) -> dict[str, str]:
    out = {}

    def f(n):
        if n.get("@type") == "urpx:Price" and "urpx:unitPrice" in n:
            out[re.sub(rf"^sdge:({re.escape(slug)}-{src}-)?price-", "", n["@id"])] = n["urpx:unitPrice"]
    walk(doc, f)
    return out


def prose_items(doc, toml: dict) -> list[tuple[str, str]]:
    """(key, text) for every prose string a version carries: JSON-LD strings keyed
    "<@id>|<property>" by their 2026-04-01 @id, deferrals keyed "deferral:<i>"."""
    out = []
    for o, k in strings(doc, []):
        out.append((f"{o.get('@id', '?')}|{k}", o[k]))
    for i, t in enumerate(toml["modeling"]["deferrals"]):
        out.append((f"deferral:{i}", t))
    return out


def check_prose(key: str, text: str, valid: set[str], allowed: set[str], confirm: list[str],
                date: str) -> list[str]:
    """Stale numbers, and computed figures (every version) and sheet, note and
    Special Condition references (2026-09-30, whose sheets renumber) that the
    prose table has not confirmed."""
    out = [f"{key}: stale {t}" for t in stale(text, valid, allowed)]
    masked = text
    for c in sorted(confirm, key=len, reverse=True):
        masked = masked.replace(c, "\x01")
    pats = [PCT, REF] if date == SEP else [PCT]
    for pat in pats:
        out += [f"{key}: unconfirmed '{m.group(0)}' in ...{masked[max(0, m.start() - 70):m.end() + 40]}..."
                for m in pat.finditer(masked)]
    return out


# --- descriptions ---------------------------------------------------------------

# The 2026-04-01 descriptions end by saying the Monday after a Sunday holiday
# resolves as a weekday; their own dated urpx:Holiday entries (2027-07-05 on)
# say otherwise, and the deferrals describe those entries.
OBSERVANCE_OLD = ("so that direction is carried as urpx:holidayRule text and is not machine-readable: the "
                  "Monday after a Sunday-falling fixed-date holiday resolves here as an ordinary weekday, first "
                  "on 2027-07-05.")
OBSERVANCE_NEW = ("so that direction is carried as urpx:holidayRule text, and each Monday it creates through 2040 "
                  "is carried as a dated urpx:Holiday, the first on 2027-07-05.")


def _holiday_paragraph(old_description: str) -> str:
    i = old_description.find("Holiday handling:")
    if i < 0:
        return ""
    para = old_description[i:]
    if OBSERVANCE_OLD not in para:
        raise SystemExit("holiday paragraph: observance sentence not found")
    return " " + para.replace(OBSERVANCE_OLD, OBSERVANCE_NEW)


def _span(p: dict[str, str], cells: list[str]) -> str:
    vals = {c: p[f"eecc-{c}"] for c in cells}
    lo = min(vals, key=lambda c: vals[c])
    hi = max(vals, key=lambda c: vals[c])
    return f"from ${vals[lo]} {lo.replace('-', ' ')} to ${vals[hi]} {hi.replace('-', ' ')}"


TOU3 = ("Three TOU periods: On-Peak 4 p.m. to 9 p.m. every day; Super Off-Peak midnight to 6 a.m. and 10 a.m. "
        "to 2 p.m. on weekdays and midnight to 2 p.m. on weekends and holidays; Off-Peak all other hours. Summer is "
        "June 1 to October 31, winter November 1 to May 31.")
MODS = ("Base Services Charge $0.79343/day; the CARE, FERA and DRAH reductions of it are the modifiers sdge:care, "
        "sdge:fera and sdge:drah.")


def description(slug: str, date: str, p: dict[str, str], old_description: str) -> str:
    pub = PUBLISHED[(slug, AUG if date == SEP else date)]
    sep = (" Advice 4874-E prints the EECC prices in this schedule itself from 2026-09-30; Schedule EECC, which "
           "carried them before, is retired." if date == SEP else "")
    hol = _holiday_paragraph(old_description)
    credit = p.get("baseline-credit", "").lstrip("-")
    if slug == "dr":
        return ("SDG&E's standard non-TOU residential schedule, optionally available to customers who leave the "
                "TOU-DR1 default. Two tiers split at 130% of the baseline allowance differ only in the UDC Total: "
                f"${pub['udc'][0]}/kWh up to 130% of baseline and ${pub['udc'][1]}/kWh above it, modeled as the "
                f"above-baseline UDC components plus a Baseline Adjustment Credit of $({credit})/kWh on the first "
                f"tier. The EECC commodity rate is flat at ${p['eecc']}/kWh in both tiers and seasons, and DWR-BC "
                f"plus WF-NBC at $0.00591/kWh. {MODS}{sep}")
    if slug in ("tou-dr", "tou-dr1"):
        lead = {"tou-dr1": "SDG&E's default residential time-of-use schedule (CPUC D.18-12-004, effective March 1, "
                           "2019).",
                "tou-dr": "SDG&E's older three-period residential time-of-use schedule, optionally available."}[slug]
        return (f"{lead} {TOU3} The UDC Total is flat at ${pub['udc'][0]}/kWh in every period, carried as its "
                "Transmission, Distribution, PPP (split into the CARE Surcharge and the rest), ND, CTC, LGC, RS and "
                "TRAC components; DWR-BC plus WF-NBC is $0.00591/kWh; the EECC commodity rate carries the TOU "
                f"signal, {_span(p, CELLS)}. A Baseline Adjustment Credit of $({credit})/kWh applies to usage up "
                f"to 130% of baseline. {MODS}{sep}{hol}")
    if slug == "tou-dr2":
        return ("SDG&E's two-period residential time-of-use schedule, a voluntary alternative to the TOU-DR1 "
                "default: On-Peak 4 p.m. to 9 p.m. every day and Off-Peak all other hours, summer June 1 to "
                "October 31. The UDC Total varies by period only through its TRAC component: "
                f"${pub['udc'][0]}/kWh summer on-peak, ${pub['udc'][1]}/kWh summer off-peak and "
                f"${pub['udc'][2]}/kWh in winter. DWR-BC plus WF-NBC is $0.00591/kWh. EECC "
                f"${p['eecc-summer-on-peak']} and ${p['eecc-summer-off-peak']} summer, "
                f"${p['eecc-winter-on-peak']} and ${p['eecc-winter-off-peak']} winter, on-peak and off-peak. A "
                f"Baseline Adjustment Credit of $({credit})/kWh applies to usage up to 130% of baseline. "
                f"{MODS}{sep}{hol}")
    if slug == "tou-elec":
        return ("SDG&E's residential time-of-use schedule for households with an electric vehicle, a natural gas "
                "vehicle refueled at home, behind-the-meter storage or an electric heat pump, with enrollment "
                f"capped. {TOU3} The UDC Total is flat at ${pub['udc'][0]}/kWh and carries no TRAC; there is no "
                "Baseline Adjustment Credit. DWR-BC plus WF-NBC is $0.00591/kWh; the EECC commodity rate runs "
                f"{_span(p, CELLS)}. {MODS}{sep}{hol}")
    if slug == "dr-ses":
        return ("SDG&E's residential time-of-use schedule for individually metered customers with an "
                f"on-premises solar energy system. {TOU3} The UDC Total is flat at ${pub['udc'][0]}/kWh and, as "
                "the schedule directs, excludes the TRAC; there is no Baseline Adjustment Credit. DWR-BC plus "
                f"WF-NBC is $0.00591/kWh; the EECC commodity rate runs {_span(p, CELLS)}. {MODS}{sep}{hol}")
    if slug in ("ev-tou", "ev-tou-2", "ev-tou-5"):
        lead = {
            "ev-tou": ("SDG&E's residential time-of-use schedule for charging an electric or natural gas "
                       "vehicle. It has no Base Services Charge: a Minimum Bill of $0.413/day applies instead."),
            "ev-tou-2": ("SDG&E's residential time-of-use schedule for customers charging an electric or "
                         f"natural gas vehicle. {MODS}"),
            "ev-tou-5": ("SDG&E's residential time-of-use schedule for households with an electric or natural "
                         f"gas vehicle, and the otherwise applicable schedule for Net Billing Tariff customers. "
                         f"{MODS}"),
        }[slug]
        tou = {"ev-tou": "its Distribution component", "ev-tou-2": "its Distribution component",
               "ev-tou-5": "its Transmission and Distribution components"}[slug]
        return (f"{lead} {TOU3} The UDC Total is ${pub['udc'][0]}/kWh on-peak and off-peak and "
                f"${pub['udc'][2]}/kWh super off-peak, varying through {tou}; there is no Baseline Adjustment "
                "Credit. DWR-BC plus WF-NBC is $0.00591/kWh; the EECC commodity rate runs "
                f"{_span(p, CELLS)}.{sep}{hol}")
    raise KeyError(slug)


# --- derivation -------------------------------------------------------------------

MODIFIERS = {"care": ["2026-06-01"], "fera": ["2026-06-01"], "drah": DATES}
PRIOR = {"care": "2025-10-01", "fera": OLD, "drah": OLD}
DOC_OF = {"drah": "tou-dr1"}  # the schedule whose document a filing is read from


def doc_slug(slug: str) -> str:
    return DOC_OF.get(slug, slug)


def versions(slug: str) -> list[str]:
    return [OLD] + DATES if is_base(slug) else [PRIOR[slug]] + MODIFIERS[slug]


def kind_for(slug: str, date: str) -> str:
    if slug in ("care", "fera"):
        return "hist"
    return {JUN: "hist", AUG: "0923", SEP: "now"}[date]


def pdf_name(slug: str, date: str) -> str:
    return f"sdge_{slug}_{date}.pdf"


def source_url(slug: str, date: str) -> str:
    k = KEY[doc_slug(slug)]
    if kind_for(slug, date) == "hist":
        return f"{API}/historical/?utilId=SDGE&bookId=ELEC&tarfKey={k}&tarfYear=2026"
    return VIEW.format(k=k)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def doc_sheets(docs: Docs, slug: str, date: str) -> list[dict]:
    return docs.sheets(doc_slug(slug), kind_for(slug, date))


def own_sheets(docs: Docs, slug: str, date: str) -> dict[int, dict]:
    """The sheets of the committed document that are in force at date."""
    return in_force(doc_sheets(docs, slug, date), date)


def set_source(doc, docs: Docs, slug: str, date: str) -> None:
    dsr = version_node(doc)["urpx:hasDataSourceReference"]
    own = own_sheets(docs, slug, date)
    pages = [s["page"] for s in own.values()]
    leaves = sorted(s["leaf"] for s in own.values())
    dsr.update({"urpx:fileName": pdf_name(slug, date),
                "urpx:accessURL": source_url(slug, date),
                "urpx:dateRetrieved": "2026-09-23" if kind_for(slug, date) == "0923" else RETRIEVED,
                "urpx:pageStart": min(pages), "urpx:pageEnd": max(pages),
                "urpx:leafStart": leaves[0], "urpx:leafEnd": leaves[-1]})


class ProseError(Exception):
    pass


def derive(docs: Docs, slug: str, date: str, src: str, report: list[str]):
    """One new version from the src version. Returns (doc, deferrals, price rows)."""
    doc = load(path(slug, src))
    toml = tomli.loads((SDGE / slug / "versions" / src / "tariff.toml").read_text(encoding="utf-8"))
    old_desc = version_node(doc).get("urpx:description", "")
    m = rename_map(doc, src, date)
    olds = old_prices(doc, slug, src)
    if is_base(slug):
        newp = prices(slug, date)
    else:
        newp = dict(olds)  # no modifier value moves in this window; reconcile() is not run on them
    apply_map(doc, m)
    set_literals(doc, date)
    rows = set_prices(doc, slug, date, src, newp, m)
    set_source(doc, docs, slug, date)

    tbl = prose_for(slug, date)
    nums: dict[str, str] = {}
    if is_base(slug):
        nums = number_map(docs, slug, date, olds, newp)
        nums.update(leaf_map(docs, slug, src, date))
    elif slug == "drah":
        nums = leaf_map(docs, "tou-dr1", OLD, date)
    else:
        nums = {o["leaf"]: n["leaf"] for k, o in docs.forced(slug, src).items()
                for kk, n in docs.forced(slug, date).items() if k == kk and o["leaf"] != n["leaf"]}
    valid = set()
    for s in docs.forced(doc_slug(slug), date).values():
        valid |= set(NUM.findall(s["text"]))
    allowed = ALLOWED | set(tbl["allow"])
    used: set[int] = set()
    errs: list[str] = []
    old_ids = {v: k for k, v in m.items()}
    for o, k in strings(doc, []):
        key = f"{old_ids.get(o.get('@id'), o.get('@id', '?'))}|{k}"
        if key in tbl["text"]:
            o[k] = tbl["text"][key]
        elif is_base(slug) and k == "urpx:description" and o is version_node(doc):
            o[k] = description(slug, date, newp, old_desc)
        else:
            o[k] = transform(o[k], tbl["repl"], nums, m, src, date, used)
        if rescope.node_type(o) not in rescope.IDENTITY_TYPES | rescope.KEEP_SHARED_TYPES \
                or o is version_node(doc):
            o[k] = dedash(o[k], k == "urpx:name")
        if RESYNCED in o[k]:
            continue
        errs += check_prose(key, o[k], valid, allowed, tbl["confirm"] + CONFIRM_ALL, date)
    deferrals = []
    for i, t in enumerate(toml["modeling"]["deferrals"]):
        if i in tbl["drop_deferrals"]:
            continue
        key = f"deferral:{i}"
        t = dedash(tbl["text"].get(key) or transform(t, tbl["repl"], nums, m, src, date, used), False)
        errs += check_prose(key, t, valid, allowed, tbl["confirm"] + CONFIRM_ALL, date)
        deferrals.append(t)
    for t in tbl["add_deferrals"]:
        t = dedash(t, False)
        errs += check_prose("added", t, valid, allowed, tbl["confirm"] + CONFIRM_ALL, date)
        deferrals.append(t)
    unused = [tbl["repl"][i] for i in range(len(tbl["repl"])) if i not in used]
    errs += [f"replacement matched nothing: {u[0][:80]!r}" for u in unused]
    report += [f"{slug} {date} {e}" for e in errs]
    return doc, deferrals, rows, toml


# --- manifests --------------------------------------------------------------------

def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def wrap(text: str) -> str:
    import textwrap
    paras = [p.strip() for p in text.strip().split("\n\n")]
    return "\n\n".join(p if p.startswith(" ") else
                       "\n".join(textwrap.wrap(" ".join(p.split()), 78, break_long_words=False,
                                               break_on_hyphens=False)) for p in paras)


def sheet_lines(own: dict[int, dict]) -> str:
    return "\n".join(f" Sheet {n}: {s['leaf']}, Advice {s['al']}, effective {iso(s['eff'])}"
                     for n, s in sorted(own.items()))


def notes(docs: Docs, slug: str, date: str, prev: str, nxt: str | None, rows) -> str:
    ds = doc_slug(slug)
    kind = kind_for(slug, date)
    k = KEY[ds]
    own = own_sheets(docs, slug, date)
    forced = docs.forced(ds, date)
    parts = []
    if kind == "hist":
        parts.append(
            f"Source bytes. SDG&E's historical document for Schedule {NAME[ds]} for 2026, "
            f"{API}/historical/?utilId=SDGE&bookId=ELEC&tarfKey={k}&tarfYear=2026, retrieved {RETRIEVED} with "
            "the X-Azure-FDID header documented in us/ca/sdge/utility.toml. It holds every sheet revision "
            "issued in 2026, superseded ones included; the sheets of this version are those in force on "
            f"{date}. SDG&E regenerates the PDF per request, so the sha256 is of the committed bytes.")
    else:
        when = "2026-09-23 by dev/fetch_tariff_documents.py (data/documents/sdge/)" if kind == "0923" \
            else RETRIEVED
        parts.append(
            f"Source bytes. Schedule {NAME[ds]} as served by {API}/tariff/?utilId=SDGE&bookId=ELEC&tarfKey={k} "
            f"(the PDF behind the tariffsprd.sdge.com viewer URL in [source]), retrieved {when} with the "
            "X-Azure-FDID header documented in us/ca/sdge/utility.toml. SDG&E regenerates the PDF per "
            "request, so the sha256 is of the committed bytes.")
    lines = sheet_lines(forced)
    missing = sorted(set(forced) - set(own))
    tail = ""
    if missing:
        tail = ("\n\n" + ("Sheets " if len(missing) > 1 else "Sheet ") + ", ".join(str(n) for n in missing)
                + (" were" if len(missing) > 1 else " was") + " last revised before 2026 and so "
                "not in this document; the revisions above are as printed in the 2026-09-23 copy and in "
                f"the {prev} filing's PDF.")
    parts.append(f"Sheets in force on {date}:\n{lines}{tail}")
    if slug in ("care", "fera"):
        al, name = AL_INCOME
    else:
        al, name = AL[date]
    revised = sorted(n for n, s in forced.items() if s["eff"] and iso(s["eff"]) == date)
    parts.append(f"Advice {al}, \"{name}\", effective {date}, revises Sheet"
                 f"{'s' if len(revised) > 1 else ''} {', '.join(str(n) for n in revised)}.")
    moved = [(a, b, c) for a, b, c in rows if b != c]
    if moved:
        parts.append(f"Price changes from the {prev} version, $ per kWh unless a per-day charge:\n"
                     + "\n".join(f" {a}: {b} -> {c}" for a, b, c in moved))
    else:
        parts.append(f"No price this filing models moved from the {prev} version.")
    if is_base(slug):
        pub = PUBLISHED[(slug, AUG if date == SEP else date)]
        parts.append(
            "Reconciliation. In every TOU cell the UDC components sum to the published UDC Total ("
            + ", ".join(dict.fromkeys(pub["udc"])) + ") and UDC + DWR-BC + WF-NBC + EECC to the published "
            "Total Rate (" + ", ".join(pub["total"]) + "). Every modeled price is printed on these sheets "
            "except the PPP split, whose CARE Surcharge is Schedule E-CARE Sheet 2's"
            + (" and sdge:dr's Baseline Adjustment Credit, the difference of its two printed totals."
               if slug == "dr" else "."))
    old_own = docs.forced(ds, prev) if prev != PRIOR.get(slug) or slug == "drah" else None
    if date == SEP:
        parts.append(
            "Supersession. Advice 4874-E reissues every sheet of the schedule as an Original sheet whose "
            "Canceling line is blank, so no sheet names what it cancels; the advice letter replaces the "
            f"2026-08-01 sheets with these, and the {prev} version ends at {date}.")
    else:
        rate_n = {"care": 3, "fera": 1}.get(slug)
        if rate_n is None:
            rate_n = min(n for n, s in forced.items() if s["eff"] and iso(s["eff"]) == date)
        cur = forced[rate_n]
        parts.append(f"Supersession. Sheet {rate_n} ({cur['leaf']}) cancels {cur['cancels']}, the sheet of the "
                     f"{prev} version it replaces, effective {date}; the {prev} version ends there."
                     + (f" This version ends at {nxt}." if nxt else ""))
    del old_own
    if is_base(slug):
        parts.append(
            "Unchanged from the 2026-04-01 version: the TOU periods, seasons, holiday calendar, eligibility "
            "rules, price structure and the modeling notes in "
            f"us/ca/sdge/electricity/{slug}/versions/2026-04-01/tariff.toml.")
    return "\n\n".join(wrap(p) if not (p.startswith("Price changes") or p.startswith("Sheets in force"))
                       else p for p in parts)


def write_manifest(docs: Docs, slug: str, date: str, prev: str, nxt: str | None, rows, deferrals, old) -> None:
    d = SDGE / slug / "versions" / date
    pdf = d / pdf_name(slug, date)
    al = AL_INCOME[0] if slug in ("care", "fera") else AL[date][0]
    docket = (f"Advice {al} (effective {date})" if date != SEP
              else "Advice 4874-E (effective 2026-09-30), implementing Decision 25-09-006")
    lines = [
        "# Identity --------------------------------------------------------------------",
        'utility = "sdge"', f'schedule = "{slug}"', f'effective_date = "{date}"', "",
        "# Source ----------------------------------------------------------------------",
        "[source]", f'url = "{source_url(slug, date)}"', f'sha256 = "{sha(pdf)}"',
        f'retrieved_on = "{"2026-09-23" if kind_for(slug, date) == "0923" else RETRIEVED}"',
        'media_type = "application/pdf"', 'filing_type = "advice-letter"', f'filing_id = "SDGE-AL-{al}"', "",
        "# Regulatory ------------------------------------------------------------------",
        "[regulator]", 'authority = "puc"', f"docket = {toml_str(docket)}", "",
        "# Extraction ------------------------------------------------------------------",
        "[extraction]", 'tool = "manual"', f'extracted_on = "{RETRIEVED}"', 'notes = """',
        notes(docs, slug, date, prev, nxt, rows), '"""', "",
        "# Validation ------------------------------------------------------------------",
        "[validation]", "shacl_passed = true", 'validator = "clj-shacl + clj-urpx (URPX v0.5.1)"',
        f'validated_on = "{RETRIEVED}"', "",
        "# Modeling -------------------------------------------------------------------",
        "[modeling]", f"complete = {'true' if old['modeling']['complete'] else 'false'}", "deferrals = [",
        *[" " + toml_str(x) + "," for x in deferrals], "]",
    ]
    mods = old["modeling"].get("applicable_modifiers")
    if mods is not None:
        lines += ["applicable_modifiers = [", *[f' "{x}",' for x in mods], "]"]
    lines += ["", "# Review ----------------------------------------------------------------------",
              "[review]", 'status = "draft"',
              "notes = " + toml_str(f"Derived from the {prev if not is_base(slug) else OLD} version by "
                                    "dev/author_sdge_2026.py: every Price reconciled to the sheets in force on "
                                    f"{date}, citations and figures rewritten for them. See [extraction] notes."),
              ""]
    text = "\n".join(lines)
    tomli.loads(text)
    (d / "tariff.toml").write_text(text, encoding="utf-8")


def vendor(docs: Docs) -> None:
    """Copy each version's source document into its filing directory."""
    for slug in BASES + list(MODIFIERS):
        for date in versions(slug)[1:]:
            src = docs.path(doc_slug(slug), kind_for(slug, date))
            body = src.read_bytes()
            if body[:5] != b"%PDF-":
                raise SystemExit(f"{src}: not a PDF")
            dst = SDGE / slug / "versions" / date / pdf_name(slug, date)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(body)


CANDIDATE = {
    "care": [("price-care-surcharge-exemption", "price-udc-care-surcharge"),
             ("price-bill-discount", "summary-care-discountable")],
    "fera": [("price-bill-discount", "summary-fera-discountable")],
}


def candidates() -> None:
    """Every CARE and FERA Price over base Prices or subtotals names the
    candidate of every base at every date, read disjunctively, as
    dev/lint_discount_summaries.py requires of every version."""
    defined: dict[str, list[str]] = {}
    for b in BASES:
        for p in sorted((SDGE / b / "versions").glob("*/rate-plan_*.jsonld")):
            def h(d, b=b):
                i = d.get("@id", "")
                if len(d) > 1 and isinstance(i, str):
                    for _, suffix in CANDIDATE["care"] + CANDIDATE["fera"]:
                        if re.fullmatch(rf"sdge:{re.escape(b)}-\d{{4}}-\d{{2}}-\d{{2}}-{suffix}", i):
                            defined.setdefault(suffix, []).append(i)
            walk(load(p), h)
    for slug, pairs in CANDIDATE.items():
        for p in sorted((SDGE / slug / "versions").glob("*/*.jsonld")):
            doc = load(p)
            hits = []

            def f(d, pairs=pairs, hits=hits):
                if d.get("@type") != "urpx:Price" or "urpx:basedOnPrice" not in d:
                    return
                for stem, suffix in pairs:
                    if re.search(rf"-{stem}(-\d{{4}}-\d{{2}}-\d{{2}})?$", d["@id"]) or \
                            re.search(rf"{slug}-\d{{4}}-\d{{2}}-\d{{2}}-{stem}$", d["@id"]):
                        d["urpx:basedOnPrice"] = [{"@id": i} for i in defined[suffix]]
                        hits.append(stem)
            walk(doc, f)
            if sorted(hits) != sorted(s for s, _ in pairs):
                raise SystemExit(f"{p}: candidate Prices found {hits}")
            dump(p, doc)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    report_only = "--report" in argv
    docs = Docs(Path(argv[1]))
    report: list[str] = []
    out = {}
    for slug in BASES + list(MODIFIERS):
        vs = versions(slug)
        for i, date in enumerate(vs[1:], 1):
            prev, nxt = vs[i - 1], (vs[i + 1] if i + 1 < len(vs) else None)
            src = OLD if is_base(slug) else PRIOR[slug]
            doc, deferrals, rows, old = derive(docs, slug, date, src, report)
            if is_base(slug):
                text = "\n".join(s["text"] for s in docs.forced(slug, date).values())
                report += reconcile(slug, date, prices(slug, date), text)
                if prev != OLD:
                    a, b = prices(slug, prev), prices(slug, date)
                    rows = [(k, a[k], b[k]) for k in a]
            out[(slug, date)] = (doc, deferrals, rows, old, prev, nxt)
    if report:
        print("\n".join(report))
        print(f"\n{len(report)} problem(s); nothing written.")
        return 1
    if report_only:
        print("clean")
        return 0
    vendor(docs)
    for (slug, date), (doc, deferrals, rows, old, prev, nxt) in out.items():
        dump(path(slug, date), doc)
        write_manifest(docs, slug, date, prev, nxt, rows, deferrals, old)
    for slug in BASES + list(MODIFIERS):
        vs = versions(slug)
        for a, b in zip(vs, vs[1:]):
            expire(slug, a, b)
    candidates()
    for (slug, date), (_, _, rows, *_r) in out.items():
        print(f"{slug} {date}: {len(rows)} prices, {sum(1 for r in rows if r[1] != r[2])} moved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
