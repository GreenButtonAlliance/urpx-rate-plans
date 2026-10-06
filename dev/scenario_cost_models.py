#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Scenario cost models: the enumeration, in one place.

A scenario cost model is URPX's urpx:ScenarioCostModel, read as a
fully-determined selection over the plan space: one urpx:RatePlanVersion
(urpx:consumesVersion), plus zero or more urpx:RatePlanModifierVersions
applicable to it (urpx:consumesModifierVersion), plus one urpx:ProfileAlternative
per dimension either of them leaves open (urpx:selectsProfileAlternative).
"Determined" means nothing remains to choose: it resolves to prices for any
instant in its window with no further input. It is the unit an OpenADR 3 price
server publishes as a program. consumesModifierVersion and
selectsProfileAlternative, and consumesVersion's sh:maxCount 1, are proposed in
urpx-org/urpx#72 and are in no URPX release yet.

A COMPOSITION is a base version plus a modifier set, with open dimensions not
yet selected. It is the row the reports and the baseline work in, and it stands
for one scenario cost model per selection: the product of its open dimensions'
alternative counts.

Identity is intrinsic: (base version IRI, sorted modifier version IRIs, sorted
alternative selections). model_iri() derives the node IRI from that tuple
alone; doc/scenario-cost-models.md specifies the derivation. A MIDAS RIN is an
optional external attestation, never the identity, and this module does not
read or assign one.

Four report generators consume this module: dev/list_scenario_cost_models.py,
dev/list_ready_for_use.py, dev/list_rate_identifiers.py and
dev/list_version_continuity.py. They share it rather than each carrying a walk,
because the failure this repository keeps hitting is two lists that drift.
dev/cross_check_scenario_cost_models.py consumes it too, for the opposite
reason: it asserts that the enumeration clj-urpx's urpx.scenario-cost-model arrives at
independently has the same members as the one here.

Nothing here is hand-maintained. Every number is derived from the corpus, from
dev/baseline/marginal-rates.edn and from the nominations declared in
dev/validate_v020.clj. Where an input is missing, ambiguous or unattributable,
build() raises SystemExit rather than reporting a verdict over it.
"""
from __future__ import annotations

import collections
import datetime
import json
import pathlib
import re
import zoneinfo

import corpus
import withheld_filings

REPO = pathlib.Path(__file__).resolve().parent.parent
BASELINE = REPO / "dev" / "baseline" / "marginal-rates.edn"
VALIDATOR = REPO / "dev" / "validate_v020.clj"
DEPS = REPO / "deps.edn"

VERSION_TYPES = {"urpx:RatePlanVersion", "urpx:RatePlanModifierVersion"}

# A refusal in these two classes is not a defect: the composition resolved, and
# legitimately prices nothing per kWh. The names and the reasoning are
# dev/validate_v020.clj's `legitimate-refusals`; they are repeated here because
# this module reads the recorded baseline, not the validator.
NOT_PRICED_REASONS = {":no-energy-ledger", ":all-energy-tiers-excluded"}

# Every urpx:effectiveDateTime in this corpus is written without an offset, and
# every filing in it is Californian, so a naive value is read in this zone. A
# value that carries its own offset is used as written.
CORPUS_ZONE = zoneinfo.ZoneInfo("America/Los_Angeles")

# The combining policy: which sets of modifier versions may sit on one base.
# NOTHING IN URPX STATES ONE. urpx:applicableToRatePlan says a modifier version
# is compatible with a base, and no property anywhere says two modifiers exclude
# or combine with each other, so every enumeration of compositions is a caller's
# policy rather than a reading of the documents. This one is base alone, or base
# plus exactly one modifier. It is deliberately conservative and knowingly
# INCOMPLETE: real customers hold several overlays at once. It is named so that
# widening it fires as a decision in two repositories at once rather than as a
# mystery diff; see dev/cross_check_scenario_cost_models.py.
COMBINE_AT_MOST_ONE_MODIFIER = "at-most-one-modifier"

# The instant at which every report decides which version of a plan is current.
# Read from dev/currency-instant.json, the one place it is stated; dev/gate.sh
# passes the same value to the clj-urpx cross-check.
CURRENCY_INSTANT_FILE = REPO / "dev" / "currency-instant.json"


def currency_instant() -> datetime.datetime:
    raw = json.loads(CURRENCY_INSTANT_FILE.read_text())["at"]
    at = datetime.datetime.fromisoformat(raw)
    if at.tzinfo is None:
        raise Refuse(f"{CURRENCY_INSTANT_FILE.name} gives {raw!r}, which carries no offset.")
    return at


SERVABLE = "servable"
NOT_PRICED = "not-priced-per-kwh"
BLOCKED = "blocked"
UNMEASURED = "unmeasured"
SUPERSEDED = "superseded"
NOT_YET_EFFECTIVE = "not-yet-effective"

OUTCOME_RANK = [SERVABLE, NOT_PRICED, BLOCKED, UNMEASURED, NOT_YET_EFFECTIVE, SUPERSEDED]


class Refuse(SystemExit):
    """Refusing to report a verdict. Never a silent pass."""

    def __init__(self, msg: str):
        super().__init__("REFUSING: " + msg)


# ---------------------------------------------------------------------------
# JSON-LD walking
# ---------------------------------------------------------------------------

def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def types_of(node) -> set[str]:
    t = node.get("@type")
    if not t:
        return set()
    return set(t if isinstance(t, list) else [t])


def iri_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [value.get("@id")] if value.get("@id") else []
    out = []
    for x in value:
        if isinstance(x, dict) and x.get("@id"):
            out.append(x["@id"])
        elif isinstance(x, str):
            out.append(x)
    return out


def dimensions_within(node) -> dict[str, dict]:
    """Every urpx:ProfileAlternatives container in this node's subtree."""
    out: dict[str, dict] = {}
    for n in walk(node):
        if "urpx:ProfileAlternatives" not in types_of(n):
            continue
        alts = n.get("urpx:hasProfileAlternative") or []
        if isinstance(alts, dict):
            alts = [alts]
        cid = n.get("@id")
        if not cid:
            raise Refuse(
                "a urpx:ProfileAlternatives container carries no @id, so an "
                "composition's alternative selections cannot be named."
            )
        if not alts:
            raise Refuse(f"urpx:ProfileAlternatives {cid} states no alternatives.")
        out[cid] = {
            "id": cid,
            "name": n.get("urpx:name"),
            "alternatives": [a.get("@id") for a in alts],
        }
    return out


