#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Require every document generated from Clojure source to equal its committed file.

Runs the generator (`clojure -M:generate`, src/rate_plans/gen.clj) into a
temporary directory and compares each generated document with the file at the
same path in this tree by dev/rdf_hash.py. The tree is the working tree, or the
staged tree when the pre-commit hook runs dev/check_all.py in its checkout of
the index.

The comparison covers every utility the generator writes a document for: each
corpus document under such a utility's directory must be generated, and each
generated document must be committed. A committed document the generator did
not write is MISSING, a generated one with no committed file is EXTRA, a hash
that cannot be computed is NOHASH, and differing hashes are DIFF. Each fails.

    python3 dev/check_generated.py           check
    python3 dev/check_generated.py --write   write into the working tree each
                                             generated document that is EXTRA
                                             or DIFF, then check

--write leaves a document whose RDF hash already equals the generated one as it
is, so formatting alone never churns a committed file.

Exit codes: 0 all equal, 1 a document differs, is missing or extra, or the
generator failed, 3 refused (the generator wrote nothing).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus  # noqa: E402
from rdf_hash import rdf_sha256  # noqa: E402

REPO = corpus.REPO


def generate(out: Path) -> list[str] | None:
    proc = subprocess.run(["clojure", "-M:generate", str(out)],
                          cwd=REPO, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout + proc.stderr)
        print(f"FAIL  the generator exited {proc.returncode}")
        return None
    return sorted(p.relative_to(out).as_posix() for p in out.rglob("*.jsonld"))


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
        generated = generate(out)
        if generated is None:
            return 1
        if not generated:
            print("refused: the generator wrote no document")
            return 3

        scope = sorted({corpus.utility_dir(REPO / g).relative_to(REPO).as_posix()
                        for g in generated})
        committed = sorted(p.relative_to(REPO).as_posix() for p in corpus.paths()
                           if any(p.relative_to(REPO).as_posix().startswith(s + "/")
                                  for s in scope))

        fail = 0
        for path in sorted(set(committed) - set(generated)):
            print(f"MISSING {path}")
            fail = 1
        same = 0
        for path in generated:
            mine, theirs = out / path, REPO / path
            want = hash_or_none(theirs) if theirs.exists() else None
            got = hash_or_none(mine)
            if write and got and want != got:
                theirs.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(mine, theirs)
                print(f"WROTE   {path}")
                want = hash_or_none(theirs)
            if not theirs.exists():
                print(f"EXTRA   {path}")
                fail = 1
            elif want is None or got is None:
                print(f"NOHASH  {path}")
                fail = 1
            elif want != got:
                print(f"DIFF    {path}")
                fail = 1
            else:
                same += 1

    print(f"{same} of {len(generated)} generated documents equal their committed "
          f"files by RDF hash; {len(committed)} committed under {', '.join(scope)}")
    return fail


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
