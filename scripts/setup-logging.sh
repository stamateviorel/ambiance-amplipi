#!/bin/bash
# Make the ambiance-amplipi logs durable + useful. Run ON THE PI (uses sudo).
#
# The base Raspberry Pi image ships journald Storage=volatile: the journal lives in RAM
# and is wiped on every reboot — exactly the logs you want after a crash/reboot/self-heal.
# This installs a drop-in that makes the journal PERSISTENT and bounded on the SD card,
# then flushes the current in-RAM journal to disk and trims to the cap.
#
# Pairs with access_log=False in asgi.py (already in the app), which keeps the journal
# signal-only instead of ~100k uvicorn access lines/day. Safe to re-run (idempotent).
set -euo pipefail

BASE="${AMBIANCE_DIR:-/home/pi/ambiance-amplipi}"
SRC="$BASE/packaging/journald.conf.d/ambiance.conf"
DST=/etc/systemd/journald.conf.d/ambiance.conf

[ -f "$SRC" ] || { echo "missing $SRC (copy the 'packaging' dir to $BASE)"; exit 1; }

echo "installing journald drop-in -> $DST"
sudo install -D -m 0644 "$SRC" "$DST"
sudo systemctl restart systemd-journald
sudo journalctl --flush
sudo journalctl --vacuum-size=100M

# mpd writes its own log under the app dir, which Debian's stock logrotate rule does not
# cover (it only matches /var/log/mpd/*.log) — without this it grows unbounded.
MPDROT="$BASE/packaging/logrotate.d/ambiance-mpd"
if [ -f "$MPDROT" ]; then
    echo "installing mpd logrotate rule -> /etc/logrotate.d/ambiance-mpd"
    sudo install -D -m 0644 "$MPDROT" /etc/logrotate.d/ambiance-mpd
    sudo logrotate --debug /etc/logrotate.d/ambiance-mpd >/dev/null && echo "   rule parses OK"
fi

echo "done. effective journald Storage (the drop-in overrides the base image):"
grep -rniE "^\s*storage" /etc/systemd/journald.conf /etc/systemd/journald.conf.d/ 2>/dev/null || true
