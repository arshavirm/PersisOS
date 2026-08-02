#!/usr/bin/env python3
"""
Stages (run in order by default, selectable with --stages):
    rootfs  debootstrap a base system, install packages in a chroot, apply
            branding/config from the file manifest, run configured hooks
    live    squash the rootfs into a live filesystem, stage kernel/initrd
    iso     assemble a bootable ISO with GRUB

Usage:
    sudo python3 build.py [options]

Options:
    -c, --config FILE     Path to config file (default: ./config.json)
    -s, --stages LIST     Comma-separated: rootfs,live,iso (default: all)
    -y, --yes             Don't prompt before removing existing directories
        --list-hook-points  Print all valid hook 'point' values and exit
    -h, --help             Show this help

Examples:
    sudo python3 build.py
    sudo python3 build.py -c variant.json
    sudo python3 build.py -s rootfs
    sudo python3 build.py -s live,iso
    python3 build.py --list-hook-points
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

# --------------------------------------------------------------------------- #
# logging
# --------------------------------------------------------------------------- #

_COLOR = sys.stdout.isatty()


def _c(code: str, msg: str) -> str:
    return f"\033[{code}m{msg}\033[0m" if _COLOR else msg


def log_info(msg: str) -> None:
    print(f"{_c('1;34', '[INFO]')} {msg}")


def log_warn(msg: str) -> None:
    print(f"{_c('1;33', '[WARN]')} {msg}", file=sys.stderr)


def log_ok(msg: str) -> None:
    print(f"{_c('1;32', '[ OK ]')} {msg}")


def die(msg: str) -> None:
    print(f"{_c('1;31', '[ERROR]')} {msg}", file=sys.stderr)
    sys.exit(1)


# --------------------------------------------------------------------------- #
# hook points
# --------------------------------------------------------------------------- #

CHROOT_POINTS = {
    "chroot:start": "very first thing in the chroot script",
    "chroot:after_sources": "after /etc/apt/sources.list is written",
    "chroot:after_update": "after 'apt-get update'",
    "chroot:after_packages": "after the main package list is installed",
    "chroot:after_locale": "after locale-gen/update-locale",
    "chroot:after_users": "after accounts are created",
    "chroot:after_services": "after 'systemctl enable' for configured services",
    "chroot:end": "after theme/desktop-database setup, before final cleanup",
    "chroot:finish": "very last thing in the chroot script",
}

HOST_POINTS = {
    "host:before_rootfs": "before debootstrap runs",
    "host:after_debootstrap": "after debootstrap, before mounts",
    "host:before_chroot": "after before_chroot file copies, before entering chroot",
    "host:after_chroot": "after the chroot script finishes, before after_chroot file copies",
    "host:after_rootfs": "end of the rootfs stage, after unmounting",
    "host:before_live": "start of the live stage",
    "host:after_live": "end of the live stage",
    "host:before_iso": "start of the iso stage",
    "host:after_iso": "end of the iso stage",
}

VALID_POINTS = {**CHROOT_POINTS, **HOST_POINTS}


# --------------------------------------------------------------------------- #
# small process/file helpers
# --------------------------------------------------------------------------- #


def run(cmd: list[str], **kwargs) -> None:
    log_info("$ " + " ".join(shlex.quote(c) for c in cmd))
    subprocess.run(cmd, check=True, **kwargs)


def is_mounted(path: Path) -> bool:
    return subprocess.run(["mountpoint", "-q", str(path)]).returncode == 0


def confirm_or_die(prompt: str, assume_yes: bool) -> None:
    if assume_yes:
        return
    reply = input(f"{prompt} [y/N] ")
    if reply.strip().lower() != "y":
        die("Aborted by user.")


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #


class Config:
    def __init__(self, config_path: Path):
        self.path = config_path
        self.base_dir = config_path.parent.resolve()
        with open(config_path) as f:
            self.data = json.load(f)

        for section in ("distro", "debian", "paths", "packages"):
            if section not in self.data:
                die(f"Config is missing required section: {section!r}")

        p = self.data["paths"]
        self.project_dir = self._resolve(p.get("project_dir", "."))
        self.assets_dir = self._resolve(p["assets_dir"])
        self.rootfs_dir = self._resolve(p["rootfs_dir"])
        self.live_dir = self._resolve(p["live_dir"])
        self.iso_work_dir = self._resolve(p["iso_work_dir"])
        self.output_dir = self._resolve(p["output_dir"])

        self.files = self.data.get("files", [])
        self.cleanup_globs = self.data.get("cleanup_globs", [])
        self.hooks = self.data.get("hooks", [])
        self._validate_hooks()

    def _resolve(self, p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else (self.base_dir / path).resolve()

    def _validate_hooks(self) -> None:
        for hook in self.hooks:
            for field in ("name", "point", "script"):
                if field not in hook:
                    die(f"Hook missing required field {field!r}: {hook}")
            if hook["point"] not in VALID_POINTS:
                die(
                    f"Hook {hook['name']!r} has invalid point {hook['point']!r}. "
                    f"Run with --list-hook-points to see valid values."
                )

    def hooks_at(self, point: str) -> list[dict]:
        return [h for h in self.hooks if h["point"] == point and h.get("enabled", True)]

    def all_packages(self) -> list[str]:
        pkgs = self.data["packages"]
        out: list[str] = []
        for group_pkgs in pkgs.get("groups", {}).values():
            out.extend(group_pkgs)
        out.extend(pkgs.get("extra", []))
        return out


# --------------------------------------------------------------------------- #
# file manifest engine
# --------------------------------------------------------------------------- #


def copy_manifest(cfg: Config, stage: str) -> None:
    """Copy every manifest entry tagged with the given stage straight from
    the project directory to its destination inside the rootfs.
    stage is 'before_chroot' or 'after_chroot'."""
    entries = [f for f in cfg.files if f.get("stage") == stage]
    if not entries:
        return
    log_info(f"Copying {len(entries)} file(s)/dir(s) for stage '{stage}'...")
    for entry in entries:
        src = cfg.project_dir / entry["src"]
        dest = cfg.rootfs_dir / entry["dest"].lstrip("/")
        if not src.exists():
            die(f"Manifest source not found: {src}")

        entry_type = entry.get("type") or ("dir" if src.is_dir() else "file")
        dest.parent.mkdir(parents=True, exist_ok=True)

        if entry_type == "dir":
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)

        mode = entry.get("mode")
        if mode:
            perm = int(mode, 8)
            if entry_type == "dir":
                for root, _dirs, files in os.walk(dest):
                    for name in files:
                        os.chmod(os.path.join(root, name), perm)
            else:
                os.chmod(dest, perm)


def run_cleanup_globs(cfg: Config) -> None:
    for pattern in cfg.cleanup_globs:
        for match in glob.glob(str(cfg.rootfs_dir / pattern.lstrip("/"))):
            log_info(f"Removing {match}")
            Path(match).unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# host-side hooks
# --------------------------------------------------------------------------- #


def host_env(cfg: Config) -> dict:
    d = cfg.data
    env = os.environ.copy()
    env.update(
        {
            "PROJECT_DIR": str(cfg.project_dir),
            "ASSETS_DIR": str(cfg.assets_dir),
            "ROOTFS_DIR": str(cfg.rootfs_dir),
            "LIVE_DIR": str(cfg.live_dir),
            "ISO_WORK_DIR": str(cfg.iso_work_dir),
            "OUTPUT_DIR": str(cfg.output_dir),
            "DISTRO_NAME": d["distro"]["name"],
            "DISTRO_VERSION": d["distro"]["version"],
            "DISTRO_HOSTNAME": d["distro"]["hostname"],
            "DEBIAN_ARCH": d["debian"]["arch"],
            "DEBIAN_DIST": d["debian"]["dist"],
        }
    )
    return env


def run_host_hooks(cfg: Config, point: str) -> None:
    for hook in cfg.hooks_at(point):
        log_info(f"Running host hook '{hook['name']}' @ {point}")
        try:
            subprocess.run(
                ["bash", "-c", hook["script"]],
                check=True,
                cwd=str(cfg.project_dir),
                env=host_env(cfg),
            )
        except subprocess.CalledProcessError as e:
            if hook.get("continue_on_error"):
                log_warn(
                    f"Hook '{hook['name']}' failed (continuing, continue_on_error=true): {e}"
                )
            else:
                raise


# --------------------------------------------------------------------------- #
# text config generation
# --------------------------------------------------------------------------- #


def write_text_configs(cfg: Config) -> None:
    d = cfg.data
    hostname = d["distro"]["hostname"]
    rootfs = cfg.rootfs_dir

    def w(rel_path: str, content: str, mode: int = 0o644) -> None:
        p = rootfs / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        os.chmod(p, mode)

    log_info("Writing hostname/hosts/network configuration...")
    w("etc/hostname", hostname + "\n")
    w("etc/hosts", f"127.0.0.1 localhost\n127.0.1.1 {hostname}\n")
    w("etc/network/interfaces", "auto lo\niface lo inet loopback\n")

    w(
        "etc/apt/apt.conf.d/99parallel",
        textwrap.dedent("""\
        Acquire::Queue-Host-Limit "6";
        Acquire::http::Pipeline-Depth "10";
        """),
    )

    w(
        "etc/NetworkManager/conf.d/10-globally-managed-devices.conf",
        "[ifupdown]\nmanaged=true\n",
    )

    w(
        "etc/systemd/system/NetworkManager.service.d/10-rfkill-unblock.conf",
        "[Service]\nExecStartPre=/usr/sbin/rfkill unblock all\n",
    )

    w(
        "etc/polkit-1/rules.d/50-netdev-networkmanager.rules",
        textwrap.dedent("""\
        polkit.addRule(function(action, subject) {
            if (action.id.indexOf("org.freedesktop.NetworkManager.") == 0 &&
                subject.isInGroup("netdev")) {
                return polkit.Result.YES;
            }
        });
        """),
    )

    grub_defaults_map = d.get("grub", {}).get("defaults", {})
    if grub_defaults_map:
        log_info("Patching /etc/default/grub...")
        grub_defaults = rootfs / "etc/default/grub"
        lines = grub_defaults.read_text().splitlines() if grub_defaults.exists() else []
        seen = set()
        for i, line in enumerate(lines):
            for key, val in grub_defaults_map.items():
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={val}"
                    seen.add(key)
        for key, val in grub_defaults_map.items():
            if key not in seen:
                lines.append(f"{key}={val}")
        grub_defaults.parent.mkdir(parents=True, exist_ok=True)
        grub_defaults.write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# chroot script assembly
# --------------------------------------------------------------------------- #


def build_chroot_script(cfg: Config) -> str:
    d = cfg.data
    lines: list[str] = [
        "#!/bin/bash",
        "set -euo pipefail",
        "export DEBIAN_FRONTEND=noninteractive",
        "",
    ]

    def emit_hooks(point: str) -> None:
        for hook in cfg.hooks_at(point):
            lines.append(f"# --- hook: {hook['name']} ({point}) ---")
            lines.append(hook["script"].rstrip("\n"))
            lines.append("")

    emit_hooks("chroot:start")

    deb = d["debian"]
    components = " ".join(deb.get("components", ["main"]))
    sources = [f"deb {deb['mirror']} {deb['dist']} {components}"] + deb.get(
        "extra_apt_sources", []
    )
    lines.append("cat > /etc/apt/sources.list <<'APT_SOURCES_EOF'")
    lines.extend(sources)
    lines.append("APT_SOURCES_EOF")
    lines.append("")
    emit_hooks("chroot:after_sources")

    lines.append("apt-get update")
    lines.append("")
    emit_hooks("chroot:after_update")

    packages = cfg.all_packages()
    if packages:
        lines.append("apt-get install -y \\")
        for i, pkg in enumerate(packages):
            cont = " \\" if i < len(packages) - 1 else ""
            lines.append(f"    {shlex.quote(pkg)}{cont}")
        lines.append('echo "finished installing packages"')
        lines.append("")
    emit_hooks("chroot:after_packages")

    lines.append(textwrap.dedent("""\
        sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
        locale-gen
        update-locale LANG=en_US.UTF-8
        """))
    emit_hooks("chroot:after_locale")

    accounts = d.get("accounts", {})
    for user in accounts.get("users", []):
        username = user["username"]
        shell = user.get("shell", "/bin/bash")
        groups = user.get("groups", [])
        cmd = f"useradd --shell {shlex.quote(shell)}"
        if user.get("create_home", True):
            cmd += " --create-home"
        if groups:
            cmd += f" --groups {shlex.quote(','.join(groups))}"
        cmd += f" {shlex.quote(username)}"
        lines.append(cmd)
        chpasswd_line = f"{username}:{user['password']}"
        lines.append(f"echo {shlex.quote(chpasswd_line)} | chpasswd")
    if "root_password" in accounts:
        lines.append(
            f"echo {shlex.quote('root:' + accounts['root_password'])} | chpasswd"
        )
    lines.append("")
    emit_hooks("chroot:after_users")

    for svc in d.get("services", []):
        lines.append(f"systemctl enable {shlex.quote(svc)}")
    lines.append("")
    emit_hooks("chroot:after_services")

    plymouth_theme = d.get("boot", {}).get("plymouth_theme")
    if plymouth_theme:
        lines.append(
            f"plymouth-set-default-theme -R {shlex.quote(plymouth_theme)} || true"
        )
    lines.append("update-desktop-database /usr/share/applications || true")
    lines.append("")
    emit_hooks("chroot:end")

    finalize = d.get("chroot_finalize", {})
    if finalize.get("machine_id_setup", True):
        lines.append("systemd-machine-id-setup")
    if finalize.get("autoremove", True):
        lines.append("apt-get autoremove -y")
    if finalize.get("apt_clean", True):
        lines.append("apt-get clean")
    if finalize.get("update_initramfs", True):
        lines.append("update-initramfs -u -k all")
    lines.append("")
    emit_hooks("chroot:finish")

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# stages
# --------------------------------------------------------------------------- #

MOUNTPOINTS = ["dev/pts", "dev", "proc", "sys", "run"]


def cleanup_mounts(rootfs: Path) -> None:
    for m in MOUNTPOINTS:
        target = rootfs / m
        if is_mounted(target):
            run(["umount", "-lf", str(target)])


def stage_rootfs(cfg: Config, assume_yes: bool) -> None:
    log_info("=== Stage 1/3: rootfs ===")
    if not cfg.assets_dir.is_dir():
        die(f"Assets directory not found: {cfg.assets_dir}")

    if cfg.rootfs_dir.exists():
        confirm_or_die(
            f"Rootfs already exists at {cfg.rootfs_dir} and will be removed. Continue?",
            assume_yes,
        )
        cleanup_mounts(cfg.rootfs_dir)
        shutil.rmtree(cfg.rootfs_dir)

    run_host_hooks(cfg, "host:before_rootfs")

    try:
        d = cfg.data
        log_info(
            f"[1/6] debootstrap ({d['debian']['dist']}/{d['debian']['arch']} from {d['debian']['mirror']})..."
        )
        run(
            [
                "debootstrap",
                f"--arch={d['debian']['arch']}",
                d["debian"]["dist"],
                str(cfg.rootfs_dir),
                d["debian"]["mirror"],
            ]
        )
        run_host_hooks(cfg, "host:after_debootstrap")

        log_info("[2/6] Mounting virtual filesystems...")
        run(["mount", "--bind", "/dev", str(cfg.rootfs_dir / "dev")])
        run(["mount", "--bind", "/dev/pts", str(cfg.rootfs_dir / "dev/pts")])
        run(["mount", "-t", "proc", "proc", str(cfg.rootfs_dir / "proc")])
        run(["mount", "-t", "sysfs", "sys", str(cfg.rootfs_dir / "sys")])
        run(["mount", "-t", "tmpfs", "tmpfs", str(cfg.rootfs_dir / "run")])

        log_info("[3/6] Applying pre-chroot file manifest and text configs...")
        copy_manifest(cfg, "before_chroot")
        write_text_configs(cfg)
        run_host_hooks(cfg, "host:before_chroot")

        log_info("[4/6] Installing packages and configuring system in chroot...")
        script_path = cfg.rootfs_dir / "root/chroot.sh"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(build_chroot_script(cfg))
        os.chmod(script_path, 0o755)
        run(["chroot", str(cfg.rootfs_dir), "/bin/bash", "/root/chroot.sh"])
        script_path.unlink(missing_ok=True)
        run_host_hooks(cfg, "host:after_chroot")

        log_info("[5/6] Applying post-chroot file manifest...")
        run_cleanup_globs(cfg)
        copy_manifest(cfg, "after_chroot")

    except subprocess.CalledProcessError as e:
        log_warn(f"Command failed: {e}. Cleaning up...")
        cleanup_mounts(cfg.rootfs_dir)
        shutil.rmtree(cfg.rootfs_dir, ignore_errors=True)
        raise
    else:
        log_info("[6/6] Unmounting...")
        cleanup_mounts(cfg.rootfs_dir)
        run_host_hooks(cfg, "host:after_rootfs")
        log_ok(f"Rootfs build complete: {cfg.rootfs_dir}")


def stage_live(cfg: Config, assume_yes: bool) -> None:
    log_info("=== Stage 2/3: live filesystem ===")
    if not cfg.rootfs_dir.is_dir():
        die(f"Rootfs not found at {cfg.rootfs_dir} (run the 'rootfs' stage first)")

    if cfg.live_dir.exists():
        confirm_or_die(
            f"Live dir already exists at {cfg.live_dir} and will be removed. Continue?",
            assume_yes,
        )
    shutil.rmtree(cfg.live_dir, ignore_errors=True)
    (cfg.live_dir / "live").mkdir(parents=True, exist_ok=True)

    run_host_hooks(cfg, "host:before_live")

    log_info("Cleaning rootfs caches/temp files before squashing...")
    shutil.rmtree(cfg.rootfs_dir / "tmp", ignore_errors=True)
    (cfg.rootfs_dir / "tmp").mkdir(exist_ok=True)
    for deb in glob.glob(str(cfg.rootfs_dir / "var/cache/apt/archives/*.deb")):
        os.remove(deb)
    (cfg.rootfs_dir / "etc/machine-id").write_text("")

    sq = cfg.data["squashfs"]
    log_info(f"Creating SquashFS (comp={sq['comp']}, block={sq['block_size']})...")
    exclude_args = []
    for pat in sq.get("exclude_wildcards", []):
        exclude_args += ["-e", pat]
    run(
        [
            "mksquashfs",
            str(cfg.rootfs_dir),
            str(cfg.live_dir / "live/filesystem.squashfs"),
            "-comp",
            sq["comp"],
            "-b",
            sq["block_size"],
            "-wildcards",
            *exclude_args,
        ]
    )

    log_info("Copying kernel...")
    kernels = sorted((cfg.rootfs_dir / "boot").glob("vmlinuz-*"))
    if not kernels:
        die(f"No vmlinuz-* found in {cfg.rootfs_dir / 'boot'}")
    shutil.copy2(kernels[-1], cfg.live_dir / "vmlinuz")

    log_info("Copying initrd...")
    initrds = sorted((cfg.rootfs_dir / "boot").glob("initrd.img-*"))
    if not initrds:
        die(f"No initrd.img-* found in {cfg.rootfs_dir / 'boot'}")
    shutil.copy2(initrds[-1], cfg.live_dir / "initrd")

    for pattern in ("memtest86*.bin", "memtest86*.efi"):
        matches = list((cfg.rootfs_dir / "boot").glob(pattern))
        if matches:
            shutil.copy2(matches[0], cfg.live_dir / matches[0].name)
        else:
            log_warn(f"No {pattern} found")

    run_host_hooks(cfg, "host:after_live")
    log_ok(f"Live filesystem complete: {cfg.live_dir}")


def stage_iso(cfg: Config) -> None:
    log_info("=== Stage 3/3: ISO ===")
    squashfs = cfg.live_dir / "live/filesystem.squashfs"
    if not squashfs.is_file():
        die(
            f"filesystem.squashfs not found in {cfg.live_dir} (run the 'live' stage first)"
        )

    run_host_hooks(cfg, "host:before_iso")

    shutil.rmtree(cfg.iso_work_dir, ignore_errors=True)
    (cfg.iso_work_dir / "boot/grub").mkdir(parents=True, exist_ok=True)
    (cfg.iso_work_dir / "live").mkdir(parents=True, exist_ok=True)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    log_info("Copying live system into ISO tree...")
    shutil.copy2(squashfs, cfg.iso_work_dir / "live/filesystem.squashfs")
    shutil.copy2(cfg.live_dir / "vmlinuz", cfg.iso_work_dir / "live/vmlinuz")
    shutil.copy2(cfg.live_dir / "initrd", cfg.iso_work_dir / "live/initrd")

    for pattern in ("memtest86*.efi", "memtest86*.bin"):
        for f in cfg.live_dir.glob(pattern):
            shutil.copy2(f, cfg.iso_work_dir / "boot" / f.name)

    log_info("Copying GRUB configuration...")
    shutil.copy2(cfg.assets_dir / "grub.cfg", cfg.iso_work_dir / "boot/grub/grub.cfg")

    d = cfg.data["distro"]
    arch = cfg.data["debian"]["arch"]
    iso_path = cfg.output_dir / f"{d['name']}-{d['version']}-{arch}.iso"
    log_info("Building ISO with grub-mkrescue...")
    run(["grub-mkrescue", "--compress=xz", "-o", str(iso_path), str(cfg.iso_work_dir)])

    run_host_hooks(cfg, "host:after_iso")
    log_ok(f"ISO written to: {iso_path}")


# --------------------------------------------------------------------------- #
# dependency checks
# --------------------------------------------------------------------------- #


def check_deps(stages: set[str]) -> None:
    needed = set()
    if "rootfs" in stages:
        needed |= {"debootstrap", "chroot", "mount", "umount", "mountpoint"}
    if "live" in stages:
        needed |= {"mksquashfs"}
    if "iso" in stages:
        needed |= {"grub-mkrescue"}

    missing = [c for c in sorted(needed) if shutil.which(c) is None]
    if missing:
        die(f"Missing required tools: {', '.join(missing)} (install them and re-run)")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def print_hook_points() -> None:
    print("chroot:* — spliced as bash into the generated chroot script, in order:")
    for point, desc in CHROOT_POINTS.items():
        print(f"  {point:<24} {desc}")
    print()
    print(
        "host:* — run as a subprocess on the host (env vars: PROJECT_DIR, ASSETS_DIR,"
    )
    print(
        "ROOTFS_DIR, LIVE_DIR, ISO_WORK_DIR, OUTPUT_DIR, DISTRO_NAME, DISTRO_VERSION,"
    )
    print("DISTRO_HOSTNAME, DEBIAN_ARCH, DEBIAN_DIST):")
    for point, desc in HOST_POINTS.items():
        print(f"  {point:<24} {desc}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a Debian-based live ISO in one shot, driven by config.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              sudo python3 build.py
              sudo python3 build.py -c variant.json
              sudo python3 build.py -s rootfs
              sudo python3 build.py -s live,iso
              python3 build.py --list-hook-points
            """),
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.json",
        help="Path to config file (default: ./config.json)",
    )
    parser.add_argument(
        "-s",
        "--stages",
        default="rootfs,live,iso",
        help="Comma-separated: rootfs,live,iso",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Don't prompt before removing existing directories",
    )
    parser.add_argument(
        "--list-hook-points",
        action="store_true",
        help="Print valid hook 'point' values and exit",
    )
    args = parser.parse_args()

    if args.list_hook_points:
        print_hook_points()
        return

    if os.geteuid() != 0:
        die(
            "This script needs root privileges (it debootstraps, mounts, and chroots). Run with: sudo python3 build.py"
        )

    config_path = Path(args.config)
    if not config_path.is_file():
        die(f"Config file not found: {config_path}")

    stages = {s.strip() for s in args.stages.split(",") if s.strip()}
    unknown = stages - {"rootfs", "live", "iso"}
    if unknown:
        die(f"Unknown stage(s): {', '.join(unknown)} (valid: rootfs, live, iso)")

    log_info(f"Loading config from {config_path}")
    cfg = Config(config_path)

    check_deps(stages)

    start = time.time()
    if "rootfs" in stages:
        stage_rootfs(cfg, args.yes)
    if "live" in stages:
        stage_live(cfg, args.yes)
    if "iso" in stages:
        stage_iso(cfg)

    log_ok(
        f"Done in {time.time() - start:.0f}s. Stages run: {', '.join(sorted(stages))}"
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        die(
            f"Command failed with exit code {e.returncode}: {' '.join(e.cmd) if isinstance(e.cmd, list) else e.cmd}"
        )
    except KeyboardInterrupt:
        die("Interrupted.")
