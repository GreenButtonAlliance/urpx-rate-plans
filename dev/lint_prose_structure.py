#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Check a filing's own prose about its structure against that structure.

Prose inside a filing inherits the trust the data has: its reader already
believes the document and has no second source to check it against. Nothing else
here compares a sentence to the node it sits on.

WHAT IT READS. Five prose channels: tariff.toml's [review].notes,
[extraction].notes and each [modeling].deferrals entry, every urpx:description in
the JSON-LD, and README.md. Reading fewer than all five is how the defect this
was written for survived, so the set is stated here and asserted in
dev/test_prose_structure.py.

WHAT SCOPE A CLAIM IS MEASURED AGAINST. The subtree of the nearest enclosing
urpx:RatePlanVersion or urpx:RatePlanModifierVersion, so the claim is measured
against the thing the sentence is about. A urpx:Evaluation on a urpx:CoverageClaim
scopes to the version carrying that claim. A manifest sentence naming one of the
directory's documents scopes to that document's version. Filing-directory scope is
wrong: a directory can hold two versions and a count of neither is a count of both.

THE CLAIM FORMS, each decidable without judging intent:

  UNIVERSAL    "each|every <Type> ... urpx:<property>"  every node of <Type> in
               scope must carry <property>.
  DISTRIBUTIVE "<n> <Type> per <Parent>"  every <Parent> in scope must hold <n>.
  TOTAL        "<n> <Type>", the type name directly after the count, so a
               qualified noun phrase counting a subset is not measured against the
               whole.
  MEMBERSHIP   a node whose urpx:name states how many members it has, against
               urpx:includesPrice. The claim and the evidence sit on one node.
  DANGLING ID  an @id named in prose that no document in the corpus defines.

WHAT IT DECLINES, printed with a count on every run. Prose legitimately describes
other filings, work not done, the standard rather than the file, subsets, and
cross-products; a deferral states what is absent, so a bare count in one is not a
claim about present structure. A check reporting two findings while silently
declining fifty sentences claims more than it earned, so the denominator is
printed rather than implied.

Exit codes: 0 clean, 1 a finding, 3 the harness could not answer.

Usage:
    python3 dev/lint_prose_structure.py [--report] [--json]
      --report  print every parsed claim with its measurement, not just failures
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))
import corpus  # noqa: E402

VERSION_TYPES = ("urpx:RatePlanVersion", "urpx:RatePlanModifierVersion")
PROSE_KEYS = ("urpx:description",)

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "twenty": 20, "thirty": 30, "forty": 40, "sixty": 60, "hundred": 100,
}
NUM = r"(?:\d{1,5}|" + "|".join(NUMBER_WORDS) + r"|" + "|".join(
    w.capitalize() for w in NUMBER_WORDS) + r")"
# NOT case-insensitive, deliberately. URPX capitalizes types and lowercases
# properties, so case IS the discriminator; with re.I the [A-Z] class matched any
# word and "per fixture-type-count" parsed as a distributive claim whose parent
# was the type "fixture".
TYPE_TOKEN = r"(?:urpx:)?([A-Z][A-Za-z]+)"
PROP_TOKEN = r"(?:urpx:)?([a-z][A-Za-z]+)"
# The lookbehind excludes \w and - so "tier-2" and "E-1" are not read as the
# counts 2 and 1, and excludes . and $ so "$0.794 Price" is not read as 794 and
# "clj-urpx 0.32.0 evaluates no ConditionExpression" is not read as a count of 0.
# The comma is in the lookbehind because \d{1,5} cannot match "4,610" and would
# otherwise match the "610" after the comma, reporting a filing that carries 4,610
# Prices as claiming 610.
COUNT = r"(?<![\w\-.$,])(" + NUM + r")"

UNIVERSAL = re.compile(
    r"\b[Ee](?:ach|very)\b[^.;]{0,80}?" + TYPE_TOKEN + r"[^.;]{0,120}?urpx:" + PROP_TOKEN)
DISTRIBUTIVE = re.compile(
    COUNT + r"\s+(?:\w+\s+){0,3}?" + TYPE_TOKEN
    + r"s?\b[^.;]{0,40}?\b(?:per\s|on each of the\s+\w+\s|for each\s)(?:\w+\s+){0,2}?"
    + TYPE_TOKEN + r"s?\b")
