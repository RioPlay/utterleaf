import unittest
from release_contract import package_metadata, verify_upgrade


class ReleaseContractTest(unittest.TestCase):
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
