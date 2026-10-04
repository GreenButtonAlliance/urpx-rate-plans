#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Require every walker corpus.json lists to see the same corpus.

Each walker's CLI is run twice, with no arguments (the documents) and with
--all (every kind), and its output must equal dev/corpus.py's in-process answer
line for line. Two walkers that each read corpus.json can still disagree,
because glob semantics differ between pathlib, java.nio, git and bb; this is
where that shows.

A walker whose runtime is not installed is skipped and named. Fewer than two
walkers run means nothing was compared, which refuses rather than passes.

Exit codes: 0 all agree, 1 a walker disagrees or fails, 3 refused.
"""
from __future__ import annotations

import difflib
import shlex
import shutil
import subprocess
import sys

import corpus


def expected(args: list[str]) -> list[str]:
    rel = lambda p: p.relative_to(corpus.REPO).as_posix()
    if args == ["--all"]:
        lines = [f"{k}\t{rel(p)}" for k in corpus.LAYOUT["kinds"] for p in corpus.paths(k)]
    else:
        lines = [rel(p) for p in corpus.paths()]
    return sorted(lines)


def main() -> int:
    docs = expected([])
    corpus.require_nonempty(docs, "documents")
    ran, failed = 0, 0
    for w in corpus.LAYOUT["walkers"]:
        cmd = shlex.split(w["cli"])
        if shutil.which(cmd[0]) is None and not (corpus.REPO / cmd[0]).exists():
            print(f"SKIP  {w['language']:<9} {cmd[0]} not found")
            continue
        ran += 1
        ok = True
        for args in ([], ["--all"]):
            proc = subprocess.run(cmd + args, cwd=corpus.REPO, capture_output=True, text=True)
            want = expected(args)
            got = proc.stdout.splitlines()
            if proc.returncode != 0 or got != want:
                ok = False
                print(f"FAIL  {w['language']:<9} {' '.join(cmd + args)} (exit {proc.returncode})")
                sys.stdout.writelines(difflib.unified_diff(
                    [l + "\n" for l in want], [l + "\n" for l in got],
                    "dev/corpus.py", w["language"], n=0))
                if proc.stderr:
                    print(proc.stderr.rstrip())
        if ok:
            print(f"OK    {w['language']:<9} {len(docs)} documents, {len(expected(['--all']))} files over all kinds")
        else:
            failed += 1
    if ran < 2:
        print(f"refused: {ran} walker(s) ran, nothing was compared")
        return 3
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
