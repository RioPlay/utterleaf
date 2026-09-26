package org.utterleaf.voice

import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.text.Selection
import android.view.View
import android.view.ViewGroup
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Button
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
        var target: AccessibilityNodeInfo? = null
        await("Missing $label") { key(label)?.takeIf { it.isEnabled }?.also { target = it } != null }
        if (target?.performAction(AccessibilityNodeInfo.ACTION_CLICK) != true) {
            throw AssertionError("Enabled $label rejected its single click")
        }
        instrumentation.waitForIdleSync()
    }

    private fun openEditingTools() {
        if (key("Select neighboring word") != null) return
        press("Editing tools")
        await("Editing tools did not open after its single click") {
            key("Select neighboring word") != null
        }
    }

    /**
     * Opens the extra-keys panel and waits until its keys are actually present.
     * Editor readiness is established before this helper. Each panel toggle is
     * dispatched once; a missing resulting state remains a test failure.
     */
    private fun openExtraKeys() {
        if (key("Accessory keys") != null && key("Close extra keys") != null) return
        if (key("Extra keys") == null) {
            openEditingTools()
        }
        press("Extra keys")
        await("Extra keys panel did not open after its single click") {
            key("Accessory keys") != null && key("Close extra keys") != null
        }
    }
    private fun longPress(label: String) {
        var target: AccessibilityNodeInfo? = null
        await("Missing $label") { key(label)?.takeIf { it.isEnabled }?.also { target = it } != null }
        if (target?.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK) != true) {
            throw AssertionError("Enabled $label rejected its single long click")
        }
        instrumentation.waitForIdleSync()
    }

    private fun descendants(view: View): List<View> = listOf(view) + if (view is ViewGroup)
        (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()

    private fun nativeKey(label: String): Button? = main {
        android.view.inspector.WindowInspector.getGlobalWindowViews().flatMap(::descendants)
            .filterIsInstance<Button>()
            .singleOrNull { it.isShown && it.contentDescription?.toString() == label }
    }

    private fun imeSelection(button: Button): Pair<Int, Int>? = main {
        val service = button.context as? KeyboardIme ?: return@main null
        fun offset(name: String) = KeyboardIme::class.java.getDeclaredField(name).run {
            isAccessible = true
            getInt(service)
        }
        offset("selectionStart") to offset("selectionEnd")
    }

    private data class EditorObservation(
        val textMatches: Boolean,
        val textLength: Int,
        val selectionStart: Int,
        val selectionEnd: Int,
    )

    private data class DeleteCase(
        val name: String,
        val value: String,
        val cursor: Int,
        val expected: String,
    )

    /**
     * setText updates the host immediately but the input session and keyboard can
     * rebuild later. Observe both sides before dispatching a one-shot edit.
     */
    private fun awaitEditorReady(
        activity: KeyboardEditorContractActivity,
        caseName: String,
        expectedText: String,
        expectedStart: Int,
        expectedEnd: Int,
        keyLabel: String,
    ) {
        val deadline = android.os.SystemClock.elapsedRealtime() + 10_000
        var previousKey: Button? = null
        var lastObservation = "not sampled"
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            val host = main {
                val actual = activity.editor.text.toString()
                EditorObservation(
                    textMatches = actual == expectedText,
                    textLength = actual.length,
                    selectionStart = activity.editor.selectionStart,
                    selectionEnd = activity.editor.selectionEnd,
                )
            }
            val currentKey = runCatching { nativeKey(keyLabel) }.getOrNull()
            val keyStable = currentKey != null && currentKey === previousKey
            val keyEnabled = currentKey?.let { main { it.isEnabled } }
            val observedSelection = currentKey?.let { runCatching { imeSelection(it) }.getOrNull() }
            // The host preserves selection direction, while Android normalizes
            // the selection bounds delivered to InputMethodService callbacks.
            val expectedImeSelection = minOf(expectedStart, expectedEnd) to maxOf(expectedStart, expectedEnd)
            val observedImeSelection = observedSelection?.let {
                minOf(it.first, it.second) to maxOf(it.first, it.second)
            }
            lastObservation = "textMatches=${host.textMatches}, textLength=${host.textLength}, " +
                "hostSelection=${host.selectionStart}..${host.selectionEnd}, " +
                "keyPresent=${currentKey != null}, keyEnabled=$keyEnabled, " +
                "keyStable=$keyStable, imeSelection=$observedSelection"
            if (host.textMatches && host.selectionStart == expectedStart && host.selectionEnd == expectedEnd &&
                keyEnabled == true && keyStable &&
                observedImeSelection == expectedImeSelection
            ) return
            previousKey = currentKey
            Thread.sleep(50)
        }
        throw AssertionError(
            "$caseName editor state did not settle before $keyLabel: " +
                "expectedLength=${expectedText.length}, expectedSelection=$expectedStart..$expectedEnd; " +
                lastObservation,
        )
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
        var primaryFailure: Throwable? = null
        try {
            automation.serviceInfo = automation.serviceInfo.apply {
                this.flags = flags or android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            }
            shell("ime enable $id"); shell("ime set $id")
            options.copy(extraKeys = true).save(app)
            ImeTestReadiness.awaitDefaultImeStable(app, manager, id, "Typing IME setup")
            block()
        } catch (error: Throwable) {
            primaryFailure = error
            throw error
        }
        finally {
            ImeTestReadiness.cleanupPreserving(
                primaryFailure,
                {
                    if (!previous.isNullOrBlank()) {
                        shell("ime set $previous")
                        ImeTestReadiness.awaitDefaultImeStable(app, manager, previous, "Previous IME restore")
                    }
                },
                { if (!enabled) shell("ime disable $id") },
                { options.save(app) },
                { automation.serviceInfo = automation.serviceInfo.apply { this.flags = flags } },
            )
        }
    }

    @Test fun freshSessionsReplaceSelectionDeleteUnicodeAndDispatchEnter() = withKeyboard {
        val text = launch(EditorInfo.IME_ACTION_DONE)
        try {
            val original = "A😀é👩‍👩‍👧‍👦Z"
            val selectionStart = original.length - 1
            main { text.editor.setText(original); Selection.setSelection(text.editor.text, selectionStart, 1) }
            awaitEditorReady(text, "Reversed UTF-16 selection", original, selectionStart, 1, "x")
            press("x"); await("Reversed selection was not replaced") { main { text.editor.text.toString() == "AxZ" } }
            for ((caseName, value, cursor, expected) in listOf(
                DeleteCase("combining-mark cluster", "á", 2, "a"),
                DeleteCase("supplementary emoji", "😀x", 2, "x"),
                DeleteCase("joined-family emoji", "👩‍👩‍👧‍👦x", "👩‍👩‍👧‍👦".length, "x"),
            )) {
                main { text.editor.setText(value); text.editor.setSelection(cursor) }
                awaitEditorReady(text, "Backward delete for $caseName", value, cursor, cursor, "Delete")
                press("Delete")
                await("Backward delete failed for $caseName; expectedLength=${expected.length}") {
                    main { text.editor.text.toString() == expected }
                }
            }
            main { text.editor.setText("😀x"); text.editor.setSelection(0) }
            awaitEditorReady(text, "Forward delete at field start", "😀x", 0, 0, "Editing tools")
            openExtraKeys(); press("Accessory keys"); press("Forward delete")
            await("Forward delete did not remove supplementary Unicode") { main { text.editor.text.toString() == "x" } }
            press("Close extra keys")
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
            awaitEditorReady(activity, "Neighboring-word selection", "alpha beta", 10, 10, "Editing tools")
            openEditingTools()
            press("Select neighboring word")
            await("Neighboring word was not selected") {
                main {
                    val start = minOf(activity.editor.selectionStart, activity.editor.selectionEnd)
                    val end = maxOf(activity.editor.selectionStart, activity.editor.selectionEnd)
                    activity.editor.text.toString() == "alpha beta" && start == 6 && end == 10
                }
            }
            longPress("Select neighboring word")
            await("Select all did not apply") {
                main { activity.editor.selectionStart == 0 && activity.editor.selectionEnd == 10 }
            }
        } finally { close(activity) }
    }

    @Test fun latchedCtrlShiftArrowsKeepSelectingWords() = withKeyboard {
        val activity = launch(EditorInfo.IME_ACTION_DONE)
        try {
            main { activity.editor.setText("one two three"); activity.editor.setSelection(activity.editor.length()) }
            awaitEditorReady(activity, "Latched word selection", "one two three", 13, 13, "Editing tools")
            openExtraKeys()
            press("Control off")
            press("Shift off")
            press("Accessory keys")
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
