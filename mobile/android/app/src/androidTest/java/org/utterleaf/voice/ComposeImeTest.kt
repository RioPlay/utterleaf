package org.utterleaf.voice

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.text.InputType
import android.text.Selection
import android.view.View
import android.view.ViewGroup
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.view.inputmethod.InputMethodSubtype
import android.widget.Button
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.util.concurrent.atomic.AtomicReference
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ComposeImeTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext

    private fun shell(command: String) = android.os.ParcelFileDescriptor.AutoCloseInputStream(
        instrumentation.uiAutomation.executeShellCommand(command),
    ).bufferedReader().use { it.readText() }

    private fun <T> main(block: () -> T): T {
        val result = AtomicReference<T>()
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

    private fun findNode(description: String): AccessibilityNodeInfo? {
        if (android.os.Build.VERSION.SDK_INT >= 34) instrumentation.uiAutomation.clearCache()
        fun find(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
            if (node.contentDescription?.toString() == description) return node
            for (index in 0 until node.childCount) node.getChild(index)?.let(::find)?.let { return it }
            return null
        }
        return instrumentation.uiAutomation.windows.asSequence()
            .filter { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD }
            .mapNotNull { it.root?.let(::find) }
            .firstOrNull()
    }

    private fun press(description: String) {
        await("Missing enabled $description") { findNode(description)?.isEnabled == true }
        val deadline = android.os.SystemClock.elapsedRealtime() + 2_000
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            if (findNode(description)?.performAction(AccessibilityNodeInfo.ACTION_CLICK) == true) {
                instrumentation.waitForIdleSync()
                return
            }
            Thread.sleep(50)
        }
        throw AssertionError("Could not press $description")
    }

    private fun longPress(description: String) {
        await("Missing enabled $description") { findNode(description)?.isEnabled == true }
        val deadline = android.os.SystemClock.elapsedRealtime() + 2_000
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            if (findNode(description)?.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK) == true) {
                instrumentation.waitForIdleSync()
                return
            }
            Thread.sleep(50)
        }
        throw AssertionError("Could not long press $description")
    }

    private fun descendants(view: View): List<View> = listOf(view) + if (view is ViewGroup)
        (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()

    private fun currentButton(description: String): Button = main {
        android.view.inspector.WindowInspector.getGlobalWindowViews().flatMap(::descendants)
            .filterIsInstance<Button>().single { it.isShown && it.contentDescription == description }
    }

    private fun currentService(): KeyboardIme = currentButton("Undo").context as KeyboardIme

    private fun launch(raw: Boolean = false): KeyboardEditorContractActivity {
        val activity = instrumentation.startActivitySync(
            Intent(app, KeyboardEditorContractActivity::class.java)
                .putExtra("ime_options", EditorInfo.IME_ACTION_DONE)
                .putExtra("raw", raw)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        ) as KeyboardEditorContractActivity
        await("Editor activity never acquired window focus") {
            // A cold CI emulator can hand out window focus late — the platform
            // launcher's ANR dialog occasionally steals it; recover that named
            // fixture failure once and keep nudging the editor.
            if (!main { activity.hasWindowFocus() }) {
                UiAwait.dismissLauncherAnrDialog()
                main { activity.editor.requestFocus() }
            }
            main { activity.hasWindowFocus() }
        }
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        main { activity.editor.requestFocus() }
        await("Editor never became active") { main { manager.isActive(activity.editor) } }
        // A prior test's manual service callbacks can leave the IME expecting a
        // fresh show cycle; retry until the panel actually appears.
        val deadline = android.os.SystemClock.elapsedRealtime() + 20_000
        var shown = false
        while (!shown && android.os.SystemClock.elapsedRealtime() < deadline) {
            main {
                manager.restartInput(activity.editor)
                manager.showSoftInput(activity.editor, InputMethodManager.SHOW_IMPLICIT)
            }
            try {
                await("Typing keyboard did not appear") { findNode("Undo") != null }
                shown = true
            } catch (retry: AssertionError) {
                Thread.sleep(250)
            }
        }
        check(shown) { "Typing keyboard did not appear" }
        return activity
    }

    private fun close(activity: KeyboardEditorContractActivity) {
        main { activity.finish() }
        await("Previous IME session did not close") { findNode("Undo") == null }
    }

    private fun openCompose() {
        if (findNode("Latin compose") == null) press("Keyboard tools")
        press("Latin compose")
        press("Acute compose mark")
        await("Compose letter view did not appear") { findNode("Cancel compose") != null }
    }

    private fun withKeyboard(block: (InputMethodManager) -> Unit) {
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        val id = manager.inputMethodList.single { it.serviceName == KeyboardIme::class.java.name }.id
        val previous = Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
        val enabled = manager.enabledInputMethodList.any { it.id == id }
        val options = KeyboardOptions.load(app)
        val automation = instrumentation.uiAutomation
        val flags = automation.serviceInfo.flags
        try {
            automation.serviceInfo = automation.serviceInfo.apply {
                this.flags = flags or AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            }
            shell("ime enable $id")
            shell("ime set $id")
            KeyboardOptions().save(app)
            await("Typing IME was not selected") {
                Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD) == id
            }
            block(manager)
        } finally {
            if (!previous.isNullOrBlank()) {
                shell("ime set $previous")
                await("Previous IME was not restored") {
                    Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD) == previous
                }
            }
            if (!enabled) shell("ime disable $id")
            options.save(app)
            automation.serviceInfo = automation.serviceInfo.apply { this.flags = flags }
        }
    }

    @Test fun completedComposeReplacesUtf16SelectionOnceWithoutClipboardOrSubmit() = withKeyboard {
        val clipboard = app.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val sentinel = "synthetic compose clipboard"
        clipboard.setPrimaryClip(ClipData.newPlainText("compose-test", sentinel))
        var opened: KeyboardEditorContractActivity? = null
        try {
            val activity = launch()
            opened = activity
            val original = "A😀 SELECT Z"
            val start = original.indexOf("SELECT")
            val end = start + "SELECT".length
            main {
                activity.editor.setText(original)
                Selection.setSelection(activity.editor.text, end, start)
            }
            openCompose()
            val staleLetter = currentButton("e")
            main { assertEquals(original, activity.editor.text.toString()) }
            press("e")
            await("Composed character did not replace the selection") {
                main { activity.editor.text.toString() == "A😀 é Z" }
            }
            main { staleLetter.performClick() }
            Thread.sleep(100)
            main {
                assertEquals("A😀 é Z", activity.editor.text.toString())
                assertEquals(EditorInfo.IME_ACTION_NONE, activity.action)
            }
            assertEquals(sentinel, clipboard.primaryClip?.getItemAt(0)?.text?.toString())
        } finally {
            clipboard.clearPrimaryClip()
            opened?.let(::close)
        }
    }

    @Test fun fieldSubtypeHideAndFinishDropPendingComposeAndStaleButtons() = withKeyboard { manager ->
        fun assertCleared(name: String, trigger: (KeyboardIme, KeyboardEditorContractActivity) -> Unit) {
            val activity = launch()
            try {
                main { activity.editor.setText("host-$name") }
                openCompose()
                val staleLetter = currentButton("e")
                val service = main { staleLetter.context as KeyboardIme }
                main { trigger(service, activity) }
                await("$name did not dismiss pending Compose") { findNode("Cancel compose") == null }
                main { staleLetter.performClick() }
                Thread.sleep(100)
                main { assertEquals("host-$name", activity.editor.text.toString()) }
            } finally {
                close(activity)
            }
        }

        assertCleared("field") { service, _ ->
            service.onStartInput(EditorInfo().apply { inputType = InputType.TYPE_CLASS_TEXT }, false)
        }
        assertCleared("subtype") { service, _ ->
            KeyboardIme::class.java.getDeclaredMethod(
                "onCurrentInputMethodSubtypeChanged",
                InputMethodSubtype::class.java,
            ).apply { isAccessible = true }.invoke(service, InputMethodSubtype.InputMethodSubtypeBuilder().build())
        }
        assertCleared("hide") { _, activity -> manager.hideSoftInputFromWindow(activity.editor.windowToken, 0) }
        assertCleared("finish") { service, _ ->
            service.onFinishInput()
            service.onFinishInputView(false)
            service.onWindowHidden()
        }
    }

    @Test fun rawFieldCannotEnterCompose() = withKeyboard {
        val activity = launch(raw = true)
        try {
            // Raw fields disable emoji and composition even though Tools remains reachable.
            val emoji = checkNotNull(findNode("Emoji"))
            assertFalse(emoji.isEnabled)
            assertFalse(emoji.performAction(AccessibilityNodeInfo.ACTION_CLICK))
            press("Keyboard tools")
            val compose = checkNotNull(findNode("Latin compose unavailable in raw input"))
            assertFalse(compose.isEnabled)
            assertFalse(compose.performAction(AccessibilityNodeInfo.ACTION_CLICK))
            assertEquals(android.view.KeyEvent.KEYCODE_UNKNOWN, main { activity.rawKey })
            assertEquals(null, findNode("Acute compose mark"))
        } finally {
            close(activity)
        }
    }
}
