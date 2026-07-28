#!/bin/bash
set -e

export DEBIAN_FRONTEND=noninteractive

echo "deb http://deb.debian.org/debian stable main contrib non-free non-free-firmware" > /etc/apt/sources.list

apt update

apt install -y \
    firmware-linux \
    firmware-misc-nonfree \
    linux-image-amd64 \
    live-boot \
    live-config \
    live-config-systemd \
    grub2 \
    memtest86+ \
    shim-signed \
    systemd-sysv \
    dosfstools \
    sudo \
    network-manager \
    network-manager-gnome \
    xorg \
    lightdm \
    lightdm-gtk-greeter \
    xfce4 \
    xfce4-goodies \
    thunar-archive-plugin \
    thunar-volman \
    ristretto \
    mousepad \
    evince \
    pipewire \
    pipewire-pulse \
    wireplumber \
    alsa-utils \
    libspa-0.2-bluetooth \
    pavucontrol \
    wpasupplicant \
    wireless-regdb \
    iw \
    wget \
    p7zip-full \
    zip \
    unzip \
    usbutils \
    pciutils \
    librsvg2-common \
    calamares \
    calamares-settings-debian

echo finished installing packages

wget https://github.com/arshavirm/apadana/releases/download/1.2/apadana_1.2_amd64.deb
apt install ./apadana_1.2_amd64.deb --no-install-recommends
rm apadana_1.2_amd64.deb

sed -i \
    's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' \
    /etc/locale.gen

locale-gen
update-locale LANG=en_US.UTF-8

echo "PersisOS" > /etc/hostname

cat > /etc/hosts <<EOF
127.0.0.1 localhost
127.0.1.1 PersisOS
EOF

mkdir -p /etc/xdg/xfce4
cp -r /persisos_temp/xfce4 /etc/xdg/xfce4

mkdir -p /etc/skel/.config
cp -r /persisos_temp/xfce4 /etc/skel/.config

mkdir -p /root/.config
cp -r /persisos_temp/xfce4 /root/.config

mkdir -p /etc/calamares/branding
cp -r /persisos_temp/calamares/persisos /etc/calamares/branding/persisos
cp -r /persisos_temp/calamares/settings.conf /etc/calamares/settings.conf
cp -r /persisos_temp/calamares/packages.conf /etc/calamares/modules/packages.conf
cp -r /persisos_temp/calamares/packagechooser.conf /etc/calamares/modules/packagechooser.conf


rm /usr/share/applications/calamares*
cp /persisos_temp/calamares-install-persisos.desktop /usr/share/applications/calamares-install-persisos.desktop

mkdir -p /etc/skel/.themes/Persis/gtk-3.0/
cp /persisos_temp/gtk.css /etc/skel/.themes/Persis/gtk-3.0/gtk.css

mkdir -p /root/.themes/Persis/gtk-3.0/
cp /persisos_temp/gtk.css /root/.themes/Persis/gtk-3.0/gtk.css

mkdir -p /boot/grub/
cp /persisos_temp/grub.cfg /boot/grub/grub.cfg

cp /persisos_temp/.face /etc/skel/.face
cp /persisos_temp/.face /root/.face

cp /persisos_temp/lightdm-gtk-greeter.conf /etc/lightdm/lightdm-gtk-greeter.conf

useradd \
    --create-home \
    --shell /bin/bash \
    --groups sudo \
    user

echo "user:user" | chpasswd
echo "root:root" | chpasswd

systemctl enable lightdm
systemctl enable NetworkManager
systemctl enable avahi-daemon

systemd-machine-id-setup

apt autoremove
apt clean

rm -rf /persisos_temp

apt update
update-initramfs -u -k all

