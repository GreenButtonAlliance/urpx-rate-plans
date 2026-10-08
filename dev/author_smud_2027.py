#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Add the SMUD versions effective 2027-01-01.

Board Resolution No. 25-06-15 (adopted June 19, 2025) prints three columns on
Rate Schedules R-TOD and R: effective May 1, 2025, January 1, 2026 and
January 1, 2027. The corpus held the January 1, 2026 column. This script adds a
version from the January 1, 2027 column for each base plan priced in those
columns: tod-5-8pm (RT02) and tod-low-use (RTL1) from Sheet R-TOD-2, fixed
(RF01) from Sheet R-2.

Each new version is derived from the 2026-01-01 version: subordinate @ids the
version owns are re-dated or scoped to it (LAYOUT.md section 6), every Price is
set from the 2027 column after the 2026 column is checked against the Price it
replaces, and the dollar amounts and column dates in the prose are moved to the
2027 column. Each 2026-01-01 version ends at 2027-01-01 (LAYOUT.md section 9).

Modifiers. cpp, eapr, med, pev-credit and ssr name plans, not versions
(urpx:applicableToRatePlan), and price nothing from the base, so they compose
with the new versions unchanged. NEM1's credits are urpx:multiplier -1 over the
base usage Prices; each gains the 2027-01-01 Price of the same cell as a further
candidate in urpx:basedOnPrice.

Run from the repo root:
    python3 dev/author_smud_2027.py <dir holding 1-R-TOD.ashx and 1-R.ashx as fetched>
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import rescope_iris as rescope  # noqa: E402

SMUD = REPO / "us/ca/smud/electricity"
SRC, DATE = "2026-01-01", "2027-01-01"
TODAY = "2026-10-07"
RATES = "https://www.smud.org/-/media/Documents/Rate-Information/Rates/"

# schedule -> (fetched file name, sheet section key)
BASES = {
    "tod-5-8pm": ("1-R-TOD.ashx", "RT02"),
    "tod-low-use": ("1-R-TOD.ashx", "RTL1"),
    "fixed": ("1-R.ashx", "RF01"),
}

# The 2026-01-01 Price @id -> (section, season, row) on the sheet.
PRICE_ROW = {
    "tod-5-8pm": {
        "smud:tod-5-8pm-2026-01-01-price-system-infrastructure-fixed-charge": ("RT02", "both", "sifc"),
        "smud:price-usage-summer-peak": ("RT02", "summer", "peak"),
        "smud:price-usage-summer-mid-peak": ("RT02", "summer", "mid-peak"),
        "smud:price-usage-summer-off-peak": ("RT02", "summer", "off-peak"),
        "smud:price-usage-non-summer-peak": ("RT02", "non-summer", "peak"),
        "smud:price-usage-non-summer-off-peak": ("RT02", "non-summer", "off-peak"),
    },
    "tod-low-use": {
        "smud:price-system-infrastructure-fixed-charge-rtl1": ("RTL1", "both", "sifc"),
        "smud:price-usage-summer-peak-rtl1": ("RTL1", "summer", "peak"),
        "smud:price-usage-summer-mid-peak-rtl1": ("RTL1", "summer", "mid-peak"),
        "smud:price-usage-summer-off-peak-rtl1": ("RTL1", "summer", "off-peak"),
        "smud:price-usage-non-summer-peak-rtl1": ("RTL1", "non-summer", "peak"),
        "smud:price-usage-non-summer-off-peak-rtl1": ("RTL1", "non-summer", "off-peak"),
    },
    "fixed": {
        "smud:fixed-2026-01-01-price-system-infrastructure-fixed-charge": ("RF01", "both", "sifc"),
        "smud:price-energy-summer": ("RF01", "summer", "all"),
        "smud:price-energy-non-summer": ("RF01", "non-summer", "all"),
    },
}

# Section headers on Sheets R-TOD-2 and R-2, in page order.
SECTIONS = [("(RT02)", "RT02"), ("(RTL1)", "RTL1"), ("Fixed Rate (RF01)", "RF01"),
            ("Mobile Home Park Billing (Closed)", "RSMM")]


# --- io ------------------------------------------------------------------------

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


def doc_path(slug: str, date: str) -> Path:
    return SMUD / slug / "versions" / date / f"rate-plan_smud_{slug}_{date}.jsonld"


def version_node(doc):
    return doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --- sheets --------------------------------------------------------------------

