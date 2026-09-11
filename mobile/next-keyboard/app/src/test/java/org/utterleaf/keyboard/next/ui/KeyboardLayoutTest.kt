package org.utterleaf.keyboard.next.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class KeyboardLayoutTest {
    @Test fun standardLayoutIsFiniteAndNonOverlapping() {
        val snapshot = KeyboardLayout.standard(1080f, 900f)
        assertTrue(snapshot.keys.isNotEmpty())
        snapshot.keys.forEach { key ->
            assertTrue(key.bounds.left.isFinite() && key.bounds.top.isFinite())
            assertTrue(key.bounds.right > key.bounds.left && key.bounds.bottom > key.bounds.top)
        }
        snapshot.keys.forEachIndexed { index, first ->
            snapshot.keys.drop(index + 1).forEach { second ->
                val vertical = first.bounds.top < second.bounds.bottom && second.bounds.top < first.bounds.bottom
                val horizontal = first.bounds.left < second.bounds.right && second.bounds.left < first.bounds.right
                assertTrue("overlap at $index", !(vertical && horizontal))
            }
        }
    }

    @Test fun smallLetterGapResolvesToNearestLetter() {
        val snapshot = KeyboardLayout.standard(1080f, 900f)
        val first = snapshot.keys.first { it.label == "q" }
        val second = snapshot.keys.first { it.label == "w" }
        val x = (first.bounds.right + second.bounds.left) / 2f
        val y = first.bounds.top + first.bounds.height / 2f
        assertNotNull(KeyboardLayout.resolve(snapshot, x, y))
    }

    @Test fun outsideAndUtilityZonesDoNotInferLetters() {
        val snapshot = KeyboardLayout.standard(1080f, 900f)
        assertNull(KeyboardLayout.resolve(snapshot, -1f, 10f))
        val shift = snapshot.keys.first { it.action.kind == KeyAction.Kind.SHIFT }
        val gap = KeyboardLayout.resolve(snapshot, shift.bounds.right + 1f, shift.bounds.top + shift.bounds.height / 2f)
        assertEquals(null, gap?.action?.kind?.takeIf { it == KeyAction.Kind.TEXT })
    }
    @Test fun symbolsContainDigitsAndReturnToLetters() {
        val snapshot = KeyboardLayout.symbols(1080f, 900f)
        val labels = snapshot.keys.filter { it.action.kind == KeyAction.Kind.PUNCTUATION }.map { it.label }
        assertTrue(labels.containsAll(listOf("1", "0", "@", ";")))
        assertEquals("ABC", snapshot.keys.first { it.action.kind == KeyAction.Kind.SYMBOLS }.label)
    }

    @Test fun optionalNumberRowAddsOneSharedRowWithoutSymbolDuplicates() {
        val scale = 2.75f
        val daily = KeyboardLayout.standard(320f * scale, 296f * scale, 56f * scale, scale, numberRow = true)
        val symbols = KeyboardLayout.symbols(320f * scale, 296f * scale, 56f * scale, scale, numberRow = true)
        assertEquals(296f * scale, daily.keyboardBounds.height, 1f)
        assertEquals("1234567890".map { it.toString() }, daily.keys.take(10).map { it.label })
        (0..9).forEach { digit -> assertEquals(1, symbols.keys.count { it.label == digit.toString() }) }
        val bottomDaily = daily.keys.first { it.action.kind == KeyAction.Kind.SYMBOLS }.bounds.top
        val bottomSymbols = symbols.keys.first { it.action.kind == KeyAction.Kind.SYMBOLS }.bounds.top
        assertEquals(bottomDaily, bottomSymbols, 0.01f)
    }

    @Test fun tinyGeometryFallsBackWithoutNegativeBounds() {
        assertTrue(KeyboardLayout.standard(10f, 10f).keys.isEmpty())
        assertTrue(KeyboardLayout.standard(960f, 660f, 154f, 2.75f).keys.isNotEmpty())
        assertTrue(KeyboardLayout.standard(960f, 1f, 154f, 2.75f).keys.isEmpty())
        assertTrue(KeyboardLayout.standard(960f, 660f, 154f, Float.NaN).keys.isEmpty())
        val phone = KeyboardLayout.standard(320f * 2.75f, 236f * 2.75f, 56f * 2.75f, 2.75f)
        assertTrue(phone.keys.first { it.action.kind == KeyAction.Kind.SHIFT }.bounds.width >= 48f * 2.75f - 1f)
        assertTrue(phone.keys.first { it.action.kind == KeyAction.Kind.ENTER }.bounds.width >= 48f * 2.75f - 1f)
    }
}