def gating_nodes(dimension_ids) -> dict[str, dict]:
    """What each dimension's alternatives are selected from.

    A dimension is only open if something in the model varies with the choice.
    Walking back from each urpx:ProfileAlternative to the nodes that carry
    urpx:referencesProfileAlternative says what that something is, and the
    shared @id prefix of those nodes says which charge it sits on. Derived, so
    it moves with the corpus instead of being asserted in prose.
    """
    import os

    wanted = set(dimension_ids)
    alt_to_dim: dict[str, str] = {}
    for path in corpus.all_filing_jsonld():
        with path.open() as fp:
            doc = json.load(fp)
        for node in walk(doc):
            if "urpx:ProfileAlternatives" not in types_of(node):
                continue
            cid = node.get("@id")
            if cid not in wanted:
                continue
            alts = node.get("urpx:hasProfileAlternative") or []
            if isinstance(alts, dict):
                alts = [alts]
            for a in alts:
                alt_to_dim[a.get("@id")] = cid

    found: dict[str, dict] = {cid: {"types": set(), "ids": set()} for cid in wanted}
    for path in corpus.all_filing_jsonld():
        with path.open() as fp:
            doc = json.load(fp)
        for node in walk(doc):
            refs = iri_list(node.get("urpx:referencesProfileAlternative"))
            for ref in refs:
                cid = alt_to_dim.get(ref)
                if cid is None:
                    continue
                found[cid]["types"] |= (types_of(node) or {"(untyped)"})
                if node.get("@id"):
                    found[cid]["ids"].add(node["@id"])

    out: dict[str, dict] = {}
    for cid, rec in found.items():
        if not rec["types"]:
            raise Refuse(
                f"{cid} declares alternatives that nothing references via "
                f"urpx:referencesProfileAlternative, so it is not a dimension "
                f"anything varies over."
            )
        out[cid] = {
            "types": sorted(rec["types"]),
            "id_prefix": os.path.commonprefix(sorted(rec["ids"])) if rec["ids"] else "",
        }
    return out


# ---------------------------------------------------------------------------
# Corpus: version nodes, authority, supersession
# ---------------------------------------------------------------------------

def check_compatibility_agreement(vid: str, authority: set[str], union: set[str]) -> None:
    """The authoritative copy of a modifier version must name every base any
    copy of it names.

    A base filing bundles the modifiers operative at its snapshot date, and each
    bundled copy is scoped to that base. If a bundled copy claims a base the
    modifier's own filing does not, the two disagree about what composes with
    what, and a composition built on either answer is a guess.
    """
    if authority == union:
        return
    raise Refuse(
        f"{vid}: copies disagree about which bases it applies to. Its own "
        f"filing says {sorted(authority)}; the union over every copy says "
        f"{sorted(union)}. Resolve that in us/ before a composition is built "
        f"on either answer."
    )


def _home_filename(utility: str, slug: str, date: str, kind: str) -> str:
    stem = "rate-plan" if kind == "plan" else "rate-plan-modifier"
    return f"{stem}_{utility}_{slug}_{date}.jsonld"


