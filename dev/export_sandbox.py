#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Export filings to a urpx-org/urpx-data-sandbox submission directory.

This repository stays the source of truth; a sandbox submission is an export of
it. Given filing directories (or a schedule directory, meaning every version
under it) and a sandbox checkout, this writes one submission directory holding:

  - every JSON-LD document of each filing, byte for byte;
  - each filing's vendored source PDF, matched to tariff.toml by sha256 (a
    [source] entry with vendored = false is listed in the README, not copied);
  - a README.md carrying what the sandbox's submission template asks for,
    derived from tariff.toml, utility.toml and the JSON-LD, plus the
    disclaimer link.

With --pr-body FILE it also writes the sandbox's pull request template, filled
in. With --record it appends a [[sandbox]] record to each exported filing's
tariff.toml (LAYOUT.md §4.5); without it, the record is printed instead. The
record holds the canonical RDF hash of each document (dev/rdf_hash.py), which
dev/check_sandbox_drift.py later compares against the sandbox and this tree.

Layout (--layout):
  commodity   submissions/<country>/<country>-<subdivision>/<utility>/<commodity>/
              the sandbox's documented depth (the default)
  schedule    the same plus /<schedule>/, one directory per rate schedule

The target directory must be empty or hold only files this export writes;
--replace deletes it first.

Usage:
  python3 dev/export_sandbox.py --sandbox DIR [--layout commodity|schedule]
      [--pr-body FILE] [--record] [--replace] PATH...

  PATH is a filing directory (us/.../<schedule>/versions/<date>) or a schedule
  directory (us/.../<schedule>), whose every version is exported.

Exit codes: 0 exported, 2 usage or input error.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import Graph, Namespace, RDF

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus  # noqa: E402
from rdf_hash import BASE, rdf_sha256  # noqa: E402

REPO = corpus.REPO
URPX = Namespace("https://urpx.org/ns/ontology/")
COMMODITY = {"electricity": "electric", "gas": "gas"}
LAYOUTS = ("commodity", "schedule")
DOCUMENT_GLOBS = ("rate-plan_*.jsonld", "rate-plan-modifier_*.jsonld")
VERSION_PATTERN = re.compile(r"(?:^|/)v?(\d+\.\d+\.\d+)(?:/|$)")
README_COPYRIGHT = "2026 Clark Communications Corporation"
SANDBOX_BANNER = "# Sandbox ---------------------------------------------------------------------"

US_STATES = {
    "al": "Alabama", "ak": "Alaska", "az": "Arizona", "ar": "Arkansas",
    "ca": "California", "co": "Colorado", "ct": "Connecticut", "de": "Delaware",
    "dc": "District of Columbia", "fl": "Florida", "ga": "Georgia", "hi": "Hawaii",
    "id": "Idaho", "il": "Illinois", "in": "Indiana", "ia": "Iowa", "ks": "Kansas",
    "ky": "Kentucky", "la": "Louisiana", "me": "Maine", "md": "Maryland",
    "ma": "Massachusetts", "mi": "Michigan", "mn": "Minnesota", "ms": "Mississippi",
    "mo": "Missouri", "mt": "Montana", "ne": "Nebraska", "nv": "Nevada",
    "nh": "New Hampshire", "nj": "New Jersey", "nm": "New Mexico", "ny": "New York",
    "nc": "North Carolina", "nd": "North Dakota", "oh": "Ohio", "ok": "Oklahoma",
    "or": "Oregon", "pa": "Pennsylvania", "ri": "Rhode Island", "sc": "South Carolina",
    "sd": "South Dakota", "tn": "Tennessee", "tx": "Texas", "ut": "Utah",
    "vt": "Vermont", "va": "Virginia", "wa": "Washington", "wv": "West Virginia",
    "wi": "Wisconsin", "wy": "Wyoming",
}


class ExportError(Exception):
    pass


@dataclass
class Version:
    iri: str
    kind: str                       # RatePlanVersion | RatePlanModifierVersion
    effective: str
    expiration: str | None


@dataclass
class Document:
    path: Path
    declared: str                   # the targetURPXVersion IRI
    plan_names: list[tuple[str, str]]   # (class, urpx:name) of RatePlan/RatePlanModifier
    versions: list[Version]


@dataclass
class SourcePdf:
    path: Path | None  # None: cited with vendored = false, so not copied
    url: str
    sha256: str
    retrieved_on: str
    filing_id: str | None


