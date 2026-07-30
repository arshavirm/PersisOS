#!/bin/bash
set -euo pipefail

DISTRO="PersisOS"
VERSION="1.0"
ARCH="amd64"

WORK="iso"
OUTPUT="output"

echo "Cleaning..."
rm -rf "$WORK"
mkdir -p "$WORK"/{boot/grub,live}
mkdir -p "$OUTPUT"

echo "Copying live system..."
cp live/live/filesystem.squashfs "$WORK/live/"
cp live/vmlinuz "$WORK/live/"
cp live/initrd "$WORK/live/"

for f in live/memtest86*.efi live/memtest86*.bin; do
    if [ -e "$f" ]; then
        cp "$f" "$WORK/boot/"
    else
        echo "Warning: $f not found, skipping" >&2
    fi
done

echo "Copying GRUB configuration..."
cp assets/grub.cfg "$WORK/boot/grub/grub.cfg"

echo "Building ISO..."

grub-mkrescue \
    --compress=xz \
    -o "$OUTPUT/${DISTRO}-${VERSION}-${ARCH}.iso" \
    "$WORK"

echo
echo "Done!"
echo "ISO written to:"
echo "  $OUTPUT/${DISTRO}-${VERSION}-${ARCH}.iso"
