package org.utterleaf.voice

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AlternateCharactersTest {
    @Test fun mappingCoversAllTwentySixLetters() {
        ('a'..'z').forEach { key ->
            assertTrue("missing hint for $key", AlternateCharacters.hint(key) != null)
            assertTrue("missing choices for $key", AlternateCharacters.choices(key, false).isNotEmpty())
        }
    }

    @Test fun uppercaseAccentsAndGermanSharpSAreStrings() {
        assertEquals(listOf("Á", "À", "Ä", "Â", "Å", "Ā", "Æ", "Ã", "@"),
            AlternateCharacters.choices('a', true))
        assertTrue(AlternateCharacters.choices('s', true).contains("SS"))
        assertEquals(AlternateCharacters.choices('s', false).last(), AlternateCharacters.hint('S'))
    }

    @Test fun choicesAreDistinctAndBounded() {
        ('a'..'z').forEach { key ->
            val lower = AlternateCharacters.choices(key, false)
            val upper = AlternateCharacters.choices(key, true)
            assertTrue(lower.size <= 10)
            assertTrue(upper.size <= 10)
            assertEquals(lower.size, lower.toSet().size)
            assertEquals(upper.size, upper.toSet().size)
        }
    }

    @Test fun nonLettersHaveNoAlternates() {
        listOf('1', '?', ' ', 'ß').forEach { key ->
            assertEquals(null, AlternateCharacters.hint(key))
            assertTrue(AlternateCharacters.choices(key, false).isEmpty())
            assertTrue(AlternateCharacters.choices(key, true).isEmpty())
        }
    }
}
