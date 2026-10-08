#!/usr/bin/env bash
# The repository gate. Two modes, because a gate people bypass is not a gate.
#
#   dev/gate.sh --fast [utility...]   the pre-commit gate. The Clojure consumer
#                                     path plus a baseline comparison for each
#                                     touched utility. Utilities are inferred
#                                     from the staged diff when not given.
#   dev/gate.sh --full                everything, for a deliberate check before
#                                     a wave lands or a release is cut.
#
# Exit codes:
#   0  green
#   1  a regression (new violation key, or a failing consumer/lint step)
#   2  tracked-file drift (a generator output was not committed)
#   3  the harness refused (it cannot produce a meaningful answer)
#
# Exit 3 exists because "refused" and "failed" are different facts. A namespace
# mismatch, a missing ../urpx checkout or an empty corpus all make the validators
# unable to answer, and reporting that as a violation count sends you looking for
# a data defect that is not there.
#
# There is no CI in this repository (.github/ does not exist), so this script run
# from the pre-commit hook is the ONLY automatic trigger. Do not treat CI as a
# fallback for anything.
#
# Every SHACL step goes through dev/shacl.sh: com.dcj/clj-shacl, in the nREPL
# named by .nrepl-port when one answers, else in a fresh JVM. For the comparison
# period, URPX_SHACL_ENGINE=pyshacl dev/gate.sh runs the same steps on pyshacl
# (dev/validate-with-base.py); dev/check_shacl_parity.py compares the two.

set -uo pipefail

REPO=$(git rev-parse --show-toplevel)
cd "$REPO"

# The Python scripts need dev/requirements.txt. Set URPX_RATE_PLANS_VENV to a
# virtualenv holding them to have it activated here; otherwise python3 on PATH
# must already have them.
if [ -n "${URPX_RATE_PLANS_VENV:-}" ]; then
    # shellcheck disable=SC1091
    source "$URPX_RATE_PLANS_VENV/bin/activate"
fi

# The instant at which "current" is judged, for the scenario cost model
# cross-check below and for every report dev/scenario_cost_models.py feeds. One
# place: dev/currency-instant.json.
CURRENCY_AT=$(python3 -c 'import json; print(json.load(open("dev/currency-instant.json"))["at"])') || {
    echo "REFUSED: cannot read dev/currency-instant.json" >&2; exit 3; }

MODE=${1:---fast}
shift || true

# One log directory per run, so gates running at once in different worktrees
# cannot print each other's evidence. Removed on a green run; kept on any other
# exit so the logs behind a failure survive.
tmp_root=${TMPDIR:-/tmp}
LOGDIR=$(mktemp -d "${tmp_root%/}/gate.XXXXXX") || { echo "gate: mktemp failed" >&2; exit 3; }
cleanup_logdir() {
    rc=$?
    if [ "$rc" -eq 0 ]; then
        rm -rf "$LOGDIR"
    elif ! rmdir "$LOGDIR" 2>/dev/null; then
        echo "  logs kept in $LOGDIR"
    fi
    return "$rc"
}
trap cleanup_logdir EXIT

# Conditions are tracked independently rather than as a single worsening number.
# They are categories, not severities: taking the max would let drift (2) mask a
# regression (1), and a regression is the one you must not miss.
regression=0
drift=0
refused=0
note() { printf '\n=== %s ===\n' "$1"; }
record() {
    case "$1" in
        1) regression=1 ;;
        2) drift=1 ;;
        3) refused=1 ;;
    esac
    return 0
}

# Utilities present in the corpus, via the shared discovery module.
utilities_all() {
    python3 - <<'PY'
import sys
sys.path.insert(0, "dev")
import corpus
files = corpus.all_filing_jsonld()
corpus.require_nonempty(files, "rate-plan filings")
print(" ".join(sorted({corpus.utility_of(f) for f in files})))
PY
}

touched_utilities() {
    local all staged u out=""
    all=$(utilities_all)
    # ACMRD, not ACMR: a commit that only DELETES a utility's filings still
    # changes that utility's corpus, and excluding D skipped its baseline check
    # entirely. Found when a deletion-only CPAU commit reported "no utility
    # touched" over seven staged CPAU deletions.
    staged=$(git diff --cached --name-only --diff-filter=ACMRD || true)
    for u in $all; do
        if printf '%s\n' "$staged" | grep -q "/$u/"; then out="$out $u"; fi
    done
    echo "$out"
}