def collect_versions() -> dict[str, dict]:
    """Every distinct urpx:RatePlanVersion / urpx:RatePlanModifierVersion.

    A version @id can occur in several filings: a base filing bundles the
    modifiers operative at its snapshot date, and a later snapshot of the same
    base re-states an unchanged version node alongside newly available
    modifiers. Those copies are not always identical, so one occurrence has to
    be the authority. It is the occurrence in the version's OWN filing, the file
    named <utility>_<slug>_<date>, which is where the filing's tariff.toml and
    source PDF live.

    Compatibility is then cross-checked against the union over every copy. A
    copy that claims a base the authority does not is a disagreement about what
    composes with what, and this refuses rather than picking a side.
    """
    files = corpus.all_filing_jsonld()
    corpus.require_nonempty(files, "filing JSON-LD files")

    occurrences: dict[str, list[tuple[str, str, dict]]] = collections.defaultdict(list)
    for path in files:
        rel = str(path.resolve().relative_to(REPO))
        utility, _schedule, _date = corpus.parse_filing_path(path)
        with path.open() as fp:
            doc = json.load(fp)
        for node in walk(doc):
            if not (VERSION_TYPES & types_of(node)):
                continue
            vid = node.get("@id")
            if not vid:
                raise Refuse(f"{rel}: a version node carries no @id.")
            occurrences[vid].append((rel, utility, node))

    corpus.require_nonempty(occurrences, "urpx:RatePlanVersion / urpx:RatePlanModifierVersion nodes")

    versions: dict[str, dict] = {}
    for vid, occs in occurrences.items():
        kind = "modifier" if "urpx:RatePlanModifierVersion" in types_of(occs[0][2]) else "plan"
        local = vid.split(":", 1)[1] if ":" in vid else vid
        m = re.match(r"^(.*)-(\d{4}-\d{2}-\d{2})$", local)
        if not m:
            raise Refuse(
                f"version @id {vid} does not end in a date, so its own filing "
                f"cannot be identified and no occurrence can be made authoritative."
            )
        slug, date = m.group(1), m.group(2)

        home_rel, home_node = None, None
        for rel, utility, node in occs:
            if rel.rsplit("/", 1)[1] == _home_filename(utility, slug, date, kind):
                home_rel, home_node = rel, node
                break
        # Inline-only modifiers (PG&E's vintaged-PCIA overlays) have no filing
        # of their own, so there is no authoritative occurrence to prefer. That
        # is fine while every copy agrees and a refusal when they do not: with
        # no home filing there is nothing to break the tie, and picking by path
        # order would let sorted() decide whether a composition exists.
        # pge:e-tou-c-vintage-pcia-2026-03-01 is exactly this case, named here
        # because the comment that used to sit at this line asserted the
        # opposite ("their sole occurrence"), which is false for it.
        if home_node is not None:
            node = home_node
        elif len(occs) == 1:
            node = occs[0][2]
        else:
            scoped = {
                rel: tuple(sorted(iri_list(n.get("urpx:applicableToRatePlanVersion"))))
                for rel, _utility, n in occs
            }
            if len(set(scoped.values())) > 1:
                detail = "; ".join(f"{rel} says {list(v) or 'nothing'}" for rel, v in sorted(scoped.items()))
                raise Refuse(
                    f"{vid} has no filing of its own and its {len(occs)} bundled copies "
                    f"disagree about which base VERSION it applies to: {detail}. With no "
                    f"authoritative occurrence there is nothing to break the tie, and "
                    f"choosing one would silently decide whether a composition exists. "
                    f"Resolve it in us/, or give the modifier its own filing."
                )
            node = occs[0][2]

        if "urpx:effectiveDateTime" not in node:
            raise Refuse(f"{vid} carries no urpx:effectiveDateTime; supersession cannot be ordered.")
        plan = iri_list(node.get("urpx:forRatePlan") or node.get("urpx:forRatePlanModifier"))
        if len(plan) != 1:
            raise Refuse(
                f"{vid} names {len(plan)} plan identities via urpx:forRatePlan / "
                f"urpx:forRatePlanModifier; exactly one is required."
            )

        authority = set(iri_list(node.get("urpx:applicableToRatePlan")))
        union: set[str] = set()
        for _rel, _u, n in occs:
            union |= set(iri_list(n.get("urpx:applicableToRatePlan")))
        if kind == "modifier":
            check_compatibility_agreement(vid, authority, union)

        versions[vid] = {
            "id": vid,
            "kind": kind,
            "plan": plan[0],
            "effective": node["urpx:effectiveDateTime"],
            "expires": node.get("urpx:expirationDateTime"),
            "home": home_rel,
            "files": sorted({rel for rel, _u, _n in occs}),
            "applies_to": sorted(authority),
            "applies_to_versions": sorted(iri_list(node.get("urpx:applicableToRatePlanVersion"))),
            "dimensions": dimensions_within(node),
            "utility": occs[0][1],
            "slug": slug,
            "date": date,
        }
    return versions


def effective_instant(version: dict) -> datetime.datetime:
    """A version's urpx:effectiveDateTime as an aware instant."""
    raw = version["effective"]
    try:
        parsed = datetime.datetime.fromisoformat(str(raw))
    except ValueError:
        raise Refuse(
            f'{version["id"]} carries urpx:effectiveDateTime {raw!r}, which is '
            f"not an ISO 8601 date-time, so it cannot be placed against an instant."
        )
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=CORPUS_ZONE)


def not_yet_effective(versions: dict[str, dict], at: datetime.datetime | None) -> set[str]:
    """Versions whose urpx:effectiveDateTime is after `at`: filed, not in force.

    Distinct from superseded, and neither is current. `at` of None applies no
    instant at all.
    """
    if at is None:
        return set()
    return {vid for vid, v in versions.items() if effective_instant(v) > at}


