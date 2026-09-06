#!/usr/bin/env bash
# Draft board + live ESPN pick sync, run from your machine.
#
#   ./draft.sh                       # rebuild the ranking board once
#   ./draft.sh --sync                # board + pull current ESPN picks once
#   ./draft.sh --sync --loop 15      # keep polling ESPN every 15s during the draft
set -euo pipefail
cd "$(dirname "$0")"

load_key() {
  [ -f "$1" ] || return 0
  local line
  line=$(grep -E "^$2=" "$1" | tail -1) || return 0
  [ -n "$line" ] && export "${line?}"
}
for k in DATABASE_URL WEB_CRYPTO_KEY; do
  load_key ../web/.env.local "$k"
  load_key ./.env "$k"
done

[ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/pip -q install --upgrade pip; }
.venv/bin/python -c "import fantasy_ingest" 2>/dev/null || .venv/bin/pip -q install -e .

exec .venv/bin/python -m fantasy_ingest.draft "$@"
