#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Compare exported filings with what urpx-data-sandbox now holds.

For every filing whose tariff.toml carries a [[sandbox]] record (LAYOUT.md
§4.5), each recorded document is hashed three ways with dev/rdf_hash.py: the
sandbox's current copy, this tree's copy, and the hash recorded at export. Each
document is reported as one of:

  unchanged             all three agree
  changed in sandbox    the sandbox copy differs from the record: it was edited
                        there; review it and fold the change in here
  changed here          this tree differs from the record: re-export
  changed in both       both differ from the record
  missing in sandbox    the sandbox has no file at the recorded path
  missing here          this tree has no file of that name
  skipped               the sandbox could not be reached; named, never passed

The sandbox copy comes from a local checkout when --sandbox or
URPX_SANDBOX_CHECKOUT names one (its working tree is read, so keep it at main),
and otherwise from `gh api repos/<repo>/contents/<path>?ref=<ref>`.

Usage:
  python3 dev/check_sandbox_drift.py [--sandbox DIR] [--repo OWNER/NAME]
      [--ref REF] [--root DIR]

  --root  read manifests under DIR instead of this repository (for tests)

Exit codes:
  0  no sandbox records, or every document unchanged
  1  a document changed or is missing, on either side
  3  refused: no manifests found, or a document was skipped because the
     sandbox could not be reached and nothing drifted among those checked
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus  # noqa: E402
from rdf_hash import rdf_sha256, rdf_sha256_text  # noqa: E402

DEFAULT_REPO = "urpx-org/urpx-data-sandbox"
DEFAULT_REF = "main"
GH_TIMEOUT = 30

UNCHANGED = "unchanged"
CHANGED_SANDBOX = "changed in sandbox"
CHANGED_HERE = "changed here"
CHANGED_BOTH = "changed in both"
MISSING_SANDBOX = "missing in sandbox"
MISSING_HERE = "missing here"
SKIPPED = "skipped"
DRIFT = {CHANGED_SANDBOX, CHANGED_HERE, CHANGED_BOTH, MISSING_SANDBOX, MISSING_HERE}


class Missing(Exception):
    pass


class Unreachable(Exception):
    pass


class LocalSandbox:
    def __init__(self, root: Path):
        self.root = root

    def describe(self) -> str:
        r = subprocess.run(["git", "-C", str(self.root), "log", "-1", "--format=%h %D"],
                           capture_output=True, text=True)
        where = r.stdout.strip() if r.returncode == 0 else "not a git checkout"
        return f"local checkout {self.root} ({where})"

    def read(self, rel: str) -> str:
        p = self.root / rel
        if not p.is_file():
            raise Missing(rel)
        return p.read_text(encoding="utf-8")


class GitHubSandbox:
    def __init__(self, repo: str, ref: str):
        self.repo, self.ref = repo, ref

    def describe(self) -> str:
        return f"{self.repo} at {self.ref}, via gh api"

    def read(self, rel: str) -> str:
        gh = shutil.which("gh")
        if gh is None:
            raise Unreachable("gh is not on PATH")
        try:
            r = subprocess.run(
                [gh, "api", "-H", "Accept: application/vnd.github.raw+json",
                 f"repos/{self.repo}/contents/{rel}?ref={self.ref}"],
                capture_output=True, text=True, timeout=GH_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise Unreachable(f"gh api timed out after {GH_TIMEOUT}s")
        if r.returncode == 0:
            return r.stdout
        if "HTTP 404" in r.stderr:
            raise Missing(rel)
        raise Unreachable((r.stderr.strip().splitlines() or ["gh api failed"])[-1])


@dataclass
class Row:
    manifest: Path
    sandbox_path: str
    document: str
    state: str
    detail: str = ""


def manifests(root: Path | None) -> list[Path]:
    if root is None:
        return corpus.tariff_tomls()
    out: set[Path] = set()
    for pattern in corpus.LAYOUT["kinds"]["tariff-manifest"]["include"]:
        for country in corpus.COUNTRY_ROOTS:
            out.update((root / country).glob(pattern))
    return sorted(out)


def classify(recorded: str, sandbox: str | None, here: str | None) -> str:
    if sandbox is None:
        return MISSING_SANDBOX
    if here is None:
        return MISSING_HERE
    s, h = sandbox != recorded, here != recorded
    return CHANGED_BOTH if s and h else CHANGED_SANDBOX if s else CHANGED_HERE if h else UNCHANGED


def check(manifest_paths: list[Path], source) -> list[Row]:
    rows: list[Row] = []
    for m in manifest_paths:
        records = corpus.load_toml(m).get("sandbox", [])
        for rec in records:
            for doc, recorded in sorted(rec["rdf_sha256"].items()):
                rel = f"{rec['path']}/{doc}"
                local = m.parent / doc
                here = rdf_sha256(local) if local.is_file() else None
                try:
                    sandbox = rdf_sha256_text(source.read(rel))
                    detail = ""
                except Missing:
                    sandbox, detail = None, ""
                except Unreachable as e:
                    rows.append(Row(m, rec["path"], doc, SKIPPED, str(e)))
                    continue
                except Exception as e:  # present but not parseable as JSON-LD
                    sandbox, detail = "unparseable", f"sandbox copy does not parse: {e}"
                state = classify(recorded, sandbox, here)
                if not detail and state != UNCHANGED:
                    detail = (f"recorded {recorded[:12]}, sandbox {(sandbox or '-')[:12]}, "
                              f"here {(here or '-')[:12]}")
                rows.append(Row(m, rec["path"], doc, state, detail))
    return rows


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sandbox", type=Path, default=os.environ.get("URPX_SANDBOX_CHECKOUT") or None)
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--ref", default=DEFAULT_REF)
    ap.add_argument("--root", type=Path)
    args = ap.parse_args(argv)

    root = args.root.resolve() if args.root else corpus.REPO
    paths = manifests(args.root.resolve() if args.root else None)
    if not paths:
        print(f"check_sandbox_drift: no tariff.toml manifests under {root}; refusing",
              file=sys.stderr)
        return 3
    with_records = [m for m in paths if corpus.load_toml(m).get("sandbox")]
    if not with_records:
        print(f"no sandbox records in {len(paths)} manifests; nothing to check")
        return 0

    if args.sandbox:
        sandbox_root = Path(args.sandbox).expanduser().resolve()
        if not sandbox_root.is_dir():
            print(f"check_sandbox_drift: {sandbox_root} is not a directory", file=sys.stderr)
            return 3
        source = LocalSandbox(sandbox_root)
    else:
        source = GitHubSandbox(args.repo, args.ref)
    print(f"Sandbox: {source.describe()}")

    rows = check(with_records, source)
    width = max(len(r.state) for r in rows)
    current = None
    for r in rows:
        key = (r.manifest, r.sandbox_path)
        if key != current:
            print(f"{r.manifest.parent.relative_to(root)} -> {r.sandbox_path}")
            current = key
        print(f"  {r.state:<{width}}  {r.document}" + (f"  ({r.detail})" if r.detail else ""))

    counts: dict[str, int] = {}
    for r in rows:
        counts[r.state] = counts.get(r.state, 0) + 1
    print("Summary: " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())))
    if any(r.state in DRIFT for r in rows):
        return 1
    if any(r.state == SKIPPED for r in rows):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
