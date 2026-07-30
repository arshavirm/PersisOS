#!/bin/bash
set -euo pipefail

DIST="${DIST:-stable}"
ARCH="${ARCH:-amd64}"
ROOTFS="${ROOTFS:-rootfs}"
MIRROR="${MIRROR:-http://deb.debian.org/debian}"

if [[ $EUID -eq 0 ]]; then
    echo "Please run this script as a normal user — it calls sudo itself when needed." >&2
    exit 1
fi

cleanup_mounts() {
    local m
    for m in dev/pts dev proc sys run; do
        if mountpoint -q "$ROOTFS/$m" 2>/dev/null; then
            sudo umount -lf "$ROOTFS/$m"
        fi
    done
}

on_error() {
    echo "An error occurred! Cleaning up..." >&2
    cleanup_mounts
    sudo rm -rf "$ROOTFS"
    exit 1
}
trap on_error ERR

echo "[1/6] Creating root filesystem..."

sudo rm -rf "$ROOTFS"

sudo debootstrap \
    --arch="$ARCH" \
    "$DIST" \
    "$ROOTFS" \
    "$MIRROR"

echo "[2/6] Mounting filesystems..."

sudo mount --bind /dev "$ROOTFS/dev"
sudo mount --bind /dev/pts "$ROOTFS/dev/pts"
sudo mount -t proc proc "$ROOTFS/proc"
sudo mount -t sysfs sys "$ROOTFS/sys"
sudo mount -t tmpfs tmpfs "$ROOTFS/run"

echo "[3/6] Copying files and setup script..."

sudo mkdir -p "$ROOTFS/usr/share/backgrounds/persisos/"
sudo cp assets/backgrounds/background_1.png "$ROOTFS/usr/share/backgrounds/persisos/background_1.png"
sudo cp assets/backgrounds/background_2.png "$ROOTFS/usr/share/backgrounds/persisos/background_2.png"
sudo cp assets/backgrounds/maharloo-lake.jpeg "$ROOTFS/usr/share/backgrounds/persisos/maharloo-lake.jpeg"
sudo cp assets/backgrounds/naqsh-e-rostam.jpg "$ROOTFS/usr/share/backgrounds/persisos/naqsh-e-rostam.jpg"

sudo mkdir -p "$ROOTFS/usr/share/pixmaps/persisos"
sudo cp persisos.svg "$ROOTFS/usr/share/pixmaps/persisos/persisos.svg"
sudo cp persisos.svg "$ROOTFS/usr/share/pixmaps/persisos.svg"

sudo cp assets/os-release "$ROOTFS/etc/os-release"
sudo cp assets/os-release "$ROOTFS/usr/lib/os-release"

sudo mkdir -p "$ROOTFS/persisos_temp"
sudo cp -r assets/xfce4 "$ROOTFS/persisos_temp/xfce4"
sudo cp -r assets/calamares "$ROOTFS/persisos_temp/calamares"
sudo cp assets/grub.cfg "$ROOTFS/persisos_temp/grub.cfg"
sudo cp -r assets/plymouth "$ROOTFS/persisos_temp/plymouth"

sudo cp assets/calamares-install-persisos.desktop "$ROOTFS/persisos_temp/calamares-install-persisos.desktop"
sudo cp assets/.face "$ROOTFS/persisos_temp/.face"
sudo cp assets/lightdm-gtk-greeter.conf "$ROOTFS/persisos_temp/lightdm-gtk-greeter.conf"
sudo cp assets/persisos-first-login "$ROOTFS/persisos_temp/persisos-first-login"
sudo cp assets/persisos-first-login.desktop "$ROOTFS/persisos_temp/persisos-first-login.desktop"

sudo cp assets/gtk.css "$ROOTFS/persisos_temp/gtk.css"

sudo cp chroot.sh "$ROOTFS/root/"

echo "[4/6] Entering chroot..."

sudo chroot "$ROOTFS" /bin/bash /root/chroot.sh

echo "[5/6] Cleaning..."

sudo rm -f "$ROOTFS/root/chroot.sh"
cleanup_mounts
trap - ERR

echo "[6/6] Done!"
echo
echo "Your Debian root filesystem is in:"
echo "$ROOTFS"
