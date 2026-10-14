#!/usr/bin/env bash
# The repository gate. Two modes, because a gate people bypass is not a gate.
#
#   dev/gate.sh --fast [utility...]   the pre-commit gate. The Clojure consumer
#                                     path plus a baseline comparison for each
#                                     touched utility. Utilities are inferred
#                                     from the staged diff when not given.
#                                     dev/gate-steps.toml declares which
#                                     staged paths select each step.
#   dev/gate.sh --full               everything, for a deliberate check before
#                                     a wave lands or a release is cut.
#   dev/gate.sh --changed [BASE]     the --full steps that the branch's
#                                     committed changes since its merge-base
#                                     with BASE (default main) select, through
#                                     the same table. Per-utility SHACL
#                                     baselines for the selected utilities
#                                     stand in for the whole-corpus one unless
#                                     every utility is selected. Refuses a
#                                     working tree or index with tracked
#                                     changes, so it checks what would merge.
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
# named by .nrepl-port when one answers, else in a fresh JVM.

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
# Each step is timed from its note to the next, and the result lists them
# slowest first, so the cost of a gate run is visible where it is spent.
STEP_TIMES=$LOGDIR/step-times
step_key=""
step_name=""
step_start=0
end_step() {
    if [ -n "$step_name" ]; then
        printf '%s\t%s\n' "$((SECONDS - step_start))" "$step_name" >> "$STEP_TIMES"
    fi
    step_name=""
}
# note KEY [HEADING]: KEY names the step in dev/gate-steps.toml; HEADING, when
# the printed heading carries more than the key, is what is printed and timed.
note() {
    end_step
    step_key=$1
    step_name=${2:-$1}
    step_start=$SECONDS
    printf '\n=== %s ===\n' "$step_name"
}
# True when --fast or --changed skips the current step: dev/gate-steps.toml
# gives it triggers and no staged (--fast) or changed (--changed) path matches
# one. A step the table does not name runs.
SKIPPED=""
skipped() {
    case "$MODE" in
        --fast) what=staged ;;
        --changed) what=changed ;;
        *) return 1 ;;
    esac
    printf '%s\n' "$SKIPPED" | grep -qxF -- "$step_key" || return 1
    echo "  skipped in $MODE: nothing $what that it checks"
}
record() {
    case "$1" in
        1) regression=1 ;;
        2) drift=1 ;;
        3) refused=1 ;;
    esac
    return 0
}

run_clojure_gate() {
    note "Clojure consumer path"
    if skipped; then
        :
    elif clojure -M:validate > "$LOGDIR"/clj.log 2>&1; then
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
    if skipped; then
        :
    elif clojure -M:coverage > "$LOGDIR"/coverage.log 2>&1; then
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
    if skipped; then
        :
    elif clojure -M:validate --check-baseline > "$LOGDIR"/marginal.log 2>&1; then
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
    note "NBT export cells"
    if skipped; then
        :
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
    note "Scenario cost models: SHACL" "Scenario cost models: SHACL at URPX $SCM_URPX_REV"
    if skipped; then
        :
    elif dev/shacl.sh --merged --urpx-rev "$SCM_URPX_REV" \
           --with reports/scenario-cost-models.jsonld --keys > "$LOGDIR"/scm-shacl.log 2>&1; then
        cat "$LOGDIR"/scm-shacl.log
    else
        rc=$?
        head -40 "$LOGDIR"/scm-shacl.log
        record "$rc"
    fi
}

# Every document with Clojure source under src/ (doc/dsl-source.md), regenerated
# and compared with its committed file, in the working tree.
# --full runs the same check inside dev/check_all.py.
# Exit 1 a document's RDF differs, or it is missing or extra, 2 the same RDF in
# different bytes (drift), 3 refused. --fast prints that drift without recording
# it, so a commit is blocked only by a semantic difference.
run_generated() {
    note "Generated from source"
    if skipped; then
        :
    elif python3 dev/check_generated.py > "$LOGDIR"/generated.log 2>&1; then
        tail -1 "$LOGDIR"/generated.log
    else
        rc=$?
        cat "$LOGDIR"/generated.log
        if [ "$rc" -eq 2 ] && [ "$MODE" = --fast ]; then
            echo "  drift only, not blocking in --fast: run python3 dev/check_generated.py --write"
        else
            record $rc
        fi
    fi
}

