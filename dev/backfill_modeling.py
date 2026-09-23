#!/usr/bin/env python3
"""Regenerate the derived half of each tariff.toml [modeling] block.

WHAT THIS WRITES, and what it must never write again.

`applicable_modifiers` is DERIVED: a reverse map over every modifier filing's
urpx:applicableToRatePlan, augmented with modifiers the source PDFs name but the
corpus has not yet modeled. That is tabulation, it is recomputable from the
corpus, and regenerating it is this script's job.

`complete` and `deferrals` are a JUDGMENT: they answer whether the JSON-LD
captures what its source PDF prices, which can only be settled by reading both.
LAYOUT.md 4.4 defines the block and the add-a-filing workflow at step 7 puts that
call on whoever models the filing, recorded in tariff.toml. This script used to
stamp them from the DEFERRALS table below, a one-time inventory lifted from
rdfs:comment prose when the convention was introduced. Wired into
dev/check_all.py, it then rewrote 45 of the 72 manifests on every full gate,
silently reverting any assessment authored after that table was frozen. That is
how the manifests went stale while the models moved on: between the v0.2.1 and
v0.5.1 migrations, filings gained vocabulary that closed their deferrals and the
table did not know. So `complete` and `deferrals` are now PRESERVED from the
manifest, and the table is kept only as the historical record of what was
deferred at bootstrap.

The agreement between the manifest, the filing's urpx:CoverageClaim and the
filing itself is enforced by dev/lint_completeness_agreement.py, which reports a
disagreement rather than overwriting one side of it.

Run from repo root:  python3 dev/backfill_modeling.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus

REPO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Per-filing within-filing-axis data.
# Key: (utility, schedule, effective_date)
# deferrals: empty list iff the filing's source PDF(s) are fully captured in
#            JSON-LD; otherwise a structured list of deferred items lifted
#            from rdfs:comment prose.
# ---------------------------------------------------------------------------
DEFERRALS: dict[tuple[str, str, str], list[str]] = {
    # PG&E
    ("pge",   "e-1",             "2026-03-01"): [],
    ("pge",   "e-tou-c",         "2026-03-01"): [
        # base is complete; sibling modifier (baseline-tier) has a deferral
        "Code M / Code S medical baseline allowances per Rule 19 + Preliminary Statement Part A (in the sibling baseline-tier modifier)",
    ],
    ("pge",   "e-tou-c",         "2026-03-27"): [],
    ("pge",   "e-tou-d",         "2026-03-27"): [],
    ("pge",   "ev2",             "2026-03-27"): [],
    ("pge",   "e-elec",          "2026-01-01"): [],
    ("pge",   "e-elec",          "2026-03-27"): [],
    # SCE
    ("sce",   "d",               "2025-11-15"): [],
    # Sheets 8-9 of the live tariff book carry Special Conditions 8 and 9, which
    # the 2025-11-15 rate-table archive does not have at all. Both grant a
    # percentage bill discount and neither is in the graph, so this filing is
    # partial and was recorded as complete with no evaluation until 2026-09-21.
    ("sce",   "d",               "2026-03-20"): [
        "SJV Pilot Bill Protection Discount (Sheet 8, Special Condition 8): 20 percent in pilot years 1 through 5 and 10 or 20 percent in years 6 through 10; not modeled, because the filing carries no condition on SJV Pilot participation to gate a price on",
        "Transitional Community Solar Discount (Sheet 9, Special Condition 9): 20 percent monthly bill credit over the same 10-year bill protection period; same pilot-participation gate",
        "California Climate Credit carry-forward (Sheet 7, Special Condition 5): the $(36.00) credit is priced, but the roll-over of any portion not consumed in a billing period to subsequent periods is not expressed",
    ],
    ("sce",   "tou-d-4-9pm",     "2025-11-15"): [
        "Heat Pump Water Heater (HPWH) baseline allocation per Preliminary Statement Part H — baseline credit modifier not yet captured",
            "SCE's Sunday-to-Monday holiday observance rule (Sheet 13) matches no urpx:ObservanceRuleValue in URPX v0.5.1, so each holiday resolves on its actual date; the Monday after an Independence Day falling on a Sunday prices On-Peak rather than the Mid-Peak Sheet 12 directs",
    ],
    ("sce",   "tou-d-5-8pm",     "2025-11-15"): [
        "Heat Pump Water Heater (HPWH) baseline allocation per Preliminary Statement Part H — baseline credit modifier not yet captured",
            "SCE's Sunday-to-Monday holiday observance rule (Sheet 13) matches no urpx:ObservanceRuleValue in URPX v0.5.1, so each holiday resolves on its actual date; the Monday after an Independence Day falling on a Sunday prices On-Peak rather than the Mid-Peak Sheet 12 directs",
    ],
    ("sce",   "tou-d-prime",     "2025-11-15"): [
        "100% Medical Line Item Discount RatePlanModifier",
        "Closed-schedule grandfather paths (TOU-D-A, TOU-D-B, TOU-D-T enrollees) beyond the four primary OR-paths",
            "SCE's Sunday-to-Monday holiday observance rule (Sheet 13) matches no urpx:ObservanceRuleValue in URPX v0.5.1, so each holiday resolves on its actual date; the Monday after an Independence Day falling on a Sunday prices On-Peak rather than the Mid-Peak Sheet 12 directs",
    ],
    ("sce",   "care",            "2025-11-15"): [
        "CARE-customer exemption from a non-CARE-funded surcharge — not modeled until base rate plans track this surcharge as a non-CARE-only line item",
    ],
    # The 18% bill discount used to sit here as a deferral claiming URPX had no
    # percentage-of-bill primitive. It is modeled: urpx:multiplier -0.18 over a
    # urpx:PriceSummary. A deferral entry means a part deliberately NOT modeled,
    # so the right correction is removal, not rewording.
    ("sce",   "fera",            "2025-11-15"): [],
    ("sce",   "deed-restricted", "2025-11-15"): [],
    # SDG&E
    ("sdge",  "dr",              "2026-04-01"): [
        "PCIA modeling per Special Condition 11 (CCA-served customers)",
    ],
    ("sdge",  "tou-dr1",         "2026-04-01"): [
        "PCIA modeling per Special Condition 16 (CCA-served customers)",
        "0.78% City of San Diego corporate-limits surcharge",
    ],
    ("sdge",  "tou-dr2",         "2026-04-01"): [],
    ("sdge",  "tou-elec",        "2026-04-01"): [],
    ("sdge",  "ev-tou-5",        "2026-04-01"): [],
    ("sdge",  "dr-ses",          "2026-04-01"): [],
    # CPAU
    ("cpau",  "e-1",             "2025-07-01"): [],
    ("cpau",  "e-1-tou",         "2026-01-01"): [],
    ("cpau",  "e-2",             "2025-07-01"): [],
    ("cpau",  "e-3",             "2007-07-01"): [
        "Section C interval-meter TOU buyback (range pricing — open URPX vocabulary question)",
    ],
    ("cpau",  "e-4",             "2025-07-01"): [
        "Section D — not modeled in v1",
    ],
    ("cpau",  "e-4-tou",         "2025-07-01"): [
        "Section D — not modeled in v1",
    ],
    ("cpau",  "e-7",             "2025-07-01"): [
        "Section D — not modeled in v1",
        "C.3 site-aggregation (multi-account contiguous-parcel billing) — URPX has no native vocabulary for site-level aggregation",
    ],
    ("cpau",  "e-7-tou",         "2025-07-01"): [
        "Section D — not modeled in v1",
    ],
    ("cpau",  "e-14",            "2025-07-01"): [
        "Interim-rate provision for lamps not on the schedule (prose-only in source)",
    ],
    ("cpau",  "e-16",            "2025-09-01"): [
        "Section E miscellaneous rates (license fees: conduit usage, utility pole attachments, communication-equipment mounting; CPI-indexed annually per Section F)",
    ],
    ("cpau",  "e-2-g",           "2025-07-01"): [
        "Per-block discrete-purchase variant ($X/block) — different metric shape from continuous per-kWh",
    ],
    ("cpau",  "e-4-g",           "2025-07-01"): [
        "Per-block discrete-purchase variant ($X/block) — different metric shape from continuous per-kWh",
    ],
    ("cpau",  "e-7-g",           "2025-07-01"): [
        "Per-block discrete-purchase variant ($X/block) — different metric shape from continuous per-kWh",
    ],
    ("cpau",  "e-eec-1",         "2025-09-01"): [],
    ("cpau",  "e-nse-1",         "2025-09-01"): [],
    ("cpau",  "e-hra",           "2023-01-01"): [],
    # SMUD
    ("smud",  "fixed",           "2026-01-01"): [
        "Plug-In EV Credit modifier",
        "EAPR / Medical Equipment overlays",
        "NEM1 / SSR / Standby / Three-Phase / Renewable-Energy options",
    ],
    ("smud",  "tod-5-8pm",       "2026-01-01"): [
        "Hydro Generation Adjustment (HGA)",
        "Standby Service Charge",
        "Three-Phase Service fee",
        "SMUD Renewable Energy Option",
    ],
    ("smud",  "nem1",            "2021-09-17"): [
        "Annual net-surplus monetary payment (published-annually scalar)",
    ],
    ("smud",  "ssr",             "2022-03-01"): [],
    ("smud",  "pev-credit",      "2025-06-20"): [],
    # LADWP
    ("ladwp", "r-1a",            "2026-04-01"): [],
    ("ladwp", "r-1b",            "2026-04-01"): [
        "$0.025/kWh EV-conditional rate — separate RatePlanModifier",
    ],
    ("ladwp", "nem",             "2008-09-01"): [
        "Service Rider REO (Green Power) — separate modifier",
    ],
}

# Additional applicable_modifiers per base, beyond what corpus-reverse-mapping
# yields. Drawn from prose deferrals that explicitly name a modifier the
# source PDF references but the corpus has not yet modeled.
ADDITIONAL_APPLICABLE: dict[tuple[str, str], list[str]] = {
    # SCE: HPWH baseline credit + Medical Line Item Discount mentioned in
    # tou-d-* prose; CARE/FERA exemption from non-CARE surcharge (cross-cutting)
    ("sce",   "tou-d-4-9pm"):     ["hpwh-baseline"],
    ("sce",   "tou-d-5-8pm"):     ["hpwh-baseline"],
    ("sce",   "tou-d-prime"):     ["medical-line-item-discount"],
    # SDG&E: CARE/FERA/DRAH explicitly referenced in dr/tou-dr1 prose as
    # "modeled as RatePlanModifiers in grid-coordination/urpx-rate-plans#13"
    ("sdge",  "dr"):              ["care", "fera", "drah"],
    ("sdge",  "tou-dr1"):         ["care", "fera", "drah"],
    ("sdge",  "tou-dr2"):         ["care", "fera", "drah"],
    ("sdge",  "tou-elec"):        ["care", "fera", "drah"],
    ("sdge",  "ev-tou-5"):        ["care", "fera", "drah"],
    ("sdge",  "dr-ses"):          ["care", "fera", "drah"],
    # PG&E: medical baseline (Code M / Code S) referenced in baseline-tier
    # modifier prose; CARE/FERA standard PG&E residential overlays
    ("pge",   "e-1"):             ["care", "fera", "medical-baseline"],
    ("pge",   "e-tou-c"):         ["care", "fera", "medical-baseline"],
    ("pge",   "e-tou-d"):         ["care", "fera", "medical-baseline"],
    ("pge",   "ev2"):             ["care", "fera", "medical-baseline"],
    ("pge",   "e-elec"):          ["care", "fera", "medical-baseline"],
    # SMUD: plug-in EV, EAPR, NEM1, SSR, Three-Phase, REO, HGA, Standby
    # mentioned across fixed/tod-5-8pm prose. pev-credit/nem1/ssr already
    # in corpus; the rest are deferred.
    ("smud",  "fixed"):           ["eapr", "standby", "three-phase", "reo", "hga"],
    ("smud",  "tod-5-8pm"):       ["eapr", "standby", "three-phase", "reo", "hga"],
    # LADWP r-1a/r-1b: NEM in corpus; r-1b prose references EV rate as separate modifier
    ("ladwp", "r-1b"):            ["ev-discount"],
}


# ---------------------------------------------------------------------------
# Corpus walk
# ---------------------------------------------------------------------------

def find_filings() -> list[tuple[str, str, str, Path]]:
    """Return (utility, schedule, date, dir_path) for every tariff.toml directory."""
    out = []
    for tp in corpus.tariff_tomls():
        # Anchored on the `versions` segment; these indices were written
        # against the pre-`us/` layout and read schedule="electricity" and
        # date="versions" for every filing, so every lookup missed and the
        # generator skipped the whole corpus while exiting 0.
        utility, schedule, date = corpus.parse_filing_path(tp)
        out.append((utility, schedule, date, tp.parent))
    # See coverage.py: a generator matching nothing must refuse rather than
    # skip the corpus and exit 0, which is what this did for months.
    corpus.require_nonempty(out, "filings (backfill discovery)")
    return out


def reverse_modifier_map() -> dict[tuple[str, str], list[str]]:
    """For each (utility, base-schedule), return list of in-corpus modifier slugs.

    Slug is the local name portion of the modifier's IRI (strips the utility
    prefix). Covers both dedicated `rate-plan-modifier_*.jsonld` filings and
    inline modifiers packaged inside a base's @graph (e.g. PG&E vintage-PCIA,
    e-tou-c-baseline-tier).
    """
    # Reuse the same walker that powers the pairings export.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from list_modifier_base_pairings import collect as collect_pairings  # noqa: E402

    by_modifier, _ = collect_pairings()
    rev: dict[tuple[str, str], set[str]] = defaultdict(set)
    for mod_iri, info in by_modifier.items():
        if ":" not in mod_iri:
            continue
        mod_utility, mod_slug = mod_iri.split(":", 1)
        for base_iri in info.get("applicable_to", []):
            if ":" not in base_iri:
                continue
            base_utility, base_slug = base_iri.split(":", 1)
            # Only attach if the modifier and the base share a utility — this
            # is the same-utility lookup the lint uses.
            if mod_utility == base_utility:
                rev[(base_utility, base_slug)].add(mod_slug)
    return {k: sorted(v) for k, v in rev.items()}


# ---------------------------------------------------------------------------
# TOML formatting
# ---------------------------------------------------------------------------

def read_authored_modeling(toml_path: Path) -> tuple[bool, list[str]] | None:
    """The modeler's own complete/deferrals, or None if the block does not exist yet.

    Parsed rather than regex-scraped so a malformed block raises here instead of
    being silently replaced by the bootstrap table's answer.
    """
    if not toml_path.exists():
        return None
    block = corpus.load_toml(toml_path).get("modeling")
    if block is None or "complete" not in block:
        return None
    return bool(block["complete"]), list(block.get("deferrals") or [])


def render_modeling_block(
    *,
    complete: bool,
    deferrals: list[str],
    applicable_modifiers: list[str] | None,
) -> str:
    """Render a [modeling] TOML block. applicable_modifiers=None means omit (modifier filings)."""
    lines = ["# Modeling -------------------------------------------------------------------",
             "[modeling]",
             f"complete = {'true' if complete else 'false'}"]

    if not deferrals:
        lines.append("deferrals = []")
    else:
        lines.append("deferrals = [")
        for d in deferrals:
            esc = d.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f' "{esc}",')
        lines.append("]")

    if applicable_modifiers is not None:
        if not applicable_modifiers:
            lines.append("applicable_modifiers = []")
        else:
            lines.append("applicable_modifiers = [")
            for m in applicable_modifiers:
                lines.append(f' "{m}",')
            lines.append("]")

    return "\n".join(lines) + "\n"


_MODELING_BLOCK_RE = re.compile(
    r"\n*# Modeling[^\n]*\n\[modeling\][\s\S]*?(?=\n# [A-Z]|\n\[[a-z]|\Z)",
    re.MULTILINE,
)


def upsert_modeling_block(toml_text: str, block: str) -> str:
    """Insert (or replace) the [modeling] block, placed before [review] if present."""
    # Remove any existing [modeling] block
    cleaned = _MODELING_BLOCK_RE.sub("", toml_text)

    # Place the new block before [review], or at end if no [review]
    review_marker = re.search(r"\n# Review[^\n]*\n\[review\]", cleaned)
    if review_marker:
        idx = review_marker.start()
        return cleaned[:idx].rstrip() + "\n\n" + block + "\n" + cleaned[idx:].lstrip("\n")
    else:
        return cleaned.rstrip() + "\n\n" + block


def is_base_rate_plan_dir(dir_path: Path) -> bool:
    """A directory is a base RatePlan filing iff it contains a rate-plan_*.jsonld."""
    return any(dir_path.glob("rate-plan_*.jsonld"))


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> int:
    rev = reverse_modifier_map()
    filings = find_filings()

    written = 0
    skipped = 0
    for utility, schedule, date, dir_path in filings:
        key = (utility, schedule, date)
        if key not in DEFERRALS:
            print(f"SKIP (no deferral data): {dir_path.relative_to(REPO)}")
            skipped += 1
            continue

        # complete/deferrals are the modeler's call, read back from the manifest
        # and written out unchanged. DEFERRALS is consulted only to decide
        # whether this filing predates the convention and has no block yet.
        authored = read_authored_modeling(dir_path / "tariff.toml")
        if authored is None:
            deferrals = DEFERRALS[key]
            complete = not deferrals
            print(f"  seeding [modeling] from the bootstrap table: {dir_path.relative_to(REPO)}")
        else:
            complete, deferrals = authored

        # applicable_modifiers only on base RatePlan filings
        applicable: list[str] | None
        if is_base_rate_plan_dir(dir_path):
            corpus_mods = list(rev.get((utility, schedule), []))
            extra = ADDITIONAL_APPLICABLE.get((utility, schedule), [])
            applicable = sorted(set(corpus_mods + extra))
        else:
            applicable = None

        block = render_modeling_block(
            complete=complete,
            deferrals=deferrals,
            applicable_modifiers=applicable,
        )

        toml_path = dir_path / "tariff.toml"
        original = toml_path.read_text()
        updated = upsert_modeling_block(original, block)
        if original != updated:
            toml_path.write_text(updated)
            written += 1
            print(f"WROTE: {toml_path.relative_to(REPO)}")
        else:
            print(f"unchanged: {toml_path.relative_to(REPO)}")

    print(f"\n{written} written, {skipped} skipped, {len(filings)} total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