TOTAL = re.compile(COUNT + r"\s+" + TYPE_TOKEN + r"s?\b")
# "a single urpx:PriceDefinition with 6 urpx:Price": the count belongs to the
# parent named before it, so it is distributive read backwards.
INVERTED = re.compile(
    r"\b(?:a single|one|each)\s+(?:[a-z0-9-]+\s+)?" + TYPE_TOKEN + r"\s+with\s+"
    + COUNT + r"\s+" + TYPE_TOKEN + r"s?\b")

# A year is not a count. "the 2025 Prices already use" is about a vintage.
YEARLIKE = re.compile(r"^(?:19|20)\d\d$")
# A count stated inside an ABSENCE claim is about what the filing does not have,
# so measuring it against what the filing has inverts the test. "Eight Prices are
# missing" is a true sentence about eight Prices that are not there.
ABSENCE = re.compile(
    r"\b(missing|absent|not modeled|not carried|no longer|has no|have no|carries no|"
    r"unrepresented|omitted|none of|nothing in the model|is not modeled|not one|"
    # "no ServiceBracket carries appliesInSeason": the negation sits before the
    # subject rather than before the verb, which the list above does not reach.
    r"no\s+(?:urpx:)?[A-Z][A-Za-z]+\s+(?:carries|carry|names?|has|have|references?)|"
    r"referenced by nothing|declared and referenced by nothing)\b", re.I)

# A sentence mentioning one of these is about the standard, not about this file.
ABOUT_THE_STANDARD = re.compile(r"\bsh:[a-zA-Z]+|\bv0\.\d|\bURPX v", re.I)
# A sentence in this mood describes work not done. The imperative and gerund
# forms are here because the first run's only finding was "add one further
# urpx:Holiday ...", a proposal that a modal-only pattern reads as a claim.
PROPOSAL = re.compile(
    r"\b(would|could|expressible|express(?:ing|ed)?\s+(?:it|this|that|the)|"
    r"needs?\b|should|proposed?|instead of|it would take|fix by|"
    r"is expressible|not expressible)\b", re.I)
# "three more PriceDefinitions", "one further Holiday": a count of things to be
# ADDED is not a count of things present.
ADDITION = re.compile(r"\b(?:more|further|additional)\s+(?:urpx:)?[A-Z]", re.I)
IMPERATIVE = re.compile(
    r"^(?:add|adding|carry|carrying|give|giving|move|moving|drop|dropping|keep|keeping|"
    r"recompute|recomputing|precompute|precomputing|host|hosting|state|stating|"
    r"either|fix)\b", re.I)


def number(token: str) -> int:
    return int(token) if token.isdigit() else NUMBER_WORDS[token.lower()]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;:])\s+", " ".join(text.split())) if s.strip()]


def descendants(node) -> list[dict]:
    """Every dict in `node`'s subtree, `node` itself excluded."""
    out: list[dict] = []

    def go(x, top=False):
        if isinstance(x, dict):
            if not top:
                out.append(x)
            for v in x.values():
                go(v)
        elif isinstance(x, list):
            for v in x:
                go(v)

    go(node, top=True)
    return out


def count_types(nodes) -> Counter:
    return Counter(n["@type"] for n in nodes
                   if isinstance(n.get("@type"), str))


def children_of(node, want_type: str) -> list[dict]:
    """Nodes of `want_type` in `node`'s subtree, nearest-first is irrelevant:
    a distributive claim counts all of them under each parent."""
    return [n for n in descendants(node) if n.get("@type") == want_type]


def prose_sites(doc):
    """(owner_node, scope_node, key, text) for every prose field under a version.

    `scope_node` is the nearest enclosing version, which is what the sentence is
    about. A urpx:Evaluation reached through urpx:hasCoverageClaim scopes to that
    same version, since the claim is the version's.
    """
    sites = []

    def go(x, scope):
        if isinstance(x, dict):
            if x.get("@type") in VERSION_TYPES:
                scope = x
            if scope is not None:
                for key in PROSE_KEYS:
                    v = x.get(key)
                    if isinstance(v, str) and len(v) >= 40:
                        sites.append((x, scope, key, v))
            for v in x.values():
                go(v, scope)
        elif isinstance(x, list):
            for v in x:
                go(v, scope)

    go(doc, None)
    return sites


def version_in(path: Path):
    """The first version node in a document, or None."""
    found = []

    def go(x):
        if isinstance(x, dict):
            if x.get("@type") in VERSION_TYPES:
                found.append(x)
            for v in x.values():
                go(v)
        elif isinstance(x, list):
            for v in x:
                go(v)

    go(json.loads(path.read_text()))
    return found[0] if found else None


