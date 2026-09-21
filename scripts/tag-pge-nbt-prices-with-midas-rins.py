#!/usr/bin/env python3
"""Retroactively tag PG&E NBT Delivery Component Prices with their CEC MIDAS
Rate Identification Numbers (RINs).

Idempotent — running multiple times produces the same result. Each Delivery
Price gets its MIDAS RIN appended to urpx:name. Generation Prices remain
untagged (PG&E doesn't publish a Generation EEC channel in MIDAS).

Discovery context (2026-05-29):
- PG&E publishes NBT Delivery EEC in MIDAS as USCA-PGXX-{code}-0000 with
  RateName "E-ELEC" + AltRateName1 carrying the NBT vintage label
- Bundled and CCA customers share the same Delivery RIN data (Delivery is
  system-wide; the CCA suffix on the AltRateName1 is a labeling artifact —
  the underlying ACC-derived Delivery values are identical)
- Generation EEC is NOT published in MIDAS for PG&E (XXPG RIN family only
  contains SGIP/Flex entries — same situation as SCE)

PG&E E-ELEC NBT MIDAS RIN mapping (Delivery only):
  USCA-PGXX-3500-0000   E-ELEC + NBT23-CCA (2023 vintage)
  USCA-PGXX-3600-0000   E-ELEC + NBT24-CCA (2024 vintage)
  USCA-PGXX-3900-0000   E-ELEC + NBT25-CCA (2025 vintage)
  USCA-PGXX-4000-0000   E-ELEC + NBT26-CCA (2026 vintage)
  (USCA-PGXX-3700-0000   E-ELEC + NBT00-CCA — no PG&E NBT00 vintage in
   our model; PG&E publishes only the 4 lock-in vintages 2023-2026)
"""

import json
from collections import OrderedDict
from pathlib import Path

JSONLD = Path("ca/iou/pge/nbt/versions/2025-10-17/rate-plan-modifier_pge_nbt_2025-10-17.jsonld")

VINTAGE_TO_RIN = {
    "2023": "USCA-PGXX-3500-0000",
    "2024": "USCA-PGXX-3600-0000",
    "2025": "USCA-PGXX-3900-0000",
    "2026": "USCA-PGXX-4000-0000",
}

RIN_MARKER = "MIDAS RIN:"


def main():
    doc = json.load(JSONLD.open(), object_pairs_hook=OrderedDict)
    prices = doc["urpx:hasRatePlanModifier"]["urpx:hasRatePlanModifierVersion"]["urpx:hasPrices"]["urpx:hasPrice"]
    tagged = 0
    already_tagged = 0
    untaggable_generation = 0

    for p in prices:
        pid = p.get("@id", "")
        # Skip ACC Plus, only handle export-rate Prices
        if "-pro-" not in pid and "-del-" not in pid:
            continue
        # Extract vintage — e.g. "pge:nbt-price-v2025-pro-m07-h17-weekday"
        import re
        m = re.search(r"-v(\d{4})-(\w{3})-", pid)
        if not m:
            continue
        vintage = m.group(1)
        component = m.group(2)  # "pro" (Generation) or "del" (Delivery)

        if component == "pro":
            untaggable_generation += 1
            continue
        if component != "del":
            continue

        rin = VINTAGE_TO_RIN.get(vintage)
        if not rin:
            continue

        name = p.get("urpx:name", "")
        if RIN_MARKER in name:
            already_tagged += 1
            continue

        # Append " (MIDAS RIN: <rin>)" before the existing " — Jan..." suffix if present
        # Existing pattern: "NBT Delivery Component — 2026 vintage, January weekday, 00:00-01:00 PT"
        # Want: "NBT Delivery Component (MIDAS RIN: USCA-PGXX-4000-0000 — E-ELEC NBT26-CCA) — 2026 vintage, January..."
        alt_label = {"2023": "E-ELEC NBT23-CCA",
                     "2024": "E-ELEC NBT24-CCA",
                     "2025": "E-ELEC NBT25-CCA",
                     "2026": "E-ELEC NBT26-CCA"}[vintage]
        new_name = name.replace(" — ", f" ({RIN_MARKER} {rin} — {alt_label}) — ", 1)
        if new_name == name:
            new_name = f"{name} ({RIN_MARKER} {rin} — {alt_label})"
        p["urpx:name"] = new_name
        tagged += 1

    print(f"Tagged {tagged} Delivery Prices with MIDAS RINs")
    print(f"Already tagged: {already_tagged}")
    print(f"Generation Prices (untaggable — no PG&E XXPG RIN family): {untaggable_generation}")

    with JSONLD.open("w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    print(f"Wrote {JSONLD}")


if __name__ == "__main__":
    main()