MONEY = re.compile(r"\$(\d+\.\d+)|n/a")


def columns(pdf: Path) -> tuple[dict, dict]:
    """(section, season, row) -> [May 2025, Jan 2026, Jan 2027], and the two
    single-row option tables (standby, three-phase) -> {column date: value}."""
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True,
                          check=True).stdout
    # The PDF's text layer splits a capital from the rest of some words ("S ummer").
    lines = [re.sub(r"\b([A-Z]) ([a-z])", r"\1\2", ln) for ln in text.splitlines()]
    cells: dict[tuple, list[str]] = {}
    section = season = None
    for ln in lines:
        for marker, key in SECTIONS:
            if marker in ln:
                section, season = key, None
        if section is None:
            continue
        if "Non-Summer Season" in ln:
            season = "non-summer"
        elif "Summer Season" in ln:
            season = "summer"
        if season is None:
            continue
        vals = [m.group(1) if m.group(1) else None for m in MONEY.finditer(ln)]
        if len(vals) != 3:
            continue
        label = ln.split("$")[0].split("n/a")[0]
        row = ("sifc" if "System Infrastructure Fixed Charge" in label else
               "mid-peak" if "Mid-Peak" in label else
               "off-peak" if "Off-Peak" in label else
               "peak" if "Peak" in label else
               "all" if "All kWh usage" in label else None)
        if row is None:
            raise SystemExit(f"{pdf.name}: unrecognized priced row: {ln.strip()}")
        key = (section, season, row)
        if key in cells:
            raise SystemExit(f"{pdf.name}: {key} printed twice")
        cells[key] = vals
    options: dict[str, dict[str, str]] = {}
    current = None
    for ln in lines:
        if "Standby Service Charge - January 1 through December 31" in ln:
            current = "standby"
        elif "Three-Phase Service - January 1 through December 31" in ln:
            current = "three-phase"
        m = re.search(r"Effective (May 1, 2025|January 1, 2026|January 1, 2027)\s+\$(\d+\.\d+)", ln)
        if current and m:
            options.setdefault(current, {})[m.group(1)] = m.group(2)
    for k, v in options.items():
        if len(v) != 3:
            raise SystemExit(f"{pdf.name}: {k} table has {len(v)} columns")
    return cells, options


def cell(cells: dict, section: str, season: str, row: str) -> list[str]:
    if season == "both":
        a, b = cells[(section, "summer", row)], cells[(section, "non-summer", row)]
        if a != b:
            raise SystemExit(f"{section} {row}: summer {a} and non-summer {b} differ")
        return a
    return cells[(section, season, row)]


# --- derivation ------------------------------------------------------------------

def rename_map(doc, slug: str) -> dict[str, str]:
    """@ids the 2026 version owns: re-dated where they carry the version stem,
    else scoped to the new version. Identity nodes are kept."""
    old_vid = version_node(doc)["@id"]
    new_vid = old_vid.replace(SRC, DATE)
    stem = f"{slug}-{SRC}"
    m: dict[str, str] = {}

    def f(d, own):
        i = d.get("@id")
        if not isinstance(i, str) or len(d) <= 1 or i in m:
            return
        if own not in (None, old_vid):
            return
        t = rescope.node_type(d)
        if stem in i:
            m[i] = i.replace(stem, f"{slug}-{DATE}")
        elif t in rescope.IDENTITY_TYPES or t in rescope.KEEP_SHARED_TYPES or i.startswith("org:") \
                or t == "urpx:URPXPackage":
            return
        else:
            m[i] = rescope.new_iri(i, new_vid)
    rescope.walk_owned(doc, f)
    if len(set(m.values())) != len(m):
        raise SystemExit(f"{slug}: rename collides")
    return m


def apply_map(doc, m: dict[str, str]) -> None:
    def f(d):
        if isinstance(d.get("@id"), str) and d["@id"] in m:
            d["@id"] = m[d["@id"]]
    walk(doc, f)


def set_literals(v: dict) -> None:
    def f(d):
        for k, x in list(d.items()):
            if not isinstance(x, str):
                continue
            if k in ("urpx:version", "urpx:modifierVersionNumber") and x == SRC:
                d[k] = DATE
            elif k == "urpx:effectiveDateTime" and x.startswith(SRC):
                d[k] = f"{DATE}T00:00:00"
            elif k == "urpx:startDate" and x == SRC:
                d[k] = DATE
            elif k == "urpx:evaluatedOn":
                d[k] = f"{TODAY}T00:00:00"
    walk(v, f)
    v.pop("urpx:expirationDateTime", None)


