#!/usr/bin/env bash
# Run one ingestion pass from this machine.
#
# UEFA's edge (Akamai) blocks datacenter IPs, so this can't run on GitHub
# Actions / Vercel — it has to run from a residential connection. It reads
# DATABASE_URL + WEB_CRYPTO_KEY from ../web/.env.local (and optional ingest/.env),
# then writes to the same database the hosted app reads.
#
#   ./run.sh --skip-sources  # FAST (~1 min): UEFA data + squad + projections from
#                            #   season xG (cached) + priors + club strength.
#                            #   This is the everyday command.
#   ./run.sh                 # + recent form: each player's last N matches OVERALL
#                            #   (Champions League + domestic league + cups), from
#                            #   Sofascore, for every CL club. Slow-paced with a
#                            #   circuit breaker; fixtures are disk-cached so a
#                            #   re-run only pulls new games and coverage builds
#                            #   run-over-run. First cold run is partial.
#   ./run.sh --matchday 2    # force a matchday
#
# Recent form is never fatal — a source failing just means less fresh data; the
# run always completes and merges the fresh slice over what's stored.
#   1. Sofascore (default): last-N-overall match logs — minutes / xG / xA / goals
#      / rating / role — across every competition, every CL club.
#   2. Understat (RECENT_FORM_SOURCE=both): big-5 domestic logs as a depth layer;
#      the matcher prefers the Sofascore row per player (it has the CL/cup games).
# Tunables: RECENT_FORM_SOURCE (sofascore* | both | understat_only),
#   SOFA_FORM_BUDGET_S (2200), SOFA_FORM_DELAY_S (1.2), RECENT_FORM_LOOKBACK (5),
#   FBREF_SEASON (auto), SOURCE_LEAGUES, RECENT_FORM_MIN_PRICE. `ucl.role_overrides`
#   in settings ({"<uefa id or name>": "FWD"}) hand-fixes role-leverage picks.
set -euo pipefail
cd "$(dirname "$0")"

# Pull specific keys out of the env files without `source`-ing them (the values
# contain $, &, ! and would be mangled or would error under `set -u`).
load_key() {  # load_key FILE KEY
  [ -f "$1" ] || return 0
  local line
  line=$(grep -E "^$2=" "$1" | tail -1) || return 0
  [ -n "$line" ] && export "${line?}"
}
for k in DATABASE_URL WEB_CRYPTO_KEY UEFA_COMP_ID UEFA_FEEDS_BASE UEFA_API_BASE \
         UEFA_ENTITY SOURCE_LEAGUES FBREF_SEASON SKIP_SOURCES \
         RECENT_FORM_SOURCE RECENT_FORM_LOOKBACK RECENT_FORM_MIN_PRICE; do
  load_key ../web/.env.local "$k"
  load_key ./.env "$k"
done

if [ ! -x .venv/bin/python ]; then
  echo "creating venv (first run only)…"
  python3 -m venv .venv
  .venv/bin/python -m pip -q install --upgrade pip
fi

# Ensure deps. The xG scrape needs the heavier [sources] extra; skip it if the
# caller passed --skip-sources.
want_sources=1
for a in "$@"; do [ "$a" = "--skip-sources" ] && want_sources=0; done
if ! .venv/bin/python -c "import fantasy_ingest, curl_cffi" 2>/dev/null; then
  .venv/bin/pip -q install -e .
fi
# The Understat depth layer (RECENT_FORM_SOURCE=both|understat|understat_only)
# needs the heavy stack; the default sofascore path only needs curl_cffi.
case "${RECENT_FORM_SOURCE:-sofascore}" in both|understat|understat_only) us_dep=1 ;; *) us_dep=0 ;; esac
if [ "$want_sources" = 1 ] && [ "$us_dep" = 1 ] \
   && ! .venv/bin/python -c "import soccerdata" 2>/dev/null; then
  echo "installing Understat deps ([sources]) …"
  .venv/bin/pip -q install -e ".[sources]"
fi

exec .venv/bin/python -m fantasy_ingest.run "$@"