# catalog/ rebuilt in memory and compared with the committed files.
# --full runs the generator inside dev/check_all.py, whose drift check catches
# the same difference. Exit 2 the catalog differs, 1 a filing cannot be summarized.
run_catalog() {
    note "Corpus catalog"
    if skipped; then
        :
    elif python3 dev/build_catalog.py --check > "$LOGDIR"/catalog.log 2>&1; then
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
    if skipped; then
        :
    elif command -v clj-kondo >/dev/null 2>&1; then
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

# The --full steps up to the SHACL baseline, which --full and --changed run in
# their own forms.
run_full_head() {
    run_clojure_gate

    # In --changed, only the dev/check_all.py steps dev/gate-steps.toml selects;
    # schema validation and the drift check run whatever is selected.
    note "Generators, schema, drift"
    if [ "$MODE" = "--changed" ]; then
        for name in $CHECK_ALL_SKIPPED; do
            echo "  $name: skipped in --changed: nothing changed that it checks"
        done
        # shellcheck disable=SC2086
        python3 dev/check_all.py --only $CHECK_ALL_SELECTED > "$LOGDIR"/checkall.log 2>&1
    else
        python3 dev/check_all.py > "$LOGDIR"/checkall.log 2>&1
    fi
    ca=$?
    tail -3 "$LOGDIR"/checkall.log
    echo "  slowest dev/check_all.py steps:"
    grep ' s)$' "$LOGDIR"/checkall.log |
        awk '{ t = $(NF-1); sub(/^\(/, "", t); printf "%s\t%s\n", t, $2 }' |
        sort -t "$(printf '\t')" -k1,1nr | head -5 |
        awk -F '\t' '{ printf "    %6.1f s  %s\n", $1, $2 }'
    [ $ca -eq 3 ] && record 3
    [ $ca -eq 2 ] && record 2
    [ $ca -eq 1 ] && record 1
}

# The --full steps after the SHACL baseline.
run_full_tail() {
    note "Per-file diagnostic (informational)"
    if ! skipped; then
        dev/shacl.sh --per-file 2>/dev/null | tail -1
        echo "  Cross-file references are unresolved in this mode, so failures here"
        echo "  are expected and do not affect the exit code."
    fi

    note "IRI scope"
    if skipped; then
        :
    elif python3 dev/lint_iri_scope.py > "$LOGDIR"/iriscope.log 2>&1; then
        tail -1 "$LOGDIR"/iriscope.log
    else
        rc=$?
        cat "$LOGDIR"/iriscope.log
        record $rc
    fi

    note "Blank nodes"
    if skipped; then
        :
    elif python3 dev/name_blank_nodes.py --check > "$LOGDIR"/blank.log 2>&1; then
        tail -1 "$LOGDIR"/blank.log
    else
        rc=$?
        cat "$LOGDIR"/blank.log
        record $rc
    fi

    note "Copy agreement"
    if skipped; then
        :
    elif python3 dev/normalize_copies.py --check > "$LOGDIR"/copies.log 2>&1; then
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
    if skipped; then
        :
    elif python3 dev/lint_copy_divergence.py > "$LOGDIR"/divergence.log 2>&1; then
        tail -1 "$LOGDIR"/divergence.log
    else
        rc=$?
        cat "$LOGDIR"/divergence.log
        record $rc
    fi

    note "Discount subtotals"
    if skipped; then
        :
    elif python3 dev/lint_discount_summaries.py > "$LOGDIR"/discounts.log 2>&1; then
        tail -1 "$LOGDIR"/discounts.log
    else
        rc=$?
        cat "$LOGDIR"/discounts.log
        record $rc
    fi

    note "Completeness agreement"
    if skipped; then
        :
    elif python3 dev/lint_completeness_agreement.py > "$LOGDIR"/completeness.log 2>&1; then
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
    if skipped; then
        :
    elif python3 dev/lint_prose_structure.py > "$LOGDIR"/prose.log 2>&1; then
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
    if skipped; then
        :
    elif python3 dev/lint_holiday_calendars.py > "$LOGDIR"/holidays.log 2>&1; then
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
    if skipped; then
        :
    elif python3 dev/lint_price_layer_conditions.py > "$LOGDIR"/price-layer.log 2>&1; then
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
    if skipped; then
        :
    elif python3 dev/lint_price_cells.py > "$LOGDIR"/price-cells.log 2>&1; then
        tail -1 "$LOGDIR"/price-cells.log
    else
        rc=$?
        cat "$LOGDIR"/price-cells.log
        record $rc
    fi

    # A literal typed xsd:decimal (or another XSD numeric type), explicitly or
    # by @context coercion, whose lexical form that type does not admit, such as
    # "-9e-05"^^xsd:decimal. Read from the raw JSON because rdflib rewrites such
    # a literal on parse, so every rdflib-based check here misses it.
    # Exit 1 an ill-typed literal, 3 refused.
    note "Numeric literals"
    if skipped; then
        :
    elif python3 dev/lint_decimal_literals.py > "$LOGDIR"/numeric.log 2>&1; then
        tail -1 "$LOGDIR"/numeric.log
    else
        rc=$?
        cat "$LOGDIR"/numeric.log
        record $rc
    fi

    note "MIDAS rate identifiers"
    if skipped; then
        :
    elif python3 dev/lint_rate_identifiers.py > "$LOGDIR"/rins.log 2>&1; then
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
    if skipped; then
        :
    elif python3 dev/cross_check_scenario_cost_models.py \
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
    if skipped; then
        :
    elif python3 dev/check_walkers.py > "$LOGDIR"/walkers.log 2>&1; then
        cat "$LOGDIR"/walkers.log
    else
        rc=$?
        cat "$LOGDIR"/walkers.log
        record $rc
    fi

    # Every way the clj-urpx namespace can go missing fails the cross-check above
    # rather than passing it. Exit 1 a case passed.
    note "Cross-check namespace negative fixtures"
    if skipped; then
        :
    elif python3 dev/test_cross_check_namespaces.py > "$LOGDIR"/xc-ns.log 2>&1; then
        tail -1 "$LOGDIR"/xc-ns.log
    else
        cat "$LOGDIR"/xc-ns.log
        record 1
    fi

    # Version dispatch and the shape exceptions.
    note "Version-dispatch and shape-exception negative fixtures"
    if skipped; then
        :
    elif clojure -M -m test-shacl-gate > "$LOGDIR"/dispatch.log 2>&1; then
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
    if ! skipped; then
        python3 dev/check_sandbox_drift.py 2>&1 | sed 's/^/  /'
        echo "  This step does not affect the exit code."
    fi

    run_clj_kondo

    note "REUSE licensing"
    if skipped; then
        :
    elif command -v reuse >/dev/null 2>&1; then
        if reuse lint > "$LOGDIR"/reuse.log 2>&1; then
            echo "  reuse lint clean"
        else
            tail -4 "$LOGDIR"/reuse.log
            record 1
        fi
    else
        echo "  reuse not installed; skipped"
    fi
}

# Every merged mode against dev/baseline/corpus.json: the whole corpus as one
# graph, and each utility as its own.
run_baseline_corpus() {
    note "Baseline: every merged mode"
    dev/shacl.sh --check-baseline
    record $?
}

# The merged graph of each utility in $targets against its recorded mode. Does
# not include the whole-corpus merged graph, the only mode that can see a new
# cross-utility @id collision.
run_baseline_utilities() {
    for u in $targets; do
        note "Baseline" "Baseline: $u"
        dev/shacl.sh --check-baseline --utility "$u"
        record $?
    done
}

case "$MODE" in
--fast)
    # What the commit changes, against dev/gate-steps.toml. Unfiltered, so a
    # deletion is a change like any other.
    STAGED=$(git diff --cached --name-only --no-renames) || {
        echo "REFUSED: cannot list the staged diff" >&2; exit 3; }
    SKIPPED=$(printf '%s\n' "$STAGED" | python3 dev/gate_steps.py skipped) || {
        echo "REFUSED: dev/gate_steps.py cannot read dev/gate-steps.toml" >&2; exit 3; }

    run_clojure_gate

    # In --fast too, not only --full. This is the check a NEW filing trips, and
    # a new filing is exactly what the pre-commit gate sees. Catching it at the
    # next audit instead is how 509 of these accumulated.
    note "IRI scope"
    if skipped; then
        :
    elif python3 dev/lint_iri_scope.py > "$LOGDIR"/iriscope.log 2>&1; then
        tail -1 "$LOGDIR"/iriscope.log
    else
        rc=$?
        cat "$LOGDIR"/iriscope.log
        record $rc
    fi

    note "Blank nodes"
    if skipped; then
        :
    elif python3 dev/name_blank_nodes.py --check > "$LOGDIR"/blank.log 2>&1; then
        tail -1 "$LOGDIR"/blank.log
    else
        rc=$?
        cat "$LOGDIR"/blank.log
        record $rc
    fi

    note "Copy agreement"
    if skipped; then
        :
    elif python3 dev/normalize_copies.py --check > "$LOGDIR"/copies.log 2>&1; then
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
    if skipped; then
        :
    elif python3 dev/lint_copy_divergence.py > "$LOGDIR"/divergence.log 2>&1; then
        tail -1 "$LOGDIR"/divergence.log
    else
        rc=$?
        cat "$LOGDIR"/divergence.log
        record $rc
    fi

    note "Discount subtotals"
    if skipped; then
        :
    elif python3 dev/lint_discount_summaries.py > "$LOGDIR"/discounts.log 2>&1; then
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
    if skipped; then
        :
    elif python3 dev/lint_completeness_agreement.py > "$LOGDIR"/completeness.log 2>&1; then
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
    if skipped; then
        :
    elif python3 dev/lint_prose_structure.py > "$LOGDIR"/prose.log 2>&1; then
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
    if skipped; then
        :
    elif python3 dev/lint_holiday_calendars.py > "$LOGDIR"/holidays.log 2>&1; then
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
    if skipped; then
        :
    elif python3 dev/lint_price_layer_conditions.py > "$LOGDIR"/price-layer.log 2>&1; then
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
    if skipped; then
        :
    elif python3 dev/lint_price_cells.py > "$LOGDIR"/price-cells.log 2>&1; then
        tail -1 "$LOGDIR"/price-cells.log
    else
        rc=$?
        cat "$LOGDIR"/price-cells.log
        record $rc
    fi

    # A literal typed xsd:decimal (or another XSD numeric type), explicitly or
    # by @context coercion, whose lexical form that type does not admit, such as
    # "-9e-05"^^xsd:decimal. Read from the raw JSON because rdflib rewrites such
    # a literal on parse, so every rdflib-based check here misses it.
    # Exit 1 an ill-typed literal, 3 refused.
    note "Numeric literals"
    if skipped; then
        :
    elif python3 dev/lint_decimal_literals.py > "$LOGDIR"/numeric.log 2>&1; then
        tail -1 "$LOGDIR"/numeric.log
    else
        rc=$?
        cat "$LOGDIR"/numeric.log
        record $rc
    fi

    note "MIDAS rate identifiers"
    if skipped; then
        :
    elif python3 dev/lint_rate_identifiers.py > "$LOGDIR"/rins.log 2>&1; then
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
    if skipped; then
        :
    elif python3 dev/cross_check_scenario_cost_models.py \
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
    if skipped; then
        :
    elif python3 dev/check_walkers.py > "$LOGDIR"/walkers.log 2>&1; then
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
    if [ -z "$targets" ] &&
            ! targets=$(printf '%s\n' "$STAGED" | python3 dev/gate_steps.py utilities Baseline); then
        note "Baseline"
        echo "  REFUSED: dev/gate_steps.py cannot select the touched utilities"
        record 3
    elif [ -z "$targets" ]; then
        printf '\n=== %s ===\n' "Corpus baseline"
        echo "  no utility touched in the staged diff; skipping the corpus check"
    else
        run_baseline_utilities
    fi
    ;;