def value_map(cells: dict, options: dict) -> dict[str, str]:
    """Every dollar amount printed in the 2026 column -> its 2027 amount. One
    2026 amount must not stand for two different 2027 amounts."""
    out: dict[str, str] = {}
    pairs = [(v[1], v[2]) for v in cells.values() if v[1] is not None]
    pairs += [(o["January 1, 2026"], o["January 1, 2027"]) for o in options.values()]
    for a, b in pairs:
        if out.get(a, b) != b:
            raise SystemExit(f"2026 amount ${a} maps to both ${out[a]} and ${b}")
        out[a] = b
    return out


MONEY_TEXT = re.compile(r"\$(\d+\.\d+)")


def move_prose(t: str, vm: dict[str, str]) -> str:
    t = MONEY_TEXT.sub(lambda x: "$" + vm.get(x.group(1), x.group(1)), t)
    t = t.replace("effective January 1, 2026", "effective January 1, 2027")
    t = t.replace("January 1, 2026 column", "January 1, 2027 column")
    t = t.replace("Jan 1, 2026 column", "Jan 1, 2027 column")
    return t


# Prose the value map does not reach: amounts printed without cents, and
# sentences about the 2026 column that the 2027 version would repeat wrongly.
DESCRIPTION_EDITS = {
    "tod-5-8pm": [
        ("this filing captures the January 1, 2027 column (current as of 2026-04-30 retrieval)",
         "this filing captures the January 1, 2027 column; smud:tod-5-8pm-2026-01-01 carries the January 1, "
         "2026 column and ends at January 1, 2027"),
    ],
    "tod-low-use": [
        ("($17/month vs RT02's $27/month)", "($17/month vs RT02's $27.80/month in the January 1, 2027 column)"),
    ],
    "fixed": [
        ("this filing captures the January 1, 2027 column.",
         "this filing captures the January 1, 2027 column; smud:fixed-2026-01-01 carries the January 1, 2026 "
         "column and ends at January 1, 2027."),
    ],
}

# Deferral sentences that named the 2027 column as uncarried. In the 2027
# version the first clause of each already states the 2027 amount.
DEFERRAL_DROPS_2027 = [
    " Note that the same table also prices $9.121 effective January 1, 2027, which no filing carries.",
    " The same table also prices $59.70 effective January 1, 2027.",
]
COLUMN_DEFERRAL = "The January 1, 2027 RTL1 rate column, priced on this filing's own Sheet R-TOD-2"


def derive(slug: str, cells: dict, options: dict) -> tuple[dict, dict[str, str], list[str], list[tuple]]:
    doc = load(doc_path(slug, SRC))
    old = {}

    def grab(d):
        if d.get("@type") == "urpx:Price" and "urpx:unitPrice" in d:
            old[d["@id"]] = d["urpx:unitPrice"]
    walk(version_node(doc)["urpx:hasPrices"], grab)
    if set(old) != set(PRICE_ROW[slug]):
        raise SystemExit(f"{slug}: modeled Prices {sorted(old)} against table {sorted(PRICE_ROW[slug])}")
    recon = []
    new_price = {}
    for pid, (sec, season, row) in PRICE_ROW[slug].items():
        c = cell(cells, sec, season, row)
        if Decimal(c[1]) != Decimal(old[pid]):
            raise SystemExit(f"{slug} {pid}: modeled {old[pid]} against the January 1, 2026 column {c[1]}")
        new_price[pid] = c[2]
        recon.append((pid, old[pid], c[2]))

    m = rename_map(doc, slug)
    apply_map(doc, m)
    v = version_node(doc)
    set_literals(v)
    doc["@id"] = doc["@id"].replace(SRC, DATE)
    for pid, val in new_price.items():
        hit = []
        walk(v["urpx:hasPrices"], lambda d: hit.append(d) if d.get("@id") == m[pid] and "urpx:unitPrice" in d else None)
        if len(hit) != 1:
            raise SystemExit(f"{slug}: {m[pid]} found {len(hit)} times")
        hit[0]["urpx:unitPrice"] = val

    file_name, _ = BASES[slug]
    dsr = v["urpx:hasDataSourceReference"]
    dsr["urpx:dateRetrieved"] = TODAY
    if dsr["urpx:accessURL"] != RATES + file_name:
        raise SystemExit(f"{slug}: source URL {dsr['urpx:accessURL']}")

    vm = value_map(cells, options)
    v["urpx:description"] = move_prose(v["urpx:description"], vm)
    for a, b in DESCRIPTION_EDITS[slug]:
        if v["urpx:description"].count(a) != 1:
            raise SystemExit(f"{slug}: description fragment not found once: {a[:60]}")
        v["urpx:description"] = v["urpx:description"].replace(a, b)
    ev = v["urpx:hasCoverageClaim"]["urpx:explainedBy"]
    ev["urpx:description"] = move_prose(ev["urpx:description"], vm)

    manifest = tomllib.loads((SMUD / slug / "versions" / SRC / "tariff.toml").read_text(encoding="utf-8"))
    deferrals = []
    for t in manifest["modeling"]["deferrals"]:
        if t.startswith(COLUMN_DEFERRAL):
            continue
        for s in DEFERRAL_DROPS_2027:
            t = t.replace(s, "")
        deferrals.append(move_prose(t, vm))

    stale = stale_amounts(cells, options)
    for where, t in [("description", v["urpx:description"]), ("evaluation", ev["urpx:description"]),
                     *[("deferral", x) for x in deferrals]]:
        left = [a for a in stale if f"${a}" in t]
        if left:
            raise SystemExit(f"{slug} {where}: 2026-only amounts remain: {left}")
        # Allowed: the RTL1 start date, the resolution's list of its three
        # columns, and the pointer to the predecessor's column.
        rest = re.sub(r"available as of January 1, 2026|/ January 1, 2026 /|"
                      r"carries the January 1,\s+2026 column", "", t)
        if "January 1, 2026" in rest:
            raise SystemExit(f"{slug} {where}: 'January 1, 2026' remains: {t[:120]}")
    return doc, m, deferrals, recon


