package org.utterleaf.voice

import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.text.Selection
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class KeyboardEditorContractTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext
    private fun shell(command: String) = android.os.ParcelFileDescriptor.AutoCloseInputStream(
        instrumentation.uiAutomation.executeShellCommand(command)).bufferedReader().use { it.readText() }
    private fun <T> main(block: () -> T): T {
        val result = java.util.concurrent.atomic.AtomicReference<T>()
        instrumentation.runOnMainSync { result.set(block()) }
        return result.get()
    }
    private fun await(message: String, condition: () -> Boolean) {
        val deadline = android.os.SystemClock.elapsedRealtime() + 10_000
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            if (condition()) return
            Thread.sleep(50)
        }
        throw AssertionError(message)
    }
    private fun key(label: String): AccessibilityNodeInfo? {
        fun find(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
            if (node.contentDescription?.toString() == label && node.isClickable) return node
            for (index in 0 until node.childCount) node.getChild(index)?.let(::find)?.let { return it }
            return null
        }
        return instrumentation.uiAutomation.windows.asSequence()
            .filter { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD }.mapNotNull { it.root?.let(::find) }.firstOrNull()
    }
    private fun press(label: String) {
        await("Missing $label") { key(label)?.isEnabled == true }
        val deadline = android.os.SystemClock.elapsedRealtime() + 2_000
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            if (key(label)?.performAction(AccessibilityNodeInfo.ACTION_CLICK) == true) {
                instrumentation.waitForIdleSync()
                return
            }
            Thread.sleep(50)
        }
        throw AssertionError("Could not press $label")
    }

    /**
     * Opens the extra-keys panel and waits until its keys are actually present.
     * A setText-driven IME rebuild lands asynchronously; a toggle pressed on
     * the pre-rebuild panel is silently lost, so retry the chevron if the
     * accessory keys never surface.
     */
    private fun openExtraKeys() {
        var attempts = 0
        val deadline = android.os.SystemClock.elapsedRealtime() + 15_000
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            press("Extra keys")
            attempts++
            val openDeadline = android.os.SystemClock.elapsedRealtime() + 3_000
            while (android.os.SystemClock.elapsedRealtime() < openDeadline) {
                if (key("Forward delete") != null) return
                Thread.sleep(50)
            }
            if (attempts >= 5) break
        }
        throw AssertionError("Extra keys panel did not open after $attempts attempts")
    }
    private fun longPress(label: String) {
        await("Missing $label") { key(label)?.isEnabled == true }
        val deadline = android.os.SystemClock.elapsedRealtime() + 2_000
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            if (key(label)?.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK) == true) {
                instrumentation.waitForIdleSync()
                return
            }
            Thread.sleep(50)
        }
        throw AssertionError("Could not long press $label")
    }
    private fun launch(options: Int, raw: Boolean = false, multiline: Boolean = false): KeyboardEditorContractActivity {
        val activity = instrumentation.startActivitySync(Intent(app, KeyboardEditorContractActivity::class.java)
            .putExtra("ime_options", options).putExtra("raw", raw).putExtra("multiline", multiline)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as KeyboardEditorContractActivity
        await("Editor activity never acquired window focus") { main { activity.hasWindowFocus() } }
        main { activity.editor.requestFocus() }
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        await("Editor never became active") { main { manager.isActive(activity.editor) } }
        main { manager.showSoftInput(activity.editor, InputMethodManager.SHOW_IMPLICIT) }
        await("Typing keyboard did not appear") { key(if (raw) "l" else "a") != null }
        return activity
    }
    private fun close(activity: KeyboardEditorContractActivity) {
        main { activity.finish() }
        await("Previous typing session did not close") { key("a") == null }
    }
    private fun withKeyboard(block: () -> Unit) {
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        val id = manager.inputMethodList.single { it.serviceName == KeyboardIme::class.java.name }.id
        val previous = Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
        val enabled = manager.enabledInputMethodList.any { it.id == id }
        val options = KeyboardOptions.load(app)
        val automation = instrumentation.uiAutomation
        val flags = automation.serviceInfo.flags
        try {
            automation.serviceInfo = automation.serviceInfo.apply {
                this.flags = flags or android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            }
            shell("ime enable $id"); shell("ime set $id")
            options.copy(extraKeys = true).save(app)
            await("Typing IME was not selected") { Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD) == id }
            block()
        }
        finally {
            if (!previous.isNullOrBlank()) shell("ime set $previous"); if (!enabled) shell("ime disable $id")
            options.save(app)
            automation.serviceInfo = automation.serviceInfo.apply { this.flags = flags }
        }
    }

    @Test fun freshSessionsReplaceSelectionDeleteUnicodeAndDispatchEnter() = withKeyboard {
        val text = launch(EditorInfo.IME_ACTION_DONE)
        try {
            main { text.editor.setText("A😀é👩‍👩‍👧‍👦Z"); Selection.setSelection(text.editor.text, text.editor.length() - 1, 1) }
            press("x"); await("Reversed selection was not replaced") { main { text.editor.text.toString() == "AxZ" } }
            for ((value, cursor, expected) in listOf(Triple("á", 2, "a"), Triple("😀x", 2, "x"),
                Triple("👩‍👩‍👧‍👦x", "👩‍👩‍👧‍👦".length, "x"))) {
                main { text.editor.setText(value); text.editor.setSelection(cursor) }
                press("Delete"); await("Unicode delete failed") { main { text.editor.text.toString() == expected } }
            }
            main { text.editor.setText("😀x"); text.editor.setSelection(0) }
            openExtraKeys(); press("Forward delete")
            await("Forward delete did not remove supplementary Unicode") { main { text.editor.text.toString() == "x" } }
            press("Extra keys")
        } finally { close(text) }
        for ((options, label, expectedAction) in listOf(
            Triple(EditorInfo.IME_ACTION_GO, "Go", EditorInfo.IME_ACTION_GO), Triple(EditorInfo.IME_ACTION_SEARCH, "Search", EditorInfo.IME_ACTION_SEARCH),
            Triple(EditorInfo.IME_ACTION_SEND, "Send", EditorInfo.IME_ACTION_SEND), Triple(EditorInfo.IME_ACTION_NEXT, "Next", EditorInfo.IME_ACTION_NEXT),
            Triple(EditorInfo.IME_ACTION_PREVIOUS, "Previous", EditorInfo.IME_ACTION_PREVIOUS), Triple(EditorInfo.IME_ACTION_DONE, "Done", EditorInfo.IME_ACTION_DONE))) {
            val activity = launch(options)
            try {
                press(label); await("$label was not dispatched") { main { activity.action == expectedAction } }
            }
            finally { close(activity) }
        }
        for (options in listOf(EditorInfo.IME_ACTION_NONE, EditorInfo.IME_ACTION_UNSPECIFIED,
            EditorInfo.IME_ACTION_DONE or EditorInfo.IME_FLAG_NO_ENTER_ACTION)) {
            val activity = launch(options, multiline = true)
            try { press("Enter"); await("Enter did not commit newline") { main { activity.editor.text.toString() == "\n" } } }
            finally { close(activity) }
        }
        val raw = launch(EditorInfo.IME_ACTION_NONE, raw = true)
        try { press("Enter"); await("TYPE_NULL did not receive raw Enter") { main { raw.rawKey == android.view.KeyEvent.KEYCODE_ENTER } } }
        finally { close(raw) }
    }

    @Test fun selectTapSelectsTheNeighboringWordThroughTheEditor() = withKeyboard {
        val activity = launch(EditorInfo.IME_ACTION_DONE)
        try {
            main { activity.editor.setText("alpha beta"); activity.editor.setSelection(activity.editor.length()) }
            press("Keyboard tools")
            longPress("Select all text")
            await("Neighboring word was not selected") {
                main {
                    val start = minOf(activity.editor.selectionStart, activity.editor.selectionEnd)
                    val end = maxOf(activity.editor.selectionStart, activity.editor.selectionEnd)
                    activity.editor.text.toString() == "alpha beta" && start == 6 && end == 10
                }
            }
            press("Select all text")
            await("Select all did not apply") {
                main { activity.editor.selectionStart == 0 && activity.editor.selectionEnd == 10 }
            }
        } finally { close(activity) }
    }

    @Test fun latchedCtrlShiftArrowsKeepSelectingWords() = withKeyboard {
        val activity = launch(EditorInfo.IME_ACTION_DONE)
        try {
            main { activity.editor.setText("one two three"); activity.editor.setSelection(activity.editor.length()) }
            openExtraKeys()
            press("Control off")
            press("Shift off")
            press("Left arrow")
            await("First Ctrl+Shift+Left did not select the neighboring word") {
                main {
                    val start = minOf(activity.editor.selectionStart, activity.editor.selectionEnd)
                    val end = maxOf(activity.editor.selectionStart, activity.editor.selectionEnd)
                    activity.editor.text.toString() == "one two three" && start == 8 && end == 13
                }
            }
            press("Left arrow")
            await("Latched Ctrl+Shift did not keep extending the selection") {
                main {
                    val start = minOf(activity.editor.selectionStart, activity.editor.selectionEnd)
                    val end = maxOf(activity.editor.selectionStart, activity.editor.selectionEnd)
                    activity.editor.text.toString() == "one two three" && end == 13 && start < 8
                }
            }
        } finally { close(activity) }
    }
}
