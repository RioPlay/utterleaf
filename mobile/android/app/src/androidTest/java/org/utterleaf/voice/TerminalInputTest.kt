package org.utterleaf.voice

import android.view.InputDevice
import android.view.KeyCharacterMap
import android.view.KeyEvent
import android.view.View
import android.view.inputmethod.BaseInputConnection
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Synthetic connections verify dispatch contracts, not physical terminal support. */
@RunWith(AndroidJUnit4::class)
class TerminalInputTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()

    private class Connection(view: View) : BaseInputConnection(view, true) {
        val events = mutableListOf<KeyEvent>()
        val commits = mutableListOf<String>()
        var failDown = false
        var throwDown = false
        override fun sendKeyEvent(event: KeyEvent): Boolean {
            events.add(KeyEvent(event))
            if (event.action == KeyEvent.ACTION_DOWN && throwDown) throw IllegalStateException("Synthetic closed connection")
            return !(event.action == KeyEvent.ACTION_DOWN && failDown)
        }
        override fun commitText(text: CharSequence?, newCursorPosition: Int): Boolean {
            assertEquals(1, newCursorPosition)
            commits.add(text.toString())
            return true
        }
        override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence {
            fail("Terminal dispatch must not read surrounding text")
            return ""
        }
        override fun getTextAfterCursor(length: Int, flags: Int): CharSequence {
            fail("Terminal dispatch must not read surrounding text")
            return ""
        }
        override fun getSelectedText(flags: Int): CharSequence {
            fail("Terminal dispatch must not read selected text")
            return ""
        }
    }

    private fun withConnection(test: (Connection) -> Unit) {
        instrumentation.runOnMainSync { test(Connection(View(instrumentation.targetContext))) }
    }

    private fun assertBalanced(events: List<KeyEvent>) {
        assertTrue(events.isNotEmpty())
        val held = mutableSetOf<Int>()
        for (event in events) {
            assertEquals(KeyCharacterMap.VIRTUAL_KEYBOARD, event.deviceId)
            assertEquals(InputDevice.SOURCE_KEYBOARD, event.source)
            assertTrue(event.flags and KeyEvent.FLAG_SOFT_KEYBOARD != 0)
            assertTrue(event.flags and KeyEvent.FLAG_KEEP_TOUCH_MODE != 0)
            assertTrue(event.eventTime >= event.downTime)
            when (event.action) {
                KeyEvent.ACTION_DOWN -> assertTrue("Duplicate key-down", held.add(event.keyCode))
                KeyEvent.ACTION_UP -> assertTrue("Key-up without key-down", held.remove(event.keyCode))
                else -> fail("Unexpected key event action")
            }
        }
        assertTrue("A modifier/key remained held", held.isEmpty())
    }

    @Test fun ctrlCAndAltXPreserveModifiersAndNeverCommitPlainText() = withConnection { connection ->
        assertTrue(TerminalInput.printable(connection, "c", ctrl=true))
        assertBalanced(connection.events)
        assertTrue(connection.events.filter { it.keyCode == KeyEvent.KEYCODE_C }.let {
            it.size == 2 && it.all { event -> event.isCtrlPressed && !event.isAltPressed }
        })
        connection.events.clear()
        assertTrue(TerminalInput.printable(connection, "x", alt=true))
        assertBalanced(connection.events)
        assertTrue(connection.events.filter { it.keyCode == KeyEvent.KEYCODE_X }.let {
            it.size == 2 && it.all { event -> event.isAltPressed && !event.isCtrlPressed }
        })
        assertTrue(connection.commits.isEmpty())
    }

    @Test fun uppercaseRetainsShiftWhenCtrlAndAltAreMerged() = withConnection { connection ->
        assertTrue(TerminalInput.printable(connection, "C", ctrl=true, alt=true))
        assertBalanced(connection.events)
        val letter = connection.events.filter { it.keyCode == KeyEvent.KEYCODE_C }
        assertEquals(2, letter.size)
        assertTrue(letter.all { it.isCtrlPressed && it.isAltPressed && it.isShiftPressed })
        assertTrue(connection.commits.isEmpty())
    }

    @Test fun terminalControlKeysHaveBalancedSoftKeyboardEvents() = withConnection { connection ->
        for (code in listOf(KeyEvent.KEYCODE_ESCAPE, KeyEvent.KEYCODE_TAB, KeyEvent.KEYCODE_F1,
            KeyEvent.KEYCODE_DEL, KeyEvent.KEYCODE_FORWARD_DEL, KeyEvent.KEYCODE_PAGE_UP, KeyEvent.KEYCODE_PAGE_DOWN,
            KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN)) {
            connection.events.clear()
            assertTrue(TerminalInput.send(connection, code, ctrl=true, alt=true, shift=true))
            assertEquals(2, connection.events.size)
            assertBalanced(connection.events)
            assertTrue(connection.events.all { it.keyCode == code && it.isCtrlPressed && it.isAltPressed && it.isShiftPressed })
        }
        assertTrue(connection.commits.isEmpty())
    }

    @Test fun modifierMetadataDoesNotLeakToLaterEvents() = withConnection { connection ->
        assertTrue(TerminalInput.send(connection, KeyEvent.KEYCODE_C, ctrl=true, shift=true))
        connection.events.clear()
        assertTrue(TerminalInput.send(connection, KeyEvent.KEYCODE_TAB))
        assertTrue(connection.events.all { !it.isCtrlPressed && !it.isAltPressed && !it.isShiftPressed })
        assertBalanced(connection.events)
    }
    @Test fun editorSelectionBalancesShiftAndStopsWhenModifierRejected() = withConnection { connection ->
        assertTrue(TerminalInput.select(connection, KeyEvent.KEYCODE_DPAD_LEFT))
        assertEquals(listOf(KeyEvent.KEYCODE_SHIFT_LEFT, KeyEvent.KEYCODE_DPAD_LEFT,
            KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_SHIFT_LEFT), connection.events.map { it.keyCode })
        assertBalanced(connection.events)
        connection.events.clear(); connection.failDown = true
        assertFalse(TerminalInput.select(connection, KeyEvent.KEYCODE_DPAD_LEFT))
        assertEquals(listOf(KeyEvent.KEYCODE_SHIFT_LEFT, KeyEvent.KEYCODE_SHIFT_LEFT), connection.events.map { it.keyCode })
        assertEquals(KeyEvent.ACTION_UP, connection.events.last().action)
    }

    @Test fun failedOrThrowingDownStillAttemptsRelease() = withConnection { connection ->
        for (throwing in listOf(false, true)) {
            connection.events.clear()
            connection.failDown = !throwing
            connection.throwDown = throwing
            assertFalse(TerminalInput.send(connection, KeyEvent.KEYCODE_ESCAPE))
            assertBalanced(connection.events)
            connection.events.clear()
            assertFalse(TerminalInput.printable(connection, "C", ctrl=true))
            assertBalanced(connection.events)
            assertTrue(connection.commits.isEmpty())
        }
    }

    @Test fun plainUnicodeCommitsButUnsupportedModifiedStringsAreRejected() = withConnection { connection ->
        assertTrue(TerminalInput.printable(connection, "Café 名前"))
        assertEquals(listOf("Café 名前"), connection.commits)
        for (value in listOf("", "ab", "é", "😀", "\n", "\t", "\u0000", "\u007f")) {
            assertFalse(TerminalInput.printable(connection, value, ctrl=true))
            assertFalse(TerminalInput.printable(connection, value, alt=true))
        }
        assertEquals(listOf("Café 名前"), connection.commits)
        assertTrue(connection.events.isEmpty())
        assertFalse(TerminalInput.printable(connection, ""))
    }

    @Test fun missingConnectionAndUnknownKeyFailWithoutDispatch() = withConnection { connection ->
        assertFalse(TerminalInput.send(null, KeyEvent.KEYCODE_ESCAPE))
        assertFalse(TerminalInput.printable(null, "a", ctrl=true))
        assertFalse(TerminalInput.printable(null, "text"))
        assertFalse(TerminalInput.send(connection, KeyEvent.KEYCODE_UNKNOWN))
        assertFalse(TerminalInput.send(connection, Int.MAX_VALUE))
        assertTrue(connection.events.isEmpty())
    }

    @Test fun rawEditorModeDispatchesAsciiWithoutPlainTextFallback() = withConnection { connection ->
        assertTrue(TerminalInput.printable(connection, "a", forceKeyEvents=true))
        assertBalanced(connection.events)
        assertEquals(2, connection.events.size)
        assertTrue(connection.events.all { it.keyCode == KeyEvent.KEYCODE_A && !it.isCtrlPressed && !it.isAltPressed })
        connection.events.clear()
        for (value in listOf("ab", "名前", "", "\n")) {
            assertFalse(TerminalInput.printable(connection, value, forceKeyEvents=true))
        }
        assertTrue(connection.events.isEmpty())
        assertTrue(connection.commits.isEmpty())
    }

    @Test fun panelModifiersAreOneShotAndResetAcrossFields() {
        instrumentation.runOnMainSync {
            val plain = mutableListOf<String>()
            val modified = mutableListOf<Triple<String, Boolean, Boolean>>()
            val special = mutableListOf<List<Any>>()
            var accepted = true
            val panel = TypingPanel(instrumentation.targetContext, KeyboardOptions(terminal=true),
                { plain.add(it); accepted }, {}, {}, {}, {}, {}, {},
                { code, ctrl, alt, shift -> special.add(listOf(code, ctrl, alt, shift)); accepted },
                { text, ctrl, alt -> modified.add(Triple(text, ctrl, alt)); accepted })
            fun buttons(view: View): List<android.widget.Button> = when (view) {
                is android.widget.Button -> listOf(view)
                is android.view.ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
                else -> emptyList()
            }
            fun key(label: String) = buttons(panel.view).single { it.contentDescription == label }
            panel.reset(true, false, "Enter")
            key("Control off").performClick(); key("c").performClick(); key("c").performClick()
            assertEquals(listOf(Triple("c", true, false)), modified)
            assertEquals(listOf("c"), plain)
            key("Shift off").performClick(); key("!").performClick(); key("1").performClick()
            assertEquals(listOf("!", "1"), plain.takeLast(2))
            assertFalse("Shifted number is one-shot", key("Shift off").isSelected)
            key("Keyboard tools").performClick(); key("Caps lock off").performClick()
            key("1").performClick()
            assertEquals("Caps lock must not alter digits", "1", plain.last())
            key("Caps lock on").performClick(); key("Keyboard tools").performClick()
            key("Control off").performClick(); key("Alt off").performClick()
            key("Shift off").performClick(); key("X").performClick()
            assertEquals(Triple("X", true, true), modified.last())
            assertFalse(key("Control off").isSelected)
            assertFalse(key("Alt off").isSelected)
            assertFalse(key("Shift off").isSelected)
            key("Control off").performClick(); key("Alt off").performClick(); key("Shift off").performClick()
            key("Escape").performClick(); key("Tab").performClick()
            assertEquals(listOf(KeyEvent.KEYCODE_ESCAPE, true, true, true), special[0])
            assertEquals(listOf(KeyEvent.KEYCODE_TAB, false, false, false), special[1])
            accepted = false
            key("Control off").performClick(); key("Alt off").performClick(); key("x").performClick()
            assertFalse("Rejected dispatch must not latch Control", key("Control off").isSelected)
            assertFalse("Rejected dispatch must not latch Alt", key("Alt off").isSelected)
            key("Control off").performClick(); key("Alt off").performClick(); key("Shift off").performClick()
            key("Function keys").performClick()
            assertTrue(buttons(panel.view).any { it.contentDescription == "F1" })
            panel.reset(false, true, "Next")
            assertFalse(key("Dictate").isEnabled)
            assertFalse(key("Control off").isSelected)
            assertFalse(key("Alt off").isSelected)
            assertFalse(buttons(panel.view).any { it.contentDescription == "F1" })
            key("Switch letters and symbols").performClick()
            assertFalse(key("Shift off").isSelected)
            key("a").performClick()
            assertEquals("a", plain.last())
        }
    }

    @Test fun panelNumberRowIsIndependentAndFunctionKeysDispatchCorrectCodes() {
        instrumentation.runOnMainSync {
            val codes = mutableListOf<Int>()
            fun panel(options: KeyboardOptions) = TypingPanel(instrumentation.targetContext, options,
                { true }, {}, {}, {}, {}, {}, {}, { code, _, _, _ -> codes.add(code); true })
                .apply { reset(true, false, "Enter") }
            fun buttons(view: View): List<android.widget.Button> = when (view) {
                is android.widget.Button -> listOf(view)
                is android.view.ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
                else -> emptyList()
            }
            val ordinary = panel(KeyboardOptions())
            assertFalse(buttons(ordinary.view).any { it.contentDescription in listOf("1", "Control off", "Function keys") })
            val numbers = panel(KeyboardOptions(numberRow=true))
            assertTrue(buttons(numbers.view).any { it.contentDescription == "1" })
            assertFalse(buttons(numbers.view).any { it.contentDescription == "Control off" })
            val terminal = panel(KeyboardOptions(terminal=true))
            fun key(label: String) = buttons(terminal.view).single { it.contentDescription == label }
            assertTrue(buttons(terminal.view).any { it.contentDescription == "1" })
            key("Function keys").performClick()
            assertFalse(buttons(terminal.view).any { it.contentDescription == "1" })
            key("F1").performClick(); key("F12").performClick()
            key("Forward delete").performClick(); key("Insert").performClick()
            key("Page up").performClick(); key("Left arrow").performClick()
            assertEquals(listOf(KeyEvent.KEYCODE_F1, KeyEvent.KEYCODE_F12, KeyEvent.KEYCODE_FORWARD_DEL,
                KeyEvent.KEYCODE_INSERT, KeyEvent.KEYCODE_PAGE_UP, KeyEvent.KEYCODE_DPAD_LEFT), codes)
            assertTrue(buttons(terminal.view).all { !it.contentDescription.isNullOrBlank() && it.isFocusable })
            key("Function keys").performClick()
            assertTrue(buttons(terminal.view).any { it.contentDescription == "1" })
            assertFalse(buttons(terminal.view).any { it.contentDescription == "F1" })
        }
    }

    @Test fun functionLayerDoesNotGrowKeyboardAndKeepsControlsInBounds() {
        instrumentation.runOnMainSync {
            val context = instrumentation.targetContext
            for (widthDp in listOf(320, 412)) for (large in listOf(false, true)) {
                val panel = TypingPanel(context, KeyboardOptions(terminal=true, large=large),
                    { true }, {}, {}, {}, {}, {}, {}, { _, _, _, _ -> true })
                fun buttons(view: View): List<android.widget.Button> = when (view) {
                    is android.widget.Button -> listOf(view)
                    is android.view.ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
                    else -> emptyList()
                }
                fun key(label: String) = buttons(panel.view).single { it.contentDescription == label }
                fun layout(): Int {
                    val width = Ui.dp(context, widthDp)
                    panel.view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                        View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
                    panel.view.layout(0, 0, width, panel.view.measuredHeight)
                    for (button in buttons(panel.view)) {
                        val rect = android.graphics.Rect(0, 0, button.width, button.height)
                        panel.view.offsetDescendantRectToMyCoords(button, rect)
                        assertTrue("Terminal control outside ${widthDp}dp large=$large: ${button.contentDescription}",
                            rect.left >= 0 && rect.right <= width && rect.top >= 0 && rect.bottom <= panel.view.height &&
                                rect.width() > 0 && rect.height() > 0)
                    }
                    return panel.view.height
                }
                panel.reset(true, false, "Enter")
                val typingHeight = layout()
                key("Function keys").performClick()
                assertTrue("Fn must replace rows, not append height", layout() <= typingHeight)
                assertFalse(buttons(panel.view).any { it.contentDescription == "q" })
                for (label in listOf("F1", "F12", "Shift off", "Insert", "Forward delete", "Return to letters", "Delete")) {
                    assertTrue("Function control must remain focusable: $label", key(label).isFocusable)
                }
                key("Return to letters").performClick()
                assertEquals(typingHeight, layout())
                assertTrue(buttons(panel.view).any { it.contentDescription == "q" })
                assertFalse(buttons(panel.view).any { it.contentDescription == "F1" })
            }
        }
    }
}
