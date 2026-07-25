#!/bin/bash
# ambiance-amplipi — bare-metal bootstrap. Rebuilds the appliance onto a FRESH Raspberry Pi OS
# (32-bit; the unit was built on Buster / Python 3.7). The hardware is a Raspberry Pi Compute
# Module 3+ with soldered eMMC (NO SD card) on the AmpliPi board + a HiFiBerry-style I2S DAC +
# the 6-zone preamp (I2C) + an ILI9341 screen on the secondary SPI bus.
#
# Get an OS onto the eMMC FIRST via rpiboot (see RECOVERY.md "Path B"), then on the Pi:
#   git clone <repo> ambiance-amplipi && cd ambiance-amplipi && ./scripts/bootstrap.sh
#
# Then REBOOT once (the DAC/SPI/I2C overlays only load at boot). See RECOVERY.md.
set -euo pipefail

BASE=/home/pi/ambiance-amplipi
SRC="$(cd "$(dirname "$0")/.." && pwd)"      # this checkout

echo "== 1/7 apt packages =="
sudo apt-get update
sudo apt-get install -y mpd mpc alsa-utils avahi-daemon i2c-tools cifs-utils \
    python3-venv python3-pip python3-dev build-essential libopenjp2-7 git

echo "== 2/7 hardware overlays in config.txt (DAC / I2C / I2S / SPI) =="
BOOT=/boot/config.txt; [ -f /boot/firmware/config.txt ] && BOOT=/boot/firmware/config.txt
if grep -q "hifiberry-dac" "$BOOT"; then
    echo "   overlays already present in $BOOT — skipping"
else
    echo "   appending overlays to $BOOT (reboot required to take effect)"
    sudo tee -a "$BOOT" < "$SRC/packaging/boot-config.append.txt" >/dev/null
fi

echo "== 3/7 ALSA routing (ch0 / ch0boost / dmix -> HiFiBerry) =="
sudo install -m 0644 "$SRC/packaging/asound.conf" /etc/asound.conf

echo "== 4/7 hardware group membership + service linger =="
sudo usermod -aG audio,i2c,spi,gpio pi || true
sudo loginctl enable-linger pi

echo "== 5/7 app + config + Python venv =="
mkdir -p "$BASE"
if [ "$SRC" != "$BASE" ]; then
    cp -r "$SRC"/ambiance "$SRC"/config "$SRC"/assets "$SRC"/systemd "$SRC"/scripts "$SRC"/packaging "$BASE"/
fi
python3 -m venv "$BASE/venv"
"$BASE/venv/bin/pip" install -U "pip<24.1" setuptools wheel   # last pip line that supports 3.7
"$BASE/venv/bin/pip" install -r "$SRC/requirements.txt"

echo "== 6/7 systemd user units + persistent logs =="
mkdir -p ~/.config/systemd/user
cp "$BASE"/systemd/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
"$BASE/scripts/setup-logging.sh"

echo "== 7/7 enable services =="
systemctl --user enable --now ambiance-mpd ambiance ambiance-display
# optional Spotify Connect:
#   "$BASE/scripts/install-spotify.sh" && systemctl --user enable --now ambiance-spotify

echo
echo "DONE.  ==> sudo reboot  <==  so the DAC/SPI/I2C overlays load."
echo "After reboot: the screen lights up and http://<pi>:8080 serves the web UI."
