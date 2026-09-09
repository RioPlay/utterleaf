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
        val ime = manager.inputMethodList.single { it.packageName == app.packageName }
        assertEquals(1, ime.subtypeCount)
        val subtype = ime.getSubtypeAt(0)
        assertEquals("voice", subtype.mode)
        assertTrue(subtype.isAuxiliary)
        assertTrue(subtype.overridesImplicitlyEnabledSubtype())
        assertEquals("android.permission.BIND_INPUT_METHOD", ime.serviceInfo.permission)
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
