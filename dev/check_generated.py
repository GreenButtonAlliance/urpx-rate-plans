#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
"""Require every document generated from Clojure source to state the same RDF as its committed file.

Runs the generator (`clojure -M:generate`, src/rate_plans/gen.clj) into a
temporary directory and compares each generated document with the file at the
same path in this tree. On a byte mismatch dev/rdf_hash.py names the reason:
DIFF when the RDF differs, a regression; FORMAT when only the bytes do, which is
drift that `--write` fixes. The tree is the working tree, or the
staged tree when the pre-commit hook runs dev/check_all.py in its checkout of
the index.

A filing whose documents are generated says so in the [generation] table of its
tariff.toml (doc/dsl-corpus-generation.md), and the check holds that record to
the source in both directions. Every committed document in a filing with
[generation] must be generated, and every generated document must be committed
in a filing whose [generation] names the `:document` var that wrote it as an
entry. Every path in its sources must exist, and must include the file of each
entry's namespace. The generator also names each file a document read through
rate-plans.prose (its prose files and its filing's tariff.toml): every such
file must be in its filing's sources, every source that is not Clojure must be
read by a document in its filing, and every prose file (the corpus.json kind
clojure-prose) must be read by some document. A committed document the
generator did not write is MISSING, a generated one with no committed file is
EXTRA, one whose filing records no [generation] or not its entry is
UNRECORDED, an entry that wrote nothing in its filing is STALE, as is a source
no document there reads, a source path that does not exist or omits an entry's
namespace or a file a document read is NOSOURCE, a prose file no document reads
is UNREAD, a hash that cannot be computed is NOHASH, differing hashes are DIFF,
and equal hashes over differing bytes are FORMAT. FORMAT is drift; each of the
others fails.

    python3 dev/check_generated.py           check
    python3 dev/check_generated.py --write   write into the working tree each
                                             generated document whose bytes
                                             differ, then check

Exit codes: 0 all byte-identical, 1 a document's RDF differs, a document is missing
or extra, or the generator failed, 2 drift (every difference is FORMAT), 3 refused
(the generator wrote nothing).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus  # noqa: E402
from rdf_hash import rdf_sha256  # noqa: E402

REPO = corpus.REPO


class Generated(NamedTuple):
    var: str
    reads: tuple[str, ...]


def generate(out: Path) -> dict[str, Generated] | None:
    """{path relative to `out`: the `:document` var that wrote it and the files
    it read}, from the generator's "<path> <var> <read>..." lines."""
    proc = subprocess.run(["clojure", "-M:generate", str(out)],
                          cwd=REPO, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout + proc.stderr)
        print(f"FAIL  the generator exited {proc.returncode}")
        return None
    by_path = {}
    for line in proc.stdout.splitlines():
        if line.strip():
            path, var, *reads = line.split()
            by_path[path] = Generated(var, tuple(reads))
    return by_path


def generation_tables() -> dict[str, dict]:
    """{filing directory, relative to the repository: its [generation] table}
    for every filing generated from Clojure source."""
    tables = {}
    for toml in corpus.tariff_tomls():
        g = corpus.load_toml(toml).get("generation")
        if g is not None and g.get("generator") == "urpx.dsl":
            tables[toml.parent.relative_to(REPO).as_posix()] = g
    return tables


def entries(table: dict) -> list[str]:
    e = table.get("entry", [])
    return [e] if isinstance(e, str) else list(e)


def namespace_file(var: str) -> str:
    """rate-plans.us.ca.pge.e-tou-c/e-tou-c -> src/rate_plans/us/ca/pge/e_tou_c.clj."""
    ns = var.split("/", 1)[0]
    return "src/" + ns.replace("-", "_").replace(".", "/") + ".clj"


def check_records(generated: dict[str, Generated], tables: dict[str, dict]) -> int:
    """The two directions between [generation] and the source; 1 on a failure."""
    fail = 0
    for filing, table in sorted(tables.items()):
        sources = table.get("sources", [])
        for src in sources:
            if not (REPO / src).is_file():
                print(f"NOSOURCE {filing}: {src}")
                fail = 1
        here = [g for path, g in generated.items() if str(Path(path).parent) == filing]
        written = {g.var for g in here}
        read = {r for g in here for r in g.reads}
        for r in sorted(read - set(sources)):
            print(f"NOSOURCE {filing}: sources omit {r}, which a document here reads")
            fail = 1
        for src in sources:
            if not src.endswith(".clj") and src not in read:
                print(f"STALE   {filing}: no document here reads {src}")
                fail = 1
        for var in entries(table):
            if var not in written:
                print(f"STALE   {filing}: {var} writes no document here")
                fail = 1
            if namespace_file(var) not in sources:
                print(f"NOSOURCE {filing}: sources omit {namespace_file(var)}, the file of {var}")
                fail = 1
    for path, g in sorted(generated.items()):
        table = tables.get(str(Path(path).parent))
        if table is None or g.var not in entries(table):
            print(f"UNRECORDED {path}: its filing's [generation] does not name {g.var}")
            fail = 1
    read = {r for g in generated.values() for r in g.reads}
    for p in corpus.paths("clojure-prose"):
        rel = p.relative_to(REPO).as_posix()
        if rel not in read:
            print(f"UNREAD  {rel}: no generated document reads it")
            fail = 1
    return fail


def same_bytes(a: Path, b: Path) -> bool:
    return a.read_bytes() == b.read_bytes()


def hash_or_none(path: Path) -> str | None:
    try:
        return rdf_sha256(path) or None
    except Exception as e:  # any parse failure is a NOHASH, reported below
        print(f"  {path}: {type(e).__name__}: {e}")
        return None


def main(argv: list[str]) -> int:
    write = argv == ["--write"]
    if argv and not write:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 3
    with tempfile.TemporaryDirectory(prefix="check-generated.") as tmp:
        out = Path(tmp)
        by_var = generate(out)
        if by_var is None:
            return 1
        if not by_var:
            print("refused: the generator wrote no document")
            return 3
        generated = sorted(by_var)

        tables = generation_tables()
        committed = sorted(p.relative_to(REPO).as_posix() for p in corpus.paths()
                           if p.parent.relative_to(REPO).as_posix() in tables)

        fail = check_records(by_var, tables)
        for path in sorted(set(committed) - set(generated)):
            print(f"MISSING {path}")
            fail = 1
        same = 0
        drift = 0
        for path in generated:
            mine, theirs = out / path, REPO / path
            if write and not (theirs.exists() and same_bytes(mine, theirs)):
                theirs.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(mine, theirs)
                print(f"WROTE   {path}")
            if not theirs.exists():
                print(f"EXTRA   {path}")
                fail = 1
            elif same_bytes(mine, theirs):
                same += 1
            else:
                want, got = hash_or_none(theirs), hash_or_none(mine)
                if want is None or got is None:
                    print(f"NOHASH  {path}")
                    fail = 1
                elif want != got:
                    print(f"DIFF    {path}")
                    fail = 1
                else:
                    print(f"FORMAT  {path}")
                    drift = 2

    print(f"{same} of {len(generated)} generated documents equal their committed "
          f"files byte for byte; {len(committed)} committed in the {len(tables)} "
          f"filings that record [generation]")
    return fail or drift


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
