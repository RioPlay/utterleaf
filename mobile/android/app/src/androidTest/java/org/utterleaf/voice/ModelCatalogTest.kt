package org.utterleaf.voice

import android.content.Intent
import android.graphics.Rect
import android.os.Build
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.widget.RadioButton
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.InputStream
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.file.Files

@RunWith(AndroidJUnit4::class)
class ModelCatalogTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext
    private fun temporaryDirectory() = Files.createTempDirectory(app.cacheDir.toPath(), "model-catalog-").toFile()

    @Suppress("DEPRECATION")
    @Test fun systemInsetsPreservePaddingWithoutAccumulation() {
        org.junit.Assume.assumeTrue(Build.VERSION.SDK_INT >= 30)
        instrumentation.runOnMainSync {
            val insets = WindowInsets.Builder()
                .setInsets(WindowInsets.Type.statusBars(), android.graphics.Insets.of(0, 23, 0, 0))
                .setInsets(WindowInsets.Type.navigationBars(), android.graphics.Insets.of(7, 0, 11, 29))
                .build()
            for (navigationOnly in listOf(false, true)) {
                val view = View(app).apply { setPadding(2, 3, 5, 7) }
                Ui.applySystemInsets(view, navigationOnly)
                repeat(2) {
                    val remaining = view.dispatchApplyWindowInsets(insets)
                    assertEquals(9, view.paddingLeft)
                    assertEquals(if (navigationOnly) 3 else 26, view.paddingTop)
                    assertEquals(16, view.paddingRight)
                    assertEquals(36, view.paddingBottom)
                    assertEquals(0, remaining.systemWindowInsetBottom)
                }
                // Hidden bars or a later inset change must restore the original padding.
                val none = WindowInsets.CONSUMED
                view.dispatchApplyWindowInsets(none)
                assertEquals(listOf(2, 3, 5, 7), listOf(view.paddingLeft, view.paddingTop, view.paddingRight, view.paddingBottom))
            }
        }
    }

    @Suppress("DEPRECATION")
    @Test fun activityContentStaysWithinSystemBarsWithoutDoublePadding() {
        for (type in listOf(SetupActivity::class.java, KeyboardSettingsActivity::class.java, KeyboardTestActivity::class.java)) {
            val activity = instrumentation.startActivitySync(Intent(app, type).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            try {
                val laidOut = java.util.concurrent.CountDownLatch(1)
                instrumentation.runOnMainSync {
                    val decor = activity.window.decorView
                    decor.post { decor.requestApplyInsets(); decor.postOnAnimation { laidOut.countDown() } }
                }
                assertTrue("Activity never laid out", laidOut.await(5, java.util.concurrent.TimeUnit.SECONDS))
                instrumentation.waitForIdleSync()
                instrumentation.runOnMainSync {
                    val decor = activity.window.decorView
                    val root = activity.findViewById<ViewGroup>(android.R.id.content).getChildAt(0)
                    assertTrue(root.width > 0 && root.height > 0)
                    val insets = decor.rootWindowInsets
                    assertNotNull(insets)
                    val safe = if (Build.VERSION.SDK_INT >= 30) {
                        val bars = insets!!.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                        Rect(bars.left, bars.top, bars.right, bars.bottom)
                    } else Rect(insets!!.systemWindowInsetLeft, insets.systemWindowInsetTop,
                        insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
                    val windowOrigin = IntArray(2); decor.getLocationOnScreen(windowOrigin)
                    val origin = IntArray(2); root.getLocationOnScreen(origin)
                    // Root may already be fitted by the platform on older Android versions.
                    assertEquals("Left content edge", maxOf(origin[0], windowOrigin[0] + safe.left), origin[0] + root.paddingLeft)
                    assertEquals("Top content edge", maxOf(origin[1], windowOrigin[1] + safe.top), origin[1] + root.paddingTop)
                    assertEquals("Right content edge", minOf(origin[0] + root.width, windowOrigin[0] + decor.width - safe.right), origin[0] + root.width - root.paddingRight)
                    assertEquals("Bottom content edge", minOf(origin[1] + root.height, windowOrigin[1] + decor.height - safe.bottom), origin[1] + root.height - root.paddingBottom)
                    // The app never owns the decor's status/navigation-bar presentation.
                    assertEquals(0, decor.paddingTop)
                    assertEquals(0, decor.paddingBottom)
                }
            } finally { instrumentation.runOnMainSync { activity.finish() } }
        }
    }

    @Test fun catalogIdentifiesLegacyPathAndEveryReviewedSize() {
        val directory = temporaryDirectory()
        try {
            assertEquals(listOf("tiny.en", "base.en", "small.en"), ModelStore.catalog.map { it.id })
            assertEquals(ModelStore.URL, ModelStore.catalog.first().url)
            assertEquals(ModelStore.SHA256, ModelStore.catalog.first().sha256)
            assertEquals(ModelStore.SIZE, ModelStore.catalog.first().size)
            assertEquals("tiny.en.bin", ModelStore.file(directory).name)
            assertNull(ModelStore.installed(directory))
            for (spec in ModelStore.catalog) {
                // Identification only: sparse files are never passed to native code.
                RandomAccessFile(ModelStore.file(directory), "rw").use { it.setLength(spec.size) }
                assertEquals(spec, ModelStore.installed(directory))
                assertTrue(ModelStore.ready(directory))
                assertTrue(spec.url.startsWith("https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-"))
            }
            RandomAccessFile(ModelStore.file(directory), "rw").use { it.setLength(123) }
            assertFalse(ModelStore.ready(directory))
        } finally { directory.deleteRecursively() }
    }

    @Test fun arbitraryCatalogEntryCannotReachTheImporter() {
        val directory = temporaryDirectory()
        try {
            val previous = ModelStore.file(directory).apply { writeText("previous verified model") }
            val untrusted = ModelStore.Spec("untrusted", 0, "", "")
            val input = object : InputStream() {
                override fun read(): Int { fail("Unreviewed spec consumed input"); return -1 }
            }
            try { ModelStore.install(input, directory, untrusted); fail("Unreviewed model accepted") }
            catch (_: IllegalArgumentException) { }
            assertEquals("previous verified model", previous.readText())
            assertFalse(File(directory, "model-import.tmp").exists())
        } finally { directory.deleteRecursively() }
    }

    @Test fun selectedModelRejectsOversizeAndPreservesPreviousBytes() {
        val directory = temporaryDirectory()
        val spec = ModelStore.catalog.first()
        var consumed = 0L
        val oversized = object : InputStream() {
            override fun read(): Int { consumed++; return 0 }
            override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
                buffer.fill(0, offset, offset + length)
                consumed += length
                return length
            }
        }
        try {
            ModelStore.file(directory).writeText("previous verified model")
            try { ModelStore.install(oversized, directory, spec); fail("Oversized model accepted") }
            catch (_: IllegalArgumentException) { }
            assertTrue(consumed > spec.size)
            assertTrue("Importer read past its selected bound", consumed <= spec.size + 65536)
            assertEquals("previous verified model", ModelStore.file(directory).readText())
            assertFalse(File(directory, "model-import.tmp").exists())
        } finally { directory.deleteRecursively() }
    }

    @Test fun selectedModelMismatchAndReadFailurePreserveVerifiedTiny() {
        val directory = temporaryDirectory()
        try {
            instrumentation.context.assets.open("ggml-tiny.en.bin").use { ModelStore.install(it, directory) }
            val original = ModelStore.file(directory)
            assertEquals("tiny.en", ModelStore.installed(directory)?.id)
            try {
                instrumentation.context.assets.open("ggml-tiny.en.bin").use {
                    ModelStore.install(it, directory, ModelStore.catalog.single { spec -> spec.id == "base.en" })
                }
                fail("A different selected model was accepted")
            } catch (_: IllegalArgumentException) { }
            val broken = object : InputStream() {
                override fun read(): Int = throw java.io.IOException("Interrupted input")
            }
            try { ModelStore.install(broken, directory); fail("Broken input accepted") }
            catch (_: java.io.IOException) { }
            val digest = java.security.MessageDigest.getInstance("SHA-256")
            original.inputStream().use { input ->
                val buffer = ByteArray(65536)
                while (true) { val count = input.read(buffer); if (count < 0) break; digest.update(buffer, 0, count) }
            }
            assertEquals(ModelStore.SHA256, digest.digest().joinToString("") { "%02x".format(it) })
            assertFalse(File(directory, "model-import.tmp").exists())
        } finally { directory.deleteRecursively() }
    }

    @Test fun baseModelTranscribesFixture() {
        val directory = temporaryDirectory()
        val assets = instrumentation.context.assets
        var audio = FloatArray(0)
        var result: ByteArray? = null
        assertTrue("Another capture or import is active", WorkLease.acquire())
        try {
            val base = ModelStore.catalog.single { it.id == "base.en" }
            val detected = assets.open("ggml-base.en.bin").use { ModelStore.install(it, directory) }
            assertEquals("Import should identify base.en without a selection", base, detected)
            assertEquals(base, ModelStore.installed(directory))
            val wav = assets.open("jfk.wav").use { it.readBytes() }
            val buffer = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN)
            assertEquals("RIFF", String(wav, 0, 4))
            var offset = 12
            while (offset + 8 <= wav.size) {
                val type = String(wav, offset, 4)
                val size = buffer.getInt(offset + 4)
                if (type == "fmt ") {
                    assertEquals(1, buffer.getShort(offset + 8).toInt())
                    assertEquals(1, buffer.getShort(offset + 10).toInt())
                    assertEquals(16000, buffer.getInt(offset + 12))
                    assertEquals(16, buffer.getShort(offset + 22).toInt())
                }
                if (type == "data") {
                    audio = FloatArray(size / 2) { buffer.getShort(offset + 8 + it * 2) / 32768f }
                    break
                }
                offset += 8 + size + (size % 2)
            }
            assertTrue(audio.size > 16000)
            NativeEngine.reset()
            result = NativeEngine.decode(ModelStore.file(directory).absolutePath, audio)
            assertNotNull(result)
            assertTrue("Known speech was not recognized by base.en", result!!.toString(Charsets.UTF_8).lowercase().contains("country"))
        } finally {
            audio.fill(0f); result?.fill(0)
            NativeEngine.reset()
            directory.deleteRecursively()
            WorkLease.release()
        }
    }

    @Test fun setupSeparatesTypingVoiceAndSelectableModelLinks() {
        val activity = instrumentation.startActivitySync(Intent(app, SetupActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        fun labels(view: View): List<TextView> = when (view) {
            is ViewGroup -> (0 until view.childCount).flatMap { labels(view.getChildAt(it)) }
            is TextView -> listOf(view)
            else -> emptyList()
        }
        try {
            instrumentation.runOnMainSync {
                val texts = labels(activity.window.decorView)
                assertTrue(texts.any { it.text.toString() == "Your keyboard" })
                assertTrue(texts.any { it.text.toString() == "Optional · offline voice" })
                assertTrue(texts.any { it.text.contains("Utterleaf Keyboard") && (it.text.contains("Step 1") || it.text.contains("Typing ready")) })
                val choices = texts.filterIsInstance<RadioButton>()
                assertEquals(3, choices.size)
                for (spec in ModelStore.catalog) {
                    choices.single { it.text.startsWith(spec.id) }.performClick()
                    assertTrue(texts.any { it.text.toString() == "Download ${spec.id} in browser" })
                    assertTrue(texts.any { it.text.toString() == "Import a model" })
                    assertEquals(1, choices.count { it.isChecked })
                }
                // Merely choosing an option must not request permission, download or import.
                assertTrue(WorkLease.acquire()); WorkLease.release()
            }
        } finally { instrumentation.runOnMainSync { activity.finish() } }
    }
}