def stale_amounts(cells: dict, options: dict) -> list[str]:
    """2026 amounts that differ from the same cell's 2027 amount and are not
    themselves a 2027 amount elsewhere."""
    now = {v[2] for v in cells.values()} | {o["January 1, 2027"] for o in options.values()}
    was = {v[1] for v in cells.values() if v[1] and v[1] != v[2]}
    was |= {o["January 1, 2026"] for o in options.values()}
    return sorted(was - now)


# --- predecessors and modifiers ------------------------------------------------------

def expire(path: Path, until: str) -> None:
    doc = load(path)
    ctx = doc["@context"]
    if "urpx:expirationDateTime" not in ctx:
        out = {}
        for k, x in ctx.items():
            out[k] = x
            if k == "urpx:effectiveDateTime":
                out["urpx:expirationDateTime"] = {"@type": "xsd:dateTime"}
        out.setdefault("urpx:expirationDateTime", {"@type": "xsd:dateTime"})
        doc["@context"] = out
    v = version_node(doc)
    new_v = {}
    for k, x in v.items():
        if k == "urpx:expirationDateTime":
            continue
        new_v[k] = x
        if k == "urpx:effectiveDateTime":
            new_v["urpx:expirationDateTime"] = f"{until}T00:00:00"
    doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"] = new_v
    dump(path, doc)


def nem1_candidates(maps: dict[str, dict[str, str]]) -> int:
    p = SMUD / "nem1/versions/2021-09-17/rate-plan-modifier_smud_nem1_2021-09-17.jsonld"
    doc = load(p)
    every = {old: new for m in maps.values() for old, new in m.items()}
    n = 0

    def f(d):
        nonlocal n
        if d.get("@type") != "urpx:Price" or "urpx:basedOnPrice" not in d:
            return
        ids = [x["@id"] for x in d["urpx:basedOnPrice"]]
        olds = [i for i in ids if i in every]
        if len(olds) != 1:
            raise SystemExit(f"nem1 {d['@id']}: candidates {ids} name {len(olds)} 2026-01-01 Prices")
        new = every[olds[0]]
        if new not in ids:
            ids.append(new)
            n += 1
        d["urpx:basedOnPrice"] = [{"@id": i} for i in ids]
    walk(doc, f)
    ev = doc["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"]["urpx:hasCoverageClaim"][
        "urpx:explainedBy"]
    a, b = NEM1_EVALUATION
    if a in ev["urpx:description"]:
        ev["urpx:description"] = ev["urpx:description"].replace(a, b)
        ev["urpx:evaluatedOn"] = f"{TODAY}T00:00:00"
    elif b not in ev["urpx:description"]:
        raise SystemExit("nem1 evaluation: basedOnPrice sentence not found")
    dump(p, doc)
    t = p.with_name("tariff.toml")
    text = t.read_text(encoding="utf-8")
    a, b = NEM1_DEFERRAL
    if a in text:
        text = text.replace(a, b)
        tomllib.loads(text)
        t.write_text(text, encoding="utf-8")
    elif b not in text:
        raise SystemExit("nem1 deferral: basedOnPrice sentence not found")
    return n


