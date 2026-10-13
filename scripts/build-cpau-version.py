#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Add a CPAU edition: one new version per schedule CPAU reissued on one date.

    python3 scripts/build-cpau-version.py --effective 2026-07-01 --pdfs <dir>

<dir> holds the fetched sheets, named cpau_<schedule>_<effective>.pdf. Each one
is vendored into its filing directory (LAYOUT.md section 7), and the new version
is derived from the schedule's newest held version: every subordinate @id is
scoped to the new version (LAYOUT.md section 6), every Price is set from the
EDITIONS table, and the held version gains urpx:expirationDateTime at the new
effective date (LAYOUT.md section 9), wherever a copy of it is defined.

The per-schedule build-cpau-<schedule>-<date>.py writers are not reused: they
target the pre-2026-09-20 layout and predate the URPX v0.5.1 migration and the
curation since, so they refuse to write. The held JSON-LD is the authority.

RECONCILIATION. The table asserts both the value it replaces and the new value.
Each pair is checked against the two sheets themselves: pdftotext reads the held
and the new PDF, their lines are aligned, and the old and new figures must stand
at the same position of corresponding lines. Prose figures (descriptions, the
manifest's deferrals) move by the same aligned pairs, and every change is
printed for review.

Needs pdftotext (poppler) on PATH.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CPAU = REPO / "us/ca/cpau/electricity"
sys.path.insert(0, str(REPO / "dev"))
import rescope_iris  # noqa: E402

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

LANDING = {
    "res": "https://www.paloalto.gov/Departments/Utilities/Customer-Service/Utilities-Rates/Residential-Rates",
    "bus": "https://www.paloalto.gov/Departments/Utilities/Customer-Service/Utilities-Rates/Business-Rates",
}
BASE_URL = "https://www.paloalto.gov/files/assets/public"

# One entry per edition: when its sheets were retrieved, then per schedule the
# document (path under BASE_URL, sha256) and {held Price @id: (held, new)}.
# Modifiers inlined into a base filing (e-nse-1 in e-1-tou) are carried by
# their own entry; the base copy is replaced with the standalone one.
EDITIONS = {
    "2026-07-01": {
        "retrieved": "2026-10-06",
        "schedules": {
            "e-nse-1": ("v/7/utilities/rates-schedules-for-utilities/residential-utility-rates/e-nse-1_effective_2026-07-01.pdf",
                        "acde158da7d2534cc2c2b12c943fab8d70b622d9b93c4ccd5a0e0eb69a299686", {
                "cpau:e-nse-1-2025-09-01-price-surplus-compensation": ("-0.10120", "-0.10640"),
            }),
            "e-eec-1": ("v/7/utilities/rates-schedules-for-utilities/residential-utility-rates/e-eec-1_effective_2026-07-01.pdf",
                        "d58af19f985e678a7a45e6f3b1a689dafd798fc763b812fcf25f46f1843a5ef8", {
                "cpau:e-eec-1-2025-09-01-price-export-compensation": ("-0.12060", "-0.09900"),
            }),
            "e-1": ("v/7/utilities/rates-schedules-for-utilities/residential-utility-rates/e-1_effective_2026-07-01.pdf",
                    "27f8671e08935375ddcb1d883e4ae03c15ae9f87db79ccdd0e99a73040a79ae0", {
                "cpau:price-customer-charge": ("5.15", "5.38"),
                "cpau:price-public-benefits": ("0.00604", "0.00631"),
                "cpau:price-commodity-tier1": ("0.10373", "0.10839"),
                "cpau:price-commodity-tier2": ("0.13372", "0.13973"),
                "cpau:price-distribution-tier1": ("0.09593", "0.10024"),
                "cpau:price-distribution-tier2": ("0.08968", "0.09371"),
            }),
            "e-1-tou": ("v/2/utilities/rates-schedules-for-utilities/residential-utility-rates/e-1-tou_effective_2026-07-01.pdf",
                        "98f8e1be9027f3ace1ec3812fd531cb90b3a8d2af6b336d8cc4963b8598df6e0", {
                "cpau:tou-price-customer-charge": ("5.15", "5.38"),
                "cpau:tou-price-distribution": ("0.09351", "0.09771"),
                "cpau:tou-price-public-benefits": ("0.00604", "0.00631"),
                "cpau:tou-price-commodity-summer-peak": ("0.23354", "0.24404"),
                "cpau:tou-price-commodity-summer-off-peak": ("0.08249", "0.08620"),
                "cpau:tou-price-commodity-summer-super-off-peak": ("0.06690", "0.06991"),
                "cpau:tou-price-commodity-winter-peak": ("0.16705", "0.17456"),
                "cpau:tou-price-commodity-winter-off-peak": ("0.11033", "0.11529"),
                "cpau:tou-price-commodity-winter-super-off-peak": ("0.07835", "0.08187"),
            }),
            "e-2": ("v/6/utilities/rates-schedules-for-utilities/commercial-utility-rates/e-2_effective_2026-07-01.pdf",
                    "b09d068b734eac5c86eed7b8c14c40d22b7feec3a710144cafaf6397394794d7", {
                "cpau:e2-price-commodity-summer": ("0.15075", "0.15753"),
                "cpau:e2-price-distribution-summer": ("0.10806", "0.11292"),
                "cpau:e2-price-public-benefits-summer": ("0.00604", "0.00631"),
                "cpau:e2-price-commodity-winter": ("0.09334", "0.09754"),
                "cpau:e2-price-distribution-winter": ("0.07352", "0.07682"),
                "cpau:e2-price-public-benefits-winter": ("0.00604", "0.00631"),
                "cpau:e2-price-customer-charge": ("6.22", "6.49"),
            }),
            "e-2-g": ("v/7/utilities/rates-schedules-for-utilities/commercial-utility-rates/e-2-g_effective_2026-07-01.pdf",
                      "d5897de2bd2898545516e08c799afc9c41df21365a8dea4bcbf91246068fd42d", {
                "cpau:e2g-price-green-charge": ("0.0075", "0.0075"),
            }),
            "e-4": ("v/6/utilities/rates-schedules-for-utilities/commercial-utility-rates/e-4_effective_2026-07-01.pdf",
                    "f1695b1f92e4304357e86e49038caf6c1038d7e4f29464d1cf18b69987dee2fd", {
                "cpau:e4-price-energy-commodity-summer": ("0.12441", "0.13000"),
                "cpau:e4-price-energy-distribution-summer": ("0.02797", "0.02922"),
                "cpau:e4-price-energy-public-benefits-summer": ("0.00604", "0.00631"),
                "cpau:e4-price-energy-commodity-winter": ("0.08028", "0.08389"),
                "cpau:e4-price-energy-distribution-winter": ("0.02797", "0.02922"),
                "cpau:e4-price-energy-public-benefits-winter": ("0.00604", "0.00631"),
                "cpau:e4-price-demand-commodity-summer": ("11.09", "11.58"),
                "cpau:e4-price-demand-distribution-summer": ("38.08", "39.79"),
                "cpau:e4-price-demand-commodity-winter": ("2.60", "2.71"),
                "cpau:e4-price-demand-distribution-winter": ("23.49", "24.54"),
                "cpau:e4-price-customer-charge": ("126.24", "131.92"),
            }),
            "e-4-g": ("v/7/utilities/rates-schedules-for-utilities/commercial-utility-rates/e-4-g_effective_2026-07-01.pdf",
                      "66fb0771327b946855a1e012818ab8ea0829c2b405cc913b13a01507848a3b1b", {
                "cpau:e4g-price-green-charge": ("0.0075", "0.0075"),
            }),
            "e-4-tou": ("v/6/utilities/rates-schedules-for-utilities/commercial-utility-rates/e-4-tou_effective_2026-07-01.pdf",
                        "f1fadf50d80f9e969bf697135d4247601d099e5170c4d6dde1884785a0823585", {
                "cpau:e4tou-price-energy-commodity-summer-peak": ("0.17208", "0.17982"),
                "cpau:e4tou-price-energy-distribution-summer-peak": ("0.02817", "0.02943"),
                "cpau:e4tou-price-energy-public-benefits-summer-peak": ("0.00604", "0.00631"),
                "cpau:e4tou-price-energy-commodity-summer-mid-peak": ("0.14181", "0.14819"),
                "cpau:e4tou-price-energy-distribution-summer-mid-peak": ("0.02817", "0.02943"),
                "cpau:e4tou-price-energy-public-benefits-summer-mid-peak": ("0.00604", "0.00631"),
                "cpau:e4tou-price-energy-commodity-summer-off-peak": ("0.10662", "0.11141"),
                "cpau:e4tou-price-energy-distribution-summer-off-peak": ("0.02817", "0.02943"),
                "cpau:e4tou-price-energy-public-benefits-summer-off-peak": ("0.00604", "0.00631"),
                "cpau:e4tou-price-energy-commodity-winter-peak": ("0.12096", "0.12640"),
                "cpau:e4tou-price-energy-distribution-winter-peak": ("0.02775", "0.02899"),
                "cpau:e4tou-price-energy-public-benefits-winter-peak": ("0.00604", "0.00631"),
                "cpau:e4tou-price-energy-commodity-winter-mid-peak": ("0.09547", "0.09976"),
                "cpau:e4tou-price-energy-distribution-winter-mid-peak": ("0.02775", "0.02899"),
                "cpau:e4tou-price-energy-public-benefits-winter-mid-peak": ("0.00604", "0.00631"),
                "cpau:e4tou-price-energy-commodity-winter-off-peak": ("0.06590", "0.06886"),
                "cpau:e4tou-price-energy-distribution-winter-off-peak": ("0.02775", "0.02899"),
                "cpau:e4tou-price-energy-public-benefits-winter-off-peak": ("0.00604", "0.00631"),
                "cpau:e4tou-price-demand-commodity-summer-peak": ("9.82", "10.26"),
                "cpau:e4tou-price-demand-distribution-summer-peak": ("19.07", "19.92"),
                "cpau:e4tou-price-demand-commodity-summer-max": ("1.30", "1.35"),
                "cpau:e4tou-price-demand-distribution-summer-max": ("19.07", "19.92"),
                "cpau:e4tou-price-demand-commodity-winter-peak": ("1.31", "1.36"),
                "cpau:e4tou-price-demand-distribution-winter-peak": ("11.91", "12.44"),
                "cpau:e4tou-price-demand-commodity-winter-max": ("1.31", "1.36"),
                "cpau:e4tou-price-demand-distribution-winter-max": ("11.91", "12.44"),
                "cpau:e4tou-price-customer-charge": ("126.24", "131.92"),
            }),
            "e-7": ("v/7/utilities/rates-schedules-for-utilities/commercial-utility-rates/e-7_effective_2026-07-01.pdf",
                    "6d771f865693ec2ee5a5860d38d15d896a66f8bb436383ab653e57581e1ebce2", {
                "cpau:e7-price-energy-commodity-summer": ("0.12786", "0.13361"),
                "cpau:e7-price-energy-distribution-summer": ("0.00402", "0.00420"),
                "cpau:e7-price-energy-public-benefits-summer": ("0.00604", "0.00631"),
                "cpau:e7-price-energy-commodity-winter": ("0.07973", "0.08331"),
                "cpau:e7-price-energy-distribution-winter": ("0.00393", "0.00410"),
                "cpau:e7-price-energy-public-benefits-winter": ("0.00604", "0.00631"),
                "cpau:e7-price-demand-commodity-summer": ("12.07", "12.61"),
                "cpau:e7-price-demand-distribution-summer": ("31.54", "32.95"),
                "cpau:e7-price-demand-commodity-winter": ("2.82", "2.94"),
                "cpau:e7-price-demand-distribution-winter": ("27.75", "28.99"),
                "cpau:e7-price-customer-charge": ("578.08", "604.09"),
            }),
            "e-7-g": ("v/7/utilities/rates-schedules-for-utilities/commercial-utility-rates/e-7-g_effective_2026-07-01.pdf",
                      "4b7af9b7ed7fbd95714cc33b036ee954a3fce708e3a6e959dfed8c2aa45b79a4", {
                "cpau:e7g-price-green-charge": ("0.0075", "0.0075"),
            }),
            "e-7-tou": ("v/6/utilities/rates-schedules-for-utilities/commercial-utility-rates/e-7-tou_effective_2026-07-01.pdf",
                        "7a0c9a96f44333e3758586e6c4c8b717d194959b3ac260724dc0e10b3d27c8fd", {
                "cpau:e7tou-price-energy-commodity-summer-peak": ("0.18199", "0.19017"),
                "cpau:e7tou-price-energy-distribution-summer-peak": ("0.00402", "0.00420"),
                "cpau:e7tou-price-energy-public-benefits-summer-peak": ("0.00604", "0.00631"),
                "cpau:e7tou-price-energy-commodity-summer-mid-peak": ("0.14999", "0.15673"),
                "cpau:e7tou-price-energy-distribution-summer-mid-peak": ("0.00402", "0.00420"),
                "cpau:e7tou-price-energy-public-benefits-summer-mid-peak": ("0.00604", "0.00631"),
                "cpau:e7tou-price-energy-commodity-summer-off-peak": ("0.11276", "0.11783"),
                "cpau:e7tou-price-energy-distribution-summer-off-peak": ("0.00402", "0.00420"),
                "cpau:e7tou-price-energy-public-benefits-summer-off-peak": ("0.00604", "0.00631"),
                "cpau:e7tou-price-energy-commodity-winter-peak": ("0.12225", "0.12775"),
                "cpau:e7tou-price-energy-distribution-winter-peak": ("0.00393", "0.00410"),
                "cpau:e7tou-price-energy-public-benefits-winter-peak": ("0.00604", "0.00631"),
                "cpau:e7tou-price-energy-commodity-winter-mid-peak": ("0.09648", "0.10082"),
                "cpau:e7tou-price-energy-distribution-winter-mid-peak": ("0.00393", "0.00410"),
                "cpau:e7tou-price-energy-public-benefits-winter-mid-peak": ("0.00604", "0.00631"),
                "cpau:e7tou-price-energy-commodity-winter-off-peak": ("0.06660", "0.06959"),
                "cpau:e7tou-price-energy-distribution-winter-off-peak": ("0.00393", "0.00410"),
                "cpau:e7tou-price-energy-public-benefits-winter-off-peak": ("0.00604", "0.00631"),
                "cpau:e7tou-price-demand-commodity-summer-peak": ("11.39", "11.90"),
                "cpau:e7tou-price-demand-distribution-summer-peak": ("16.33", "17.06"),
                "cpau:e7tou-price-demand-commodity-summer-max": ("1.46", "1.52"),
                "cpau:e7tou-price-demand-distribution-summer-max": ("16.33", "17.06"),
                "cpau:e7tou-price-demand-commodity-winter-peak": ("1.46", "1.52"),
                "cpau:e7tou-price-demand-distribution-winter-peak": ("14.42", "15.06"),
                "cpau:e7tou-price-demand-commodity-winter-max": ("1.46", "1.52"),
                "cpau:e7tou-price-demand-distribution-winter-max": ("14.42", "15.06"),
                "cpau:e7tou-price-customer-charge": ("578.08", "604.09"),
            }),
            "e-14": ("v/5/utilities/rates-schedules-for-utilities/city-facility-utility-rates/e-14_effective_2026-07-01.pdf",
                     "7c9f5d5cd0c7db1fa2cc07c374b951546d36f486b28e715893dc4887ccc39570", {
                "cpau:e14-price-mv-400w": ("53.53", "55.93"),
                "cpau:e14-price-hpsv-70w": ("35.37", "36.95"),
                "cpau:e14-price-hpsv-100w": ("45.35", "47.39"),
                "cpau:e14-price-hpsv-150w": ("62.00", "64.79"),
                "cpau:e14-price-hpsv-250w": ("95.30", "99.59"),
                "cpau:e14-price-led-70w-eq": ("13.27", "13.86"),
                "cpau:e14-price-led-100w-eq": ("20.83", "21.77"),
                "cpau:e14-price-led-150w-eq": ("27.80", "29.04"),
                "cpau:e14-price-led-175w-eq": ("31.43", "32.84"),
                "cpau:e14-price-led-250w": ("46.87", "48.97"),
                "cpau:e14-price-tsig-12head-ryg": ("27.12", "28.34"),
                "cpau:e14-price-tsig-8head-ryg": ("23.55", "24.60"),
                "cpau:e14-price-tsig-12arrow-ryg": ("25.49", "26.63"),
                "cpau:e14-price-tsig-12beacon": ("10.19", "10.65"),
                "cpau:e14-price-tsig-pedestrian": ("9.36", "9.78"),
                "cpau:e14-price-tsig-controller": ("20.05", "20.95"),
                "cpau:e14-price-tsig-speed-signs": ("92.73", "96.89"),
                "cpau:e14-price-switching-surcharge": ("2.50", "2.50"),
            }),
            "e-16": ("v/3/utilities/rates-schedules-for-utilities/city-facility-utility-rates/e-16_effective_2026-07-01.pdf",
                     "56bacb850990f5a43b41688fcd1dd33547dabd36f9b0ccce6a995718ff938cdb", {
                "cpau:e16-price-customer-charge": ("10.96", "11.28"),
            }),
        },
        # Prose the aligned figures cannot move. Each replacement must hit, and
        # each dropped deferral (named by its opening words) must exist.
        "edits": {
            # E-16 C.2 prices energy by reference to E-2, so it quotes E-2's figures.
            "e-16": {"replace": [(
                "(0.15075 + 0.10806 + 0.00604 = 0.26485/kWh summer, 0.09334 + 0.07352 + 0.00604 = "
                "0.17290/kWh winter as of 2025-07-01)",
                "(0.15753 + 0.11292 + 0.00631 = 0.27676/kWh summer, 0.09754 + 0.07682 + 0.00631 = "
                "0.18067/kWh winter as of 2026-07-01)")]},
            # The 2026-07-01 E-4 sheets reflow Section D: D.2 moves onto E-4-1, D.5 ends on
            # E-4-2, and D.6.d and D.6.e(1) sit wholly on E-4-3.
            "e-4": {"replace": [
                ("Section D.5, Sheets E-4-2 and E-4-3:", "Section D.5, Sheet E-4-2:"),
                ("Section D.6.d, Sheets E-4-3 and E-4-4:", "Section D.6.d, Sheet E-4-3:"),
                ("Section D.6.e(1), Sheet E-4-4:", "Section D.6.e(1), Sheet E-4-3:"),
                ("Section D.2, Sheet E-4-2:", "Section D.2, Sheet E-4-1:"),
            ]},
            # Sheet E-4-G-1 C.1 now prints a winter energy total (0.12692) equal to its
            # components, so the stale-total note no longer describes the source.
            "e-4-g": {"drop": ["Source arithmetic, recorded so it is not re-derived:"]},
        },
    },
}

VERSION_TYPES = rescope_iris.VERSION_TYPES
UNSCOPED_TYPES = rescope_iris.IDENTITY_TYPES | rescope_iris.KEEP_SHARED_TYPES
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
CURIE = re.compile(r"cpau:[A-Za-z0-9_-]*[A-Za-z0-9_]")
FIGURE = re.compile(r"(?<![\d.])\d[\d,]*\.\d+(?!\d)(?!\.\d)")
# String-valued keys that are data rather than prose.
NOT_PROSE = {"@id", "@type", "urpx:unitPrice", "urpx:startDate", "urpx:url", "urpx:fileName",
             "urpx:targetURPXVersion", "urpx:effectiveDateTime", "urpx:expirationDateTime",
             "urpx:initialEffectiveDate", "urpx:dateRetrieved", "urpx:version",
             "urpx:modifierVersionNumber", "urpx:evaluatedOn", "urpx:month", "urpx:baseQuantity"}


# --- documents --------------------------------------------------------------

def pdf_lines(p: Path) -> list[str]:
    out = subprocess.run(["pdftotext", "-layout", str(p), "-"], check=True,
                         capture_output=True, text=True).stdout
    return [" ".join(x.split()) for x in out.splitlines() if x.strip()]


def figures(line: str) -> list[Decimal]:
    return [Decimal(t.replace(",", "")) for t in FIGURE.findall(line)]


def attested(old_pdf: Path, new_pdf: Path) -> dict[Decimal, set[Decimal]]:
    """Old figure -> the figures at the same position of the aligned new line.

    A figure on an unchanged line maps to itself. A changed line maps position by
    position; a new line that adds a trailing figure (E-4-G's winter demand total)
    maps its shared prefix."""
    a, b = pdf_lines(old_pdf), pdf_lines(new_pdf)
    m: dict[Decimal, set[Decimal]] = defaultdict(set)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for x in a[i1:i2]:
                for f in figures(x):
                    m[f].add(f)
        elif op == "replace":
            xs = [x for x in a[i1:i2] if figures(x)]
            ys = [y for y in b[j1:j2] if figures(y)]
            if len(xs) != len(ys):
                continue
            for x, y in zip(xs, ys):
                for p, q in zip(figures(x), figures(y)):
                    m[p].add(q)
    return m


def fmt_like(template: str, value: Decimal) -> str:
    places = len(template.split(".")[1]) if "." in template else 0
    return f"{value:.{places}f}"


def figure_map(att: dict[Decimal, set[Decimal]]) -> dict[Decimal, Decimal]:
    """The figures that moved, where the move is unambiguous."""
    return {k: next(iter(v)) for k, v in att.items() if len(v) == 1 and next(iter(v)) != k}


def move_figures(s: str, fm: dict[Decimal, Decimal]) -> str:
    def sub(mo):
        t = mo.group(0)
        d = Decimal(t.replace(",", ""))
        return fmt_like(t, fm[d]) if d in fm else t
    return FIGURE.sub(sub, s)


# --- JSON-LD ----------------------------------------------------------------

def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def dump(p: Path, doc) -> None:
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def walk(o, f, owner=None, key=None):
    if isinstance(o, dict):
        if rescope_iris.node_type(o) in VERSION_TYPES:
            owner = o["@id"]
        f(o, owner)
        for k, v in o.items():
            if k != "@context":
                walk(v, f, owner, k)
    elif isinstance(o, list):
        for v in o:
            walk(v, f, owner, key)


def scoped(iri: str, owner: str, schedule: str) -> str:
    """rescope_iris.new_iri, also dropping the compact schedule token the
    2025 generators led with (cpau:e2-pd-commodity-summer)."""
    out = rescope_iris.new_iri(iri, owner)
    head = f"{owner}-"
    rest = out[len(head):]
    compact = schedule.replace("-", "")
    if rest.startswith(compact + "-"):
        rest = rest[len(compact) + 1:]
    return head + rest


def rename_map(doc, schedule: str, old: str, new: str) -> dict[str, str]:
    own_old = f"cpau:{schedule}-{old}"
    own_new = f"cpau:{schedule}-{new}"
    m: dict[str, str] = {}

    def f(d, owner):
        i = d.get("@id")
        if not isinstance(i, str) or len(d) < 2 or not i.startswith("cpau:"):
            return
        if old in i:
            m[i] = i.replace(old, new)
        elif owner == own_old and rescope_iris.node_type(d) not in UNSCOPED_TYPES:
            m[i] = scoped(i, own_new, schedule)
    walk(doc, f)
    if len(set(m.values())) != len(m):
        raise SystemExit(f"{schedule}: two @ids collapse onto one")
    kept = set()
    walk(doc, lambda d, _o: kept.add(d["@id"]) if isinstance(d.get("@id"), str) and d["@id"] not in m else None)
    if set(m.values()) & kept:
        raise SystemExit(f"{schedule}: rescoped @ids collide with kept ones: {sorted(set(m.values()) & kept)[:3]}")
    return m


def apply_ids(doc, m: dict[str, str]) -> None:
    def f(d, _owner):
        if isinstance(d.get("@id"), str) and d["@id"] in m:
            d["@id"] = m[d["@id"]]
    walk(doc, f)


def move_curies(s: str, m: dict[str, str]) -> str:
    return CURIE.sub(lambda mo: m.get(mo.group(0), mo.group(0)), s)


def version_node(doc):
    if "urpx:hasRatePlan" in doc:
        return doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]
    return doc["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"]


