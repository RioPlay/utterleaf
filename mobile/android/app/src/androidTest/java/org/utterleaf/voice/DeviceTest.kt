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
        assertEquals(setOf("android.permission.RECORD_AUDIO"), info.requestedPermissions.toSet())
        assertEquals(0, app.applicationInfo.flags and ApplicationInfo.FLAG_ALLOW_BACKUP)
    }
    @Test fun passwordFieldsAreBlocked() {
        for (variant in listOf(InputType.TYPE_TEXT_VARIATION_PASSWORD,
            InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD, InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD))
            assertFalse(VoiceIme.safeField(InputType.TYPE_CLASS_TEXT or variant))
        assertFalse(VoiceIme.safeField(InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD))
        assertTrue(VoiceIme.safeField(InputType.TYPE_CLASS_TEXT))
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
