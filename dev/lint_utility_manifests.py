#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Check every utility.toml against schema/utility-manifest.schema.json.

The schema existed with no runner. `corpus.utility_tomls()` had no callers, no
lint loaded the schema, and `check_all.py` never mentioned it, so the twenty-one
manifests were checked only by whoever last edited one by hand. Adding fifteen
at once is what made that worth fixing.

Three things the schema cannot state are checked here as well:

  - `utility` has to equal the directory name. The schema constrains its
    spelling and cannot see where the file sits, so a copied manifest keeping
    the utility it was copied from would validate.
  - A directory holding filings has to hold a manifest. Absence is the failure
    the schema can never catch, because it only ever sees files that exist.
  - A URL has to be an http(s) URL. `format: uri` in draft 2020-12 is an
    annotation rather than an assertion, so nothing was enforcing even that.

Not checked: whether a URL is a discovery surface rather than one tariff. The
first draft rejected any `.pdf`, which flagged SCE's annual summary of available
rates. That one is a discovery surface that happens to be a PDF, and nothing in
a URL separates it from a single schedule's PDF, so the rule was dropped instead
of being given an exemption it could not justify.

Exit 0 clean, 1 on any violation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 and earlier
    import tomli as tomllib

import corpus

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "schema" / "utility-manifest.schema.json"


def main() -> int:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        print("REFUSING: jsonschema is not installed, so nothing would be "
              "validated and this lint would pass without comparing anything.",
              file=sys.stderr)
        return 1

    validator = Draft202012Validator(json.loads(SCHEMA.read_text()))
    manifests = corpus.utility_tomls()
    # A lint that matches no file passes trivially; that has happened here
    # before (see the note at the top of dev/coverage.py).
    corpus.require_nonempty(manifests, "utility manifests")

    problems: list[str] = []
    seen: dict[str, Path] = {}

    for path in manifests:
        rel = path.relative_to(REPO)
        directory = path.parent.name
        try:
            doc = tomllib.loads(path.read_text())
        except tomllib.TOMLDecodeError as exc:
            problems.append(f"{rel}: not parseable as TOML: {exc}")
            continue

        for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.path)):
            where = "/".join(str(p) for p in err.path) or "(root)"
            problems.append(f"{rel}: {where}: {err.message}")

        declared = doc.get("utility")
        if declared is not None and declared != directory:
            problems.append(
                f"{rel}: declares utility '{declared}' but sits in directory "
                f"'{directory}'. Every report keys on the directory, so the two "
                f"disagreeing silently splits one utility into two.")
        if declared in seen:
            problems.append(f"{rel}: utility '{declared}' also declared in "
                            f"{seen[declared].relative_to(REPO)}")
        elif declared is not None:
            seen[declared] = path

        for url in doc.get("tariff_index_urls", []):
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                problems.append(f"{rel}: tariff_index_urls: '{url}' is not an http(s) URL")

    # A utility directory is one holding either a manifest or filings. Both
    # shapes are legitimate on their own except this one: filings with no
    # manifest, which leaves no record of where the next version comes from.
    for jsonld in corpus.all_filing_jsonld():
        util, _, _ = corpus.parse_filing_path(jsonld)
        if util not in seen:
            problems.append(f"us/ca/{util}/: has filings but no utility.toml, so "
                            f"nothing records where its tariffs are published")
            seen[util] = jsonld  # report once

    if problems:
        print(f"utility manifests: {len(problems)} problem(s)\n", file=sys.stderr)
        for p in sorted(set(problems)):
            print(f"  {p}", file=sys.stderr)
        return 1

    filings = {corpus.parse_filing_path(j)[0] for j in corpus.all_filing_jsonld()}
    print(f"utility manifests: clean ({len(manifests)} manifest(s) validated, "
          f"{len(filings)} with filings, {len(manifests) - len(filings)} manifest-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
