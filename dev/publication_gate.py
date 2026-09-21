#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Publication-readiness gate: is this corpus fit to be made public?

Ten checks are defined (see the URPXT-pubgate issue). Six are mechanical and
enforced here. Four depend on facts no script can establish, and those are
printed as UNCHECKED rather than silently passing, because a gate that reports
success over checks it never ran is worse than no gate.

THE GATE DOES NOT HANG ON ANY OF THESE. It hangs on urpx-org/urpx flipping from
INTERNAL to PUBLIC. Until then 124 outbound references 404 for an anonymous
reader, and this repository's own validator cannot obtain its shapes, because
dev/validate-with-base.py deliberately does not vendor them.

Exit: 0 all mechanical checks pass, 1 at least one fails.
Run: python3 dev/publication_gate.py
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"\n        {detail}" if detail else ""))


def tracked(*patterns: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", *patterns],
                         capture_output=True, text=True, check=True).stdout.split()
    return out


# --- 1 -----------------------------------------------------------------------
def check_gate() -> None:
    r = subprocess.run(["python3", "dev/validate-with-base.py", "--check-baseline"],
                       cwd=REPO, capture_output=True, text=True)
    at_baseline = r.returncode == 0
    # Residual violations must be traceable to a NAMED deferred decision, not
    # merely tolerated. LAYOUT.md is where those are recorded.
    layout = (REPO / "LAYOUT.md").read_text(encoding="utf-8")
    documented = "cross-filing" in layout.lower() or "@id reuse" in layout.lower()
    check("1. corpus at recorded baseline", at_baseline,
          "" if at_baseline else "dev/validate-with-base.py --check-baseline is not clean")
    check("1b. residual violations documented in LAYOUT.md", documented,
          "" if documented else "LAYOUT.md does not explain the accepted cross-filing @id reuse")


# --- 2 -----------------------------------------------------------------------
def check_reuse() -> None:
    r = subprocess.run(["reuse", "lint"], cwd=REPO, capture_output=True, text=True)
    check("2. reuse lint exits 0", r.returncode == 0,
          "" if r.returncode == 0 else r.stdout.strip().splitlines()[-1] if r.stdout else "reuse failed")


# --- 3 -----------------------------------------------------------------------
# The boundary is load-bearing. A naive URPX-\w+ matches ordinary English after
# "URPX-" (URPX-team, URPX-native, URPX-style) and can never pass, because
# REUSE.toml legitimately reads "URPX-team-authored".
BEADS_ID = re.compile(r'(URPXT|URPX)-[0-9a-z]{3}([^0-9a-z-]|$)')


