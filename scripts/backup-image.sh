#!/bin/bash
# Image the WORKING system of this Pi (partition table + boot + root, through the end of /)
# to a gzip'd .img for disaster recovery. Run ON THE PI. It stops at the end of the root
# partition, so unused/empty trailing partitions don't bloat the image.
#
#   ./scripts/backup-image.sh /mnt/backup/ambiance-pi-$(date +%F).img.gz
#
# Restore (to a card at least as large as the original): see RECOVERY.md, e.g.
#   gunzip -c ambiance-pi-YYYY-MM-DD.img.gz | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress
set -euo pipefail

DEST="${1:?usage: backup-image.sh /path/to/ambiance-pi-YYYY-MM-DD.img.gz}"
ROOT=$(findmnt -no SOURCE /)                        # e.g. /dev/mmcblk0p2
RN=$(basename "$ROOT")                              # mmcblk0p2
DISK="/dev/$(lsblk -no PKNAME "$ROOT" | head -1)"   # e.g. /dev/mmcblk0
END=$(( ( $(cat "/sys/class/block/$RN/start") + $(cat "/sys/class/block/$RN/size") ) * 512 ))
MB=$(( (END + 1048575) / 1048576 ))                 # whole MiB, rounded up, through end of /

echo "imaging $DISK 0..$MB MiB (partition table + boot + root) -> $DEST"
sudo dd if="$DISK" bs=1M count="$MB" status=progress | gzip -1 > "$DEST"
echo "done: $(ls -lh "$DEST" | awk '{print $5}')"
echo "verifying gzip integrity ..."; gzip -t "$DEST" && echo "OK: $DEST"