def derive_supersession(versions: dict[str, dict], at: datetime.datetime | None = None) -> set[str]:
    """A plan identity holding more than one distinct version @id: all but the
    latest urpx:effectiveDateTime are superseded.

    Derived from the data, never from directory names. Two filing directories
    can hold one version node (CPAU E-1 is filed at 2025-07-01 and again at
    2025-09-01, both carrying cpau:e-1-2025-07-01 because the base rates did not
    change), so a directory count is not a version count.

    `at` pins the instant supersession is judged at. With an instant, only
    versions in force at it can supersede anything, and a version filed for a
    later date does not yet displace the one in force; it is reported by
    not_yet_effective instead, and a version whose urpx:expirationDateTime is
    at or before `at` has ended and is superseded whether or not a successor is
    in the corpus. With None the latest version of each plan wins regardless of
    date; the reports pass currency_instant().
    """
    by_plan: dict[str, list[dict]] = collections.defaultdict(list)
    future = not_yet_effective(versions, at)
    for v in versions.values():
        if v["id"] in future:
            continue
        by_plan[v["plan"]].append(v)

    superseded: set[str] = set()
    for plan, vs in by_plan.items():
        if len(vs) < 2:
            continue
        latest = max(v["effective"] for v in vs)
        if sum(1 for v in vs if v["effective"] == latest) != 1:
            raise Refuse(
                f"{plan} holds {len(vs)} versions of which more than one shares "
                f"the latest urpx:effectiveDateTime {latest}; supersession cannot "
                f"be ordered."
            )
        superseded |= {v["id"] for v in vs if v["effective"] != latest}
    if at is not None:
        for v in versions.values():
            if v["id"] not in future and v.get("expires") and _as_instant(v, v["expires"]) <= at:
                superseded.add(v["id"])
    return superseded


def _as_instant(version: dict, raw) -> datetime.datetime:
    try:
        parsed = datetime.datetime.fromisoformat(str(raw))
    except ValueError:
        raise Refuse(f'{version["id"]} carries {raw!r}, which is not an ISO 8601 date-time.')
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=CORPUS_ZONE)


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------

def _pinned_clj_urpx_version() -> str:
    m = re.search(r'clj-urpx\s*\{:mvn/version\s+"([^"]+)"', DEPS.read_text(), re.S)
    if not m:
        raise Refuse(f"{DEPS.name} does not pin a clj-urpx version.")
    return m.group(1)


def load_baseline() -> dict:
    try:
        import edn_format
    except ImportError as e:  # pragma: no cover - environment problem, not data
        raise Refuse(
            f"python dep missing: {e}. Install dev/requirements.txt "
            f"(pip install -r dev/requirements.txt) before running this."
        )
    if not BASELINE.exists():
        raise Refuse(f"{BASELINE.relative_to(REPO)} is missing; there is nothing to measure against.")
    data = edn_format.loads(BASELINE.read_text())
    K = edn_format.Keyword
    rows = data.get(K("rows"))
    if not rows:
        raise Refuse(f"{BASELINE.relative_to(REPO)} records no rows.")
    instants = data.get(K("probe-instants")) or []
    if not instants:
        raise Refuse(f"{BASELINE.relative_to(REPO)} declares no probe instants.")
    recorded = str(data.get(K("clj-urpx-version")))
    pinned = _pinned_clj_urpx_version()
    if recorded != pinned:
        raise Refuse(
            f"the baseline was recorded against clj-urpx {recorded} but deps.edn "
            f"pins {pinned}. Re-record it before reading servability off it."
        )
    cells = {}
    for key, per_instant in rows.items():
        k = str(key)
        cells[k] = {
            str(i): {
                "status": str(r[K("status")]),
                "reason": str(r[K("reason")]) if K("reason") in r else None,
            }
            for i, r in per_instant.items()
        }
    return {
        "rows": cells,
        "instants": [str(i[K("id")]) for i in instants],
        "clj_urpx_version": recorded,
    }


def classify(keys: list[str], baseline: dict) -> tuple[str, str]:
    """(outcome, reason) for one composition, from its baseline rows.

    A composition is servable only when EVERY row at EVERY probe instant
    resolved. A key with no row, or a key that resolves at some instants and
    refuses at others, is never servable.
    """
    if not keys:
        return UNMEASURED, (
            "no baseline row: the modifier is inline in a base filing, and the "
            "baseline composes only standalone modifier files"
        )
    n_instants = len(baseline["instants"])
    statuses: set[str] = set()
    reasons: set[str] = set()
    for key in keys:
        cells = baseline["rows"].get(key)
        if cells is None:
            return UNMEASURED, f"no baseline row for {key}"
        if len(cells) != n_instants:
            return BLOCKED, (
                f"{key} carries {len(cells)} of {n_instants} probe instants"
            )
        for cell in cells.values():
            statuses.add(cell["status"])
            if cell["reason"]:
                reasons.add(cell["reason"])
    if statuses == {":ok"}:
        return SERVABLE, ""
    if statuses == {":refused"} and reasons and reasons <= NOT_PRICED_REASONS:
        return NOT_PRICED, ", ".join(sorted(reasons))
    detail = ", ".join(sorted(reasons)) if reasons else ", ".join(sorted(statuses))
    if ":ok" in statuses:
        detail = "resolves at some probe instants and refuses at others: " + detail
    return BLOCKED, detail


# ---------------------------------------------------------------------------
# Nominations
# ---------------------------------------------------------------------------

def load_nominations(text: str | None = None) -> dict[str, str]:
    """The alternative selections dev/validate_v020.clj nominates when it records
    the baseline. Read from that file rather than restated here, because a table
    kept in two places is a table that drifts."""
    if text is None:
        text = VALIDATOR.read_text()
    m = re.search(r"\(def profile-alternative-nominations\s*\{(.*?)\}\)", text, re.S)
    if not m:
        raise Refuse(
            f"{VALIDATOR.relative_to(REPO)} no longer declares "
            f"profile-alternative-nominations, so which alternative selections "
            f"the baseline exercised cannot be established."
        )
    pairs = re.findall(r'"([^"]+)"\s+"([^"]+)"', m.group(1))
    return dict(pairs)


# ---------------------------------------------------------------------------
# The enumeration
# ---------------------------------------------------------------------------