def expire(doc, version_id: str, at: str) -> int:
    """Bound every definition of version_id in doc at `at`. Returns the count."""
    n = 0

    def f(d, _owner):
        nonlocal n
        if d.get("@id") == version_id and rescope_iris.node_type(d) in VERSION_TYPES:
            items = list(d.items())
            d.clear()
            for k, v in items:
                if k == "urpx:expirationDateTime":
                    continue
                d[k] = v
                if k == "urpx:effectiveDateTime":
                    d["urpx:expirationDateTime"] = f"{at}T00:00:00"
            n += 1
    walk(doc, f)
    if n:
        ctx = doc["@context"]
        if "urpx:expirationDateTime" not in ctx:
            out = {}
            for k, v in ctx.items():
                out[k] = v
                if k == "urpx:effectiveDateTime":
                    out["urpx:expirationDateTime"] = {"@type": "xsd:dateTime"}
            doc["@context"] = out
    return n


# --- tariff.toml ------------------------------------------------------------

def q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def emit_source(lines: list[str], d: dict, indent: str = "") -> None:
    for k in ("url", "sha256", "retrieved_on", "media_type", "filing_type"):
        if k in d:
            lines.append(f"{indent}{k} = {q(d[k])}")


def emit_toml(t: dict, extraction_notes: str) -> str:
    L = ["# Identity " + "-" * 69,
         f"utility = {q(t['utility'])}", f"schedule = {q(t['schedule'])}",
         f"effective_date = {q(t['effective_date'])}", "",
         "# Source " + "-" * 71, "[source]"]
    src = t["source"]
    if "landing_page" in src:
        L.append(f"landing_page = {q(src['landing_page'])}")
    if "url" in src:
        emit_source(L, src)
    for name, sub in src.items():
        if isinstance(sub, dict):
            L += ["", f"  [source.{name}]"]
            emit_source(L, sub, "  ")
    L += ["# paloalto.gov rejects standard urllib/requests with HTTP 403 (TLS",
          "# fingerprint check). Re-fetch via curl_cffi with Chrome impersonation:",
          "# requests.Session(impersonate=\"chrome120\").", "",
          "# Regulatory " + "-" * 67, "[regulator]", f"authority = {q(t['regulator']['authority'])}", "",
          "# Extraction " + "-" * 67, "[extraction]", f"tool = {q(t['extraction']['tool'])}",
          f"extracted_on = {q(t['extraction']['extracted_on'])}",
          f'notes = """\n{extraction_notes}\n"""', "",
          "# Validation " + "-" * 67, "[validation]",
          f"shacl_passed = {'true' if t['validation']['shacl_passed'] else 'false'}",
          f"validator = {q(t['validation']['validator'])}",
          f"validated_on = {q(t['validation']['validated_on'])}", "",
          "# Modeling " + "-" * 68, "[modeling]",
          f"complete = {'true' if t['modeling']['complete'] else 'false'}"]
    if t["modeling"]["deferrals"]:
        L.append("deferrals = [")
        L += [f" {q(x)}," for x in t["modeling"]["deferrals"]]
        L.append("]")
    else:
        L.append("deferrals = []")
    if "applicable_modifiers" in t["modeling"]:
        L.append("applicable_modifiers = [")
        L += [f" {q(x)}," for x in t["modeling"]["applicable_modifiers"]]
        L.append("]")
    L += ["", "# Review " + "-" * 71, "[review]", f"status = {q(t['review']['status'])}",
          f"notes = {q(t['review']['notes'])}", ""]
    text = "\n".join(L)
    if tomllib.loads(text) != {**t, "extraction": {**t["extraction"], "notes": extraction_notes + "\n"}}:
        raise SystemExit(f"{t['schedule']}: emitted TOML does not round-trip")
    return text