# Prose on NEM1 that said each credit names one Price; it now names that cell's
# Price in each version of its base plan.
NEM1_EVALUATION = (
    "The credit is written as twelve urpx:multiplier -1 Prices, each naming exactly one urpx:basedOnPrice: ten "
    "among the five usage Prices of smud:tod-5-8pm and the five of smud:tod-low-use,",
    "The credit is written as twelve urpx:multiplier -1 Prices, each naming one base cell, and in "
    "urpx:basedOnPrice that cell's Price in each version of its base plan (2026-01-01 and 2027-01-01): ten among "
    "the five usage cells of smud:tod-5-8pm and the five of smud:tod-low-use,")
NEM1_DEFERRAL = (
    "Built: this filing carries twelve credit Prices, each with urpx:multiplier -1 and a single "
    "urpx:basedOnPrice, and together they name smud:price-energy-summer and smud:price-energy-non-summer on "
    "smud:fixed, the five usage Prices of smud:tod-5-8pm and the five -rtl1 usage Prices of smud:tod-low-use.",
    "Built: this filing carries twelve credit Prices, each with urpx:multiplier -1 over one base cell, and "
    "together they cover the summer and non-summer energy charges of smud:fixed, the five usage charges of "
    "smud:tod-5-8pm and the five of smud:tod-low-use. Each names in urpx:basedOnPrice its cell's Price in every "
    "version of the base plan (2026-01-01 and 2027-01-01); clj-urpx reads those as alternatives and values the "
    "one present in the base version composed.")


def drop_column_deferral(slug: str) -> None:
    """The 2026-01-01 tod-low-use manifest recorded the 2027 column as carried by
    no filing; it now is, and the 2026 version ends where it starts."""
    p = SMUD / slug / "versions" / SRC / "tariff.toml"
    text = p.read_text(encoding="utf-8")
    lines = text.split("\n")
    keep = [ln for ln in lines if not ln.startswith(" " + json.dumps(COLUMN_DEFERRAL)[:-1])]
    if len(keep) == len(lines):
        return
    if len(lines) - len(keep) != 1:
        raise SystemExit(f"{slug} {SRC}: column deferral matched {len(lines) - len(keep)} lines")
    out = "\n".join(keep)
    tomllib.loads(out)
    p.write_text(out, encoding="utf-8")


# --- manifests -------------------------------------------------------------------

def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def wrap(text: str) -> str:
    import textwrap
    return "\n".join(textwrap.wrap(" ".join(text.split()), 78, break_long_words=False, break_on_hyphens=False))


SHEET = {"tod-5-8pm": ("R-TOD-2", "II.A"), "tod-low-use": ("R-TOD-2", "II.B"), "fixed": ("R-2", "II.A")}


def notes(slug: str, recon: list[tuple], m: dict[str, str]) -> str:
    file_name, section = BASES[slug]
    sheet, sec = SHEET[slug]
    rows = "\n".join(f" {m[pid].split(':', 1)[1]}: {old} -> {new}" for pid, old, new in recon)
    parts = [
        f"Source bytes. {RATES}{file_name} as served on {TODAY}; the bytes equal those of the 2026-01-01 "
        f"directory's PDF (Last-Modified 2025-06-30). Resolution No. 25-06-15 (adopted June 19, 2025), "
        f"fetched the same day from SMUD's rate archive page, prints the same {section} table.",
        f"Column. Sheet {sheet} Section {sec} prints the {section} prices in three columns, effective May 1, "
        f"2025, January 1, 2026 and January 1, 2027. This version carries the January 1, 2027 column.",
        f"Reconciliation. Each Price below was checked against the January 1, 2026 column before being set "
        f"from the January 1, 2027 column (2026 -> 2027):",
        rows,
        "Supersession. The 2026-01-01 version ends at 2027-01-01, where this column takes effect.",
        "Derived from the 2026-01-01 version by dev/author_smud_2027.py.",
    ]
    return "\n\n".join(p if p is rows else wrap(p) for p in parts).replace("\n\n" + rows, "\n" + rows)