def pair_candidates(bases: dict[str, dict], modifiers: list[dict],
                    combine: str = COMBINE_AT_MOST_ONE_MODIFIER):
    """(base, modifier-or-None) for every composition the policy admits.

    The one copy of the combining rule. build() and enumerate_pairs() both go
    through it, so the reports and the cross-check against clj-urpx cannot come
    to different answers about what composes with what.

    A modifier version reaches a base when urpx:applicableToRatePlan names the
    base's plan identity, OR when urpx:applicableToRatePlanVersion names the
    base version itself. The two ADD. Naming a version does not withdraw the
    compatibility that naming a plan asserts.

    That reading is ASSUMED, not settled, and the assumption is disclosed
    rather than buried. URPX Decision #090, which introduced
    applicableToRatePlanVersion, supports both readings a few lines apart. For
    additive: its selected alternative "Preserves the existing document-level
    properties for document-scoped relationships". For narrowing: its rationale
    says the properties "avoid ambiguity where a modifier document is broadly
    applicable but only certain modifier versions are valid for a particular
    rate plan version".

    Additive is pinned here because it is the only reading that survives RDF
    merge: under narrowing, merging a document can retract a compatibility that
    held before it. The cost, stated plainly, is that under additive this
    property can never change an answer applicableToRatePlan did not already
    license, so a decision taken to add precision buys almost none. The
    working group should say which it meant; see the comment in
    dev/cross_check_scenario_cost_models.clj for the full citation and the third
    reading neither of these two is.

    This function narrowed until the reading was settled. The narrowing never
    fired, because no node in this corpus names a version of a plan it does not
    also name, which is exactly why the corpus cannot tell the two readings
    apart. test_scenario_cost_models.py carries the fixture that can.

    Both are the documents talking. That at most one modifier at a time is
    admitted is not: see COMBINE_AT_MOST_ONE_MODIFIER.
    """
    if combine != COMBINE_AT_MOST_ONE_MODIFIER:
        raise Refuse(
            f"unknown combining policy {combine!r}. This module implements "
            f"{COMBINE_AT_MOST_ONE_MODIFIER!r} only; widening it is a change "
            f"in both this repository and clj-urpx."
        )
    # A base the pinned clj-urpx cannot resolve correctly is left out of every
    # composition, and so out of every scenario cost model; see
    # dev/withheld-filings.json. Its filing still rolls up, as unmeasured.
    bases = {plan: base for plan, base in bases.items()
             if not withheld_filings.withheld(base.get("home"))}
    for base in sorted(bases.values(), key=lambda v: v["id"]):
        yield base, None
    by_version = {base["id"]: base for base in bases.values()}
    for modifier in sorted(modifiers, key=lambda v: v["id"]):
        reached: dict[str, dict] = {}
        for plan in modifier["applies_to"]:
            base = bases.get(plan)
            if base is not None:
                reached[base["id"]] = base
        for vid in modifier["applies_to_versions"]:
            base = by_version.get(vid)
            if base is not None:
                reached[vid] = base
        for vid in sorted(reached):
            yield reached[vid], modifier


def enumerate_pairs(at: datetime.datetime | None,
                    combine: str = COMBINE_AT_MOST_ONE_MODIFIER,
                    versions: dict[str, dict] | None = None) -> dict:
    """The set of (base version IRI, frozenset of modifier version IRIs) current
    at `at`, with the versions excluded for getting there.

    Open dimensions are left UNEXPANDED: a base plus a modifier over a
    three-value dimension is one row here and three scenario cost models. That is the
    membership claim two implementations can make identically; expanding is a
    separate decision about whether a pending choice is one row or several.
    """
    if versions is None:
        versions = collect_versions()
    superseded = derive_supersession(versions, at=at)
    future = not_yet_effective(versions, at)
    current = {k: v for k, v in versions.items() if k not in superseded and k not in future}
    bases = {v["plan"]: v for v in current.values() if v["kind"] == "plan"}
    modifiers = [v for v in current.values() if v["kind"] == "modifier"]
    when = "at any instant" if at is None else f"at {at.isoformat()}"
    if not bases:
        raise Refuse(f"no base urpx:RatePlanVersion is current {when}.")
    pairs = {
        (base["id"], frozenset([modifier["id"]] if modifier else []))
        for base, modifier in pair_candidates(bases, modifiers, combine)
    }
    if not pairs:
        raise Refuse(f"the corpus expresses no scenario cost model {when}.")
    return {
        "pairs": pairs,
        "at": at,
        "combine": combine,
        "superseded": sorted(superseded),
        "not_yet_effective": sorted(future),
        "versions": len(versions),
    }


# ---------------------------------------------------------------------------
# Scenario cost models: expansion, identity, IRI
# ---------------------------------------------------------------------------

def selection_sets(alternatives: dict[str, list[str]]) -> list[tuple[str, ...]]:
    """Every way of choosing one urpx:ProfileAlternative per open dimension, as
    sorted tuples of alternative IRIs. One empty tuple when nothing is open.

    An alternative IRI names its container, so the selection is recorded as the
    alternatives alone; an alternative offered by two containers would make that
    ambiguous, and is refused.
    """
    owner: dict[str, str] = {}
    for cid, alts in alternatives.items():
        for alt in alts:
            if owner.setdefault(alt, cid) != cid:
                raise Refuse(
                    f"urpx:ProfileAlternative {alt} is offered by both {owner[alt]} "
                    f"and {cid}, so a selection of it does not say which dimension "
                    f"it closes."
                )
    sets: list[tuple[str, ...]] = [()]
    for cid in sorted(alternatives):
        sets = [s + (alt,) for s in sets for alt in alternatives[cid]]
    return [tuple(sorted(s)) for s in sets]