run_clojure_gate() {
    note "Clojure consumer path"
    if clojure -M:validate > "$LOGDIR"/clj.log 2>&1; then
        tail -1 "$LOGDIR"/clj.log
    else
        tail -1 "$LOGDIR"/clj.log
        grep '✗' "$LOGDIR"/clj.log || true
        record 1
    fi

    # Resolution asserts that resolving SUCCEEDS; this asserts that the charges
    # a filing declares actually come back. Without it a consumer-side
    # regression that drops a whole class of charge leaves the gate green,
    # which is how 89 recurring charges went missing across all 40 base plans.
    note "Resolution coverage"
    if clojure -M:coverage > "$LOGDIR"/coverage.log 2>&1; then
        tail -1 "$LOGDIR"/coverage.log
    else
        rc=$?
        cat "$LOGDIR"/coverage.log
        record "$rc"
    fi

    # Resolution asserts that resolving succeeds; coverage asserts that the
    # declared charges come back. Neither one looks at the NUMBER. Nothing in
    # this repository did, which is how three NBT compositions resolved to
    # -213, -218 and -260 dollars per kWh with the gate green. This compares
    # every resolved marginal rate against dev/baseline/marginal-rates.edn.
    #
    # AT 21 INSTANTS, not one. One instant is a gate over one hour of one day
    # type of one season: a TOU discriminator moved on four SDG&E filings and
    # was wrong at most hours of most days while the single probed instant, and
    # therefore this gate, was unchanged. The instants and the reason for each
    # are in probe-instants in dev/validate_v020.clj. Widening cost nothing
    # here: 3,021 cells in 4.0s against 159 cells in 5.5s, because load and
    # Malli validation are now cached per filing instead of repeated per
    # resolution.
    #
    # Exit 1 a recorded value moved, 2 cells appeared or vanished, 3 refused.
    # Refusals now include a per-instant denominator: a probe instant that
    # compares no recorded rate refuses rather than riding along green on the
    # strength of the other 18. The gate NEVER re-records: a baseline refreshed
    # whenever it disagrees with the tree asserts only that the tree equals
    # itself. Re-record by hand and review the diff:
    #   clojure -M:validate --record-baseline
    note "Marginal-rate baseline"
    if clojure -M:validate --check-baseline > "$LOGDIR"/marginal.log 2>&1; then
        tail -1 "$LOGDIR"/marginal.log
    else
        rc=$?
        cat "$LOGDIR"/marginal.log
        record "$rc"
    fi

    # The marginal-rate baseline excludes export ledgers, so it cannot see the
    # NBT export grids. This walks a year of segments per vintage and asserts
    # each export ledger resolves to exactly the Price its cell names. A bracket
    # gap admits every Price on the ledger without an error, and a mistyped
    # alternative key withholds every one; both are silent in clj-urpx.
    # Exit 1 a violation, 3 refused.
    #
    # It takes about 50 s, so --fast runs it only when the commit stages an NBT
    # filing, a base plan an NBT modifier composes with, the check, the
    # remodel script, or deps.edn (the clj-urpx pin). --full always runs it.
    note "NBT export cells"
    if [ "$MODE" = "--fast" ] && ! git diff --cached --name-only |
            grep -qE '/nbt/|/e-elec/|/tou-d-prime/|/ev-tou-5/|^dev/check_nbt_export\.clj$|^dev/remodel_nbt\.py$|^deps\.edn$'; then
        echo "  skipped in --fast: nothing staged that it checks"
    elif clojure -M:nbt-export > "$LOGDIR"/nbt-export.log 2>&1; then
        tail -1 "$LOGDIR"/nbt-export.log
    else
        rc=$?
        grep -E '✗|\.\.\.|REFUSED' "$LOGDIR"/nbt-export.log | head -40
        tail -1 "$LOGDIR"/nbt-export.log
        record "$rc"
    fi
}

