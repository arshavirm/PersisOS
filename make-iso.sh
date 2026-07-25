#!/bin/bash
set -e

DISTRO="PersisOS"
VERSION="1.0"

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

echo "Copying GRUB configuration..."
cp assets/grub.cfg "$WORK/boot/grub/grub.cfg"

echo "Building ISO..."

grub-mkrescue \
    --compress=xz \
    -o "$OUTPUT/${DISTRO}-${VERSION}.iso" \
    "$WORK"

echo
echo "Done!"
echo "ISO written to:"
echo "  $OUTPUT/${DISTRO}-${VERSION}.iso"