#!/usr/bin/env python3
"""
build.py

Usage:
  sudo python3 build.py config.json [--workdir /path/to/build] [--outdir /path/to/output]

Must be run as root (debootstrap, chroot, and mount all require it).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path

REQUIRED_KEYS = [
    "distro_name",
    "version",
    "debian_distro",
    "apt_mirror",
    "packages",
]

SUPPORTED_ARCHES = ["amd64", "arm64", "armhf"]

BIOS_CAPABLE_ARCHES = ["amd64"]

KERNEL_PACKAGE_MAP = {
    "amd64": "linux-image-amd64",
    "arm64": "linux-image-arm64",
    "armhf": "linux-image-armmp",
}

GRUB_EFI_PACKAGE_MAP = {
    "amd64": "grub-efi-amd64-bin",
    "arm64": "grub-efi-arm64-bin",
    "armhf": "grub-efi-arm-bin",
}

LIVE_BOOT_PACKAGES = [
    "live-boot",
    "systemd-sysv",
    "sudo",
    "locales",
]

ISO_BUILD_PACKAGES_COMMON = [
    "squashfs-tools",
    "xorriso",
    "mtools",
    "dosfstools",
    "grub-common",
]

ISO_BUILD_PACKAGES_BIOS = [
    "grub-pc-bin",
]


# --------------------------------------------------------------------------
# Error handling
# --------------------------------------------------------------------------


class BuildError(Exception):
    """A known, expected failure -- reported cleanly, no traceback."""


@contextmanager
def build_step(description):
    log(f"==> {description}")
    try:
        yield
    except BuildError:
        raise
    except subprocess.CalledProcessError as e:
        cmd_str = e.cmd if isinstance(e.cmd, str) else " ".join(map(str, e.cmd))
        raise BuildError(
            f"Step failed: {description}\n"
            f"  Command:    {cmd_str}\n"
            f"  Exit code:  {e.returncode}\n"
            f"  (see command output above for the underlying error)"
        ) from e
    except FileNotFoundError as e:
        raise BuildError(
            f"Step failed: {description}\n  Missing file or command: {e}"
        ) from e
    except OSError as e:
        raise BuildError(f"Step failed: {description}\n  OS error: {e}") from e


def log(msg):
    print(f"[build_live_iso] {msg}", flush=True)


def run(cmd, **kwargs):
    """Run a command, echoing it first, raising on failure."""
    log("+ " + (cmd if isinstance(cmd, str) else " ".join(map(str, cmd))))
    subprocess.run(cmd, check=True, **kwargs)


def require_root():
    if os.geteuid() != 0:
        raise BuildError(
            "This script must be run as root (needed for debootstrap/chroot/mount)."
        )


def require_tool(name, hint=None):
    if shutil.which(name) is None:
        extra = f" ({hint})" if hint else ""
        raise BuildError(f"Required tool '{name}' not found on host{extra}.")


def host_arch():
    return subprocess.check_output(["dpkg", "--print-architecture"]).decode().strip()


def sanitize_volume_id(name):
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name.upper())
    return cleaned[:32] or "LIVECD"


def load_config(path):
    try:
        with open(path, "r") as f:
            raw = f.read()
    except OSError as e:
        raise BuildError(f"Could not read config file '{path}': {e}")

    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError as e:
        raise BuildError(f"Config file '{path}' is not valid JSON: {e}")

    missing = [k for k in REQUIRED_KEYS if k not in cfg]
    if missing:
        raise BuildError(f"Config is missing required keys: {', '.join(missing)}")

    if not isinstance(cfg["packages"], list) or not all(
        isinstance(p, str) for p in cfg["packages"]
    ):
        raise BuildError("'packages' must be a JSON list of package name strings")

    cfg.setdefault("exclude_packages", [])
    if not isinstance(cfg["exclude_packages"], list) or not all(
        isinstance(p, str) for p in cfg["exclude_packages"]
    ):
        raise BuildError(
            "'exclude_packages' must be a JSON list of package name strings"
        )
    overlap = set(cfg["packages"]) & set(cfg["exclude_packages"])
    if overlap:
        raise BuildError(
            "Package(s) listed in both 'packages' and 'exclude_packages': "
            + ", ".join(sorted(overlap))
        )

    if "post_install_scripts" in cfg:
        scripts = cfg["post_install_scripts"]
        if not isinstance(scripts, list) or not all(
            isinstance(s, str) for s in scripts
        ):
            raise BuildError("'post_install_scripts' must be a JSON list of strings")
        cfg["post_install_scripts"] = scripts
    elif "post_install_script" in cfg:
        log(
            "WARNING: 'post_install_script' (string) is deprecated, "
            "use 'post_install_scripts' (list of strings) instead"
        )
        cfg["post_install_scripts"] = [cfg["post_install_script"]]
    else:
        raise BuildError("Config must contain 'post_install_scripts' (list of strings)")

    # --- pre_chroot_scripts: host-side scripts run right after debootstrap,
    cfg.setdefault("pre_chroot_scripts", [])
    if not isinstance(cfg["pre_chroot_scripts"], list) or not all(
        isinstance(s, str) for s in cfg["pre_chroot_scripts"]
    ):
        raise BuildError("'pre_chroot_scripts' must be a JSON list of strings")

    # --- arch ---
    cfg.setdefault("arch", "amd64")
    if cfg["arch"] not in SUPPORTED_ARCHES:
        raise BuildError(
            f"'arch' must be one of {SUPPORTED_ARCHES}, got '{cfg['arch']}'"
        )

    # --- other optional fields with defaults ---
    cfg.setdefault("hostname", cfg["distro_name"].lower().replace(" ", "-"))
    cfg.setdefault("locale", "en_US.UTF-8")
    cfg.setdefault("timezone", "UTC")
    cfg.setdefault("root_password", None)
    cfg.setdefault("live_username", None)
    if cfg.get("live_username") and not cfg.get("live_user_password"):
        cfg["live_user_password"] = cfg["live_username"]
    cfg.setdefault("extra_apt_sources", [])
    if not isinstance(cfg["extra_apt_sources"], list):
        raise BuildError("'extra_apt_sources' must be a JSON list of strings")
    cfg.setdefault("debootstrap_variant", None)
    cfg.setdefault("kernel_package", KERNEL_PACKAGE_MAP[cfg["arch"]])
    cfg.setdefault("squashfs_compression", "xz")
    cfg.setdefault("boot_append", "quiet splash")
    cfg.setdefault("iso_filename", None)
    cfg.setdefault("iso_volume_id", None)
    if cfg["iso_volume_id"] is not None:
        vol_id = cfg["iso_volume_id"]
        if not isinstance(vol_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_]{1,32}", vol_id
        ):
            raise BuildError(
                "'iso_volume_id' must be 1-32 characters, "
                "letters/digits/underscore only (leave unset to auto-generate one)"
            )

    return cfg


class LiveBuilder:
    def __init__(self, cfg, workdir, outdir):
        self.cfg = cfg
        self.arch = cfg["arch"]
        self.iso_volume_id = cfg["iso_volume_id"] or sanitize_volume_id(
            cfg["distro_name"]
        )
        self.workdir = Path(workdir).resolve()
        self.outdir = Path(outdir).resolve()

        self.chroot_dir = self.workdir / "chroot"
        self.iso_tree = self.workdir / "iso"
        self.mounted = []  # bind mounts currently active, for cleanup

    # ---------- setup ----------

    def prepare_dirs(self):
        if self.workdir.exists():
            shutil.rmtree(self.workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        if self.outdir.exists():
            shutil.rmtree(self.outdir)
        self.outdir.mkdir(parents=True, exist_ok=True)
        if self.chroot_dir.exists():
            shutil.rmtree(self.chroot_dir)
        self.chroot_dir.mkdir(parents=True, exist_ok=True)
        (self.iso_tree / "live").mkdir(parents=True, exist_ok=True)
        (self.iso_tree / "boot" / "grub").mkdir(parents=True, exist_ok=True)

    # ---------- debootstrap ----------

    def run_debootstrap(self):
        distro = self.cfg["debian_distro"]
        mirror = self.cfg["apt_mirror"]
        variant = self.cfg["debootstrap_variant"]

        host = host_arch()
        if self.arch != host:
            raise BuildError(
                f"Config arch '{self.arch}' does not match host arch '{host}'. "
                f"This script only builds for the host's own architecture -- "
                f"set 'arch' to '{host}', or build on a '{self.arch}' host."
            )

        log(
            f"Running debootstrap for '{distro}' ({self.arch}) from {mirror} into {self.chroot_dir}"
        )

        if variant:
            run(
                [
                    "debootstrap",
                    f"--arch={self.arch}",
                    f"--variant={variant}",
                    distro,
                    str(self.chroot_dir),
                    mirror,
                ]
            )
        else:
            run(
                [
                    "debootstrap",
                    f"--arch={self.arch}",
                    distro,
                    str(self.chroot_dir),
                    mirror,
                ]
            )

    # ---------- apt config inside chroot ----------

    def configure_apt(self):
        distro = self.cfg["debian_distro"]
        mirror = self.cfg["apt_mirror"]
        sources = self.chroot_dir / "etc" / "apt" / "sources.list"
        lines = [
            f"deb {mirror} {distro} main contrib non-free non-free-firmware",
            f"deb {mirror} {distro}-updates main contrib non-free non-free-firmware",
        ]
        lines.extend(self.cfg["extra_apt_sources"])
        sources.write_text("\n".join(lines) + "\n")

        # basic resolv.conf so apt can resolve the mirror inside the chroot
        resolv = self.chroot_dir / "etc" / "resolv.conf"
        resolv.write_text("nameserver 8.8.8.8\nnameserver 1.1.1.1\n")

        hostname = self.chroot_dir / "etc" / "hostname"
        hostname.write_text(self.cfg["hostname"] + "\n")

        hosts = self.chroot_dir / "etc" / "hosts"
        hosts.write_text(
            "127.0.0.1   localhost\n"
            f"127.0.1.1   {self.cfg['hostname']}\n"
            "::1         localhost ip6-localhost ip6-loopback\n"
        )

    # ---------- pre-chroot phase (host-side, rootfs not yet chrooted) ----------

    def run_pre_chroot_scripts(self):
        scripts = self.cfg["pre_chroot_scripts"]
        if not scripts:
            log("No pre_chroot_scripts provided, skipping")
            return

        scripts_dir = self.workdir / "pre_chroot_scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["ROOTFS"] = str(self.chroot_dir)
        env["ARCH"] = self.arch
        env["DISTRO_NAME"] = self.cfg["distro_name"]

        for i, script in enumerate(scripts, start=1):
            if not script.strip():
                continue
            script_name = f"pre_chroot_{i:02d}.sh"
            script_path = scripts_dir / script_name
            script_path.write_text(script)
            script_path.chmod(0o755)

            with build_step(
                f"Running pre-chroot script {i}/{len(scripts)} ({script_name})"
            ):
                run(["/bin/bash", str(script_path)], env=env)

    # ---------- chroot mount management ----------

    def bind_mount(self, host_path, chroot_relative_path):
        """Bind-mount host_path onto chroot_relative_path inside the chroot.

        Tracked in self.mounted so unmount_chroot() tears it back down
        (in reverse order) along with everything else.
        """
        target = self.chroot_dir / chroot_relative_path.lstrip("/")
        target.mkdir(parents=True, exist_ok=True)
        run(["mount", "--bind", str(host_path), str(target)])
        self.mounted.append(target)
        return target

    def mount_chroot(self):
        for b in ["/dev", "/dev/pts", "/proc", "/sys"]:
            self.bind_mount(b, b)

    def unmount_chroot(self):
        for target in reversed(self.mounted):
            try:
                run(["umount", "-lf", str(target)])
            except subprocess.CalledProcessError:
                log(f"WARNING: failed to unmount {target}, continuing")
        self.mounted = []

    def chroot_exec(self, bash_command):
        """Run a shell command string inside the chroot."""
        run(["chroot", str(self.chroot_dir), "/bin/bash", "-c", bash_command])

    # ---------- package install ----------

    def install_packages(self):
        iso_packages = list(ISO_BUILD_PACKAGES_COMMON)
        if self.arch in BIOS_CAPABLE_ARCHES:
            iso_packages += ISO_BUILD_PACKAGES_BIOS
        iso_packages.append(GRUB_EFI_PACKAGE_MAP[self.arch])

        all_packages = list(
            dict.fromkeys(
                self.cfg["packages"]
                + [self.cfg["kernel_package"]]
                + LIVE_BOOT_PACKAGES
                + iso_packages
            )
        )

        exclude = self.cfg["exclude_packages"]
        install_args = all_packages + [f"{p}-" for p in exclude]

        pkg_str = " ".join(install_args)
        log(
            f"Installing {len(all_packages)} packages inside chroot"
            + (f" (excluding {len(exclude)}: {', '.join(exclude)})" if exclude else "")
        )
        self.chroot_exec(
            "export DEBIAN_FRONTEND=noninteractive && "
            "apt-get update && "
            f"apt-get install -y {pkg_str} && "
            "apt-get clean"
        )

    # ---------- locale / timezone / users ----------

    def configure_system(self):
        locale = self.cfg["locale"]
        timezone = self.cfg["timezone"]
        log(f"Configuring locale ({locale}) and timezone ({timezone})")

        self.chroot_exec(
            f"echo '{locale} UTF-8' >> /etc/locale.gen && "
            f"locale-gen && "
            f"update-locale LANG={locale}"
        )
        self.chroot_exec(
            f"ln -sf /usr/share/zoneinfo/{timezone} /etc/localtime && "
            f"echo '{timezone}' > /etc/timezone && "
            f"dpkg-reconfigure -f noninteractive tzdata || true"
        )

        root_password = self.cfg["root_password"]
        if root_password:
            log("Setting root password")
            self.chroot_exec(f"echo 'root:{root_password}' | chpasswd")
        else:
            log("No root_password set, locking root account")
            self.chroot_exec("passwd -l root || true")

        live_user = self.cfg["live_username"]
        if live_user:
            log(f"Creating live user '{live_user}'")
            self.chroot_exec(
                f"useradd -m -s /bin/bash {live_user} || true && "
                f"echo '{live_user}:{self.cfg['live_user_password']}' | chpasswd && "
                f"echo '{live_user} ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/{live_user}"
            )

    # ---------- post-install scripts ----------

    def run_post_install_scripts(self):
        scripts = self.cfg["post_install_scripts"]
        if not scripts:
            log("No post_install_scripts provided, skipping")
            return

        tmp_dir = self.chroot_dir / "tmp"
        for i, script in enumerate(scripts, start=1):
            if not script.strip():
                continue
            script_name = f"post_install_{i:02d}.sh"
            script_path_host = tmp_dir / script_name
            script_path_host.write_text(script)
            script_path_host.chmod(0o755)

            with build_step(
                f"Running post-install script {i}/{len(scripts)} ({script_name})"
            ):
                self.chroot_exec(f"/bin/bash /tmp/{script_name}")
            script_path_host.unlink(missing_ok=True)

    # ---------- cleanup chroot artifacts before squashing ----------

    def cleanup_chroot(self):
        log("Cleaning up chroot (apt cache, machine-id, resolv.conf)")
        self.chroot_exec(
            "apt-get clean && "
            "rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* && "
            "truncate -s 0 /etc/machine-id || true"
        )
        resolv = self.chroot_dir / "etc" / "resolv.conf"
        resolv.write_text("")

    # ---------- squashfs + kernel/initrd extraction ----------

    def export_kernel_and_initrd(self):
        boot_dir = self.chroot_dir / "boot"
        live_dir = self.iso_tree / "live"

        vmlinuz = sorted(boot_dir.glob("vmlinuz-*"))
        initrd = sorted(boot_dir.glob("initrd.img-*"))
        if not vmlinuz or not initrd:
            raise BuildError(
                "Could not find kernel/initrd in chroot /boot; "
                "is the kernel package installed correctly?"
            )

        shutil.copy(vmlinuz[-1], live_dir / "vmlinuz")
        shutil.copy(initrd[-1], live_dir / "initrd")
        log(f"Copied kernel {vmlinuz[-1].name} and initrd {initrd[-1].name}")

    def build_squashfs(self):
        live_dir = self.iso_tree / "live"
        squashfs_path = live_dir / "filesystem.squashfs"
        comp = self.cfg["squashfs_compression"]
        log(
            f"Building squashfs ({comp}) of the chroot filesystem (this can take a while)"
        )
        run(
            [
                "mksquashfs",
                str(self.chroot_dir),
                str(squashfs_path),
                "-comp",
                comp,
                "-e",
                "boot",
                "-noappend",
            ]
        )

    # ---------- boot config (grub.cfg, shared by both BIOS and EFI) ----------

    def write_boot_configs(self):
        name = self.cfg["distro_name"]
        version = self.cfg["version"]
        label = f"{name} {version}".strip()
        boot_append = self.cfg["boot_append"]

        (self.iso_tree / "boot" / "grub" / "grub.cfg").write_text(f"""\
