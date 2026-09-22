#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Service arrangements: the enumeration, in one place.

A SERVICE ARRANGEMENT is a fully-determined selection over the plan space: one
urpx:RatePlanVersion, plus zero or more urpx:RatePlanModifierVersions applicable
to it, plus one urpx:ProfileAlternative per dimension either of them leaves open.
"Determined" means nothing remains to choose: it resolves to prices for any
instant in its window with no further input. It is the thing a customer takes
service under, and the unit an OpenADR 3 price server publishes as a program.

URPX v0.5.1 has no term for it. Every owl:ObjectProperty whose range is one of
the four plan classes was enumerated: fifteen, none with a composition domain.
urpx:hasModifierOptions states availability, urpx:applicableToRatePlan states
compatibility, and urpx:AccountServiceAgreement is a stub whose own skos:note
pushes account data out of scope. A urpx:RatePlanVersion is the BASE plan's
snapshot, not the composition.

Identity is intrinsic: (base version IRI, sorted modifier version IRIs, sorted
alternative selections). A MIDAS RIN is an optional external attestation, never
the identity, and this module does not read or assign one.

Three report generators consume this module: dev/list_service_arrangements.py,
dev/list_ready_for_use.py and dev/list_rate_identifiers.py. They share it rather
than each carrying a walk, because the failure this repository keeps hitting is
two lists that drift. dev/cross_check_arrangements.py consumes it too, for the
opposite reason: it asserts that the enumeration clj-urpx arrives at
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

REPO = pathlib.Path(__file__).resolve().parent.parent
BASELINE = REPO / "dev" / "baseline" / "marginal-rates.edn"
VALIDATOR = REPO / "dev" / "validate_v020.clj"
DEPS = REPO / "deps.edn"

VERSION_TYPES = {"urpx:RatePlanVersion", "urpx:RatePlanModifierVersion"}

# A refusal in these two classes is not a defect: the arrangement resolved, and
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
# mystery diff; see dev/cross_check_arrangements.py.
COMBINE_AT_MOST_ONE_MODIFIER = "at-most-one-modifier"

SERVABLE = "servable"
NOT_PRICED = "not-priced-per-kwh"
BLOCKED = "blocked"
UNMEASURED = "unmeasured"
SUPERSEDED = "superseded"

OUTCOME_RANK = [SERVABLE, NOT_PRICED, BLOCKED, UNMEASURED, SUPERSEDED]


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
                "arrangement's alternative selections cannot be named."
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
    what, and an arrangement built on either answer is a guess.
    """
    if authority == union:
        return
    raise Refuse(
        f"{vid}: copies disagree about which bases it applies to. Its own "
        f"filing says {sorted(authority)}; the union over every copy says "
        f"{sorted(union)}. Resolve that in us/ before an arrangement is built "
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
        # order would let sorted() decide whether an arrangement exists.
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
                    f"choosing one would silently decide whether an arrangement exists. "
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
    instant at all, which is what the reports do.
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
    not_yet_effective instead. With None the latest version of each plan wins
    regardless of date, which is what the reports have always done and what they
    still do. The corpus carries no urpx:expirationDateTime, so a version's
    window has no end bound here and currency is decided by succession alone.
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
    return superseded


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
            f"python dep missing: {e}. Activate the venv "
            f"(source ~/env/py/p3newa/bin/activate) before running this."
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
    """(outcome, reason) for one arrangement, from its baseline rows.

    An arrangement is servable only when EVERY row at EVERY probe instant
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
    base's plan identity, narrowed by urpx:applicableToRatePlanVersion when that
    is stated. Both are the documents talking. That at most one modifier at a
    time is admitted is not: see COMBINE_AT_MOST_ONE_MODIFIER.
    """
    if combine != COMBINE_AT_MOST_ONE_MODIFIER:
        raise Refuse(
            f"unknown combining policy {combine!r}. This module implements "
            f"{COMBINE_AT_MOST_ONE_MODIFIER!r} only; widening it is a change "
            f"in both this repository and clj-urpx."
        )
    for base in sorted(bases.values(), key=lambda v: v["id"]):
        yield base, None
    for modifier in sorted(modifiers, key=lambda v: v["id"]):
        for target in modifier["applies_to"]:
            base = bases.get(target)
            if base is None:
                continue
            if modifier["applies_to_versions"] and base["id"] not in modifier["applies_to_versions"]:
                continue
            yield base, modifier


def enumerate_pairs(at: datetime.datetime | None,
                    combine: str = COMBINE_AT_MOST_ONE_MODIFIER,
                    versions: dict[str, dict] | None = None) -> dict:
    """The set of (base version IRI, frozenset of modifier version IRIs) current
    at `at`, with the versions excluded for getting there.

    Open dimensions are left UNEXPANDED: a base plus a modifier over a
    three-value dimension is one row here and three arrangements. That is the
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
        raise Refuse(f"the corpus expresses no service arrangement {when}.")
    return {
        "pairs": pairs,
        "at": at,
        "combine": combine,
        "superseded": sorted(superseded),
        "not_yet_effective": sorted(future),
        "versions": len(versions),
    }


