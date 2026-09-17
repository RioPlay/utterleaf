package org.utterleaf.voice

import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.view.accessibility.AccessibilityNodeInfo
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Live-IME evidence for the suggestion strip: completions of the composing
 * word, tap-to-complete, and the restricted-field gates. These checks run the
 * real typing IME against the contract activity's editor.
 */
@RunWith(AndroidJUnit4::class)
class SuggestionStripTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext

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

    private fun node(label: String): AccessibilityNodeInfo? {
        fun find(current: AccessibilityNodeInfo): AccessibilityNodeInfo? {
            if (current.contentDescription?.toString() == label && current.isClickable && current.isVisibleToUser) return current
            for (index in 0 until current.childCount) current.getChild(index)?.let(::find)?.let { return it }
            return null
        }
        return instrumentation.uiAutomation.windows.asSequence()
            .filter { it.type == android.view.accessibility.AccessibilityWindowInfo.TYPE_INPUT_METHOD }
            .mapNotNull { it.root?.let(::find) }.firstOrNull()
    }

    private fun press(label: String) {
        await("Could not press $label") {
            node(label)?.let { it.isEnabled && it.performAction(AccessibilityNodeInfo.ACTION_CLICK) } == true
        }
        instrumentation.waitForIdleSync()
    }

    private fun key(label: String) = node(label)

    private fun shell(command: String) = android.os.ParcelFileDescriptor.AutoCloseInputStream(
        instrumentation.uiAutomation.executeShellCommand(command)).bufferedReader().use { it.readText() }

    /** Enable and select Utterleaf's typing IME; restore the previous default when done. */
    private fun withKeyboard(block: () -> Unit) {
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        val id = manager.inputMethodList.single { it.serviceName == KeyboardIme::class.java.name }.id
        val previous = Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
        val wasEnabled = manager.enabledInputMethodList.any { it.id == id }
        val automation = instrumentation.uiAutomation
        val flags = automation.serviceInfo.flags
        try {
            automation.serviceInfo = automation.serviceInfo.apply {
                this.flags = flags or android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            }
            shell("ime enable $id"); shell("ime set $id")
            await("Typing IME was not selected") {
                Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD) == id
            }
            block()
        } finally {
            if (!previous.isNullOrBlank()) shell("ime set $previous")
            if (!wasEnabled) shell("ime disable $id")
            automation.serviceInfo = automation.serviceInfo.apply { this.flags = flags }
        }
    }

    private fun launch(raw: Boolean = false, password: Boolean = false): KeyboardEditorContractActivity {
        val activity = instrumentation.startActivitySync(Intent(app, KeyboardEditorContractActivity::class.java)
            .putExtra("ime_options", EditorInfo.IME_ACTION_DONE).putExtra("raw", raw)
            .putExtra("password", password).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        ) as KeyboardEditorContractActivity
        await("Editor activity never acquired window focus") {
            if (!main { activity.hasWindowFocus() }) main { activity.editor.requestFocus() }
            main { activity.hasWindowFocus() }
        }
        main { activity.editor.requestFocus() }
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        await("Editor never became active") { main { manager.isActive(activity.editor) } }
        // A cold emulator's first show cycle can be eaten while the system
        // settles the selected input method; retry until the panel appears.
        val deadline = android.os.SystemClock.elapsedRealtime() + 20_000
        var shown = false
        while (!shown && android.os.SystemClock.elapsedRealtime() < deadline) {
            main {
                manager.restartInput(activity.editor)
                manager.showSoftInput(activity.editor, InputMethodManager.SHOW_IMPLICIT)
            }
            try {
                await("Typing keyboard did not appear") { key("Undo") != null }
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
        await("Previous IME session did not close") { key("Undo") == null }
    }

    private fun keyboardOptions(): KeyboardOptions = KeyboardOptions.load(app)

    private fun keyDescriptions(): List<String> {
        val found = mutableListOf<String>()
        fun walk(current: AccessibilityNodeInfo) {
            if (found.size < 200) current.contentDescription?.let { description -> found.add(description.toString()) }
            for (index in 0 until current.childCount) current.getChild(index)?.let(::walk)
        }
        instrumentation.uiAutomation.windows
            .filter { it.type == android.view.accessibility.AccessibilityWindowInfo.TYPE_INPUT_METHOD }
            .forEach { it.root?.let(::walk) }
        return found
    }

    @Test fun stripCompletesTheComposingWordThroughTheEditor() {
        val previous = keyboardOptions()
        KeyboardOptions().save(app)
        withKeyboard {
            val activity = launch()
            try {
                for (letter in "hel") press(letter.toString())
                val deadline = android.os.SystemClock.elapsedRealtime() + 10_000
                var candidate: String? = null
                while (android.os.SystemClock.elapsedRealtime() < deadline) {
                    candidate = candidate ?: keyDescriptions().firstOrNull { it.startsWith("Complete with ") }
                    if (candidate != null) break
                    Thread.sleep(50)
                }
                if (candidate == null) {
                    throw AssertionError("Strip did not offer a completion for hel; shown=${keyDescriptions()}")
                }
                press(candidate)
                await("Tapping the completion did not commit through the editor") {
                    main { activity.editor.text.toString() } == candidate.removePrefix("Complete with ")
                }
            } finally {
                close(activity)
            }
        }
    }

    @Test fun preferenceAndRestrictedFieldsGateTheStrip() {
        val previous = keyboardOptions()
        var activity: KeyboardEditorContractActivity? = null
        withKeyboard {
            try {
                KeyboardOptions(suggestions = false).save(app)
                activity = launch()
                for (letter in "hel") press(letter.toString())
                instrumentation.waitForIdleSync()
                assertTrue("Strip rendered while suggestions were disabled",
                    keyDescriptions().none { it.startsWith("Complete with ") })
                close(activity!!)

                KeyboardOptions().save(app)
                activity = launch(password = true)
                await("Password keyboard did not appear") { key("Undo") != null }
                for (letter in "hel") press(letter.toString())
                instrumentation.waitForIdleSync()
                assertTrue("Strip rendered on a password field",
                    keyDescriptions().none { it.startsWith("Complete with ") })
                close(activity!!)

                activity = launch(raw = true)
                await("Raw keyboard did not appear") { key("Undo") != null }
                assertTrue("Strip rendered on a raw field",
                    keyDescriptions().none { it.startsWith("Complete with ") })
            } finally {
                activity?.let(::close)
            }
        }
    }
}
