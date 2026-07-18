#!/bin/bash
# Install/upgrade the go-librespot binary for the ambiance-amplipi Spotify Connect source.
# Run ON THE PI as user pi. The binary is a static Go build (no glibc dependency), so it
# runs on this old Buster image; armv6_rpi is the Raspberry-Pi hardfloat build (fine on
# the Pi 3's armv7). NOT committed to git (bin/ is ignored) — this script fetches it.
set -euo pipefail

VERSION="${1:-v0.7.4}"
BASE=/home/pi/ambiance-amplipi
URL="https://github.com/devgianlu/go-librespot/releases/download/${VERSION}/go-librespot_linux_armv6_rpi.tar.gz"

mkdir -p "$BASE/bin"
echo "fetching go-librespot ${VERSION} ..."
curl -fsSL -o /tmp/go-librespot.tar.gz "$URL"
tar -xzf /tmp/go-librespot.tar.gz -C "$BASE/bin" go-librespot
chmod +x "$BASE/bin/go-librespot"
rm -f /tmp/go-librespot.tar.gz
echo "installed -> $BASE/bin/go-librespot"
echo "unit: systemctl --user enable --now ambiance-spotify.service"
