
# PersisOS

[![Build](https://github.com/arshavirm/PersisOS/actions/workflows/build.yml/badge.svg)](https://github.com/arshavirm/PersisOS/actions/workflows/build.yml)
![Debian](https://img.shields.io/badge/base-Debian%2013-A81D33?logo=debian&logoColor=white)
![Architectures](https://img.shields.io/badge/architectures-amd64%20%7C%20arm64-4B6CB7)

PersisOS is a polished KDE Plasma live desktop built on Debian 13. It ships with a focused set of everyday applications, a branded Plasma experience, and secure-by-default services.

## Design goals

- **Stable:** PersisOS 2.0 is pinned to Debian 13 (Trixie) and enables the
  matching security and stable-updates repositories.
- **User-friendly:** The live session provides a complete Plasma desktop,
  modern web browsing, common file formats, screenshots, networking, audio,
  Bluetooth, and a branded graphical installer.
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

## Project layout

- `build.py` — reproducible live ISO builder
- `PersisOS-2.0-*.json` — architecture-specific image definitions
- `assets/` — Plasma, SDDM, icon, and wallpaper branding
- `.github/workflows/` — pull request, branch, and release builds
