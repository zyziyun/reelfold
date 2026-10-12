#!/usr/bin/env bash
# Decides what a CI run has to do (used by desk-ci.yml and engine.yml), and writes to $GITHUB_OUTPUT:
#   run=true|false   the changed files touch RUN_PATHS (else the jobs are skipped and the aggregator passes as a no-op)
#   full=true|false  the full tier: nightly, tags, release/**, a manual run (unless tier=quick), or FULL_PATHS changed
#   known=true|false the change list was read; it is written to $CHANGED_FILES (default $RUNNER_TEMP/changed.txt) for
#                    select_tests.py, which picks the tests of a quick-tier run from it
# Usage: ci-changes.sh '<RUN_PATHS regex>' '<FULL_PATHS regex>'
# Env: GH_TOKEN, REPO, EVENT, REF, BEFORE, AFTER, PR_BASE, PR_HEAD, TIER. When the change list cannot be read (new
# branch, an API error, 300+ files) it assumes everything changed.
set -euo pipefail
run_re=$1
full_re=$2
run=false
full=false
known=false
changed_out=${CHANGED_FILES:-${RUNNER_TEMP:-/tmp}/changed.txt}
: > "$changed_out"

case "$EVENT" in
  schedule) full=true ;;
  workflow_dispatch) [ "${TIER:-full}" = quick ] || full=true ;;
esac
case "$REF" in
  refs/tags/* | refs/heads/release/*) full=true ;;
esac

range=
if [ "$EVENT" = pull_request ]; then
  range="$PR_BASE...$PR_HEAD"
elif [ "$EVENT" = push ] && [[ "$REF" != refs/tags/* ]] && [[ ! "${BEFORE:-}" =~ ^0*$ ]]; then
  range="$BEFORE...$AFTER"
fi

if [ -z "$range" ]; then
  echo "no diff range for $EVENT on $REF: running everything"
  run=true
elif ! files=$(gh api "repos/$REPO/compare/$range" --jq '.files[].filename'); then
  echo "::warning::could not list the changed files ($range): running everything"
  run=true
  full=true
elif [ "$(printf '%s\n' "$files" | grep -c .)" -ge 300 ]; then
  echo "300+ changed files ($range): running everything"
  run=true
  full=true
else
  echo "changed files ($range):"
  printf '%s\n' "$files" | sed 's/^/  /'
  printf '%s\n' "$files" > "$changed_out"
  known=true
  if printf '%s\n' "$files" | grep -Eq "$run_re"; then run=true; fi
  if printf '%s\n' "$files" | grep -Eq "$full_re"; then full=true; fi
fi

# a tag, release branch, nightly or manual run always runs (path filters do not apply to them)
case "$EVENT" in schedule | workflow_dispatch) run=true ;; esac
case "$REF" in refs/tags/* | refs/heads/release/*) run=true ;; esac
[ "$run" = true ] || full=false

echo "run=$run full=$full known=$known"
{ echo "run=$run"; echo "full=$full"; echo "known=$known"; } >> "$GITHUB_OUTPUT"