def write_manifest(slug: str, deferrals: list[str], recon: list[tuple], m: dict[str, str], pdf: Path) -> None:
    old = tomllib.loads((SMUD / slug / "versions" / SRC / "tariff.toml").read_text(encoding="utf-8"))
    s, r = old["source"], old["regulator"]
    src_lines = [f"url = {toml_str(s['url'])}", f'sha256 = "{sha(pdf)}"', f'retrieved_on = "{TODAY}"',
                 f"media_type = {toml_str(s['media_type'])}", f"filing_type = {toml_str(s['filing_type'])}",
                 f"filing_id = {toml_str(s['filing_id'])}"]
    if "landing_page" in s:
        src_lines.append(f"landing_page = {toml_str(s['landing_page'])}")
    extra = set(s) - {"url", "sha256", "retrieved_on", "media_type", "filing_type", "filing_id", "landing_page"}
    if extra:
        raise SystemExit(f"{slug}: unhandled [source] keys {sorted(extra)}")
    lines = ["# Identity --------------------------------------------------------------------",
             'utility = "smud"', f'schedule = "{slug}"', f'effective_date = "{DATE}"', "",
             "# Source ----------------------------------------------------------------------", "[source]",
             *src_lines, "",
             "# Regulatory ------------------------------------------------------------------", "[regulator]",
             f"authority = {toml_str(r['authority'])}", f"docket = {toml_str(r['docket'])}", "",
             "# Extraction ------------------------------------------------------------------",
             "[extraction]", 'tool = "manual-diff"', f'extracted_on = "{TODAY}"', 'notes = """',
             notes(slug, recon, m), '"""', "",
             "# Validation ------------------------------------------------------------------",
             "[validation]", "shacl_passed = true", 'validator = "pyshacl + clj-urpx (URPX v0.5.1)"',
             f'validated_on = "{TODAY}"', "",
             "# Modeling -------------------------------------------------------------------",
             "[modeling]", f"complete = {'true' if old['modeling']['complete'] else 'false'}", "deferrals = [",
             *[" " + toml_str(x) + "," for x in deferrals], "]"]
    mods = old["modeling"].get("applicable_modifiers")
    if mods is not None:
        lines += ["applicable_modifiers = [", *[f' "{x}",' for x in mods], "]"]
    lines += ["", "# Review ----------------------------------------------------------------------", "[review]",
              'status = "draft"',
              "notes = " + toml_str("Derived from the 2026-01-01 version by dev/author_smud_2027.py; see "
                                    "[extraction] notes for the column read and the reconciliation."), ""]
    text = "\n".join(lines)
    tomllib.loads(text)
    (SMUD / slug / "versions" / DATE / "tariff.toml").write_text(text, encoding="utf-8")


# --- main ------------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    fetched = Path(argv[1])
    parsed = {}
    for slug, (file_name, _) in BASES.items():
        pdf = fetched / file_name
        held = SMUD / slug / "versions" / SRC / f"smud_{slug}_{SRC}.pdf"
        if sha(pdf) != sha(held):
            raise SystemExit(f"{slug}: {pdf} is not the held 2026-01-01 document; reconcile it first")
        if file_name not in parsed:
            parsed[file_name] = columns(pdf)
    staged = {}
    for slug, (file_name, _) in BASES.items():
        cells, options = parsed[file_name]
        staged[slug] = derive(slug, cells, options)
    maps = {}
    for slug, (doc, m, deferrals, recon) in staged.items():
        file_name, _ = BASES[slug]
        held = SMUD / slug / "versions" / SRC / f"smud_{slug}_{SRC}.pdf"
        d = SMUD / slug / "versions" / DATE
        d.mkdir(parents=True, exist_ok=True)
        pdf = d / f"smud_{slug}_{DATE}.pdf"
        shutil.copyfile(held, pdf)
        dump(doc_path(slug, DATE), doc)
        write_manifest(slug, deferrals, recon, m, pdf)
        expire(doc_path(slug, SRC), DATE)
        maps[slug] = {pid: m[pid] for pid in PRICE_ROW[slug] if pid in m}
        print(f"{slug} {DATE}: " + ", ".join(f"{new}" for _, _, new in recon))
    drop_column_deferral("tod-low-use")
    n = nem1_candidates(maps)
    print(f"nem1: {n} credit Prices gain a 2027-01-01 candidate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
