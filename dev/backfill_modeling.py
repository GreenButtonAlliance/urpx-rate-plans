#!/usr/bin/env python3
"""Backfill [modeling] blocks into every tariff.toml in the corpus.

Within-filing axis (`complete` + `deferrals`) is derived from a per-filing
deferral inventory hand-curated below from a prose scan of the JSON-LD.

Corpus-coverage axis (`applicable_modifiers`, base RatePlan filings only) is
bootstrapped from the existing modifier filings' urpx:applicableToRatePlan
reverse mapping, augmented with prose-mentioned but not-yet-modeled modifiers.

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
    ("sce",   "tou-d-4-9pm",     "2025-11-15"): [
        "Heat Pump Water Heater (HPWH) baseline allocation per Preliminary Statement Part H — baseline credit modifier not yet captured",
    ],
    ("sce",   "tou-d-5-8pm",     "2025-11-15"): [
        "Heat Pump Water Heater (HPWH) baseline allocation per Preliminary Statement Part H — baseline credit modifier not yet captured",
    ],
    ("sce",   "tou-d-prime",     "2025-11-15"): [
        "100% Medical Line Item Discount RatePlanModifier",
        "Closed-schedule grandfather paths (TOU-D-A, TOU-D-B, TOU-D-T enrollees) beyond the four primary OR-paths",
    ],
    ("sce",   "care",            "2025-11-15"): [
        "CARE-customer exemption from a non-CARE-funded surcharge — not modeled until base rate plans track this surcharge as a non-CARE-only line item",
    ],
    ("sce",   "fera",            "2025-11-15"): [
        "20% bill discount on the pre-tax subtotal — URPX has no percentage-of-bill primitive (same upstream-vocabulary gap as the CARE modifier)",
    ],
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
    ("cpau",  "e-1",             "2025-09-01"): [],
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
        # ca/<class>/<utility>/<schedule>/versions/<date>/tariff.toml
        parts = tp.relative_to(REPO).parts
        utility = parts[2]
        schedule = parts[3]
        date = parts[5]
        out.append((utility, schedule, date, tp.parent))
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

def render_modeling_block(
    *,
    complete: bool,
    deferrals: list[str],
    applicable_modifiers: list[str] | None,
) -> str:
    """Render a [modeling] TOML block. applicable_modifiers=None means omit (modifier filings)."""
    lines = ["# Modeling -------------------------------------------------------------------",
             "[modeling]",
             f"complete  = {'true' if complete else 'false'}"]

    if not deferrals:
        lines.append("deferrals = []")
    else:
        lines.append("deferrals = [")
        for d in deferrals:
            esc = d.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'  "{esc}",')
        lines.append("]")

    if applicable_modifiers is not None:
        if not applicable_modifiers:
            lines.append("applicable_modifiers = []")
        else:
            lines.append("applicable_modifiers = [")
            for m in applicable_modifiers:
                lines.append(f'  "{m}",')
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

        deferrals = DEFERRALS[key]
        complete = not deferrals

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
