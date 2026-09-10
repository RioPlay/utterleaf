package org.utterleaf.voice

import android.content.Intent
import android.text.InputType
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.BaseInputConnection
import android.widget.Button
import android.widget.EditText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class EditorActionsTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()

    @Test fun dispatchIsBoundedAndDoesNotFallBackToTerminalKeys() {
        instrumentation.runOnMainSync {
            val calls = mutableListOf<Int>()
            val connection = object : BaseInputConnection(View(instrumentation.targetContext), true) {
                override fun performContextMenuAction(id: Int): Boolean { calls += id; return true }
                override fun sendKeyEvent(event: android.view.KeyEvent): Boolean { fail("Unexpected key fallback"); return false }
            }
            EditorAction.values().forEach { assertTrue(EditorActions.perform(connection, it, InputType.TYPE_CLASS_TEXT)) }
            assertEquals(EditorAction.values().map { it.menuId }, calls)
            calls.clear()
            val passwords = listOf(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD,
                InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD,
                InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD,
                InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD)
            passwords.forEach {
                assertFalse(EditorActions.perform(connection, EditorAction.COPY, it))
                assertFalse(EditorActions.perform(connection, EditorAction.CUT, it))
            }
            assertFalse(EditorActions.perform(connection, EditorAction.PASTE, InputType.TYPE_NULL))
            assertFalse(EditorActions.perform(null, EditorAction.PASTE, InputType.TYPE_CLASS_TEXT))
            assertTrue(calls.isEmpty())
            assertTrue(EditorActions.perform(connection, EditorAction.PASTE, passwords.first()))
            val rejected = object : BaseInputConnection(View(instrumentation.targetContext), true) {
                override fun performContextMenuAction(id: Int): Boolean = throw IllegalStateException("closed")
            }
            assertFalse(EditorActions.perform(rejected, EditorAction.UNDO, InputType.TYPE_CLASS_TEXT))
        }
    }

    @Test fun practiceActionsEditRealTextAndOldButtonsCannotActAfterReset() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        KeyboardOptions().save(context)
        val activity = instrumentation.startActivitySync(Intent(context, KeyboardSettingsActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        try {
            instrumentation.runOnMainSync {
                fun views() = descendants(activity.window.decorView)
                fun key(description: String) = views().filterIsInstance<Button>().single { it.contentDescription == description }
                val editor = views().filterIsInstance<EditText>().single()
                editor.setText("cat"); editor.setSelection(3)
                key("s").performClick()
                assertEquals("cats", editor.text.toString())
                key("Keyboard tools").performClick(); key("Edit actions").performClick()
                assertFalse(views().filterIsInstance<Button>().any { it.contentDescription == "a" })
                key("Undo").performClick(); assertEquals("cat", editor.text.toString())
                key("Redo").performClick(); assertEquals("cats", editor.text.toString())
                key("Select all").performClick()
                assertEquals(0, editor.selectionStart); assertEquals(4, editor.selectionEnd)
                key("Copy").performClick(); key("Select all").performClick(); key("Cut").performClick()
                assertEquals("", editor.text.toString())
                key("Paste").performClick(); assertEquals("cats", editor.text.toString())
                val stale = key("Cut")
                key("Return to typing").performClick()
                editor.selectAll(); stale.performClick()
                assertEquals("cats", editor.text.toString())
                key("Edit actions").performClick()
                check(context.applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE != 0)
                activity.window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
            }
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync {
                descendants(activity.window.decorView).filterIsInstance<android.widget.ScrollView>().first().fullScroll(View.FOCUS_DOWN)
            }
            instrumentation.waitForIdleSync()
            android.os.ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand(
                "screencap -p /data/local/tmp/utterleaf-keyboard-actions.png")).use { it.readBytes() }
        } finally {
            instrumentation.runOnMainSync {
                activity.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
                activity.finish()
                (context.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager)
                    .setPrimaryClip(android.content.ClipData.newPlainText("", ""))
            }
            original.save(context)
        }
    }

    @Test fun actionPanelIsCompactAndReportsRejection() {
        instrumentation.runOnMainSync {
            val context = instrumentation.targetContext
            val panel = TypingPanel(context, KeyboardOptions(), { true }, {}, {}, {}, {}, {}, {})
            fun key(description: String) = descendants(panel.view).filterIsInstance<Button>().single { it.contentDescription == description }
            fun height(): Int {
                panel.view.measure(View.MeasureSpec.makeMeasureSpec(Ui.dp(context, 320), View.MeasureSpec.EXACTLY),
                    View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
                return panel.view.measuredHeight
            }
            panel.reset(false, false, "Enter"); val typingHeight = height()
            key("Keyboard tools").performClick(); key("Edit actions").performClick()
            assertTrue(height() <= typingHeight)
            key("Undo").performClick()
            assertTrue(descendants(panel.view).filterIsInstance<android.widget.TextView>().any { it.text == "Key unavailable" && it.visibility == View.VISIBLE })
            val stale = key("Paste")
            panel.reset(false, true, "Next"); stale.performClick()
            assertFalse(descendants(panel.view).filterIsInstance<Button>().any { it.contentDescription == "Paste" })
        }
    }
}