# --- one schedule -------------------------------------------------------------

def held(schedule: str, new: str) -> Path:
    vs = sorted(p for p in (CPAU / schedule / "versions").iterdir() if p.is_dir() and p.name < new)
    return vs[-1]


def jsonld_in(d: Path) -> Path:
    (p,) = [x for x in d.glob("rate-plan*.jsonld")]
    return p


def build(schedule: str, new: str, ed: dict, pdfs: Path, built: dict) -> None:
    path, sha, prices = ed["schedules"][schedule]
    retrieved = ed["retrieved"]
    old_dir = held(schedule, new)
    old = old_dir.name
    new_dir = old_dir.parent / new
    src_pdf = pdfs / f"cpau_{schedule}_{new}.pdf"
    if hashlib.sha256(src_pdf.read_bytes()).hexdigest() != sha:
        raise SystemExit(f"{schedule}: {src_pdf} does not hash to the recorded sha256")
    old_pdf = old_dir / f"cpau_{schedule}_{old}.pdf"
    att = attested(old_pdf, src_pdf)
    fm = figure_map(att)

    old_path = jsonld_in(old_dir)
    doc = load(old_path)
    m = rename_map(doc, schedule, old, new)
    inlined = doc.get("urpx:hasRatePlanModifier") if "urpx:hasRatePlan" in doc else None
    for rpm in inlined if isinstance(inlined, list) else []:
        mod = rpm["@id"].split(":", 1)[1]
        if mod in built:
            m.update({k: v for k, v in built[mod]["map"].items() if k not in m})
    apply_ids(doc, m)

    # Inlined modifiers reissued in this edition: take the standalone copy.
    if "urpx:hasRatePlan" in doc and isinstance(doc.get("urpx:hasRatePlanModifier"), list):
        mods = doc["urpx:hasRatePlanModifier"]
        for k, rpm in enumerate(mods):
            mod = rpm["@id"].split(":", 1)[1]
            if mod in built:
                held_copy = copy.deepcopy(built[mod]["held_modifier"])
                apply_ids(held_copy, built[mod]["map"])
                renamed = copy.deepcopy(rpm)
                if json.dumps(renamed, sort_keys=True) != json.dumps(held_copy, sort_keys=True):
                    raise SystemExit(f"{schedule}: inlined {mod} differs from its standalone filing")
                mods[k] = copy.deepcopy(built[mod]["modifier"])

    v = version_node(doc)
    own = v["@id"]
    changes: list[str] = []

    def f(d, owner):
        if owner != own:
            return
        if d is v:
            d["urpx:effectiveDateTime"] = f"{new}T00:00:00"
            d.pop("urpx:expirationDateTime", None)
            if "urpx:version" in d:
                d["urpx:version"] = new
            if "urpx:modifierVersionNumber" in d:
                d["urpx:modifierVersionNumber"] = new
            d["urpx:changeReason"] = {"@id": "urpx:rateCase"}
        t = rescope_iris.node_type(d)
        if t == "urpx:Price":
            if "urpx:startDate" in d:
                d["urpx:startDate"] = new
        if t == "urpx:DataSourceReference":
            d["urpx:url"] = f"{BASE_URL}/{path}"
            d["urpx:fileName"] = path.rsplit("/", 1)[1]
            d["urpx:dateRetrieved"] = retrieved
        if "urpx:evaluatedOn" in d:
            d["urpx:evaluatedOn"] = f"{retrieved}T00:00:00"
        for k, x in list(d.items()):
            if k in NOT_PROSE or not isinstance(x, str):
                continue
            y = move_figures(move_curies(x, m), fm).replace(old, new)
            if y != x:
                d[k] = y
                changes.append(f"{d.get('@id')} {k}")
    walk(doc, f)

    # Prices, each pair attested by the two sheets.
    inv = {b: a for a, b in m.items()}
    seen = set()
    rows = []

    def p(d, owner):
        if owner != own or rescope_iris.node_type(d) != "urpx:Price" or "urpx:unitPrice" not in d:
            return
        held_id = inv.get(d["@id"], d["@id"])
        if held_id in seen:
            return
        if held_id not in prices:
            raise SystemExit(f"{schedule}: no new price for {held_id}")
        a, b = prices[held_id]
        if d["urpx:unitPrice"] != a:
            raise SystemExit(f"{schedule}: {held_id} is {d['urpx:unitPrice']}, table says {a}")
        if Decimal(b).copy_abs() not in att.get(Decimal(a).copy_abs(), set()):
            raise SystemExit(f"{schedule}: {held_id} {a} -> {b} is not attested by the sheets "
                             f"(aligned: {sorted(att.get(Decimal(a).copy_abs(), set()))})")
        seen.add(held_id)
        rows.append((held_id, a, b))
        d["urpx:unitPrice"] = b
    walk(doc, p)
    if set(prices) - seen:
        raise SystemExit(f"{schedule}: table names prices the document lacks: {sorted(set(prices) - seen)}")

    new_dir.mkdir(exist_ok=True)
    shutil.copyfile(src_pdf, new_dir / f"cpau_{schedule}_{new}.pdf")
    new_path = new_dir / old_path.name.replace(old, new)
    dump(new_path, doc)

    # Manifest.
    t = tomllib.loads((old_dir / "tariff.toml").read_text(encoding="utf-8"))
    t["effective_date"] = new
    base = t["source"]["base"] if "base" in t["source"] else t["source"]
    base.update({"url": f"{BASE_URL}/{path}", "sha256": sha, "retrieved_on": retrieved})
    for name, sub in t["source"].items():
        if isinstance(sub, dict) and name.startswith("modifier_"):
            mod = name[len("modifier_"):].replace("_", "-")
            if mod in built:
                sub.update(built[mod]["source"])
            mod_dir = CPAU / mod / "versions" / new if mod in built else held(mod, new)
            fn = f"cpau_{mod}_{mod_dir.name}.pdf"
            shutil.copyfile(mod_dir / fn, new_dir / fn)
    t["extraction"] = {"tool": "manual", "extracted_on": retrieved}
    t["validation"]["validated_on"] = retrieved
    defs = [move_figures(move_curies(x, m), fm) for x in t["modeling"]["deferrals"]]
    edit = ed.get("edits", {}).get(schedule, {})
    for prefix in edit.get("drop", []):
        keep = [x for x in defs if not x.startswith(prefix)]
        if len(keep) != len(defs) - 1:
            raise SystemExit(f"{schedule}: drop {prefix!r} matched {len(defs) - len(keep)} deferrals")
        defs = keep
    for a, b in edit.get("replace", []):
        if not any(a in x for x in defs):
            raise SystemExit(f"{schedule}: replacement {a!r} found in no deferral")
        defs = [x.replace(a, b) for x in defs]
    t["modeling"]["deferrals"] = defs
    t["review"]["notes"] = (f"Derived from the {old} version by scripts/build-cpau-version.py: every Price "
                            f"reconciled to the sheets effective {new}. See [extraction] notes.")
    moved = [f" {i.split(':', 1)[1]}: {a} -> {b}" for i, a, b in rows if a != b]
    kept = [f" {i.split(':', 1)[1]}: {a}" for i, a, b in rows if a == b]
    notes = [f"Source bytes. Retrieved {retrieved} from {path.rsplit('/', 1)[1]}, linked from CPAU's "
             f"{'Residential' if 'residential' in path else 'Business'}-Rates page; the sha256 above is "
             "its hash.", "",
             f"Supersession. Every sheet of this document is effective {new} and supersedes the "
             f"sheet of the same number dated {old}, so the {old} version expires at {new}.", ""]
    if moved:
        notes += [f"Price changes from the {old} version:"] + moved
    if kept:
        notes += ([""] if moved else []) + [f"Unchanged from the {old} version:"] + kept
    dump_text = emit_toml(t, "\n".join(notes))
    (new_dir / "tariff.toml").write_text(dump_text, encoding="utf-8")

    built[schedule] = {
        "map": m, "date": new,
        "source": {"url": f"{BASE_URL}/{path}", "sha256": sha, "retrieved_on": retrieved},
        "held_modifier": load(old_path).get("urpx:hasRatePlanModifier"),
        "modifier": doc.get("urpx:hasRatePlanModifier"),
        "old_version": f"cpau:{schedule}-{old}",
    }
    print(f"{schedule}: {old} -> {new}, {len(rows)} prices ({len(moved)} moved), "
          f"{len(m)} @ids rescoped, {len(changes)} prose fields changed")
    for c in changes:
        print(f"    prose: {c}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--effective", required=True, choices=sorted(EDITIONS))
    ap.add_argument("--pdfs", required=True, type=Path)
    args = ap.parse_args()
    if shutil.which("pdftotext") is None:
        print("REFUSED: pdftotext not on PATH", file=sys.stderr)
        return 3
    new = args.effective
    ed = EDITIONS[new]
    built: dict = {}
    # Modifiers first: base filings inline them.
    order = sorted(ed["schedules"], key=lambda s: (not s.startswith(("e-nse", "e-eec")), s))
    for s in order:
        if (CPAU / s / "versions" / new).exists():
            raise SystemExit(f"{s}: {new} already exists; remove it to rebuild")
    for s in order:
        build(s, new, ed, args.pdfs, built)

    expiring = {b["old_version"] for b in built.values()}
    for p in sorted(CPAU.glob("*/versions/*/*.jsonld")):
        if p.parent.name == new:
            continue
        doc = load(p)
        n = sum(expire(doc, vid, new) for vid in expiring)
        if n:
            dump(p, doc)
            print(f"expired {n} version definition(s) in {p.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