@dataclass
class Filing:
    dir: Path
    country: str
    subdivision: str
    utility: str
    carrier: str
    schedule: str
    date: str
    manifest: dict
    documents: list[Document] = field(default_factory=list)
    pdfs: list[SourcePdf] = field(default_factory=list)


# --- reading -----------------------------------------------------------------

def parse_path(d: Path) -> tuple[str, str, str, str, str, str]:
    """(country, subdivision, utility, carrier, schedule, date) of a filing
    directory, anchored on the `versions` segment as corpus.parse_filing_path is,
    but for any path, so a copy outside the repository reads the same."""
    parts = d.resolve().parts
    if "versions" not in parts:
        raise ExportError(f"not a filing directory (no 'versions' segment): {d}")
    i = len(parts) - 1 - parts[::-1].index("versions")
    if i < 5 or i + 1 >= len(parts):
        raise ExportError(f"malformed filing path: {d}")
    return parts[i - 5], parts[i - 4], parts[i - 3], parts[i - 2], parts[i - 1], parts[i + 1]


def expand(paths: list[Path]) -> list[Path]:
    """Filing directories named by `paths`, each a filing or a schedule directory."""
    out: list[Path] = []
    for p in paths:
        p = p.resolve()
        if (p / corpus.TARIFF_MANIFEST).is_file():
            out.append(p)
        elif (p / "versions").is_dir():
            found = sorted(v for v in (p / "versions").iterdir()
                           if (v / corpus.TARIFF_MANIFEST).is_file())
            if not found:
                raise ExportError(f"{p}: no filing under versions/")
            out.extend(found)
        else:
            raise ExportError(f"{p}: neither a filing directory nor a schedule directory")
    seen: set[Path] = set()
    return [d for d in out if not (d in seen or seen.add(d))]


def _date(literal) -> str:
    s = str(literal)
    return s[:10] if s.endswith("T00:00:00") or len(s) == 10 else s


def read_document(path: Path) -> Document:
    g = Graph()
    g.parse(data=path.read_text(encoding="utf-8"), format="json-ld", publicID=BASE)
    declared = sorted({str(o) for o in g.objects(None, URPX.targetURPXVersion)})
    if len(declared) != 1:
        raise ExportError(f"{path.name}: expected one urpx:targetURPXVersion, found {declared}")
    names = []
    for cls in ("RatePlan", "RatePlanModifier"):
        for s in sorted(g.subjects(RDF.type, URPX[cls])):
            names.append((cls, str(g.value(s, URPX.name) or s)))
    versions = []
    for cls in ("RatePlanVersion", "RatePlanModifierVersion"):
        for s in sorted(g.subjects(RDF.type, URPX[cls])):
            eff = g.value(s, URPX.effectiveDateTime)
            if eff is None:
                continue
            exp = g.value(s, URPX.expirationDateTime)
            versions.append(Version(str(s), cls, _date(eff), _date(exp) if exp else None))
    return Document(path, declared[0], names, versions)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_entries(manifest: dict) -> list[dict]:
    """The [source] block as a list of per-document tables, either shape."""
    src = manifest["source"]
    if "url" in src:
        return [src]
    return [v for v in src.values() if isinstance(v, dict)]


def read_filing(d: Path) -> Filing:
    country, subdivision, utility, carrier, schedule, date = parse_path(d)
    manifest = corpus.load_toml(d / corpus.TARIFF_MANIFEST)
    f = Filing(d, country, subdivision, utility, carrier, schedule, date, manifest)
    docs = sorted({p for pat in DOCUMENT_GLOBS for p in d.glob(pat)})
    if not docs:
        raise ExportError(f"{d}: no JSON-LD document")
    f.documents = [read_document(p) for p in docs]
    by_hash = {sha256_file(p): p for p in d.glob("*.pdf")}
    for entry in source_entries(manifest):
        pdf = by_hash.get(entry["sha256"])
        if entry.get("vendored", True) is False:
            if pdf is not None:
                raise ExportError(f"{d}: source sha256 {entry['sha256'][:12]} is declared vendored = false, but a PDF in the filing matches it")
        elif pdf is None:
            raise ExportError(f"{d}: no vendored PDF matches source sha256 {entry['sha256'][:12]}")
        f.pdfs.append(SourcePdf(pdf, entry["url"], entry["sha256"], str(entry["retrieved_on"]),
                                entry.get("filing_id")))
    return f


def utility_record(filing: Filing) -> dict:
    path = filing.dir.parents[3] / corpus.UTILITY_MANIFEST
    if not path.is_file():
        raise ExportError(f"{path}: missing")
    return corpus.load_toml(path)


# --- the submission ----------------------------------------------------------

