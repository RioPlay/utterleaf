import re
import unittest
from pathlib import Path


ANDROID_ROOT = Path(__file__).resolve().parents[1]


class LifecycleHostBuildContractTest(unittest.TestCase):
    def test_connected_fixture_installs_the_product_first(self):
        script = (ANDROID_ROOT / "lifecycleHost/build.gradle.kts").read_text()
        wiring = re.search(
            r'tasks\.matching\s*\{\s*it\.name\s*==\s*"connectedDebugAndroidTest"\s*\}'
            r'\.configureEach\s*\{(?P<body>[^}]*)\}',
            script,
            re.DOTALL,
        )
        self.assertIsNotNone(wiring, "Lifecycle-host task wiring must stay lazy and debug-specific")
        self.assertIn('dependsOn(":app:installDebug")', wiring.group("body"))
        self.assertNotIn("mustRunAfter", wiring.group("body"))

    def test_fixture_stays_opt_in_and_cannot_build_a_release_variant(self):
        settings = (ANDROID_ROOT / "settings.gradle.kts").read_text()
        self.assertRegex(
            settings,
            r'if\s*\(providers\.gradleProperty\("includeLifecycleHost"\)'
            r'\.orNull\s*==\s*"true"\)\s*\{\s*include\(":lifecycleHost"\)\s*\}',
        )
        script = (ANDROID_ROOT / "lifecycleHost/build.gradle.kts").read_text()
        self.assertIn(
            'beforeVariants(selector().withBuildType("release")) { it.enable = false }',
            script,
        )


if __name__ == "__main__":
    unittest.main()
