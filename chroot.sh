#!/bin/bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

echo "deb http://deb.debian.org/debian stable main contrib non-free non-free-firmware" > /etc/apt/sources.list

apt-get update

apt-get install -y \
    firmware-linux \
    firmware-linux-free \
    firmware-linux-nonfree \
    firmware-misc-nonfree \
    linux-image-amd64 \
    live-boot \
    live-config \
    live-config-systemd \
    grub2 \
    memtest86+ \
    shim-signed \
    systemd \
    systemd-sysv \
    dosfstools \
    sudo \
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
    wireless-regdb \
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

wget -O apadana_1.2_amd64.deb https://github.com/arshavirm/apadana/releases/download/1.2/apadana_1.2_amd64.deb
apt-get install -y ./apadana_1.2_amd64.deb --no-install-recommends
rm -f apadana_1.2_amd64.deb

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


mkdir -p /etc/xdg/xfce4 /etc/skel/.config/xfce4 /root/.config/xfce4
cp -r /persisos_temp/xfce4/. /etc/xdg/xfce4/
cp -r /persisos_temp/xfce4/. /etc/skel/.config/xfce4/
cp -r /persisos_temp/xfce4/. /root/.config/xfce4/

mkdir -p /usr/share/plymouth/themes/persisos
cp -r /persisos_temp/plymouth/persisos/. /usr/share/plymouth/themes/persisos

plymouth-set-default-theme -R persisos


mkdir -p /etc/calamares/branding
cp -r /persisos_temp/calamares/persisos /etc/calamares/branding/persisos
cp -r /persisos_temp/calamares/settings.conf /etc/calamares/settings.conf
cp -r /persisos_temp/calamares/packages.conf /etc/calamares/modules/packages.conf
cp -r /persisos_temp/calamares/packagechooser.conf /etc/calamares/modules/packagechooser.conf

rm -f /usr/share/applications/calamares*.desktop
rm -f /etc/xdg/autostart/calamares*.desktop
install -Dm644 /persisos_temp/calamares-install-persisos.desktop \
    /usr/share/applications/calamares-install-persisos.desktop
update-desktop-database /usr/share/applications || true

install -Dm644 /persisos_temp/gtk.css /etc/skel/.themes/Persis/gtk-3.0/gtk.css
install -Dm644 /persisos_temp/gtk.css /root/.themes/Persis/gtk-3.0/gtk.css

install -Dm644 /persisos_temp/grub.cfg /boot/grub/grub.cfg

install -Dm644 /persisos_temp/.face /etc/skel/.face
install -Dm644 /persisos_temp/.face /root/.face

install -Dm644 /persisos_temp/lightdm-gtk-greeter.conf /etc/lightdm/lightdm-gtk-greeter.conf

install -Dm644 /persisos_temp/persisos-first-login /usr/local/bin/persisos-first-login
chmod +x /usr/local/bin/persisos-first-login
install -Dm644 /persisos_temp/persisos-first-login.desktop /etc/xdg/autostart/persisos-first-login.desktop

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

apt-get autoremove -y
apt-get clean

rm -rf /persisos_temp

apt-get update
update-initramfs -u -k all
