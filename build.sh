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
sudo cp background_1.png $ROOTFS/usr/share/backgrounds/persisos/background_1.png

sudo mkdir -p $ROOTFS/etc/xdg/xfce4/xfconf/xfce-perchannel-xml/
sudo cp xfce4-desktop.xml $ROOTFS/etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-desktop.xml


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
