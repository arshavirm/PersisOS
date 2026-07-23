#!/bin/bash
set -e

export DEBIAN_FRONTEND=noninteractive

echo "deb http://deb.debian.org/debian stable main contrib non-free non-free-firmware" > /etc/apt/sources.list

apt update

apt install -y \
    firmware-linux \
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
    vlc \
    dbus-x11 \
    calamares \
    calamares-settings-debian

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

sudo mkdir -p /root/.config
sudo cp -r /persisos_temp/xfce4 /root/.config

sudo mkdir -p /etc/calamares/branding
sudo cp -r /persisos_temp/calamares/persisos /etc/calamares/branding/persisos
sudo cp -r /persisos_temp/calamares/settings.conf /etc/calamares/settings.conf
sudo cp -r /persisos_temp/calamares/packages.conf /etc/calamares/modules/packages.conf

sudo rm /usr/share/applications/calamares-install-debian.desktop
sudo cp /persisos_temp/calamares-install-persisos.desktop /usr/share/applications/calamares-install-persisos.desktop

sudo mkdir -p /boot/grub/
sudo cp -r /persisos_temp/grub.cfg /boot/grub/grub.cfg

sudo cp /persisos_temp/.face /etc/skel/.face
sudo cp /persisos_temp/.face /root/.face

sudo cp /persisos_temp/lightdm-gtk-greeter.conf /etc/lightdm/lightdm-gtk-greeter.conf

useradd -m -G sudo -s /bin/bash user

echo "user:user" | chpasswd
echo "root:root" | chpasswd

systemctl enable NetworkManager
systemctl enable lightdm

apt clean

sudo update-initramfs -u -k all

rm -rf /var/lib/apt/lists/*

rm -rd /persisos_temp