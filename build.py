#!/usr/bin/env python3
"""
PersisOS live ISO builder
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Architecture maps
# ---------------------------------------------------------------------------

KERNEL_PACKAGES = {
    "amd64": "linux-image-amd64",
    "arm64": "linux-image-arm64",
    "armhf": "linux-image-armmp",
}

GRUB_EFI_PACKAGES = {
    "amd64": "grub-efi-amd64-bin",
    "arm64": "grub-efi-arm64-bin",
    "armhf": "grub-efi-arm-bin",
}

GRUB_EFI_FORMAT = {
    "amd64": "x86_64-efi",
    "arm64": "arm64-efi",
    "armhf": "arm-efi",
}

GRUB_EFI_BINARY = {
    "amd64": "bootx64.efi",
    "arm64": "bootaa64.efi",
    "armhf": "bootarm.efi",
}

LIVE_PACKAGES = [
    "live-boot",
    "systemd-sysv",
    "sudo",
    "locales",
]

HOST_BUILD_TOOLS = [
    "debootstrap",
    "mksquashfs",
    "xorriso",
    "mtools",
    "mkdosfs",
    "grub-mkimage",
    "mkfs.vfat",
]

# ---------------------------------------------------------------------------
# GRUB module lists — self-contained and Ventoy-safe
# ---------------------------------------------------------------------------

GRUB_BIOS_MODULES = [
    "biosdisk",
    "part_gpt",
    "part_msdos",
    "fat",
    "iso9660",
    "udf",
    "linux",
    "initrd",
    "normal",
    "configfile",
    "search",
    "search_fs_uuid",
    "search_fs_file",
    "search_label",
    "loopback",
    "gfxterm",
    "all_video",
    "test",
    "true",
    "echo",
    "help",
    "ls",
    "reboot",
    "halt",
]

GRUB_EFI_MODULES = [
    "part_gpt",
    "part_msdos",
    "fat",
    "iso9660",
    "udf",
    "linux",
    "initrd",
    "normal",
    "configfile",
    "search",
    "search_fs_uuid",
    "search_fs_file",
    "search_label",
    "loopback",
    "gfxterm",
    "all_video",
    "test",
    "true",
    "echo",
    "help",
    "ls",
    "reboot",
    "halt",
]

# ---------------------------------------------------------------------------
# Error handling helpers
# ---------------------------------------------------------------------------


class BuildError(Exception):
    pass


def run(cmd, **kwargs):
    """Run a command, raising BuildError on failure."""
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        raise BuildError(
            f"Command failed (exit {result.returncode}): {' '.join(str(c) for c in cmd)}"
        )
    return result


def build_step(name):
    """Context manager that prints step banners."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        print(f"\n{'='*60}")
        print(f"  {name}")
        print(f"{'='*60}")
        try:
            yield
        except BuildError:
            raise
        except Exception as exc:
            raise BuildError(f"Step '{name}' failed: {exc}") from exc

    return _ctx()


def require_root():
    if os.geteuid() != 0:
        raise BuildError("This script must be run as root.")


def require_tool(name):
    if shutil.which(name) is None:
        raise BuildError(f"Required tool not found: {name}")


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

REQUIRED_KEYS = ["distro_name", "version", "debian_distro", "apt_mirror", "packages"]
DEFAULTS = {
    "locale": "en_US.UTF-8",
    "timezone": "UTC",
    "squashfs_compression": "xz",
    "splash": "",
    "pre_chroot_scripts": [],
    "post_install_scripts": [],
    "architecture": "amd64",
}


def load_config(path: str) -> dict:
    with open(path) as f:
        cfg = json.load(f)

    missing = [k for k in REQUIRED_KEYS if k not in cfg]
    if missing:
        raise BuildError(f"Config missing required keys: {', '.join(missing)}")

    for k, v in DEFAULTS.items():
        cfg.setdefault(k, v)

    # Derive iso_volume_id from distro name if not set
    if "iso_volume_id" not in cfg:
        vol = re.sub(r"[^A-Za-z0-9_]", "_", cfg["distro_name"])[:32]
        cfg["iso_volume_id"] = vol

    if not re.fullmatch(r"[A-Za-z0-9_]{1,32}", cfg["iso_volume_id"]):
        raise BuildError(
            f"iso_volume_id must match [A-Za-z0-9_]{{1,32}}, got: {cfg['iso_volume_id']!r}"
        )

    return cfg