def build() -> dict:
    """The full enumeration the reports are generated from.

    No instant: currency here is succession alone, the latest version of each
    plan identity. The cross-check against clj-urpx pins an instant instead and
    calls enumerate_pairs, because two implementations answering "current" as of
    different moments would disagree for a reason that is not a disagreement.
    """
    versions = collect_versions()
    superseded = derive_supersession(versions)
    baseline = load_baseline()
    nominations = load_nominations()

    current = {k: v for k, v in versions.items() if k not in superseded}
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

    arrangements: list[dict] = []

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
        arrangements.append({
            "base": base["id"],
            "modifiers": [modifier["id"]] if modifier else [],
            "utility": base["utility"],
            "schedule": base["slug"],
            "dimensions": sorted(dims),
            "selections": selections,
            "nominated_dimensions": sorted(c for c in dims if c in nominations),
            "baseline_keys": keys,
            "outcome": outcome,
            "reason": reason,
        })

    for base, modifier in pair_candidates(bases, modifiers):
        add(base, modifier)

    if not arrangements:
        raise Refuse("the corpus expresses no service arrangement at all.")
    if not any(a["outcome"] == SERVABLE for a in arrangements):
        raise Refuse(
            "not one arrangement is servable. Either the baseline lost its rows "
            "or the corpus stopped resolving; both are regressions, not a report."
        )

    # Every baseline row this enumeration does NOT reach has to be accounted for.
    # An unreferenced row means either a version the enumeration dropped as
    # superseded, or an arrangement it failed to find, and those must be told
    # apart rather than both passing quietly.
    referenced = {k for a in arrangements for k in a["baseline_keys"]}
    superseded_files = {f for vid in superseded for f in versions[vid]["files"]}
    superseded_homes = {versions[vid]["home"] for vid in superseded if versions[vid]["home"]}
    unattributed = []
    for key in baseline["rows"]:
        if key in referenced:
            continue
        kind, _, rest = key.partition("|")
        if kind == "plan" and rest in superseded_files:
            continue
        if kind == "compose" and rest.split("|")[0] in superseded_homes:
            continue
        unattributed.append(key)
    if unattributed:
        raise Refuse(
            "the baseline holds rows this enumeration neither reaches nor can "
            "attribute to a superseded version:\n  "
            + "\n  ".join(sorted(unattributed))
        )

    filings = roll_up_to_filings(versions, superseded, arrangements)

    return {
        "versions": versions,
        "superseded": sorted(superseded),
        "baseline": baseline,
        "nominations": nominations,
        "dimensions": known_dimensions,
        "arrangements": arrangements,
        "filings": filings,
    }


def roll_up_to_filings(versions, superseded, arrangements) -> list[dict]:
    """One row per tariff.toml directory, scored by the arrangements its version
    nodes take part in.

    A filing's outcome is the best outcome over every arrangement drawing on a
    version node present in its JSON-LD, because the question the report answers
    is whether a price server can get a price out of this filing at all. A
    filing whose every version node is superseded is not a service arrangement
    and says so.
    """
    import tomli

    dirs = corpus.tariff_tomls()
    corpus.require_nonempty(dirs, "tariff.toml manifests")

    by_version: dict[str, list[dict]] = collections.defaultdict(list)
    for a in arrangements:
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
        live = [v for v in present if v["id"] not in superseded]
        dead = [v for v in present if v["id"] in superseded]
        if not live:
            outcome, reason = SUPERSEDED, "every version node in this filing has been superseded"
        else:
            candidates = [a for v in live for a in by_version.get(v["id"], [])]
            if not candidates:
                outcome, reason = UNMEASURED, "no arrangement draws on this filing"
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
            "arrangements": len([a for v in live for a in by_version.get(v["id"], [])]),
        })
    return rows


def tally(arrangements) -> collections.Counter:
    return collections.Counter(a["outcome"] for a in arrangements)