@dataclass
class Submission:
    filings: list[Filing]
    rel_path: str                   # relative to the sandbox root
    utility: dict
    declared: str
    version: str
    state: str
    iso: str
    schedules: list[str]


def plan(filings: list[Filing], layout: str) -> Submission:
    keys = {(f.country, f.subdivision, f.utility, f.carrier) for f in filings}
    if len(keys) != 1:
        raise ExportError(f"filings span more than one utility or commodity: {sorted(keys)}")
    country, subdivision, utility, carrier = keys.pop()
    if carrier not in COMMODITY:
        raise ExportError(f"no sandbox commodity for carrier {carrier!r}")
    schedules = sorted({f.schedule for f in filings})
    iso = f"{country}-{subdivision}"
    parts = ["submissions", country, iso, utility, COMMODITY[carrier]]
    if layout == "schedule":
        if len(schedules) != 1:
            raise ExportError(f"--layout schedule takes one schedule, given {schedules}")
        parts.append(schedules[0])
    declared = sorted({doc.declared for f in filings for doc in f.documents})
    if len(declared) != 1:
        raise ExportError(f"documents declare different URPX versions: {declared}")
    m = VERSION_PATTERN.search(declared[0])
    if not m:
        raise ExportError(f"targetURPXVersion {declared[0]!r} names no version")
    state = US_STATES.get(subdivision, subdivision.upper()) if country == "us" else subdivision.upper()
    return Submission(filings, "/".join(parts), utility_record(filings[0]), declared[0],
                      m.group(1), state, iso, schedules)


def files_of(sub: Submission) -> dict[str, Path]:
    """Every file the submission carries except its README, by sandbox name."""
    out: dict[str, Path] = {}
    for f in sub.filings:
        for p in [doc.path for doc in f.documents] + [pdf.path for pdf in f.pdfs if pdf.path]:
            # One source document vendored in several version directories, such
            # as PG&E Electric Rule 19, is the same bytes under the same name.
            if p.name in out and out[p.name] != p and out[p.name].read_bytes() != p.read_bytes():
                raise ExportError(f"two files would share the name {p.name}")
            if p.name in out:
                continue
            out[p.name] = p
    return out


def _version_line(v: Version) -> str:
    until = f"until {v.expiration}" if v.expiration else "no end date stated"
    return f"`{v.iri.rsplit('/', 1)[-1]}` from {v.effective}, {until}"


def readme(sub: Submission) -> str:
    u = sub.utility
    depth = sub.rel_path.count("/") + 1
    up = "../" * depth
    sched = ", ".join(s.upper() for s in sub.schedules)
    plan_names = sorted({n for f in sub.filings for d in f.documents
                         for cls, n in d.plan_names if cls == "RatePlan"})
    # REUSE-IgnoreStart
    lines = [
        f"<!-- SPDX-FileCopyrightText: {README_COPYRIGHT} -->",
        "<!-- SPDX-License-Identifier: Apache-2.0 -->",
        "",
        # REUSE-IgnoreEnd
        f"# {u['short_name']} {sched}",
        "",
    ]
    if plan_names:
        lines += [f"{'; '.join(plan_names)}: rate schedule {sched} of {u['legal_name']}, "
                  "as URPX JSON-LD.", ""]
    lines += [
        f"- **Utility:** {u['legal_name']} ({u['short_name']})",
        f"- **Jurisdiction:** {sub.state} (`{sub.iso}`)",
        f"- **Declared URPX version:** {sub.version} (`{sub.declared}`)",
        "- **Built from a real, published dataset:** yes. Each document is modeled "
        "from the utility's published tariff, vendored here as the source document.",
        "",
        "## Documents",
        "",
        "| Document | Effective date | Versions it carries (service period) |",
        "|---|---|---|",
    ]
    for f in sub.filings:
        for d in f.documents:
            vs = "<br>".join(_version_line(v) for v in d.versions) or "none"
            lines.append(f"| [`{d.path.name}`]({d.path.name}) | {f.date} | {vs} |")
    lines += [
        "",
        "## Source documents",
        "",
        "| File | Filing | Retrieved from | Capture date | SHA-256 |",
        "|---|---|---|---|---|",
    ]
    for f in sub.filings:
        for p in f.pdfs:
            cell = f"[`{p.path.name}`]({p.path.name})" if p.path else "cited, not included"
            lines.append(f"| {cell} | {p.filing_id or ''} | "
                         f"<{p.url}> | {p.retrieved_on} | `{p.sha256}` |")
    lines += [
        "",
        "## Disclaimer",
        "",
        "Nothing in this repository is reviewed for data content, completeness, or accuracy. "
        "A submission is checked for conformance to the URPX version it states it targets, "
        f"and for nothing else. See the [repository README]({up}README.md).",
        "",
    ]
    return "\n".join(lines)


