#!/usr/bin/env bash
# Refresh EVERY league's data in one go, from this machine.
#
# UEFA's edge and ESPN block datacenter IPs, so this has to run from a home
# connection — not GitHub Actions / Vercel. The web app only reads the database;
# this script is the only thing that writes it.
#
#   ./update.sh            # everyday refresh: CL (with recent-form scrape) + FPL + NFL
#   ./update.sh --fast     # skip the slow Sofascore/Understat scrape (CL ~1 min)
#   ./update.sh --cl       # only Champions League
#   ./update.sh --fpl      # only FPL Draft
#   ./update.sh --nfl      # only NFL
#
# A per-league failure is logged and the others still run. Exit code is non-zero
# if anything failed.
set -uo pipefail
cd "$(dirname "$0")"

FAST=0; ONLY=""
for a in "$@"; do
  case "$a" in
    --fast) FAST=1 ;;
    --cl|--ucl) ONLY="cl" ;;
    --fpl) ONLY="fpl" ;;
    --nfl) ONLY="nfl" ;;
    *) echo "unknown arg: $a" >&2; exit 2 ;;
  esac
done

run() {  # run <label> <cmd...>
  local label=$1; shift
  echo "── $label ──────────────────────────────────────────"
  if "$@"; then
    echo "   ✓ $label"
  else
    echo "   ✗ $label FAILED (exit $?)" >&2
    FAILED="$FAILED $label"
  fi
}

FAILED=""
CL_ARGS=(); [ "$FAST" = 1 ] && CL_ARGS=(--skip-sources)

[ -z "$ONLY" ] || [ "$ONLY" = cl  ] && run "Champions League" ./run.sh "${CL_ARGS[@]}"
[ -z "$ONLY" ] || [ "$ONLY" = fpl ] && run "FPL Draft"        ./draft.sh --sport fpl --sync
[ -z "$ONLY" ] || [ "$ONLY" = nfl ] && run "NFL"              ./draft.sh --sport nfl --sync

echo "────────────────────────────────────────────────────────"
if [ -n "$FAILED" ]; then
  echo "done, with failures:$FAILED"
  exit 1
fi
echo "done — all leagues refreshed $(date '+%Y-%m-%d %H:%M')"
