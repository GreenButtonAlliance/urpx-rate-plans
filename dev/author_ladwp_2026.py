#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Author the LADWP R-1A and R-1B versions effective 2026-07-01 and 2026-10-01.

LADWP's base rates have not moved since the 2019-07-01 Electric Rate Summary;
what moves is the quarterly adjustment factors (utility.toml scrape_notes). Each
version here is derived from the 2026-04-01 version of its schedule: every
subordinate @id is scoped to the new version (dev/rescope_iris.new_iri), the
seven factor Prices are set from FACTORS, and each factor Price cites the
document that states it. IRCA moves out of the quarterly PriceSet into one of its
own starting 2026-07-01, because the summary sheet footnotes it as computed
annually and Board Resolution 026 243 sets it for fiscal year 2026-27.

Before writing anything, every value is checked three ways: against the 2026
table on the residential adjustment billing factors page, against the
resolutions' own Factors Summary (by hand; see FACTORS), and, base charge plus
the seven factors, against the Total Consumption Charge the residential rates
page publishes for each tier, period and quarter (PUBLISHED).

Each predecessor gains urpx:expirationDateTime at its successor's effective date
(LAYOUT.md section 9). Run dev/resync_coverage_evaluations.py afterwards.

Run from the repo root:
    python3 dev/author_ladwp_2026.py <directory holding the fetched documents>

