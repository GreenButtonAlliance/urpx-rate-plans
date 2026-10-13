#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
#
# The gate's SHACL step: dev/shacl.sh [options]. The options, modes and exit
# codes are in the namespace docstring of dev/shacl_gate.clj.
#
# Engine: com.dcj/clj-shacl (Apache Jena). It runs in the nREPL named by
# .nrepl-port (or URPX_NREPL_PORT) when one answers there with com.dcj/clj-shacl
# on its classpath, and otherwise in a fresh JVM. URPX_NREPL_PORT=none forces the
# fresh JVM.

set -uo pipefail

REPO=$(git rev-parse --show-toplevel)
cd "$REPO" || exit 3

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
