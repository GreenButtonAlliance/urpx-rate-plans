#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Utility identity, in one place.

`corpus.py` answers where things are. This answers who they are, and the two are
separate on purpose: `corpus.py` holds no data at all, which is what lets it
promise that the next restructure changes nothing in it. A name table in there
would put that promise up for review every time the tree moves.

What was duplicated before this module existed:

  - `UTILITY_ORDER` and `UTILITY_LABEL`, byte-identical in
    `list_ready_for_use.py` and `list_scenario_cost_models.py`, plus three
    partial copies elsewhere.
  - The MIDAS party segment map, in three copies. Two were identical 8-entry
    tables under different names (`SEGMENT_UTILITY`, `MODELED`). The third,
    `build_inventory.MIDAS_SEGMENTS`, held only the five bundled segments and
    said why. That third one was never drift, so it is kept here as a named
    view rather than flattened into the others.
  - The regulatory class, held in three places with three vocabularies.

The DATA is not here either. It lives in each utility's `utility.toml`, beside
the discovery URLs describing the same utility, where a person edits it and where
`dev/lint_utility_manifests.py` schema-checks it. This module only reads and
shapes it. `_check()` refuses if the manifests and the tree disagree, because a
roster that falls behind the directories is the failure this module exists to
remove.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus  # noqa: E402


class Utility(NamedTuple):
    slug: str
    short_name: str           # "" where no established abbreviation is recorded
    utility_class: str        # iou | pou | cca
    bundled_segment: str      # MIDAS party segment for its own bundled service
    delivery_segment: str     # the CCA-served, delivery-only segment; "" if none
    legal_name: str           # as the corpus states it in urpx:legalName; "" if unknown
    eia_id: str               # skos:notation under urpx:eiaScheme; "" if unknown
    midas_party_names: tuple  # how the MIDAS Energy lookup spells this party
    delivered_by: str         # utility slug whose wires carry it; "" if its own


CLASS_LABEL = {"iou": "IOU", "pou": "POU", "cca": "CCA"}


def _load() -> dict[str, Utility]:
    """Read identity out of the per-utility utility.toml manifests.

    The data used to be a literal here. It is on disk instead because the disk
    copy is the one a person edits when a utility changes, it is schema-checked by
    dev/lint_utility_manifests.py, and it is beside the discovery URLs that
    describe the same utility.

    Absence is distinguished from emptiness only where the schema allows it:
    utility_class is required of every manifest, so a missing one is a refusal
    rather than a default.
    """
    out: dict[str, Utility] = {}
    for manifest in corpus.utility_tomls():
        slug = manifest.parent.name
        d = corpus.load_toml(manifest)
        klass = d.get("utility_class")
        if klass not in CLASS_LABEL:
            raise SystemExit(
                f"ERROR: {manifest.parent.name}/utility.toml has utility_class "
                f"{klass!r}, which is not one of {sorted(CLASS_LABEL)}. Every manifest "
                f"must state a class; guessing one would put a utility in the wrong "
                f"regulatory category in every report that groups by it."
            )
        out[slug] = Utility(
            slug=slug,
            short_name=d.get("short_name", ""),
            utility_class=klass,
            bundled_segment=d.get("midas_bundled_segment", ""),
            delivery_segment=d.get("midas_delivery_segment", ""),
            legal_name=d.get("legal_name", ""),
            eia_id=d.get("eia_id", ""),
            midas_party_names=tuple(d.get("midas_party_names", ())),
            delivered_by=d.get("delivered_by", ""),
        )
    corpus.require_nonempty(out, "utility identity (utility.toml manifests)")
    return out


ALL = _load()
BY_SLUG = ALL

# Presentation order for per-utility report sections. Declared rather than
# derived: it is largest-first by customers served, which no manifest states.
# Only utilities with filings appear in those sections.
ORDER = ["pge", "sce", "gpc", "sdge", "pse", "scl", "cpau", "smud", "ladwp"]


