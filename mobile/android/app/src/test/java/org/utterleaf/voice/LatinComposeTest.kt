package org.utterleaf.voice

import java.text.Normalizer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LatinComposeTest {
    @Test fun everyDeclaredPairIsOneNfcCodePointWithUppercase() {
        LatinComposeMark.entries.forEach { mark ->
            assertEquals(mark.bases.length, mark.bases.toSet().size)
            mark.bases.forEach { base ->
                val lower = checkNotNull(LatinCompose.compose(mark, base, false))
                val upper = checkNotNull(LatinCompose.compose(mark, base, true))
                for (value in listOf(lower, upper)) {
                    assertEquals(value, Normalizer.normalize(value, Normalizer.Form.NFC))
                    assertEquals(1, value.codePointCount(0, value.length))
                }
                assertEquals(lower.uppercase(), upper)
            }
        }
    }

    @Test fun reviewedMarksHaveUniqueIdentityAndExpectedRepresentativeResults() {
        assertEquals(LatinComposeMark.entries.size, LatinComposeMark.entries.map { it.label }.toSet().size)
        assertEquals(LatinComposeMark.entries.size, LatinComposeMark.entries.map { it.symbol }.toSet().size)
        assertEquals("é", LatinCompose.compose(LatinComposeMark.ACUTE, 'e', false))
        assertEquals("é", LatinCompose.compose(LatinComposeMark.ACUTE, 'E', false))
        assertEquals("É", LatinCompose.compose(LatinComposeMark.ACUTE, 'E', true))
        assertEquals("Ñ", LatinCompose.compose(LatinComposeMark.TILDE, 'n', true))
        assertEquals("ž", LatinCompose.compose(LatinComposeMark.CARON, 'z', false))
        assertEquals("Ż", LatinCompose.compose(LatinComposeMark.DOT_ABOVE, 'z', true))
    }

    @Test fun unsupportedPairsReturnNothing() {
        LatinComposeMark.entries.forEach { mark ->
            ('a'..'z').filterNot { it in mark.bases }.forEach { base ->
                assertNull("$mark $base", LatinCompose.compose(mark, base, false))
                assertNull("$mark ${base.uppercaseChar()}", LatinCompose.compose(mark, base, true))
            }
        }
        assertNull(LatinCompose.compose(LatinComposeMark.ACUTE, '1', false))
        // These Unicode characters have case relationships with ASCII letters,
        // but are not declared input bases for this deliberately small table.
        assertNull(LatinCompose.compose(LatinComposeMark.ACUTE, '\u0130', false)) // I with dot
        assertNull(LatinCompose.compose(LatinComposeMark.ACUTE, '\u0131', true)) // dotless i
        assertNull(LatinCompose.compose(LatinComposeMark.ACUTE, '\u017f', true)) // long s
        assertTrue(LatinComposeMark.entries.all { it.bases.isNotEmpty() })
    }
}