# ---------------------------------------------------------------------------
# LiveBuilder
# ---------------------------------------------------------------------------


class LiveBuilder:
    def __init__(
        self, config: dict, workdir: str, outdir: str, keep_workdir: bool = False
    ):
        self.cfg = config
        self.workdir = Path(workdir)
        self.outdir = Path(outdir)
        self.keep_workdir = keep_workdir
        self.arch = config["architecture"]

        self.chroot = self.workdir / "chroot"
        self.iso_root = self.workdir / "iso"

    # ------------------------------------------------------------------
    # Directory setup
    # ------------------------------------------------------------------

    def prepare_dirs(self):
        with build_step("Preparing directories"):
            for d in [
                self.chroot,
                self.iso_root / "live",
                self.iso_root / "boot" / "grub",
                self.iso_root / ".disk",
            ]:
                d.mkdir(parents=True, exist_ok=True)
            self.outdir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # debootstrap
    # ------------------------------------------------------------------

    def run_debootstrap(self):
        with build_step("Running debootstrap"):
            run(
                [
                    "debootstrap",
                    "--arch",
                    self.arch,
                    self.cfg["debian_distro"],
                    str(self.chroot),
                    self.cfg["apt_mirror"],
                ]
            )

    # ------------------------------------------------------------------
    # APT configuration
    # ------------------------------------------------------------------

    def configure_apt(self):
        with build_step("Configuring APT"):
            sources = (
                f"deb {self.cfg['apt_mirror']} {self.cfg['debian_distro']} "
                "main contrib non-free non-free-firmware\n"
            )
            (self.chroot / "etc" / "apt" / "sources.list").write_text(sources)
            self._chroot(["apt-get", "update"])

    # ------------------------------------------------------------------
    # Scripts
    # ------------------------------------------------------------------

    def pre_chroot_scripts(self):
        for script in self.cfg.get("pre_chroot_scripts", []):
            with build_step(f"Pre-chroot script: {script}"):
                run(["bash", script])

    def post_install_scripts(self):
        for script in self.cfg.get("post_install_scripts", []):
            with build_step(f"Post-install script: {script}"):
                dest = self.chroot / "tmp" / Path(script).name
                shutil.copy2(script, dest)
                dest.chmod(0o755)
                self._chroot(["bash", f"/tmp/{Path(script).name}"])
                dest.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Package installation
    # ------------------------------------------------------------------

    def install_packages(self):
        with build_step("Installing packages"):
            pkgs = (
                list(self.cfg["packages"])
                + LIVE_PACKAGES
                + [KERNEL_PACKAGES[self.arch]]
            )
            if self.arch in GRUB_EFI_PACKAGES:
                pkgs.append(GRUB_EFI_PACKAGES[self.arch])
            if self.arch == "amd64":
                pkgs += ["grub-pc-bin", "grub2-common"]

            env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
            self._chroot(
                ["apt-get", "install", "-y", "--no-install-recommends"] + pkgs,
                extra_env=env,
            )

    # ------------------------------------------------------------------
    # System configuration
    # ------------------------------------------------------------------

    def configure_system(self):
        with build_step("Configuring system"):
            # Locale
            locale = self.cfg["locale"]
            locale_gen = self.chroot / "etc" / "locale.gen"
            lines = locale_gen.read_text() if locale_gen.exists() else ""
            if f"# {locale}" in lines:
                lines = lines.replace(f"# {locale}", locale)
            else:
                lines += f"\n{locale} UTF-8\n"
            locale_gen.write_text(lines)
            self._chroot(["locale-gen"])
            (self.chroot / "etc" / "locale.conf").write_text(f"LANG={locale}\n")

            # Timezone
            tz = self.cfg["timezone"]
            tz_file = self.chroot / "usr" / "share" / "zoneinfo" / tz
            localtime = self.chroot / "etc" / "localtime"
            if localtime.exists() or localtime.is_symlink():
                localtime.unlink()
            localtime.symlink_to(f"/usr/share/zoneinfo/{tz}")
            (self.chroot / "etc" / "timezone").write_text(tz + "\n")

            # Hostname
            (self.chroot / "etc" / "hostname").write_text(
                self.cfg["distro_name"].lower() + "\n"
            )

    # ------------------------------------------------------------------
    # Chroot cleanup
    # ------------------------------------------------------------------

    def cleanup_chroot(self):
        with build_step("Cleaning chroot"):
            env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
            self._chroot(["apt-get", "clean"], extra_env=env)
            for p in (self.chroot / "var" / "cache" / "apt" / "archives").glob("*.deb"):
                p.unlink(missing_ok=True)
            for p in (self.chroot / "tmp").glob("*"):
                if p.is_file():
                    p.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Kernel / initrd export
    # ------------------------------------------------------------------

    def export_kernel_and_initrd(self):
        with build_step("Exporting kernel and initrd"):
            vmlinuz_list = sorted((self.chroot / "boot").glob("vmlinuz-*"))
            initrd_list = sorted((self.chroot / "boot").glob("initrd.img-*"))
            if not vmlinuz_list:
                raise BuildError("No kernel found in chroot/boot/")
            if not initrd_list:
                raise BuildError("No initrd found in chroot/boot/")
            shutil.copy2(vmlinuz_list[-1], self.iso_root / "live" / "vmlinuz")
            shutil.copy2(initrd_list[-1], self.iso_root / "live" / "initrd")
            print(f"  Kernel : {vmlinuz_list[-1].name}")
            print(f"  Initrd : {initrd_list[-1].name}")

    # ------------------------------------------------------------------
    # Squashfs
    # ------------------------------------------------------------------

    def build_squashfs(self):
        with build_step("Building squashfs"):
            squashfs_path = self.iso_root / "live" / "filesystem.squashfs"
            squashfs_path.unlink(missing_ok=True)
            run(
                [
                    "mksquashfs",
                    str(self.chroot),
                    str(squashfs_path),
                    "-comp",
                    self.cfg["squashfs_compression"],
                    "-e",
                    "boot",
                    "-noappend",
                ]
            )

    # ------------------------------------------------------------------
    # GRUB config
    # ------------------------------------------------------------------

    def write_boot_configs(self):
        with build_step("Writing GRUB configuration"):
            vol_id = self.cfg["iso_volume_id"]
            distro = self.cfg["distro_name"]
            version = self.cfg["version"]
            splash = self.cfg.get("splash", "")
            splash_param = f"splash {splash}".strip() if splash else ""

            grub_cfg = f"""\
set default=0
set timeout=5
set gfxpayload=keep

# Locate the ISO root — works under Ventoy, direct boot, and QEMU.
# We try three methods in order; the first to succeed sets $root.
if search --no-floppy --set=root --label "{vol_id}" ; then
    echo "Found ISO root by volume label: {vol_id}"
elif search --no-floppy --set=root --file /live/filesystem.squashfs ; then
    echo "Found ISO root by filesystem marker"
else
    echo "WARNING: could not locate ISO root; boot may fail"
fi

menuentry "{distro} {version} (live)" {{
    linux  /live/vmlinuz boot=live components quiet {splash_param}
    initrd /live/initrd
}}

menuentry "{distro} {version} (live, nomodeset)" {{
    linux  /live/vmlinuz boot=live components quiet nomodeset {splash_param}
    initrd /live/initrd
}}

menuentry "{distro} {version} (live, debug)" {{
    linux  /live/vmlinuz boot=live components
    initrd /live/initrd
}}
"""
            (self.iso_root / "boot" / "grub" / "grub.cfg").write_text(grub_cfg)
            (self.iso_root / ".disk" / "info").write_text(
                f"{distro} {version} - Live\n"
            )

    # ------------------------------------------------------------------
    # ISO assembly
    # ------------------------------------------------------------------

    def _find_grub_lib(self, grub_arch: str) -> Path:
        """Return the path to pre-built GRUB modules for grub_arch."""
        for base in ("/usr/lib/grub", "/usr/share/grub"):
            p = Path(base) / grub_arch
            if p.is_dir():
                return p
        raise BuildError(f"GRUB module directory not found for arch '{grub_arch}'")

    def build_iso(self):
        with build_step("Building ISO image"):
            vol_id = self.cfg["iso_volume_id"]
            distro = self.cfg["distro_name"]
            version = self.cfg["version"]
            grub_dir = self.iso_root / "boot" / "grub"

            # ----------------------------------------------------------
            # The early config is embedded directly into the GRUB core
            # image.  Using search here — rather than a hardcoded
            # (cd) or (hd0) device — is what fixes the Ventoy
            # "you must load the kernel first" error on real hardware:
            # Ventoy remaps device handles so a hardcoded device alias
            # never resolves, but search finds the volume by label or
            # by the presence of a known file regardless of remapping.
            # ----------------------------------------------------------
            early_cfg = (
                f'search --no-floppy --set=root --label "{vol_id}"\n'
                f'if [ -z "$root" ]; then\n'
                f"    search --no-floppy --set=root --file /live/filesystem.squashfs\n"
                f"fi\n"
                f"set prefix=($root)/boot/grub\n"
            )

            xorriso_args = [
                "xorriso",
                "-as",
                "mkisofs",
                "-iso-level",
                "3",
                "-volid",
                vol_id,
                "-full-iso9660-filenames",
                "-rational-rock",
                "-joliet",
            ]

            # ----------------------------------------------------------
            # BIOS boot (i386-pc) — amd64 only
            # ----------------------------------------------------------
            if self.arch == "amd64":
                grub_bios_arch = "i386-pc"
                grub_bios_lib = self._find_grub_lib(grub_bios_arch)

                # Copy BIOS modules into the ISO tree
                bios_mod_dst = grub_dir / grub_bios_arch
                bios_mod_dst.mkdir(parents=True, exist_ok=True)
                for mod in Path(grub_bios_lib).glob("*.mod"):
                    shutil.copy2(mod, bios_mod_dst / mod.name)
                # Also copy .lst files (module dependency lists)
                for lst in Path(grub_bios_lib).glob("*.lst"):
                    shutil.copy2(lst, bios_mod_dst / lst.name)

                # Build standalone BIOS core image with early config baked in
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".cfg", delete=False
                ) as ecfg:
                    ecfg.write(early_cfg)
                    early_cfg_path = ecfg.name

                bios_core = grub_dir / "bios.img"
                cdboot = Path(grub_bios_lib) / "cdboot.img"
                bios_core_raw = grub_dir / "core_bios.img"

                try:
                    run(
                        [
                            "grub-mkimage",
                            "--format",
                            grub_bios_arch,
                            "--output",
                            str(bios_core_raw),
                            "--prefix",
                            "/boot/grub",
                            "--config",
                            early_cfg_path,
                            "--directory",
                            str(grub_bios_lib),
                        ]
                        + GRUB_BIOS_MODULES
                    )
                finally:
                    Path(early_cfg_path).unlink(missing_ok=True)

                # Concatenate cdboot.img + core.img → bios.img
                with open(bios_core, "wb") as out_f:
                    out_f.write(cdboot.read_bytes())
                    out_f.write(bios_core_raw.read_bytes())
                bios_core_raw.unlink(missing_ok=True)

                # Locate boot_hybrid.img for MBR
                boot_hybrid = Path(grub_bios_lib) / "boot_hybrid.img"
                if not boot_hybrid.exists():
                    boot_hybrid = Path("/usr/lib/grub/i386-pc/boot_hybrid.img")
                if not boot_hybrid.exists():
                    raise BuildError("boot_hybrid.img not found — install grub-pc-bin")

                xorriso_args += [
                    "-eltorito-boot",
                    "boot/grub/bios.img",
                    "-no-emul-boot",
                    "-boot-load-size",
                    "4",
                    "-boot-info-table",
                    "--grub2-boot-info",
                    "--grub2-mbr",
                    str(boot_hybrid),
                ]

            # ----------------------------------------------------------
            # EFI boot
            # ----------------------------------------------------------
            if self.arch in GRUB_EFI_FORMAT:
                efi_arch = GRUB_EFI_FORMAT[self.arch]
                efi_binary = GRUB_EFI_BINARY[self.arch]
                grub_efi_lib = self._find_grub_lib(efi_arch)

                # Copy EFI modules into the ISO tree
                efi_mod_dst = grub_dir / efi_arch
                efi_mod_dst.mkdir(parents=True, exist_ok=True)
                for mod in Path(grub_efi_lib).glob("*.mod"):
                    shutil.copy2(mod, efi_mod_dst / mod.name)
                for lst in Path(grub_efi_lib).glob("*.lst"):
                    shutil.copy2(lst, efi_mod_dst / lst.name)

                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".cfg", delete=False
                ) as ecfg:
                    ecfg.write(early_cfg)
                    early_cfg_path = ecfg.name

                efi_out = grub_dir / efi_binary
                try:
                    run(
                        [
                            "grub-mkimage",
                            "--format",
                            efi_arch,
                            "--output",
                            str(efi_out),
                            "--prefix",
                            "/boot/grub",
                            "--config",
                            early_cfg_path,
                            "--directory",
                            str(grub_efi_lib),
                        ]
                        + GRUB_EFI_MODULES
                    )
                finally:
                    Path(early_cfg_path).unlink(missing_ok=True)

                # Build a FAT12 ESP image and put the EFI binary inside it
                efi_img = grub_dir / "efi.img"
                efi_img.unlink(missing_ok=True)
                # Size: 1.44 MB is sufficient for a standalone EFI binary
                run(["dd", "if=/dev/zero", f"of={efi_img}", "bs=1k", "count=1440"])
                run(["mkfs.vfat", "-F", "12", "-n", "GRUB_EFI", str(efi_img)])
                run(["mmd", "-i", str(efi_img), "::/EFI", "::/EFI/BOOT"])
                run(
                    [
                        "mcopy",
                        "-i",
                        str(efi_img),
                        str(efi_out),
                        f"::/EFI/BOOT/{efi_binary}",
                    ]
                )

                xorriso_args += [
                    "-eltorito-alt-boot",
                    "-e",
                    "boot/grub/efi.img",
                    "-no-emul-boot",
                    "-isohybrid-gpt-basdat",
                ]

            # ----------------------------------------------------------
            # Final xorriso invocation
            # ----------------------------------------------------------
            iso_name = f"{distro}-{version}-{self.arch}.iso"
            iso_out = self.outdir / iso_name
            xorriso_args += ["-output", str(iso_out), str(self.iso_root)]
            run(xorriso_args)
            print(f"\n  ISO written to: {iso_out}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _chroot(self, cmd, extra_env=None):
        env = extra_env or os.environ.copy()
        run(["chroot", str(self.chroot)] + cmd, env=env)

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def build(self):
        try:
            self.prepare_dirs()
            self.run_debootstrap()
            self.configure_apt()
            self.pre_chroot_scripts()
            self.install_packages()
            self.configure_system()
            self.post_install_scripts()
            self.cleanup_chroot()
            self.export_kernel_and_initrd()
            self.build_squashfs()
            self.write_boot_configs()
            self.build_iso()
            print("\n✓ Build complete.")
        finally:
            if not self.keep_workdir:
                shutil.rmtree(self.workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="PersisOS live ISO builder")
    parser.add_argument("config", help="Path to JSON build config")
    parser.add_argument(
        "--workdir", default=None, help="Working directory (default: temp dir)"
    )
    parser.add_argument(
        "--outdir", default="./output", help="Output directory for the ISO"
    )
    parser.add_argument(
        "--keep-workdir", action="store_true", help="Do not delete workdir after build"
    )
    args = parser.parse_args()

    require_root()
    for tool in HOST_BUILD_TOOLS:
        require_tool(tool)

    cfg = load_config(args.config)

    if args.workdir:
        workdir = args.workdir
        Path(workdir).mkdir(parents=True, exist_ok=True)
        builder = LiveBuilder(cfg, workdir, args.outdir, keep_workdir=args.keep_workdir)
        builder.build()
    else:
        with tempfile.TemporaryDirectory(prefix="persisOS_build_") as tmpdir:
            builder = LiveBuilder(
                cfg, tmpdir, args.outdir, keep_workdir=args.keep_workdir
            )
            builder.build()


if __name__ == "__main__":
    try:
        main()
    except BuildError as e:
        print(f"\n✗ Build failed: {e}", file=sys.stderr)
        sys.exit(1)
