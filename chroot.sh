#!/bin/bash
set -e

export DEBIAN_FRONTEND=noninteractive

echo "deb http://deb.debian.org/debian stable main contrib non-free non-free-firmware" > /etc/apt/sources.list

apt update

apt install -y --no-install-recommends \
    firmware-linux \
    firmware-linux-free \
    firmware-linux-nonfree \
    firmware-misc-nonfree \
    linux-image-amd64 \
    live-boot \
    live-config \
    live-config-systemd \
    grub-efi-amd64 \
    shim-signed \
    systemd-sysv \
    e2fsprogs \
    dosfstools \
    udev \
    dbus-x11 \
    sudo \
    network-manager \
    network-manager-gnome \
    xorg \
    xfce4 \
    lightdm \
    lightdm-gtk-greeter \
    xfce4-terminal \
    xfce4-screenshooter \
    xfce4-power-manager \
    xfce4-battery-plugin \
    adwaita-icon-theme \
    adwaita-icon-theme-legacy \
    gtk2-engines-pixbuf \
    gtk2-engines-murrine \
    librsvg2-common \
    thunar \
    thunar-archive-plugin \
    thunar-volman \
    tumbler \
    gvfs \
    gvfs-backends \
    udisks2 \
    mousepad \
    ristretto \
    evince \
    file-roller \
    p7zip-full \
    firefox-esr \
    vlc \
    pipewire \
    pipewire-pulse \
    wireplumber \
    pavucontrol \
    dbus \
    avahi-daemon \
    locales \
    wget \
    ca-certificates \
    curl \
    nano \
    less \
    bash-completion \
    unzip \
    zip \
    xz-utils \
    usbutils \
    pciutils \
    calamares \
    calamares-settings-debian

echo finished installing packages

wget https://github.com/arshavirm/apadana/releases/download/1.1/apadana_1.1_amd64.deb
apt install ./apadana_1.1_amd64.deb --no-install-recommends
rm apadana_1.1_amd64.deb

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

rm /usr/share/applications/calamares*
cp /persisos_temp/calamares-install-persisos.desktop /usr/share/applications/calamares-install-persisos.desktop

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

systemctl enable NetworkManager
systemctl enable lightdm

apt clean

rm -rf /persisos_temp

update-initramfs -u -k all