# The emitted urpx:ScenarioCostModel nodes, merged with the whole corpus, against
# the URPX revision that admits them. PINNED TO cd13ce8a, the head of
# urpx-org/urpx#72, which adds urpx:consumesModifierVersion,
# urpx:selectsProfileAlternative, urpx:name and urpx:description to the closed
# ScenarioCostModelShape. No release carries them yet, so at the corpus's own
# revision the nodes fail on exactly those properties. Move the pin to the
# release tag when #72 ships.
# Exit 1 a violation, 3 refused.
SCM_URPX_REV=cd13ce8a
run_scm_shacl() {
    note "Scenario cost models: SHACL at URPX $SCM_URPX_REV"
    if dev/shacl.sh --merged --urpx-rev "$SCM_URPX_REV" \
           --with reports/scenario-cost-models.jsonld --keys > "$LOGDIR"/scm-shacl.log 2>&1; then
        cat "$LOGDIR"/scm-shacl.log
    else
        rc=$?
        head -40 "$LOGDIR"/scm-shacl.log
        record "$rc"
    fi
}

# Every document with Clojure source under src/ (doc/dsl-source.md), regenerated
# and compared with its committed file byte for byte, in the working tree.
# About 4 s. --full runs the same check inside dev/check_all.py.
# Exit 1 a document differs, is missing or extra, 3 refused.
run_generated() {
    note "Generated from source"
    if python3 dev/check_generated.py > "$LOGDIR"/generated.log 2>&1; then
        tail -1 "$LOGDIR"/generated.log
    else
        rc=$?
        cat "$LOGDIR"/generated.log
        record $rc
    fi
}

# catalog/ rebuilt in memory and compared with the committed files. About 10 s.
# --full runs the generator inside dev/check_all.py, whose drift check catches
# the same difference. Exit 2 the catalog differs, 1 a filing cannot be summarized.
run_catalog() {
    note "Corpus catalog"
    if python3 dev/build_catalog.py --check > "$LOGDIR"/catalog.log 2>&1; then
        tail -1 "$LOGDIR"/catalog.log
    else
        rc=$?
        cat "$LOGDIR"/catalog.log
        record $rc
    fi
}

# The Clojure source under src/, with the hooks clj-urpx exports in its jar
# (copied into .clj-kondo/imports).
run_clj_kondo() {
    note "clj-kondo"
    if command -v clj-kondo >/dev/null 2>&1; then
        if clj-kondo --lint src > "$LOGDIR"/kondo.log 2>&1; then
            tail -1 "$LOGDIR"/kondo.log
        else
            cat "$LOGDIR"/kondo.log
            record 1
        fi
    else
        echo "  clj-kondo not installed; skipped"
    fi
}

