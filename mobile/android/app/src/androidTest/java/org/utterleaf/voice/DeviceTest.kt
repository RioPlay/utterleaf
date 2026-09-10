package org.utterleaf.voice

import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.text.InputType
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.*
import org.junit.Test
import org.junit.FixMethodOrder
import org.junit.runners.MethodSorters
import org.junit.runner.RunWith
import java.nio.ByteBuffer
import java.nio.ByteOrder

@RunWith(AndroidJUnit4::class)
@FixMethodOrder(MethodSorters.NAME_ASCENDING)
class DeviceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext
    @Test fun packagedPermissionsAndBackupsAreRestricted() {
        val info = app.packageManager.getPackageInfo(app.packageName, PackageManager.GET_PERMISSIONS)
        assertEquals(setOf("android.permission.RECORD_AUDIO"), info.requestedPermissions.orEmpty().toSet())
        assertEquals(0, app.applicationInfo.flags and ApplicationInfo.FLAG_ALLOW_BACKUP)
    }
    @Test fun passwordFieldsAreBlocked() {
        for (variant in listOf(InputType.TYPE_TEXT_VARIATION_PASSWORD,
            InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD, InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD))
            assertFalse(VoiceIme.safeField(InputType.TYPE_CLASS_TEXT or variant))
        assertFalse(VoiceIme.safeField(InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD))
        assertTrue(VoiceIme.safeField(InputType.TYPE_CLASS_TEXT))
    }
    @Test fun systemRecognizesAnAuxiliaryVoiceInputMethod() {
        val manager = app.getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
        val ime = manager.inputMethodList.single { it.serviceName == VoiceIme::class.java.name }
        assertEquals(1, ime.subtypeCount)
        val subtype = ime.getSubtypeAt(0)
        assertEquals("voice", subtype.mode)
        assertTrue(subtype.isAuxiliary)
        assertTrue(subtype.overridesImplicitlyEnabledSubtype())
        assertEquals("android.permission.BIND_INPUT_METHOD", ime.serviceInfo.permission)
    }
    @Test fun typingKeyboardIsSeparateAndProtected() {
        val manager = app.getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
        val ime = manager.inputMethodList.single { it.serviceName == KeyboardIme::class.java.name }
        assertEquals("android.permission.BIND_INPUT_METHOD", ime.serviceInfo.permission)
        assertEquals("keyboard", ime.getSubtypeAt(0).mode)
        assertFalse(ime.getSubtypeAt(0).isAuxiliary)
        assertTrue(ime.getSubtypeAt(0).isAsciiCapable)
    }
    @Test fun keyboardSettingsPreviewRendersWithoutEnteringText() {
        val activity = instrumentation.startActivitySync(android.content.Intent(app, KeyboardSettingsActivity::class.java)
            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
        try {
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync {
                val content = activity.findViewById<android.view.ViewGroup>(android.R.id.content)
                (content.getChildAt(0) as android.widget.ScrollView).fullScroll(android.view.View.FOCUS_DOWN)
            }
            instrumentation.waitForIdleSync()
            val screenshot = instrumentation.uiAutomation.takeScreenshot()
            assertNotNull(screenshot)
            screenshot!!.recycle()
            // UTP uninstalls the target after testing. Preserve only this synthetic UI
            // screenshot in shell-owned storage before that cleanup removes app files.
            val command = "screencap -p /data/local/tmp/utterleaf-keyboard-preview.png"
            android.os.ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand(command)).use { it.readBytes() }
        } finally { instrumentation.runOnMainSync { activity.finish() } }
    }
    @Test fun typingKeysWorkWithoutSpeechAndResetSensitiveState() {
        instrumentation.runOnMainSync {
            val inserted = mutableListOf<String>()
            var deletes = 0
            var enters = 0
            val panel = TypingPanel(app, KeyboardOptions(), { inserted.add(it); true },
                { deletes++ }, { enters++ }, {}, { fail("Speech must be disabled") }, {}, {})
            fun buttons(view: android.view.View): List<android.widget.Button> = when (view) {
                is android.widget.Button -> listOf(view)
                is android.view.ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
                else -> emptyList()
            }
            fun key(label: String) = buttons(panel.view).single { it.contentDescription == label }
            panel.reset(false, false, "Done")
            assertFalse(key("Dictate").isEnabled)
            key("Shift off").performClick(); key("A").performClick(); key("a").performClick()
            key("Caps lock off").performClick(); key("B").performClick(); key("B").performClick()
            key("Shift off").performClick(); key("a").performClick(); key("B").performClick()
            key("Delete").performClick(); key("Done").performClick()
            assertEquals(listOf("A", "a", "B", "B", "a", "B"), inserted)
            assertEquals(1, deletes); assertEquals(1, enters)
            panel.reset(false, true, "Next") // A new numeric/password field cannot retain case state.
            key("1").performClick(); key("$").performClick()
            key("Switch letters and symbols").performClick()
            key("a").performClick()
            assertEquals(listOf("A", "a", "B", "B", "a", "B", "1", "$", "a"), inserted)
            assertTrue(buttons(panel.view).all { !it.contentDescription.isNullOrBlank() })
            assertTrue(key("Shift off").isFocusable)
        }
    }
    @Test fun liveKeyboardEditsAndSurvivesFieldAndVisibilityChanges() {
        val automation = instrumentation.uiAutomation
        val previousFlags = automation.serviceInfo.flags
        val manager = app.getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
        val keyboardId = manager.inputMethodList.single { it.serviceName == KeyboardIme::class.java.name }.id
        val wasEnabled = manager.enabledInputMethodList.any { it.id == keyboardId }
        val previousKeyboard = android.provider.Settings.Secure.getString(app.contentResolver,
            android.provider.Settings.Secure.DEFAULT_INPUT_METHOD)
        fun shell(value: String): String = android.os.ParcelFileDescriptor.AutoCloseInputStream(
            automation.executeShellCommand(value)).bufferedReader().use { it.readText() }
        fun awaitCondition(message: String, condition: () -> Boolean) {
            val deadline = android.os.SystemClock.elapsedRealtime() + 10000
            while (android.os.SystemClock.elapsedRealtime() < deadline) {
                if (condition()) return
                Thread.sleep(50)
            }
            fail(message)
        }
        fun <T> onMain(block: () -> T): T {
            val result = java.util.concurrent.atomic.AtomicReference<T>()
            instrumentation.runOnMainSync { result.set(block()) }
            return result.get()
        }
        fun findKey(description: String): android.view.accessibility.AccessibilityNodeInfo? {
            fun find(node: android.view.accessibility.AccessibilityNodeInfo): android.view.accessibility.AccessibilityNodeInfo? {
                if (node.contentDescription?.toString() == description && node.isClickable) return node
                for (index in 0 until node.childCount) {
                    val child = node.getChild(index) ?: continue
                    val found = find(child)
                    if (found != null) return found
                }
                return null
            }
            return automation.windows.asSequence()
                .filter { it.type == android.view.accessibility.AccessibilityWindowInfo.TYPE_INPUT_METHOD }
                .mapNotNull { it.root?.let(::find) }.firstOrNull()
        }
        fun press(description: String) {
            awaitCondition("Keyboard key unavailable: $description") { findKey(description)?.isEnabled == true }
            assertTrue("Could not press $description", findKey(description)!!.performAction(
                android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK))
            instrumentation.waitForIdleSync()
        }
        var activity: KeyboardTestActivity? = null
        try {
            automation.serviceInfo = automation.serviceInfo.apply {
                flags = flags or android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            }
            shell("ime enable $keyboardId")
            shell("ime set $keyboardId")
            awaitCondition("Test keyboard was not selected") {
                android.provider.Settings.Secure.getString(app.contentResolver,
                    android.provider.Settings.Secure.DEFAULT_INPUT_METHOD) == keyboardId
            }
            val screen = instrumentation.startActivitySync(android.content.Intent(app, KeyboardTestActivity::class.java)
                .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)) as KeyboardTestActivity
            activity = screen
            instrumentation.waitForIdleSync()
            fun show(field: android.widget.EditText) {
                onMain { field.requestFocus() }
                awaitCondition("Synthetic field did not acquire its input connection") { onMain { manager.isActive(field) } }
                onMain { manager.showSoftInput(field, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT) }
                awaitCondition("Typing keyboard did not appear") { findKey("a") != null }
            }
            show(screen.editor)
            press("a"); press("b"); press("c")
            awaitCondition("InputConnection did not commit letters") { onMain { screen.editor.text.toString() == "abc" } }
            press("Move cursor left")
            awaitCondition("InputConnection did not move cursor") { onMain { screen.editor.selectionStart == 2 } }
            press("Delete")
            awaitCondition("InputConnection did not delete before cursor") { onMain { screen.editor.text.toString() == "ac" } }
            press("Move cursor right"); press("d")
            awaitCondition("Cursor-right edit was incorrect") { onMain { screen.editor.text.toString() == "acd" } }
            press("Done")
            awaitCondition("Editor action did not reach editor") { onMain { screen.lastEditorAction == android.view.inputmethod.EditorInfo.IME_ACTION_DONE } }

            // Enter the real voice panel, then change fields. No microphone capture is started.
            press("Dictate")
            awaitCondition("Voice panel did not appear") {
                automation.windows.filter { it.type == android.view.accessibility.AccessibilityWindowInfo.TYPE_INPUT_METHOD }
                    .any { it.root?.findAccessibilityNodeInfosByText("Speak")?.isNotEmpty() == true }
            }
            show(screen.password)
            assertFalse("Password field allowed dictation", findKey("Dictate")!!.isEnabled)
            press("x")
            awaitCondition("Password typing did not work") { onMain { screen.password.text.toString() == "x" } }
            onMain { manager.hideSoftInputFromWindow(screen.password.windowToken, 0) }
            awaitCondition("Keyboard did not hide") { findKey("a") == null }
            show(screen.password)
            assertFalse("Reopened password field allowed dictation", findKey("Dictate")!!.isEnabled)
            press("y")
            awaitCondition("Keyboard failed after reopen") { onMain { screen.password.text.toString() == "xy" } }
            assertEquals("Password input changed the previous field", "acd", onMain { screen.editor.text.toString() })
        } finally {
            activity?.let { screen -> onMain { screen.finish() } }
            try {
                if (!previousKeyboard.isNullOrBlank()) shell("ime set $previousKeyboard")
            } finally {
                if (!wasEnabled) shell("ime disable $keyboardId")
                automation.serviceInfo = automation.serviceInfo.apply { flags = previousFlags }
            }
        }
    }
    @Test fun deniedPermissionCannotStartCapture() {
        assertEquals(PackageManager.PERMISSION_DENIED, app.checkSelfPermission("android.permission.RECORD_AUDIO"))
        instrumentation.runOnMainSync {
            val errors = mutableListOf<String>()
            val session = VoiceSession(app, { fail("Unexpected capture state") }, { fail("Unexpected transcript") }, { errors.add(it) })
            session.start()
            assertTrue(errors.single().contains("permission"))
            session.cancel()
        }
    }
    @Test fun realPanelRejectsLateSpeechAndInsertsOnlyOnce() {
        instrumentation.runOnMainSync {
            val callbacks = mutableListOf<(String) -> Unit>()
            val inserted = mutableListOf<String>()
            var cancellations = 0
            val panel = VoicePanel(app, { inserted.add(it); true }, {}, { _, result, _ ->
                callbacks.add(result)
                object : CaptureSession {
                    override fun start() { }
                    override fun stop() { }
                    override fun cancel() { cancellations++ }
                }
            })
            fun buttons(view: android.view.View): List<android.widget.Button> = when(view) {
                is android.widget.Button -> listOf(view)
                is android.view.ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
                else -> emptyList()
            }
            val speak = buttons(panel.view).first { it.text == "Speak" }
            val insert = buttons(panel.view).first { it.text == "Insert" }
            panel.view.measure(android.view.View.MeasureSpec.makeMeasureSpec(Ui.dp(app, 360), android.view.View.MeasureSpec.EXACTLY),
                android.view.View.MeasureSpec.makeMeasureSpec(0, android.view.View.MeasureSpec.UNSPECIFIED))
            assertTrue("Idle voice panel takes too much space", panel.view.measuredHeight <= Ui.dp(app, 240))
            speak.performClick()
            panel.clear() // Same path used by input-field changes and hiding the IME.
            callbacks[0]("stale speech")
            assertFalse(insert.isEnabled)
            assertEquals(1, cancellations)
            speak.performClick()
            callbacks[1]("fresh speech")
            assertTrue(insert.isEnabled)
            insert.performClick()
            insert.performClick()
            assertEquals(listOf("fresh speech"), inserted)
            assertFalse(insert.isEnabled)
            panel.clear()
        }
    }
    @Test fun verifiedModelTranscribesRealSpeechWithoutNetwork() {
        val testAssets = instrumentation.context.assets
        testAssets.open("ggml-tiny.en.bin").use { ModelStore.install(it, app.noBackupFilesDir) }
        assertTrue(ModelStore.ready(app.noBackupFilesDir))
        val wav = testAssets.open("jfk.wav").use { it.readBytes() }
        val buffer = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals("RIFF", String(wav, 0, 4))
        var offset = 12
        var audio = FloatArray(0)
        while (offset + 8 <= wav.size) {
            val type = String(wav, offset, 4)
            val size = buffer.getInt(offset + 4)
            if (type == "fmt ") { assertEquals(1, buffer.getShort(offset + 8).toInt()); assertEquals(16000, buffer.getInt(offset + 12)) }
            if (type == "data") {
                audio = FloatArray(size / 2) { buffer.getShort(offset + 8 + it * 2) / 32768f }; break
            }
            offset += 8 + size + (size % 2)
        }
        assertTrue(audio.size > 16000)
        NativeEngine.reset()
        val result = NativeEngine.decode(ModelStore.file(app.noBackupFilesDir).absolutePath, audio)
        assertNotNull(result)
        val text = result!!.toString(Charsets.UTF_8).lowercase()
        assertTrue("Known speech was not recognized", text.contains("country"))
        NativeEngine.reset(); NativeEngine.cancel()
        assertNull(NativeEngine.decode(ModelStore.file(app.noBackupFilesDir).absolutePath, audio))
        audio.fill(0f); result.fill(0)
    }
    @Test fun zCaptureStopsAndReleasesItsLeaseOnCancel() {
        // Last test: granting a runtime permission persists for this emulator install.
        instrumentation.context.assets.open("ggml-tiny.en.bin").use { ModelStore.install(it, app.noBackupFilesDir) }
        instrumentation.uiAutomation.grantRuntimePermission(app.packageName, "android.permission.RECORD_AUDIO")
        val activity = instrumentation.startActivitySync(android.content.Intent(app, SetupActivity::class.java)
            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
        val listening = java.util.concurrent.CountDownLatch(1)
        val failure = java.util.concurrent.atomic.AtomicReference<String>()
        lateinit var session: VoiceSession
        try {
            instrumentation.runOnMainSync {
                session = VoiceSession(app, { if (it.startsWith("Listening")) listening.countDown() },
                    { failure.set("Cancelled capture produced text") }, { failure.set(it); listening.countDown() })
                session.start()
            }
            assertTrue("Capture did not start", listening.await(10, java.util.concurrent.TimeUnit.SECONDS))
            assertNull(failure.get())
        } finally {
            instrumentation.runOnMainSync { session.cancel(); activity.finish() }
        }
        val deadline = android.os.SystemClock.elapsedRealtime() + 5000
        var released = false
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            if (WorkLease.acquire()) { WorkLease.release(); released = true; break }
            Thread.sleep(20)
        }
        assertTrue("Capture did not release its lease", released)
        assertNull(failure.get())
    }
}
