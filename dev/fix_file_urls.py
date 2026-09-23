#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Replace dangling `file://` DataSourceReference URLs with the canonical source.

Eleven urpx:url values across five filings pointed at `file://./assets/<NAME>.pdf`.
None of those files exist: there is no assets/ directory anywhere in the corpus,
and the real PDFs sit beside each filing under the LAYOUT.md section 7 name. The
form is not even a well-formed absolute URI, since file:// takes an authority, so
`./` parses as the host.

The authority for what each should say is the filing's own tariff.toml, which
LAYOUT.md already defines as the manifest recording the canonical URL, sha256 and
retrieval date. This script reads that rather than copying between JSON-LD files,
so the result agrees with the manifest by construction.

TWO DIFFERENT FIXES, because the two utilities use different properties:

  CPAU filings carry the canonical https URL in urpx:url and no urpx:accessURL,
  which is what the standalone modifier filings already do. The inline copies get
  the same treatment, which also makes them agree with their standalone originals.

  PG&E filings carry urpx:accessURL and NO urpx:url at all: verified across
  e-tou-c, e-tou-d, ev2 and e-1, none of which has one. The two e-elec urpx:url
  values are leftovers sitting beside an already-correct accessURL, so they are
  deleted rather than corrected.

Usage:
    python3 dev/fix_file_urls.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

# Which tariff.toml [source.*] section backs each stray file:// basename.
SECTION_OF = {
    "CPAU_E-1_": "base",
    "CPAU_E-1-TOU_": "base",
    "CPAU_E-HRA_": "modifier_e_hra",
    "CPAU_E-EEC-1_": "modifier_e_eec_1",
    "CPAU_E-NSE-1_": "modifier_e_nse_1",
}


def source_entry(toml_path: Path, basename: str) -> dict | None:
    doc = corpus.load_toml(toml_path)
    src = doc.get("source") or {}

    # Match the named sub-table FIRST. Falling back to the single-source
    # [source].url before checking is what made an earlier run attribute the
    # E-HRA modifier to the E-1 base PDF: the wrong provenance, asserted
    # confidently, in the exact field a reader would trust. A basename that
    # names a modifier must resolve to that modifier's own section or not at all.
    section = next((s for prefix, s in SECTION_OF.items()
                    if basename.startswith(prefix)), None)
    if section and section != "base":
        s = src.get(section)
        if isinstance(s, dict) and "url" in s:
            return {"url": s["url"], "retrieved_on": s.get("retrieved_on")}
        return None

    if isinstance(src.get("base"), dict) and "url" in src["base"]:
        return {"url": src["base"]["url"],
                "retrieved_on": src["base"].get("retrieved_on")}
    if "url" in src:
        return {"url": src["url"], "retrieved_on": src.get("retrieved_on")}
    return None


def fix_file(path: Path, dry_run: bool) -> tuple[int, list[str]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    toml_path = path.parent / "tariff.toml"
    if not toml_path.exists():
        return 0, [f"{path.name}: no tariff.toml beside it"]

    changes: list[str] = []
    problems: list[str] = []
    is_pge = "/pge/" in str(path)
    # urpx:dateRetrieved is sh:datatype xsd:date, and these filings carry no
    # coercion for it because they never used the property before. Written as a
    # bare string it lands as an xsd:string and fails the shape, so the term has
    # to go into @context alongside the value. Every filing that already uses
    # dateRetrieved declares exactly this.
    needs_date_term: set[bool] = set()

    def visit(node):
        if not isinstance(node, dict):
            return
        u = node.get("urpx:url")
        if not (isinstance(u, str) and u.startswith("file://")):
            return
        basename = u.rsplit("/", 1)[-1]

        if is_pge:
            # Deleting is only safe because accessURL already carries the real
            # source; refuse rather than drop the only pointer this node has.
            if not node.get("urpx:accessURL"):
                problems.append(f"{path.name}: {basename} has no accessURL to fall "
                                f"back on; refusing to delete its urpx:url")
                return
            del node["urpx:url"]
            changes.append(f"    removed urpx:url {basename} "
                           f"(accessURL already correct)")
            return

        entry = source_entry(toml_path, basename)
        if entry is None:
            problems.append(f"{path.name}: no tariff.toml [source] entry backs "
                            f"{basename}")
            return
        node["urpx:url"] = entry["url"]
        node["urpx:fileName"] = entry["url"].rsplit("/", 1)[-1]
        if entry["retrieved_on"]:
            node["urpx:dateRetrieved"] = str(entry["retrieved_on"])
            needs_date_term.add(True)
        node.setdefault("urpx:dataSourceType", {"@id": "urpx:utilityWebsiteSource"})
        changes.append(f"    {basename} -> {entry['url'].rsplit('/', 1)[-1]}")

    def walk(node):
        if isinstance(node, dict):
            visit(node)
            for k, v in node.items():
                if k == "@context":
                    continue
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(doc)
    if problems:
        return 0, problems

    if needs_date_term:
        ctx = doc.get("@context")
        if not isinstance(ctx, dict):
            return 0, [f"{path.name}: @context is not an inline object; cannot "
                       f"add the xsd:date coercion urpx:dateRetrieved needs"]
        if "urpx:dateRetrieved" not in ctx:
            ctx["urpx:dateRetrieved"] = {"@type": "xsd:date"}
            changes.append("    @context += urpx:dateRetrieved -> xsd:date")

    if changes and not dry_run:
        with path.open("w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    if changes:
        print(f"  {path.name}")
        for c in changes:
            print(c)
    return len(changes), []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = corpus.all_filing_jsonld()
    corpus.require_nonempty(files, "rate-plan filings")

    total = 0
    problems: list[str] = []
    for p in files:
        n, probs = fix_file(Path(p), args.dry_run)
        total += n
        problems.extend(probs)

    if problems:
        print("\nREFUSED:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 3
    verb = "would fix" if args.dry_run else "fixed"
    print(f"\n{verb} {total} file:// reference(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
