#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
"""Generate reports/scenario-cost-models.{md,edn,jsonld}.

Pure tabulation. Every number comes from the corpus, from
dev/baseline/marginal-rates.edn and from the nominations declared in
dev/validate_v020.clj; nothing here is a hand-maintained table, and
dev/scenario_cost_models.py refuses rather than reporting when an input is missing or
unattributable. The guards are exercised against broken inputs in
dev/test_scenario_cost_models.py.

Run from repo root:  python3 dev/list_scenario_cost_models.py
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scenario_cost_models as A
import utilities  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

# Order and labels come from dev/utilities.py. This block used to be a
# byte-identical copy in two generators, and its roster was not checked against
# the corpus, so a utility gaining filings dropped out of the report silently.
UTILITY_ORDER = utilities.ORDER
UTILITY_LABEL = utilities.labels()
OUTCOME_LABEL = {
    A.SERVABLE: "servable",
    A.NOT_PRICED: "not priced per kWh",
    A.BLOCKED: "blocked",
    A.UNMEASURED: "not measured",
}


MIDAS = REPO / "reports" / "midas-coverage.json"


def midas_overlay_evidence() -> list[str]:
    """What MIDAS says real compositions look like, derived from
    reports/midas-coverage.json rather than asserted here.

    A MIDAS rate identifier names a composition, not a plan, so the RINs sharing
    one rate_name are that plan's overlay combinations, and their alt_name
    suffixes are the overlays. This reads the plan carrying the most of them.
    """
    import itertools
    import json as _json

    if not MIDAS.exists():
        return ["`reports/midas-coverage.json` is not present, so the external evidence for "
                "what a real composition looks like could not be computed here."]
    rids = _json.loads(MIDAS.read_text()).get("rids") or []
    groups: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    # Which of those plans this corpus actually models, taken from the coverage
    # report's own urpx_match rather than re-deriving the name match here.
    modeled_groups: set[tuple[str, str]] = set()
    for r in rids:
        name = r.get("rate_name")
        alt = r.get("alt_name")
        # Only the utilities that spell an alt_name as the rate name plus
        # hyphen-delimited overlays are readable this way. SDG&E, for one, uses
        # a different scheme entirely, and splitting it on hyphens would invent
        # overlays. Groups that do not all follow the convention are skipped
        # rather than parsed into nonsense.
        if name and alt and (alt == name or alt.startswith(name + "-")):
            groups[(r.get("utility") or "", name)].append(alt)
            if r.get("urpx_match"):
                modeled_groups.add((r.get("utility") or "", name))
    groups = {k: v for k, v in groups.items() if len(v) > 1}
    if not groups:
        return ["`reports/midas-coverage.json` carries no named rate identifiers, so the external "
                "evidence for what a real composition looks like could not be computed here."]

    # Prefer a plan the corpus models, then the most overlays within that. Picking
    # the global maximum instead made the exemplar follow whatever the coverage
    # report happened to enumerate: widening its scope to LADWP and SMUD moved it
    # onto PG&E B-1, a commercial schedule with no filing here, so the passage
    # illustrated composition using a plan the reader cannot look up in this repo.
    preferred = {k: v for k, v in groups.items() if k in modeled_groups} or groups
    (utility, name), alts = max(preferred.items(), key=lambda kv: len(kv[1]))
    combos = []
    for alt in alts:
        rest = alt[len(name):].lstrip("-") if alt.startswith(name) else alt
        combos.append(tuple(t for t in rest.split("-") if t))
    overlays = sorted({t for c in combos for t in c})
    stacked = max(len(c) for c in combos)
    never: list[tuple[str, str]] = []
    for a, b in itertools.combinations(overlays, 2):
        if not any(a in c and b in c for c in combos):
            never.append((a, b))

    lines = [
        f"MIDAS publishes {len(alts)} rate identifiers for {utility} {name}, and their `alt_name` "
        f"values name the overlays: {', '.join(overlays)}. A rate identifier there names the "
        f"composition, not the plan, so those {len(alts)} are that one plan's compositions as the "
        f"utility itself publishes them."
    ]
    lines.append(
        f"Up to {stacked} overlays stack at once, so the at-most-one grain here under-enumerates by a "
        f"long way."
    )
    if never:
        pairs = "; ".join(f"{a} with {b}" for a, b in never)
        word = "pair" if len(never) == 1 else "pairs"
        # The CARE/FERA gloss is conditional on that pair actually appearing in
        # the derived list. Stating it unconditionally would leave a sentence
        # asserting a fact about a pair the computation no longer found.
        known_exclusive = ("CARE", "FERA")
        gloss = (
            "CARE with FERA is exclusive by the tariffs' own text; any others "
            if any(sorted(pr) == sorted(known_exclusive) for pr in never)
            else "These "
        )
        lines.append(
            f"And {len(never)} {word} never co-occur across those {len(alts)}: {pairs}. {gloss}"
            f"may be exclusive or may be a MIDAS gap, and the list does not distinguish them. "
            f"Either way it is the shape of constraint the corpus has no way to state, and it is "
            f"why enumerating full subsets here would manufacture compositions no customer can take."
        )
    return lines


def utilities_in(rows) -> list[str]:
    seen = [u for u in UTILITY_ORDER if any(r["utility"] == u for r in rows)]
    for u in sorted({r["utility"] for r in rows}):
        if u not in seen:
            seen.append(u)
    return seen


def label(a) -> str:
    if a["modifiers"]:
        return f'`{a["base"]}` + `{a["modifiers"][0]}`'
    return f'`{a["base"]}`'


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def render_md(d: dict) -> str:
    ar = d["compositions"]
    tally = A.tally(ar)
    determined = sum(a["selections"] for a in ar)
    no_open = [a for a in ar if not a["dimensions"]]
    only_nominated = [a for a in ar
                      if a["dimensions"] and set(a["dimensions"]) <= set(d["nominations"])]
    instants = d["baseline"]["instants"]

    o: list[str] = []
    w = o.append

    w("# Scenario cost models")
    w("")
    w("Auto-generated by `dev/list_scenario_cost_models.py`. Do not edit by hand.")
    w("")
    w("## What a scenario cost model is")
    w("")
    w("A scenario cost model is URPX's `urpx:ScenarioCostModel`, read as a fully-determined selection "
      "over the plan space: one `urpx:RatePlanVersion` (`urpx:consumesVersion`), plus zero or more "
      "`urpx:RatePlanModifierVersion`s applicable to it (`urpx:consumesModifierVersion`), plus one "
      "`urpx:ProfileAlternative` per dimension either of them leaves open "
      "(`urpx:selectsProfileAlternative`). Determined means nothing remains to choose: it resolves to "
      "prices for any instant in its window with no further input. It is the unit an OpenADR 3 price "
      "server publishes as a program for an EMS to subscribe to.")
    w("")
    w("`urpx:consumesModifierVersion` and `urpx:selectsProfileAlternative` are proposed in "
      "[urpx-org/urpx#72](https://github.com/urpx-org/urpx/pull/72) and are in no URPX release yet.")
    w("")
    w("A scenario cost model is identified by its own components: the base version IRI, the sorted "
      "modifier version IRIs, and the sorted alternative selections. Its IRI is derived from those "
      "alone, as [`doc/scenario-cost-models.md`](../doc/scenario-cost-models.md) specifies. A MIDAS RIN "
      "is an optional external attestation, attached only where it is confidently derivable. It is never "
      "the identity, and this report neither reads nor assigns one.")
    w("")
    w(f"[`scenario-cost-models.jsonld`](./scenario-cost-models.jsonld) carries one "
      f"`urpx:ScenarioCostModel` node per model counted below, {len(d['models'])} in all. "
      f"[`scenario-cost-models.edn`](./scenario-cost-models.edn) carries each one's name, keyed by IRI.")
    w("")

    w("## What this report counts")
    w("")
    per_base = collections.Counter(a["base"] for a in ar if a["modifiers"])
    full_subsets = sum(2 ** per_base[b] for b in {a["base"] for a in ar})
    w(f"**Enumerated at the grain of one base version plus at most one modifier version.** "
      f"That grain is what the corpus can defend. Taking every subset of each base's applicable "
      f"modifiers instead would give {full_subsets} compositions, and most of those combinations are "
      f"not real: CARE and FERA are mutually exclusive by their own source text, and URPX v0.5.1 has "
      f"no vocabulary for stating exclusivity between two `urpx:RatePlanModifier`s, so nothing in the "
      f"corpus can rule the combination out. Enumerating combinations the tariffs forbid would be "
      f"worse than under-enumerating. What a fuller enumeration would need is set out below.")
    w("")
    w("**Superseded versions are excluded.** Nobody takes service under a superseded version. "
      "Supersession is derived from the data, never from directory names, "
      "because a directory count is not a version count. Two filing directories can hold one version "
      "node: CPAU E-1 is filed at 2025-07-01 and again at 2025-09-01, and both carry "
      "`cpau:e-1-2025-07-01`, because the base rates did not change and only the modifiers operative "
      "at the snapshot did.")
    w("")
    w("**A composition is a base version plus a modifier set, with open dimensions not yet selected.** "
      "Servability is measured per composition, because that is the grain the baseline records. Each "
      "composition stands for one scenario cost model per selection, the product of its open "
      "dimensions' alternative counts; both numbers are below.")
    w("")

    w("## Counts")
    w("")
    w("| | Count |")
    w("|---|---:|")
    w(f"| Compositions enumerated (base + at most one modifier) | {len(ar)} |")
    w(f"| of which base alone | {len([a for a in ar if not a['modifiers']])} |")
    w(f"| of which base + one modifier | {len([a for a in ar if a['modifiers']])} |")
    w(f"| Scenario cost models, open dimensions expanded | {determined} |")
    w("")
    w("| Outcome | Compositions | Scenario cost models |")
    w("|---|---:|---:|")
    for k in (A.SERVABLE, A.NOT_PRICED, A.BLOCKED, A.UNMEASURED):
        n = tally[k]
        det = sum(a["selections"] for a in ar if a["outcome"] == k)
        w(f"| **{OUTCOME_LABEL[k]}** | {n} | {det} |")
    w(f"| **total** | {len(ar)} | {determined} |")
    w("")
    w("- **servable** resolves to a number at every probe instant.")
    w("- **not priced per kWh** resolves, and legitimately prices nothing per kWh. CPAU E-14 and E-16 "
      "are street lighting: they price per lamp, per fixture and per month. This is not a defect.")
    w("- **blocked** refuses for a reason that is a gap or an undecided selection.")
    w("- **not measured** has no row in the baseline, so nothing is claimed about it either way.")
    w("")

    w("## By utility")
    w("")
    counts = collections.Counter((a["utility"], a["outcome"]) for a in ar)
    w("| Utility | Servable | Not priced per kWh | Blocked | Not measured | Total |")
    w("|---|---:|---:|---:|---:|---:|")
    for u in utilities_in(ar):
        row = [counts[(u, k)] for k in (A.SERVABLE, A.NOT_PRICED, A.BLOCKED, A.UNMEASURED)]
        w(f"| {UTILITY_LABEL.get(u, u.upper())} | " + " | ".join(str(x) for x in row)
          + f" | {sum(row)} |")
    w("")

    for outcome, heading, preamble in (
        (A.NOT_PRICED, "Not priced per kWh", None),
        (A.BLOCKED, "Blocked", None),
        (A.UNMEASURED, "Not measured", None),
    ):
        rows = [a for a in ar if a["outcome"] == outcome]
        if not rows:
            continue
        w(f"## {heading} ({len(rows)})")
        w("")
        if preamble:
            w(preamble)
            w("")
        w("| Composition | Reason |")
        w("|---|---|")
        for a in sorted(rows, key=lambda x: (x["base"], x["modifiers"])):
            w(f"| {label(a)} | {a['reason']} |")
        w("")

    w("## Open dimensions")
    w("")
    w("A dimension a composition's components leave open. The corpus states the alternatives; "
      "choosing among them is the customer attribute a scenario cost model closes over.")
    w("")
    w("| Dimension | Alternatives | Compositions | Selected over | Selection exercised by the baseline |")
    w("|---|---:|---:|---|---|")
    used = collections.Counter(c for a in ar for c in a["dimensions"])
    gating = A.gating_nodes(used)
    for cid in sorted(used):
        dim = d["dimensions"][cid]
        nom = d["nominations"].get(cid)
        cell = f"`{nom}`" if nom else "no"
        g = gating[cid]
        over = ", ".join(f"`{t}`" for t in g["types"])
        if g["id_prefix"]:
            over += f"<br>`{g['id_prefix']}`"
        w(f"| `{cid}`<br>{dim['name']} | {len(dim['alternatives'])} | {used[cid]} | {over} | {cell} |")
    w("")
    w(f"The baseline exercised a specific selection in {len(no_open) + len(only_nominated)} of the "
      f"{determined} scenario cost models: {len(no_open)} leave no dimension open, and "
      f"{len(only_nominated)} leave open only a dimension `dev/validate_v020.clj` nominates a cell in. "
      f"Everywhere else the baseline resolved without making a selection, which establishes that the "
      f"dimension does not gate the per-kWh energy rate at the probe instants. It does not establish "
      f"which alternative the recorded rate belongs to, and it says nothing about the rest of the "
      f"bill. The Selected-over column is where to look: PG&E's income tier is selected over "
      f"`psa-bsc-tier-`, the Basic Service Charge price set, so CARE, FERA and standard share a "
      f"marginal energy rate in this model and part company on a charge the baseline does not probe.")
    w("")

    w("## What a fuller enumeration would need")
    w("")
    for line in midas_overlay_evidence():
        w(line)
        w("")
    w("Three things would close the gap. A way to say two modifiers are mutually exclusive, which "
      "URPX v0.5.1 does not have. A baseline that composes a base with more than one modifier at a "
      "time, which the present one does not do. And a selection recorded per open dimension, so that "
      "a rate can be attributed to the alternative it belongs to rather than to the composition as a "
      "whole.")
    w("")
    both = sorted({a["base"] for a in ar if a["modifiers"]
                   and a["modifiers"][0].split(":", 1)[1].startswith("care-")}
                  & {a["base"] for a in ar if a["modifiers"]
                     and a["modifiers"][0].split(":", 1)[1].startswith("fera-")})
    w(f"The corpus already models the same exclusivity both ways. PG&E states income tier as a "
      f"`urpx:ProfileAlternatives` dimension whose alternatives are mutually exclusive by "
      f"construction. Elsewhere CARE and FERA are separate `urpx:RatePlanModifier`s with nothing to "
      f"say they cannot both apply, and {len(both)} base versions here accept both of them: "
      + ", ".join(f"`{b}`" for b in both)
      + ". One shape is machine-checkable and the other is not.")
    w("")

    w("## Superseded versions excluded")
    w("")
    w(f"{len(d['superseded'])} version nodes, over as many plan identities, each holding more than one "
      f"distinct version `@id`. All but the latest `urpx:effectiveDateTime` are superseded.")
    w("")
    w("| Plan | Superseded version | Effective | Current version | Effective |")
    w("|---|---|---|---|---|")
    for vid in d["superseded"]:
        v = d["versions"][vid]
        cur = [x for x in d["versions"].values()
               if x["plan"] == v["plan"] and x["id"] not in d["superseded"]]
        c = cur[0] if cur else None
        w(f"| `{v['plan']}` | `{vid}` | {v['effective'][:10]} | "
          f"`{c['id'] if c else ''}` | {c['effective'][:10] if c else ''} |")
    w("")

    w("## Provenance")
    w("")
    w(f"Servability is read from `dev/baseline/marginal-rates.edn`, not re-resolved here. The figures "
      f"are as of that baseline: {len(instants)} probe instants per key, resolved by clj-urpx "
      f"{d['baseline']['clj_urpx_version']}. A composition counts as servable only when every one of "
      f"its baseline rows resolved at every one of those instants. Re-record the baseline deliberately "
      f"(`clojure -M:validate --record-baseline`) and this report moves with it.")
    w("")
    w("Every baseline row is accounted for: each is either reached by a composition here or belongs "
      "to a superseded version. A row that is neither makes this generator refuse rather than report.")
    w("")
    w("`reports/ready-for-use.md` rolls these outcomes up to one row per filing directory. "
      "`[modeling].complete` in each `tariff.toml` answers a different question, whether the JSON-LD "
      "fully captures its source PDF, and is not used here.")
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------------------
# EDN
# ---------------------------------------------------------------------------

def render_edn(d: dict) -> str:
    ar = d["compositions"]
    tally = A.tally(ar)
    o: list[str] = []
    w = o.append
    w(";; Auto-generated by dev/list_scenario_cost_models.py. Do not edit by hand.")
    w(";;")
    w(";; A scenario cost model (urpx:ScenarioCostModel) is one RatePlanVersion, plus")
    w(";; zero or more RatePlanModifierVersions applicable to it, plus one")
    w(";; ProfileAlternative per dimension either leaves open. Identity is intrinsic:")
    w(";; base + modifiers + selections. A MIDAS RIN is an optional external")
    w(";; attestation and is not recorded here.")
    w(";;")
    w(";; :compositions are base + modifier set with open dimensions UNEXPANDED, the")
    w(";; grain servability is measured at. :scenario-cost-models maps each model's")
    w(";; IRI, as reports/scenario-cost-models.jsonld carries it, to its name and its")
    w(";; composition's outcome.")
    w(";;")
    w(";; Enumerated at the grain of base + AT MOST ONE modifier, and over CURRENT")
    w(";; versions only. See reports/scenario-cost-models.md for why.")
    w(";;")
    w(";; :outcome is read from dev/baseline/marginal-rates.edn, not re-resolved.")
    w(";;   :servable           resolved at every probe instant")
    w(";;   :not-priced-per-kwh resolved, and legitimately prices nothing per kWh")
    w(";;   :blocked            refused: a gap or an undecided selection")
    w(";;   :not-measured       no baseline row, so nothing is claimed")
    w(";;")
    w(";; :selections is how many scenario cost models a composition stands for,")
    w(";; the product of its open dimensions' alternative counts.")
    w("")
    w("{:baseline")
    w(' {:file "dev/baseline/marginal-rates.edn"')
    w(f'  :clj-urpx-version "{d["baseline"]["clj_urpx_version"]}"')
    w(f'  :probe-instants {len(d["baseline"]["instants"])}}}')
    w("")
    w(" :totals")
    w(f'  {{:compositions {len(ar)}')
    w(f"   :scenario-cost-models {len(d['models'])}")
    w(f"   :servable {tally[A.SERVABLE]}")
    w(f"   :not-priced-per-kwh {tally[A.NOT_PRICED]}")
    w(f"   :blocked {tally[A.BLOCKED]}")
    w(f"   :not-measured {tally[A.UNMEASURED]}}}")
    w("")
    w(" :superseded")
    w("  [" + " ".join(f'"{v}"' for v in d["superseded"]) + "]")
    w("")
    w(" :compositions")
    w(" [")
    for a in sorted(ar, key=lambda x: (x["utility"], x["base"], x["modifiers"])):
        mods = " ".join(f'"{m}"' for m in a["modifiers"])
        dims = " ".join(f'"{c}"' for c in a["dimensions"])
        w(f'  {{:base "{a["base"]}"')
        w(f"   :modifiers [{mods}]")
        w(f"   :open-dimensions [{dims}]")
        w(f"   :selections {a['selections']}")
        w(f"   :outcome :{OUTCOME_KW[a['outcome']]}")
        if a["reason"]:
            w(f'   :reason "{a["reason"]}"')
        w(f"   :baseline-keys [" + " ".join(f'"{k}"' for k in a["baseline_keys"]) + "]}")
    w(" ]")
    w("")
    w(" :scenario-cost-models")
    w(" {")
    outcome = {(a["base"], tuple(sorted(a["modifiers"]))): a["outcome"] for a in ar}
    names = A.component_names()
    iris = A.model_iris(d["models"])
    for identity in sorted(d["models"], key=lambda i: iris[i]):
        name = A.model_name(identity, d["versions"], names)
        w(f'  "{iris[identity]}"')
        w(f'  {{:name {edn_string(name)}')
        w(f"   :outcome :{OUTCOME_KW[outcome[(identity[0], identity[1])]]}}}")
    w(" }}")
    return "\n".join(o) + "\n"


OUTCOME_KW = {
    A.SERVABLE: "servable",
    A.NOT_PRICED: "not-priced-per-kwh",
    A.BLOCKED: "blocked",
    A.UNMEASURED: "not-measured",
}


def edn_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> int:
    import json

    d = A.build()
    md = REPO / "reports" / "scenario-cost-models.md"
    edn = REPO / "reports" / "scenario-cost-models.edn"
    jsonld = REPO / "reports" / "scenario-cost-models.jsonld"
    md.write_text(render_md(d))
    edn.write_text(render_edn(d))
    jsonld.write_text(json.dumps(A.model_document(d["models"], d["versions"]), indent=2) + "\n")
    t = A.tally(d["compositions"])
    print(f"wrote {md.relative_to(REPO)}, {edn.relative_to(REPO)} and {jsonld.relative_to(REPO)}: "
          f"{len(d['compositions'])} compositions, {len(d['models'])} scenario cost models; "
          f"compositions {t[A.SERVABLE]} servable, {t[A.NOT_PRICED]} not priced per kWh, "
          f"{t[A.BLOCKED]} blocked, {t[A.UNMEASURED]} not measured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