set timeout=5
set default=0

menuentry "{label} (live)" {{
    linux /live/vmlinuz boot=live components {boot_append}
    initrd /live/initrd
}}
""")

    # ---------- final ISO build ----------

    def build_iso(self):

        name = self.cfg["distro_name"].lower().replace(" ", "-")
        version = self.cfg["version"]
        iso_name = self.cfg["iso_filename"] or f"{name}-{version}-{self.arch}.iso"
        iso_path = self.outdir / iso_name

        log(f"Building ISO ({self.arch}) with grub-mkrescue: {iso_path}")

        iso_tree_rel = self.iso_tree.relative_to(self.workdir)
        tmp_iso_name = "grub-mkrescue-output.iso"

        self.mount_chroot()  # grub-mkrescue's internal mkfs.vfat step needs /dev
        self.bind_mount(self.workdir, "mnt/iso_build")
        try:
            self.chroot_exec(
                f"grub-mkrescue "
                f"-o /mnt/iso_build/{tmp_iso_name} "
                f"/mnt/iso_build/{iso_tree_rel} "
                f'-- -volid "{self.iso_volume_id}"'
            )
        finally:
            self.unmount_chroot()

        produced = self.workdir / tmp_iso_name
        if not produced.exists():
            raise BuildError(f"grub-mkrescue did not produce an ISO at {produced}")
        shutil.move(str(produced), str(iso_path))
        return iso_path

    # ---------- orchestration ----------

    def build(self):
        try:
            with build_step("Preparing build directories"):
                self.prepare_dirs()
            with build_step("Running debootstrap"):
                self.run_debootstrap()
            with build_step("Configuring apt sources"):
                self.configure_apt()
            self.run_pre_chroot_scripts()
            with build_step("Mounting chroot filesystems"):
                self.mount_chroot()
            with build_step("Installing packages in chroot"):
                self.install_packages()
            with build_step("Configuring locale/timezone/users"):
                self.configure_system()
            self.run_post_install_scripts()
            with build_step("Cleaning up chroot"):
                self.cleanup_chroot()
        finally:
            with build_step("Unmounting chroot filesystems"):
                self.unmount_chroot()

        with build_step("Exporting kernel and initrd"):
            self.export_kernel_and_initrd()
        with build_step("Building squashfs"):
            self.build_squashfs()
        with build_step("Writing bootloader configs"):
            self.write_boot_configs()
        with build_step("Building final ISO"):
            return self.build_iso()


def parse_args():
    p = argparse.ArgumentParser(
        description="Build a custom Debian live ISO from a JSON config."
    )
    p.add_argument("config", help="Path to JSON config file")
    p.add_argument(
        "--workdir",
        default=None,
        help="Working directory for chroot/build files (default: temp dir)",
    )
    p.add_argument(
        "--outdir",
        default="./output",
        help="Directory to place the final ISO in (default: ./output)",
    )
    p.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Don't delete the working directory (chroot) after building, "
        "useful for debugging a failed build",
    )
    return p.parse_args()


def main():
    args = parse_args()
    builder = None
    try:
        require_root()
        for tool in (
            "debootstrap",
            "chroot",
            "mksquashfs",
            "mount",
            "umount",
            "dpkg",
        ):
            require_tool(tool)

        cfg = load_config(args.config)

        workdir = args.workdir or tempfile.mkdtemp(prefix="live-build-")
        builder = LiveBuilder(cfg, workdir, args.outdir)

        log(
            f"Distro: {cfg['distro_name']} {cfg['version']} "
            f"(arch: {cfg['arch']}, base: {cfg['debian_distro']})"
        )
        log(f"Workdir: {builder.workdir}")
        log(f"Output dir: {builder.outdir}")

        iso_path = builder.build()
        log(f"Done! ISO created at: {iso_path}")
        return 0

    except BuildError as e:
        print("\n[build_live_iso] BUILD FAILED", file=sys.stderr)
        print(f"[build_live_iso] {e}", file=sys.stderr)
        return 1

    except KeyboardInterrupt:
        print("\n[build_live_iso] Interrupted by user", file=sys.stderr)
        return 130

    except Exception:
        print(
            "\n[build_live_iso] UNEXPECTED ERROR (please report this)", file=sys.stderr
        )
        traceback.print_exc()
        return 2

    finally:
        if builder is not None:
            builder.unmount_chroot()
            if not args.keep_workdir and not args.workdir:
                log(f"Cleaning up temporary workdir {builder.workdir}")
                shutil.rmtree(builder.workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
