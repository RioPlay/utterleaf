package org.utterleaf.voice

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Context
import android.content.Intent
import android.media.AudioManager
import android.os.SystemClock
import android.provider.Settings
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.view.inputmethod.InputMethodManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.util.concurrent.atomic.AtomicReference
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Real auxiliary-IME lifecycle, with no recording action or synthetic service callbacks. */
@RunWith(AndroidJUnit4::class)
class VoiceImeLifecycleTest {
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
        val deadline = SystemClock.elapsedRealtime() + 10_000
        while (SystemClock.elapsedRealtime() < deadline) {
            if (condition()) return
            SystemClock.sleep(50)
        }
        throw AssertionError(message)
    }

    private fun node(label: String): AccessibilityNodeInfo? {
        if (android.os.Build.VERSION.SDK_INT >= 34) instrumentation.uiAutomation.clearCache()
        fun find(item: AccessibilityNodeInfo): AccessibilityNodeInfo? {
            if (item.isVisibleToUser && (item.text?.toString() == label ||
                    item.contentDescription?.toString() == label)) return item
            for (index in 0 until item.childCount) item.getChild(index)?.let(::find)?.let { return it }
            return null
        }
        return instrumentation.uiAutomation.windows.asSequence()
            .filter { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD }
            .mapNotNull { it.root?.let(::find) }.firstOrNull()
    }

    private fun click(label: String) {
        var target: AccessibilityNodeInfo? = null
        await("Missing enabled $label") { node(label)?.takeIf { it.isEnabled }?.also { target = it } != null }
        assertTrue("$label rejected its single click", target!!.performAction(AccessibilityNodeInfo.ACTION_CLICK))
        instrumentation.waitForIdleSync()
    }

    @Test
    fun auxiliaryVoiceHideReopenClearsOptionsAndDoesNotStartCapture() {
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        val audio = app.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val voiceId = manager.inputMethodList.single { it.serviceName == VoiceIme::class.java.name }.id
        val keyboardId = manager.inputMethodList.single { it.serviceName == KeyboardIme::class.java.name }.id
        val previous = Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
        val initiallyEnabled = manager.enabledInputMethodList.map { it.id }.toSet()
        val automation = instrumentation.uiAutomation
        val originalFlags = automation.serviceInfo.flags
        var activity: KeyboardTestActivity? = null
        var failure: Throwable? = null
        try {
            automation.serviceInfo = automation.serviceInfo.apply {
                flags = originalFlags or AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            }
            // Establish a deterministic previous keyboard for the auxiliary IME's return action.
            shell("ime enable $keyboardId")
            shell("ime enable $voiceId")
            shell("ime set $keyboardId")
            ImeTestReadiness.awaitDefaultImeStable(app, manager, keyboardId, "Voice previous-keyboard setup")
            shell("ime set $voiceId")
            ImeTestReadiness.awaitDefaultImeStable(app, manager, voiceId, "Auxiliary voice setup")
            val screen = instrumentation.startActivitySync(
                Intent(app, KeyboardTestActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            ) as KeyboardTestActivity
            activity = screen
            await("Voice host window did not focus") { main { screen.hasWindowFocus() } }
            main { screen.editor.setText("voice lifecycle sentinel"); screen.editor.requestFocus() }
            await("Voice host editor did not become active") { main { manager.isActive(screen.editor) } }
            main {
                manager.restartInput(screen.editor)
                manager.showSoftInput(screen.editor, InputMethodManager.SHOW_IMPLICIT)
            }
            await("Auxiliary voice IME did not open idle") { node("Voice available") != null && node("Voice options") != null }
            assertTrue("Opening voice started recording", audio.activeRecordingConfigurations.isEmpty())
            click("Voice options")
            await("Voice options did not expand") { node("Hide voice options") != null }
            main { manager.hideSoftInputFromWindow(screen.editor.windowToken, 0) }
            await("Auxiliary voice IME did not hide") { node("Voice available") == null }
            assertEquals("voice lifecycle sentinel", main { screen.editor.text.toString() })
            assertTrue("Hiding voice left recording active", audio.activeRecordingConfigurations.isEmpty())

            // One explicit show, no restartInput: exercises reuse after onWindowHidden.
            main { manager.showSoftInput(screen.editor, InputMethodManager.SHOW_IMPLICIT) }
            await("Auxiliary voice IME did not reopen idle with collapsed options") {
                node("Voice available") != null && node("Voice options") != null && node("Hide voice options") == null
            }
            assertTrue("Reopening voice started recording", audio.activeRecordingConfigurations.isEmpty())
            click("Voice options")
            await("Reopened voice controls were not usable") { node("Hide voice options") != null }
            click("Hide voice options")
            click("Keyboard")
            ImeTestReadiness.awaitDefaultImeStable(app, manager, keyboardId, "Return from auxiliary voice")
            await("Return did not show the typing keyboard") { node("Editing tools") != null }
            assertEquals("voice lifecycle sentinel", main { screen.editor.text.toString() })
        } catch (error: Throwable) {
            failure = error
            throw error
        } finally {
            ImeTestReadiness.cleanupPreserving(failure,
                { activity?.let { main { it.finish() }; instrumentation.waitForIdleSync() } },
                {
                    if (!previous.isNullOrBlank()) {
                        shell("ime set $previous")
                        ImeTestReadiness.awaitDefaultImeStable(app, manager, previous, "Voice prior-IME restore")
                    }
                },
                { if (voiceId !in initiallyEnabled) shell("ime disable $voiceId") },
                { if (keyboardId !in initiallyEnabled) shell("ime disable $keyboardId") },
                { automation.serviceInfo = automation.serviceInfo.apply { flags = originalFlags } },
            )
        }
    }
}