def check_beads_ids() -> None:
    hits: list[str] = []
    for f in tracked():
        p = REPO / f
        if not p.is_file() or p.suffix in (".pdf", ".png", ".jpg", ".svg"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if BEADS_ID.search(line):
                hits.append(f"{f}:{i}")
    check("3. zero private beads ids in shipped content", not hits,
          "" if not hits else f"{len(hits)} occurrence(s), e.g. " + ", ".join(hits[:3]))


# --- 4 -----------------------------------------------------------------------
SHADOW = re.compile(r'shadow-repo[/\w.-]*|shadow-repo/urpx-tariffs|/shadow-repo/')


def check_shadow_refs() -> None:
    hits: list[str] = []
    for f in tracked():
        p = REPO / f
        # This file names the pattern it searches for, so it always matches itself.
        if f == "dev/publication_gate.py":
            continue
        if not p.is_file() or p.suffix in (".pdf", ".png", ".jpg", ".svg"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if SHADOW.search(line):
                hits.append(f"{f}:{i}")
    check("4. zero shadow-repo path references", not hits,
          "" if not hits else f"{len(hits)} occurrence(s), e.g. " + ", ".join(hits[:3])
          + ". scripts/ is the reserved landing spot if they are to be published.")


# --- 5 -----------------------------------------------------------------------
def check_example_com() -> None:
    hits = [f for f in tracked("*.jsonld", "*.toml", "*.md", "*.json")
            if "example.com" in (REPO / f).read_text(encoding="utf-8", errors="ignore")]
    check("5. zero example.com IRIs", not hits,
          "" if not hits else f"{len(hits)} file(s), e.g. " + ", ".join(hits[:3]))


# --- 5b ----------------------------------------------------------------------
def check_source_urls() -> None:
    """Every source URL a reader could follow must be fetchable by them.

    Same class as example.com: a URL that means something only on one machine.
    Eleven urpx:url values across five filings pointed at
    `file://./assets/<NAME>.pdf`, none of which existed anywhere in the corpus,
    and `file://./` is not a well-formed absolute URI in any case, since file://
    takes an authority. They shipped for months because nothing looked.
    """
    bad: list[str] = []
    for f in tracked("*.jsonld"):
        doc = json.loads((REPO / f).read_text(encoding="utf-8"))

        def walk(node, _f=f):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == "@context":
                        continue
                    if k in ("urpx:url", "urpx:accessURL") and isinstance(v, str):
                        if not v.startswith("https://"):
                            bad.append(f"{_f}: {k} = {v[:60]}")
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(doc)
    check("5b. every source URL is https", not bad,
          "" if not bad else f"{len(bad)} occurrence(s), e.g. " + "; ".join(bad[:3]))


# --- 6 -----------------------------------------------------------------------
def check_provenance() -> None:
    import tomli
    declared: set[str] = set()
    for t in corpus.tariff_tomls():
        for m in re.finditer(r'sha256\s*=\s*"([0-9a-f]{64})"', t.read_text(encoding="utf-8")):
            declared.add(m.group(1))
    pdfs = tracked("*.pdf")
    unmatched = []
    for f in pdfs:
        h = hashlib.sha256((REPO / f).read_bytes()).hexdigest()
        if h not in declared:
            unmatched.append(f)
    check("6. every tracked PDF matches a declared sha256", not unmatched,
          f"{len(pdfs)} PDFs, {len(declared)} distinct declared hashes"
          + ("" if not unmatched else f"; UNMATCHED: {', '.join(unmatched[:3])}"))


# --- 7 to 10 ------------------------------------------------------------------
UNCHECKED = [
    ("7. third-party github.com links resolve unauthenticated",
     "Needs network and an anonymous identity. Self-links cannot resolve until this gate fires."),
    ("8. rename complete across GitHub, local, shadow, Gitea, and BOTH consumers re-pinned",
     "No cross-tracker dependency edge exists for the clj-price-server side; verify by hand."),
    ("9. LAYOUT.md states the @context is vendored if the namespace does not dereference",
     "Judgement call, and only required if upstream ships without a resolving namespace."),
    ("10. content decisions settled: PDF copyright position, code-vs-data split, "
     "shadow-script publish-or-strip, the 2026-04 usage report",
     "Owner decisions. A script cannot tell whether they were made."),
]


def main() -> int:
    print("Publication-readiness gate\n")
    print("MECHANICAL CHECKS")
    check_gate()
    check_reuse()
    check_beads_ids()
    check_shadow_refs()
    check_example_com()
    check_source_urls()
    check_provenance()

    print("\nNOT CHECKED HERE (printed, never silently passed)")
    for name, why in UNCHECKED:
        print(f"  ----  {name}\n        {why}")

    failed = [n for n, ok, _ in results if not ok]
    print()
    print("THE GATE ALSO HANGS ON THREE UPSTREAM EVENTS, none of them ours:")
    print("  (a) urpx-org/urpx PR #60 merged and v0.5.1 tagged, firing the license transition")
    print("  (b) urpx-org/urpx flipping INTERNAL to PUBLIC. This is the real blocker.")
    print("  (c) a dereferencing URPX namespace, or a recorded decision to ship without one")
    print()
    if failed:
        print(f"{len(failed)} mechanical check(s) failed: {', '.join(failed)}")
        return 1
    print(f"all {len(results)} mechanical checks pass; 4 remain unchecked by design")
    return 0


if __name__ == "__main__":
    sys.exit(main())
