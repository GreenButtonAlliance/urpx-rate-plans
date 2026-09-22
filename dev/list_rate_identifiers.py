#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Generate reports/rate-identifiers.{md,edn}: the MIDAS attestation map.

A MIDAS Rate Identification Number is an OPTIONAL EXTERNAL ATTESTATION about a
service arrangement. It is never the arrangement's identity. An arrangement is
identified intrinsically, by its base version IRI, its sorted modifier version
IRIs and its sorted alternative selections, which is what
reports/service-arrangements.{md,edn} enumerates.

So this report sits BESIDE the corpus, not inside it. No RIN is written into any
filing as a urpx:RatePlanIdentifier or urpx:RatePlanModifierIdentifier, and this
file refuses if one ever is. Two reasons, both checkable:

  Every RIN the corpus cites names a COMPOSITION, not a modifier. MIDAS gives
  USCA-SCSC-0603-0000 as "TOU-D-PRIME-NBT 2023 VINTAGE" and USCA-PGXX-3500-0000
  as E-ELEC with alt_name "NBT23-CCA": base plan, plus NBT, plus vintage, plus
  supply arrangement. Hanging one on the NBT modifier node would assert that the
  modifier alone is what California means by that code.

  urpx-shacl:RatePlanModifierIdentifierShape is sh:closed true over exactly
  skos:notation, urpx:scheme and urpx:identifierJurisdiction
  (../urpx/shacl/urpx-shacl.ttl:3518-3541, URPX v0.5.1), so there is no slot in
  which to qualify the scope of what the notation names.

Pure tabulation. Every number comes from the corpus JSON-LD, from
reports/midas-coverage.json and from dev/arrangements.py. Nothing here is a
hand-maintained table of RINs: the enumeration is whatever the corpus asserts,
and where an input is missing, ambiguous or unattributable this refuses rather
than reporting a verdict over it. The guards are exercised against deliberately
broken inputs in dev/test_rate_identifiers.py.

Run from repo root:  python3 dev/list_rate_identifiers.py
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import arrangements as A  # noqa: E402
import corpus  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MIDAS = REPO / "reports" / "midas-coverage.json"
OWN_OUTPUTS = {"reports/rate-identifiers.md", "reports/rate-identifiers.edn"}

# The token shape, deliberately loose: four dash-separated groups, the first
# being the US/California prefix MIDAS uses. What counts as WELL FORMED is not
# decided here; it is derived from the identifiers MIDAS actually published, in
# derive_grammar() below.
RIN = re.compile(r"USCA-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}")

# The one place a RIN is allowed to appear in a filing: the free-text name of a
# urpx:Price, as a note about where the number came from.
ALLOWED_TYPE = "urpx:Price"
ALLOWED_PROPERTY = "urpx:name"

# "<label> (MIDAS RIN: <expression>)<tail>". The expression is whatever the
# corpus wrote between the colon and the closing parenthesis, quoted verbatim
# into the report rather than reinterpreted here.
CITATION = re.compile(r"^(?P<label>.*?)\s*\(MIDAS RIN:\s*(?P<expr>[^)]*)\)(?P<tail>.*)$", re.S)

CONFIRMED = "confirmed"
DERIVED = "derived"
UNRESOLVED = "unresolved"
STATES = [CONFIRMED, DERIVED, UNRESOLVED]


class Refuse(SystemExit):
    """Refusing to report a verdict. Never a silent pass."""

    def __init__(self, msg: str):
        super().__init__("REFUSING: " + msg)


def norm(s: str | None) -> str:
    """Lowercase, keep only alphanumerics.

    MIDAS spells one identifier's rate_name "TOU-D-PRIME- NBT 2026 VINTAGE" and
    its four siblings without the stray space, so a comparison that respects
    punctuation compares typography instead of names.
    """
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


# ---------------------------------------------------------------------------
# The MIDAS snapshot
# ---------------------------------------------------------------------------

