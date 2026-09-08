import configparser
import json
import subprocess
import unittest
from pathlib import Path

import build


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATHS = [
    ROOT / "PersisOS-2.0-amd64.json",
    ROOT / "PersisOS-2.0-arm64.json",
]
SERVER_CONFIG_PATH = ROOT / "PersisOS-Server-2.0-amd64.json"
ALL_CONFIG_PATHS = CONFIG_PATHS + [SERVER_CONFIG_PATH]


class ProjectValidationTests(unittest.TestCase):
    def test_manifests_load_and_stay_in_sync(self):
        manifests = []
        for path in CONFIG_PATHS:
            config = build.load_config(str(path))
            self.assertEqual(config["debian_distro"], "trixie")
            self.assertEqual(len(config["packages"]), len(set(config["packages"])))
            manifests.append(config)

        self.assertEqual(
            {manifest["architecture"] for manifest in manifests}, {"amd64", "arm64"}
        )
        self.assertEqual(
            {manifest["iso_volume_id"] for manifest in manifests},
            {"PERSISOS_2_0_AMD64", "PERSISOS_2_0_ARM64"},
        )
        self.assertEqual(
            {manifest["iso_filename"] for manifest in manifests},
            {"PersisOS-2.0-amd64.iso", "PersisOS-2.0-arm64.iso"},
        )
        for manifest in manifests:
            manifest.pop("arch", None)
            manifest.pop("architecture", None)
            manifest.pop("iso_volume_id", None)
            manifest.pop("iso_filename", None)
        self.assertEqual(manifests[0], manifests[1])

        required_desktop_packages = {
            "kwin-x11",
            "kwin-wayland",
            "plasma-workspace-wayland",
            "power-profiles-daemon",
            "udisks2",
            "fwupd",
            "plasma-disks",
        }
        for path in CONFIG_PATHS:
            manifest = json.loads(path.read_text())
            self.assertTrue(required_desktop_packages.issubset(manifest["packages"]))

    def test_inline_build_scripts_have_valid_shell_syntax(self):
        for path in ALL_CONFIG_PATHS:
            manifest = json.loads(path.read_text())
            scripts = manifest["pre_chroot_scripts"] + manifest["post_install_scripts"]
            for index, script in enumerate(scripts):
                result = subprocess.run(
                    ["bash", "-n"],
                    input=script,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"{path.name} script {index}: {result.stderr}",
                )

    def test_desktop_shortcuts_are_valid_and_executable(self):
        desktop_files = [
            ROOT
            / "assets/persisos-plasma-theme/etc/skel/Desktop/Home.desktop",
            ROOT
            / "assets/persisos-plasma-theme/etc/skel/Desktop/Trash.desktop",
            ROOT
            / "assets/persisos-plasma-theme/usr/share/applications/install-persisos.desktop",
        ]
        for path in desktop_files:
            parser = configparser.ConfigParser(interpolation=None, strict=True)
            parser.optionxform = str
            parser.read(path)
            entry = parser["Desktop Entry"]
            self.assertIn(entry["Type"], {"Application", "Link"})
            self.assertTrue(entry["Name"])
            self.assertTrue(entry["Icon"])
            self.assertTrue(path.stat().st_mode & 0o111)

        home = configparser.ConfigParser(interpolation=None)
        home.read(desktop_files[0])
        self.assertEqual(home["Desktop Entry"]["Exec"], "dolphin")

        trash = configparser.ConfigParser(interpolation=None)
        trash.read(desktop_files[1])
        self.assertEqual(trash["Desktop Entry"]["URL"], "trash:/")

        installer = configparser.ConfigParser(interpolation=None)
        installer.read(desktop_files[2])
        self.assertEqual(installer["Desktop Entry"]["TryExec"], "calamares")
        self.assertEqual(installer["Desktop Entry"]["Exec"], "pkexec calamares")
        self.assertNotEqual(desktop_files[2].parent, desktop_files[0].parent)

        for path in CONFIG_PATHS:
            manifest = json.loads(path.read_text())
            self.assertIn("calamares", manifest["packages"])
            self.assertIn("pkexec", manifest["packages"])

    def test_server_manifest_is_headless_and_server_focused(self):
        config = build.load_config(str(SERVER_CONFIG_PATH))
        self.assertEqual(config["architecture"], "amd64")
        self.assertEqual(config["iso_filename"], "PersisOS-Server-2.0-amd64.iso")
        self.assertEqual(len(config["packages"]), len(set(config["packages"])))

        required = {
            "openssh-server",
            "nftables",
            "fail2ban",
            "podman",
            "smartmontools",
            "qemu-guest-agent",
        }
        self.assertTrue(required.issubset(config["packages"]))

        graphical = {
            "kde-plasma-desktop",
            "xserver-xorg",
            "sddm",
            "calamares",
            "firefox-esr",
        }
        self.assertTrue(graphical.isdisjoint(config["packages"]))

        scripts = "\n".join(config["post_install_scripts"])
        self.assertIn("systemctl disable ssh", scripts)


if __name__ == "__main__":
    unittest.main()
