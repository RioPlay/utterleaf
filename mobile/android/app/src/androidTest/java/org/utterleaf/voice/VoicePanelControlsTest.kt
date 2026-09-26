package org.utterleaf.voice

import android.content.Intent
import android.content.ContextWrapper
import android.graphics.Rect
import android.os.SystemClock
import android.util.TypedValue
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.CheckBox
import android.widget.TextView
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
        fun hasText(label: String) = main {
            descendants(panel.view).filterIsInstance<android.widget.TextView>().any { it.text == label }
        }
        fun click(label: String) = main { key(label).performClick() }
        fun holdMode() = main { descendants(panel.view).filterIsInstance<CheckBox>().single().isChecked = true }
        fun touch(button: Button, action: Int, outside: Boolean = false) = main {
            val now = SystemClock.uptimeMillis()
            val event = MotionEvent.obtain(now, now, action, if (outside) -500f else button.width / 2f, button.height / 2f, 0)
            try { button.dispatchTouchEvent(event) } finally { event.recycle() }
        }
        fun hold(): Button {
            holdMode(); val button = key("Hold to dictate"); touch(button, MotionEvent.ACTION_DOWN)
            UiAwait.until("Hold did not start capture") { fake.started == 1 }
            assertEquals(1, main { fake.started }); return button
        }
        fun capture(name: String) {
            require(name in setOf("voice-available", "voice-listening", "voice-processing",
                "voice-review", "voice-edit", "voice-problem", "voice-oled-available"))
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
    private fun withPanel(accept: Boolean = true, theme: ThemeMode? = null,
                          insertResult: ((String) -> Boolean)? = null, test: (Fixture) -> Unit) {
        val context = instrumentation.targetContext
        val oldOptions = KeyboardOptions.load(context)
        if (theme != null) oldOptions.copy(theme = theme).save(context)
        val prefs = context.getSharedPreferences("keyboard", 0)
        val old = prefs.getBoolean("voiceHoldToInsert", false)
        prefs.edit().putBoolean("voiceHoldToInsert", false).commit()
        val activity = instrumentation.startActivitySync(Intent(context, KeyboardSettingsActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        try {
            val laidOut = java.util.concurrent.CountDownLatch(1)
            val fixture = main {
                val fake = Fake(); val results = mutableListOf<(String) -> Unit>(); val inserted = mutableListOf<String>()
                val panel = VoicePanel(activity, { text ->
                    inserted.add(text)
                    insertResult?.invoke(text) ?: accept
                }, {}, { state, result, _ ->
                    fake.status = state; results.add(result); fake
                })
                Ui.applySystemInsets(panel.view)
                panel.view.addOnLayoutChangeListener { _, l, t, r, b, _, _, _, _ -> if (r > l && b > t) laidOut.countDown() }
                activity.setContentView(panel.view)
                Fixture(activity, panel, fake, results, inserted)
            }
            assertTrue(laidOut.await(5, java.util.concurrent.TimeUnit.SECONDS)); instrumentation.waitForIdleSync()
            test(fixture)
        } finally {
            main { activity.finish() }; instrumentation.waitForIdleSync()
            oldOptions.save(context); prefs.edit().putBoolean("voiceHoldToInsert", old).commit()
        }
    }
    @Test fun captureLimitTransitionsToProcessingAndRejectsLateStatus() = withPanel { f ->
        f.click("Start dictation")
        val callback = f.fake.status
        main { callback(CaptureStatus(CapturePhase.PROCESSING, "Microphone off")) }
        assertFalse(main { f.key("Transcribing locally…").isEnabled })
        assertEquals(0, main { f.fake.stopped }) // No manual Stop needed at the capture limit.
        main { callback(CaptureStatus(CapturePhase.RECORDING, "Late recording update")) }
        assertFalse(main { f.key("Transcribing locally…").isEnabled })
        main { f.results.single()("finished") }
        main { callback(CaptureStatus(CapturePhase.PROCESSING, "Late processing update")) }
        assertTrue(main { f.key("Insert text").isEnabled })
        f.click("Retake")
        main { callback(CaptureStatus(CapturePhase.PROCESSING, "Previous take")) }
        assertTrue(main { f.key("Stop & transcribe").isEnabled })
    }
    @Test fun utterlingStateLabelsTrackTheVoiceWorkflow() = withPanel { f ->
        assertTrue(f.hasText("Voice available")); f.capture("voice-available")
        f.click("Start dictation"); assertTrue(f.hasText("Listening")); f.capture("voice-listening")
        f.click("Stop & transcribe"); assertTrue(f.hasText("Processing locally")); f.capture("voice-processing")
        main { f.results.single()("draft") }; assertTrue(f.hasText("Transcript ready")); f.capture("voice-review")
        f.click("Fix transcript"); assertTrue(f.hasText("Editing transcript")); f.capture("voice-edit")
        f.click("Done editing"); assertTrue(f.hasText("Transcript ready"))
        f.click("Retake"); assertTrue(f.hasText("Listening"))
        f.click("Stop & transcribe"); main { f.results.last()(" ") }
        assertTrue(f.hasText("Needs attention")); f.capture("voice-problem")
    }
    @Test fun utterlingAvailableStateRemainsReadableOnOledBlack() =
        withPanel(theme = ThemeMode.OLED) { f ->
            val background = main { f.panel.view.background as android.graphics.drawable.ColorDrawable }
            assertEquals(android.graphics.Color.BLACK, background.color)
            assertTrue(f.hasText("Voice available")); f.capture("voice-oled-available")
        }
    @Test fun micEntryStartsOnceUnlessTheUserExplicitlyRetakes() = withPanel { f ->
        f.holdMode()
        main { f.panel.startFromMicTap(); f.panel.startFromMicTap() }
        assertEquals(1, main { f.fake.started })
        f.click("Stop & transcribe"); main { f.results.single()("review first") }
        assertTrue(f.inserted.isEmpty())
        f.click("Retake"); main { f.panel.startFromMicTap() }
        assertEquals(2, main { f.fake.started })
        main { (f.panel.view.parent as ViewGroup).removeView(f.panel.view); f.panel.startFromMicTap() }
        assertEquals(2, main { f.fake.started })
    }
    @Test fun primaryControlAndLocalEditingInsertExactlyOnce() = withPanel { f ->
        val primary = f.key("Start dictation"); f.click("Start dictation"); assertSame(primary, f.key("Stop & transcribe"))
        f.click("Stop & transcribe"); assertEquals(1, main { f.fake.stopped })
        main { f.results.single()("cat") }; assertSame(primary, f.key("Insert text"))
        f.click("Fix transcript"); f.click("s"); f.capture("voice-edit"); f.click("Done editing"); f.capture("voice-review")
        assertTrue(f.inserted.isEmpty())
        f.click("Insert text"); main { primary.performClick() }
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
        f.click("Start dictation"); f.click("Stop & transcribe")
        val transcript = (1..30).joinToString("\n") { "Line $it of the transcript." }
        main { f.results.single()(transcript) }
        val preview = main { descendants(f.panel.view).filterIsInstance<android.widget.EditText>().single() }
        val collapsed = main { preview.layoutParams.height }
        assertTrue(main { preview.isEnabled && preview.keyListener == null && preview.isTextSelectable })
        assertEquals(View.GONE, main { descendants(f.panel.view).filterIsInstance<CheckBox>().single().visibility })
        f.click("Expand transcript")
        assertTrue(main { preview.layoutParams.height > collapsed })
        assertEquals(transcript, main { preview.text.toString() })
        f.click("Fix transcript")
        assertEquals(collapsed, main { preview.layoutParams.height })
        assertNotNull(main { preview.keyListener })
        main { preview.setSelection(preview.length()) }
        f.click("s"); f.click("Done editing"); f.click("Insert text")
        assertEquals(listOf(transcript + "s"), f.inserted)
    }
    @Test fun shortTapDoesNotCaptureAndExtraFingerCancelsHold() = withPanel { f ->
        f.holdMode(); val primary = f.key("Hold to dictate")
        f.touch(primary, MotionEvent.ACTION_DOWN); f.touch(primary, MotionEvent.ACTION_UP)
        UiAwait.remains("Short tap must not start capture") { f.fake.started == 0 }
        val held = f.hold(); f.extraFinger(held); f.touch(held, MotionEvent.ACTION_UP)
        main { f.results.single()("cancelled") }
        assertTrue(f.inserted.isEmpty()); assertEquals(1, main { f.fake.cancelled })
    }
    @Test fun unconfirmedManualInsertLocksTheTakeButKeepsSelectableRecovery() {
        var accept = false
        withPanel(insertResult = { accept }) { f ->
            f.click("Start dictation"); f.click("Stop & transcribe")
            main { f.results.single()("original") }
            val primary = f.key("Insert text")
            val preview = main { descendants(f.panel.view).filterIsInstance<android.widget.EditText>().single() }
            f.click("Insert text")
            assertEquals(listOf("original"), f.inserted)
            assertSame(primary, f.key("Insert unavailable"))
            assertFalse(main { primary.isEnabled })
            assertTrue(f.hasText("Insertion unconfirmed. Check the field; select the transcript to copy."))
            assertTrue(main { preview.isEnabled && preview.keyListener == null && preview.isTextSelectable })

            main { primary.performClick(); primary.performClick() }
            f.click("Fix transcript")
            assertTrue(f.hasText("Insertion unconfirmed. Check the field; select the transcript to copy."))
            f.click("."); f.click("Done editing")
            assertEquals("original.", main { preview.text.toString() })
            assertFalse(main { f.key("Insert unavailable").isEnabled })
            assertTrue(f.hasText("Insertion unconfirmed. Check the field; select the transcript to copy."))
            assertEquals(listOf("original"), f.inserted)
            main { f.key("Keep reviewing").performClick() }
            assertTrue(f.hasText("Insertion unconfirmed. Check the field; select the transcript to copy."))

            f.click("Fix transcript")
            main { preview.setText("original"); preview.setSelection(preview.length()) }
            f.click("Done editing")
            main { primary.performClick() }
            assertTrue(f.hasText("Insertion unconfirmed. Check the field; select the transcript to copy."))
            assertEquals(listOf("original"), f.inserted)

            accept = true
            f.click("Retake"); assertEquals(2, main { f.fake.started })
            f.click("Stop & transcribe"); main { f.results.last()("fresh take") }
            f.click("Insert text")
            assertEquals(listOf("original", "fresh take"), f.inserted)
            assertTrue(f.hasText("Inserted · microphone off"))
        }
    }

    @Test fun unconfirmedHeldInsertRejectsReentryAndClearAllowsANewTake() {
        var accept = false
        var reentered = false
        var reenter: (() -> Unit)? = null
        withPanel(insertResult = {
            if (!reentered) { reentered = true; reenter?.invoke() }
            accept
        }) { f ->
            val primary = f.hold()
            reenter = { main { primary.performClick() } }
            main { f.results.single()("held take") }
            f.touch(primary, MotionEvent.ACTION_UP)
            assertEquals(listOf("held take"), f.inserted)
            assertFalse(main { f.key("Insert unavailable").isEnabled })
            main { primary.performClick(); primary.performClick() }
            assertEquals(listOf("held take"), f.inserted)

            main {
                f.panel.clear()
                descendants(f.panel.view).filterIsInstance<CheckBox>().single().isChecked = false
            }
            accept = true
            f.click("Start dictation"); f.click("Stop & transcribe")
            main { f.results.last()("fresh after clear") }
            f.click("Insert text")
            assertEquals(listOf("held take", "fresh after clear"), f.inserted)
        }
    }

    @Test fun throwingInsertLocksTheTakeWithoutEscapingOrRetrying() =
        withPanel(insertResult = { throw IllegalStateException("Synthetic closed connection") }) { f ->
            f.click("Start dictation"); f.click("Stop & transcribe")
            main { f.results.single()("uncertain") }
            val primary = f.key("Insert text")
            f.click("Insert text")
            assertEquals(listOf("uncertain"), f.inserted)
            assertSame(primary, f.key("Insert unavailable"))
            assertFalse(main { primary.isEnabled })
            assertTrue(f.hasText("Insertion unconfirmed. Check the field; select the transcript to copy."))
            main { primary.performClick() }
            assertEquals(listOf("uncertain"), f.inserted)
        }

    @Test fun modelSelectorSwitchesVerifiedPrivateSlotsAndRejectsBusyOrStaleChoices() {
        val activity = instrumentation.startActivitySync(Intent(instrumentation.targetContext, KeyboardSettingsActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        val directory = Files.createTempDirectory(activity.cacheDir.toPath(), "utterleaf-voice-models").toFile()
        try {
            instrumentation.context.assets.open("ggml-tiny.en.bin").use { ModelStore.install(it, directory) }
            instrumentation.context.assets.open("ggml-base.en.bin").use { ModelStore.install(it, directory) }
            assertTrue(ModelStore.select(directory, ModelStore.catalog.single { it.id == "tiny.en" }))
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
            val tinySpec = ModelStore.catalog.single { it.id == "tiny.en" }
            val baseSpec = ModelStore.catalog.single { it.id == "base.en" }
            val tinyPresentation = ModelPresentation.forSpec(tinySpec)
            val basePresentation = ModelPresentation.forSpec(baseSpec)
            val tinyLabel = "${tinyPresentation.summary(tinySpec)} · ${tinyPresentation.tradeoff}"
            val baseLabel = "${basePresentation.summary(baseSpec)} · ${basePresentation.tradeoff}"
            main {
                button("Voice options").performClick()
                button("Model · Compact English").performClick()
                val visible = descendants(panel.view).filterIsInstance<Button>().filter { it.visibility == View.VISIBLE }
                assertFalse(visible.any { it.text.contains("tiny.en") || it.text.contains("base.en") })
            }
            val baseChoice = button(baseLabel)
            main { assertTrue(WorkLease.acquire()) }
            try { main { baseChoice.performClick() } }
            finally { main { WorkLease.release() } }
            assertEquals("tiny.en", ModelStore.installed(directory)?.id)
            main { baseChoice.performClick() }
            assertEquals("tiny.en", ModelStore.installed(directory)?.id)
            main { button("Model · Compact English").performClick(); button(baseLabel).performClick() }
            assertEquals("base.en", ModelStore.installed(directory)?.id)

            main { button("Model · Medium English").performClick() }
            val staleChoice = button(tinyLabel)
            main {
                descendants(panel.view).filterIsInstance<TextView>().forEach { label ->
                    label.setTextSize(TypedValue.COMPLEX_UNIT_PX, label.textSize * 1.5f)
                }
                val width = Ui.dp(wrapper, 320)
                panel.view.measure(
                    View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                    View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED),
                )
                panel.view.layout(0, 0, width, panel.view.measuredHeight)
                listOf(button(tinyLabel), button(baseLabel)).forEach { option ->
                    val textLayout = checkNotNull(option.layout) { "Model option text was not laid out" }
                    assertEquals(option.text.length, textLayout.getLineEnd(textLayout.lineCount - 1))
                    assertTrue((0 until textLayout.lineCount).all { textLayout.getEllipsisCount(it) == 0 })
                    assertTrue(option.height >= textLayout.height + option.compoundPaddingTop + option.compoundPaddingBottom)
                }
                descendants(panel.view).filter { it.isShown && it.isClickable }.forEach { action ->
                    assertTrue("Visible action has no touch area", action.width > 0 && action.height > 0)
                    val bounds = Rect(0, 0, action.width, action.height)
                    panel.view.offsetDescendantRectToMyCoords(action, bounds)
                    assertTrue("Action extends left of the voice panel", bounds.left >= 0)
                    assertTrue("Action extends right of the voice panel", bounds.right <= panel.view.width)
                    assertTrue("Action extends above the voice panel", bounds.top >= 0)
                    assertTrue("Action extends below the voice panel", bounds.bottom <= panel.view.height)
                }
                // VoiceIme returns this raw panel instead of KeyboardIme's ScrollView wrapper.
                assertTrue("Large-text model choices exceed the standalone voice screen",
                    panel.view.height <= activity.resources.displayMetrics.heightPixels)
                assertEquals("Geometry measurement started capture", 0, fake.started)
            }
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
