import json
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from audit_dependencies import KAPT_ADVISORY, MAVEN_JAR, affected_version, main, maven_comparator, scan


def compare_numeric(left, right):
    a = tuple(map(int, left.split(".")))
    b = tuple(map(int, right.split(".")))
    return (a > b) - (a < b)


class DependencyAuditTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "advisories.zip"
        self.inventory = {"gradleVersion": "8.14.6", "configurations": [":app:debugRuntimeClasspath"],
                          "dependencies": [{"name": "example:library", "version": "1.0"}]}

    def write_advisory(self, versions, advisory_id="GHSA-example", **extra):
        advisory = {"id": advisory_id, "affected": [{"package": {"ecosystem": "Maven", "name": "example:library"},
                                                     "versions": versions}], **extra}
        with zipfile.ZipFile(self.database, "w") as archive:
            archive.writestr("advisory.json", json.dumps(advisory))

    def test_affected_and_fixed_versions(self):
        self.write_advisory(["1.0"])
        self.assertEqual(scan(self.inventory, self.database, compare_numeric)["findings"][0]["status"], "affected")
        self.inventory["dependencies"][0]["version"] = "1.1"
        self.assertEqual(scan(self.inventory, self.database, compare_numeric)["findings"], [])

    def test_withdrawn_is_ignored(self):
        self.write_advisory(["1.0"], withdrawn="2026-01-01T00:00:00Z")
        self.assertEqual(scan(self.inventory, self.database, compare_numeric)["findings"], [])

    def test_kapt_finding_returns_when_kapt_is_enabled(self):
        self.inventory["dependencies"][0]["name"] = "org.jetbrains.kotlin:kotlin-gradle-plugin"
        self.write_advisory(["1.0"], KAPT_ADVISORY)
        with zipfile.ZipFile(self.database) as archive:
            advisory = json.loads(archive.read("advisory.json"))
        advisory["affected"][0]["package"]["name"] = "org.jetbrains.kotlin:kotlin-gradle-plugin"
        with zipfile.ZipFile(self.database, "w") as archive:
            archive.writestr("advisory.json", json.dumps(advisory))
        self.assertEqual(scan(self.inventory, self.database, compare_numeric)["findings"][0]["status"], "not-applicable")
        self.inventory["configurations"].append(":app:kapt")
        self.assertEqual(scan(self.inventory, self.database, compare_numeric)["findings"][0]["status"], "affected")

    def test_empty_inventory_and_missing_enumeration_fail(self):
        self.write_advisory([])
        with self.assertRaisesRegex(ValueError, "Neither enumerated"):
            scan(self.inventory, self.database, compare_numeric)
        self.inventory["dependencies"] = []
        with self.assertRaisesRegex(ValueError, "Empty inventory"):
            scan(self.inventory, self.database, compare_numeric)

    def test_invalid_archive_does_not_pass(self):
        self.database.write_text("network error")
        with self.assertRaises(zipfile.BadZipFile):
            scan(self.inventory, self.database, compare_numeric)

    def test_range_union_and_fixed_boundary(self):
        affected = {"versions": ["1.0"], "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.0"}]}]}
        self.assertTrue(affected_version("1.1", affected, compare_numeric))
        self.assertFalse(affected_version("2.0", affected, compare_numeric))
        affected["versions"].append("2.0")
        self.assertTrue(affected_version("2.0", affected, compare_numeric))

    def test_unknown_ranges_and_events_fail_even_when_enumerated(self):
        for ranges in ([{"type": "UNKNOWN", "events": []}],
                       [{"type": "ECOSYSTEM", "events": [{"mystery": "1.0"}]}]):
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                affected_version("1.0", {"versions": ["1.0"], "ranges": ranges}, compare_numeric)

    def test_last_affected_limit_and_multiple_intervals(self):
        affected = {"ranges": [{"type": "ECOSYSTEM", "events": [
            {"introduced": "1.0"}, {"last_affected": "1.2"},
            {"introduced": "2.0"}, {"limit": "2.2"}]}]}
        for version, expected in [("0.9", False), ("1.2", True), ("1.3", False), ("2.1", True), ("2.2", False)]:
            self.assertEqual(affected_version(version, affected, compare_numeric), expected)

    def test_maven_helper_qualifiers_and_malformed_input(self):
        jar = Path(__file__).resolve().parents[1] / "build/reports/security" / MAVEN_JAR
        if not jar.exists():
            self.skipTest("Run audit --download with JDK 17 for comparator integration")
        with maven_comparator(jar) as compare:
            self.assertLess(compare("4.2.0.Alpha1", "4.2.0"), 0)
            self.assertLess(compare("4.0.0-RC1", "4.0.0"), 0)
            self.assertEqual(compare("1.0.Final", "1.0"), 0)
            with self.assertRaisesRegex(ValueError, "Invalid Maven"):
                compare("1.0\tmalformed", "1.0")

    def test_failed_cli_replaces_stale_success_report(self):
        output = Path(self.directory.name) / "audit.json"
        output.write_text('{"status":"complete"}')
        with patch("sys.argv", ["audit", "--inventory", str(self.database), "--output", str(output)]):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(), 2)
        self.assertEqual(json.loads(output.read_text())["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