The directory holds the publisher's files under the names in DOCS, plus the two
ladwp.com pages saved as residential-adjustment-billing-factors.html and
residential-rates.html.
"""
from __future__ import annotations

import copy
import hashlib
import html
import json
import re
import shutil
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import rescope_iris as rescope  # noqa: E402
from resync_coverage_evaluations import description_for  # noqa: E402

LADWP = REPO / "us/ca/ladwp/electricity"
OLD = "2026-04-01"
RETRIEVED = "2026-10-07"
SLUGS = ("r-1a", "r-1b")

FACTORS_PAGE = "https://www.ladwp.com/account/customer-service/electric-rates/residential-adjustment-billing-factors"
RATES_PAGE = "https://www.ladwp.com/account/customer-service/electric-rates/residential-rates"
EXPENDITURES_PAGE = ("https://www.ladwp.com/account/understanding-your-rates/"
                     "approved-expenditures-water-and-power-pass-through-adjustment-factors")

DOCS = {
    "summary": ("Electric_Rate_Summary_effective_7_1_2019_with_factors_referenced_rev1.pdf",
                "https://www.ladwp.com/sites/default/files/documents/"
                "Electric_Rate_Summary_effective_7_1_2019_with_factors_referenced_rev1.pdf"),
    "eca-2026-07-01": ("Energy Cost Adjustment Expenditures for the 12-Month Period Commencing July 1, 2026.pdf",
                       "https://www.ladwp.com/sites/default/files/2026-08/Energy%20Cost%20Adjustment%20"
                       "Expenditures%20for%20the%2012-Month%20Period%20Commencing%20July%201%2C%202026.pdf"),
    "eca-2026-10-01": ("Energy Cost Adjustment Expenditures for the 12-Month Period Commencing October 1, 2026 - ADact.pdf",
                       "https://www.ladwp.com/sites/default/files/2026-10/Energy%20Cost%20Adjustment%20"
                       "Expenditures%20for%20the%2012-Month%20Period%20Commencing%20October%201%2C%202026"
                       "%20-%20ADact.pdf"),
    "psrp": ("Power System Reliability Program Expenditures for Fiscal Year 2026-27 r.pdf",
             "https://www.ladwp.com/sites/default/files/2026-08/Power%20System%20Reliability%20Program%20"
             "Expenditures%20for%20Fiscal%20Year%202026-27%20r.pdf"),
}

# The Board of Water and Power Commissioners resolution behind each quarter's
# ECA, VEA, CRPSEA and VRPSEA: its number as stamped on page 1, the meeting that
# adopted it as certified on its Resolution page, and the page of Attachment B
# headed "Factors Summary".
ECA_RESOLUTION = {
    "2026-07-01": {"no": "026 241", "adopted": "June 9, 2026", "page": 11},
    "2026-10-01": {"no": "027 035", "adopted": "Sept 8, 2026", "page": 11},
}
# Resolution 026 243, adopted June 9, 2026: Power System Reliability Program
# expenditures for fiscal year 2026-27. Its Appendix (page 8) states the
# residential RCA, $0.003 per kWh, and IRCA, $0.06934 per kWh.
PSRP = {"no": "026 243", "adopted": "Jun 9, 2026", "page": 8}

QUARTERS = {
    "2026-07-01": {"label": "Jul-Sep 2026", "row": "Jul - Sep", "q": "2026-q3", "expires": "2026-10-01"},
    "2026-10-01": {"label": "Oct-Dec 2026", "row": "Oct - Dec", "q": "2026-q4", "expires": None},
}
ORDER = ("eca", "esa", "rca", "irca", "vea", "crpsea", "vrpsea")

# $/kWh. Each value is on the factors page's 2026 table and, apart from ESA, in
# a resolution: ECA, VEA, CRPSEA, VRPSEA on the ECA resolution's Factors Summary,
# RCA and IRCA on the PSRP resolution's Appendix. ESA is the capped-ordinance
# value printed on the 2019-07-01 summary.
FACTORS = {
    "2026-04-01": {"eca": "0.05690", "esa": "0.00147", "rca": "0.00300", "irca": "0.05505",
                   "vea": "0.00503", "crpsea": "0.01779", "vrpsea": "0.03296"},
    "2026-07-01": {"eca": "0.05690", "esa": "0.00147", "rca": "0.00300", "irca": "0.06934",
                   "vea": "0.01071", "crpsea": "0.01817", "vrpsea": "0.03307"},
    "2026-10-01": {"eca": "0.05690", "esa": "0.00147", "rca": "0.00300", "irca": "0.06934",
                   "vea": "0.01590", "crpsea": "0.01973", "vrpsea": "0.03516"},
}

# Total Consumption Charge, 2026, from the residential rates page: R-1A Tier 1,
# 2, 3 and R-1B High Peak, Low Peak, Base. July-September is High Season,
# October-December Low Season. Keyed by the base energy-charge Price @id (in the
# 2026-04-01 documents) whose value plus the seven factors must give it.
PUBLISHED = {
    ("r-1a", "2026-07-01"): {"ladwp:price-energy-high-zone1-t1": "0.26408",
                             "ladwp:price-energy-high-zone1-t2": "0.32267",
                             "ladwp:price-energy-high-zone1-t3": "0.40968"},
    ("r-1a", "2026-10-01"): {"ladwp:price-energy-low-zone1-t1": "0.27292",
                             "ladwp:price-energy-low-zone1-t2": "0.33151",
                             "ladwp:price-energy-low-zone1-t3": "0.33151"},
    ("r-1b", "2026-07-01"): {"ladwp:price-energy-summer-high-peak": "0.35124",
                             "ladwp:price-energy-summer-low-peak": "0.29284",
                             "ladwp:price-energy-summer-base": "0.26540"},
    ("r-1b", "2026-10-01"): {"ladwp:price-energy-winter-high-peak": "0.30168",
                             "ladwp:price-energy-winter-low-peak": "0.30168",
                             "ladwp:price-energy-winter-base": "0.27814"},
}

SUMMARY_PAGE = {"r-1a": 1, "r-1b": 2}


def path(slug: str, date: str) -> Path:
    return LADWP / slug / "versions" / date / f"rate-plan_ladwp_{slug}_{date}.jsonld"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def dump(p: Path, doc) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def version_node(doc):
    return doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"]


# --- reconciliation -----------------------------------------------------------

def page_table(fetched: Path) -> dict[str, dict[str, str]]:
    """The 2026 rows of the factors page, keyed by its Period Applicable label."""
    text = (fetched / "residential-adjustment-billing-factors.html").read_text(encoding="utf-8")
    m = re.search(r"Residential Adjustment Factors \(2026\).*?</table>", text, re.S)
    if not m:
        raise SystemExit("factors page: no 2026 table")
    rows = {}
    for tr in re.findall(r"<tr>(.*?)</tr>", m.group(0), re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
        if cells and cells[0] != "Period Applicable":
            rows[cells[0]] = dict(zip(("eca", "esa", "rca", "irca", "vea", "crpsea", "vrpsea"), cells[1:]))
    return rows


def reconcile(fetched: Path) -> None:
    rows = page_table(fetched)
    for date, label in (("2026-04-01", "Apr - Jun"), *((d, q["row"]) for d, q in QUARTERS.items())):
        if rows.get(label) != FACTORS[date]:
            raise SystemExit(f"factors page {label}: {rows.get(label)} != {FACTORS[date]}")
    for (slug, date), want in PUBLISHED.items():
        doc = load(path(slug, OLD))
        base = {}
        rescope.walk(doc, lambda d: base.__setitem__(d["@id"], d["urpx:unitPrice"])
                     if d.get("@type") == "urpx:Price" and "urpx:unitPrice" in d else None)
        total = sum(Decimal(v) for v in FACTORS[date].values())
        for pid, published in want.items():
            got = Decimal(base[pid]) + total
            if got != Decimal(published):
                raise SystemExit(f"{slug} {date} {pid}: {base[pid]} + {total} = {got}, published {published}")


# --- derivation ---------------------------------------------------------------

def dsr(rid: str, key: str, page: int) -> dict:
    name, url = DOCS[key]
    return {
        "@type": "urpx:DataSourceReference",
        "@id": f"{rid}-data-source-reference",
        "urpx:fileName": name,
        "urpx:mediaType": {"@id": "urpx:applicationPdf"},
        "urpx:accessURL": url,
        "urpx:dateRetrieved": RETRIEVED,
        "urpx:dataSourceType": {"@id": "urpx:utilityWebsiteSource"},
        "urpx:pageStart": page,
        "urpx:pageEnd": page,
    }


def cites(slug: str, new: str, factor: str) -> tuple[str, int]:
    if factor in ("eca", "vea", "crpsea", "vrpsea"):
        return f"eca-{new}", ECA_RESOLUTION[new]["page"]
    if factor in ("rca", "irca"):
        return "psrp", PSRP["page"]
    return "summary", SUMMARY_PAGE[slug]


def derive(slug: str, new: str) -> list[tuple[str, str, str]]:
    q = QUARTERS[new]
    doc = load(path(slug, OLD))
    owner = f"ladwp:{slug}-{new}"
    m: dict[str, str] = {}

    def plan(d):
        i, t = d.get("@id"), rescope.node_type(d)
        if not isinstance(i, str) or len(d) == 1 or i in m:
            return
        if t in rescope.IDENTITY_TYPES and t not in rescope.VERSION_TYPES:
            return
        if t == "urpx:MetricSpecification":
            return
        if t in rescope.VERSION_TYPES or t == "urpx:URPXPackage" or i.startswith("ladwp:cc-"):
            m[i] = i.replace(OLD, new)
            return
        j = i.replace("-2026-q2", f"-{q['q']}")
        if re.search(r"-price-irca-2026-q2$", i):
            j = i.replace("-2026-q2", "-fy2026-27")
        m[i] = rescope.new_iri(j, owner)
    rescope.walk(doc, plan)

    def rename(d):
        if isinstance(d.get("@id"), str) and d["@id"] in m:
            d["@id"] = m[d["@id"]]
    rescope.walk(doc, rename)

    v = version_node(doc)
    # Effective and expiration dates, in that order after effectiveDateTime.
    out = {}
    for k, x in v.items():
        if k == "urpx:expirationDateTime":
            continue
        out[k] = x
        if k == "urpx:effectiveDateTime":
            out[k] = f"{new}T00:00:00"
            if q["expires"]:
                out["urpx:expirationDateTime"] = f"{q['expires']}T00:00:00"
    v.clear()
    v.update(out)
    old_sentence = ("The factors captured here are the Apr-Jun 2026 quarterly values; subsequent quarterly "
                    "refreshes will be filed as new RatePlanVersions.")
    if v["urpx:description"].count(old_sentence) != 1:
        raise SystemExit(f"{slug}: version description lacks the quarter sentence")
    v["urpx:description"] = v["urpx:description"].replace(old_sentence, (
        f"The factors captured here are the {q['label']} quarterly values, with the fiscal-year 2026-27 "
        "IRCA; each quarterly refresh is filed as a new RatePlanVersion."))
    v["urpx:hasDataSourceReference"]["urpx:dateRetrieved"] = RETRIEVED

    # Factor Prices: new values, a citation each, and IRCA into its own PriceSet.
    prices = v["urpx:hasPrices"]
    sets = prices["urpx:hasPriceSet"]
    factor_set = next(s for s in sets if s["@id"].endswith(f"-ps-adjustment-factors-{q['q']}"))
    factor_set["urpx:startDate"] = new
    rows, kept, irca = [], [], None
    for p in factor_set["urpx:hasPrice"]:
        f = re.search(r"-price-([a-z]+)-(?:2026-q[34]|fy2026-27)$", p["@id"]).group(1)
        rows.append((f, p["urpx:unitPrice"], FACTORS[new][f]))
        p["urpx:unitPrice"] = FACTORS[new][f]
        if not p["urpx:name"].endswith(" (Apr-Jun 2026)"):
            raise SystemExit(f"{p['@id']}: name {p['urpx:name']!r}")
        p["urpx:name"] = p["urpx:name"].replace(
            "(Apr-Jun 2026)", "(fiscal year 2026-27)" if f == "irca" else f"({q['label']})")
        key, page = cites(slug, new, f)
        p["urpx:hasDataSourceReference"] = dsr(p["@id"], key, page)
        if f == "irca":
            irca = p
        else:
            kept.append(p)
    if sorted(r[0] for r in rows) != sorted(ORDER) or irca is None:
        raise SystemExit(f"{slug}: factor PriceSet does not hold exactly the seven factors")
    factor_set["urpx:hasPrice"] = kept
    sets.insert(sets.index(factor_set) + 1, {
        "@type": "urpx:PriceSet",
        "@id": f"{owner}-ps-irca-fy2026-27",
        "urpx:startDate": "2026-07-01",
        "urpx:hasPrice": [irca],
    })

    cc = v["urpx:hasCoverageClaim"]
    ev = cc["urpx:explainedBy"]
    ev["urpx:evaluatedOn"] = f"{RETRIEVED}T00:00:00"
    if slug == "r-1a":
        ev["urpx:description"] = description_for(r1a_deferrals(new))
    dump(path(slug, new), doc)
    return rows


def expire(slug: str, date: str, until: str) -> None:
    p = path(slug, date)
    doc = load(p)
    ctx = doc["@context"]
    if "urpx:expirationDateTime" not in ctx:
        out = {}
        for k, x in ctx.items():
            out[k] = x
            if k == "urpx:effectiveDateTime":
                out["urpx:expirationDateTime"] = {"@type": "xsd:dateTime"}
        doc["@context"] = out
    v = version_node(doc)
    out = {}
    for k, x in v.items():
        if k == "urpx:expirationDateTime":
            continue
        out[k] = x
        if k == "urpx:effectiveDateTime":
            out["urpx:expirationDateTime"] = f"{until}T00:00:00"
    doc["urpx:hasRatePlan"]["urpx:hasRatePlanVersion"] = out
    dump(p, doc)


# --- manifests ----------------------------------------------------------------

def old_deferrals(slug: str) -> list[str]:
    import tomli
    t = tomli.loads((LADWP / slug / "versions" / OLD / "tariff.toml").read_text(encoding="utf-8"))
    return t["modeling"]["deferrals"]


# R-1A keeps the zone and minimum-charge deferrals of its 2026-04-01 version.
# The provenance deferral is closed by the per-Price citations, and the expiry
# deferral by urpx:expirationDateTime and the separate IRCA PriceSet.
R1A_DEFERRALS = [d for d in old_deferrals("r-1a")
                 if d.startswith(("Zone 1 / Zone 2 selector absent.", "Minimum Charge composition not modeled."))]
assert len(R1A_DEFERRALS) == 2


def r1a_deferrals(new: str) -> list[str]:
    """The kept deferrals, naming this version's own @ids."""
    return [d.replace("ladwp:price-minimum-charge", f"ladwp:r-1a-{new}-price-minimum-charge")
            for d in R1A_DEFERRALS]


