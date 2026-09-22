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

set -uo pipefail

REPO=$(git rev-parse --show-toplevel)
cd "$REPO"

if [ -f "$HOME/env/py/p3newa/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$HOME/env/py/p3newa/bin/activate"
fi

MODE=${1:---fast}
shift || true

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
    staged=$(git diff --cached --name-only --diff-filter=ACMR || true)
    for u in $all; do
        if printf '%s\n' "$staged" | grep -q "/$u/"; then out="$out $u"; fi
    done
    echo "$out"
}

run_clojure_gate() {
    note "Clojure consumer path"
    if clojure -M:validate > /tmp/gate-clj.log 2>&1; then
        tail -1 /tmp/gate-clj.log
    else
        tail -1 /tmp/gate-clj.log
        grep '✗' /tmp/gate-clj.log || true
        record 1
    fi

    # Resolution asserts that resolving SUCCEEDS; this asserts that the charges
    # a filing declares actually come back. Without it a consumer-side
    # regression that drops a whole class of charge leaves the gate green,
    # which is how 89 recurring charges went missing across all 40 base plans.
    note "Resolution coverage"
    if clojure -M:coverage > /tmp/gate-coverage.log 2>&1; then
        tail -1 /tmp/gate-coverage.log
    else
        rc=$?
        cat /tmp/gate-coverage.log
        record "$rc"
    fi

    # Resolution asserts that resolving succeeds; coverage asserts that the
    # declared charges come back. Neither one looks at the NUMBER. Nothing in
    # this repository did, which is how three NBT compositions resolved to
    # -213, -218 and -260 dollars per kWh with the gate green. This compares
    # every resolved marginal rate against dev/baseline/marginal-rates.edn.
    #
    # AT 19 INSTANTS, not one. One instant is a gate over one hour of one day
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
    if clojure -M:validate --check-baseline > /tmp/gate-marginal.log 2>&1; then
        tail -1 /tmp/gate-marginal.log
    else
        rc=$?
        cat /tmp/gate-marginal.log
        record "$rc"
    fi
}

case "$MODE" in
--fast)
    run_clojure_gate

    # In --fast too, not only --full. This is the check a NEW filing trips, and
    # a new filing is exactly what the pre-commit gate sees. Catching it at the
    # next audit instead is how 509 of these accumulated.
    note "IRI scope"
    if python3 dev/lint_iri_scope.py > /tmp/gate-iriscope.log 2>&1; then
        tail -1 /tmp/gate-iriscope.log
    else
        rc=$?
        cat /tmp/gate-iriscope.log
        record $rc
    fi

    note "Blank nodes"
    if python3 dev/name_blank_nodes.py --check > /tmp/gate-blank.log 2>&1; then
        tail -1 /tmp/gate-blank.log
    else
        rc=$?
        cat /tmp/gate-blank.log
        record $rc
    fi

    note "Copy agreement"
    if python3 dev/normalize_copies.py --check > /tmp/gate-copies.log 2>&1; then
        tail -1 /tmp/gate-copies.log
    else
        rc=$?
        cat /tmp/gate-copies.log
        record $rc
    fi

    note "Discount subtotals"
    if python3 dev/lint_discount_summaries.py > /tmp/gate-discounts.log 2>&1; then
        tail -1 /tmp/gate-discounts.log
    else
        rc=$?
        cat /tmp/gate-discounts.log
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
    if python3 dev/lint_completeness_agreement.py > /tmp/gate-completeness.log 2>&1; then
        tail -1 /tmp/gate-completeness.log
    else
        rc=$?
        cat /tmp/gate-completeness.log
        record $rc
    fi

    targets="$*"
    [ -z "$targets" ] && targets=$(touched_utilities)
    if [ -z "$targets" ]; then
        note "Corpus baseline"
        echo "  no utility touched in the staged diff; skipping the corpus check"
    else
        for u in $targets; do
            note "Baseline: $u"
            python3 dev/validate-with-base.py --check-baseline --utility "$u"
            record $?
        done
    fi
    ;;

--full)
    run_clojure_gate

    note "Generators, schema, drift"
    python3 dev/check_all.py > /tmp/gate-checkall.log 2>&1
    ca=$?
    tail -3 /tmp/gate-checkall.log
    [ $ca -eq 2 ] && record 2
    [ $ca -eq 1 ] && record 1

    note "Baseline: every merged mode"
    python3 dev/validate-with-base.py --check-baseline
    record $?

    note "Per-file diagnostic (informational)"
    python3 dev/validate-with-base.py --per-file 2>/dev/null | tail -1
    echo "  Cross-file references are unresolved in this mode, so failures here"
    echo "  are expected and do not affect the exit code."

    note "IRI scope"
    if python3 dev/lint_iri_scope.py > /tmp/gate-iriscope.log 2>&1; then
        tail -1 /tmp/gate-iriscope.log
    else
        rc=$?
        cat /tmp/gate-iriscope.log
        record $rc
    fi

    note "Blank nodes"
    if python3 dev/name_blank_nodes.py --check > /tmp/gate-blank.log 2>&1; then
        tail -1 /tmp/gate-blank.log
    else
        rc=$?
        cat /tmp/gate-blank.log
        record $rc
    fi

    note "Copy agreement"
    if python3 dev/normalize_copies.py --check > /tmp/gate-copies.log 2>&1; then
        tail -1 /tmp/gate-copies.log
    else
        rc=$?
        cat /tmp/gate-copies.log
        record $rc
    fi

    note "Discount subtotals"
    if python3 dev/lint_discount_summaries.py > /tmp/gate-discounts.log 2>&1; then
        tail -1 /tmp/gate-discounts.log
    else
        rc=$?
        cat /tmp/gate-discounts.log
        record $rc
    fi

    note "Completeness agreement"
    if python3 dev/lint_completeness_agreement.py > /tmp/gate-completeness.log 2>&1; then
        tail -1 /tmp/gate-completeness.log
    else
        rc=$?
        cat /tmp/gate-completeness.log
        record $rc
    fi

    note "Version-dispatch negative fixtures"
    if python3 dev/test_dispatch.py > /tmp/gate-dispatch.log 2>&1; then
        tail -1 /tmp/gate-dispatch.log
    else
        cat /tmp/gate-dispatch.log
        record 1
    fi

    note "REUSE licensing"
    if command -v reuse >/dev/null 2>&1; then
        if reuse lint > /tmp/gate-reuse.log 2>&1; then
            echo "  reuse lint clean"
        else
            tail -4 /tmp/gate-reuse.log
            echo "  KNOWN FAILING: tracked by URPXT-gate.5"
            record 1
        fi
    else
        echo "  reuse not installed; skipped (URPXT-gate.5 installs it)"
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
