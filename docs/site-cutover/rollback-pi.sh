#!/usr/bin/env bash
# ambiance-amplipi :: Pi-side rollback. Run ON the Pi. Instantly returns to the old LMS +
# amplipi + squeezelite stack. The ambiance units are stopped + returned to Phase-0 (safe)
# mode, not deleted -> cutover-pi.sh can re-run later.
set -uo pipefail
A=/home/pi/ambiance-amplipi
U="systemctl --user"
say() { echo "[rollback $(date +%H:%M:%S)] $*"; }

NEW_USER="ambiance-mpd.service ambiance.service ambiance-display.service"
OLD_USER="amplipi.service amplipi-updater.service amplipi-display.service amplipi-tasks.service amplipi-audiodetector.service squeezelite-general.service squeezelite-announce.service alsaloop-resync.service"

say "1/4 stopping ambiance units"
# shellcheck disable=SC2086
$U stop $NEW_USER 2>/dev/null || true
# shellcheck disable=SC2086
$U disable $NEW_USER 2>/dev/null || true

say "2/4 returning Ambiance to Phase-0 (safe) mode"
cat > "$A/config/ambiance.env" <<'EOF'
AMBIANCE_DIR=/home/pi/ambiance-amplipi
AMBIANCE_HW=mock
AMBIANCE_DRY=1
AMBIANCE_PORT=8080
EOF

say "3/4 restoring house.json (newest pre-ambiance backup) + re-enabling the old stack"
newest=$(find /home/pi -maxdepth 3 -name 'house.json.pre-ambiance-*' 2>/dev/null | sort | tail -1)
if [ -n "${newest:-}" ]; then tgt="${newest%%.pre-ambiance-*}"; cp -a "$newest" "$tgt" && say "  restored $tgt"; fi
sudo systemctl enable --now logitechmediaserver.service 2>/dev/null || true
# shellcheck disable=SC2086
$U enable $OLD_USER 2>/dev/null || true
# shellcheck disable=SC2086
$U start  $OLD_USER 2>/dev/null || true

say "4/4 health check"; sleep 2
echo "  logitechmediaserver: $(systemctl is-active logitechmediaserver.service 2>/dev/null)"
for u in $OLD_USER; do printf "  %-28s %s\n" "$u" "$($U is-active "$u" 2>/dev/null)"; done
say "DONE — old stack restored. Run rollback-openhab.sh on the openHAB host too."
