#!/bin/bash
set -euo pipefail

ROOTFS="rootfs"
LIVE="live"

rm -rf "$LIVE"
mkdir -p "$LIVE/live"

echo "Cleaning..."

sudo rm -rf "${ROOTFS:?}/tmp/"*
sudo rm -rf "${ROOTFS:?}/var/cache/apt/archives/"*.deb
sudo rm -f "$ROOTFS/etc/machine-id"

sudo touch "$ROOTFS/etc/machine-id"

echo "Creating SquashFS..."

# memtest86 binaries are copied out of rootfs/boot separately below and only
# ever needed on the ISO itself, so there's no need to ship them inside the
# live filesystem too.
sudo mksquashfs \
    "$ROOTFS" \
    "$LIVE/live/filesystem.squashfs" \
    -comp xz \
    -b 1M \
    -wildcards \
    -e boot/memtest86*

echo "Copying kernel..."

# Pick the newest kernel/initrd if more than one is installed, instead of
# letting a bare glob silently grab whichever one sorts last.
KERNEL="$(sudo find "$ROOTFS/boot" -maxdepth 1 -name 'vmlinuz-*' | sort -V | tail -n1)"
if [ -z "$KERNEL" ]; then
    echo "Error: no vmlinuz-* found in $ROOTFS/boot" >&2
    exit 1
fi
sudo cp "$KERNEL" "$LIVE/vmlinuz"

echo "Copying initrd..."

INITRD="$(sudo find "$ROOTFS/boot" -maxdepth 1 -name 'initrd.img-*' | sort -V | tail -n1)"
if [ -z "$INITRD" ]; then
    echo "Error: no initrd.img-* found in $ROOTFS/boot" >&2
    exit 1
fi
sudo cp "$INITRD" "$LIVE/initrd"

cp "$ROOTFS"/boot/memtest86*.bin "$LIVE/" 2>/dev/null || echo "Warning: no memtest86 .bin found"
cp "$ROOTFS"/boot/memtest86*.efi "$LIVE/" 2>/dev/null || echo "Warning: no memtest86 .efi found"

echo "Live filesystem complete."
