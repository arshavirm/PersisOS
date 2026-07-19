#!/bin/bash
set -e

DISTRO="PersisOS"
VERSION="1.0"

WORK=iso
OUTPUT=output

rm -rf "$WORK"
mkdir -p "$WORK"
mkdir -p "$OUTPUT"

mkdir -p "$WORK/live"
mkdir -p "$WORK/boot/grub"
mkdir -p "$WORK/EFI/BOOT"

echo "Copying live system..."

cp live/live/filesystem.squashfs "$WORK/live/"
cp live/vmlinuz "$WORK/live/"
cp live/initrd "$WORK/live/"

echo "Creating grub.cfg..."

cat > "$WORK/boot/grub/grub.cfg" <<EOF
set timeout=5
set default=0

menuentry "${DISTRO}" {

    linux /live/vmlinuz boot=live quiet splash

    initrd /live/initrd

}
EOF

echo "Creating EFI image..."

dd if=/dev/zero of=efiboot.img bs=1M count=20

mkfs.vfat efiboot.img

mkdir -p efimount

sudo mount efiboot.img efimount

sudo mkdir -p efimount/EFI/BOOT

sudo grub-mkstandalone \
    -O x86_64-efi \
    --modules="part_gpt part_msdos fat iso9660 normal linux configfile search search_fs_file search_label search_fs_uuid efi_gop efi_uga gfxterm all_video font" \
    --output=BOOTX64.EFI \
    "boot/grub/grub.cfg=$WORK/boot/grub/grub.cfg"

sudo cp BOOTX64.EFI efimount/EFI/BOOT/

sudo umount efimount

rm -rf efimount

mv efiboot.img "$WORK/EFI/"

echo "Building ISO..."

grub-mkrescue \
    -o "$OUTPUT/${DISTRO}-${VERSION}.iso" \
    "$WORK"

echo
echo "ISO created:"
echo
echo "$OUTPUT/${DISTRO}-${VERSION}.iso"