def model_identity(base: str, modifiers, alternatives) -> tuple:
    """(base version IRI, sorted modifier version IRIs, sorted alternative IRIs)."""
    return (base, tuple(sorted(modifiers)), tuple(sorted(alternatives)))


def expand_compositions(compositions: list[dict]) -> list[tuple]:
    """Every scenario cost model the compositions stand for, as identity tuples,
    sorted. One per selection set of each composition."""
    out = [
        model_identity(c["base"], c["modifiers"], s)
        for c in compositions
        for s in selection_sets(c["alternatives"])
    ]
    if len(set(out)) != len(out):
        raise Refuse("two compositions expand to the same scenario cost model identity.")
    expected = sum(c["selections"] for c in compositions)
    if len(out) != expected:
        raise Refuse(
            f"expanding the compositions gave {len(out)} scenario cost models where "
            f"their selection counts sum to {expected}."
        )
    return sorted(out)


def enumerate_models(at: datetime.datetime | None,
                     combine: str = COMBINE_AT_MOST_ONE_MODIFIER,
                     versions: dict[str, dict] | None = None) -> set[tuple]:
    """The scenario cost model identities current at `at`, open dimensions
    expanded. enumerate_pairs() with each pair's selections multiplied out."""
    if versions is None:
        versions = collect_versions()
    pairs = enumerate_pairs(at, combine, versions)["pairs"]
    out: set[tuple] = set()
    for base, mods in pairs:
        alternatives: dict[str, list[str]] = {}
        for vid in [base, *sorted(mods)]:
            for cid, d in versions[vid]["dimensions"].items():
                alternatives[cid] = list(d["alternatives"])
        for s in selection_sets(alternatives):
            out.add(model_identity(base, mods, s))
    return out


# The IRI scheme. doc/scenario-cost-models.md specifies it for a second
# implementation; change both together.
IRI_ROOT = "https://rate-plans.grid-coordination.energy/"
IRI_SLUG_PREFIX = "scm-"
IRI_SEPARATOR = "--"
IRI_HASH_HEX = 12
LOCAL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def corpus_prefixes() -> dict[str, str]:
    """Every compact-IRI prefix the filings bind, refusing a prefix bound two ways."""
    out: dict[str, str] = {}
    for path in corpus.all_filing_jsonld():
        with path.open() as fp:
            ctx = json.load(fp).get("@context")
        for part in (ctx if isinstance(ctx, list) else [ctx]):
            if not isinstance(part, dict):
                continue
            for k, v in part.items():
                if isinstance(v, str) and out.setdefault(k, v) != v:
                    raise Refuse(f"prefix {k}: is bound to both {out[k]} and {v}.")
    corpus.require_nonempty(out, "@context prefix bindings")
    return out


def expand_iri(iri: str, prefixes: dict[str, str]) -> str:
    if iri.startswith(("http://", "https://")):
        return iri
    prefix, sep, local = iri.partition(":")
    if not sep or prefix not in prefixes:
        raise Refuse(f"{iri} uses no prefix the corpus binds, so it cannot be expanded.")
    return prefixes[prefix] + local


def canonical_identity(identity: tuple) -> str:
    """The hash input: one line per component, absolute IRIs, code-point order."""
    base, mods, alts = identity
    lines = [f"base {base}"]
    lines += [f"modifier {m}" for m in sorted(mods)]
    lines += [f"alternative {a}" for a in sorted(alts)]
    return "\n".join(lines)


def model_iri(identity: tuple) -> str:
    """The absolute IRI of the scenario cost model `identity` names.

    `identity` is in absolute IRIs. Every component must sit in the base
    version's utility namespace, and each local name must be lower-case ASCII
    words joined by single hyphens, so that IRI_SEPARATOR cannot occur inside
    one; anything else is refused rather than escaped.
    """
    import hashlib

    base, mods, alts = identity
    if not base.startswith(IRI_ROOT):
        raise Refuse(f"{base} is not under {IRI_ROOT}.")
    utility = base[len(IRI_ROOT):].split("/", 1)[0]
    ns = f"{IRI_ROOT}{utility}/"

    def local(iri: str) -> str:
        if not iri.startswith(ns):
            raise Refuse(f"{iri} is outside {ns}, the namespace of base version {base}.")
        name = iri[len(ns):]
        if not LOCAL_NAME.match(name):
            raise Refuse(f"{iri}: local name {name!r} is not lower-case words joined by single hyphens.")
        return name

    slug = IRI_SLUG_PREFIX + IRI_SEPARATOR.join([local(base)] + [local(m) for m in sorted(mods)])
    for a in alts:
        local(a)
    if alts:
        digest = hashlib.sha256(canonical_identity(identity).encode("utf-8")).hexdigest()
        slug += IRI_SEPARATOR + digest[:IRI_HASH_HEX]
    return ns + slug


