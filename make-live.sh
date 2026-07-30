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

sudo mksquashfs \
    "$ROOTFS" \
    "$LIVE/live/filesystem.squashfs" \
    -comp xz \
    -b 1M \
    -wildcards \
    -e boot/memtest86*

echo "Copying kernel..."

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