case "$MODE" in
--fast)
    run_clojure_gate

    # In --fast too, not only --full. This is the check a NEW filing trips, and
    # a new filing is exactly what the pre-commit gate sees. Catching it at the
    # next audit instead is how 509 of these accumulated.
    note "IRI scope"
    if python3 dev/lint_iri_scope.py > "$LOGDIR"/iriscope.log 2>&1; then
        tail -1 "$LOGDIR"/iriscope.log
    else
        rc=$?
        cat "$LOGDIR"/iriscope.log
        record $rc
    fi

    note "Blank nodes"
    if python3 dev/name_blank_nodes.py --check > "$LOGDIR"/blank.log 2>&1; then
        tail -1 "$LOGDIR"/blank.log
    else
        rc=$?
        cat "$LOGDIR"/blank.log
        record $rc
    fi

    note "Copy agreement"
    if python3 dev/normalize_copies.py --check > "$LOGDIR"/copies.log 2>&1; then
        tail -1 "$LOGDIR"/copies.log
    else
        rc=$?
        cat "$LOGDIR"/copies.log
        record $rc
    fi

    # The other half of copy agreement. normalize_copies compares a fixed list
    # of properties and reconciles them; this compares EVERY property and
    # reconciles nothing. cpau:e-nse-1-2025-09-01 carried a copy-local
    # applicableToRatePlanVersion for five months and neither the copy gate nor
    # any lint could see it, because that property is deliberately off the list.
    note "Copy divergence"
    if python3 dev/lint_copy_divergence.py > "$LOGDIR"/divergence.log 2>&1; then
        tail -1 "$LOGDIR"/divergence.log
    else
        rc=$?
        cat "$LOGDIR"/divergence.log
        record $rc
    fi

    note "Discount subtotals"
    if python3 dev/lint_discount_summaries.py > "$LOGDIR"/discounts.log 2>&1; then
        tail -1 "$LOGDIR"/discounts.log
    else
        rc=$?
        cat "$LOGDIR"/discounts.log
        record $rc
    fi

    # Completeness is asserted in three places: the urpx:CoverageClaim, the
    # [modeling] table in tariff.toml, and the filing itself. Nothing compared
    # them, and they drift in one direction: somebody models a gap, and the
    # sentence that said it was unmodeled stays. Six CARE and FERA filings were
    # in exactly that state, every one corrected by the commit that added the
    # discount as a urpx:multiplier and not one of the six evaluations revised.
    # In --fast because a new or edited filing is what the pre-commit gate sees,
    # and this is the check such a filing trips.
    #
    # Exit 1 a disagreement, 3 refused. Refusals are collapsed denominators: no
    # filings, no manifests, no coverage claims, no urpx:multiplier anywhere in
    # the corpus, no manifest carrying a Modeling deferrals section, a partial
    # claim carrying no evaluation prose, a deferrals section whose body yields
    # no readable item, or a presence claim pointing at a directory that holds
    # no filing. Each leaves the comparison with no second side.
    note "Completeness agreement"
    if python3 dev/lint_completeness_agreement.py > "$LOGDIR"/completeness.log 2>&1; then
        tail -1 "$LOGDIR"/completeness.log
    else
        rc=$?
        cat "$LOGDIR"/completeness.log
        record $rc
    fi

    # What a filing's own prose says about its structure, against that structure.
    # Prose inside a document inherits the trust the data has, and no other check
    # here compares a sentence to the node it sits on. It prints what it declined
    # to judge on every run, because it declines most of what it reads.
    note "Prose versus structure"
    if python3 dev/lint_prose_structure.py > "$LOGDIR"/prose.log 2>&1; then
        head -1 "$LOGDIR"/prose.log
    else
        rc=$?
        cat "$LOGDIR"/prose.log
        record $rc
    fi

    # Every MIDAS identifier the corpus cites, checked against the party segments
    # the snapshot actually publishes. Five were malformed for months and nothing
    # looked: urpx:RatePlanIdentifier models skos:notation as a plain string, so
    # a malformed notation validates exactly as a correct one does and no
    # consumer can tell them apart. The grammar that can is derived from a
    # California snapshot this repository holds, which is why the check lives
    # here and not in clj-urpx. In --fast because a new filing citing a RIN is
    # what the pre-commit gate sees.
    #
    # Fails ONLY on a component that appears in none of the snapshot's records,
    # which is a statement about structure. An identifier that is well formed but
    # absent from the snapshot is reported and does not fail: the snapshot is
    # dated and cannot be refreshed (MIDAS returns 401), so failing on it would
    # gate commits on the freshness of a file nobody can refresh.
    #
    # Exit 1 a malformed identifier, 3 refused. Refusals are collapsed
    # denominators: no snapshot, a snapshot with no identifiers or no derivable
    # segment structure, no filing directories, or a corpus that cites no
    # identifier at all.
    # A filing whose text or brackets say holidays are priced differently must
    # carry a urpx:HolidayCalendar, or record in [modeling].deferrals that it
    # does not. Thirteen TOU filings stated the rule and carried none until 03f5ec3.
    # Exit 1 a filing missing one or a stale allowlist entry, 3 refused.
    note "Holiday calendars"
    if python3 dev/lint_holiday_calendars.py > "$LOGDIR"/holidays.log 2>&1; then
        tail -1 "$LOGDIR"/holidays.log
    else
        rc=$?
        cat "$LOGDIR"/holidays.log
        record $rc
    fi

    # A free-text condition on a Price, PriceSet or PriceDefinition makes
    # mutually exclusive prices read as concurrent; the selection belongs on a
    # urpx:ProfileAlternative. Two event-day filings are allowlisted.
    # Exit 1 a condition in the price layer or a stale allowlist entry, 3 refused.
    note "Price-layer conditions"
    if python3 dev/lint_price_layer_conditions.py > "$LOGDIR"/price-layer.log 2>&1; then
        tail -1 "$LOGDIR"/price-layer.log
    else
        rc=$?
        cat "$LOGDIR"/price-layer.log
        record $rc
    fi

    # Two Prices on one PriceDefinition, tier and TOU period with the same start
    # are one cell to clj-urpx, which reads only one of them.
    # Exit 1 a shared cell, 3 refused.
    note "Price cells"
    if python3 dev/lint_price_cells.py > "$LOGDIR"/price-cells.log 2>&1; then
        tail -1 "$LOGDIR"/price-cells.log
    else
        rc=$?
        cat "$LOGDIR"/price-cells.log
        record $rc
    fi

    # A literal typed xsd:decimal (or another XSD numeric type), explicitly or
    # by @context coercion, whose lexical form that type does not admit, such as
    # "-9e-05"^^xsd:decimal. Read from the raw JSON because rdflib rewrites such
    # a literal on parse, so pyshacl and every rdflib-based check here miss it.
    # Exit 1 an ill-typed literal, 3 refused.
    note "Numeric literals"
    if python3 dev/lint_decimal_literals.py > "$LOGDIR"/numeric.log 2>&1; then
        tail -1 "$LOGDIR"/numeric.log
    else
        rc=$?
        cat "$LOGDIR"/numeric.log
        record $rc
    fi

    note "MIDAS rate identifiers"
    if python3 dev/lint_rate_identifiers.py > "$LOGDIR"/rins.log 2>&1; then
        head -1 "$LOGDIR"/rins.log
    else
        rc=$?
        cat "$LOGDIR"/rins.log
        record $rc
    fi

    # Two implementations of one rule exist: dev/scenario_cost_models.py here and
    # clj-urpx's urpx.scenario-cost-model, which enumerates the same set. Two
    # plausible halves with nothing comparing them is the failure this repository
    # keeps recording, so this compares MEMBERSHIP in both directions, three
    # times: the (base, modifier-set) compositions, the scenario cost models with
    # open ProfileAlternatives dimensions expanded, and the nodes of the committed
    # reports/scenario-cost-models.jsonld against that expanded set. Then each of
    # those nodes against the node clj-urpx builds for the same model, its @id
    # and urpx:name minted by clj-urpx's implementations of this repository's
    # IRI and name rules.
    #
    # BOTH PARAMETERS BELOW ARE PINNED, VISIBLY, AND NEITHER HAS A DEFAULT.
    #
    # --at: every count is a count AT AN INSTANT. A scenario cost model is current
    # when every one of its components is current, so the set is a property of the corpus AT A TIME
    # and not of the corpus. A check enumerating at "now" would pass today and
    # start failing the morning a version is superseded, with a diff that looks
    # like an implementation disagreement and is not; worse, two sides both
    # drifting to "now" can agree while answering a question neither intended.
    # It is $CURRENCY_AT, read from dev/currency-instant.json, which is also the
    # instant reports/scenario-cost-models.jsonld and the other reports judge
    # currency at, so a version filed for a later date is not yet effective in
    # both. It moved from 2026-07-15T17:00 to 2026-10-06T17:00 (the
    # october-weekday-peak probe) when pse:307-2026-10-01 superseded
    # pse:307-2026-05-01.
    #
    # --combine: base alone, or base plus exactly one modifier. NOTHING IN URPX
    # STATES THIS. No property anywhere says two modifiers exclude or combine, so
    # clj-urpx refuses to invent one and takes it as an argument; this repository
    # names the same policy in COMBINE_AT_MOST_ONE_MODIFIER. It is deliberately
    # conservative and knowingly INCOMPLETE, since real customers hold several
    # overlays at once.
    #
    # CHANGING EITHER LITERAL IS A COORDINATED CHANGE ACROSS TWO REPOSITORIES,
    # not an edit to this file. Both sides must move together or the comparison
    # silently starts asserting nothing.
    #
    # The comparison runs or the check fails. A load error, an empty result or a
    # wrong shape FAILS, because "present but produced nothing" must never read
    # as a pass. urpx.scenario-cost-model absent FAILS too, naming whether its
    # 0.35.0 name urpx.arrangements loads instead, and a missing var FAILS naming
    # the var: a rename must not stop the comparison with the gate green.
    #
    # Exit 1 a disagreement or a broken contract, 3 refused.
    note "Scenario cost models: clj-urpx cross-check"
    if python3 dev/cross_check_scenario_cost_models.py \
           --at "$CURRENCY_AT" \
           --combine at-most-one-modifier > "$LOGDIR"/scenario-cost-models.log 2>&1; then
        cat "$LOGDIR"/scenario-cost-models.log
    else
        rc=$?
        cat "$LOGDIR"/scenario-cost-models.log
        record $rc
    fi

    # About 40 s, so --fast runs it only when the commit stages a filing, the
    # emitted document or its generator. --full always runs it.
    if git diff --cached --name-only |
            grep -qE '^us/|^reports/scenario-cost-models\.jsonld$|^dev/scenario_cost_models\.py$|^dev/validate-with-base\.py$|^dev/shacl_gate\.clj$|^dev/shape-exceptions\.json$'; then
        run_scm_shacl
    else
        note "Scenario cost models: SHACL at URPX $SCM_URPX_REV"
        echo "  skipped in --fast: nothing staged that it checks"
    fi

    # corpus.json declares the layout once; every walker it lists must see the
    # same files. Exit 1 a walker disagrees, 3 fewer than two walkers ran.
    note "Corpus walkers agree"
    if python3 dev/check_walkers.py > "$LOGDIR"/walkers.log 2>&1; then
        cat "$LOGDIR"/walkers.log
    else
        rc=$?
        cat "$LOGDIR"/walkers.log
        record $rc
    fi

    run_generated
    run_catalog
    run_clj_kondo

    targets="$*"
    [ -z "$targets" ] && targets=$(touched_utilities)
    if [ -z "$targets" ]; then
        note "Corpus baseline"
        echo "  no utility touched in the staged diff; skipping the corpus check"
    else
        for u in $targets; do
            note "Baseline: $u"
            dev/shacl.sh --check-baseline --utility "$u"
            record $?
        done
    fi
    ;;

