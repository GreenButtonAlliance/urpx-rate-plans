#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Download SCE tariff PDFs from a SharePoint folder.

SCE publishes its current and historical tariff PDFs in Microsoft SharePoint
folders at edisonintl.sharepoint.com. The folders are anonymously-readable
(no login) but require a real browser session — direct curl gets 403, and
the spel CLI's downloads land in ~/Downloads.

This script uses Playwright (Python) to:
  - open the SharePoint folder URL as an unauthenticated visitor
  - enumerate all PDF rows in the file listing
  - click each PDF and capture its download into a non-sandbox dir
  - emit a manifest (filename, size, sha256, source_url) usable for
    seeding tariff.toml [source.sha256] entries

Usage:
    python scripts/fetch-sce-tariffs.py \\
        --folder-url 'https://edisonintl.sharepoint.com/:f:/t/Public/TM2/...' \\
        --out-dir <download-dir>/

The folder URL is the public share link from SCE's tariff-books pages
(e.g. /regulatory/tariff-books/historical-rates/historical-rate-schedules-for-2025
points to the residential-rates SharePoint folder).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def strip_multipart_wrapper(path: Path) -> bool:
    """SCE's SharePoint preview returns the PDF inside a multipart/form-data
    response (boundary + Content-Disposition headers + body). Playwright's
    download.save_as captures the raw response, leaving the wrapper around
    the PDF. Strip it in place. Returns True if a wrapper was found."""
    data = path.read_bytes()
    if data.startswith(b"%PDF-"):
        return False
    start = data.find(b"%PDF-")
    if start < 0:
        return False
    eof = data.rfind(b"%%EOF")
    body = data[start:eof + 5] + b"\n" if eof > start else data[start:]
    path.write_bytes(body)
    return True


def fetch_folder(folder_url: str, out_dir: Path, only: list[str] | None = None) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        page.goto(folder_url, wait_until="domcontentloaded")
        # SharePoint renders the file list lazily. The PDF row is an
        # accessible button whose name is the filename. Use role-based
        # locator + name regex (this is what spel's a11y tree showed).
        try:
            page.get_by_role("button", name=re.compile(r"\.pdf$")).first.wait_for(timeout=30_000)
        except PWTimeout:
            page.screenshot(path=str(out_dir / "_debug-no-pdfs.png"))
            print(f"DEBUG: no .pdf buttons found; screenshot saved to {out_dir}/_debug-no-pdfs.png")
            print(f"DEBUG: current URL = {page.url}")
            print(f"DEBUG: page title = {page.title()}")
            raise

        pdf_buttons = page.get_by_role("button", name=re.compile(r"\.pdf$"))
        count = pdf_buttons.count()
        print(f"Found {count} PDF entries in folder")

        # Cache filenames before we start clicking — clicking opens a preview
        # dialog that re-renders the row list, invalidating positional indexes.
        filenames = []
        for i in range(count):
            btn = pdf_buttons.nth(i)
            name = btn.get_attribute("aria-label") or btn.inner_text() or ""
            filenames.append(name.strip() or f"pdf-{i}.pdf")

        for i, filename in enumerate(filenames):
            if only and not any(filename == name or filename.startswith(name) for name in only):
                continue

            target = out_dir / filename
            if target.exists():
                print(f"  [{i+1}/{count}] {filename} already exists — skipping")
                manifest.append({
                    "filename": filename,
                    "path": str(target),
                    "size": target.stat().st_size,
                    "sha256": sha256_of(target),
                    "source_url": folder_url,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "skipped": True,
                })
                continue

            print(f"  [{i+1}/{count}] downloading {filename} ...")
            row_button = page.get_by_role("button", name=filename).first
            try:
                with page.expect_download(timeout=60_000) as dl_info:
                    row_button.click()
                    page.wait_for_timeout(2000)
                    # Find and click the "Download this file to your device" menuitem
                    download_btn = page.get_by_role("menuitem", name=re.compile(r"^Download this file", re.I)).first
                    download_btn.click(timeout=10_000)
                download = dl_info.value
                download.save_as(str(target))
                if strip_multipart_wrapper(target):
                    print(f"      stripped multipart wrapper from {filename}")
            except PWTimeout:
                print(f"      ! timeout — closing preview and continuing")
            finally:
                close_btn = page.get_by_role("menuitem", name="Close").first
                try:
                    if close_btn.is_visible():
                        close_btn.click()
                        page.wait_for_timeout(500)
                except Exception:
                    pass

            if not target.exists():
                continue

            manifest.append({
                "filename": filename,
                "path": str(target),
                "size": target.stat().st_size,
                "sha256": sha256_of(target),
                "source_url": folder_url,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })

        browser.close()

    return manifest


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--folder-url", required=True, help="SharePoint folder URL")
    p.add_argument("--out-dir", required=True, type=Path, help="Local download directory")
    p.add_argument(
        "--only",
        nargs="*",
        help="Filter to specific filenames or prefixes (e.g. ELECTRIC_SCHEDULES_TOU-D)",
    )
    p.add_argument("--manifest", type=Path, help="Write JSON manifest to this path")
    args = p.parse_args()

    manifest = fetch_folder(args.folder_url, args.out_dir, args.only)

    print("\n=== Manifest ===")
    for entry in manifest:
        marker = "(cached)" if entry.get("skipped") else "(fresh)"
        print(f"  {marker} {entry['filename']}  {entry['size']:,} bytes  sha256={entry['sha256'][:16]}...")

    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2))
        print(f"\nWrote manifest to {args.manifest}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
