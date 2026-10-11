#!/usr/bin/env bash
# Install the systemd --user timers that keep the dashboard's data fresh.
#
# Result: `update.sh --fast` runs every 30 min 08:00-23:00, and a full
# `update.sh` (with the recent-form scrape) runs once at 06:15 — automatically,
# in the background, surviving logout. Logs go to the journal.
#
#   ./deploy/install-timers.sh          # install + enable + start
#   ./deploy/install-timers.sh --status # show timer + last-run status
#   ./deploy/install-timers.sh --remove # stop + uninstall
set -euo pipefail
cd "$(dirname "$0")/.."                 # -> ingest/
SRC="$PWD/deploy"
DST="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNITS=(fantasy-update.service fantasy-update.timer fantasy-update-full.service fantasy-update-full.timer)

case "${1:-install}" in
  --status)
    systemctl --user list-timers 'fantasy-*' --all || true
    echo
    for u in fantasy-update fantasy-update-full; do
      echo "── last run: $u ──"
      systemctl --user status "$u.service" --no-pager -n 8 || true
      echo
    done
    exit 0
    ;;
  --remove)
    systemctl --user disable --now fantasy-update.timer fantasy-update-full.timer 2>/dev/null || true
    for u in "${UNITS[@]}"; do rm -fv "$DST/$u"; done
    systemctl --user daemon-reload
    echo "removed. (linger left enabled; 'loginctl disable-linger $USER' to undo)"
    exit 0
    ;;
esac

# 1. sanity: the thing the timers run must work
[ -x ./update.sh ] || chmod +x ./update.sh
if ! grep -q '^DATABASE_URL=' ../web/.env.local 2>/dev/null; then
  echo "!! ../web/.env.local has no DATABASE_URL — set it up first (see README Deploy)." >&2
  exit 1
fi

# 2. keep --user services running after logout / on boot without a login
if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]; then
  echo "enabling linger so the timers fire even when you're not logged in..."
  if ! sudo -n loginctl enable-linger "$USER" 2>/dev/null && ! sudo loginctl enable-linger "$USER"; then
    NEED_LINGER=1
    echo "  (couldn't get sudo now — timers still work while you're logged in;" >&2
    echo "   run 'sudo loginctl enable-linger $USER' once to cover logout/boot)" >&2
  fi
fi

# 3. install unit files
mkdir -p "$DST"
for u in "${UNITS[@]}"; do install -m 0644 "$SRC/$u" "$DST/$u"; done
systemctl --user daemon-reload
systemctl --user enable --now fantasy-update.timer fantasy-update-full.timer

echo
echo "installed. next runs:"
systemctl --user list-timers 'fantasy-*' --no-pager || true
echo
echo "  logs:        journalctl --user -u fantasy-update -f"
echo "  run now:     systemctl --user start fantasy-update.service"
echo "  full now:    systemctl --user start fantasy-update-full.service"
echo "  status:      ./deploy/install-timers.sh --status"
echo "  remove:      ./deploy/install-timers.sh --remove"
if [ "${NEED_LINGER:-0}" = 1 ]; then
  echo
  echo "  ONE THING LEFT: run this once so it also runs after logout / reboot:"
  echo "      sudo loginctl enable-linger $USER"
fi
