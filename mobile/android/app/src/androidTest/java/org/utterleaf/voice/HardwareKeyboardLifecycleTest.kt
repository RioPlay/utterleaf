package org.utterleaf.voice

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Context
import android.content.Intent
import android.hardware.input.InputManager
import android.media.AudioManager
import android.os.Handler
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import android.provider.Settings
import android.view.InputDevice
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.view.inputmethod.InputMethodManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.filters.SdkSuppress
import androidx.test.platform.app.InstrumentationRegistry
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** API 35 emulator evidence: a real uinput device, not synthetic configuration callbacks. */
@RunWith(AndroidJUnit4::class)
@SdkSuppress(minSdkVersion = 31)
class HardwareKeyboardLifecycleTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext
    private val deviceName = "Utterleaf lifecycle keyboard"

    private fun shell(command: String) = ParcelFileDescriptor.AutoCloseInputStream(
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
            if (item.isVisibleToUser && item.contentDescription?.toString() == label) return item
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
    fun externalKeyboardAddRemoveAndExplicitReopenLeaveNoToolsOrCapture() {
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        val devices = app.getSystemService(Context.INPUT_SERVICE) as InputManager
        val audio = app.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val id = manager.inputMethodList.single { it.serviceName == KeyboardIme::class.java.name }.id
        val previous = Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
        val enabled = manager.enabledInputMethodList.any { it.id == id }
        val originalOptions = KeyboardOptions.load(app)
        val automation = instrumentation.uiAutomation
        val originalFlags = automation.serviceInfo.flags
        val added = AtomicInteger(-1)
        val removed = AtomicBoolean(false)
        val listener = object : InputManager.InputDeviceListener {
            override fun onInputDeviceAdded(deviceId: Int) {
                if (devices.getInputDevice(deviceId)?.name == deviceName) added.set(deviceId)
            }
            override fun onInputDeviceRemoved(deviceId: Int) {
                if (deviceId == added.get()) removed.set(true)
            }
            override fun onInputDeviceChanged(deviceId: Int) = Unit
        }
        var activity: KeyboardTestActivity? = null
        var commandOutput: ParcelFileDescriptor? = null
        var commandInput: ParcelFileDescriptor.AutoCloseOutputStream? = null
        var failure: Throwable? = null
        try {
            assertTrue("A prior fixture device was left attached", devices.inputDeviceIds.none {
                devices.getInputDevice(it)?.name == deviceName
            })
            automation.serviceInfo = automation.serviceInfo.apply {
                flags = originalFlags or AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            }
            originalOptions.copy(extraKeys = true).save(app)
            shell("ime enable $id")
            shell("ime set $id")
            ImeTestReadiness.awaitDefaultImeStable(app, manager, id, "Hardware lifecycle setup")
            val screen = instrumentation.startActivitySync(
                Intent(app, KeyboardTestActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            ) as KeyboardTestActivity
            activity = screen
            await("Hardware host window did not focus") { main { screen.hasWindowFocus() } }
            main {
                screen.editor.setText("hardware sentinel")
                screen.editor.setSelection(screen.editor.length())
                screen.editor.requestFocus()
            }
            await("Hardware host editor did not become active") { main { manager.isActive(screen.editor) } }
            main {
                manager.restartInput(screen.editor)
                manager.showSoftInput(screen.editor, InputMethodManager.SHOW_IMPLICIT)
            }
            click("Editing tools")
            click("Extra keys")
            click("Control off")
            await("Control did not arm") { node("Control on") != null }

            devices.registerInputDeviceListener(listener, Handler(Looper.getMainLooper()))
            val descriptors = automation.executeShellCommandRw("uinput -")
            commandOutput = descriptors[0]
            commandInput = ParcelFileDescriptor.AutoCloseOutputStream(descriptors[1])
            // Numeric control/event codes work with the Android 15 uinput parser.
            val registration = """{"id":1,"command":"register","name":"$deviceName","vid":6353,"pid":5678,"bus":"usb","configuration":[{"type":100,"data":[1]},{"type":101,"data":[16,30,44,28,57]}]}"""
            commandInput.write((registration + "\n").toByteArray(Charsets.UTF_8))
            commandInput.flush()
            await("Android did not report the external keyboard being added") { added.get() >= 0 }
            val attached = checkNotNull(devices.getInputDevice(added.get()))
            assertTrue(attached.isExternal)
            assertEquals(InputDevice.KEYBOARD_TYPE_ALPHABETIC, attached.keyboardType)
            assertTrue(attached.supportsSource(InputDevice.SOURCE_KEYBOARD))
            assertEquals("hardware sentinel", main { screen.editor.text.toString() })
            assertTrue("Attaching a keyboard started recording", audio.activeRecordingConfigurations.isEmpty())

            // Android may retain the input view if another hardware keyboard was already
            // present. Do not substitute that situation for a configuration transition.
            android.util.Log.i("UtterleafLifecycle", "externalAdded=true keyboard=" +
                main { screen.resources.configuration.keyboard } + " toolsVisible=" + (node("Control on") != null))
            main { manager.hideSoftInputFromWindow(screen.editor.windowToken, 0) }
            await("Keyboard did not hide with the external device attached") { node("a") == null }
            commandInput.close() // EOF unregisters only this owned uinput device.
            commandInput = null
            await("Android did not report the external keyboard being removed") {
                removed.get() && devices.getInputDevice(added.get()) == null
            }
            assertTrue("Removing a keyboard started recording", audio.activeRecordingConfigurations.isEmpty())
            main { manager.showSoftInput(screen.editor, InputMethodManager.SHOW_IMPLICIT) }
            await("Reopen after removal did not restore daily typing") {
                node("Editing tools") != null && node("Control on") == null && node("Escape") == null
            }
            click("a")
            await("Fresh typing failed after the hardware lifecycle") {
                main { screen.editor.text.toString() == "hardware sentinela" }
            }
            click("Editing tools")
            click("Extra keys")
            await("Hardware lifecycle retained a modifier") { node("Control off") != null && node("Control on") == null }
        } catch (error: Throwable) {
            failure = error
            throw error
        } finally {
            ImeTestReadiness.cleanupPreserving(failure,
                { commandInput?.close() },
                { commandOutput?.close() },
                {
                    if (added.get() >= 0) await("Fixture keyboard remained attached during cleanup") {
                        devices.getInputDevice(added.get()) == null
                    }
                },
                { devices.unregisterInputDeviceListener(listener) },
                { activity?.let { main { it.finish() }; instrumentation.waitForIdleSync() } },
                {
                    if (!previous.isNullOrBlank()) {
                        shell("ime set $previous")
                        ImeTestReadiness.awaitDefaultImeStable(app, manager, previous, "Hardware prior-IME restore")
                    }
                },
                { if (!enabled) shell("ime disable $id") },
                { originalOptions.save(app) },
                { automation.serviceInfo = automation.serviceInfo.apply { flags = originalFlags } },
            )
        }
    }
}
