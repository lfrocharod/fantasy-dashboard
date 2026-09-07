#!/usr/bin/env bash
# Run one ingestion pass from this machine.
#
# UEFA's edge (Akamai) blocks datacenter IPs, so this can't run on GitHub
# Actions / Vercel — it has to run from a residential connection. It reads
# DATABASE_URL + WEB_CRYPTO_KEY from ../web/.env.local (and optional ingest/.env),
# then writes to the same database the hosted app reads.
#
#   ./run.sh                 # public data + your squad + mini-league + xG scrape
#   ./run.sh --skip-sources  # skip the slow FBref/Understat scrape
#   ./run.sh --matchday 2    # force a matchday
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
