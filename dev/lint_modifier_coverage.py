#!/usr/bin/env python3
"""Modifier-coverage lint.

For each base RatePlan filing in the corpus, cross-reference its
`[modeling].applicable_modifiers` against the actual RatePlanModifier filings
under the same utility. Emits `reports/modifier-coverage.md`.

Each (base, applicable_modifier) pair lands in one of four buckets:

  - present-and-complete: a matching modifier filing exists and its own
    [modeling].complete is true.
  - present-but-incomplete: a matching modifier filing exists but has
    deferrals (its [modeling].complete is false).
  - missing: no matching modifier filing exists in the corpus.
  - error: matching modifier filing has no [modeling] block.

Two matching strategies are tried, in order:

  (1) Directory match — `ca/<class>/<utility>/<slug>/versions/.../`
      catches the common case (`care`, `fera`, `e-eec-1`, etc.).
  (2) IRI-suffix match — fall back to scanning all rate-plan-modifier
      filings under the utility and matching the local IRI name
      (e.g. `pge:e-tou-c-baseline-tier` matches slug
      `e-tou-c-baseline-tier` even though the filing lives inside
      `iou/pge/e-tou-c/versions/...`).

Run from repo root:  python3 dev/lint_modifier_coverage.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import tomli

REPO = Path(__file__).resolve().parent.parent

# Reuse the JSON-LD walker from the pairings export.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from list_modifier_base_pairings import collect as collect_pairings  # noqa: E402

# ---------------------------------------------------------------------------
# Corpus walk
# ---------------------------------------------------------------------------

def is_base_rate_plan_dir(d: Path) -> bool:
    return any(d.glob("rate-plan_*.jsonld"))


def is_modifier_dir(d: Path) -> bool:
    return any(d.glob("rate-plan-modifier_*.jsonld"))


def load_modeling(toml_path: Path) -> dict | None:
    with toml_path.open("rb") as fp:
        return tomli.load(fp).get("modeling")


def extract_modifier_iri_suffixes(jsonld_path: Path) -> list[str]:
    """Return the local-name part of every RatePlanModifier IRI in a modifier file."""
    with jsonld_path.open() as fp:
        data = json.load(fp)
    out: list[str] = []

    def walk(o):
        if isinstance(o, dict):
            t = o.get("@type")
            iri = o.get("@id")
            if iri and t and (
                (isinstance(t, str) and t == "urpx:RatePlanModifier")
                or (isinstance(t, list) and "urpx:RatePlanModifier" in t)
            ):
                if ":" in iri:
                    out.append(iri.split(":", 1)[1])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(data)
    return out


def build_modifier_index() -> dict[tuple[str, str], dict]:
    """{(utility, slug) -> {dir, complete, deferrals, source}} for every modifier in corpus.

    `source` is "directory" if the slug came from a top-level modifier directory name,
    or "iri" if matched only via in-graph IRI scan (inline-packaged modifier).
    """
    idx: dict[tuple[str, str], dict] = {}
    # Directory-name matches first (preferred)
    for d in REPO.glob("ca/*/*/*/versions/*"):
        if not is_modifier_dir(d):
            continue
        utility = d.relative_to(REPO).parts[2]
        slug = d.relative_to(REPO).parts[3]
        modeling = load_modeling(d / "tariff.toml") or {}
        idx[(utility, slug)] = {
            "dir": str(d.relative_to(REPO)),
            "complete": modeling.get("complete"),
            "deferrals": modeling.get("deferrals", []),
            "source": "directory",
        }
    # IRI-scan fallback for inline modifiers in base directories
    for jp in REPO.glob("ca/*/*/*/versions/*/rate-plan-modifier_*.jsonld"):
        utility = jp.relative_to(REPO).parts[2]
        d = jp.parent
        modeling = load_modeling(d / "tariff.toml") or {}
        for slug in extract_modifier_iri_suffixes(jp):
            key = (utility, slug)
            if key in idx:
                continue  # directory match already wins
            idx[key] = {
                "dir": str(d.relative_to(REPO)),
                "complete": modeling.get("complete"),
                "deferrals": modeling.get("deferrals", []),
                "source": "iri",
            }
    return idx


# ---------------------------------------------------------------------------
# Status classification
# ---------------------------------------------------------------------------

STATUS_PRESENT_COMPLETE = "present-complete"
STATUS_PRESENT_INCOMPLETE = "present-incomplete"
STATUS_MISSING = "missing"
STATUS_NO_MODELING_BLOCK = "no-modeling-block"

STATUS_GLYPH = {
    STATUS_PRESENT_COMPLETE: "✓",
    STATUS_PRESENT_INCOMPLETE: "~",
    STATUS_MISSING: "✗",
    STATUS_NO_MODELING_BLOCK: "?",
}


def classify(slug: str, utility: str, idx: dict[tuple[str, str], dict]) -> tuple[str, dict | None]:
    entry = idx.get((utility, slug))
    if entry is None:
        return STATUS_MISSING, None
    if entry["complete"] is None:
        return STATUS_NO_MODELING_BLOCK, entry
    return (STATUS_PRESENT_COMPLETE if entry["complete"] else STATUS_PRESENT_INCOMPLETE), entry


# ---------------------------------------------------------------------------
# Asymmetry detection
# ---------------------------------------------------------------------------

ASYMMETRY_MOD_CLAIMS = "modifier-claims-base-not-listed"
ASYMMETRY_BASE_LISTS = "base-lists-modifier-not-claimed"


def find_asymmetries(bases: list[dict], by_modifier: dict[str, dict]) -> list[dict]:
    """Cross-check the two declarations of base ↔ modifier pairing.

    Direction A — `modifier-claims-base-not-listed`:
      a modifier's urpx:applicableToRatePlan declares it applies to a base,
      but the base's [modeling].applicable_modifiers doesn't list the
      modifier's slug.

    Direction B — `base-lists-modifier-not-claimed`:
      a base's [modeling].applicable_modifiers references a slug that
      resolves to an existing modifier in the corpus, but the modifier's
      urpx:applicableToRatePlan doesn't include this base's IRI.

    Pairings where the modifier doesn't exist in the corpus at all are
    `STATUS_MISSING` (already surfaced in the per-base detail table) — not
    an asymmetry.
    """
    out: list[dict] = []

    # base IRI ("sce:d") → list of (per-version) base records
    by_base_iri: dict[str, list[dict]] = defaultdict(list)
    for b in bases:
        by_base_iri[f"{b['utility']}:{b['schedule']}"].append(b)

    # Direction A
    for mod_iri, info in sorted(by_modifier.items()):
        if ":" not in mod_iri:
            continue
        _, slug = mod_iri.split(":", 1)
        for base_iri in info.get("applicable_to", []):
            for b in by_base_iri.get(base_iri, []):
                if slug not in (b.get("applicable_modifiers") or []):
                    out.append({
                        "kind": ASYMMETRY_MOD_CLAIMS,
                        "modifier_iri": mod_iri,
                        "modifier_slug": slug,
                        "modifier_filing": info.get("filing"),
                        "base_iri": base_iri,
                        "base_dir": b["dir"],
                    })

    # Direction B
    for b in bases:
        base_iri = f"{b['utility']}:{b['schedule']}"
        for slug in (b.get("applicable_modifiers") or []):
            mod_iri = f"{b['utility']}:{slug}"
            mod_info = by_modifier.get(mod_iri)
            if mod_info is None:
                continue  # missing — reported elsewhere
            if base_iri not in mod_info.get("applicable_to", []):
                out.append({
                    "kind": ASYMMETRY_BASE_LISTS,
                    "modifier_iri": mod_iri,
                    "modifier_slug": slug,
                    "modifier_filing": mod_info.get("filing"),
                    "base_iri": base_iri,
                    "base_dir": b["dir"],
                })

    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def collect_bases() -> list[dict]:
    """One record per (utility, schedule, version-date) base RatePlan filing."""
    out = []
    for d in sorted(REPO.glob("ca/*/*/*/versions/*")):
        if not is_base_rate_plan_dir(d):
            continue
        parts = d.relative_to(REPO).parts
        utility = parts[2]
        schedule = parts[3]
        date = parts[5]
        modeling = load_modeling(d / "tariff.toml") or {}
        out.append({
            "utility": utility,
            "schedule": schedule,
            "date": date,
            "dir": str(d.relative_to(REPO)),
            "complete": modeling.get("complete"),
            "deferrals": modeling.get("deferrals", []),
            "applicable_modifiers": modeling.get("applicable_modifiers", []),
        })
    return out


def render_markdown(bases: list[dict], idx: dict, asymmetries: list[dict]) -> str:
    lines: list[str] = []
    lines.append("# Modifier-coverage report")
    lines.append("")
    lines.append("Generated by `dev/lint_modifier_coverage.py`. Do not edit by hand.")
    lines.append("")
    lines.append("For each base RatePlan filing, cross-references `[modeling].applicable_modifiers` "
                 "against the actual RatePlanModifier filings in the corpus.")
    lines.append("")
    lines.append("Status glyphs:")
    lines.append("")
    lines.append("- `✓` present and `[modeling].complete = true`")
    lines.append("- `~` present but `[modeling].complete = false` (has deferrals)")
    lines.append("- `✗` not modeled — no matching filing in the corpus")
    lines.append("- `?` filing exists but has no `[modeling]` block (lint cannot judge completeness)")
    lines.append("")

    # Aggregate stats
    counts: dict[str, int] = defaultdict(int)
    bases_fully_covered = 0
    for b in bases:
        all_complete = bool(b["applicable_modifiers"]) and b["complete"]
        for slug in b["applicable_modifiers"]:
            status, _ = classify(slug, b["utility"], idx)
            counts[status] += 1
            if status != STATUS_PRESENT_COMPLETE:
                all_complete = False
        if all_complete:
            bases_fully_covered += 1

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Base RatePlan filings: **{len(bases)}**")
    lines.append(f"- Fully covered (base complete + every applicable modifier present-and-complete): **{bases_fully_covered}**")
    lines.append(f"- Applicable-modifier slots across all bases: **{sum(counts.values())}**")
    lines.append(f"  - present and complete: {counts[STATUS_PRESENT_COMPLETE]}")
    lines.append(f"  - present but incomplete: {counts[STATUS_PRESENT_INCOMPLETE]}")
    lines.append(f"  - missing: {counts[STATUS_MISSING]}")
    if counts[STATUS_NO_MODELING_BLOCK]:
        lines.append(f"  - no [modeling] block: {counts[STATUS_NO_MODELING_BLOCK]}")
    lines.append(f"- Asymmetries between modifier-side and base-side declarations: **{len(asymmetries)}**")
    lines.append("")

    # Asymmetries
    lines.append("## Asymmetries")
    lines.append("")
    lines.append(
        "Cross-checks the two declarations of base ↔ modifier pairing: "
        "`urpx:applicableToRatePlan` on each `RatePlanModifierVersion` (modifier side) "
        "and `[modeling].applicable_modifiers` in each base's `tariff.toml` (base side). "
        "These should agree."
    )
    lines.append("")
    if not asymmetries:
        lines.append("_None — both declarations agree across the corpus._")
        lines.append("")
    else:
        mod_claims = [a for a in asymmetries if a["kind"] == ASYMMETRY_MOD_CLAIMS]
        base_lists = [a for a in asymmetries if a["kind"] == ASYMMETRY_BASE_LISTS]
        if mod_claims:
            lines.append("### Modifier claims base, but base doesn't list modifier")
            lines.append("")
            lines.append(
                "Modifier's `applicableToRatePlan` declares it applies to this base, "
                "but the base's `[modeling].applicable_modifiers` doesn't include the "
                "modifier's slug. Likely fix: add the slug to the base's "
                "`applicable_modifiers` array."
            )
            lines.append("")
            lines.append("| Modifier | Missing from base |")
            lines.append("|---|---|")
            for a in mod_claims:
                lines.append(f"| `{a['modifier_iri']}` | `{a['base_dir']}` |")
            lines.append("")
        if base_lists:
            lines.append("### Base lists modifier, but modifier doesn't claim base")
            lines.append("")
            lines.append(
                "Base's `[modeling].applicable_modifiers` lists this slug, the slug "
                "resolves to an existing modifier in the corpus, but the modifier's "
                "`applicableToRatePlan` doesn't include this base's IRI. Likely fix: "
                "extend the modifier's `applicableToRatePlan` array — or remove the "
                "slug from the base if the pairing was speculative."
            )
            lines.append("")
            lines.append("| Base | Slug claims | Modifier filing |")
            lines.append("|---|---|---|")
            for a in base_lists:
                lines.append(f"| `{a['base_dir']}` | `{a['modifier_slug']}` | `{a['modifier_filing']}` |")
            lines.append("")

    # Per-base detail, grouped by utility
    lines.append("## Per-base detail")
    lines.append("")

    by_utility: dict[str, list[dict]] = defaultdict(list)
    for b in bases:
        by_utility[b["utility"]].append(b)

    for utility in sorted(by_utility.keys()):
        lines.append(f"### {utility.upper()}")
        lines.append("")
        for b in by_utility[utility]:
            base_status = "✓" if b["complete"] else ("~" if b["complete"] is False else "?")
            lines.append(f"#### `{b['schedule']}` @ {b['date']}  &nbsp; base: {base_status}")
            lines.append("")
            if b["deferrals"]:
                lines.append("Base deferrals:")
                for d in b["deferrals"]:
                    lines.append(f"- {d}")
                lines.append("")
            if not b["applicable_modifiers"]:
                lines.append("_No applicable modifiers declared._")
                lines.append("")
                continue
            lines.append("| Modifier | Status | Filing |")
            lines.append("|---|---|---|")
            for slug in b["applicable_modifiers"]:
                status, entry = classify(slug, b["utility"], idx)
                glyph = STATUS_GLYPH[status]
                filing = f"`{entry['dir']}`" if entry else "—"
                lines.append(f"| `{slug}` | {glyph} {status} | {filing} |")
            lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON to stdout instead of writing the markdown report")
    parser.add_argument("--out", default="reports/modifier-coverage.md", help="output path for markdown report")
    args = parser.parse_args()

    idx = build_modifier_index()
    bases = collect_bases()
    by_modifier, _ = collect_pairings()
    asymmetries = find_asymmetries(bases, by_modifier)

    if args.json:
        records = []
        for b in bases:
            for slug in b["applicable_modifiers"]:
                status, entry = classify(slug, b["utility"], idx)
                records.append({
                    "base": {
                        "utility": b["utility"],
                        "schedule": b["schedule"],
                        "date": b["date"],
                        "complete": b["complete"],
                    },
                    "modifier_slug": slug,
                    "status": status,
                    "modifier_filing": entry["dir"] if entry else None,
                    "modifier_complete": entry["complete"] if entry else None,
                })
        json.dump({"coverage": records, "asymmetries": asymmetries}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    md = render_markdown(bases, idx, asymmetries)
    out_path = REPO / args.out
    out_path.write_text(md)
    print(f"wrote {out_path.relative_to(REPO)} ({len(asymmetries)} asymmetries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