--full)
    run_clojure_gate

    note "Generators, schema, drift"
    python3 dev/check_all.py > "$LOGDIR"/checkall.log 2>&1
    ca=$?
    tail -3 "$LOGDIR"/checkall.log
    [ $ca -eq 2 ] && record 2
    [ $ca -eq 1 ] && record 1

    note "Baseline: every merged mode"
    dev/shacl.sh --check-baseline
    record $?

    note "Per-file diagnostic (informational)"
    dev/shacl.sh --per-file 2>/dev/null | tail -1
    echo "  Cross-file references are unresolved in this mode, so failures here"
    echo "  are expected and do not affect the exit code."

    note "IRI scope"
    if python3 dev/lint_iri_scope.py > "$LOGDIR"/iriscope.log 2>&1; then
        tail -1 "$LOGDIR"/iriscope.log
    else
        rc=$?
        cat "$LOGDIR"/iriscope.log
        record $rc
    fi

    note "Blank nodes"
    if python3 dev/name_blank_nodes.py --check > "$LOGDIR"/blank.log 2>&1; then
        tail -1 "$LOGDIR"/blank.log
    else
        rc=$?
        cat "$LOGDIR"/blank.log
        record $rc
    fi

    note "Copy agreement"
    if python3 dev/normalize_copies.py --check > "$LOGDIR"/copies.log 2>&1; then
        tail -1 "$LOGDIR"/copies.log
    else
        rc=$?
        cat "$LOGDIR"/copies.log
        record $rc
    fi

    # The other half of copy agreement. normalize_copies compares a fixed list
    # of properties and reconciles them; this compares EVERY property and
    # reconciles nothing. cpau:e-nse-1-2025-09-01 carried a copy-local
    # applicableToRatePlanVersion for five months and neither the copy gate nor
    # any lint could see it, because that property is deliberately off the list.
    note "Copy divergence"
    if python3 dev/lint_copy_divergence.py > "$LOGDIR"/divergence.log 2>&1; then
        tail -1 "$LOGDIR"/divergence.log
    else
        rc=$?
        cat "$LOGDIR"/divergence.log
        record $rc
    fi

    note "Discount subtotals"
    if python3 dev/lint_discount_summaries.py > "$LOGDIR"/discounts.log 2>&1; then
        tail -1 "$LOGDIR"/discounts.log
    else
        rc=$?
        cat "$LOGDIR"/discounts.log
        record $rc
    fi

    note "Completeness agreement"
    if python3 dev/lint_completeness_agreement.py > "$LOGDIR"/completeness.log 2>&1; then
        tail -1 "$LOGDIR"/completeness.log
    else
        rc=$?
        cat "$LOGDIR"/completeness.log
        record $rc
    fi

    # What a filing's own prose says about its structure, against that structure.
    # Prose inside a document inherits the trust the data has, and no other check
    # here compares a sentence to the node it sits on. It prints what it declined
    # to judge on every run, because it declines most of what it reads.
    note "Prose versus structure"
    if python3 dev/lint_prose_structure.py > "$LOGDIR"/prose.log 2>&1; then
        head -1 "$LOGDIR"/prose.log
    else
        rc=$?
        cat "$LOGDIR"/prose.log
        record $rc
    fi

    # A filing whose text or brackets say holidays are priced differently must
    # carry a urpx:HolidayCalendar, or record in [modeling].deferrals that it
    # does not. Thirteen TOU filings stated the rule and carried none until 03f5ec3.
    # Exit 1 a filing missing one or a stale allowlist entry, 3 refused.
    note "Holiday calendars"
    if python3 dev/lint_holiday_calendars.py > "$LOGDIR"/holidays.log 2>&1; then
        tail -1 "$LOGDIR"/holidays.log
    else
        rc=$?
        cat "$LOGDIR"/holidays.log
        record $rc
    fi

    # A free-text condition on a Price, PriceSet or PriceDefinition makes
    # mutually exclusive prices read as concurrent; the selection belongs on a
    # urpx:ProfileAlternative. Two event-day filings are allowlisted.
    # Exit 1 a condition in the price layer or a stale allowlist entry, 3 refused.
    note "Price-layer conditions"
    if python3 dev/lint_price_layer_conditions.py > "$LOGDIR"/price-layer.log 2>&1; then
        tail -1 "$LOGDIR"/price-layer.log
    else
        rc=$?
        cat "$LOGDIR"/price-layer.log
        record $rc
    fi

    # Two Prices on one PriceDefinition, tier and TOU period with the same start
    # are one cell to clj-urpx, which reads only one of them.
    # Exit 1 a shared cell, 3 refused.
    note "Price cells"
    if python3 dev/lint_price_cells.py > "$LOGDIR"/price-cells.log 2>&1; then
        tail -1 "$LOGDIR"/price-cells.log
    else
        rc=$?
        cat "$LOGDIR"/price-cells.log
        record $rc
    fi

    # A literal typed xsd:decimal (or another XSD numeric type), explicitly or
    # by @context coercion, whose lexical form that type does not admit, such as
    # "-9e-05"^^xsd:decimal. Read from the raw JSON because rdflib rewrites such
    # a literal on parse, so pyshacl and every rdflib-based check here miss it.
    # Exit 1 an ill-typed literal, 3 refused.
    note "Numeric literals"
    if python3 dev/lint_decimal_literals.py > "$LOGDIR"/numeric.log 2>&1; then
        tail -1 "$LOGDIR"/numeric.log
    else
        rc=$?
        cat "$LOGDIR"/numeric.log
        record $rc
    fi

    note "MIDAS rate identifiers"
    if python3 dev/lint_rate_identifiers.py > "$LOGDIR"/rins.log 2>&1; then
        head -1 "$LOGDIR"/rins.log
    else
        rc=$?
        cat "$LOGDIR"/rins.log
        record $rc
    fi

    # Two implementations of one rule exist: dev/scenario_cost_models.py here and
    # clj-urpx's urpx.scenario-cost-model, which enumerates the same set. Two
    # plausible halves with nothing comparing them is the failure this repository
    # keeps recording, so this compares MEMBERSHIP in both directions, three
    # times: the (base, modifier-set) compositions, the scenario cost models with
    # open ProfileAlternatives dimensions expanded, and the nodes of the committed
    # reports/scenario-cost-models.jsonld against that expanded set. Then each of
    # those nodes against the node clj-urpx builds for the same model, its @id
    # and urpx:name minted by clj-urpx's implementations of this repository's
    # IRI and name rules.
    #
    # BOTH PARAMETERS BELOW ARE PINNED, VISIBLY, AND NEITHER HAS A DEFAULT.
    #
    # --at: every count is a count AT AN INSTANT. A scenario cost model is current
    # when every one of its components is current, so the set is a property of the corpus AT A TIME
    # and not of the corpus. A check enumerating at "now" would pass today and
    # start failing the morning a version is superseded, with a diff that looks
    # like an implementation disagreement and is not; worse, two sides both
    # drifting to "now" can agree while answering a question neither intended.
    # It is $CURRENCY_AT, read from dev/currency-instant.json, which is also the
    # instant reports/scenario-cost-models.jsonld and the other reports judge
    # currency at, so a version filed for a later date is not yet effective in
    # both. It moved from 2026-07-15T17:00 to 2026-10-06T17:00 (the
    # october-weekday-peak probe) when pse:307-2026-10-01 superseded
    # pse:307-2026-05-01.
    #
    # --combine: base alone, or base plus exactly one modifier. NOTHING IN URPX
    # STATES THIS. No property anywhere says two modifiers exclude or combine, so
    # clj-urpx refuses to invent one and takes it as an argument; this repository
    # names the same policy in COMBINE_AT_MOST_ONE_MODIFIER. It is deliberately
    # conservative and knowingly INCOMPLETE, since real customers hold several
    # overlays at once.
    #
    # CHANGING EITHER LITERAL IS A COORDINATED CHANGE ACROSS TWO REPOSITORIES,
    # not an edit to this file. Both sides must move together or the comparison
    # silently starts asserting nothing.
    #
    # The comparison runs or the check fails. A load error, an empty result or a
    # wrong shape FAILS, because "present but produced nothing" must never read
    # as a pass. urpx.scenario-cost-model absent FAILS too, naming whether its
    # 0.35.0 name urpx.arrangements loads instead, and a missing var FAILS naming
    # the var: a rename must not stop the comparison with the gate green.
    #
    # Exit 1 a disagreement or a broken contract, 3 refused.
    note "Scenario cost models: clj-urpx cross-check"
    if python3 dev/cross_check_scenario_cost_models.py \
           --at "$CURRENCY_AT" \
           --combine at-most-one-modifier > "$LOGDIR"/scenario-cost-models.log 2>&1; then
        cat "$LOGDIR"/scenario-cost-models.log
    else
        rc=$?
        cat "$LOGDIR"/scenario-cost-models.log
        record $rc
    fi

    run_scm_shacl

    # corpus.json declares the layout once; every walker it lists must see the
    # same files. Exit 1 a walker disagrees, 3 fewer than two walkers ran.
    note "Corpus walkers agree"
    if python3 dev/check_walkers.py > "$LOGDIR"/walkers.log 2>&1; then
        cat "$LOGDIR"/walkers.log
    else
        rc=$?
        cat "$LOGDIR"/walkers.log
        record $rc
    fi

    # Every way the clj-urpx namespace can go missing fails the cross-check above
    # rather than passing it. Exit 1 a case passed.
    note "Cross-check namespace negative fixtures"
    if python3 dev/test_cross_check_namespaces.py > "$LOGDIR"/xc-ns.log 2>&1; then
        tail -1 "$LOGDIR"/xc-ns.log
    else
        cat "$LOGDIR"/xc-ns.log
        record 1
    fi

    # Version dispatch and the shape exceptions, on clj-shacl. The pyshacl
    # versions, dev/test_dispatch.py and dev/test_shape_exceptions.py, run in
    # dev/check_all.py above while pyshacl stays.
    note "Version-dispatch and shape-exception negative fixtures"
    if clojure -M -m test-shacl-gate > "$LOGDIR"/dispatch.log 2>&1; then
        tail -1 "$LOGDIR"/dispatch.log
    else
        cat "$LOGDIR"/dispatch.log
        record 1
    fi

    # Exported filings against urpx-data-sandbox (LAYOUT.md §4.5). Informational:
    # the sandbox changes outside this repository, so its state must not decide
    # this gate. Reads URPX_SANDBOX_CHECKOUT when set, else gh api; an unreachable
    # sandbox is reported as skipped. With no [[sandbox]] record it says so.
    note "Sandbox drift (informational)"
    python3 dev/check_sandbox_drift.py 2>&1 | sed 's/^/  /'
    echo "  This step does not affect the exit code."

    run_clj_kondo

    note "REUSE licensing"
    if command -v reuse >/dev/null 2>&1; then
        if reuse lint > "$LOGDIR"/reuse.log 2>&1; then
            echo "  reuse lint clean"
        else
            tail -4 "$LOGDIR"/reuse.log
            record 1
        fi
    else
        echo "  reuse not installed; skipped"
    fi
    ;;

*)
    echo "usage: dev/gate.sh [--fast [utility...] | --full]" >&2
    exit 3
    ;;
esac

note "Result"
[ $regression -eq 1 ] && echo "  regression: a new violation key, or a failing consumer or lint step"
[ $drift -eq 1 ]      && echo "  tracked-file drift: a generator output was not committed"
[ $refused -eq 1 ]    && echo "  refused: the harness could not produce a meaningful answer"
if [ $((regression + drift + refused)) -eq 0 ]; then
    echo "  green"
    exit 0
fi
# Every condition that fired is printed above. The exit code names the most
# actionable one: a refusal means no result was produced at all, and a
# regression outranks drift because drift is fixed by committing.
[ $refused -eq 1 ] && exit 3
[ $regression -eq 1 ] && exit 1
exit 2
