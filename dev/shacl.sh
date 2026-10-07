#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: CDLA-Permissive-2.0
#
# The gate's SHACL step: dev/shacl.sh [options]. The options, modes and exit
# codes are in the namespace docstring of dev/shacl_gate.clj.
#
# Engine: com.dcj/clj-shacl (Apache Jena) by default. During the comparison
# period URPX_SHACL_ENGINE=pyshacl runs dev/validate-with-base.py instead, with
# the same options, modes, baseline and exit codes.
#
# clj-shacl runs in the nREPL named by .nrepl-port (or URPX_NREPL_PORT) when one
# answers there with com.dcj/clj-shacl on its classpath, and otherwise in a
# fresh JVM. URPX_NREPL_PORT=none forces the fresh JVM.

set -uo pipefail

REPO=$(git rev-parse --show-toplevel)
cd "$REPO" || exit 3

case "${URPX_SHACL_ENGINE:-clj-shacl}" in
    pyshacl)
        exec python3 dev/validate-with-base.py "$@"
        ;;
    clj-shacl)
        ;;
    *)
        echo "REFUSED  URPX_SHACL_ENGINE must be clj-shacl or pyshacl, not '$URPX_SHACL_ENGINE'" >&2
        exit 3
        ;;
esac

port=${URPX_NREPL_PORT:-}
if [ -z "$port" ] && [ -f .nrepl-port ]; then
    port=$(cat .nrepl-port)
fi
if [ -n "$port" ] && [ "$port" != "none" ]; then
    python3 dev/shacl_nrepl.py --port "$port" "$@"
    rc=$?
    # 125: no REPL answered, or it lacks clj-shacl. Anything else is the answer.
    [ "$rc" -ne 125 ] && exit "$rc"
fi
exec clojure -M:shacl "$@"
