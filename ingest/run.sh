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
#   ./run.sh                 # + the slow Understat/Sofascore scrape for recent
#                            #   form (hot streaks, role checks). Best-effort and
#                            #   time-boxed — SOFA_FORM_BUDGET_S=600 to allow more.
#   ./run.sh --matchday 2    # force a matchday
#
# Recent-form scraping is fragile (Sofascore throttles a busy IP). It is now:
#   - prioritised by ownership/price, so the budget covers players that matter;
#   - merged over everything already stored in `player_form` (upsert store), so a
#     partial run keeps prior coverage instead of shrinking the pool;
#   - backed by a UEFA-minutes start-probability prior for every player, so even
#     a fully-throttled run still separates nailed starters from fringe.
# Tunables: SOFA_FORM_BUDGET_S (default 600), RECENT_FORM_MIN_PRICE (default 4.5).
# Set `ucl.role_overrides` in settings ({"<uefa id or name>": "FWD"}) to hand-fix
# the handful of role-leverage picks (e.g. Raphinha).
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
# The Understat fallback (RECENT_FORM_SOURCE=understat) needs the heavy stack.
if [ "$want_sources" = 1 ] && [ "${RECENT_FORM_SOURCE:-sofascore}" = "understat" ] \
   && ! .venv/bin/python -c "import soccerdata" 2>/dev/null; then
  echo "installing Understat deps ([sources]) …"
  .venv/bin/pip -q install -e ".[sources]"
fi

exec .venv/bin/python -m fantasy_ingest.run "$@"