def _effective_lines(sub: Submission) -> list[str]:
    out = []
    for f in sub.filings:
        fid = {p.filing_id for p in f.pdfs if p.filing_id}
        note = f" ({', '.join(sorted(fid))})" if fid else ""
        out.append(f"- {f.date}{note}: {', '.join(f'`{d.path.name}`' for d in f.documents)}")
    return out


def _service_lines(sub: Submission) -> list[str]:
    seen: dict[str, Version] = {}
    for f in sub.filings:
        for d in f.documents:
            for v in d.versions:
                seen.setdefault(v.iri, v)
    return [f"- {_version_line(v)}" for v in sorted(seen.values(), key=lambda v: (v.effective, v.iri))]


def pr_body(sub: Submission, template: str, layout: str) -> str:
    """The sandbox's pull request template with each field filled in."""
    u = sub.utility
    sources = [(f"- `{p.path.name}`, placed at `{sub.rel_path}/{p.path.name}`, retrieved from "
                f"<{p.url}> on {p.retrieved_on}") if p.path else
               f"- <{p.url}>, retrieved on {p.retrieved_on}, cited and not included"
               for f in sub.filings for p in f.pdfs]
    values = {
        "Utility:": [f"{u['legal_name']} ({u['short_name']})"],
        "Jurisdiction (utility and state):": [f"{u['legal_name']}, {sub.state} (`{sub.iso}`)"],
        "Source document reference:": sources,
        "Declared URPX version:": [f"{sub.version} (`{sub.declared}`)"],
        "Built from a real, published dataset?": [
            "yes. Each document is modeled from the utility's published tariff, vendored in "
            "this pull request."],
        "Effective dates:": _effective_lines(sub),
        "Service-period dates:": _service_lines(sub),
    }
    body = re.sub(r"<!--.*?-->\n?", "", template, flags=re.S).lstrip("\n")
    out: list[str] = []
    filled: set[str] = set()
    for line in body.splitlines():
        label = next((k for k in values if line.startswith(f"**{k}**")), None)
        if label is not None:
            v = values[label]
            if len(v) == 1 and not v[0].startswith("- "):
                out.append(f"**{label}** {v[0]}")
            else:
                out += [f"**{label}**", ""] + v
            filled.add(label)
            continue
        if line.startswith("- [ ] "):
            item = line[6:]
            checked = ("source document is vendored" in item
                       or "declares the URPX version" in item
                       or "This is a dataset submission" in item
                       or ("lives under" in item and layout == "commodity"))
            out.append(("- [x] " if checked else "- [ ] ") + item)
            continue
        out.append(line)
    missing = sorted(set(values) - filled)
    if missing:
        raise ExportError(f"the sandbox's pull request template no longer has the fields {missing}")
    return "\n".join(out).rstrip("\n") + "\n"


# --- the record --------------------------------------------------------------

def head_commit(repo: Path = REPO) -> str:
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise ExportError(f"{repo}: not a git checkout")
    return r.stdout.strip()


def uncommitted(paths: list[Path], repo: Path = REPO) -> list[str]:
    r = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--"]
                       + [str(p) for p in paths], capture_output=True, text=True)
    return [line[3:] for line in r.stdout.splitlines()]


def record_for(filing: Filing, rel_path: str, exported_from: str, today: str) -> dict:
    return {
        "path": rel_path,
        "exported_from": exported_from,
        "exported_on": today,
        "rdf_sha256": {d.path.name: rdf_sha256(d.path) for d in filing.documents},
    }


def _loads(text: str) -> dict:
    try:
        import tomllib
    except ModuleNotFoundError:            # Python < 3.11
        import tomli as tomllib
    return tomllib.loads(text)


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_records(records: list[dict]) -> str:
    out = [SANDBOX_BANNER,
           "# Written by dev/export_sandbox.py (LAYOUT.md §4.5). pr and merge_commit",
           "# are added by hand once the pull request exists and merges."]
    for r in records:
        out += ["[[sandbox]]",
                f"path          = {_toml_str(r['path'])}",
                f"exported_from = {_toml_str(r['exported_from'])}",
                f"exported_on   = {_toml_str(r['exported_on'])}"]
        if r.get("pr") is not None:
            out.append(f"pr            = {int(r['pr'])}")
        if r.get("merge_commit"):
            out.append(f"merge_commit  = {_toml_str(r['merge_commit'])}")
        out += ["", "  [sandbox.rdf_sha256]"]
        out += [f"  {_toml_str(k)} = {_toml_str(v)}" for k, v in sorted(r["rdf_sha256"].items())]
        out.append("")
    return "\n".join(out)