def model_iris(models: list[tuple], prefixes: dict[str, str] | None = None) -> dict[tuple, str]:
    """identity -> absolute IRI, refusing two identities that derive one IRI."""
    if prefixes is None:
        prefixes = corpus_prefixes()
    out: dict[tuple, str] = {}
    seen: dict[str, tuple] = {}
    for identity in models:
        base, mods, alts = identity
        iri = model_iri((expand_iri(base, prefixes),
                         tuple(expand_iri(m, prefixes) for m in mods),
                         tuple(expand_iri(a, prefixes) for a in alts)))
        if iri in seen:
            raise Refuse(f"{iri} is derived from two identities: {seen[iri]} and {identity}.")
        seen[iri] = identity
        out[identity] = iri
    return out


def component_names() -> dict[str, str]:
    """urpx:name of every RatePlan, RatePlanModifier and ProfileAlternative."""
    wanted = {"urpx:RatePlan", "urpx:RatePlanModifier", "urpx:ProfileAlternative"}
    out: dict[str, str] = {}
    for path in corpus.all_filing_jsonld():
        with path.open() as fp:
            doc = json.load(fp)
        for node in walk(doc):
            if wanted & types_of(node) and node.get("@id") and isinstance(node.get("urpx:name"), str):
                out.setdefault(node["@id"], node["urpx:name"])
    return out


def model_name(identity: tuple, versions: dict[str, dict], names: dict[str, str]) -> str:
    """A human-readable name: each consumed version's plan name and @id, then the
    selected alternatives' names. Not an identifier; model_iri() is."""
    base, mods, alts = identity

    def named(iri: str) -> str:
        if iri not in names:
            raise Refuse(f"{iri} carries no urpx:name, so a scenario cost model naming it cannot be named.")
        return names[iri]

    parts = [f"{named(versions[v]['plan'])} [{v}]" for v in [base, *mods]]
    out = " + ".join(parts)
    if alts:
        out += "; " + "; ".join(named(a) for a in alts)
    return out


def model_document(models: list[tuple], versions: dict[str, dict]) -> dict:
    """The JSON-LD document of urpx:ScenarioCostModel nodes, one per identity,
    each with the urpx:name model_name() gives it.

    Not wrapped in a urpx:URPXPackage: its urpx:targetURPXVersion would have to
    name a release, and no release admits the properties urpx-org/urpx#72 adds.
    Empty consumesModifierVersion and selectsProfileAlternative are omitted.
    """
    prefixes = corpus_prefixes()
    iris = model_iris(models, prefixes)
    names = component_names()
    used: dict[str, str] = {"urpx": prefixes["urpx"]}
    nodes: list[dict] = []
    for identity in models:
        base, mods, alts = identity
        prefix = base.split(":", 1)[0]
        used[prefix] = prefixes[prefix]
        node = {
            "@id": f"{prefix}:{iris[identity][len(prefixes[prefix]):]}",
            "@type": "urpx:ScenarioCostModel",
            "urpx:name": model_name(identity, versions, names),
            "urpx:consumesVersion": {"@id": base},
        }
        if mods:
            node["urpx:consumesModifierVersion"] = [{"@id": m} for m in mods]
        if alts:
            node["urpx:selectsProfileAlternative"] = [{"@id": a} for a in alts]
        nodes.append(node)
    nodes.sort(key=lambda n: n["@id"])
    return {"@context": dict(sorted(used.items())), "@graph": nodes}


def build() -> dict:
    """The full enumeration the reports are generated from.

    Currency is judged at currency_instant(), the instant dev/gate.sh also
    passes to the cross-check against clj-urpx, so the reports and the
    cross-check say "current" about the same moment. A version filed for a later
    date is not yet effective there: it is not current, and it does not
    supersede the version in force.
    """
    versions = collect_versions()
    at = currency_instant()
    superseded = derive_supersession(versions, at=at)
    future = not_yet_effective(versions, at)
    baseline = load_baseline()
    nominations = load_nominations()

    current = {k: v for k, v in versions.items() if k not in superseded and k not in future}
    bases = {v["plan"]: v for v in current.values() if v["kind"] == "plan"}
    modifiers = [v for v in current.values() if v["kind"] == "modifier"]
    if not bases:
        raise Refuse("no current base RatePlanVersion survives supersession.")

    known_dimensions: dict[str, dict] = {}
    for v in versions.values():
        for cid, d in v["dimensions"].items():
            known_dimensions.setdefault(cid, dict(d, carried_by=[]))
            known_dimensions[cid]["carried_by"].append(v["id"])
    unknown = sorted(set(nominations) - set(known_dimensions))
    if unknown:
        raise Refuse(
            f"dev/validate_v020.clj nominates a selection in "
            f"{', '.join(unknown)}, which no urpx:ProfileAlternatives in the "
            f"corpus declares. The nomination and the corpus have drifted."
        )

    compositions: list[dict] = []

    def add(base: dict, modifier: dict | None) -> None:
        dims: dict[str, dict] = dict(base["dimensions"])
        if modifier:
            dims.update(modifier["dimensions"])
        if modifier is None:
            keys = [f"plan|{f}" for f in base["files"] if "/rate-plan_" in f]
        elif modifier["home"]:
            keys = [f'compose|{modifier["home"]}|{base["plan"]}']
        else:
            keys = []
        outcome, reason = classify(keys, baseline)
        selections = 1
        for d in dims.values():
            selections *= len(d["alternatives"])
        compositions.append({
            "base": base["id"],
            "modifiers": [modifier["id"]] if modifier else [],
            "utility": base["utility"],
            "schedule": base["slug"],
            "dimensions": sorted(dims),
            "alternatives": {cid: list(d["alternatives"]) for cid, d in sorted(dims.items())},
            "selections": selections,
            "nominated_dimensions": sorted(c for c in dims if c in nominations),
            "baseline_keys": keys,
            "outcome": outcome,
            "reason": reason,
        })

    for base, modifier in pair_candidates(bases, modifiers):
        add(base, modifier)

    if not compositions:
        raise Refuse("the corpus expresses no scenario cost model at all.")
    if not any(a["outcome"] == SERVABLE for a in compositions):
        raise Refuse(
            "not one composition is servable. Either the baseline lost its rows "
            "or the corpus stopped resolving; both are regressions, not a report."
        )

    # Every baseline row this enumeration does NOT reach has to be accounted for.
    # An unreferenced row means either a version the enumeration dropped as
    # superseded, or a composition it failed to find, and those must be told
    # apart rather than both passing quietly.
    referenced = {k for a in compositions for k in a["baseline_keys"]}
    superseded_files = {f for vid in superseded | future for f in versions[vid]["files"]}
    superseded_homes = {versions[vid]["home"] for vid in superseded | future if versions[vid]["home"]}
    unattributed = []
    for key in baseline["rows"]:
        if key in referenced:
            continue
        kind, _, rest = key.partition("|")
        if kind == "plan" and rest in superseded_files:
            continue
        if kind == "compose" and rest.split("|")[0] in superseded_homes:
            continue
        # validate_v020 records a modifier version in effect at no probe
        # instant as one "modifier|<file>" row instead of compose keys.
        if kind == "modifier" and rest in superseded_homes:
            continue
        unattributed.append(key)
    if unattributed:
        raise Refuse(
            "the baseline holds rows this enumeration neither reaches nor can "
            "attribute to a superseded version:\n  "
            + "\n  ".join(sorted(unattributed))
        )

    filings = roll_up_to_filings(versions, superseded, compositions, future)

    return {
        "versions": versions,
        "superseded": sorted(superseded),
        "not_yet_effective": sorted(future),
        "currency_instant": at,
        "baseline": baseline,
        "nominations": nominations,
        "dimensions": known_dimensions,
        "compositions": compositions,
        "models": expand_compositions(compositions),
        "filings": filings,
    }


