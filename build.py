#!/usr/bin/env python3
"""
Simple ISO build script for Debian-based live systems.

Usage: sudo python3 build.py [config.json]
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Load configuration
config_file = sys.argv[1] if len(sys.argv) > 1 else "config.json"
with open(config_file) as f:
    cfg = json.load(f)

# Resolve paths relative to config file location
base_dir = Path(config_file).parent.resolve()
def resolve_path(p):
    path = Path(p)
    return path if path.is_absolute() else (base_dir / path).resolve()

paths = cfg["paths"]
PROJECT_DIR = base_dir
ASSETS_DIR = resolve_path(paths["assets_dir"])
ROOTFS_DIR = resolve_path(paths["rootfs_dir"])
LIVE_DIR = resolve_path(paths["live_dir"])
ISO_WORK_DIR = resolve_path(paths["iso_work_dir"])
OUTPUT_DIR = resolve_path(paths["output_dir"])

distro = cfg["distro"]
debian = cfg["debian"]
packages = cfg["packages"]
accounts = cfg.get("accounts", {})
services = cfg.get("services", [])
files = cfg.get("files", [])
cleanup_globs = cfg.get("cleanup_globs", [])
hooks = cfg.get("hooks", [])

def log(msg):
    print(f"[INFO] {msg}")

def die(msg):
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)

def run(cmd, **kwargs):
    log(" ".join(cmd))
    subprocess.run(cmd, check=True, **kwargs)

def is_mounted(path):
    return subprocess.run(["mountpoint", "-q", str(path)]).returncode == 0

def cleanup_mounts(rootfs):
    for m in ["dev/pts", "dev", "proc", "sys", "run"]:
        target = rootfs / m
        if is_mounted(target):
            run(["umount", "-lf", str(target)])

def run_hooks(point, chroot=False):
    """Run hooks at a given point. If chroot=True, run inside chroot."""
    for hook in hooks:
        if hook["point"] == point and hook.get("enabled", True):
            log(f"Running hook: {hook['name']}")
            if chroot:
                script = f"chroot {ROOTFS_DIR} /bin/bash -c {subprocess.list2cmdline(['/bin/bash', '-c', hook['script']])}"
                # Write hook script to temp file in rootfs
                hook_script = ROOTFS_DIR / f"tmp/hook_{hook['name'].replace(' ', '_')}.sh"
                hook_script.parent.mkdir(parents=True, exist_ok=True)
                hook_script.write_text(hook["script"])
                hook_script.chmod(0o755)
                run(["chroot", str(ROOTFS_DIR), str(hook_script)])
                hook_script.unlink()
            else:
                env = os.environ.copy()
                env.update({
                    "PROJECT_DIR": str(PROJECT_DIR),
                    "ASSETS_DIR": str(ASSETS_DIR),
                    "ROOTFS_DIR": str(ROOTFS_DIR),
                    "LIVE_DIR": str(LIVE_DIR),
                    "ISO_WORK_DIR": str(ISO_WORK_DIR),
                    "OUTPUT_DIR": str(OUTPUT_DIR),
                    "DISTRO_NAME": distro["name"],
                    "DISTRO_VERSION": distro["version"],
                    "DISTRO_HOSTNAME": distro["hostname"],
                    "DEBIAN_ARCH": debian["arch"],
                    "DEBIAN_DIST": debian["dist"],
                })
                subprocess.run(["bash", "-c", hook["script"]], check=True, cwd=str(PROJECT_DIR), env=env)

def copy_files(stage):
    """Copy files from manifest for given stage (before_chroot or after_chroot)."""
    entries = [f for f in files if f.get("stage") == stage]
    for entry in entries:
        src = PROJECT_DIR / entry["src"]
        dest = ROOTFS_DIR / entry["dest"].lstrip("/")
        if not src.exists():
            die(f"Source not found: {src}")
        
        entry_type = entry.get("type") or ("dir" if src.is_dir() else "file")
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        if entry_type == "dir":
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)
        
        if "mode" in entry:
            perm = int(entry["mode"], 8)
            if entry_type == "dir":
                for root, _dirs, fs in os.walk(dest):
                    for name in fs:
                        os.chmod(os.path.join(root, name), perm)
            else:
                os.chmod(dest, perm)

def write_text_configs():
    """Write hostname, hosts, network, and other text configs."""
    hostname = distro["hostname"]
    
    def write(rel_path, content, mode=0o644):
        p = ROOTFS_DIR / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        os.chmod(p, mode)
    
    log("Writing system configuration files...")
    write("etc/hostname", hostname + "\n")
    write("etc/hosts", f"127.0.0.1 localhost\n127.0.1.1 {hostname}\n")
    write("etc/network/interfaces", "auto lo\niface lo inet loopback\n")
    write("etc/apt/apt.conf.d/99parallel", 'Acquire::Queue-Host-Limit "6";\nAcquire::http::Pipeline-Depth "10";\n')
    write("etc/NetworkManager/conf.d/10-globally-managed-devices.conf", "[ifupdown]\nmanaged=true\n")
    write("etc/systemd/system/NetworkManager.service.d/10-rfkill-unblock.conf", "[Service]\nExecStartPre=/usr/sbin/rfkill unblock all\n")
    
    # GRUB defaults
    grub_defaults = cfg.get("grub", {}).get("defaults", {})
    if grub_defaults:
        log("Configuring GRUB...")
        grub_file = ROOTFS_DIR / "etc/default/grub"
        lines = grub_file.read_text().splitlines() if grub_file.exists() else []
        seen = set()
        for i, line in enumerate(lines):
            for key, val in grub_defaults.items():
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={val}"
                    seen.add(key)
        for key, val in grub_defaults.items():
            if key not in seen:
                lines.append(f"{key}={val}")
        grub_file.parent.mkdir(parents=True, exist_ok=True)
        grub_file.write_text("\n".join(lines) + "\n")

def get_all_packages():
    """Get all packages from groups and extra list."""
    pkgs = []
    for group_pkgs in packages.get("groups", {}).values():
        pkgs.extend(group_pkgs)
    pkgs.extend(packages.get("extra", []))
    return pkgs

# ============================================================================
# STAGE 1: Build rootfs with debootstrap
# ============================================================================
log("=== Stage 1: Building rootfs ===")

if not ASSETS_DIR.is_dir():
    die(f"Assets directory not found: {ASSETS_DIR}")

if ROOTFS_DIR.exists():
    log("Removing existing rootfs...")
    cleanup_mounts(ROOTFS_DIR)
    shutil.rmtree(ROOTFS_DIR)

ROOTFS_DIR.mkdir(parents=True, exist_ok=True)

# Run pre-debootstrap hooks
run_hooks("host:before_rootfs")

# Debootstrap
log(f"Running debootstrap for {debian['dist']}/{debian['arch']}...")
run([
    "debootstrap",
    f"--arch={debian['arch']}",
    debian["dist"],
    str(ROOTFS_DIR),
    debian["mirror"],
])

run_hooks("host:after_debootstrap")

# Mount virtual filesystems
log("Mounting virtual filesystems...")
run(["mount", "--bind", "/dev", str(ROOTFS_DIR / "dev")])
run(["mount", "--bind", "/dev/pts", str(ROOTFS_DIR / "dev/pts")])
run(["mount", "-t", "proc", "proc", str(ROOTFS_DIR / "proc")])
run(["mount", "-t", "sysfs", "sys", str(ROOTFS_DIR / "sys")])
run(["mount", "-t", "tmpfs", "tmpfs", str(ROOTFS_DIR / "run")])

# Copy before_chroot files and write configs
log("Copying pre-chroot files...")
copy_files("before_chroot")
write_text_configs()
run_hooks("host:before_chroot")

# Build and run chroot script
log("Running chroot setup (installing packages, configuring system)...")

# Collect all chroot commands
chroot_cmds = ["#!/bin/bash", "set -euo pipefail", "export DEBIAN_FRONTEND=noninteractive", ""]

# Run chroot:start hooks
for hook in hooks:
    if hook["point"] == "chroot:start" and hook.get("enabled", True):
        chroot_cmds.append(f"# Hook: {hook['name']}")
        chroot_cmds.append(hook["script"])
        chroot_cmds.append("")

# Setup apt sources
components = " ".join(debian.get("components", ["main"]))
sources = [f"deb {debian['mirror']} {debian['dist']} {components}"] + debian.get("extra_apt_sources", [])
chroot_cmds.append("cat > /etc/apt/sources.list <<'EOF'")
chroot_cmds.extend(sources)
chroot_cmds.append("EOF")
chroot_cmds.append("")

# Run after_sources hooks
for hook in hooks:
    if hook["point"] == "chroot:after_sources" and hook.get("enabled", True):
        chroot_cmds.append(f"# Hook: {hook['name']}")
        chroot_cmds.append(hook["script"])
        chroot_cmds.append("")

# apt-get update
chroot_cmds.append("apt-get update")
chroot_cmds.append("")

# Run after_update hooks
for hook in hooks:
    if hook["point"] == "chroot:after_update" and hook.get("enabled", True):
        chroot_cmds.append(f"# Hook: {hook['name']}")
        chroot_cmds.append(hook["script"])
        chroot_cmds.append("")

# Install packages
all_pkgs = get_all_packages()
if all_pkgs:
    chroot_cmds.append("apt-get install -y \\")
    for i, pkg in enumerate(all_pkgs):
        cont = " \\" if i < len(all_pkgs) - 1 else ""
        chroot_cmds.append(f"    {pkg}{cont}")
    chroot_cmds.append("")

# Run after_packages hooks
for hook in hooks:
    if hook["point"] == "chroot:after_packages" and hook.get("enabled", True):
        chroot_cmds.append(f"# Hook: {hook['name']}")
        chroot_cmds.append(hook["script"])
        chroot_cmds.append("")

# Locale setup
chroot_cmds.append("sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen")
chroot_cmds.append("locale-gen")
chroot_cmds.append("update-locale LANG=en_US.UTF-8")
chroot_cmds.append("")

# User accounts
for user in accounts.get("users", []):
    username = user["username"]
    shell = user.get("shell", "/bin/bash")
    groups = user.get("groups", [])
    cmd = f"useradd --shell {shell}"
    if user.get("create_home", True):
        cmd += " --create-home"
    if groups:
        cmd += f" --groups {','.join(groups)}"
    cmd += f" {username}"
    chroot_cmds.append(cmd)
    chroot_cmds.append(f"echo '{username}:{user['password']}' | chpasswd")

if "root_password" in accounts:
    chroot_cmds.append(f"echo 'root:{accounts['root_password']}' | chpasswd")
chroot_cmds.append("")

# Enable services
for svc in services:
    chroot_cmds.append(f"systemctl enable {svc}")
chroot_cmds.append("")

# Plymouth theme
plymouth_theme = cfg.get("boot", {}).get("plymouth_theme")
if plymouth_theme:
    chroot_cmds.append(f"plymouth-set-default-theme -R {plymouth_theme} || true")

chroot_cmds.append("update-desktop-database /usr/share/applications || true")
chroot_cmds.append("")

# Finalize
finalize = cfg.get("chroot_finalize", {})
if finalize.get("machine_id_setup", True):
    chroot_cmds.append("systemd-machine-id-setup")
if finalize.get("autoremove", True):
    chroot_cmds.append("apt-get autoremove -y")
if finalize.get("apt_clean", True):
    chroot_cmds.append("apt-get clean")
if finalize.get("update_initramfs", True):
    chroot_cmds.append("update-initramfs -u -k all")

# Write and execute chroot script
chroot_script = ROOTFS_DIR / "root/chroot.sh"
chroot_script.parent.mkdir(parents=True, exist_ok=True)
chroot_script.write_text("\n".join(chroot_cmds) + "\n")
chroot_script.chmod(0o755)
run(["chroot", str(ROOTFS_DIR), "/bin/bash", "/root/chroot.sh"])
chroot_script.unlink()

run_hooks("host:after_chroot")

# Cleanup globs
for pattern in cleanup_globs:
    import glob
    for match in glob.glob(str(ROOTFS_DIR / pattern.lstrip("/"))):
        log(f"Removing {match}")
        Path(match).unlink(missing_ok=True)

# Copy after_chroot files
log("Copying post-chroot files...")
copy_files("after_chroot")

# Unmount
log("Unmounting rootfs...")
cleanup_mounts(ROOTFS_DIR)
run_hooks("host:after_rootfs")

log("Rootfs build complete!")

# ============================================================================
# STAGE 2: Create live filesystem (SquashFS)
# ============================================================================
log("=== Stage 2: Creating live filesystem ===")

if not ROOTFS_DIR.is_dir():
    die(f"Rootfs not found at {ROOTFS_DIR}")

shutil.rmtree(LIVE_DIR, ignore_errors=True)
(LIVE_DIR / "live").mkdir(parents=True, exist_ok=True)

run_hooks("host:before_live")

# Clean caches
log("Cleaning rootfs caches...")
shutil.rmtree(ROOTFS_DIR / "tmp", ignore_errors=True)
(ROOTFS_DIR / "tmp").mkdir(exist_ok=True)
for deb in glob.glob(str(ROOTFS_DIR / "var/cache/apt/archives/*.deb")):
    os.remove(deb)
(ROOTFS_DIR / "etc/machine-id").write_text("")

# Create SquashFS
squashfs_cfg = cfg["squashfs"]
log(f"Creating SquashFS ({squashfs_cfg['comp']}, block={squashfs_cfg['block_size']})...")
exclude_args = []
for pat in squashfs_cfg.get("exclude_wildcards", []):
    exclude_args += ["-e", pat]
run([
    "mksquashfs",
    str(ROOTFS_DIR),
    str(LIVE_DIR / "live/filesystem.squashfs"),
    "-comp", squashfs_cfg["comp"],
    "-b", squashfs_cfg["block_size"],
    "-wildcards", *exclude_args,
])

# Copy kernel
log("Copying kernel...")
kernels = sorted((ROOTFS_DIR / "boot").glob("vmlinuz-*"))
if not kernels:
    die(f"No vmlinuz-* found in {ROOTFS_DIR / 'boot'}")
shutil.copy2(kernels[-1], LIVE_DIR / "vmlinuz")

# Copy initrd
log("Copying initrd...")
initrds = sorted((ROOTFS_DIR / "boot").glob("initrd.img-*"))
if not initrds:
    die(f"No initrd.img-* found in {ROOTFS_DIR / 'boot'}")
shutil.copy2(initrds[-1], LIVE_DIR / "initrd")

# Copy memtest if available
for pattern in ("memtest86*.bin", "memtest86*.efi"):
    matches = list((ROOTFS_DIR / "boot").glob(pattern))
    if matches:
        shutil.copy2(matches[0], LIVE_DIR / matches[0].name)

run_hooks("host:after_live")
log("Live filesystem complete!")

# ============================================================================
# STAGE 3: Build bootable ISO
# ============================================================================
log("=== Stage 3: Building ISO ===")

squashfs = LIVE_DIR / "live/filesystem.squashfs"
if not squashfs.is_file():
    die(f"filesystem.squashfs not found (run stage 2 first)")

run_hooks("host:before_iso")

shutil.rmtree(ISO_WORK_DIR, ignore_errors=True)
(ISO_WORK_DIR / "boot/grub").mkdir(parents=True, exist_ok=True)
(ISO_WORK_DIR / "live").mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

log("Copying files to ISO tree...")
shutil.copy2(squashfs, ISO_WORK_DIR / "live/filesystem.squashfs")
shutil.copy2(LIVE_DIR / "vmlinuz", ISO_WORK_DIR / "live/vmlinuz")
shutil.copy2(LIVE_DIR / "initrd", ISO_WORK_DIR / "live/initrd")

for pattern in ("memtest86*.efi", "memtest86*.bin"):
    for f in LIVE_DIR.glob(pattern):
        shutil.copy2(f, ISO_WORK_DIR / "boot" / f.name)

log("Copying GRUB configuration...")
shutil.copy2(ASSETS_DIR / "grub.cfg", ISO_WORK_DIR / "boot/grub/grub.cfg")

iso_name = f"{distro['name']}-{distro['version']}-{debian['arch']}.iso"
iso_path = OUTPUT_DIR / iso_name

log("Building ISO with grub-mkrescue...")
run(["grub-mkrescue", "--compress=xz", "-o", str(iso_path), str(ISO_WORK_DIR)])

run_hooks("host:after_iso")
log(f"ISO built successfully: {iso_path}")
