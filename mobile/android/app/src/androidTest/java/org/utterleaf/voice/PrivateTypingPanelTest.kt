package org.utterleaf.voice

import android.os.SystemClock
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PrivateTypingPanelTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext

    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) }
        else emptyList()

    private fun buttons(panel: TypingPanel) = descendants(panel.view).filterIsInstance<Button>()

    private fun key(panel: TypingPanel, description: String) =
        buttons(panel).single { it.contentDescription == description }

    private fun descriptions(panel: TypingPanel) =
        buttons(panel).map { it.contentDescription?.toString().orEmpty() }.toSet()

    @Test fun privateModeKeepsOwnedTypingAndEditingButCannotOpenHostCapabilities() {
        instrumentation.runOnMainSync {
            val inserted = mutableListOf<String>()
            var eraseCalls = 0
            var enterCalls = 0
            val moves = mutableListOf<Boolean>()
            var dictateCalls = 0
            var settingsCalls = 0
            var switchCalls = 0
            var quickOptionCalls = 0
            var draftCalls = 0
            val specialKeys = mutableListOf<List<Any>>()
            val modified = mutableListOf<String>()
            val actions = mutableListOf<EditorAction>()
            val available = mutableSetOf(EditorAction.SELECT_ALL)
            val panel = TypingPanel(context,
                KeyboardOptions(terminal = true, numberRow = true,
                    alignment = KeyboardAlignment.RIGHT, letterLayout = LetterLayout.AZERTY),
                { inserted += it; true }, { eraseCalls++ }, { enterCalls++ }, { moves += it },
                { dictateCalls++ }, { settingsCalls++ }, { switchCalls++ },
                terminalKey = { code, ctrl, alt, shift ->
                    specialKeys += listOf(code, ctrl, alt, shift); true
                },
                modifiedCommit = { value, _, _ -> modified += value; true },
                quickOptionsChanged = { quickOptionCalls++ },
                editorAction = { actions += it; true },
                privateEditing = true, openDraft = { draftCalls++ },
                actionAvailable = { it in available })

            panel.reset(allowVoice = true, numeric = false, action = "Done")
            val initial = descriptions(panel)
            assertTrue("Inherited number-row preference was lost", "1" in initial)
            assertTrue("Inherited AZERTY layout was lost", "a" in initial && "z" in initial)
            assertFalse("Terminal mode escaped its private gate", "Escape" in initial || "Control off" in initial)
            assertForbiddenControlsAbsent(initial)

            key(panel, "a").performClick()
            key(panel, "Delete").performClick()
            key(panel, "Done").performClick()
            key(panel, "Keyboard tools").performClick()
            val tools = descriptions(panel)
            assertTrue(listOf("Caps lock off", "Move cursor left", "Move cursor right",
                "Accents and alternate characters", "Select text", "Delete to right",
                "Go to beginning", "Go to end").all { it in tools })
            assertForbiddenControlsAbsent(tools)
            key(panel, "Move cursor left").performClick()
            key(panel, "Move cursor right").performClick()
            key(panel, "Delete to right").performClick()
            key(panel, "Go to beginning").performClick()
            key(panel, "Go to end").performClick()
            key(panel, "Caps lock off").performClick()
            key(panel, "A").performClick()
            key(panel, "Caps lock on").performClick()
            val alternate = AlternateCharacters.choices('a', false, LetterLayout.AZERTY).first()
            key(panel, "Accents and alternate characters").performClick()
            key(panel, "a").performClick()
            key(panel, alternate).performClick()
            key(panel, "Select text").performClick()
            key(panel, "Move cursor left").performClick()

            key(panel, "Keyboard tools").performClick()
            key(panel, "Edit actions").performClick()
            assertFalse(descriptions(panel).any { it in setOf("Cut", "Copy", "Paste") })
            val undo = key(panel, "Undo")
            val redo = key(panel, "Redo")
            val selectAll = key(panel, "Select all")
            assertFalse(undo.isEnabled)
            assertFalse(redo.isEnabled)
            assertTrue(selectAll.isEnabled)
            touch(undo, MotionEvent.ACTION_DOWN)
            touch(undo, MotionEvent.ACTION_UP)
            assertTrue(actions.isEmpty())
            selectAll.performClick()
            available += EditorAction.UNDO
            available += EditorAction.REDO
            panel.refreshEditorActions()
            assertTrue(undo.isEnabled)
            assertTrue(redo.isEnabled)
            undo.performClick()
            redo.performClick()

            assertEquals(listOf("a", "A", alternate), inserted)
            assertEquals(1, eraseCalls)
            assertEquals(1, enterCalls)
            assertEquals(listOf(true, false), moves)
            assertEquals(listOf(
                listOf(KeyEvent.KEYCODE_FORWARD_DEL, false, false, false),
                listOf(KeyEvent.KEYCODE_MOVE_HOME, false, false, false),
                listOf(KeyEvent.KEYCODE_MOVE_END, false, false, false),
                listOf(KeyEvent.KEYCODE_DPAD_LEFT, false, false, true)), specialKeys)
            assertEquals(listOf(EditorAction.SELECT_ALL, EditorAction.UNDO, EditorAction.REDO), actions)
            assertTrue(modified.isEmpty())
            assertEquals(0, dictateCalls)
            assertEquals(0, settingsCalls)
            assertEquals(0, switchCalls)
            assertEquals(0, quickOptionCalls)
            assertEquals(0, draftCalls)

            panel.reset(allowVoice = true, numeric = false, action = "Send")
            val reset = descriptions(panel)
            assertTrue("1" in reset)
            assertFalse("Escape" in reset || "Control off" in reset || "Function keys" in reset)
            assertForbiddenControlsAbsent(reset)
            panel.dispose()
        }
    }

    @Test fun draftEntryExistsOnlyForAnOrdinaryPanelWithAnExplicitCallback() {
        instrumentation.runOnMainSync {
            fun panel(privateEditing: Boolean, draft: (() -> Unit)?): TypingPanel =
                TypingPanel(context, KeyboardOptions(), { true }, {}, {}, {}, {}, {}, {},
                    privateEditing = privateEditing, openDraft = draft).also {
                    it.reset(allowVoice = true, numeric = false, action = "Enter")
                }

            val withoutDraft = panel(privateEditing = false, draft = null)
            key(withoutDraft, "Keyboard tools").performClick()
            assertFalse("Private draft" in descriptions(withoutDraft))

            var opens = 0
            val ordinary = panel(privateEditing = false, draft = { opens++ })
            key(ordinary, "Keyboard tools").performClick()
            key(ordinary, "Private draft").performClick()
            assertEquals(1, opens)

            val private = panel(privateEditing = true, draft = { opens++ })
            key(private, "Keyboard tools").performClick()
            assertFalse("Private draft" in descriptions(private))
            assertEquals(1, opens)

            withoutDraft.dispose()
            ordinary.dispose()
            private.dispose()
        }
    }

    @Test fun disposeCancelsPendingHoldEmojiInsertionAndEveryStaleReentryPath() {
        val inserted = mutableListOf<String>()
        lateinit var holdPanel: TypingPanel
        lateinit var heldLetter: Button
        instrumentation.runOnMainSync {
            holdPanel = TypingPanel(context, KeyboardOptions(holdDelayMs = 250),
                { inserted += it; true }, {}, {}, {}, {}, {}, {}, privateEditing = true)
            holdPanel.reset(allowVoice = true, numeric = false, action = "Enter")
            holdPanel.view.measure(
                View.MeasureSpec.makeMeasureSpec(Ui.dp(context, 320), View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
            holdPanel.view.layout(0, 0, holdPanel.view.measuredWidth, holdPanel.view.measuredHeight)
            heldLetter = key(holdPanel, "e")
            touch(heldLetter, MotionEvent.ACTION_DOWN)
            holdPanel.dispose()
        }
        Thread.sleep(350)
        instrumentation.waitForIdleSync()
        instrumentation.runOnMainSync {
            touch(heldLetter, MotionEvent.ACTION_UP)
            heldLetter.performClick()
            holdPanel.reset(allowVoice = true, numeric = false, action = "Send")
            assertTrue(buttons(holdPanel).isEmpty())
            assertFalse(descendants(holdPanel.view).any { it is AlternateStrip })
        }

        lateinit var emojiPanel: TypingPanel
        var staleEmojiEntry: Button? = null
        lateinit var staleReturn: Button
        instrumentation.runOnMainSync {
            emojiPanel = TypingPanel(context, KeyboardOptions(), { inserted += it; true },
                {}, {}, {}, {}, {}, {}, privateEditing = true)
            emojiPanel.reset(allowVoice = true, numeric = false, action = "Enter")
            key(emojiPanel, "Emoji").performClick()
            staleReturn = key(emojiPanel, "Return from emoji to letters")
        }
        val deadline = SystemClock.uptimeMillis() + 5_000
        do {
            instrumentation.waitForIdleSync()
            val found = arrayOfNulls<Button>(1)
            instrumentation.runOnMainSync {
                found[0] = buttons(emojiPanel).firstOrNull { button ->
                    button.isEnabled && button.text.toString().codePoints().anyMatch { it > 0xffff }
                }
            }
            if (found[0] != null) {
                staleEmojiEntry = found[0]
                break
            }
            Thread.sleep(25)
        } while (SystemClock.uptimeMillis() < deadline)
        assertNotNull("Local emoji catalog did not expose an entry", staleEmojiEntry)
        instrumentation.runOnMainSync {
            emojiPanel.dispose()
            staleEmojiEntry!!.performClick()
            staleReturn.performClick()
            emojiPanel.reset(allowVoice = true, numeric = false, action = "Send")
            assertTrue(buttons(emojiPanel).isEmpty())
        }
        assertTrue(inserted.isEmpty())
    }

    private fun assertForbiddenControlsAbsent(labels: Set<String>) {
        val forbidden = setOf("Dictate", "Keyboard settings", "Switch keyboard", "Private draft",
            "Number row on", "Number row off", "Terminal controls on", "Terminal controls off",
            "Full width layout", "Left hand layout", "Right hand layout",
            "QWERTY letter layout", "QWERTZ letter layout", "AZERTY letter layout",
            "Escape", "Tab", "Control off", "Alt off", "Function keys", "Cut", "Copy", "Paste")
        assertTrue("Private panel exposed ${labels.intersect(forbidden)}", labels.intersect(forbidden).isEmpty())
    }

    private fun touch(button: Button, action: Int) {
        val now = SystemClock.uptimeMillis()
        val event = MotionEvent.obtain(now, now, action,
            button.width.coerceAtLeast(1) / 2f, button.height.coerceAtLeast(1) / 2f, 0)
        try { button.dispatchTouchEvent(event) } finally { event.recycle() }
    }
}
