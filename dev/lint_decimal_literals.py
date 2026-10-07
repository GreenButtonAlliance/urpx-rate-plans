#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Fail a literal typed with an XSD numeric datatype whose lexical form is not
in that datatype's lexical space (XML Schema 1.1 Part 2, section 3.3).

xsd:decimal has no exponent form: "-9e-05"^^xsd:decimal is ill-typed, and SHACL
sh:datatype must report it. rdflib rewrites such a literal to a canonical form
while parsing, so pyshacl, dev/rdf_hash.py and every other check here that goes
through rdflib cannot see one. This lint reads the raw JSON instead.

A literal's datatype comes from one of two places:

  - an explicit value object, {"@value": "...", "@type": "xsd:decimal"};
  - the @context, when the property's term definition coerces it, e.g.
    "urpx:unitPrice": {"@type": "xsd:decimal"}. A term is looked up by the key
    as written, as JSON-LD does, and embedded and property-scoped contexts are
    applied where they occur.

A native JSON number under a numeric coercion is judged by the lexical form
JSON-LD gives it: an integral number becomes its digits, any other number the
canonical xsd:double form (with an exponent), which no xsd:decimal or integer
type admits. A native number with no coercion becomes xsd:integer or xsd:double
and is always well typed.

Lexical spaces checked (sign is "+" or "-"):
  decimal          optional sign, digits with an optional fraction, or a fraction
                   alone: 1, -1.50, +.5, 5.
  integer types    optional sign and digits, within the type's value range
                   (nonNegativeInteger, long, unsignedByte and the rest)
  float, double    the decimal form with an optional exponent, or INF, +INF,
                   -INF, NaN
No lexical space admits leading or trailing whitespace.

Exit codes: 0 clean, 1 an ill-typed literal, 3 the harness could not answer.

Usage:
    python3 dev/lint_decimal_literals.py [--verbose] [--file JSONLD ...]

--file checks the named documents instead of the corpus;
dev/test_decimal_literals.py uses it on fixtures.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

XSD = "http://www.w3.org/2001/XMLSchema#"

_DECIMAL = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
DECIMAL = re.compile(_DECIMAL)
INTEGER = re.compile(r"[+-]?[0-9]+")
FLOAT = re.compile(rf"{_DECIMAL}(?:[eE][+-]?[0-9]+)?|[+-]?INF|NaN")

# Integer types: (minimum, maximum), None for unbounded.
INTEGER_RANGES = {
    "integer": (None, None),
    "nonPositiveInteger": (None, 0),
    "negativeInteger": (None, -1),
    "nonNegativeInteger": (0, None),
    "positiveInteger": (1, None),
    "long": (-2**63, 2**63 - 1),
    "int": (-2**31, 2**31 - 1),
    "short": (-2**15, 2**15 - 1),
    "byte": (-2**7, 2**7 - 1),
    "unsignedLong": (0, 2**64 - 1),
    "unsignedInt": (0, 2**32 - 1),
    "unsignedShort": (0, 2**16 - 1),
    "unsignedByte": (0, 2**8 - 1),
}
NUMERIC = {"decimal", "float", "double", *INTEGER_RANGES}


class Refused(Exception):
    pass


class Native:
    """A JSON number as written, so a coerced one can be judged as JSON-LD
    would convert it."""

    def __init__(self, text: str):
        self.text = text

    def lexical(self) -> str:
        v = float(self.text)
        if v.is_integer() and abs(v) < 1e21:
            return str(int(v))
        m, e = f"{Decimal(repr(v)).normalize():E}".split("E")
        return f"{m if '.' in m else m + '.0'}E{int(e)}"


def load(path: Path):
    return json.loads(path.read_text(), parse_float=Native, parse_int=Native)


def ill_typed(lexical: str, local: str) -> str | None:
    """Why `lexical` is not in xsd:`local`'s lexical space, or None."""
    if local == "decimal":
        if not DECIMAL.fullmatch(lexical):
            return "not an xsd:decimal lexical form (no exponent, no whitespace)"
    elif local in ("float", "double"):
        if not FLOAT.fullmatch(lexical):
            return f"not an xsd:{local} lexical form"
    else:
        if not INTEGER.fullmatch(lexical):
            return f"not an xsd:{local} lexical form (digits only)"
        lo, hi = INTEGER_RANGES[local]
        n = int(lexical)
        if (lo is not None and n < lo) or (hi is not None and n > hi):
            return f"outside the value space of xsd:{local}"
    return None


