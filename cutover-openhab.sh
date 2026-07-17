#!/usr/bin/env bash
# ambiance-amplipi :: openHAB-side cutover. Run on the openHAB host AFTER the Pi is live
# (cutover-pi.sh). Points the whole music control surface at the ambianceamplipi binding, so
# the existing SqueezeMultiZoneControl widget + music_motion_control keep working unchanged.
# Backed up first; rollback-openhab.sh restores it. Hot-reloads (expect a 1-2 min rule cascade).
set -uo pipefail
SRC=/home/openhab/work/ambiance-amplipi/openhab
JSR=/etc/openhab/automation/jsr223
ITEMS=/etc/openhab/items
THINGS=/etc/openhab/things
BK=/etc/openhab/misc/audio/pre-ambiance-cutover-$(date +%Y%m%d-%H%M%S)
mkdir -p "$BK"

echo "1/4 backing up"
for f in "$JSR/announcement.js" "$JSR/alarmpanel_output_hooks.js" "$JSR/radio_bridge.js" \
         "$ITEMS/music.items" "$ITEMS/amplipi.items" \
         "$THINGS/lyron.things" "$THINGS/amplipi.things"; do
  [ -f "$f" ] && cp -a "$f" "$BK/" && echo "   $(basename "$f")"
done
echo "$BK" > /etc/openhab/misc/audio/.last-ambiance-cutover-backup

echo "2/4 rules (announce -> audio sink; siren -> Ambiance_Siren)"
cp -f "$SRC/announcement.js"            "$JSR/announcement.js"
cp -f "$SRC/alarmpanel_output_hooks.js" "$JSR/alarmpanel_output_hooks.js"
rm -f "$JSR/radio_bridge.js"            # remove the daemon-era bridge if it was ever deployed

echo "3/4 items (rebound to ambianceamplipi channels) + things"
cp -f "$SRC/music.items"   "$ITEMS/music.items"
cp -f "$SRC/amplipi.items" "$ITEMS/amplipi.items"
cp -f "$SRC/ambiance.things" "$THINGS/ambiance.things"

echo "4/4 disabling the dead squeezebox + amplipi things"
[ -f "$THINGS/lyron.things" ]   && mv "$THINGS/lyron.things"   "$THINGS/lyron.things.disabled"
[ -f "$THINGS/amplipi.things" ] && mv "$THINGS/amplipi.things" "$THINGS/amplipi.things.disabled"

echo "openHAB cutover done. The widget items are now driven by the ambianceamplipi binding. Backup: $BK"