def _check() -> None:
    """Refuse if the manifests and the corpus disagree about what is modeled.

    Three ways they can disagree, all of which are silent otherwise:

      - a utility has filings but no manifest, so nothing knows its class;
      - a utility has filings and a manifest but no `short_name`, so every
        per-utility report heading would render as "(IOU)" with a blank name;
      - ORDER and the set of modeled utilities differ, so a section would be
        dropped from a report or an unknown slug looked up.

    A manifest WITHOUT filings is not an error; LAYOUT.md §5 calls it a normal
    state, and dev/lint_utility_manifests.py prints the current split.
    """
    modeled = set(corpus.utilities_with_filings())
    known = set(ALL)
    if modeled - known:
        raise SystemExit(
            f"ERROR: {sorted(modeled - known)} have filings in the corpus but no "
            f"utility.toml, so nothing states their class and every per-utility "
            f"report would omit them silently."
        )
    unnamed = sorted(s for s in modeled if not ALL[s].short_name)
    if unnamed:
        raise SystemExit(
            f"ERROR: {unnamed} have filings but no short_name in their utility.toml, "
            f"so their report headings would render with an empty name. Add one."
        )
    if set(ORDER) != modeled:
        raise SystemExit(
            f"ERROR: ORDER in dev/utilities.py is {sorted(ORDER)} but the corpus models "
            f"{sorted(modeled)}. Missing from ORDER: {sorted(modeled - set(ORDER))}; "
            f"in ORDER without filings: {sorted(set(ORDER) - modeled)}."
        )


def ordered() -> list[Utility]:
    """Every modeled utility in report order, after checking the roster."""
    _check()
    return [ALL[s] for s in ORDER]


def label(slug: str) -> str:
    """"PG&E (IOU)". The form two report generators each built their own copy of."""
    u = ALL[slug]
    return f"{u.short_name} ({CLASS_LABEL[u.utility_class]})"


def labels() -> dict[str, str]:
    """Labels for the modeled utilities, which are the ones reports group by."""
    return {u.slug: label(u.slug) for u in ordered()}


def by_class(utility_class: str) -> list[Utility]:
    out = [u for u in ordered() if u.utility_class == utility_class]
    corpus.require_nonempty(out, f"utilities of class {utility_class!r}")
    return out


def segment_utility() -> dict[str, str]:
    """Every MIDAS party segment this corpus models -> utility slug.

    Both bundled and delivery-only segments. Replaces the two identical copies
    that were in `fetch_tariff_documents.py` and `list_midas_catalog.py`. Only
    manifests that record a segment contribute, so the aggregators, which have a
    party name and no segment recorded, do not appear.
    """
    out = {}
    for u in ALL.values():
        for seg in (u.bundled_segment, u.delivery_segment):
            if seg:
                out[seg] = u.slug
    corpus.require_nonempty(out, "MIDAS party segments in the manifests")
    return out


def bundled_segment_utility() -> dict[str, str]:
    """Bundled segments only -> utility slug.

    The narrower view `build_inventory.py` needs, where a segment is used to
    attribute an inventory of schedules. A delivery-only segment names a
    composition of one party's delivery with another's generation rather than a
    schedule, so including it there would attribute compositions to a schedule
    list. Kept as a separate accessor because that distinction is real.
    """
    out = {u.bundled_segment: u.slug for u in ALL.values() if u.bundled_segment}
    corpus.require_nonempty(out, "bundled MIDAS party segments in the manifests")
    return out


def party_name_utility() -> dict[str, str]:
    """MIDAS Energy-table Description -> utility slug.

    The half of `list_california_parties.KIND` that is a fact about MIDAS rather
    than an assertion about regulation.
    """
    out = {}
    for u in ALL.values():
        for name in u.midas_party_names:
            out[name] = u.slug
    corpus.require_nonempty(out, "MIDAS party names in the manifests")
    return out
