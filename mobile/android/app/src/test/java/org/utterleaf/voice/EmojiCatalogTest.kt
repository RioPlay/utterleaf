package org.utterleaf.voice

import java.io.StringReader
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class EmojiCatalogTest {
    @Test fun parsesTheCompleteCheckedInCatalog() {
        val resource = listOf(
            File("app/src/main/res/raw/emoji_catalog.txt"),
            File("src/main/res/raw/emoji_catalog.txt"),
        ).firstOrNull(File::isFile) ?: error("checked-in emoji catalog not found")
        val catalog = resource.bufferedReader(Charsets.UTF_8).use(EmojiCatalog::parse)

        assertEquals(3944, catalog.entries.size)
        assertEquals(
            listOf("smileys-emotion", "people-body", "animals-nature", "food-drink", "travel-places",
                "activities", "objects", "symbols", "flags"),
            catalog.categories,
        )
        assertEquals("grinning face", catalog.entries.first().name)
        assertEquals("😀", catalog.entries.first().sequence)
        assertEquals(26, catalog.entries.maxOf { catalog.familyVariants(it).size })
    }

    @Test fun parsesExactSequencesCategoriesAndImmutableViews() {
        val catalog = EmojiCatalog.parse(fixture())

        assertEquals(6, catalog.entries.size)
        assertEquals(listOf("smileys-emotion", "people-body", "flags"), catalog.categories)
        assertEquals("👩🏽‍⚕️", catalog.entries[3].sequence)
        assertEquals("🇺🇸", catalog.entries.last().sequence)
        assertThrows(UnsupportedOperationException::class.java) {
            (catalog.entries as MutableList).add(catalog.entries.first())
        }
        assertThrows(UnsupportedOperationException::class.java) {
            (catalog.entries.first().keywords as MutableList).add("changed")
        }
    }

    @Test fun groupsToneVariantsAndKeepsGenderSeparate() {
        val catalog = EmojiCatalog.parse(fixture())
        val wave = catalog.entries.first { it.sequence == "👋" }
        val tonedWave = catalog.entries.first { it.sequence == "👋🏻" }
        val womanHealth = catalog.entries.first { it.sequence == "👩🏽‍⚕️" }
        val manHealth = catalog.entries.first { it.sequence == "👨‍⚕️" }

        assertTrue(wave.isCanonical)
        assertFalse(tonedWave.isCanonical)
        assertEquals(listOf("👋", "👋🏻"), catalog.familyVariants(tonedWave).map(EmojiEntry::sequence))
        assertEquals(3, catalog.categoryEntries(EmojiCategory.PEOPLE_BODY).size)
        assertTrue(womanHealth.isCanonical) // The fixture has no no-tone woman-health entry.
        assertTrue(manHealth.isCanonical)
        assertTrue(womanHealth.familyKey != manHealth.familyKey)
    }

    @Test fun searchRanksExactPrefixTokensAndKeywordsDeterministically() {
        val catalog = EmojiCatalog.parse(fixture())

        assertEquals("😀", catalog.search("grinning face", 1).single().sequence)
        assertEquals("👋", catalog.search("waving", 1).single().sequence)
        assertEquals("👋🏻", catalog.search("light wave", 1).single().sequence)
        assertEquals("👩🏽‍⚕️", catalog.search("doctor woman", 1).single().sequence)
        assertEquals("cafe", EmojiCatalog.normalizeQuery("  Café! "))
        assertTrue(catalog.search("   ").isEmpty())
    }

    @Test fun queryAndResultBoundsAreEnforced() {
        val catalog = EmojiCatalog.parse(fixture())

        assertThrows(IllegalArgumentException::class.java) {
            catalog.search("x".repeat(EmojiCatalog.MAX_QUERY_LENGTH + 1))
        }
        assertThrows(IllegalArgumentException::class.java) {
            catalog.search("face", EmojiCatalog.MAX_SEARCH_LIMIT + 1)
        }
        assertTrue(catalog.search("face", 0).isEmpty())
    }

    @Test fun malformedHeaderCountCategorySequenceAndFamilyFail() {
        assertFails("header", fixture().replace("# utterleaf-emoji-catalog-v1", "# wrong"))
        assertFails("count", fixture().replace("# count=6", "# count=5"))
        assertFails("category", fixture().replaceFirst("smileys-emotion", "unknown"))
        assertFails("Unicode scalar", fixture().replaceFirst("1F600", "110000"))
        assertFails("family", fixture().replaceFirst("hand-fingers-open\t1F44B\twaving hand", "hand-fingers-open\t1F44C\twaving hand"))
    }

    @Test fun duplicateAndReaderBoundsFail() {
        val duplicate = fixture().replace("# count=6", "# count=7") +
            "1F600\tsmileys-emotion\tface-smiling\t1F600\tgrinning face\tface|grin\n"
        assertFails("duplicate", duplicate)
        val longLine = "# utterleaf-emoji-catalog-v1\n# count=1\n" + "X".repeat(EmojiCatalog.MAX_LINE_CHARS + 1)
        assertFails("line exceeds", longLine)
        assertFails("character bound", StringReader("#\n".repeat(EmojiCatalog.MAX_CATALOG_CHARS / 2 + 1)))
    }

    private fun assertFails(fragment: String, text: String) {
        val error = assertThrows(IllegalArgumentException::class.java) { EmojiCatalog.parse(text) }
        assertTrue("expected '$fragment' in '${error.message}'", error.message.orEmpty().contains(fragment))
    }

    private fun assertFails(fragment: String, reader: StringReader) {
        val error = assertThrows(IllegalArgumentException::class.java) { EmojiCatalog.parse(reader) }
        assertTrue("expected '$fragment' in '${error.message}'", error.message.orEmpty().contains(fragment))
    }

    private fun fixture(): String = """
        # utterleaf-emoji-catalog-v1
        # SPDX-License-Identifier: Unicode-3.0
        # unicode=17.0
        # cldr=48@acd6d88ae493633240e19a87a721076a8a75c310
        # count=6
        1F600\tsmileys-emotion\tface-smiling\t1F600\tgrinning face\tface|grin|happy
        1F44B\tpeople-body\thand-fingers-open\t1F44B\twaving hand\thand|hello|wave
        1F44B 1F3FB\tpeople-body\thand-fingers-open\t1F44B\twaving hand: light skin tone\thand|light skin tone|wave
        1F469 1F3FD 200D 2695 FE0F\tpeople-body\tperson-role\t1F469 200D 2695\twoman health worker: medium skin tone\tdoctor|healthcare|woman
        1F468 200D 2695 FE0F\tpeople-body\tperson-role\t1F468 200D 2695\tman health worker\tdoctor|healthcare|man
        1F1FA 1F1F8\tflags\tcountry-flag\t1F1FA 1F1F8\tflag: United States\tflag|United States
    """.trimIndent().replace("\\t", "\t") + "\n"
}
