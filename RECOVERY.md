# Ambiance AmpliPi — Disaster Recovery

If the Pi or its SD card dies, use this. Two paths: **restore an SD image** (fast, exact) or
**rebuild from a blank card** (no image needed). Hardware: a Raspberry Pi 3 + a HiFiBerry-style
I2S DAC + the AmpliPi 6-zone preamp (I2C) + an ILI9341 status screen on the **secondary** SPI bus.

## What lives where
- **This git repo** — the app, all config, systemd units, the ALSA routing
  (`packaging/asound.conf`), the boot overlays (`packaging/boot-config.append.txt`), the pinned
  Python deps (`requirements.txt`) and the setup scripts. Enough to rebuild from scratch.
- **SD images** (if you run `scripts/backup-image.sh` regularly) — on the NAS backup share:
  `//192.168.3.163/back-up/projects/geert hangaar/openhab-backup/ambiance-pi-*.img.gz`.

## Path A — restore the SD image (fastest, exact)
1. Grab the newest `ambiance-pi-*.img.gz` from the NAS share.
2. Write it to a fresh card **at least as large as the original (32 GB)**:
   ```
   gunzip -c ambiance-pi-YYYY-MM-DD.img.gz | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress
   ```
   (or Raspberry Pi Imager → "Use custom image" → the .img.gz.)
3. Put the card in the Pi, reconnect the DAC/preamp/screen, power on. It boots straight into the
   appliance — radio auto-starts, the screen lights up, and `http://<pi>:8080` serves the UI.

## Path B — rebuild from a blank card (no image / new unit)
1. Flash **Raspberry Pi OS 32-bit**, enable SSH, boot, `ssh pi@<pi>`. (Built on Buster / Python
   3.7; the pinned deps target 3.7.)
2. `git clone <this repo> ambiance-amplipi && cd ambiance-amplipi`
3. `./scripts/bootstrap.sh` — apt + Python deps, ALSA routing, boot overlays, services,
   persistent logging, all enabled.
4. `sudo reboot` (required once so the DAC/SPI/I2C overlays load).
5. After reboot: screen on, `http://<pi>:8080` up. Optional Spotify:
   `scripts/install-spotify.sh && systemctl --user enable --now ambiance-spotify`.

## Take a fresh image (do this periodically — an image only helps if it's recent)
`scripts/backup-image.sh` images the partition table + boot + root (it stops at the end of `/`,
so the unused trailing partitions don't bloat it). Mount your NAS/USB and run it ON THE PI:
```
./scripts/backup-image.sh /mnt/backup/ambiance-pi-$(date +%F).img.gz
gzip -t /mnt/backup/ambiance-pi-*.img.gz    # verify
```

## Gotchas (bitten by these)
- **Persistent logs are done with a drop-in, on purpose.** We set `Storage=persistent` in
  `packaging/journald.conf.d/ambiance.conf`, NOT in the main `/etc/systemd/journald.conf`. The
  base AmpliPi image ships a nightly cron (`/usr/local/bin/increment_auto_off.py`) that, if it
  sees `Storage=persistent` in the **main** journald.conf, counts down ~14 nights and reverts it
  to volatile. The drop-in overrides the main conf while that cron reads "volatile" and stays
  inert. **Never set Storage=persistent in the main journald.conf** — always use the drop-in.
- **Reboot after `bootstrap.sh`** — the DAC/SPI/I2C overlays only load at boot.
- **The screen is on the SECONDARY SPI** (SCLK_2/MOSI_2, cs=D44, dc=D39): the `spi1-2cs` /
  `spi2-2cs` + `i2s-gpio28-31` overlays in `boot-config.append.txt` are required.
- **pydantic must stay v1** (<2); the whole stack targets Python 3.7 — don't blind-upgrade.
- The daily `config_*.tgz` in `/home/pi/backups` is **config-only** (a few KB) — it is NOT a
  system backup. Use `backup-image.sh` (image) or Path B (rebuild) for real recovery.
