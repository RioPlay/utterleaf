import unittest
import json
import re
from pathlib import Path
from release_contract import package_metadata, verify_upgrade


class ReleaseContractTest(unittest.TestCase):
    def test_signed_upgrade_and_reinstall_each_verify_preservation(self):
        workflow = (
            Path(__file__).resolve().parents[3] / ".github/workflows/android-release.yml"
        ).read_text()
        smoke = workflow.split("- name: Signed APK installation smoke test", 1)[1].split(
            "- name: Publish Android prerelease independently of desktop", 1
        )[0]
        predecessor = "predecessor/Utterleaf-Android-0.1.0-alpha03.apk"
        candidate_install = "adb install -r release/Utterleaf-Android-${{ env.VERSION }}.apk"
        seed_if_predecessor = (
            f"if [ -f {predecessor} ]; then adb install {predecessor} && "
            "adb shell am start -W -n org.utterleaf.voice/.SetupActivity && "
            "python3 mobile/android/tools/preserve_upgrade.py seed; fi"
        )
        verify_if_predecessor = (
            f"if [ -f {predecessor} ]; then python3 "
            "mobile/android/tools/preserve_upgrade.py verify; fi"
        )

        self.assertEqual(smoke.count(seed_if_predecessor), 1)
        self.assertEqual(smoke.count(candidate_install), 2)
        self.assertEqual(smoke.count("preserve_upgrade.py verify"), 2)
        self.assertEqual(smoke.count(verify_if_predecessor), 2)

        cursor = 0
        for command in (
            seed_if_predecessor,
            candidate_install,
            verify_if_predecessor,
            candidate_install,
            verify_if_predecessor,
            "adb shell am start -W -n org.utterleaf.voice/.SetupActivity",
        ):
            cursor = smoke.index(command, cursor) + len(command)

    def test_obtainium_selects_only_signed_android_channel(self):
        config = json.loads((Path(__file__).parents[1] / "app/src/main/assets/obtainium.json").read_text())
        settings = json.loads(config["additionalSettings"])
        self.assertEqual(config["id"], "org.utterleaf.voice")
        self.assertTrue(settings["includePrereleases"])
        self.assertFalse(settings["verifyLatestTag"])
        self.assertTrue(settings["fallbackToOlderReleases"])
        self.assertTrue(settings["versionDetection"])
        version = re.fullmatch(settings["versionExtractionRegEx"], "android-v0.1.0-alpha03")
        self.assertEqual(version[int(settings["matchGroupToUse"])], "0.1.0-alpha03")
        self.assertRegex("Utterleaf Android 0.1.0-alpha03", settings["filterReleaseTitlesByRegEx"])
        for title in ("Utterleaf v0.3.8", "Utterleaf Voice for Android — alpha 2"):
            self.assertIsNone(re.search(settings["filterReleaseTitlesByRegEx"], title))
        self.assertRegex("Utterleaf-Android-0.1.0-alpha03.apk", settings["apkFilterRegEx"])
        for name in ("Utterleaf-Voice-0.1.0-alpha02-debug.apk", "app-release-unsigned.apk", "Utterleaf-windows.zip"):
            self.assertIsNone(re.search(settings["apkFilterRegEx"], name))

    def test_identity_and_debug_rejection(self):
        base = "package: name='org.utterleaf.voice' versionCode='3' versionName='0.1.0-alpha03'\n"
        metadata = package_metadata(base, "0.1.0-alpha03", "a" * 64)
        self.assertEqual(metadata["versionCode"], 3)
        for badging in (base.replace("org.utterleaf.voice", "wrong.package"),
                        base + "application-debuggable\n", base.replace("alpha03", "alpha02")):
            with self.assertRaises(ValueError):
                package_metadata(badging, "0.1.0-alpha03", "a" * 64)

    def test_update_rejects_downgrade_and_signer_change(self):
        previous = dict(packageName="org.utterleaf.voice", versionCode=3, signingCertificateSha256="a" * 64)
        current = dict(previous, versionCode=4)
        verify_upgrade(current, previous)
        for wrong in (dict(current, versionCode=3), dict(current, versionCode=2),
                      dict(current, signingCertificateSha256="b" * 64), dict(current, packageName="other")):
            with self.assertRaises(ValueError):
                verify_upgrade(wrong, previous)


if __name__ == "__main__":
    unittest.main()
