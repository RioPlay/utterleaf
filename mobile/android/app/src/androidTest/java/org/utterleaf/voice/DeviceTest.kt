package org.utterleaf.voice

import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.text.InputType
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.nio.ByteBuffer
import java.nio.ByteOrder

@RunWith(AndroidJUnit4::class)
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
}
