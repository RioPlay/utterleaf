package org.utterleaf.voice

import android.content.Intent
import android.content.ContextWrapper
import android.os.SystemClock
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.CheckBox
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.atomic.AtomicReference
import java.nio.file.Files

@RunWith(AndroidJUnit4::class)
class VoicePanelControlsTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private fun <T> main(block: () -> T): T {
        if (android.os.Looper.myLooper() == android.os.Looper.getMainLooper()) return block()
        val result = AtomicReference<T>(); instrumentation.runOnMainSync { result.set(block()) }; return result.get()
    }
    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()
    private class Fake : CaptureSession {
        var started = 0; var stopped = 0; var cancelled = 0
        var status: (CaptureStatus) -> Unit = {}
        override fun start() { started++ }; override fun stop() { stopped++ }; override fun cancel() { cancelled++ }
    }
    private inner class Fixture(val activity: android.app.Activity, val panel: VoicePanel, val fake: Fake, val results: MutableList<(String) -> Unit>, val inserted: MutableList<String>) {
        fun key(label: String): Button = main { descendants(panel.view).filterIsInstance<Button>().single { it.text == label } }
        fun click(label: String) = main { key(label).performClick() }
        fun holdMode() = main { descendants(panel.view).filterIsInstance<CheckBox>().single().isChecked = true }
        fun touch(button: Button, action: Int, outside: Boolean = false) = main {
            val now = SystemClock.uptimeMillis()
            val event = MotionEvent.obtain(now, now, action, if (outside) -500f else button.width / 2f, button.height / 2f, 0)
            try { button.dispatchTouchEvent(event) } finally { event.recycle() }
        }
        fun hold(): Button {
            holdMode(); val button = key("Hold to speak"); touch(button, MotionEvent.ACTION_DOWN)
            UiAwait.until("Hold did not start capture") { fake.started == 1 }
            assertEquals(1, main { fake.started }); return button
        }
        fun capture(name: String) {
            require(name in setOf("voice-review", "voice-edit"))
            assertTrue(instrumentation.targetContext.applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE != 0)
            val flags = main { activity.window.attributes.flags }
            try {
                main { activity.window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE) }
                instrumentation.waitForIdleSync()
                android.os.ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand(
                    "screencap -p /data/local/tmp/utterleaf-$name.png")).use { it.readBytes() }
            } finally { main { activity.window.setFlags(flags, -1) } }
        }
        fun extraFinger(button: Button) = main {
            val props = Array(2) { index -> MotionEvent.PointerProperties().apply { id = index; toolType = MotionEvent.TOOL_TYPE_FINGER } }
            val coords = Array(2) { index -> MotionEvent.PointerCoords().apply {
                x = button.width / 2f + index; y = button.height / 2f; pressure = 1f; size = 1f
            } }
            val now = SystemClock.uptimeMillis()
            val event = MotionEvent.obtain(now, now, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT),
                2, props, coords, 0, 0, 1f, 1f, 0, 0, android.view.InputDevice.SOURCE_TOUCHSCREEN, 0)
            try { button.dispatchTouchEvent(event) } finally { event.recycle() }
        }
    }
    private fun withPanel(accept: Boolean = true, test: (Fixture) -> Unit) {
        val context = instrumentation.targetContext
        val prefs = context.getSharedPreferences("keyboard", 0)
        val old = prefs.getBoolean("voiceHoldToInsert", false)
        prefs.edit().putBoolean("voiceHoldToInsert", false).commit()
        val activity = instrumentation.startActivitySync(Intent(context, KeyboardSettingsActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        try {
            val laidOut = java.util.concurrent.CountDownLatch(1)
            val fixture = main {
                val fake = Fake(); val results = mutableListOf<(String) -> Unit>(); val inserted = mutableListOf<String>()
                val panel = VoicePanel(activity, { inserted.add(it); accept }, {}, { state, result, _ ->
                    fake.status = state; results.add(result); fake
                })
                Ui.applySystemInsets(panel.view)
                panel.view.addOnLayoutChangeListener { _, l, t, r, b, _, _, _, _ -> if (r > l && b > t) laidOut.countDown() }
                activity.setContentView(panel.view)
                Fixture(activity, panel, fake, results, inserted)
            }
            assertTrue(laidOut.await(5, java.util.concurrent.TimeUnit.SECONDS)); instrumentation.waitForIdleSync()
            test(fixture)
        } finally { main { activity.finish() }; instrumentation.waitForIdleSync(); prefs.edit().putBoolean("voiceHoldToInsert", old).commit() }
    }
    @Test fun captureLimitTransitionsToProcessingAndRejectsLateStatus() = withPanel { f ->
        f.click("Speak")
        val callback = f.fake.status
        main { callback(CaptureStatus(CapturePhase.PROCESSING, "Microphone off")) }
        assertFalse(main { f.key("Transcribing…").isEnabled })
        assertEquals(0, main { f.fake.stopped }) // No manual Stop needed at the capture limit.
        main { callback(CaptureStatus(CapturePhase.RECORDING, "Late recording update")) }
        assertFalse(main { f.key("Transcribing…").isEnabled })
        main { f.results.single()("finished") }
        main { callback(CaptureStatus(CapturePhase.PROCESSING, "Late processing update")) }
        assertTrue(main { f.key("Insert").isEnabled })
        f.click("Discard"); f.click("Speak")
        main { callback(CaptureStatus(CapturePhase.PROCESSING, "Previous take")) }
        assertTrue(main { f.key("Stop").isEnabled })
    }
    @Test fun micEntryStartsOneReviewTakeAndNeverRestartsOnClear() = withPanel { f ->
        f.holdMode()
        main { f.panel.startFromMicTap(); f.panel.startFromMicTap() }
        assertEquals(1, main { f.fake.started })
        f.click("Stop"); main { f.results.single()("review first") }
        assertTrue(f.inserted.isEmpty())
        f.click("Discard"); main { f.panel.startFromMicTap() }
        assertEquals(1, main { f.fake.started })
        main { (f.panel.view.parent as ViewGroup).removeView(f.panel.view); f.panel.startFromMicTap() }
        assertEquals(1, main { f.fake.started })
    }
    @Test fun primaryControlAndLocalEditingInsertExactlyOnce() = withPanel { f ->
        val primary = f.key("Speak"); f.click("Speak"); assertSame(primary, f.key("Stop"))
        f.click("Stop"); assertEquals(1, main { f.fake.stopped })
        main { f.results.single()("cat") }; assertSame(primary, f.key("Insert"))
        f.click("Edit transcript"); f.click("s"); f.capture("voice-edit"); f.click("Use edits"); f.capture("voice-review")
        assertTrue(f.inserted.isEmpty())
        f.click("Insert"); main { primary.performClick() }
        assertEquals(listOf("cats"), f.inserted); assertEquals(1, main { f.fake.started })
    }
    @Test fun holdReleaseThenResultInsertsOnce() = withPanel { f ->
        val button = f.hold(); f.touch(button, MotionEvent.ACTION_UP)
        assertEquals(1, main { f.fake.stopped }); assertTrue(f.inserted.isEmpty())
        main { f.results.single()("held take"); f.results.single()("duplicate") }
        assertEquals(listOf("held take"), f.inserted)
    }
    @Test fun resultBeforeReleaseWaitsAndCancelledHoldNeverInserts() = withPanel { f ->
        val button = f.hold(); main { f.results.single()("wait for release") }
        assertTrue(f.inserted.isEmpty())
        f.touch(button, MotionEvent.ACTION_UP, outside = true)
        main { f.results.single()("late") }; assertTrue(f.inserted.isEmpty())
    }
    @Test fun resultBeforeReleaseInsertsOnlyWhenFingerLifts() = withPanel { f ->
        val button = f.hold(); main { f.results.single()("ready") }
        assertTrue(f.inserted.isEmpty()); f.touch(button, MotionEvent.ACTION_UP)
        assertEquals(listOf("ready"), f.inserted)
    }
    @Test fun clearDuringHoldRejectsLateResultAndRelease() = withPanel { f ->
        val button = f.hold(); main { f.panel.clear() }
        f.touch(button, MotionEvent.ACTION_UP); main { f.results.single()("wrong field") }
        assertTrue(f.inserted.isEmpty()); assertEquals(1, main { f.fake.cancelled })
    }
    @Test fun transcriptExpandsAndEditsWithoutRecordingPreferences() = withPanel { f ->
        f.click("Speak"); f.click("Stop")
        val transcript = (1..30).joinToString("\n") { "Line $it of the transcript." }
        main { f.results.single()(transcript) }
        val preview = main { descendants(f.panel.view).filterIsInstance<android.widget.EditText>().single() }
        val collapsed = main { preview.layoutParams.height }
        assertTrue(main { preview.isEnabled && preview.keyListener == null && preview.isTextSelectable })
        assertEquals(View.GONE, main { descendants(f.panel.view).filterIsInstance<CheckBox>().single().visibility })
        f.click("Expand transcript")
        assertTrue(main { preview.layoutParams.height > collapsed })
        assertEquals(transcript, main { preview.text.toString() })
        f.click("Edit transcript")
        assertEquals(collapsed, main { preview.layoutParams.height })
        assertNotNull(main { preview.keyListener })
        main { preview.setSelection(preview.length()) }
        f.click("s"); f.click("Use edits"); f.click("Insert")
        assertEquals(listOf(transcript + "s"), f.inserted)
    }
    @Test fun shortTapDoesNotCaptureAndExtraFingerCancelsHold() = withPanel { f ->
        f.holdMode(); val primary = f.key("Hold to speak")
        f.touch(primary, MotionEvent.ACTION_DOWN); f.touch(primary, MotionEvent.ACTION_UP)
        UiAwait.remains("Short tap must not start capture") { f.fake.started == 0 }
        val held = f.hold(); f.extraFinger(held); f.touch(held, MotionEvent.ACTION_UP)
        main { f.results.single()("cancelled") }
        assertTrue(f.inserted.isEmpty()); assertEquals(1, main { f.fake.cancelled })
    }
    @Test fun rejectedAutomaticInsertKeepsEditableReview() = withPanel(accept = false) { f ->
        val button = f.hold(); main { f.results.single()("original") }
        f.touch(button, MotionEvent.ACTION_UP)
        assertEquals(listOf("original"), f.inserted)
        f.click("Edit transcript"); f.click("."); f.click("Use edits"); f.click("Insert")
        assertEquals(listOf("original", "original."), f.inserted)
    }

    @Test fun modelSelectorSwitchesVerifiedPrivateSlotsAndRejectsBusyOrStaleChoices() {
        val activity = instrumentation.startActivitySync(Intent(instrumentation.targetContext, KeyboardSettingsActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        val directory = Files.createTempDirectory(activity.cacheDir.toPath(), "utterleaf-voice-models").toFile()
        try {
            fun sparse(id: String) {
                val spec = ModelStore.catalog.single { it.id == id }
                val file = java.io.File(directory, "models/ggml-$id.bin")
                file.parentFile.mkdirs(); java.io.RandomAccessFile(file, "rw").use { it.setLength(spec.size) }
            }
            // Private readiness fixtures only: fake sessions never send sparse files to native code.
            sparse("tiny.en"); sparse("base.en")
            java.io.File(directory, "active-model").writeText("tiny.en")
            lateinit var panel: VoicePanel; lateinit var fake: Fake
            val results = mutableListOf<(String) -> Unit>()
            val wrapper = object : ContextWrapper(activity) { override fun getNoBackupFilesDir() = directory }
            val laidOut = java.util.concurrent.CountDownLatch(1)
            main {
                fake = Fake()
                panel = VoicePanel(wrapper, { true }, {}, { _, result, _ -> results += result; fake })
                panel.view.addOnLayoutChangeListener { _, l, t, r, b, _, _, _, _ -> if (r > l && b > t) laidOut.countDown() }
                activity.setContentView(panel.view)
            }
            assertTrue(laidOut.await(5, java.util.concurrent.TimeUnit.SECONDS)); instrumentation.waitForIdleSync()
            fun button(text: String) = main { descendants(panel.view).filterIsInstance<Button>().single { it.text == text } }
            main { button("Model · tiny.en").performClick() }
            val baseChoice = button("Balanced · base.en")
            main { assertTrue(WorkLease.acquire()) }
            try { main { baseChoice.performClick() } }
            finally { main { WorkLease.release() } }
            assertEquals("tiny.en", ModelStore.installed(directory)?.id)
            main { baseChoice.performClick() }
            assertEquals("tiny.en", ModelStore.installed(directory)?.id)
            main { button("Model · tiny.en").performClick(); button("Balanced · base.en").performClick() }
            assertEquals("base.en", ModelStore.installed(directory)?.id)

            main { button("Model · base.en").performClick() }
            val staleChoice = button("Fast · tiny.en")
            main { panel.startFromMicTap() }
            main { staleChoice.performClick() }
            assertEquals("base.en", ModelStore.installed(directory)?.id)
            main { panel.clear(); staleChoice.performClick() }
            assertEquals("base.en", ModelStore.installed(directory)?.id)
            assertEquals(1, fake.started)
        } finally {
            main { activity.finish() }; instrumentation.waitForIdleSync(); directory.deleteRecursively()
        }
    }
}