class Context:
    """The parts of a JSON-LD active context this lint needs: term definitions
    and the IRIs they expand to."""

    def __init__(self, terms: dict | None = None):
        self.terms = dict(terms or {})

    def merged(self, local) -> "Context":
        out = Context(self.terms)
        for c in local if isinstance(local, list) else [local]:
            if c is None:
                out = Context()
            elif isinstance(c, dict):
                for k, v in c.items():
                    if not k.startswith("@"):
                        out.terms[k] = v
            else:
                raise Refused(f"a remote @context ({c!r}) cannot be read; this lint reads inline "
                              "contexts only")
        return out

    def expand(self, s: str) -> str:
        d = self.terms.get(s)
        if isinstance(d, str):
            return self.expand(d) if d != s else d
        if isinstance(d, dict) and isinstance(d.get("@id"), str) and d["@id"] != s:
            return self.expand(d["@id"])
        if ":" in s:
            prefix, suffix = s.split(":", 1)
            if not suffix.startswith("//"):
                p = self.terms.get(prefix)
                if isinstance(p, dict):
                    p = p.get("@id")
                if isinstance(p, str):
                    return p + suffix
        return s

    def coercion(self, key: str) -> str | None:
        d = self.terms.get(key)
        if isinstance(d, dict) and isinstance(d.get("@type"), str) and not d["@type"].startswith("@"):
            return self.expand(d["@type"])
        return None

    def scoped(self, key: str) -> "Context":
        d = self.terms.get(key)
        if isinstance(d, dict) and "@context" in d:
            return self.merged(d["@context"])
        return self


def numeric_local(iri: str | None) -> str | None:
    if iri and iri.startswith(XSD) and iri[len(XSD):] in NUMERIC:
        return iri[len(XSD):]
    return None


def scan(doc, rel: str) -> tuple[int, list[dict]]:
    """(numeric literals seen, findings) for one document."""
    seen = 0
    findings: list[dict] = []

    def judge(lexical: str, local: str, where: str, how: str) -> None:
        nonlocal seen
        seen += 1
        why = ill_typed(lexical, local)
        if why:
            findings.append({"file": rel, "where": where, "lexical": lexical,
                             "datatype": f"xsd:{local}", "how": how, "why": why})

    def value(v, ctx: Context, coerced: str | None, where: str) -> None:
        if isinstance(v, list):
            for x in v:
                value(x, ctx, coerced, where)
        elif isinstance(v, dict):
            if "@context" in v:
                ctx = ctx.merged(v["@context"])
            if "@value" in v:
                t = v.get("@type")
                local = numeric_local(ctx.expand(t)) if isinstance(t, str) else None
                if local:
                    x = v["@value"]
                    judge(x.lexical() if isinstance(x, Native) else
                          json.dumps(x) if isinstance(x, bool) else str(x),
                          local, where, "explicit @type")
            elif "@list" in v or "@set" in v:
                value(v.get("@list", v.get("@set")), ctx, coerced, where)
            else:
                node(v, ctx)
        elif coerced:
            local = numeric_local(coerced)
            if local:
                lexical = (v.lexical() if isinstance(v, Native) else
                           json.dumps(v) if isinstance(v, bool) else v)
                if isinstance(lexical, str):
                    judge(lexical, local, where, "@context coercion")

    def node(n: dict, ctx: Context) -> None:
        if "@context" in n:
            ctx = ctx.merged(n["@context"])
        nid = n.get("@id", "(no @id)")
        for k, v in n.items():
            if k in ("@context", "@id", "@type", "@value", "@language", "@direction", "@index"):
                continue
            if k in ("@graph", "@included", "@nest", "@reverse"):
                value(v, ctx, None, f"{nid} {k}")
                continue
            value(v, ctx.scoped(k), ctx.coercion(k), f"{nid} {k}")

    value(doc, Context(), None, "(document)")
    return seen, findings


def documents() -> list[Path]:
    """Every filing, and every JSON-LD report generated from them."""
    reports = sorted((REPO / "reports").glob("*.jsonld"))
    return corpus.all_filing_jsonld() + reports


def run(paths: list[Path], whole_corpus: bool = True) -> dict:
    if not paths:
        raise Refused("no JSON-LD documents to check")
    seen = 0
    findings: list[dict] = []
    for p in paths:
        rel = str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p)
        try:
            doc = load(p)
        except (OSError, ValueError) as e:
            raise Refused(f"{rel}: {e}")
        s, f = scan(doc, rel)
        seen += s
        findings += f
    if whole_corpus and not seen:
        raise Refused("no XSD-numeric literal anywhere in the corpus, so the check compared "
                      "nothing; the walk has probably broken")
    return {"documents": len(paths), "seen": seen, "findings": findings}


def report(r: dict, verbose: bool, limit: int = 10) -> int:
    by_file: dict[str, list[dict]] = {}
    for f in r["findings"]:
        by_file.setdefault(f["file"], []).append(f)
    for rel, fs in sorted(by_file.items()):
        print(f"ILL-TYPED  {rel}: {len(fs)} literal(s)", file=sys.stderr)
        for f in fs if verbose else fs[:limit]:
            print(f"  {f['where']}: \"{f['lexical']}\" as {f['datatype']} ({f['how']}): {f['why']}",
                  file=sys.stderr)
        if not verbose and len(fs) > limit:
            print(f"  ... {len(fs) - limit} more; --verbose lists them all", file=sys.stderr)
    bad = len(r["findings"])
    print(f"numeric literals: {bad} ill-typed in {len(by_file)} document(s), over {r['seen']} "
          f"XSD-numeric literals in {r['documents']} documents",
          file=sys.stderr if bad else sys.stdout)
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--file", nargs="+", type=Path, help="check these documents instead of the corpus")
    args = ap.parse_args(argv)
    try:
        r = (run([p.resolve() for p in args.file], whole_corpus=False) if args.file
             else run(documents()))
    except (Refused, SystemExit) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3
    return report(r, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