--full)
    run_full_head
    run_baseline_corpus
    run_full_tail
    ;;

--changed)
    [ $# -le 1 ] || { echo "usage: dev/gate.sh --changed [BASE]" >&2; exit 3; }
    BASE=${1:-main}
    # Committed changes only: with tracked edits outside them, the steps would
    # judge a tree that is not the one that merges.
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "REFUSED: the working tree or index has tracked changes; commit or stash them" >&2
        exit 3
    fi
    MERGE_BASE=$(git merge-base "$BASE" HEAD) || {
        echo "REFUSED: no merge-base between $BASE and HEAD" >&2; exit 3; }
    # --no-renames, so a moved file names both the directory it left and the one
    # it entered.
    CHANGED=$(git diff --name-only --no-renames "$MERGE_BASE" HEAD) || {
        echo "REFUSED: cannot list the changes since $MERGE_BASE" >&2; exit 3; }
    count=$(printf '%s\n' "$CHANGED" | grep -c .)
    printf '\n=== %s ===\n' "Changes against $BASE"
    echo "  $count changed path(s) since merge-base ${MERGE_BASE:0:12}"
    # An empty diff merges nothing, so a finding could only be about BASE
    # itself, which is what --full on BASE checks.
    if [ "$count" -eq 0 ]; then
        echo "  nothing to check"
        exit 0
    fi
    SKIPPED=$(printf '%s\n' "$CHANGED" | python3 dev/gate_steps.py skipped) &&
        CHECK_ALL_SELECTED=$(printf '%s\n' "$CHANGED" | python3 dev/gate_steps.py check-all selected) &&
        CHECK_ALL_SKIPPED=$(printf '%s\n' "$CHANGED" | python3 dev/gate_steps.py check-all skipped) &&
        targets=$(printf '%s\n' "$CHANGED" | python3 dev/gate_steps.py utilities Baseline) &&
        every=$(python3 dev/gate_steps.py corpus-utilities) || {
        echo "REFUSED: dev/gate_steps.py cannot read dev/gate-steps.toml or the corpus" >&2; exit 3; }
    echo "  selected utilities: ${targets:-none}"

    run_full_head
    if [ -z "$targets" ]; then
        printf '\n=== %s ===\n' "Baseline"
        echo "  skipped in --changed: nothing changed that it checks"
    elif [ "$targets" = "$every" ]; then
        run_baseline_corpus
    else
        run_baseline_utilities
    fi
    run_full_tail
    ;;

*)
    echo "usage: dev/gate.sh [--fast [utility...] | --full | --changed [BASE]]" >&2
    exit 3
    ;;
esac

end_step
if [ -s "$STEP_TIMES" ]; then
    printf '\n=== Step times ===\n'
    sort -t "$(printf '\t')" -k1,1nr "$STEP_TIMES" | awk -F '\t' '{ printf "  %5d s  %s\n", $1, $2 }'
    printf '  %5d s  total\n' "$SECONDS"
fi

printf '\n=== %s ===\n' "Result"
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
