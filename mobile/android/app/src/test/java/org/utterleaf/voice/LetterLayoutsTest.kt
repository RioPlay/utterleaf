package org.utterleaf.voice

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LetterLayoutsTest {
    private val expected = mapOf(
        LetterLayout.QWERTY to listOf("qwertyuiop", "asdfghjkl", "zxcvbnm"),
        LetterLayout.QWERTZ to listOf("qwertzuiop", "asdfghjkl", "yxcvbnm"),
        LetterLayout.AZERTY to listOf("azertyuiop", "qsdfghjklm", "wxcvbn"),
    )

    @Test fun rowsAreFixedCompleteAndUnique() {
        expected.forEach { (layout, rows) ->
            assertEquals(rows, layout.rows)
            val letters = rows.joinToString("")
            assertEquals(26, letters.length)
            assertEquals(('a'..'z').toSet(), letters.toSet())
        }
    }

    @Test fun storedValuesRoundTripAndUnknownValuesUseQwerty() {
        LetterLayout.entries.forEach { assertEquals(it, LetterLayout.fromStored(it.stored)) }
        assertEquals(LetterLayout.QWERTY, LetterLayout.fromStored(null))
        assertEquals(LetterLayout.QWERTY, LetterLayout.fromStored("future-or-corrupt"))
    }

    @Test fun hintsFollowPositionsAndAlternateMenusEndWithTheSameHint() {
        val hintRows = listOf("1234567890", "@#$%&-+()/", "*\"':;!?")
        LetterLayout.entries.forEach { layout ->
            layout.rows.zip(hintRows).forEach { (letters, hints) ->
                letters.forEachIndexed { index, letter ->
                    val hint = hints[index].toString()
                    assertEquals("$layout $letter", hint, AlternateCharacters.hint(letter, layout))
                    val choices = AlternateCharacters.choices(letter, false, layout)
                    assertEquals("$layout $letter", hint, choices.last())
                    assertEquals(choices.size, choices.toSet().size)
                    assertTrue(choices.size <= 10)
                }
            }
        }
        assertNull(AlternateCharacters.hint('?', LetterLayout.AZERTY))
    }

    @Test fun qwertyAlternateOrderAndCaseRemainStable() {
        assertEquals(listOf("á", "à", "ä", "â", "å", "ā", "æ", "ã", "@"),
            AlternateCharacters.choices('a', false, LetterLayout.QWERTY))
        assertEquals(listOf("Á", "À", "Ä", "Â", "Å", "Ā", "Æ", "Ã", "@"),
            AlternateCharacters.choices('a', true, LetterLayout.QWERTY))
        assertEquals("6", AlternateCharacters.choices('y', false, LetterLayout.QWERTY).last())
        assertEquals("*", AlternateCharacters.choices('z', false, LetterLayout.QWERTY).last())
    }
}
