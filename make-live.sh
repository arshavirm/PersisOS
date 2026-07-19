#!/bin/bash
set -e

ROOTFS=rootfs
LIVE=live

rm -rf "$LIVE"

mkdir -p "$LIVE/live"

echo "Cleaning..."

sudo rm -rf "$ROOTFS/tmp/"*
sudo rm -rf "$ROOTFS/var/cache/apt/"*
sudo rm -rf "$ROOTFS/var/lib/apt/lists/"*
sudo rm -f "$ROOTFS/etc/machine-id"

sudo touch "$ROOTFS/etc/machine-id"

echo "Creating SquashFS..."

sudo mksquashfs \
    "$ROOTFS" \
    "$LIVE/live/filesystem.squashfs" \
    -comp xz \
    -b 1M \
    -wildcards

echo "Copying kernel..."

sudo cp "$ROOTFS"/boot/vmlinuz-* "$LIVE/vmlinuz"

echo "Copying initrd..."

sudo cp "$ROOTFS"/boot/initrd.img-* "$LIVE/initrd"

echo "Live filesystem complete."