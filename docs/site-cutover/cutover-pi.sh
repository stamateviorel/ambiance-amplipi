#!/usr/bin/env bash
# ambiance-amplipi :: Pi-side cutover. Run ON the Pi (needs sudo for the system LMS unit +
# linger). Stops the old stack, flips Ambiance to LIVE, installs + starts the ambiance units.
# Old stack is DISABLED, not deleted -> rollback-pi.sh brings it straight back.
# PRECONDITION: the alarm is DISARMED and someone is present (this drives audio + the siren).
set -uo pipefail
A=/home/pi/ambiance-amplipi
U="systemctl --user"
say() { echo "[cutover $(date +%H:%M:%S)] $*"; }

OLD_USER="amplipi.service amplipi-updater.service amplipi-display.service amplipi-tasks.service amplipi-audiodetector.service squeezelite-general.service squeezelite-announce.service alsaloop-resync.service radio-mpd.service radio-zonectl.service radio-ttsplay.service radio-radiod.service radio-watchdog.service radio-display.service"
NEW_USER="ambiance-mpd.service ambiance.service ambiance-display.service"
TS=$(date +%Y%m%d-%H%M%S)

say "1/7 backing up house.json (for rollback)"
find /home/pi -maxdepth 3 -name 'house.json' 2>/dev/null | while read -r f; do cp -a "$f" "$f.pre-ambiance-$TS" 2>/dev/null || true; done

say "2/7 stopping the old stack (LMS + amplipi + squeezelite + superseded radio-* daemons)"
sudo systemctl stop logitechmediaserver.service 2>/dev/null || true
# shellcheck disable=SC2086
$U stop $OLD_USER 2>/dev/null || true

say "3/7 disabling the old stack (kept installed; rollback re-enables)"
sudo systemctl disable logitechmediaserver.service 2>/dev/null || true
# shellcheck disable=SC2086
$U disable $OLD_USER 2>/dev/null || true

say "4/7 flipping Ambiance to LIVE (rpi hardware + real audio, mpd -> ch0)"
cat > "$A/config/ambiance.env" <<'EOF'
# LIVE (set by cutover-pi.sh)
AMBIANCE_DIR=/home/pi/ambiance-amplipi
AMBIANCE_HW=rpi
AMBIANCE_DRY=0
AMBIANCE_PORT=8080
EOF
cp -f "$A/config/mpd-live.conf" "$A/config/mpd.conf"

say "5/7 installing + starting the ambiance units"
mkdir -p /home/pi/.config/systemd/user
cp -f "$A/systemd/"*.service /home/pi/.config/systemd/user/
$U daemon-reload
$U start ambiance-mpd.service        # mpd -> ch0 (squeezelite-general released it in step 2)
$U start ambiance.service            # rt.Rpi() resets the preamps — amplipi.service stopped in step 2
$U start ambiance-display.service    # Conflicts=amplipi-display (already stopped)

say "6/7 enabling units + linger (boot-to-radio)"
# shellcheck disable=SC2086
$U enable $NEW_USER 2>/dev/null || true
sudo loginctl enable-linger pi 2>/dev/null || true

say "7/7 default station + health check"
sleep 3
curl -s -X POST http://127.0.0.1:8080/api/radio -H 'Content-Type: application/json' -d '{"station":"VRT Radio 1"}' >/dev/null || true
sleep 1
for u in $NEW_USER; do printf "  %-26s %s\n" "$u" "$($U is-active "$u" 2>/dev/null)"; done
echo "  status:  $(curl -s http://127.0.0.1:8080/api/status | head -c 300)"
echo "  siren selftest: $(curl -s http://127.0.0.1:8080/api/alarm/selftest)"
say "DONE — verify audio in a zone, then run cutover-openhab.sh on the openHAB host."
