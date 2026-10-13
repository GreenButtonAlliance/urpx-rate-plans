#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Clark Communications Corporation
# SPDX-License-Identifier: MIT
#
# This corpus's bash walker. Reads the layout from corpus.json (needs jq) and
# lists files with git ls-files, so the corpus is what git sees: tracked files
# plus untracked ones that are not ignored.
#
#   dev/corpus.sh              the documents, one repo-relative path per line
#   dev/corpus.sh <kind>...    the files of those kinds
#   dev/corpus.sh --all        every kind, as kind<TAB>path
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

list_kind() {
    jq -r --arg k "$1" '(.kinds[$k].roots // .roots)[] as $r | .kinds[$k].include[] | ":(glob)\($r)/\(.)"' corpus.json |
        while IFS= read -r spec; do
            git ls-files --cached --others --exclude-standard -- "$spec"
        done
}

if [ "$#" -eq 1 ] && [ "$1" = "--all" ]; then
    jq -r '.kinds | keys[]' corpus.json | while IFS= read -r k; do
        list_kind "$k" | awk -v k="$k" '{ print k "\t" $0 }'
    done | LC_ALL=C sort -u
else
    if [ "$#" -eq 0 ]; then
        jq -r '.documents[]' corpus.json
    else
        printf '%s\n' "$@"
    fi | while IFS= read -r k; do list_kind "$k"; done | LC_ALL=C sort -u
fi
