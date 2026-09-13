import hashlib
import unittest
from collections import Counter

import emoji_catalog


class EmojiCatalogToolTest(unittest.TestCase):
    def test_pinned_inputs_and_generated_outputs_match(self):
        catalog, notice = emoji_catalog.expected_outputs()
        self.assertEqual(catalog, emoji_catalog.RESOURCE.read_bytes())
        self.assertEqual(notice, emoji_catalog.NOTICE.read_bytes())
        self.assertEqual(
            "05319ac5b761f60eac2441c62ca253eb30b77313d7b8a20949157ccfd4b01914",
            hashlib.sha256(catalog).hexdigest(),
        )
        self.assertEqual(558943, len(catalog))
        text = catalog.decode("utf-8")
        self.assertLessEqual(len(text), emoji_catalog.MAX_CATALOG_CHARS)
        self.assertLessEqual(max(map(len, text.splitlines())), emoji_catalog.MAX_LINE_CHARS)

    def test_full_fully_qualified_catalog_and_categories(self):
        entries = emoji_catalog.parse_emoji_test(
            emoji_catalog.read_pinned("emoji-test-17.0.txt"), enforce_catalog_contract=True
        )
        self.assertEqual(3944, len(entries))
        self.assertEqual(3944, len({entry.codepoints for entry in entries}))
        self.assertEqual(
            Counter(
                {
                    "people-body": 2418,
                    "flags": 270,
                    "objects": 266,
                    "symbols": 224,
                    "travel-places": 219,
                    "smileys-emotion": 171,
                    "animals-nature": 160,
                    "food-drink": 131,
                    "activities": 85,
                }
            ),
            Counter(entry.category for entry in entries),
        )
        self.assertNotIn((0x1F3FB,), {entry.codepoints for entry in entries})

    def test_annotations_cover_every_emitted_entry(self):
        text = emoji_catalog.build_catalog()
        records = [line for line in text.splitlines() if line and not line.startswith("#")]
        self.assertEqual(3944, len(records))
        self.assertTrue(all(len(record.split("\t")) == 6 for record in records))
        grinning = next(record for record in records if record.startswith("1F600\t"))
        self.assertIn("\tgrinning face\t", grinning)
        self.assertIn("smile", grinning.split("\t")[-1].split("|"))

    def test_tone_family_removes_only_tones_and_variation_selectors(self):
        self.assertEqual(
            (0x1F469, 0x200D, 0x2695),
            emoji_catalog.family_codepoints((0x1F469, 0x1F3FD, 0x200D, 0x2695, 0xFE0F)),
        )
        self.assertNotEqual(
            emoji_catalog.family_codepoints((0x1F469, 0x200D, 0x2695, 0xFE0F)),
            emoji_catalog.family_codepoints((0x1F468, 0x200D, 0x2695, 0xFE0F)),
        )

    def test_xml_allows_only_the_exact_official_doctype(self):
        valid = b'<?xml version="1.0"?><!DOCTYPE ldml SYSTEM "../../common/dtd/ldml.dtd"><ldml />'
        self.assertEqual("ldml", emoji_catalog._safe_xml_root("fixture", valid).tag)
        with self.assertRaisesRegex(ValueError, "unexpected or missing DOCTYPE"):
            emoji_catalog._safe_xml_root("fixture", b'<!DOCTYPE ldml SYSTEM "https://example.test/x"><ldml />')
        with self.assertRaisesRegex(ValueError, "entity declarations are forbidden"):
            emoji_catalog._safe_xml_root(
                "fixture",
                b'<!DOCTYPE ldml SYSTEM "../../common/dtd/ldml.dtd"><!ENTITY x "bad"><ldml />',
            )

    def test_malformed_duplicate_and_oversized_inputs_fail(self):
        duplicate = (
            "# group: Smileys & Emotion\n# subgroup: face-smiling\n"
            "1F600 ; fully-qualified # X E1.0 grinning face\n"
            "1F600 ; fully-qualified # X E1.0 grinning face\n"
        ).encode()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            emoji_catalog.parse_emoji_test(duplicate)
        malformed = b"# group: Smileys & Emotion\nthis is not a record\n"
        with self.assertRaisesRegex(ValueError, "malformed"):
            emoji_catalog.parse_emoji_test(malformed)
        unknown_group = b"# group: Surprise\n# subgroup: new\n"
        with self.assertRaisesRegex(ValueError, "unknown group"):
            emoji_catalog.parse_emoji_test(unknown_group)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            emoji_catalog.verify_bytes("emoji-test-17.0.txt", b"x" * (emoji_catalog.MAX_INPUT_BYTES + 1))

    def test_pinned_catalog_shape_drift_fails_generation(self):
        data = emoji_catalog.read_pinned("emoji-test-17.0.txt")
        changed = data.replace(b"; fully-qualified", b"; minimally-qualified", 1)
        with self.assertRaisesRegex(ValueError, "catalog shape changed"):
            emoji_catalog.parse_emoji_test(changed, enforce_catalog_contract=True)


if __name__ == "__main__":
    unittest.main()