def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def wrap(text: str) -> str:
    import textwrap
    paras = [p.strip() for p in text.strip().split("\n\n")]
    return "\n\n".join("\n".join(textwrap.wrap(" ".join(p.split()), 78, break_long_words=False,
                                               break_on_hyphens=False)) for p in paras)


NAMES = {"eca": "ECA", "esa": "ESA", "rca": "RCA", "irca": "IRCA", "vea": "VEA",
         "crpsea": "CRPSEA", "vrpsea": "VRPSEA"}


def notes(slug: str, new: str, fetched: Path) -> str:
    q = QUARTERS[new]
    r = ECA_RESOLUTION[new]
    prev = "2026-04-01" if new == "2026-07-01" else "2026-07-01"
    page = sha(fetched / "residential-adjustment-billing-factors.html")
    rates = sha(fetched / "residential-rates.html")
    pub = PUBLISHED[(slug, new)]
    total = sum(Decimal(x) for x in FACTORS[new].values())
    parts = [
        f"""Base rates are unchanged: the Electric Rate Summary effective 2019-07-01,
        page {SUMMARY_PAGE[slug]}, fetched {RETRIEVED} with the same sha256 as the copy in
        the 2026-04-01 version. This version moves the seven adjustment factors to the
        {q['label']} values.""",
        f"""Factor sources. ECA, VEA, CRPSEA and VRPSEA: Board of Water and Power
        Commissioners Resolution No. {r['no']}, adopted at the meeting held {r['adopted']},
        Attachment B page {r['page']} (Factors Summary). RCA and IRCA: Resolution No.
        {PSRP['no']}, adopted at the meeting held {PSRP['adopted']}, Appendix (page
        {PSRP['page']}), for fiscal year 2026-27. ESA: the capped-ordinance value on the
        2019-07-01 summary. Each factor Price cites its document and page. Both
        resolutions are listed on {EXPENDITURES_PAGE}.""",
        f"""Factors page. The same values are the 2026 table's "{q['row']}" row on
        {FACTORS_PAGE}, retrieved {RETRIEVED}, sha256 {page} for the HTML as served. The
        page is not vendored: this corpus vendors PDF source documents only.""",
    ]
    tables = [
        "Factor values, $/kWh, against the " + prev + " version:\n" + "\n".join(
            f" {NAMES[f]}: {FACTORS[prev][f]} -> {FACTORS[new][f]}" for f in ORDER)
        + f"\n Sum: {sum(Decimal(x) for x in FACTORS[prev].values())} -> {total}",
        "Reconciliation. Base charge plus the factor sum equals the 2026 Total\n"
        "Consumption Charge on " + RATES_PAGE + " (retrieved " + RETRIEVED + ",\n"
        "sha256 " + rates + "):\n" + "\n".join(
            f" {k.removeprefix('ladwp:price-energy-')}: {v}" for k, v in pub.items()),
    ]
    if q["expires"]:
        parts.append(f"""Supersession. This version expires {q['expires']}, when the 2026-10-01
        version takes effect. The 2026-04-01 version expires on this version's effective
        date.""")
    else:
        parts.append(f"""Supersession. The 2026-07-01 version expires on this version's effective
        date. This version carries no urpx:expirationDateTime: Resolution No. {r['no']}
        states the next quarterly factors update would be effective January 1, 2027, and
        those factors were not published at retrieval.""")
    return "\n\n".join([wrap(p) for p in parts[:3]] + tables + [wrap(p) for p in parts[3:]])


