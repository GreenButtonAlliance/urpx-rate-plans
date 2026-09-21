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
