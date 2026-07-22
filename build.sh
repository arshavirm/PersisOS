#!/bin/bash
set -e

DIST=stable
ARCH=amd64
ROOTFS=rootfs
MIRROR=http://deb.debian.org/debian

echo "[1/6] Creating root filesystem..."

sudo rm -rf "$ROOTFS"

sudo debootstrap \
    --arch=$ARCH \
    --variant=minbase \
    $DIST \
    $ROOTFS \
    $MIRROR

echo "[2/6] Mounting filesystems..."

sudo mount --bind /dev $ROOTFS/dev
sudo mount --bind /dev/pts $ROOTFS/dev/pts
sudo mount -t proc proc $ROOTFS/proc
sudo mount -t sysfs sys $ROOTFS/sys
sudo mount -t tmpfs tmpfs $ROOTFS/run

echo "[3/6] Copying files and setup script..."

sudo mkdir -p $ROOTFS/usr/share/backgrounds/persisos/
sudo cp assets/background_1.png $ROOTFS/usr/share/backgrounds/persisos/background_1.png
sudo cp assets/background_2.png $ROOTFS/usr/share/backgrounds/persisos/background_2.png

sudo mkdir -p $ROOTFS/usr/share/pixmaps/persisos
sudo cp persisos.svg $ROOTFS/usr/share/pixmaps/persisos/persisos.svg

sudo cp assets/os-release $ROOTFS/etc/os-release

sudo mkdir -p $ROOTFS/persisos_temp
sudo cp -r assets/xfce4 $ROOTFS/persisos_temp/xfce4
sudo cp -r assets/calamares $ROOTFS/persisos_temp/calamares
sudo cp -r assets/grub.cfg $ROOTFS/persisos_temp/grub.cfg
sudo cp -r assets/calamares-install-persisos.desktop $ROOTFS/persisos_temp/calamares-install-persisos.desktop
sudo cp assets/.face $ROOTFS/persisos_temp/.face
sudo cp assets/lightdm-gtk-greeter.conf $ROOTFS/persisos_temp/lightdm-gtk-greeter.conf

sudo cp chroot.sh $ROOTFS/root/

echo "[4/6] Entering chroot..."

sudo chroot $ROOTFS /bin/bash /root/chroot.sh

echo "[5/6] Cleaning..."

sudo rm $ROOTFS/root/chroot.sh

sudo umount -lf $ROOTFS/dev/pts
sudo umount -lf $ROOTFS/dev
sudo umount -lf $ROOTFS/proc
sudo umount -lf $ROOTFS/sys
sudo umount -lf $ROOTFS/run

echo
echo "Done!"
echo
echo "Your Debian root filesystem is in:"
echo "$ROOTFS"
