# Ambiance AmpliPi — Disaster Recovery

**Hardware:** a **Raspberry Pi Compute Module 3+ (CM3+)** with **soldered 32 GB eMMC — there is NO
removable SD card** — seated on the AmpliPi controller board, plus a HiFiBerry-style I2S DAC, the
AmpliPi 6-zone preamp (I2C), and an ILI9341 status screen on the *secondary* SPI bus.

Because the boot media is soldered eMMC, **you cannot swap a card**. Recovery is either
**reflash the eMMC over USB (`rpiboot`)** or **replace the Compute Module**. Two data paths:
restore the eMMC image (fast, exact) or rebuild onto a blank eMMC (bootstrap).

## What lives where
- **This git repo** — app, config, systemd units, ALSA routing (`packaging/asound.conf`), boot
  overlays (`packaging/boot-config.append.txt`), pinned deps (`requirements.txt`), scripts.
- **eMMC images** (from `scripts/backup-image.sh`) — on the NAS:
  `//192.168.3.163/back-up/projects/geert hangaar/openhab-backup/ambiance-pi-*.img.gz`
  (first: `ambiance-pi-2026-07-25.img.gz`, 2.8 GB, verified). A full image of the eMMC
  (partition table + boot + root; the `mmcblk0boot0/1` HW boot partitions are unused).

## What you need (physical)
- A computer (Linux/macOS/Windows) with **rpiboot** — `github.com/raspberrypi/usbboot`.
- The AmpliPi controller's **USB "program"/slave port** and its **boot-enable jumper** (puts the
  CM in USB-boot mode instead of booting from eMMC — see the AmpliPi board silkscreen / hardware docs).
- For a **dead module** (not just corrupted eMMC): a spare **CM3+ with 32 GB eMMC** (CM3+/32GB).

## Path A — reflash the eMMC from the image (fast, exact)
1. Power off. Set the board's boot-enable jumper to USB/rpiboot mode; connect its USB program port
   to your computer.
2. On the computer run `sudo rpiboot`. The CM's eMMC enumerates as a USB mass-storage disk
   (e.g. `/dev/sdX` on Linux). **Confirm `/dev/sdX` is the 32 GB eMMC, not your own disk.**
3. Fetch the newest image from the NAS and write it to the eMMC:
   ```
   gunzip -c ambiance-pi-YYYY-MM-DD.img.gz | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress
   ```
   (or Raspberry Pi Imager → "Use custom image" → the `.img.gz` → the eMMC disk.)
4. Remove/reset the boot jumper, disconnect USB, power on. It boots straight into the appliance.

## Path B — rebuild onto a blank eMMC (no image / new module)
For a fresh CM3+ or when there's no usable image.
1. Enter rpiboot mode as above, run `sudo rpiboot`; the eMMC appears as `/dev/sdX`.
2. Write **Raspberry Pi OS 32-bit** to `/dev/sdX` with Raspberry Pi Imager; enable SSH. (The unit
   was built on Buster / Python 3.7; the pinned deps target 3.7.)
3. Reset the jumper, boot, `ssh pi@<pi>`.
4. `git clone <this repo> ambiance-amplipi && cd ambiance-amplipi && ./scripts/bootstrap.sh`
5. `sudo reboot` (so the DAC/SPI/I2C overlays load). Optional Spotify:
   `scripts/install-spotify.sh && systemctl --user enable --now ambiance-spotify`.

## Take a fresh image (do this periodically — an image only helps if it's recent)
Runs **ON THE PI** — no rpiboot needed, it reads its own live eMMC. Mount your NAS/USB first:
```
./scripts/backup-image.sh /mnt/backup/ambiance-pi-$(date +%F).img.gz
gzip -t /mnt/backup/ambiance-pi-*.img.gz    # verify
```
(For THIS site: the Pi mounts the NAS directly — it can reach `192.168.3.163` and has `mount.cifs`;
credentials live on the openHAB host at `/etc/openhab/misc/samba/.smb-backup-credentials`.)

## Gotchas (bitten by these)
- **Persistent logs are done with a drop-in, on purpose.** `Storage=persistent` is set in
  `packaging/journald.conf.d/ambiance.conf`, NOT in the main `/etc/systemd/journald.conf`. The base
  AmpliPi image ships a nightly cron (`/usr/local/bin/increment_auto_off.py`) that, if it sees
  `Storage=persistent` in the **main** journald.conf, counts down ~14 nights and reverts it to
  volatile. The drop-in overrides the main conf while the cron reads "volatile" and stays inert.
  **Never set Storage=persistent in the main journald.conf** — always use the drop-in.
- **Reboot after `bootstrap.sh`** — the DAC/SPI/I2C overlays only load at boot.
- **The screen is on the SECONDARY SPI** (SCLK_2/MOSI_2, cs=D44, dc=D39): the `spi1-2cs` /
  `spi2-2cs` + `i2s-gpio28-31` overlays in `boot-config.append.txt` are required.
- **pydantic must stay v1** (<2); the whole stack targets Python 3.7 — don't blind-upgrade.
- The daily `config_*.tgz` in `/home/pi/backups` is **config-only** (a few KB) — NOT a system
  backup. Use `backup-image.sh` (image) or Path B (rebuild) for real recovery.
