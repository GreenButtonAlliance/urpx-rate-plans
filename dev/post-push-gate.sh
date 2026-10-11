#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
#
# The full gate on a pushed commit, the safety net behind --fast and --changed:
# a trigger missing from dev/gate-steps.toml lets a branch merge green, and this
# run, on everything, is what then catches it. dev/git-hooks/pre-push starts it.
#
#   dev/post-push-gate.sh SHA     run dev/gate.sh --full on SHA
#   dev/post-push-gate.sh --status
#                                 the last run's commit and result
#
# The run uses its own detached worktree, so the checkout it was pushed from is
# never touched, and its own JVMs (URPX_NREPL_PORT=none). Runs queue on a lock,
# one at a time. Logs stay under the repository's git directory, in
# post-push-gate/, one per commit; `latest` names the last one. A failure runs
# the command in `git config urpx.postPushGateNotify`, if set, with the message
# as its one argument.

set -uo pipefail

common=$(git rev-parse --path-format=absolute --git-common-dir) || exit 3
dir="$common/post-push-gate"
mkdir -p "$dir"

if [ "${1:-}" = "--status" ]; then
    if [ -f "$dir/latest" ]; then
        cat "$dir/latest"
    else
        echo "no post-push gate has run"
    fi
    exit 0
fi

sha=$(git rev-parse --verify --quiet "${1:-}^{commit}") || {
    echo "usage: dev/post-push-gate.sh SHA | --status" >&2; exit 3; }
short=${sha:0:7}
log="$dir/$short.log"

# One run at a time. A lock left by a run that died is taken over.
lock="$dir/lock"
until mkdir "$lock" 2>/dev/null; do
    holder=$(cat "$lock/pid" 2>/dev/null || true)
    if [ -n "$holder" ] && ! kill -0 "$holder" 2>/dev/null; then
        rm -rf "$lock"
        continue
    fi
    sleep 30
done
echo $$ > "$lock/pid"

wt="$dir/wt-$short"
cleanup() {
    git worktree remove --force "$wt" > /dev/null 2>&1 || true
    rm -rf "$lock"
}
trap cleanup EXIT

(
    echo "post-push gate: $sha, started $(date '+%Y-%m-%d %H:%M:%S')"
    git worktree add --detach "$wt" "$sha" > /dev/null 2>&1 || {
        echo "REFUSED: cannot create a worktree at $sha"; exit 3; }
    cd "$wt" && URPX_NREPL_PORT=none nice -n 10 dev/gate.sh --full
) > "$log" 2>&1
rc=$?

result="green"
[ "$rc" -ne 0 ] && result="FAILED (exit $rc)"
printf '%s %s %s\n' "$short" "$result" "$log" > "$dir/latest"

if [ "$rc" -ne 0 ]; then
    notify=$(git config urpx.postPushGateNotify || true)
    if [ -n "$notify" ]; then
        sh -c "$notify \"\$1\"" _ "post-push gate on $short $result; log: $log" > /dev/null 2>&1 || true
    fi
fi
exit "$rc"
