package org.utterleaf.voice

import android.content.Intent
import android.os.SystemClock
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.FrameLayout
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class TypingPanelLifecycleTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext

    private class Calls {
        val inserted = mutableListOf<String>()
        var erases = 0
        var enters = 0
        val moves = mutableListOf<Boolean>()
        var dictates = 0
        var settings = 0
        var switches = 0
        var drafts = 0
        var quickOptions = 0
        val actions = mutableListOf<EditorAction>()
        val terminal = mutableListOf<List<Any>>()
    }

    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) }
        else emptyList()

    private fun buttons(panel: TypingPanel) = descendants(panel.view).filterIsInstance<Button>()

    private fun key(panel: TypingPanel, description: String): Button = buttons(panel)
        .single { it.contentDescription == description }

    private fun descriptions(panel: TypingPanel) = buttons(panel)
        .mapNotNull { it.contentDescription?.toString() }.toSet()

    private fun createPanel(
        context: android.content.Context,
        calls: Calls,
        options: KeyboardOptions = KeyboardOptions(extraKeys = true),
        privateEditing: Boolean = false,
        stageOptions: ((KeyboardOptions) -> Unit)? = null,
    ) = TypingPanel(
        context,
        options,
        { value -> calls.inserted += value; true },
        { calls.erases++ },
        { calls.enters++ },
        { left -> calls.moves += left },
        { calls.dictates++ },
        { calls.settings++ },
        { calls.switches++ },
        terminalKey = { code, ctrl, alt, shift ->
            calls.terminal += listOf(code, ctrl, alt, shift)
            true
        },
        quickOptionsChanged = { calls.quickOptions++ },
        editorAction = { action -> calls.actions += action; true },
        privateEditing = privateEditing,
        openDraft = { calls.drafts++ },
        actionAvailable = { true },
        stageOptions = stageOptions,
    )

    private fun startHost(): Pair<KeyboardTestActivity, FrameLayout> {
        val activity = instrumentation.startActivitySync(
            Intent(app, KeyboardTestActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        ) as KeyboardTestActivity
        lateinit var host: FrameLayout
        instrumentation.runOnMainSync {
            host = FrameLayout(activity)
            activity.setContentView(host)
        }
        return activity to host
    }

    private fun attach(host: FrameLayout, panel: TypingPanel) {
        host.addView(panel.view, FrameLayout.LayoutParams(-1, -2))
    }

    private fun reattach(host: FrameLayout, panel: TypingPanel) {
        host.removeView(panel.view)
        attach(host, panel)
    }

    private fun assertDailyLetters(panel: TypingPanel, action: String) {
        val labels = descriptions(panel)
        assertTrue(listOf("Keyboard tools", "Editing tools", "Emoji", "a", "Shift off", "Space", action)
            .all { it in labels })
        assertTrue(listOf(
            "Close tools and settings", "Close editing tools", "Close extra keys", "F1",
            "Close alternate characters", "Cancel alternate characters", "Cancel compose",
            "Return from emoji to letters", "More numbers and symbols",
        ).none { it in labels })
    }

    private fun touch(button: Button, action: Int, downTime: Long) {
        val event = MotionEvent.obtain(
            downTime,
            SystemClock.uptimeMillis(),
            action,
            button.width / 2f,
            button.height / 2f,
            0,
        )
        try {
            button.dispatchTouchEvent(event)
        } finally {
            event.recycle()
        }
    }

    @Test fun samePanelDetachReturnsEveryTransientLayerToDailyTypingAndInvalidatesStaleKeys() {
        val (activity, host) = startHost()
        val calls = Calls()
        lateinit var panel: TypingPanel
        var panelReady = false
        try {
            instrumentation.runOnMainSync {
                panel = createPanel(activity, calls)
                panelReady = true
                panel.reset(allowVoice = true, numeric = false, action = "Done")
                attach(host, panel)
                assertDailyLetters(panel, "Done")

                key(panel, "Keyboard tools").performClick()
                assertTrue("Close tools and settings" in descriptions(panel))
                reattach(host, panel)
                assertDailyLetters(panel, "Done")

                key(panel, "Editing tools").performClick()
                assertTrue("Close editing tools" in descriptions(panel))
                reattach(host, panel)
                assertDailyLetters(panel, "Done")

                key(panel, "Extra keys").performClick()
                key(panel, "Control off").performClick()
                key(panel, "Alt off").performClick()
                buttons(panel).single { it.contentDescription == "Shift off" && it.text.toString() == "Shift" }
                    .performClick()
                key(panel, "Function keys").performClick()
                assertTrue("F1" in descriptions(panel))
                reattach(host, panel)
                assertDailyLetters(panel, "Done")
                key(panel, "Extra keys").performClick()
                assertFalse(key(panel, "Control off").isSelected)
                assertFalse(key(panel, "Alt off").isSelected)
                assertTrue(buttons(panel).filter { it.contentDescription == "Shift off" }.all { !it.isSelected })
                assertTrue(key(panel, "Accessory keys").isSelected)
                assertFalse("F1" in descriptions(panel))
                reattach(host, panel)

                key(panel, "Keyboard tools").performClick()
                key(panel, "Accents and alternate characters").performClick()
                key(panel, "a").performClick()
                assertTrue("Cancel alternate characters" in descriptions(panel))
                reattach(host, panel)
                assertDailyLetters(panel, "Done")

                key(panel, "Keyboard tools").performClick()
                key(panel, "Latin compose").performClick()
                key(panel, "Acute compose mark").performClick()
                assertTrue("Cancel compose" in descriptions(panel))
                reattach(host, panel)
                assertDailyLetters(panel, "Done")

                key(panel, "Emoji").performClick()
                assertTrue("Return from emoji to letters" in descriptions(panel))
                reattach(host, panel)
                assertDailyLetters(panel, "Done")

                key(panel, "Switch letters and symbols").performClick()
                key(panel, "More symbols").performClick()
                assertTrue("More numbers and symbols" in descriptions(panel))
                reattach(host, panel)
                assertDailyLetters(panel, "Done")

                val staleLetter = key(panel, "a")
                val staleShift = key(panel, "Shift off")
                assertTrue(staleShift.performLongClick())
                assertTrue("A" in descriptions(panel))
                reattach(host, panel)
                staleLetter.performClick()
                assertFalse("A stale Shift must not re-arm Caps Lock", staleShift.performLongClick())
                assertTrue(calls.inserted.isEmpty())
                assertDailyLetters(panel, "Done")
                key(panel, "a").performClick()
                key(panel, "Done").performClick()
                assertEquals(listOf("a"), calls.inserted)
                assertEquals(1, calls.enters)
                assertTrue(calls.terminal.isEmpty())
            }
        } finally {
            instrumentation.runOnMainSync {
                if (panelReady) {
                    if (panel.view.parent === host) host.removeView(panel.view)
                    panel.dispose()
                }
                activity.finish()
            }
        }
    }

    @Test fun numericPanelReturnsToItsFirstSymbolPageAfterDetach() {
        val (activity, host) = startHost()
        val calls = Calls()
        lateinit var panel: TypingPanel
        var panelReady = false
        try {
            instrumentation.runOnMainSync {
                panel = createPanel(activity, calls)
                panelReady = true
                panel.reset(allowVoice = false, numeric = true, action = "Next")
                attach(host, panel)
                assertTrue("More symbols" in descriptions(panel))
                assertFalse("a" in descriptions(panel))
                key(panel, "More symbols").performClick()
                val staleSymbol = key(panel, "~")
                assertTrue("More numbers and symbols" in descriptions(panel))

                reattach(host, panel)
                staleSymbol.performClick()
                assertTrue(calls.inserted.isEmpty())
                assertTrue("Numeric baseline did not restore its first page", "More symbols" in descriptions(panel))
                assertFalse("More numbers and symbols" in descriptions(panel))
                assertFalse("a" in descriptions(panel))
                key(panel, "1").performClick()
                key(panel, "Next").performClick()
                assertEquals(listOf("1"), calls.inserted)
                assertEquals(1, calls.enters)
            }
        } finally {
            instrumentation.runOnMainSync {
                if (panelReady) {
                    if (panel.view.parent === host) host.removeView(panel.view)
                    panel.dispose()
                }
                activity.finish()
            }
        }
    }

    @Test fun detachPreservesStagedOptionsAndPrivateEditorOwnershipWithoutCallingHosts() {
        val (activity, host) = startHost()
        var stagedPanel: TypingPanel? = null
        var privatePanel: TypingPanel? = null
        try {
            instrumentation.runOnMainSync {
                val stagedCalls = Calls()
                val staged = mutableListOf<KeyboardOptions>()
                stagedPanel = createPanel(
                    activity,
                    stagedCalls,
                    KeyboardOptions(numberRow = true, extraKeys = true, letterLayout = LetterLayout.AZERTY),
                    stageOptions = { staged += it },
                ).also { panel ->
                    panel.reset(allowVoice = false, numeric = false, action = "Send")
                    attach(host, panel)
                }
                val preview = requireNotNull(stagedPanel)
                key(preview, "Keyboard tools").performClick()
                key(preview, "Number row on").performClick()
                assertEquals(1, staged.size)
                assertFalse(staged.single().numberRow)
                assertEquals(1, stagedCalls.quickOptions)
                key(preview, "Close tools and settings").performClick()
                reattach(host, preview)
                assertDailyLetters(preview, "Send")
                assertFalse("A staged disabled number row was lost on detach", "1" in descriptions(preview))
                key(preview, "Keyboard tools").performClick()
                assertTrue(key(preview, "AZERTY letter layout").isSelected)
                key(preview, "Close tools and settings").performClick()
                key(preview, "a").performClick()
                key(preview, "Send").performClick()
                assertEquals(listOf("a"), stagedCalls.inserted)
                assertEquals(1, stagedCalls.enters)
                assertEquals(1, stagedCalls.quickOptions)
                assertEquals(1, staged.size)
                assertEquals(0, stagedCalls.settings)
                assertEquals(0, stagedCalls.switches)
                assertEquals(0, stagedCalls.drafts)

                host.removeView(preview.view)
                preview.dispose()

                val privateCalls = Calls()
                privatePanel = createPanel(activity, privateCalls, privateEditing = true).also { panel ->
                    panel.reset(allowVoice = true, numeric = false, action = "Done")
                    attach(host, panel)
                }
                val owned = requireNotNull(privatePanel)
                key(owned, "a").performClick()
                key(owned, "Keyboard tools").performClick()
                assertTrue("Latin compose" in descriptions(owned))
                reattach(host, owned)
                assertDailyLetters(owned, "Done")
                assertEquals(listOf("a"), privateCalls.inserted)
                key(owned, "a").performClick()
                key(owned, "Done").performClick()
                assertEquals(listOf("a", "a"), privateCalls.inserted)
                assertEquals(1, privateCalls.enters)
                assertEquals(0, privateCalls.dictates)
                assertEquals(0, privateCalls.settings)
                assertEquals(0, privateCalls.switches)
                assertEquals(0, privateCalls.drafts)
                assertEquals(0, privateCalls.quickOptions)
            }
        } finally {
            instrumentation.runOnMainSync {
                listOfNotNull(stagedPanel, privatePanel).forEach { panel ->
                    if (panel.view.parent === host) host.removeView(panel.view)
                    panel.dispose()
                }
                activity.finish()
            }
        }
    }

    @Test fun detachCancelsAPendingDeleteRepeatBeforeReattachingTheSamePanel() {
        val (activity, host) = startHost()
        val calls = Calls()
        lateinit var panel: TypingPanel
        lateinit var staleDelete: Button
        var panelReady = false
        val downTime = SystemClock.uptimeMillis()
        try {
            instrumentation.runOnMainSync {
                panel = createPanel(
                    activity,
                    calls,
                    KeyboardOptions(extraKeys = true, deleteRepeat = true, repeatGuard = false),
                )
                panelReady = true
                panel.reset(allowVoice = false, numeric = false, action = "Enter")
                attach(host, panel)
            }
            UiAwait.until("Attached Delete key did not lay out") {
                panel.view.isAttachedToWindow && key(panel, "Delete").width > 0
            }
            instrumentation.runOnMainSync {
                staleDelete = key(panel, "Delete")
                touch(staleDelete, MotionEvent.ACTION_DOWN, downTime)
                reattach(host, panel)
            }
            UiAwait.remains("Detached Delete hold reached the host callback") { calls.erases == 0 }
            instrumentation.runOnMainSync {
                touch(staleDelete, MotionEvent.ACTION_UP, downTime)
                assertEquals(0, calls.erases)
                key(panel, "Delete").performClick()
                assertEquals(1, calls.erases)
            }
        } finally {
            instrumentation.runOnMainSync {
                if (panelReady) {
                    if (panel.view.parent === host) host.removeView(panel.view)
                    panel.dispose()
                }
                activity.finish()
            }
        }
    }
}
