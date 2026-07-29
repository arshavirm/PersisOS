#!/bin/bash
set -e

DISTRO="PersisOS"
VERSION="1.0"
ARCH=amd64

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

cp live/memtest86*.efi "$WORK/boot/"
cp live/memtest86*.bin "$WORK/boot/"


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