def write_record(manifest_path: Path, record: dict) -> None:
    """Add `record` to the manifest's [[sandbox]] records, replacing one with the
    same path. A replaced record keeps its pr, since a re-export updates the same
    pull request, and drops its merge_commit, since the new content is unmerged.

    The records live after SANDBOX_BANNER at the end of the file, which this
    rewrites whole; it refuses if anything else follows the banner."""
    text = manifest_path.read_text()
    original = corpus.load_toml(manifest_path)
    head, sep, _ = text.partition("\n" + SANDBOX_BANNER)
    head = head.rstrip("\n") + "\n"
    rest = _loads(head)
    if {k: v for k, v in original.items() if k != "sandbox"} != rest:
        raise ExportError(f"{manifest_path}: something other than [[sandbox]] follows the "
                          "sandbox banner, or [[sandbox]] sits elsewhere in the file")
    records = list(original.get("sandbox", []))
    for i, r in enumerate(records):
        if r["path"] == record["path"]:
            if "pr" in r:
                record = {**record, "pr": r["pr"]}
            records[i] = record
            break
    else:
        records.append(record)
    manifest_path.write_text(head + "\n" + render_records(records))


# --- driver ------------------------------------------------------------------

def export(paths: list[Path], sandbox: Path, layout: str = "commodity", *,
           replace: bool = False) -> Submission:
    """Write the submission directory; return what was written."""
    if layout not in LAYOUTS:
        raise ExportError(f"--layout must be one of {LAYOUTS}")
    if not (sandbox / "submissions").is_dir():
        raise ExportError(f"{sandbox}: no submissions/ directory; not a sandbox checkout")
    filings = sorted((read_filing(d) for d in expand(paths)), key=lambda f: (f.schedule, f.date))
    sub = plan(filings, layout)
    files = files_of(sub)
    target = sandbox / sub.rel_path
    if target.exists():
        foreign = sorted(p.name for p in target.iterdir() if p.name not in files and p.name != "README.md")
        if foreign and not replace:
            raise ExportError(f"{target} holds files this export does not write: {foreign}; "
                              "pass --replace to clear it first")
        if replace:
            shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for name, src in files.items():
        shutil.copyfile(src, target / name)
    (target / "README.md").write_text(readme(sub))
    return sub


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--sandbox", type=Path, required=True,
                    help="checkout of urpx-org/urpx-data-sandbox to export into")
    ap.add_argument("--layout", choices=LAYOUTS, default="commodity")
    ap.add_argument("--pr-body", type=Path, help="write the filled pull request template here")
    ap.add_argument("--record", action="store_true",
                    help="write the [[sandbox]] record into each filing's tariff.toml")
    ap.add_argument("--replace", action="store_true",
                    help="delete the target directory before writing")
    args = ap.parse_args(argv)

    try:
        sub = export(args.paths, args.sandbox.resolve(), args.layout, replace=args.replace)
        target = args.sandbox.resolve() / sub.rel_path
        print(f"Exported {sum(len(f.documents) for f in sub.filings)} document(s) from "
              f"{len(sub.filings)} filing(s) to {target}")
        for p in sorted(target.iterdir()):
            print(f"  {p.name}")
        if args.pr_body:
            template = (args.sandbox / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text()
            args.pr_body.write_text(pr_body(sub, template, args.layout))
            print(f"Pull request body: {args.pr_body}")

        exported_from = head_commit()
        dirty = uncommitted([f.dir for f in sub.filings])
        today = datetime.date.today().isoformat()
        for f in sub.filings:
            rec = record_for(f, sub.rel_path, exported_from, today)
            manifest = f.dir / corpus.TARIFF_MANIFEST
            if args.record:
                if dirty:
                    raise ExportError(f"uncommitted changes under the exported filings, so "
                                      f"exported_from {exported_from[:12]} would not name what "
                                      f"was exported: {dirty}")
                write_record(manifest, rec)
                print(f"Recorded in {manifest}")
            else:
                print(f"\nRecord for {manifest} (not written; pass --record):")
                print(render_records([rec]))
        if dirty and not args.record:
            print(f"Note: uncommitted changes under the exported filings: {dirty}")
    except ExportError as e:
        print(f"export_sandbox: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
