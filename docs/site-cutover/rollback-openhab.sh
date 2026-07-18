#!/usr/bin/env bash
# ambiance-amplipi :: openHAB-side rollback. Restores the squeezebox/amplipi control surface
# from the backup cutover-openhab.sh recorded, removes ambiance.things, re-enables the things.
set -uo pipefail
JSR=/etc/openhab/automation/jsr223
ITEMS=/etc/openhab/items
THINGS=/etc/openhab/things
BK=$(cat /etc/openhab/misc/audio/.last-ambiance-cutover-backup 2>/dev/null || true)
[ -d "${BK:-}" ] || { echo "ERROR: no recorded cutover backup dir"; exit 1; }

echo "restoring rules + items from $BK"
[ -f "$BK/announcement.js" ]            && cp -f "$BK/announcement.js"            "$JSR/announcement.js"
[ -f "$BK/alarmpanel_output_hooks.js" ] && cp -f "$BK/alarmpanel_output_hooks.js" "$JSR/alarmpanel_output_hooks.js"
[ -f "$BK/music.items" ]                && cp -f "$BK/music.items"                "$ITEMS/music.items"
[ -f "$BK/amplipi.items" ]              && cp -f "$BK/amplipi.items"              "$ITEMS/amplipi.items"

echo "removing ambiance.things + re-enabling squeezebox/amplipi things"
rm -f "$THINGS/ambiance.things"
[ -f "$THINGS/lyron.things.disabled" ]   && mv "$THINGS/lyron.things.disabled"   "$THINGS/lyron.things"
[ -f "$THINGS/amplipi.things.disabled" ] && mv "$THINGS/amplipi.things.disabled" "$THINGS/amplipi.things"

echo "openHAB rolled back to the squeezebox/amplipi bindings; hot-reload in ~1-2 min."
echo "(If needed, the full pre-Ambiance restore point is misc/audio/backups/pre-ambiance-20260717-161003/ — see its RESTORE_INSTRUCTIONS.md)"