def primary_version(filing_dir: Path, schedule: str, date: str):
    """The version node the manifest is about: the one in the document whose slug
    is the manifest's own schedule and date. Returns None when that document
    cannot be identified, so the manifest's prose is then declined rather than
    measured against the wrong subtree."""
    if not schedule or not date:
        return None
    pattern = re.compile(r"rate-plan(?:-modifier)?_[a-z0-9-]+?_"
                         + re.escape(schedule) + r"_" + re.escape(date) + r"\.jsonld$")
    matches = [p for p in sorted(filing_dir.glob("*.jsonld")) if pattern.match(p.name)]
    if len(matches) != 1:
        return None
    doc = json.loads(matches[0].read_text())
    found = []

    def go(x):
        if isinstance(x, dict):
            if x.get("@type") in VERSION_TYPES:
                found.append(x)
            for v in x.values():
                go(v)
        elif isinstance(x, list):
            for v in x:
                go(v)

    go(doc)
    return found[0] if found else None


def property_vocabulary() -> set[str]:
    """Local names of every urpx: property the corpus uses as a key."""
    names: set[str] = set()

    def go(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k.startswith("urpx:"):
                    names.add(k.split(":", 1)[1])
                go(v)
        elif isinstance(x, list):
            for v in x:
                go(v)

    for p in corpus.all_filing_jsonld():
        go(json.loads(p.read_text()))
    return names


def type_vocabulary() -> set[str]:
    """Local names of every @type the corpus actually uses.

    Needed because prose writes bare "20 ServiceTiers" as often as
    "20 urpx:ServiceTiers", so the pattern has to admit an unprefixed name, and a
    bare capitalized word otherwise matches "Sheet", "Territory" and "Baseline".
    Deriving the vocabulary from the data rather than listing it here means a name
    counts as a type only if some filing uses it as one.
    """
    names: set[str] = set()

    def go(x):
        if isinstance(x, dict):
            t = x.get("@type")
            if isinstance(t, str) and t.startswith("urpx:"):
                names.add(t.split(":", 1)[1])
            for v in x.values():
                go(v)
        elif isinstance(x, list):
            for v in x:
                go(v)

    for p in corpus.all_filing_jsonld():
        go(json.loads(p.read_text()))
    return names


def schedule_slugs() -> set[str]:
    """Every schedule slug in the corpus, so a sentence naming somebody else's
    structure can be set aside rather than measured against this filing."""
    return {d.parent.parent.name for d in corpus.tariff_tomls()}


MEMBER_COUNT = re.compile(r"(?<![\w\-.$])(\d{1,4})\s+\w+\s+components?\b", re.I)


IDTOKEN = re.compile(r"\b[a-z][a-z0-9-]*:[a-z][a-z0-9-]{2,}\b")
INTS = re.compile(r"(?<![\w\-.$,])(\d{1,5})(?![\d.]|\s*-\s*\d)")


def not_a_total(sentence: str, stated: int, measured: int):
    """Why a stated count may legitimately differ from the type's count in scope.

    Each branch is here because it reported a true sentence as a defect. Returns a
    reason string, or None when the claim really is a total.
    """
    # An enumeration whose parts add up: "5 PriceDefinitions for usage charges
    # keyed by touPeriodNumber 1-5 + 1 PriceDefinition for SIFC" states a part,
    # and 5 + 1 is the 6 the file holds.
    others = [int(x) for x in INTS.findall(sentence)]
    if stated in others:
        others.remove(stated)
    if others and stated + sum(others) == measured:
        return "a part of an enumeration whose parts sum to the measured count"

    # A sentence that names its own members: "PRIME has 3 PriceDefinitions with
    # blank-node CalculationMethod (sce:pd-base-services-charge,
    # sce:pd-ev-meter-credit, sce:pd-ev-submeter-credit)".
    named = {i for i in IDTOKEN.findall(sentence) if not i.startswith(("urpx:", "sh:", "xsd:"))}
    if len(named) == stated and stated > 0:
        return "the sentence names exactly that many @ids, so it enumerates a subset"

    # A cross-product the sentence spells out with slash-lists.
    for group in re.findall(r"\(([^()]*[x\u00d7][^()]*)\)", sentence):
        parts = re.split(r"[x\u00d7]", group)
        if len(parts) >= 2:
            sizes = [len([t for t in part.split("/") if t.strip()]) for part in parts]
            product = 1
            for n in sizes:
                product *= n
            if product == stated and all(n >= 1 for n in sizes) and product != measured:
                return ("the sentence spells the count out as a cross-product, so it "
                        "names a subset")

    # An explicitly restrictive scope: "Section C.1 WITHOUT-interval-meter case
    # only - 4 PriceDefinitions".
    head = sentence[:sentence.find(str(stated))] if str(stated) in sentence else sentence
    if re.search(r"\bonly\b", head, re.I):
        return "the clause before the count restricts it to a named subset"

    return None


def ambiguous_owner(scope, readings):
    """None, or a reason: more than one plural-typed container in scope could own
    the counted nodes, so a bare count does not say which. CPAU E-4-TOU carries two
    urpx:TOUSchedule and its README states a TOUPeriod count for each."""
    for name in readings:
        want = f"urpx:{name}"
        owners = set()

        def go(node, nearest):
            if isinstance(node, dict):
                t = node.get("@type")
                if isinstance(t, str) and t.startswith("urpx:") and t != want and t.endswith("s"):
                    nearest = node.get("@id") or t
                if t == want:
                    owners.add(nearest)
                for v in node.values():
                    go(v, nearest)
            elif isinstance(node, list):
                for v in node:
                    go(v, nearest)

        go(scope, None)
        if len(owners) > 1:
            return (f"more than one container in scope holds {want}, so a bare count "
                    f"does not say which")
    return None


def dangling_id_findings():
    """@ids that prose names and the filing does not define.

    Exact, and the sharpest form here: no counting, no mood, no scope. A sentence
    saying "a single pd-udc-trac PriceDefinition with 4 Prices" is describing a
    node, and if no node carries that @id the sentence describes a shape the file
    does not have. Only prefixes the filing itself uses are considered, so naming
    another utility's node is not a finding; and only @ids whose local name looks
    like ours (a known structural stem) are checked, so ordinary hyphenated words
    with a colon in front are not mistaken for identifiers.
    """
    STEM = re.compile(r"^(?:pd|price|ps|psa|pa|cx|cn|bn|mi|ms|ledger|tier|tiers|bracket|"
                      r"er|cc|doc|season|tou|summary|pur)-")
    # Resolved against the WHOLE CORPUS, not the filing directory. Prose
    # legitimately names another filing's nodes: a prior version it supersedes, a
    # base plan a modifier applies to, a sibling schedule it was derived from.
    # Scoped to one directory this check reported 29 such references as defects,
    # of which the great majority resolve one directory over. Only an @id that
    # exists NOWHERE is a claim about a node that does not exist.
    corpus_ids = set()

    def collect(x):
        if isinstance(x, dict):
            i = x.get("@id")
            if isinstance(i, str) and ":" in i:
                corpus_ids.add(i)
            for v in x.values():
                collect(v)
        elif isinstance(x, list):
            for v in x:
                collect(v)

    for jsonld in corpus.all_filing_jsonld():
        collect(json.loads(jsonld.read_text()))
    corpus.require_nonempty(corpus_ids, "@ids defined anywhere in the corpus")
    out = []
    for toml in sorted(corpus.tariff_tomls()):
        filing = str(toml.parent.relative_to(REPO))
        defined, prefixes = set(), set()
        for jsonld in sorted(toml.parent.glob("*.jsonld")):
            doc = json.loads(jsonld.read_text())

            def go(x):
                if isinstance(x, dict):
                    i = x.get("@id")
                    if isinstance(i, str) and ":" in i:
                        defined.add(i)
                        prefixes.add(i.split(":", 1)[0])
                    for v in x.values():
                        go(v)
                elif isinstance(x, list):
                    for v in x:
                        go(v)

            go(doc)
        prefixes -= {"urpx", "xsd", "sh", "skos"}
        if not prefixes:
            continue

        manifest = corpus.load_toml(toml)
        texts = [("tariff.toml:[review].notes", (manifest.get("review") or {}).get("notes")),
                 ("tariff.toml:[extraction].notes",
                  (manifest.get("extraction") or {}).get("notes"))]
        for i, d in enumerate((manifest.get("modeling") or {}).get("deferrals") or [], 1):
            texts.append((f"tariff.toml:[modeling].deferrals[{i}]", d))
        for channel, text in texts:
            if not isinstance(text, str):
                continue
            flat = " ".join(text.split())
            # An id split by TOML's hard wrapping rejoins here, so "sce:tou-d- 4-9pm"
            # is not read as a reference to a nonexistent "sce:tou-d".
            rejoined = re.sub(r"-\s+(?=[a-z0-9])", "-", flat)
            for token in set(IDTOKEN.findall(rejoined)):
                prefix, _, local = token.partition(":")
                if prefix not in prefixes or not STEM.match(local):
                    continue
                if token in corpus_ids:
                    continue
                # A brace or glob after the stem makes it a PATTERN naming a family,
                # not an identifier: "smud:tou-tier-{peak,mid-peak,off-peak}-rtl1",
                # "smud:pd-usage-*-rtl1".
                if re.search(re.escape(token) + r"(?:-?\{|-?\*)", rejoined):
                    continue
                # Prose that deliberately names an id the model does NOT carry, to
                # describe a rename or a mismatch: "sce:pd-base-services-charge ->
                # sce:pd-base-services-charge-2026-03-20", "keys UNBUNDLED_RATES on
                # 'pge:pd-new-system-generation' while the model's is ...".
                near = next((x for x in sentences(rejoined) if token in x), "")
                if re.search(r"\u2192|->|renamed|date-suffix|keys\b|while the model|"
                             r"\bwas\b|no longer|used to", near, re.I):
                    continue
                out.append({"filing": filing, "channel": channel, "form": "dangling-id",
                            "claim": f"names {token}, which no document here defines",
                            "stated": token, "measured": "absent",
                            "sentence": next((x for x in sentences(text) if token in x),
                                             token)[:220]})
    return out


def membership_findings():
    """Nodes whose own name states how many members they have, checked against
    urpx:includesPrice. Exact: no mood, scope or vocabulary judgement is involved,
    because the claim and the evidence sit on the same node."""
    out = []

    def go(node, path):
        if isinstance(node, dict):
            members = node.get("urpx:includesPrice")
            if members is not None:
                members = members if isinstance(members, list) else [members]
                name = node.get("urpx:name") or ""
                m = MEMBER_COUNT.search(name)
                if m and int(m.group(1)) != len(members):
                    out.append({"filing": path, "channel": node.get("@id") or "(unnamed)",
                                "form": "membership",
                                "claim": f"{m.group(1)} components named in urpx:name",
                                "stated": int(m.group(1)), "measured": len(members),
                                "sentence": name})
            for v in node.values():
                go(v, path)
        elif isinstance(node, list):
            for v in node:
                go(v, path)

    for jsonld in corpus.all_filing_jsonld():
        go(json.loads(jsonld.read_text()), str(jsonld.relative_to(REPO)))
    return out


def findings(report: bool = False):
    all_slugs = schedule_slugs()
    corpus.require_nonempty(all_slugs, "schedule slugs")
    vocab = type_vocabulary()
    corpus.require_nonempty(vocab, "URPX type names used by the corpus")
    props = property_vocabulary()
    corpus.require_nonempty(props, "URPX property names used by the corpus")
    out, judged, skipped = [], [], Counter()
    claims_seen = defaultdict(list)          # (filing, kind, key) -> [(value, channel)]

    for toml in sorted(corpus.tariff_tomls()):
        filing = str(toml.parent.relative_to(REPO))
        manifest = corpus.load_toml(toml)
        mine = str(manifest.get("schedule") or "")
        others = {s for s in all_slugs if s != mine and len(s) > 2}

        sites = []
        for jsonld in sorted(toml.parent.glob("*.jsonld")):
            doc = json.loads(jsonld.read_text())
            for owner, scope, key, text in prose_sites(doc):
                sites.append((f"{jsonld.name}:{owner.get('@id') or owner.get('@type')}:{key}",
                              scope, text))
        # The manifest is a prose channel and its claims are about the filing's
        # primary version, so it is scoped to that version's subtree. Omitting it
        # is how the E-TOU-C defect survived: the in-document copy was corrected
        # and the manifest copy was not, leaving a corrected sibling vouching for
        # a false one.
        primary = primary_version(toml.parent, mine, str(manifest.get("effective_date") or ""))
        if primary is not None:
            notes = (manifest.get("review") or {}).get("notes")
            if isinstance(notes, str) and notes:
                sites.append(("tariff.toml:[review].notes", primary, notes))
            for i, d in enumerate((manifest.get("modeling") or {}).get("deferrals") or [], 1):
                sites.append((f"tariff.toml:[modeling].deferrals[{i}]", primary, d))
            # README.md is the third prose channel and makes the same structural
            # claims. Headings, code fences and tables are dropped: a fenced
            # pyshacl invocation is not a claim about the filing, and a table row
            # is a value rather than a sentence.
            enotes = (manifest.get("extraction") or {}).get("notes")
            if isinstance(enotes, str) and enotes:
                sites.append(("tariff.toml:[extraction].notes", primary, enotes))
            readme = toml.parent / "README.md"
            if readme.is_file():
                body, fenced = [], False
                for line in readme.read_text().splitlines():
                    if line.lstrip().startswith("```"):
                        fenced = not fenced
                        continue
                    if fenced or line.startswith("#") or line.lstrip().startswith("|"):
                        continue
                    body.append(line)
                text = "\n".join(body)
                if text.strip():
                    sites.append(("README.md", primary, text))

        docs_here = {j.name: j for j in sorted(toml.parent.glob("*.jsonld"))}

        def rescope(channel, text, scope):
            """A manifest sentence naming one of this directory's documents is
            about THAT document's version, not the manifest's primary one."""
            if not channel.startswith("tariff.toml"):
                return scope
            for name, path in docs_here.items():
                if name in text:
                    v = version_in(path)
                    if v is not None:
                        return v
            return scope

        for channel, scope, text in sites:
            for s in sentences(text):
                scope_here = rescope(channel, s, scope)
                kids = descendants(scope_here)
                counts = count_types(kids)
                if not any(n in s for n in vocab):
                    continue
                if any(re.search(r"\b" + re.escape(o) + r"\b", s) for o in others):
                    skipped["names another schedule"] += 1
                    continue
                if ABOUT_THE_STANDARD.search(s):
                    skipped["about the standard, not the file"] += 1
                    continue
                if PROPOSAL.search(s) or IMPERATIVE.match(s):
                    skipped["describes work not done"] += 1
                    continue
                if ABSENCE.search(s):
                    skipped["states an absence, so the count is of what is NOT there"] += 1
                    continue
                if ADDITION.search(s):
                    skipped["counts what would be added, not what is present"] += 1
                    continue

                m = UNIVERSAL.search(s)
                if m and m.group(1) in vocab and m.group(2) in props:
                    if re.search(r"\b(?:urpx:)?[A-Z][A-Za-z]+\." + re.escape(m.group(2)), s):
                        skipped["property is attributed to another type by a dotted name"] += 1
                        continue
                    t, prop = f"urpx:{m.group(1)}", f"urpx:{m.group(2)}"
                    subjects = [n for n in kids if n.get("@type") == t]
                    if not subjects:
                        skipped["universal claim names a type not in scope"] += 1
                        continue
                    carrying = sum(1 for n in subjects if prop in n)
                    rec = {"filing": filing, "channel": channel, "form": "universal",
                           "claim": f"each {t} carries {prop}",
                           "stated": len(subjects), "measured": carrying,
                           "sentence": s}
                    judged.append(rec)
                    claims_seen[(filing, "universal", (t, prop))].append(
                        (carrying == len(subjects), channel))
                    if carrying != len(subjects):
                        out.append(rec)
                    continue

                inv = INVERTED.search(s)
                if inv and inv.group(1) in vocab and inv.group(3) in vocab:
                    skipped["an inverted distributive: the count belongs to the parent "
                            "named before it"] += 1
                    continue

                dist = DISTRIBUTIVE.search(s)
                dist_ok = bool(dist and dist.group(2) in vocab and dist.group(3) in vocab
                               and dist.group(2) != dist.group(3))
                if re.search(r"\b(?:per\s|for each\s)", s) and not dist_ok:
                    skipped["distributive claim whose parent is not a URPX type"] += 1
                    continue

                m = dist
                if dist_ok:
                    n_stated = number(m.group(1))
                    child, parent = f"urpx:{m.group(2)}", f"urpx:{m.group(3)}"
                    parents = [p for p in kids if p.get("@type") == parent]
                    if not parents:
                        skipped["distributive claim names a parent not in scope"] += 1
                        continue
                    per = {len(children_of(p, child)) for p in parents}
                    rec = {"filing": filing, "channel": channel, "form": "distributive",
                           "claim": f"{n_stated} {child} per {parent}",
                           "stated": n_stated, "measured": sorted(per),
                           "sentence": s}
                    judged.append(rec)
                    claims_seen[(filing, "distributive", (child, parent))].append(
                        (n_stated, channel))
                    if per != {n_stated}:
                        out.append(rec)
                    continue

                # A [modeling].deferral is BY DEFINITION about what the filing does
                # not carry, and its sentences routinely describe the fix in noun
                # phrases with no modal to detect ("two Prices with multiplier -1 and
                # basedOnPrice naming the base plan's ESA and RCA Prices"). Measuring
                # a bare count in one against present structure inverts the test. The
                # two syntactic forms above are safe there, because "each X carries Y"
                # and "n X per Y" assert a shape rather than a quantity; a bare count
                # is not, so TOTAL declines deferrals.
                if channel.startswith("tariff.toml:[modeling].deferrals"):
                    skipped["bare count inside a deferral, which states what is absent"] += 1
                    continue

                m = TOTAL.search(s)
                if m and YEARLIKE.match(m.group(1)):
                    skipped["the number is a year, not a count"] += 1
                    continue
                if m and (m.group(2) in vocab
                          or (m.group(2).endswith("s") and m.group(2)[:-1] in vocab)):
                    n_stated = number(m.group(1))
                    named = m.group(2)
                    readings = [named] if named in vocab else []
                    if named.endswith("s") and named[:-1] in vocab:
                        readings.append(named[:-1])      # the member, not the container
                    present = [r for r in readings if f"urpx:{r}" in counts]
                    if not present:
                        skipped["total claim names a type not in scope"] += 1
                        continue
                    measured = {r: counts[f"urpx:{r}"] for r in present}
                    rec = {"filing": filing, "channel": channel, "form": "total",
                           "claim": f"{n_stated} {'/'.join(present)} in this version",
                           "stated": n_stated, "measured": measured,
                           "sentence": s}
                    if n_stated not in measured.values():
                        best = max(measured.values())
                        reason = not_a_total(s, n_stated, best)
                        if reason:
                            skipped[reason] += 1
                            continue
                    judged.append(rec)
                    claims_seen[(filing, "total", tuple(present))].append((n_stated, channel))
                    if n_stated not in measured.values():
                        out.append(rec)
                    continue

                skipped["parses into none of the three forms"] += 1

    # A claim corrected in one channel and left standing in another is worse than
    # one wrong in both, because the corrected copy vouches for the survivor.
    disagreements = []
    for keyed, values in claims_seen.items():
        distinct = {v for v, _ in values}
        if len(distinct) > 1:
            disagreements.append({"filing": keyed[0], "form": keyed[1],
                                  "subject": keyed[2], "values": values})

    members = membership_findings()
    out.extend(members)
    judged.extend(members)
    dangling = dangling_id_findings()
    out.extend(dangling)
    judged.extend(dangling)
    return out, judged, skipped, disagreements


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true",
                    help="print every parsed claim with its measurement")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out, judged, skipped, disagreements = findings(args.report)
    if not judged:
        print("prose structure: REFUSING, parsed zero structural claims in any filing. "
              "Either the prose changed shape or the parser is broken; either way "
              "nothing was compared.", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps({"findings": out, "judged": len(judged),
                          "skipped": dict(skipped), "disagreements": disagreements},
                         indent=2))
        return 1 if out or disagreements else 0

    if args.report:
        for r in judged:
            mark = "FAIL" if r in out else "ok  "
            print(f"  {mark} {r['claim']:52} measured {r['measured']}")
            print(f"       {r['channel']}")

    total_sentences = len(judged) + sum(skipped.values())
    print(f"prose structure: {len(out)} finding(s) from {len(judged)} claim(s) judged, "
          f"out of {total_sentences} sentence(s) naming a URPX type")
    for reason, n in skipped.most_common():
        print(f"    {n:4} not judged: {reason}")

    for r in out:
        print(f"\n  {r['filing']}")
        print(f"    {r['channel']}")
        print(f"    claims   {r['claim']}")
        print(f"    measured {r['measured']}")
        print(f"    \"{r['sentence'][:220]}\"")

    for d in disagreements:
        print(f"\n  {d['filing']}: one claim, two answers across channels")
        print(f"    subject {d['subject']}")
        for v, ch in d["values"]:
            print(f"      {v!r:12} {ch}")

    return 1 if out or disagreements else 0


if __name__ == "__main__":
    raise SystemExit(main())