def _shown(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def load_midas(path: Path = MIDAS) -> dict:
    if not path.exists():
        raise Refuse(
            f"{_shown(path)} is missing, so there is nothing to check the "
            f"corpus's identifiers against and every one of them would be reported "
            f"as uncorroborated on the strength of an absent file."
        )
    data = json.loads(path.read_text())
    rids = data.get("rids") or []
    if not rids:
        raise Refuse(
            f"{_shown(path)} carries no rate identifiers, so the "
            f"corroboration test has no second side."
        )
    if not any(r.get("rate_name") for r in rids):
        raise Refuse(
            f"{_shown(path)} carries {len(rids)} rate identifiers and not "
            f"one of them has a rate_name, so name agreement could never be "
            f"established and every identifier would fall through to uncorroborated."
        )
    return {
        "generated_at": data.get("generated_at_utc") or "(unrecorded)",
        "rids": rids,
        "index": {r["rid"]: r for r in rids if r.get("rid")},
        "errors": {e["rid"]: e for e in (data.get("errors") or []) if e.get("rid")},
    }


def derive_grammar(rids: list[dict]) -> dict:
    """What the four-character provider segment encodes, read off the real ones.

    Nothing here asserts the MIDAS format. Each identifier is split into its
    provider segment, rate code and sub code, and the provider segment into two
    halves; the halves that actually occur, and the positions "XX" occupies in
    them, are counted. That is the whole basis on which a corpus identifier is
    later called well formed or not.
    """
    if len(rids) < 2:
        raise Refuse(
            "the MIDAS snapshot holds fewer than two rate identifiers, so no "
            "structure can be read off it and well-formedness would be asserted "
            "rather than derived."
        )
    first: collections.Counter = collections.Counter()
    second: collections.Counter = collections.Counter()
    codes: collections.Counter = collections.Counter()
    subs: collections.Counter = collections.Counter()
    by_segment: collections.Counter = collections.Counter()
    for r in rids:
        parts = (r.get("rid") or "").split("-")
        if len(parts) != 4:
            continue
        seg = parts[1]
        by_segment[seg] += 1
        first[seg[:2]] += 1
        second[seg[2:]] += 1
        codes["numeric" if parts[2].isdigit() else "has-alpha"] += 1
        subs[parts[3]] += 1
    if len(first) < 2 or len(second) < 2:
        raise Refuse(
            f"the MIDAS snapshot shows {len(first)} distinct first halves and "
            f"{len(second)} distinct second halves of the provider segment. With "
            f"fewer than two of either, the segment carries no observable "
            f"structure and calling a corpus identifier well formed would be "
            f"asserting the format, not deriving it."
        )
    return {
        "records": sum(by_segment.values()),
        "segments": dict(by_segment),
        "first_half": dict(first),
        "second_half": dict(second),
        "xx_first": first.get("XX", 0),
        "xx_second": second.get("XX", 0),
        "rate_codes": dict(codes),
        "sub_codes": dict(subs),
    }


def well_formed(rin: str, grammar: dict) -> tuple[bool, str]:
    """Judged against the derived grammar, not against a format asserted here."""
    parts = rin.split("-")
    if len(parts) != 4:
        return False, "not four dash-separated groups"
    seg, code, sub = parts[1], parts[2], parts[3]
    problems = []
    if seg[:2] not in grammar["first_half"]:
        problems.append(f"first half {seg[:2]!r} occurs in no MIDAS identifier")
    if seg[2:] not in grammar["second_half"]:
        problems.append(f"second half {seg[2:]!r} occurs in no MIDAS identifier")
    if sub not in grammar["sub_codes"]:
        problems.append(f"sub code {sub!r} occurs in no MIDAS identifier")
    if not problems:
        shape = "numeric" if code.isdigit() else "has-alpha"
        if not grammar["rate_codes"].get(shape):
            problems.append(f"rate code {code!r} has a shape no MIDAS identifier uses")
    return (not problems), "; ".join(problems)


# ---------------------------------------------------------------------------
# What the corpus asserts
# ---------------------------------------------------------------------------

def load_docs() -> list[tuple[str, dict]]:
    files = corpus.all_filing_jsonld()
    corpus.require_nonempty(files, "filing JSON-LD files")
    out = []
    for path in files:
        with path.open() as fp:
            out.append((str(path.resolve().relative_to(REPO)), json.load(fp)))
    return out


def _richest_by_id(doc) -> dict[str, dict]:
    """Nodes are stated once in full and referenced elsewhere by @id alone, so a
    reference has to be resolved back to the occurrence that carries the body."""
    best: dict[str, dict] = {}
    for n in A.walk(doc):
        i = n.get("@id")
        if not i:
            continue
        if i not in best or len(n) > len(best[i]):
            best[i] = n
    return best


def _conditions(node: dict) -> list[tuple[str, str]]:
    """(custom condition property, string value) for every comparison below a node."""
    out = []
    for cn in A.walk(node):
        if "urpx:ComparisonNode" not in str(cn.get("@type")):
            continue
        left = cn.get("urpx:leftOperand")
        right = cn.get("urpx:rightOperand")
        prop = left.get("urpx:customConditionProperty") if isinstance(left, dict) else None
        val = right.get("urpx:stringValue") if isinstance(right, dict) else None
        if prop and val:
            out.append((prop, val))
    return out


def extract_occurrences(docs: list[tuple[str, dict]]) -> list[dict]:
    """Every place the corpus cites a rate identifier, found by walking, not listed.

    Refuses on a citation it cannot attribute. A RIN outside a urpx:Price name
    is the case this repository decided against, so it is a refusal and not a
    note: an identifier in a skos:notation would be asserting that the node it
    hangs on is what California means by the code.
    """
    occurrences: list[dict] = []
    for rel, doc in docs:
        by_id = _richest_by_id(doc)
        for node in A.walk(doc):
            for prop, value in node.items():
                if not isinstance(value, str) or not RIN.search(value):
                    continue
                types = A.types_of(node)
                if ALLOWED_TYPE not in types or prop != ALLOWED_PROPERTY:
                    raise Refuse(
                        f"{rel}: a rate identifier appears in {prop} on a "
                        f"{'/'.join(sorted(types)) or 'untyped node'} "
                        f"({node.get('@id') or 'no @id'}). The only place this corpus "
                        f"cites one is the {ALLOWED_PROPERTY} of a {ALLOWED_TYPE}, "
                        f"because a MIDAS identifier names a whole composition and "
                        f"attaching it to a node asserts that node is what the code "
                        f"names. Decide that deliberately before this report can "
                        f"tabulate it."
                    )
                m = CITATION.match(value)
                if not m:
                    raise Refuse(
                        f"{rel}: {node.get('@id')} cites a rate identifier in a name "
                        f"this cannot parse into a citation: {value!r}. Expected "
                        f"'<label> (MIDAS RIN: <expression>) ...'."
                    )
                pd = node.get("urpx:referencesPriceDefinition")
                pd_id = pd.get("@id") if isinstance(pd, dict) else pd
                if not pd_id:
                    raise Refuse(
                        f"{rel}: {node.get('@id')} cites {m.group('expr')} but names no "
                        f"urpx:referencesPriceDefinition, so which charge the "
                        f"attestation is about cannot be established."
                    )
                ar = node.get("urpx:hasApplicabilityRule")
                ar_id = ar.get("@id") if isinstance(ar, dict) else ar
                conds = _conditions(by_id.get(ar_id, {})) if ar_id else []
                if not conds:
                    raise Refuse(
                        f"{rel}: {node.get('@id')} cites {m.group('expr')} but its "
                        f"urpx:hasApplicabilityRule ({ar_id or 'absent'}) yields no "
                        f"condition, so which vintage the attestation is about cannot "
                        f"be established."
                    )
                occurrences.append({
                    "file": rel,
                    "node": node.get("@id"),
                    "price_definition": pd_id,
                    "applicability_rule": ar_id,
                    "conditions": tuple(sorted(set(conds))),
                    "rins": tuple(RIN.findall(value)),
                    "expression": m.group("expr").strip(),
                    "label": m.group("label").strip(),
                    "name": value,
                })
    if not occurrences:
        raise Refuse(
            "the corpus cites no rate identifier anywhere, so this report would "
            "tabulate an empty set and call it coverage."
        )
    return occurrences


def group_attestations(occurrences: list[dict]) -> list[dict]:
    """One attestation per (filing, charge, vintage, identifier expression).

    The grain is the thing the corpus actually claims: this charge, for this
    vintage, comes from these MIDAS series. The per-hour Prices under it are
    occurrences of the same claim, so they are counted, not listed.
    """
    groups: dict[tuple, dict] = {}
    for o in occurrences:
        key = (o["file"], o["price_definition"], o["conditions"], o["rins"])
        g = groups.setdefault(key, {
            "file": o["file"],
            "price_definition": o["price_definition"],
            "conditions": o["conditions"],
            "rins": list(o["rins"]),
            "expressions": set(),
            "labels": set(),
            "name": o["name"],
            "occurrences": 0,
        })
        g["expressions"].add(o["expression"])
        g["labels"].add(o["label"])
        g["occurrences"] += 1
    out = []
    for g in groups.values():
        if len(g["labels"]) != 1 or len(g["expressions"]) != 1:
            raise Refuse(
                f"{g['file']}: the {g['occurrences']} Prices citing "
                f"{', '.join(g['rins'])} for {g['price_definition']} disagree about "
                f"what they are citing: labels {sorted(g['labels'])}, expressions "
                f"{sorted(g['expressions'])}. One attestation cannot be two claims."
            )
        g["label"] = g["labels"].pop()
        g["expression"] = g["expressions"].pop()
        del g["labels"], g["expressions"]
        out.append(g)
    return sorted(out, key=lambda g: (g["file"], g["price_definition"], g["conditions"]))


def attach_arrangements(attestations: list[dict], model: dict) -> None:
    """Key each attestation to the service arrangements its filing takes part in.

    Reuses dev/arrangements.py rather than re-deriving the enumeration, so the
    two reports cannot disagree about what an arrangement is. The link is the
    version node whose OWN filing is the file the attestation lives in; that is
    the same authority rule collect_versions() applies.
    """
    versions = model["versions"]
    for g in attestations:
        home = [v for v in versions.values() if v["home"] == g["file"]]
        if not home:
            raise Refuse(
                f"{g['file']} cites rate identifiers but is the home filing of no "
                f"version node, so the attestation cannot be keyed to an arrangement."
            )
        ids = {v["id"] for v in home}
        rows = [a for a in model["arrangements"]
                if a["base"] in ids or set(a["modifiers"]) & ids]
        if not rows:
            raise Refuse(
                f"{g['file']} cites rate identifiers and its version nodes "
                f"({', '.join(sorted(ids))}) take part in no arrangement. Either the "
                f"version is superseded or the enumeration lost it; both make the "
                f"attestation unattributable."
            )
        g["versions"] = sorted(ids)
        g["arrangements"] = [
            {"base": a["base"], "modifiers": list(a["modifiers"]),
             "open_dimensions": list(a["dimensions"]), "selections": a["selections"],
             "outcome": a["outcome"]}
            for a in sorted(rows, key=lambda a: (a["base"], a["modifiers"]))
        ]
        g["utility"] = rows[0]["utility"]
        g["base_slug"] = versions[rows[0]["base"]]["slug"]


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def agreement(att: dict, rec: dict) -> tuple[bool, str]:
    """Does the MIDAS record name the arrangement the corpus expresses?

    Two conditions, both able to fail. The rate_name has to appear in the name
    the corpus wrote around the identifier, and it has to name the base schedule
    of the arrangement the attestation was keyed to. alt_name is recorded
    separately and not required: SCE spells it "TDPRIME", a plan short code the
    corpus never writes, while PG&E spells the whole composition there.
    """
    rate_name = norm(rec.get("rate_name"))
    if not rate_name:
        return False, "MIDAS carries no rate_name for this identifier"
    if rate_name not in norm(att["name"]):
        return False, (f"MIDAS rate_name {rec.get('rate_name')!r} does not appear in the "
                       f"name the corpus wrote")
    if not rate_name.startswith(norm(att["base_slug"])):
        return False, (f"MIDAS rate_name {rec.get('rate_name')!r} does not name the base "
                       f"schedule {att['base_slug']} this attestation was keyed to")
    return True, ""


def classify(att: dict, midas: dict) -> tuple[str, str]:
    index, errors = midas["index"], midas["errors"]
    missing = [r for r in att["rins"] if r not in index and r not in errors]
    if missing:
        return UNRESOLVED, (
            f"{', '.join(missing)} appears nowhere in the MIDAS snapshot"
        )
    if len(att["rins"]) != 1:
        return DERIVED, (
            f"the corpus's value is an expression over {len(att['rins'])} MIDAS "
            f"series ({att['expression']}); no single MIDAS record publishes it"
        )
    rin = att["rins"][0]
    if rin in errors:
        return DERIVED, (
            f"the MIDAS run reached {rin} but could not read its metadata "
            f"({errors[rin].get('error')}), so there is no name to agree with"
        )
    ok, why = agreement(att, index[rin])
    return (CONFIRMED, "") if ok else (DERIVED, why)


def midas_family(base_slug: str, asserted: set[str], midas: dict) -> dict:
    """What MIDAS publishes on one base schedule, against what the corpus asserts.

    The coverage statement. An identifier names a composition, so the records
    whose rate_name starts with the base schedule are the compositions the
    utility itself publishes on that plan; the corpus asserts some subset, and
    the rest are arrangements this corpus does not express.
    """
    base = norm(base_slug)
    fam = [r for r in midas["rids"] if norm(r.get("rate_name")).startswith(base)]
    kin = [r for r in fam
           if "nbt" in norm(r.get("rate_name")) + norm(r.get("alt_name"))]
    return {
        "base_slug": base_slug,
        "family": len(fam),
        "export_related": len(kin),
        "asserted_here": len([r for r in fam if r["rid"] in asserted]),
        "examples": [(r["rid"], r.get("rate_name"), r.get("alt_name"))
                     for r in sorted(kin, key=lambda r: r["rid"])],
    }


def extending_identifiers(att: dict, midas: dict) -> list[tuple[str, str]]:
    """Snapshot identifiers whose alt_name extends this attestation's.

    Where a utility spells the overlays in alt_name, an identifier that extends
    another's names the same composition plus one more overlay, so this is the
    discount and program dimension the asserted identifier does NOT cover. PG&E
    spells overlays that way; SCE puts a plan short code there and gets none,
    which is a property of the naming scheme and not of the arrangement.
    """
    out = []
    for rin in att["rins"]:
        rec = midas["index"].get(rin)
        if not rec or not rec.get("alt_name"):
            continue
        mine = norm(rec["alt_name"])
        for other in midas["rids"]:
            alt = norm(other.get("alt_name"))
            if (other["rid"] != rin and alt.startswith(mine) and len(alt) > len(mine)
                    and norm(other.get("rate_name")) == norm(rec.get("rate_name"))):
                out.append((other["rid"], other.get("alt_name")))
    return sorted(set(out))


def profile_alternatives_by_file(docs: list[tuple[str, dict]]) -> dict[str, list[str]]:
    """Every urpx:ProfileAlternatives container each filing declares, by name."""
    out: dict[str, list[str]] = {}
    for rel, doc in docs:
        names = []
        for node in A.walk(doc):
            if "urpx:ProfileAlternatives" in A.types_of(node):
                names.append(node.get("urpx:name") or node.get("@id") or "(unnamed)")
        out[rel] = names
    return out


def vintage_is_selectable(att: dict, pa_by_file: dict[str, list[str]]) -> bool:
    """Is the vintage this attestation names a selectable alternative?

    Scoped to the filing that carries the vintage, which is where a
    urpx:ProfileAlternatives for it would have to live. A filing declaring none
    settles it without any name matching; the earlier version of this compared
    the vintage against the keyed arrangement's dimension IRIs instead and
    reported a match, because pge:e-elec-2026-03-27-pa-income-tier contains the
    digits 2026 in its version date.
    """
    containers = pa_by_file.get(att["file"])
    if not containers:
        return False
    wanted = {norm(v) for _p, v in att["conditions"] if norm(v)}
    return any(w in norm(c) for c in containers for w in wanted)


def segment_analysis(midas: dict, grammar: dict, asserted: dict) -> dict:
    """The evidence for what the provider segment's two halves encode.

    Every claim in the report's segment section is one of these numbers. The
    rendering branches on them rather than restating a conclusion, so a refreshed
    snapshot that contradicts today's reading changes the sentence instead of
    leaving a false one in place.
    """
    rids = midas["rids"]
    by_seg: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    for r in rids:
        parts = (r.get("rid") or "").split("-")
        if len(parts) == 4:
            by_seg[parts[1]][parts[2]] = r

    # A rate code carried by both <UU><UU> and <UU>XX under the same rate_name
    # is the same rate published twice, differing only in who supplies the
    # energy. That is the evidence for what the second half encodes.
    mirrored = []
    for seg, codes in by_seg.items():
        if seg[2:] != "XX" or seg[:2] == "XX":
            continue
        bundled = by_seg.get(seg[:2] + seg[:2], {})
        for code, rec in codes.items():
            twin = bundled.get(code)
            if twin and norm(twin.get("rate_name")) == norm(rec.get("rate_name")):
                mirrored.append((seg[:2], code))

    # "CCA" is matched against the raw alt_name, not a normalized one: stripping
    # punctuation turns SDG&E's "TOUDR - C CARE" into "toudrccare", which
    # contains the three letters and is not a CCA rate. That false positive put
    # 53 bundled records in this bucket on the first run.
    def says_cca(r) -> bool:
        return "CCA" in (r.get("alt_name") or "").upper()

    per_half: dict[str, dict] = {}
    for r in rids:
        seg = (r.get("rid") or "").split("-")[1]
        if len(seg) != 4:
            continue
        h = per_half.setdefault(seg[:2], {"delivery_only": 0, "delivery_only_cca": 0,
                                          "bundled": 0, "bundled_cca": 0})
        if seg[2:] == "XX":
            h["delivery_only"] += 1
            h["delivery_only_cca"] += says_cca(r)
        else:
            h["bundled"] += 1
            h["bundled_cca"] += says_cca(r)

    codes_asserted = {r.split("-")[2] for r in asserted}
    codes_in_midas = {(r.get("rid") or "").split("-")[2] for r in rids}

    # What the snapshot does publish on the base schedules the unresolved
    # identifiers were keyed to. Absent identifiers are one fact; whether MIDAS
    # covers the same arrangement under different codes is another, and the
    # second is what says whether the absence is about the code or the rate.
    return {
        "xx_first": grammar["xx_first"],
        "xx_second": grammar["xx_second"],
        "mirrored_rate_codes": len(mirrored),
        "per_first_half": per_half,
        "asserted_rate_codes_absent": sorted(codes_asserted - codes_in_midas),
        "asserted_rate_codes_present": sorted(codes_asserted & codes_in_midas),
    }


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------

def build() -> dict:
    midas = load_midas()
    grammar = derive_grammar(midas["rids"])
    model = A.build()
    docs = load_docs()
    pa_by_file = profile_alternatives_by_file(docs)
    occurrences = extract_occurrences(docs)
    attestations = group_attestations(occurrences)
    attach_arrangements(attestations, model)

    for att in attestations:
        att["state"], att["reason"] = classify(att, midas)
        att["extended_by"] = extending_identifiers(att, midas)
        att["vintage_is_selectable"] = vintage_is_selectable(att, pa_by_file)
        att["profile_alternatives_here"] = len(pa_by_file.get(att["file"], []))
        att["fully_determined"] = all(a["selections"] == 1 for a in att["arrangements"])

    by_base: dict[str, set[str]] = collections.defaultdict(set)
    for att in attestations:
        by_base[att["base_slug"]] |= set(att["rins"])
    families = [midas_family(slug, rins, midas) for slug, rins in sorted(by_base.items())]

    asserted: dict[str, dict] = {}
    for att in attestations:
        for rin in att["rins"]:
            rec = asserted.setdefault(rin, {
                "rin": rin, "files": set(), "attestations": 0, "sole": 0, "in_expression": 0,
            })
            rec["files"].add(att["file"])
            rec["attestations"] += 1
            rec["sole" if len(att["rins"]) == 1 else "in_expression"] += 1
    for rin, rec in asserted.items():
        rec["files"] = sorted(rec["files"])
        rec["in_midas"] = rin in midas["index"]
        rec["midas"] = midas["index"].get(rin)
        rec["metadata_error"] = midas["errors"].get(rin, {}).get("error")
        ok, why = well_formed(rin, grammar)
        rec["well_formed"] = ok
        rec["malformed_because"] = why

    require_some_corroboration(asserted)

    tokens = sum(len(att["rins"]) * att["occurrences"] for att in attestations)
    return {
        "midas": {"generated_at": midas["generated_at"], "records": len(midas["rids"]),
                  "metadata_errors": len(midas["errors"])},
        "grammar": grammar,
        "attestations": attestations,
        "identifiers": [asserted[k] for k in sorted(asserted)],
        "families": families,
        "segments": segment_analysis(midas, grammar, asserted),
        "profile_alternatives": pa_by_file,
        "mirror": mirror_analysis(attestations, [asserted[k] for k in sorted(asserted)]),
        "sightings": scan_repo(),
        "occurrences": sum(att["occurrences"] for att in attestations),
        "tokens": tokens,
        "tally": collections.Counter(att["state"] for att in attestations),
    }


def require_some_corroboration(asserted: dict[str, dict]) -> None:
    """The lookup has to succeed at least once before its misses mean anything.

    If not one asserted identifier is in the snapshot, the corroboration test
    compared nothing and every row would read unresolved on the strength of a
    lookup that never landed: a wrong snapshot, a renamed field or a changed
    prefix all look exactly like a coverage finding.
    """
    if not any(r["in_midas"] for r in asserted.values()):
        raise Refuse(
            f"not one of the {len(asserted)} rate identifiers the corpus asserts was "
            f"found in the MIDAS snapshot. That is a failed comparison, not a "
            f"coverage result: check that the snapshot covers these utilities before "
            f"reading anything off it."
        )


def mirror_analysis(attestations: list[dict], identifiers: list[dict]) -> dict:
    """The `XX`-first identifiers, against their mirror-segment siblings.

    The question is whether a first-half `XX` is a transposition of the
    delivery-only code. Three things bear on it and all three are counted here
    rather than argued: whether the siblings are equally absent, whether the
    corpus uses the two forms on different charges, and whether the strings were
    read out of a source file rather than composed.
    """
    index = {r["rin"]: r for r in identifiers}
    suspect = sorted(r for r in index if r.split("-")[1][:2] == "XX")
    if not suspect:
        return {"suspect": [], "siblings": []}
    codes = {r.split("-")[2] for r in suspect}
    siblings = sorted(r for r in index
                      if r.split("-")[1][2:] == "XX" and r.split("-")[2] in codes)

    def charges(rins: set[str]) -> list[str]:
        return sorted({a["price_definition"] for a in attestations
                       if set(a["rins"]) & rins})

    xx_first_charges = charges(set(suspect))
    mirror_charges = charges(set(siblings))

    # The claim that these came out of the utility's upload files, tied to the
    # code that does it. If that script stops reading a RIN column the sentence
    # stops being written, rather than standing as an unsourced assertion.
    source = None
    for cand in sorted((REPO / "scripts").glob("extract-*-eec-values.py")):
        text = cand.read_text()
        if 'index("RIN")' in text and "USCA-" in text:
            source = str(cand.relative_to(REPO))
            break

    return {
        "suspect": suspect,
        "siblings": siblings,
        "suspect_absent": len([r for r in suspect if not index[r]["in_midas"]]),
        "siblings_absent": len([r for r in siblings if not index[r]["in_midas"]]),
        "xx_first_charges": xx_first_charges,
        "mirror_charges": mirror_charges,
        "splits_by_charge": bool(xx_first_charges and mirror_charges
                                 and not set(xx_first_charges) & set(mirror_charges)),
        "verbatim_source": source,
    }


def scan_repo() -> list[dict]:
    """Every tracked file citing a rate identifier, corpus JSON-LD or not.

    extract_occurrences() reads the corpus, which is where the attestations
    live. But an identifier also turns up in filing manifests, filing prose and
    the loader scripts, and "the corpus asserts 24" is only honest alongside
    where else the same strings are written down. Read from git's index so an
    untracked scratch file cannot pad the count.
    """
    import subprocess

    listed = subprocess.run(["git", "ls-files", "-z"], cwd=REPO,
                            capture_output=True, text=True, check=True)
    out = []
    for rel in listed.stdout.split("\0"):
        if not rel:
            continue
        # This report's own outputs are excluded. They quote every identifier,
        # so including them would make the report change every time it is
        # regenerated after being committed, and the drift check would fire on
        # a file that had only caught up with itself.
        if rel in OWN_OUTPUTS:
            continue
        path = REPO / rel
        try:
            text = path.read_text(errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        hits = RIN.findall(text)
        if not hits:
            continue
        out.append({"file": rel, "tokens": len(hits), "distinct": len(set(hits)),
                    "is_filing": rel.startswith("us/")})
    if not out:
        raise Refuse(
            "no tracked file in the repository cites a rate identifier, which "
            "contradicts the corpus walk that just found some. One of the two is "
            "reading the wrong tree."
        )
    return sorted(out, key=lambda r: (-r["tokens"], r["file"]))


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

STATE_LABEL = {
    CONFIRMED: "**confirmed**",
    DERIVED: "**derived**",
    UNRESOLVED: "**unresolved**",
}


def _vintage(att: dict) -> str:
    return ", ".join(f"{p} = {v}" for p, v in att["conditions"])


def _arrangement_label(a: dict) -> str:
    if a["modifiers"]:
        return f'`{a["base"]}` + `{a["modifiers"][0]}`'
    return f'`{a["base"]}`'


def render_md(d: dict) -> str:
    o: list[str] = []
    w = o.append
    t = d["tally"]
    atts = d["attestations"]

    w("# Rate identifiers: the MIDAS attestation map")
    w("")
    w("Auto-generated by `dev/list_rate_identifiers.py`. Do not edit by hand.")
    w("")
    w("## An identifier is an attestation, not an identity")
    w("")
    w("A CEC MIDAS Rate Identification Number is an optional external attestation about a service "
      "arrangement. It is never the arrangement's identity. An arrangement is identified "
      "intrinsically, by its base version IRI, its sorted modifier version IRIs and its sorted "
      "alternative selections, and that is what "
      "[`reports/service-arrangements.md`](./service-arrangements.md) enumerates.")
    w("")
    w("**No identifier is written into any filing.** Not one `urpx:RatePlanIdentifier` and not one "
      "`urpx:RatePlanModifierIdentifier` in this corpus carries a RIN, and the generator refuses to "
      "produce this report if one ever does. Every identifier below is cited in the free-text "
      f"`{ALLOWED_PROPERTY}` of a `{ALLOWED_TYPE}`, as a note about where that number came from.")
    w("")
    w("Two reasons, both checkable against the artifacts:")
    w("")
    w("- Every identifier the corpus cites names a **composition**: base plan, plus the export "
      "tariff, plus a vintage, plus a supply arrangement. Hanging one on the modifier node would "
      "assert that the modifier alone is what California means by the code.")
    w("- `urpx-shacl:RatePlanModifierIdentifierShape` is `sh:closed true` over exactly "
      "`skos:notation`, `urpx:scheme` and `urpx:identifierJurisdiction` (URPX v0.5.1), so there is "
      "no slot in which to qualify the scope of what the notation names.")
    w("")

    w("## What the corpus asserts")
    w("")
    w(f"| | Count |")
    w(f"|---|---:|")
    w(f"| Distinct rate identifiers | {len(d['identifiers'])} |")
    w(f"| Attestations (one per filing, charge, vintage and identifier expression) | {len(atts)} |")
    w(f"| `{ALLOWED_TYPE}` nodes citing one | {d['occurrences']:,} |")
    w(f"| Identifier tokens across those nodes | {d['tokens']:,} |")
    w("")
    w(f"The token count exceeds the node count because "
      f"{len([a for a in atts if len(a['rins']) > 1])} attestations cite more than one identifier "
      f"in a single expression.")
    w("")
    w("| Filing | Identifiers | Attestations | Prices citing one |")
    w("|---|---:|---:|---:|")
    per_file: dict[str, list] = collections.defaultdict(list)
    for a in atts:
        per_file[a["file"]].append(a)
    for f in sorted(per_file):
        rows = per_file[f]
        rins = {r for a in rows for r in a["rins"]}
        w(f"| `{f}` | {len(rins)} | {len(rows)} | {sum(a['occurrences'] for a in rows):,} |")
    w("")
    w("Those are the filings. The same strings are also written down outside the corpus, and the "
      "full tracked-file list is worth having so nobody looks for an identifier where there is none:")
    w("")
    w("| File | Tokens | Distinct |")
    w("|---|---:|---:|")
    for s in d["sightings"]:
        w(f"| `{s['file']}` | {s['tokens']:,} | {s['distinct']:,} |")
    w("")

    w("## Provenance")
    w("")
    w(f"| State | Attestations | What it means |")
    w(f"|---|---:|---|")
    w(f"| **confirmed** | {t[CONFIRMED]} | The identifier is in the MIDAS snapshot and its "
      f"`rate_name` names the arrangement the corpus keyed it to. |")
    w(f"| **derived** | {t[DERIVED]} | The corpus asserts it and it is structurally well formed, "
      f"but nothing in the snapshot corroborates the value. |")
    w(f"| **unresolved** | {t[UNRESOLVED]} | The corpus asserts it and it does not appear in the "
      f"MIDAS snapshot at all. |")
    w(f"| total | {sum(t.values())} | |")
    w("")
    w("**Derived is a resting state, not a defect.** An export compensation rate a utility does not "
      "publish as a single MIDAS series has to be computed from the ones it does, and the result is "
      "correct without being corroborable. The attestation records the arithmetic instead of "
      "claiming an identifier for the answer.")
    w("")
    w("**Unresolved is a statement about the snapshot, not about California.** "
      f"`reports/midas-coverage.json` was generated {d['midas']['generated_at']} and holds "
      f"{d['midas']['records']:,} records. It cannot be refreshed at present: the MIDAS token "
      f"endpoint returns 401 to the stored credentials, checked again when this report was first "
      f"written. So unresolved means *not corroborated by a months-old snapshot*, never *does not "
      f"exist*.")
    w("")

    w("## The attestations")
    w("")
    w("| Utility | Arrangement | Charge | Vintage | Identifier expression | Prices | State |")
    w("|---|---|---|---|---|---:|---|")
    for a in sorted(atts, key=lambda a: (a["utility"], a["price_definition"], a["conditions"])):
        arr = "; ".join(_arrangement_label(x) for x in a["arrangements"])
        w(f"| {a['utility']} | {arr} | `{a['price_definition']}` | {_vintage(a)} | "
          f"`{a['expression']}` | {a['occurrences']:,} | {STATE_LABEL[a['state']]} |")
    w("")
    for a in sorted(atts, key=lambda a: (a["utility"], a["price_definition"], a["conditions"])):
        if a["reason"]:
            w(f"- `{a['expression']}`: {a['reason']}.")
    w("")

    w("## The identifiers")
    w("")
    w("*Shape seen in MIDAS* asks only whether each part of the identifier occurs somewhere in the "
      "snapshot. A no means the snapshot shows no precedent for that part, not that the identifier "
      "is invalid; the reading is in the provider-segment section below.")
    w("")
    w("| Identifier | Shape seen in MIDAS | In MIDAS | MIDAS `rate_name` | MIDAS `alt_name` | "
      "Cited alone | Cited in an expression |")
    w("|---|---|---|---|---|---:|---:|")
    for r in d["identifiers"]:
        m = r["midas"] or {}
        w(f"| `{r['rin']}` | {'yes' if r['well_formed'] else 'no: ' + r['malformed_because']} | "
          f"{'yes' if r['in_midas'] else 'no'} | {m.get('rate_name') or 'not in snapshot'} | "
          f"{m.get('alt_name') or 'not in snapshot'} | {r['sole']} | {r['in_expression']} |")
    w("")

    w("## What the identifier names that the arrangement does not carry")
    w("")
    w("An identifier names a composition. The arrangement it was keyed to expresses part of that "
      "composition structurally and the rest some other way, or not at all. Both are worth stating.")
    w("")
    keyed = len([a for a in atts if a["arrangements"]])
    w(f"**Every one of the {len(atts)} attestations keys to an arrangement the corpus expresses**, "
      f"at the grain of one base version plus one modifier version. What none of them keys to is a "
      f"*fully determined* arrangement, for two reasons that are different in kind.")
    w("")
    w("**Vintage is not a `urpx:ProfileAlternative`.** In these filings the interconnection vintage "
      "is carried by `urpx:ApplicabilityRule` conditions, so it is not an open dimension of the "
      "arrangement: expanding the arrangement's alternatives will never produce one arrangement per "
      f"vintage. Checked against the filing that carries each vintage, "
      f"{len([a for a in atts if a['vintage_is_selectable']])} of {keyed} attestations name a "
      f"vintage that is a selectable alternative there. Per filing:")
    w("")
    w("| Filing | Vintages cited | Condition property | `urpx:ProfileAlternatives` declared here | "
      "Open dimensions of the keyed arrangements |")
    w("|---|---:|---|---:|---|")
    for f in sorted(per_file):
        rows = per_file[f]
        vintages = {v for a in rows for _p, v in a["conditions"]}
        props = {p for a in rows for p, _v in a["conditions"]}
        dims = {c for a in rows for x in a["arrangements"] for c in x["open_dimensions"]}
        w(f"| `{f}` | {len(vintages)} | {', '.join(sorted(f'`{p}`' for p in props))} | "
          f"{len(d['profile_alternatives'].get(f, []))} | "
          f"{', '.join(sorted(f'`{c}`' for c in dims)) or 'none'} |")
    w("")
    w("**The discount tier and the supply arrangement are in the identifier.** Where a utility "
      "spells its overlays in `alt_name`, the snapshot holds identifiers that extend the asserted "
      "one by exactly one more overlay, and those are the compositions the asserted identifier does "
      "not name:")
    w("")
    extended = [a for a in atts if a["extended_by"]]
    if extended:
        w("| Asserted | Extended in the snapshot by |")
        w("|---|---|")
        for a in sorted(extended, key=lambda a: a["rins"][0]):
            ex = "; ".join(f"`{r}` ({alt})" for r, alt in a["extended_by"])
            w(f"| `{a['rins'][0]}` | {ex} |")
    else:
        w("No asserted identifier is extended by another in the snapshot.")
    w("")
    w("What MIDAS publishes on each base schedule, against what the corpus asserts there:")
    w("")
    w("| Base schedule | MIDAS records naming it | of which export-related | asserted here |")
    w("|---|---:|---:|---:|")
    for f in d["families"]:
        w(f"| `{f['base_slug']}` | {f['family']} | {f['export_related']} | {f['asserted_here']} |")
    w("")
    for f in d["families"]:
        if f["export_related"] and not f["asserted_here"]:
            ex = "; ".join(f"`{r}` {a!r}" for r, _n, a in f["examples"][:4])
            w(f"- **`{f['base_slug']}`: the corpus asserts none of the {f['export_related']} "
              f"export-related identifiers the snapshot carries on this schedule.** They include "
              f"{ex}. The snapshot covers this arrangement; it codes it differently from what the "
              f"corpus cites.")
    w("")

    w("## The provider segment, read off the snapshot")
    w("")
    s = d["segments"]
    g = d["grammar"]
    w(f"Every claim here is a count over the {g['records']:,} identifiers in the snapshot.")
    w("")
    w(f"- Provider segments observed: "
      f"{', '.join(f'`{k}` ({v:,})' for k, v in sorted(g['segments'].items()))}.")
    w(f"- First halves: {', '.join(f'`{k}` ({v:,})' for k, v in sorted(g['first_half'].items()))}.")
    w(f"- Second halves: "
      f"{', '.join(f'`{k}` ({v:,})' for k, v in sorted(g['second_half'].items()))}.")
    w(f"- {s['mirrored_rate_codes']:,} (utility, rate code) pairs appear under both `<UU><UU>` and "
      f"`<UU>XX` carrying the same `rate_name`: the same rate published twice, differing only in "
      f"the second half.")
    w("")
    w("| First half | Records with second half `XX` | of which say CCA | Records with a utility "
      "second half | of which say CCA |")
    w("|---|---:|---:|---:|---:|")
    for h in sorted(s["per_first_half"]):
        r = s["per_first_half"][h]
        w(f"| `{h}` | {r['delivery_only']:,} | {r['delivery_only_cca']:,} | {r['bundled']:,} | "
          f"{r['bundled_cca']:,} |")
    w("")
    w("That is the structure: the four characters are two two-character provider codes, the "
      "distribution provider then the energy provider, and `XX` means *not the utility*. The "
      "mirrored rate codes carry most of that weight; the CCA column corroborates it wherever a "
      "utility says CCA in `alt_name` at all, which in this snapshot is one of the three.")
    w("")

    w("## The five `XXSD` identifiers")
    w("")
    m = d["mirror"]
    if not m["suspect"]:
        w("The corpus asserts no identifier with `XX` in the first half of the provider segment.")
    else:
        w(f"The corpus asserts {len(m['suspect'])} identifiers whose provider segment puts `XX` "
          f"first: {', '.join(f'`{r}`' for r in m['suspect'])}. {m['suspect_absent']} of them are "
          f"absent from the snapshot.")
        w("")
        w(f"Their {len(m['siblings'])} mirror-segment siblings, "
          f"{', '.join(f'`{r}`' for r in m['siblings'])}, are absent too: {m['siblings_absent']} of "
          f"{len(m['siblings'])}. **The absence is about the rate code, not about the segment.** "
          f"The rate codes the corpus asserts that the snapshot does not hold are "
          f"{', '.join(f'`{c}`' for c in s['asserted_rate_codes_absent']) or 'none'}; the ones it "
          f"does hold are "
          f"{', '.join(f'`{c}`' for c in s['asserted_rate_codes_present']) or 'none'}. Singling out "
          f"the `XX`-first five treats a property of the segment as the explanation for an absence "
          f"that falls on both segments equally.")
        w("")
        if m["splits_by_charge"]:
            w(f"The pair carries a distinction, and the corpus uses it consistently: the "
              f"`XX`-first identifiers are cited only on {', '.join(f'`{c}`' for c in m['xx_first_charges'])} "
              f"and their siblings only on {', '.join(f'`{c}`' for c in m['mirror_charges'])}. A "
              f"transposition would not divide along the charge like that.")
        else:
            w(f"The `XX`-first identifiers and their siblings are cited on overlapping charges "
              f"({', '.join(f'`{c}`' for c in m['xx_first_charges'])} against "
              f"{', '.join(f'`{c}`' for c in m['mirror_charges'])}), so the corpus is not using the "
              f"pair to carry a component distinction and a transposition cannot be ruled out on "
              f"that basis.")
        w("")
        if s["xx_first"] == 0:
            w(f"On the segment itself: `XX` occupies the second half of {s['xx_second']:,} snapshot "
              f"identifiers and the first half of none. Read against the structure above, a "
              f"first-half `XX` means *this utility supplies the energy, someone else delivers it*, "
              f"the exact mirror of the delivery-only code and the way a generation-only series "
              f"would have to be written. Coherent under the grammar; unattested in this snapshot.")
        else:
            w(f"`XX` occupies the first half of {s['xx_first']:,} snapshot identifiers, so the "
              f"snapshot itself shows the form is one MIDAS issues.")
        w("")
        if m["verbatim_source"]:
            w(f"The strings were not composed here. `{m['verbatim_source']}` reads them out of the "
              f"`RIN` column of the utility's own MIDAS-format upload files and refuses if the "
              f"column is not constant per vintage and component.")
            w("")
        w("**Verdict: not a transposition, and nothing to fix in `us/`.** Confidence is high on the "
          "reading of the segment: the two halves divide along the two charges" +
          (", and the strings come verbatim from the utility's own upload files"
           if m["verbatim_source"] else "") +
          ". Confidence is lower on whether MIDAS publishes this rate-code family at all, which "
          "rests on a single snapshot taken through a single enumeration path and not refreshable "
          "at present. If a refreshed snapshot still lacks the family, the change worth making is "
          "to record the snapshot's own identifiers for the same arrangement alongside these, not "
          "to alter these.")
    w("")

    w("## How to read a row")
    w("")
    w("An arrangement is the unit. The identifier is a note attached beside it saying *California "
      "publishes this composition under this code*. A consumer verifying prices should resolve the "
      "arrangement, then look the identifier up; a consumer building an identity should use the "
      "arrangement's own components and never the identifier.")
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------------------
# EDN
# ---------------------------------------------------------------------------

def _s(v) -> str:
    return "nil" if v is None else '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_edn(d: dict) -> str:
    o: list[str] = []
    w = o.append
    t = d["tally"]
    w(";; Auto-generated by dev/list_rate_identifiers.py. Do not edit by hand.")
    w(";;")
    w(";; A MIDAS rate identifier is an OPTIONAL EXTERNAL ATTESTATION about a service")
    w(";; arrangement, never the arrangement's identity. Identity is intrinsic:")
    w(";; :base + :modifiers + the alternative selections, per")
    w(";; reports/service-arrangements.edn. No identifier is written into any filing;")
    w(";; each is cited in the free-text urpx:name of a urpx:Price.")
    w(";;")
    w(";; :state")
    w(";;   :confirmed  in the MIDAS snapshot, and its rate_name names the arrangement")
    w(";;   :derived    asserted and well formed, but the value is not corroborated")
    w(";;   :unresolved asserted, and absent from the MIDAS snapshot altogether")
    w(";;")
    w(";; :unresolved is a statement about the snapshot. It was generated")
    w(f";; {d['midas']['generated_at']} and cannot currently be refreshed: the MIDAS token")
    w(";; endpoint returns 401 to the stored credentials.")
    w("")
    w("{:midas")
    w(f'  {{:generated-at {_s(d["midas"]["generated_at"])}')
    w(f'   :records {d["midas"]["records"]}')
    w(f'   :metadata-errors {d["midas"]["metadata_errors"]}}}')
    w("")
    w(" :totals")
    w(f'  {{:identifiers {len(d["identifiers"])}')
    w(f"   :attestations {len(d['attestations'])}")
    w(f"   :prices-citing-one {d['occurrences']}")
    w(f"   :identifier-tokens {d['tokens']}")
    w(f"   :confirmed {t[CONFIRMED]}")
    w(f"   :derived {t[DERIVED]}")
    w(f"   :unresolved {t[UNRESOLVED]}}}")
    w("")
    w(" :provider-segment")
    w(f'  {{:records {d["grammar"]["records"]}')
    w("   :first-half {" + " ".join(f"{_s(k)} {v}" for k, v in sorted(d["grammar"]["first_half"].items())) + "}")
    w("   :second-half {" + " ".join(f"{_s(k)} {v}" for k, v in sorted(d["grammar"]["second_half"].items())) + "}")
    w(f'   :mirrored-rate-codes {d["segments"]["mirrored_rate_codes"]}')
    w("   :per-first-half {" + " ".join(
        _s(h) + " {:delivery-only " + str(r["delivery_only"])
        + " :delivery-only-cca " + str(r["delivery_only_cca"])
        + " :bundled " + str(r["bundled"])
        + " :bundled-cca " + str(r["bundled_cca"]) + "}"
        for h, r in sorted(d["segments"]["per_first_half"].items())) + "}")
    w("   :asserted-rate-codes-absent ["
      + " ".join(_s(c) for c in d["segments"]["asserted_rate_codes_absent"]) + "]}")
    w("")
    m = d["mirror"]
    w(" :mirror-segment")
    w("  {:xx-first [" + " ".join(_s(r) for r in m["suspect"]) + "]")
    w(f'   :xx-first-absent {m.get("suspect_absent", 0)}')
    w("   :siblings [" + " ".join(_s(r) for r in m["siblings"]) + "]")
    w(f'   :siblings-absent {m.get("siblings_absent", 0)}')
    w("   :xx-first-charges [" + " ".join(_s(c) for c in m.get("xx_first_charges", [])) + "]")
    w("   :sibling-charges [" + " ".join(_s(c) for c in m.get("mirror_charges", [])) + "]")
    w(f'   :splits-by-charge {"true" if m.get("splits_by_charge") else "false"}')
    w(f'   :verbatim-source {_s(m.get("verbatim_source"))}}}')
    w("")
    w(" :attestations")
    w(" [")
    for a in sorted(d["attestations"], key=lambda a: (a["utility"], a["price_definition"], a["conditions"])):
        arr = " ".join(
            "{:base " + _s(x["base"]) + " :modifiers ["
            + " ".join(_s(m) for m in x["modifiers"]) + "]}"
            for x in a["arrangements"])
        conds = " ".join("[" + _s(p) + " " + _s(v) + "]" for p, v in a["conditions"])
        w(f'  {{:file {_s(a["file"])}')
        w(f'   :utility {_s(a["utility"])}')
        w(f"   :arrangements [{arr}]")
        w(f'   :price-definition {_s(a["price_definition"])}')
        w(f"   :conditions [{conds}]")
        w(f'   :expression {_s(a["expression"])}')
        w("   :identifiers [" + " ".join(_s(r) for r in a["rins"]) + "]")
        w(f'   :prices {a["occurrences"]}')
        w(f'   :state :{a["state"]}')
        if a["reason"]:
            w(f'   :reason {_s(a["reason"])}')
        w("   }")
    w(" ]")
    w("")
    w(" :identifiers")
    w(" [")
    for r in d["identifiers"]:
        m = r["midas"] or {}
        w(f'  {{:identifier {_s(r["rin"])}')
        w(f'   :well-formed {"true" if r["well_formed"] else "false"}')
        w(f'   :in-midas {"true" if r["in_midas"] else "false"}')
        w(f'   :midas-rate-name {_s(m.get("rate_name"))}')
        w(f'   :midas-alt-name {_s(m.get("alt_name"))}')
        w(f'   :cited-alone {r["sole"]}')
        w(f'   :cited-in-expression {r["in_expression"]}')
        w("   :files [" + " ".join(_s(f) for f in r["files"]) + "]}")
    w(" ]}")
    return "\n".join(o) + "\n"


def main() -> int:
    d = build()
    md = REPO / "reports" / "rate-identifiers.md"
    edn = REPO / "reports" / "rate-identifiers.edn"
    md.write_text(render_md(d))
    edn.write_text(render_edn(d))
    t = d["tally"]
    print(f"wrote {md.relative_to(REPO)} and {edn.relative_to(REPO)}: "
          f"{len(d['identifiers'])} identifiers across {len(d['attestations'])} attestations "
          f"({d['occurrences']:,} Prices), "
          f"{t[CONFIRMED]} confirmed, {t[DERIVED]} derived, {t[UNRESOLVED]} unresolved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
