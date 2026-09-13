import unittest
from pathlib import Path
from preserve_upgrade import (
    ACTIVE, ACTIVE_BYTES, MARKER, MARKER_BYTES, PREFS, KEYBOARD_XML,
    assert_preserved, missing_after_upgrade, parse_keyboard_prefs, seed_files,
)


class PreserveUpgradeTest(unittest.TestCase):
    def test_seeded_prefs_round_trip(self):
        values = parse_keyboard_prefs(KEYBOARD_XML.encode())
        self.assertEqual(True, values["terminal"])
        self.assertEqual(500, values["holdDelayMs"])

    def test_upgrade_keeps_prefs_and_model_marker(self):
        before = seed_files()
        after = dict(before)
        after[PREFS] = b"""<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <boolean name="numberRow" value="false" />
    <boolean name="terminal" value="true" />
    <int name="holdDelayMs" value="500" />
</map>
"""
        assert_preserved(before, after)

    def test_manifest_disables_backup_without_clearing_upgrades(self):
        manifest = Path(__file__).parents[1].joinpath("app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn('android:allowBackup="false"', manifest)

    def test_upgrade_fails_if_prefs_or_models_change(self):
        before = seed_files()
        wiped = {PREFS: KEYBOARD_XML.replace("true", "false").encode()}
        problems = missing_after_upgrade(before, wiped)
        self.assertTrue(any("terminal" in item for item in problems))
        self.assertTrue(any(MARKER in item for item in problems))
        self.assertTrue(any(ACTIVE in item for item in problems))
        with self.assertRaises(ValueError) as failure:
            assert_preserved(before, {MARKER: MARKER_BYTES, ACTIVE: ACTIVE_BYTES})
        self.assertIn("keyboard.xml", str(failure.exception))
        self.assertIn("must keep keyboard preferences and models", str(failure.exception))


if __name__ == "__main__":
    unittest.main()
