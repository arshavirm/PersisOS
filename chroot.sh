#!/bin/bash
set -e

export DEBIAN_FRONTEND=noninteractive

echo "deb http://deb.debian.org/debian stable main contrib non-free non-free-firmware" > /etc/apt/sources.list

apt update

apt install -y \
    linux-image-amd64 \
    live-boot \
    live-config \
    live-config-systemd \
    systemd-sysv \
    grub-pc \
    sudo \
    network-manager \
    xfce4 \
    lightdm \
    lightdm-gtk-greeter \
    xfce4-goodies \
    xorg \
    locales \
    dialog \
    wget \
    curl \
    nano \
    bash-completion \
    plymouth \
    dbus \
    avahi-daemon \
    pulseaudio \
    pavucontrol \
    firefox-esr \
    dbus-x11

echo "en_US.UTF-8 UTF-8" > /etc/locale.gen
locale-gen
update-locale LANG=en_US.UTF-8

echo "PersisOS" > /etc/hostname

cat > /etc/hosts <<EOF
127.0.0.1 localhost
127.0.1.1 PersisOS
EOF

sudo mkdir -p /etc/xdg/xfce4
sudo cp -r /persisos_temp/xfce4 /etc/xdg/xfce4

sudo mkdir -p /etc/skel/.config
sudo cp -r /persisos_temp/xfce4 /etc/skel/.config


useradd -m -G sudo -s /bin/bash user
echo "user:user" | chpasswd

echo "root:root" | chpasswd

systemctl enable NetworkManager
systemctl enable lightdm

apt clean

rm -rf /var/lib/apt/lists/*

rm -rd /persisos_temp