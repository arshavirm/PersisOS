#!/bin/bash
set -e

export DEBIAN_FRONTEND=noninteractive

echo "deb http://deb.debian.org/debian stable main contrib non-free non-free-firmware" > /etc/apt/sources.list

apt update

apt install -y --no-install-recommends \
    firmware-linux \
    linux-image-amd64 \
    live-boot \
    live-config \
    live-config-systemd \
    systemd-sysv \
    grub-pc \
    grub-efi-amd64 \
    shim-signed \
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
    adwaita-icon-theme \
    gnome-icon-theme \
    librsvg2-common \
    thunar \
    thunar-archive-plugin \
    thunar-volman \
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
    plymouth \
    dbus \
    avahi-daemon \
    locales \
    wget \
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

cp /persisos_temp/calamares-install-persisos.desktop /usr/share/applications/calamares-install-persisos.desktop

cp -r /persisos_temp/plymouth/persisos /usr/share/plymouth/themes/
cp /persisos_temp/plymouth/plymouthd.defaults /usr/share/plymouth/plymouthd.defaults
plymouth-set-default-theme persisos

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