def roll_up_to_filings(versions, superseded, compositions, future=frozenset()) -> list[dict]:
    """One row per tariff.toml directory, scored by the compositions its version
    nodes take part in.

    A filing's outcome is the best outcome over every composition drawing on a
    version node present in its JSON-LD, because the question the report answers
    is whether a price server can get a price out of this filing at all. A
    filing whose every version node is superseded is not a scenario cost model
    and says so.
    """
    import tomli

    dirs = corpus.tariff_tomls()
    corpus.require_nonempty(dirs, "tariff.toml manifests")

    by_version: dict[str, list[dict]] = collections.defaultdict(list)
    for a in compositions:
        for vid in [a["base"]] + a["modifiers"]:
            by_version[vid].append(a)

    rows: list[dict] = []
    for tp in dirs:
        d = tp.parent
        rel_dir = str(d.resolve().relative_to(REPO))
        utility, schedule, date = corpus.parse_filing_path(tp)
        with tp.open("rb") as fp:
            manifest = tomli.load(fp)
        complete = (manifest.get("modeling") or {}).get("complete") is True

        present = [v for v in versions.values() if any(f.startswith(rel_dir + "/") for f in v["files"])]
        if not present:
            raise Refuse(
                f"{rel_dir} holds a tariff.toml but no version node, so nothing "
                f"can be said about what it serves."
            )
        live = [v for v in present if v["id"] not in superseded and v["id"] not in future]
        dead = [v for v in present if v["id"] in superseded]
        if not live and any(v["id"] in future for v in present):
            outcome, reason = NOT_YET_EFFECTIVE, "every version node in this filing takes effect after the currency instant"
        elif not live:
            outcome, reason = SUPERSEDED, "every version node in this filing has been superseded"
        else:
            candidates = [a for v in live for a in by_version.get(v["id"], [])]
            held = withheld_filings.withheld(rel_dir + "/")
            if held:
                outcome, reason = UNMEASURED, (
                    f"withheld from resolution until clj-urpx {held['until_clj_urpx']} "
                    f"({held['cites']}); see dev/withheld-filings.json")
            elif not candidates:
                outcome, reason = UNMEASURED, "no composition draws on this filing"
            else:
                best = min(candidates, key=lambda a: OUTCOME_RANK.index(a["outcome"]))
                outcome, reason = best["outcome"], best["reason"]
            if dead:
                # A filing whose base version has been superseded can still be
                # the home of current modifier versions, and reporting it as
                # plainly servable would hide that its own base is not.
                note = (f"{len(dead)} of {len(present)} version nodes here are superseded "
                        f"({', '.join(sorted(v['id'] for v in dead))}); "
                        f"the outcome is for the rest")
                reason = f"{reason}; {note}" if reason else note
        rows.append({
            "dir": rel_dir,
            "utility": utility,
            "schedule": schedule,
            "date": date,
            "outcome": outcome,
            "reason": reason,
            "complete": complete,
            "versions": len(present),
            "superseded_here": len(dead),
            "compositions": len([a for v in live for a in by_version.get(v["id"], [])]),
        })
    return rows


def tally(compositions) -> collections.Counter:
    return collections.Counter(a["outcome"] for a in compositions)
