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
        for manifest in manifests:
            manifest.pop("arch", None)
            manifest.pop("architecture", None)
        self.assertEqual(manifests[0], manifests[1])

    def test_inline_build_scripts_have_valid_shell_syntax(self):
        for path in CONFIG_PATHS:
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
        self.assertEqual(installer["Desktop Entry"]["Exec"], "pkexec calamares")
        self.assertNotEqual(desktop_files[2].parent, desktop_files[0].parent)


if __name__ == "__main__":
    unittest.main()
