package org.utterleaf.voice

import android.content.Intent
import android.text.InputType
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.BaseInputConnection
import android.view.inputmethod.EditorInfo
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

    @Test fun primaryEditorActionRefusesOnceWithoutTextOrKeyFallback() {
        instrumentation.runOnMainSync {
            var accepted = true
            var throwing = false
            val calls = mutableListOf<Int>()
            val connection = object : BaseInputConnection(View(instrumentation.targetContext), true) {
                override fun performEditorAction(actionCode: Int): Boolean {
                    calls += actionCode
                    if (throwing) throw IllegalStateException("Synthetic closed connection")
                    return accepted
                }
                override fun commitText(text: CharSequence?, newCursorPosition: Int): Boolean {
                    fail("Rejected editor action fell back to text")
                    return false
                }
                override fun sendKeyEvent(event: android.view.KeyEvent): Boolean {
                    fail("Rejected editor action fell back to a key event")
                    return false
                }
            }

            assertTrue(EditorActions.performImeAction(connection, EditorInfo.IME_ACTION_SEND))
            accepted = false
            assertFalse(EditorActions.performImeAction(connection, EditorInfo.IME_ACTION_SEND))
            throwing = true
            assertFalse(EditorActions.performImeAction(connection, EditorInfo.IME_ACTION_SEND))
            assertFalse(EditorActions.performImeAction(null, EditorInfo.IME_ACTION_SEND))
            assertEquals(listOf(EditorInfo.IME_ACTION_SEND, EditorInfo.IME_ACTION_SEND,
                EditorInfo.IME_ACTION_SEND), calls)
        }
    }

    @Test fun dispatchIsBoundedAndDoesNotFallBackToTerminalKeys() {
        instrumentation.runOnMainSync {
            val calls = mutableListOf<Int>()
            val connection = object : BaseInputConnection(View(instrumentation.targetContext), true) {
                override fun performContextMenuAction(id: Int): Boolean { calls += id; return true }
                override fun sendKeyEvent(event: android.view.KeyEvent): Boolean { fail("Unexpected key fallback"); return false }
                override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence? =
                    throw AssertionError("Editor action read preceding text")
                override fun getTextAfterCursor(length: Int, flags: Int): CharSequence? =
                    throw AssertionError("Editor action read following text")
                override fun getSelectedText(flags: Int): CharSequence? =
                    throw AssertionError("Editor action read selected text")
                override fun getExtractedText(request: android.view.inputmethod.ExtractedTextRequest?, flags: Int):
                    android.view.inputmethod.ExtractedText? = throw AssertionError("Editor action extracted field text")
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
            passwords.forEach { inputType ->
                calls.clear()
                assertTrue(EditorActions.perform(connection, EditorAction.PASTE, inputType))
                assertEquals("Each explicit password Paste must dispatch exactly once", listOf(android.R.id.paste), calls)
            }
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
                views().single { (it.contentDescription as? String)?.startsWith("Layout & size") == true }.performClick()
                val editor = views().filterIsInstance<EditText>()
                    .single { it.hint == "Practice typing here" }
                editor.setText("cat"); editor.setSelection(3)
                key("s").performClick()
                assertEquals("cats", editor.text.toString())
                key("Editing tools").performClick()
                key("Undo").performClick(); assertEquals("cat", editor.text.toString())
                key("Redo").performClick(); assertEquals("cats", editor.text.toString())
                key("Select neighboring word").performLongClick()
                assertEquals(0, editor.selectionStart); assertEquals(4, editor.selectionEnd)
                key("Copy").performClick(); key("Select neighboring word").performLongClick(); key("Cut").performClick()
                assertEquals("", editor.text.toString())
                key("Paste").performClick(); assertEquals("cats", editor.text.toString())
                val stale = key("Cut")
                key("Extra keys").performClick()
                editor.selectAll(); stale.performClick()
                assertEquals("cats", editor.text.toString())
                key("Close extra keys").performClick()
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
            val attempts = mutableListOf<EditorAction>()
            val panel = TypingPanel(context, KeyboardOptions(), { true }, {}, {}, {}, {}, {}, {},
                editorAction = { attempts.add(it); false })
            fun key(description: String) = descendants(panel.view).filterIsInstance<Button>().single { it.contentDescription == description }
            fun height(): Int {
                panel.view.measure(View.MeasureSpec.makeMeasureSpec(Ui.dp(context, 320), View.MeasureSpec.EXACTLY),
                    View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
                return panel.view.measuredHeight
            }
            panel.reset(false, false, "Enter"); val typingHeight = height()
            key("Editing tools").performClick(); val editHeight = height()
            assertTrue("Edit tools should replace letters without growing the keyboard", editHeight <= typingHeight)
            key("Undo").performClick()
            assertEquals("A refused action must not change the layout", editHeight, height())
            assertFalse("Refused actions must not add a status row",
                descendants(panel.view).filterIsInstance<android.widget.TextView>()
                    .any { it.text == "Key unavailable" && it.visibility == View.VISIBLE })
            assertEquals(1, attempts.size)
            val stale = key("Paste")
            panel.reset(false, true, "Next"); stale.performClick()
            assertEquals("A stale edit button must not act after reset", 1, attempts.size)
        }
    }
}
