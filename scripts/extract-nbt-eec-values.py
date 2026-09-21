#!/usr/bin/env python3
"""Extract EEC values from PG&E's published per-vintage price sheets.

PG&E publishes Solar Billing Plan / NBT Energy Export Credit values as PDFs
in a ZIP at pge.com/energyexportcredit. Each per-vintage PDF carries two
tables (Weekday + Weekend/Holiday) where each cell is 1 hour × 1 month and
contains 2 values: Energy Produced + Energy Delivered.

Approach: pdfplumber's extract_text() returns the full 48 hour rows cleanly
(24 weekday + 24 weekend) — each as a single line. extract_words() drops a
row inconsistently across vintages, so text-line parsing is more robust.
Within each line, the time prefix ("12:00 AM") is followed by 24 dollar
values (12 months × 2 components — Produced, Delivered, Produced, ...).

Output: JSON at the path passed via --out, structure:
  { vintage: { "weekday": [[{"produced", "delivered"}×12]×24], "weekend": [...] } }
Hour 0 = 12:00 AM; month 0 = January.
"""

import os
import argparse
import json
import re
from pathlib import Path

import pdfplumber
import pypdf

VINTAGE_PDFS = {
    "2023": "PGE_Solar Billing Plan_EEC Values Price Sheet 2023.pdf",
    "2024": "PGE_Solar Billing Plan_EEC Values Price Sheet 2024.pdf",
    "2025": "PGE_Solar Billing Plan_EEC Values Price Sheet 2025.pdf",
    "2026": "PGE_Solar Billing Plan_EEC Values Price Sheet 2026.pdf",
}

# A row line looks like: "12:00 AM 0.09342 0.00089 ... 0.08964 0.00085" (or with $ prefix)
ROW_RE = re.compile(r"^(\d{1,2}):00 (AM|PM)\b\s*(.*)$")
# Decimal value: optional leading $, digits, dot, digits. Trailing characters/footnote markers
# (e.g., "HigherValueforCredits") follow with whitespace and are dropped by re.findall.
VAL_RE = re.compile(r"\$?(\d+\.\d+)")


def parse_hour(label_h, label_ampm):
    h = int(label_h)
    if label_ampm == "AM":
        return 0 if h == 12 else h
    return 12 if h == 12 else h + 12


def _text_pdfplumber(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        return pdf.pages[0].extract_text()


def _text_pypdf(pdf_path):
    return pypdf.PdfReader(str(pdf_path)).pages[0].extract_text()


def _try_extract(text):
    """Return list of (hour, [24 values]) tuples for the first 48 rows; or None
    if any row found has fewer than 24 values."""
    row_matches = []
    for ln in text.split("\n"):
        m = ROW_RE.match(ln.strip())
        if not m:
            continue
        h = parse_hour(m.group(1), m.group(2))
        rest = m.group(3)
        vals = VAL_RE.findall(rest)
        if len(vals) < 24:
            return None
        row_matches.append((h, vals[:24]))
        if len(row_matches) == 48:
            break
    if len(row_matches) != 48:
        return None
    return row_matches


def extract_vintage(pdf_path):
    # PDFs have inconsistent quirks across vintages: 2026 has bold-overstrike
    # (breaks pdfplumber); 2025 has whitespace that pypdf collapses (breaks pypdf).
    # Try both text extractors and use whichever yields a clean parse.
    row_matches = None
    for extractor in (_text_pdfplumber, _text_pypdf):
        text = extractor(pdf_path)
        row_matches = _try_extract(text)
        if row_matches is not None:
            break
    if row_matches is None:
        raise RuntimeError(f"both pdfplumber and pypdf failed to extract 48 clean rows from {pdf_path.name}")
    text = None  # not needed beyond here

    weekday = [None] * 24
    weekend = [None] * 24
    seen_weekday = set()
    for h, vals in row_matches:
        table = weekday if h not in seen_weekday else weekend
        if h not in seen_weekday:
            seen_weekday.add(h)
        if table[h] is not None:
            raise RuntimeError(f"duplicate row at hour={h}")
        table[h] = [{"produced": vals[m * 2], "delivered": vals[m * 2 + 1]} for m in range(12)]

    if any(r is None for r in weekday + weekend):
        raise RuntimeError("missing rows after parse")

    return {"weekday": weekday, "weekend": weekend}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pdf-dir",
        default=os.environ.get("URPX_SOURCE_DATA", "") + "/pge-eec-price-sheets/PGE-EEC-Price-Sheets",
    )
    parser.add_argument("--out", default="/tmp/pge-nbt-eec-values.json")
    args = parser.parse_args()

    out = {}
    for vintage, fname in VINTAGE_PDFS.items():
        pdf_path = Path(args.pdf_dir) / fname
        print(f"Extracting {vintage}...")
        out[vintage] = extract_vintage(pdf_path)

    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {args.out}")
    # Sanity samples
    s = out["2026"]["weekday"][0][0]
    print(f"  2026 weekday hour 0 month 0: {s} (expected Jan 12am Produced=0.09342 Delivered=0.00089)")
    s = out["2023"]["weekday"][0][0]
    print(f"  2023 weekday hour 0 month 0: {s}")


if __name__ == "__main__":
    main()
