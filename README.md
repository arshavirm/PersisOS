
# PersisOS

[![Build](https://github.com/arshavirm/PersisOS/actions/workflows/build.yml/badge.svg)](https://github.com/arshavirm/PersisOS/actions/workflows/build.yml)
[![Build PersisOS Server](https://github.com/arshavirm/PersisOS/actions/workflows/server-build.yml/badge.svg)](https://github.com/arshavirm/PersisOS/actions/workflows/server-build.yml)
![Debian](https://img.shields.io/badge/base-Debian%2013-A81D33?logo=debian&logoColor=white)
![Architectures](https://img.shields.io/badge/architectures-amd64%20%7C%20arm64-4B6CB7)

PersisOS is a Debian 13-based operating system available as a polished KDE
Plasma desktop and a headless server edition. The desktop ships with a focused
set of everyday applications and a branded Plasma experience. The server image
provides administration, diagnostics, storage, networking, security, container,
and virtualization tools without a graphical stack.

## Design goals

- **Stable:** PersisOS 2.0 is pinned to Debian 13 (Trixie) and enables the
  matching security and stable-updates repositories.
- **User-friendly:** The live session provides a complete Plasma desktop,
  both Wayland and X11 sessions, modern web browsing, common file formats,
  screenshots, networking, audio, Bluetooth, power and firmware management,
  disk-health monitoring, and a branded graphical installer.
- **Lean:** Packages are installed without automatic recommendations. The
  image includes a deliberately small application set instead of multiple
  programs for the same task.

Package additions should solve a common desktop need, hardware requirement,
security issue, or accessibility problem. Optional specialist applications
belong in the repositories rather than the base image.

## Build

The builder must run as root (or inside the provided CI container) and requires debootstrap, xorriso, squashfs-tools, GRUB, and dosfstools.

```bash
sudo python3 build.py PersisOS-2.0-amd64.json --workdir build --outdir output
```

Use the arm64 configuration for ARM images. Generated files are written to `output/`; temporary build state is kept in `build/` and ignored by Git.

The amd64 server image uses its own manifest and CI workflow:

```bash
sudo python3 build.py PersisOS-Server-2.0-amd64.json \
  --workdir build-server --outdir output-server
```

The server live account is `admin` with password `persisos`. SSH is installed
but intentionally disabled on live media until the administrator changes that
password and enables the service.

## Project layout

- `build.py` — reproducible live ISO builder
- `PersisOS-2.0-*.json` — desktop image definitions
- `PersisOS-Server-2.0-amd64.json` — headless amd64 server image definition
- `assets/` — Plasma, SDDM, icon, and wallpaper branding
- `.github/workflows/` — pull request, branch, and release builds
