#!/usr/bin/env bash
# Set up — or update — the home runner: a clean clone of main, its env file and
# the systemd user timers. Idempotent; safe to re-run.
#
#   infra/home/install.sh                      # env file must already exist
#   infra/home/install.sh --from-env FILE      # first time: copy DATABASE_URL and
#                                              # WEB_CRYPTO_KEY out of FILE
#
# It also retires the previous scheduler (the ingest/ timers and cron lines),
# so only one thing ever writes the database.
set -euo pipefail

here=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
REPO_URL=${REPO_URL:-$(git -C "$here" remote get-url origin)}
RUNNER=$HOME/.local/share/fantasy-dashboard/runner
ENV_DIR=$HOME/.config/fantasy-dashboard
ENV_FILE=$ENV_DIR/env
UNIT_DIR=$HOME/.config/systemd/user

from_env=""
while [ $# -gt 0 ]; do
  case $1 in
    --from-env) from_env=${2:?--from-env needs a file}; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

for cmd in git uv flock curl systemctl; do
  command -v "$cmd" >/dev/null || { echo "missing: $cmd" >&2; exit 1; }
done

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }

say "runner checkout: $RUNNER"
if [ -d "$RUNNER/.git" ]; then
  git -C "$RUNNER" fetch --quiet origin main && git -C "$RUNNER" reset --quiet --hard FETCH_HEAD
else
  mkdir -p "$(dirname "$RUNNER")"
  git clone --quiet --branch main "$REPO_URL" "$RUNNER"
fi

say "environment: $ENV_FILE"
mkdir -p "$ENV_DIR" && chmod 700 "$ENV_DIR"
if [ ! -f "$ENV_FILE" ]; then
  (
    umask 077
    echo "# Fantasy dashboard home runner — secrets stay on this machine."
    echo "# NTFY_TOPIC: an ntfy.sh topic for failure + matchday pushes (optional)."
    for key in DATABASE_URL WEB_CRYPTO_KEY NTFY_TOPIC NTFY_URL; do
      value=""
      [ -n "$from_env" ] && value=$(sed -n "s/^$key=//p" "$from_env" | tail -n 1)
      if [ -n "$value" ]; then echo "$key=$value"; else echo "#$key="; fi
    done
  ) > "$ENV_FILE"
fi
if ! grep -q '^DATABASE_URL=.' "$ENV_FILE"; then
  echo "!! DATABASE_URL is not set in $ENV_FILE — fill it in and re-run." >&2
  exit 1
fi

say "dependencies (from the lockfile)"
(cd "$RUNNER/backend" && uv sync --frozen --quiet --extra jobs --extra sources --extra ml)

# Production builds on Vercel migrate too; doing it here as well means the first
# sync never meets an old schema, whichever side goes first. Idempotent.
say "database schema"
(cd "$RUNNER/backend" && uv run --frozen --no-sync fantasy --env-file "$ENV_FILE" db upgrade)

say "systemd user units"
mkdir -p "$UNIT_DIR"
install -m 644 "$RUNNER"/infra/home/systemd/* "$UNIT_DIR"/
systemctl --user daemon-reload
systemctl --user enable --now fantasy-sync-fast.timer fantasy-sync-full.timer fantasy-sync-live.timer \
  fantasy-ml-train.timer
# fit the FPL model once now, so predictions start with the next sync
systemctl --user start --no-block fantasy-sync@train.service

say "retiring the previous scheduler"
for timer in fantasy-update.timer fantasy-update-full.timer; do
  if systemctl --user is-enabled --quiet "$timer" 2>/dev/null; then
    systemctl --user disable --now "$timer"
    echo "   disabled $timer"
  fi
done
if crontab -l 2>/dev/null | grep -q 'fantasy-dashboard/ingest'; then
  crontab -l | grep -v 'fantasy-dashboard/ingest' | crontab -
  echo "   removed the old cron lines"
fi

# Timers keep firing when you're logged out (they still need the machine awake).
if ! loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q yes; then
  loginctl enable-linger "$USER"
fi

say "done — next runs:"
systemctl --user list-timers 'fantasy-*' --no-pager
echo
echo "Logs:      journalctl --user -u 'fantasy-sync@*' -f"
echo "Run now:   systemctl --user start fantasy-sync@fast"
