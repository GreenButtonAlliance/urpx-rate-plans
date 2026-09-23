#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Utility identity, in one place.

`corpus.py` answers where things are. This answers who they are, and the two are
separate on purpose: `corpus.py` holds no data at all, which is what lets it
promise that the next restructure changes nothing in it. A name table in there
would put that promise up for review every time the tree moves.

What was duplicated before this module existed:

  - `UTILITY_ORDER` and `UTILITY_LABEL`, byte-identical in
    `list_ready_for_use.py` and `list_service_arrangements.py`, plus three
    partial copies elsewhere.
  - The MIDAS party segment map, in three copies. Two were identical 8-entry
    tables under different names (`SEGMENT_UTILITY`, `MODELED`). The third,
    `build_inventory.MIDAS_SEGMENTS`, held only the five bundled segments and
    said why. That third one was never drift, so it is kept here as a named
    view rather than flattened into the others.
  - The regulatory class, held in three places with three vocabularies.

The roster is NOT restated here. It is read from the corpus, and `_check()`
refuses if this table and the tree disagree, because a hardcoded roster that
falls behind the directories is the failure this module exists to remove.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus  # noqa: E402


class Utility(NamedTuple):
    slug: str
    short_name: str
    utility_class: str        # iou | pou
    bundled_segment: str      # MIDAS party segment for its own bundled service
    delivery_segment: str     # the CCA-served, delivery-only segment; "" if none


# Only utilities with filings need an identity here; the other 15 directories
# under us/ca/ are discovery manifests with nothing to label yet.
#
# A publicly owned utility has no community choice aggregation in its territory,
# so it publishes no delivery-only segment. That is why the POU rows carry "":
# it is an absence in MIDAS, not a value this table is missing. Verified against
# the mined feed, where XXLA, LAXX, XXSM and SMXX all return zero rows.
_UTILITIES = (
    Utility("pge",   "PG&E",   "iou", "PGPG", "PGXX"),
    Utility("sce",   "SCE",    "iou", "SCSC", "SCXX"),
    Utility("sdge",  "SDG&E",  "iou", "SDSD", "SDXX"),
    Utility("cpau",  "CPAU",   "pou", "",     ""),
    Utility("smud",  "SMUD",   "pou", "SMSM", ""),
    Utility("ladwp", "LADWP",  "pou", "LALA", ""),
)

CLASS_LABEL = {"iou": "IOU", "pou": "POU", "cca": "CCA"}

# Presentation order for per-utility report sections. Declared, not derived:
# it is largest-first by customers served, which no file on disk states.
ORDER = [u.slug for u in _UTILITIES]

BY_SLUG = {u.slug: u for u in _UTILITIES}


def _check() -> None:
    """Refuse if this table and the corpus disagree about which utilities exist.

    The direction that matters is a utility gaining filings without gaining a
    row here: it would then be dropped from every per-utility report section
    with nothing failing. The reverse, a row here for a utility whose filings
    were removed, is reported too.
    """
    modeled = set(corpus.utilities_with_filings())
    known = set(BY_SLUG)
    if modeled - known:
        raise SystemExit(
            f"ERROR: {sorted(modeled - known)} have filings in the corpus but no row "
            f"in dev/utilities.py, so every per-utility report would omit them "
            f"silently. Add them to _UTILITIES."
        )
    if known - modeled:
        raise SystemExit(
            f"ERROR: {sorted(known - modeled)} have a row in dev/utilities.py but no "
            f"filings in the corpus. Remove the row, or restore the filings."
        )


def ordered() -> list[Utility]:
    """Every modeled utility in report order, after checking the roster."""
    _check()
    return [BY_SLUG[s] for s in ORDER]


def label(slug: str) -> str:
    """"PG&E (IOU)". The form two report generators each built their own copy of."""
    u = BY_SLUG[slug]
    return f"{u.short_name} ({CLASS_LABEL[u.utility_class]})"


def labels() -> dict[str, str]:
    return {u.slug: label(u.slug) for u in _UTILITIES}


def by_class(utility_class: str) -> list[Utility]:
    out = [u for u in ordered() if u.utility_class == utility_class]
    corpus.require_nonempty(out, f"utilities of class {utility_class!r}")
    return out


def segment_utility() -> dict[str, str]:
    """Every MIDAS party segment this corpus models -> utility slug.

    Both bundled and delivery-only segments. Replaces the two identical copies
    in `fetch_tariff_documents.py` and `list_midas_catalog.py`.
    """
    out = {}
    for u in _UTILITIES:
        for seg in (u.bundled_segment, u.delivery_segment):
            if seg:
                out[seg] = u.slug
    return out


def bundled_segment_utility() -> dict[str, str]:
    """Bundled segments only -> utility slug.

    The narrower view `build_inventory.py` needs, where a segment is used to
    attribute an inventory of schedules. A delivery-only segment names a
    composition of one party's delivery with another's generation rather than a
    schedule, so including it there would attribute compositions to a schedule
    list. Kept as a separate accessor because that distinction is real.
    """
    return {u.bundled_segment: u.slug for u in _UTILITIES if u.bundled_segment}