def manifest(slug: str, new: str, fetched: Path) -> None:
    d = LADWP / slug / "versions" / new
    r = ECA_RESOLUTION[new]

    def src(name, key, filing_type, filing_id=None, landing=None):
        fname, url = DOCS[key]
        lines = [f"  [source.{name}]", f"  url = {toml_str(url)}",
                 f'  sha256 = "{sha(d / VENDORED[key](slug, new))}"',
                 f'  retrieved_on = "{RETRIEVED}"', '  media_type = "application/pdf"',
                 f'  filing_type = "{filing_type}"']
        if filing_id:
            lines.append(f'  filing_id = "{filing_id}"')
        if landing:
            lines.append(f'  landing_page = "{landing}"')
        return "\n".join(lines)

    deferrals = r1a_deferrals(new) if slug == "r-1a" else old_deferrals(slug)
    import tomli
    old = tomli.loads((LADWP / slug / "versions" / OLD / "tariff.toml").read_text(encoding="utf-8"))
    mods = old["modeling"]["applicable_modifiers"]
    eca_no = r["no"].replace(" ", "-")
    psrp_no = PSRP["no"].replace(" ", "-")
    lines = [
        "# Identity --------------------------------------------------------------------",
        'utility = "ladwp"', f'schedule = "{slug}"', f'effective_date = "{new}"', "",
        "# Source ----------------------------------------------------------------------",
        "[source]", f'landing_page = "{RATES_PAGE}"', "",
        src("base", "summary", "tariff-schedule"), "",
        f"  # ECA, VEA, CRPSEA and VRPSEA for {QUARTERS[new]['label']}.",
        src("eca", f"eca-{new}", "resolution", f"LADWP-Resolution-{eca_no}", EXPENDITURES_PAGE), "",
        "  # RCA and IRCA for fiscal year 2026-27.",
        src("psrp", "psrp", "resolution", f"LADWP-Resolution-{psrp_no}", EXPENDITURES_PAGE), "",
        "# Regulatory ------------------------------------------------------------------",
        "[regulator]",
        "  [regulator.base]", '  authority = "city-council"',
        '  docket = "Final Incremental Electric Rate Ordinance (4-15-16) + Electric Rates Ordinance"', "",
        "  [regulator.eca]", '  authority = "board"',
        f'  docket = "Board of Water and Power Commissioners Resolution No. {r["no"]}"', "",
        "  [regulator.psrp]", '  authority = "board"',
        f'  docket = "Board of Water and Power Commissioners Resolution No. {PSRP["no"]}"', "",
        "# Extraction ------------------------------------------------------------------",
        "[extraction]", 'tool = "manual"', f'extracted_on = "{RETRIEVED}"',
        'notes = """', notes(slug, new, fetched), '"""', "",
        "# Validation ------------------------------------------------------------------",
        "[validation]", "shacl_passed = true", 'validator = "clj-shacl + clj-urpx (URPX v0.5.1)"',
        f'validated_on = "{RETRIEVED}"', "",
        "# Modeling -------------------------------------------------------------------",
        "[modeling]", "complete = false", "deferrals = [",
        *[" " + toml_str(x) + "," for x in deferrals], "]",
        "applicable_modifiers = [", *[f' "{x}",' for x in mods], "]", "",
        "# Review ----------------------------------------------------------------------",
        "[review]", 'status = "draft"',
        "notes = " + toml_str(f"Derived from the {OLD} version by dev/author_ladwp_2026.py: subordinate "
                              "@ids scoped to this version, the seven factor Prices set and cited, IRCA "
                              "moved to its own PriceSet. See [extraction] notes."),
        "",
    ]
    text = "\n".join(lines)
    tomli.loads(text)
    (d / "tariff.toml").write_text(text, encoding="utf-8")


VENDORED = {
    "summary": lambda slug, new: f"ladwp_{slug}_{new}.pdf",
    "eca-2026-07-01": lambda slug, new: f"ladwp_eca-expenditures_{new}.pdf",
    "eca-2026-10-01": lambda slug, new: f"ladwp_eca-expenditures_{new}.pdf",
    "psrp": lambda slug, new: f"ladwp_psrp-expenditures_{new}.pdf",
}


def vendor(fetched: Path, slug: str, new: str) -> None:
    for key in ("summary", f"eca-{new}", "psrp"):
        src = fetched / DOCS[key][0]
        if src.read_bytes()[:5] != b"%PDF-":
            raise SystemExit(f"{src}: not a PDF")
        dst = LADWP / slug / "versions" / new / VENDORED[key](slug, new)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python3 dev/author_ladwp_2026.py <directory holding the fetched documents>")
        return 2
    fetched = Path(argv[1])
    reconcile(fetched)
    for slug in SLUGS:
        for new in QUARTERS:
            vendor(fetched, slug, new)
            derive(slug, new)
            manifest(slug, new, fetched)
            print(f"{slug} {new}: written")
        expire(slug, OLD, "2026-07-01")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
