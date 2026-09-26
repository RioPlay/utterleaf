package org.utterleaf.voice

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Rect
import android.os.Build
import android.os.Debug
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import android.provider.Settings
import android.text.Editable
import android.text.TextWatcher
import android.view.FrameMetrics
import android.view.InputDevice
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.ViewTreeObserver
import android.view.Window
import android.view.WindowInsets
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnectionWrapper
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.filters.SdkSuppress
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Opt-in API-35 emulator baseline. Durations use only elapsedRealtimeNanos
 * boundaries on the device. First-draw values are proxies, not display
 * presentation timing or evidence about physical-phone responsiveness.
 */
@RunWith(AndroidJUnit4::class)
@SdkSuppress(minSdkVersion = 31)
@PerformanceMeasurement
class KeyboardPerformanceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext
    private val recorder = PerformanceRecorder()

    private val warmups = 5
    private val cheapSamples = 30
    private val decodeWarmups = 0
    private val decodeSamples = 5
    private val sustainedKeys = 200
    private val feedbackHoldSafetyMillis = 200L

    private fun <T> main(block: () -> T): T {
        val value = AtomicReference<T>()
        instrumentation.runOnMainSync { value.set(block()) }
        return value.get()
    }

    private fun await(message: String, timeoutMillis: Long = 10_000, condition: () -> Boolean) {
        val deadline = SystemClock.elapsedRealtime() + timeoutMillis
        while (SystemClock.elapsedRealtime() < deadline) {
            if (condition()) return
            SystemClock.sleep(25)
        }
        throw AssertionError(message)
    }

    private fun shell(command: String): String = android.os.ParcelFileDescriptor.AutoCloseInputStream(
        instrumentation.uiAutomation.executeShellCommand(command),
    ).bufferedReader().use { it.readText() }

    private fun descendants(view: View): List<View> = listOf(view) + if (view is ViewGroup) {
        (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) }
    } else emptyList()

    private fun button(root: View, description: String): Button = main {
        descendants(root).filterIsInstance<Button>().single {
            it.isShown && it.contentDescription?.toString() == description
        }
    }

    private fun hasButton(root: View, description: String): Boolean =
        descendants(root).filterIsInstance<Button>().any {
            it.isShown && it.contentDescription?.toString() == description
        }

    private fun liveButton(description: String): Button = main {
        android.view.inspector.WindowInspector.getGlobalWindowViews().flatMap(::descendants)
            .filterIsInstance<Button>().single {
                it.isShown && it.contentDescription?.toString() == description
            }
    }

    private inner class DrawProbe(
        private val root: View,
        private val ready: () -> Boolean,
    ) : AutoCloseable {
        private val start = AtomicLong(0)
        private val end = AtomicLong(0)
        private val observed = CountDownLatch(1)
        private val listener = ViewTreeObserver.OnDrawListener {
            val began = start.get()
            if (began != 0L && ready() && end.compareAndSet(0, SystemClock.elapsedRealtimeNanos())) {
                observed.countDown()
            }
        }

        fun arm() = main {
            check(root.viewTreeObserver.isAlive) { "Draw observer is not alive" }
            root.viewTreeObserver.addOnDrawListener(listener)
        }

        fun begin(): Long = SystemClock.elapsedRealtimeNanos().also { start.set(it) }

        fun finish(message: String, timeoutMillis: Long = 10_000): Pair<Long, Long> {
            assertTrue(message, observed.await(timeoutMillis, TimeUnit.MILLISECONDS))
            val began = start.get()
            val finished = end.get()
            check(began > 0L && finished >= began) { "$message produced invalid timestamps" }
            close()
            return began to finished
        }

        override fun close() {
            main {
                val observer = root.viewTreeObserver
                if (observer.isAlive) observer.removeOnDrawListener(listener)
            }
        }
    }

    private data class Touch(val x: Float, val y: Float, val downTime: Long)

    private fun touch(button: Button): Touch = main {
        check(button.isShown && button.width > 0 && button.height > 0) { "Button is not touchable" }
        val location = IntArray(2)
        button.getLocationOnScreen(location)
        Touch(
            location[0] + button.width / 2f,
            location[1] + button.height / 2f,
            SystemClock.uptimeMillis(),
        )
    }

    private fun inject(target: Touch, action: Int) {
        val event = MotionEvent.obtain(
            target.downTime,
            maxOf(target.downTime, SystemClock.uptimeMillis()),
            action,
            target.x,
            target.y,
            0,
        ).apply { source = InputDevice.SOURCE_TOUCHSCREEN }
        try {
            check(instrumentation.uiAutomation.injectInputEvent(event, true)) {
                "The emulator rejected a synthetic touch event"
            }
        } finally {
            event.recycle()
        }
    }

    private fun tap(button: Button) {
        val target = touch(button)
        inject(target, MotionEvent.ACTION_DOWN)
        inject(target, MotionEvent.ACTION_UP)
    }

    private fun tapUpToFirstDraw(
        button: Button,
        root: View,
        message: String,
        ready: () -> Boolean,
    ): Pair<Long, Long> {
        val target = touch(button)
        inject(target, MotionEvent.ACTION_DOWN)
        val probe = DrawProbe(root, ready)
        probe.arm()
        return try {
            probe.begin()
            inject(target, MotionEvent.ACTION_UP)
            probe.finish(message)
        } catch (failure: Throwable) {
            probe.close()
            runCatching { inject(target, MotionEvent.ACTION_CANCEL) }
            throw failure
        }
    }

    private fun imeVisible(activity: Activity): Boolean = main {
        activity.window.decorView.rootWindowInsets?.isVisible(WindowInsets.Type.ime()) == true
    }

    private data class SettledGeometry(val bounds: Rect, val imeBottom: Int, val imeVisible: Boolean)

    /**
     * Wait for three identical rendered frames. This is an unmeasured setup
     * barrier: first-draw can occur while Android is still animating the IME
     * window, when global touch coordinates are not stable yet.
     */
    private fun awaitSettledGeometry(target: View, activity: Activity? = null, requireIme: Boolean = false) {
        val root = target.rootView
        val settled = CountDownLatch(1)
        var previous: SettledGeometry? = null
        var stableFrames = 0
        val listener = ViewTreeObserver.OnPreDrawListener {
            val bounds = Rect()
            val insets = activity?.window?.decorView?.rootWindowInsets
            val visible = insets?.isVisible(WindowInsets.Type.ime()) == true
            val bottom = insets?.getInsets(WindowInsets.Type.ime())?.bottom ?: 0
            val current = if (target.isAttachedToWindow && target.isShown &&
                target.getGlobalVisibleRect(bounds) && bounds.width() > 0 && bounds.height() > 0 &&
                !target.isLayoutRequested && !root.isLayoutRequested && (!requireIme || visible)
            ) SettledGeometry(Rect(bounds), bottom, visible) else null
            stableFrames = when {
                current == null -> 0
                current == previous -> stableFrames + 1
                else -> 1
            }
            previous = current
            if (stableFrames >= 3) settled.countDown() else root.postInvalidateOnAnimation()
            true
        }
        main {
            check(root.viewTreeObserver.isAlive)
            root.viewTreeObserver.addOnPreDrawListener(listener)
            root.postInvalidateOnAnimation()
        }
        try {
            assertTrue("Interactive surface geometry did not settle", settled.await(5, TimeUnit.SECONDS))
        } finally {
            main {
                val observer = root.viewTreeObserver
                if (observer.isAlive) observer.removeOnPreDrawListener(listener)
            }
        }
    }

    private fun showToFirstDraw(
        activity: KeyboardEditorContractActivity,
        manager: InputMethodManager,
        message: String,
    ): Pair<Long, Long> {
        val decor = activity.window.decorView
        val probe = DrawProbe(decor) {
            decor.rootWindowInsets?.isVisible(WindowInsets.Type.ime()) == true
        }
        probe.arm()
        return try {
            main {
                probe.begin()
                manager.showSoftInput(activity.editor, InputMethodManager.SHOW_IMPLICIT)
            }
            probe.finish(message)
        } catch (failure: Throwable) {
            probe.close()
            throw failure
        }
    }

    private fun hideKeyboard(activity: KeyboardEditorContractActivity, manager: InputMethodManager) {
        main { manager.hideSoftInputFromWindow(activity.editor.windowToken, 0) }
        await("Keyboard did not hide between show samples") { !imeVisible(activity) }
        awaitSettledGeometry(activity.window.decorView, activity)
    }

    private fun launchHost(manager: InputMethodManager): KeyboardEditorContractActivity {
        val activity = instrumentation.startActivitySync(
            Intent(app, KeyboardEditorContractActivity::class.java)
                .putExtra("ime_options", EditorInfo.IME_ACTION_DONE)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        ) as KeyboardEditorContractActivity
        try {
            await("Performance editor did not acquire focus") { main { activity.hasWindowFocus() } }
            main { activity.editor.requestFocus() }
            await("Performance editor never became active") { main { manager.isActive(activity.editor) } }
            main { manager.restartInput(activity.editor) }
            if (imeVisible(activity)) hideKeyboard(activity, manager)
            return activity
        } catch (failure: Throwable) {
            main { activity.finish() }
            throw failure
        }
    }

    private fun measureKeyboardShow(
        activity: KeyboardEditorContractActivity,
        manager: InputMethodManager,
    ) {
        val first = showToFirstDraw(activity, manager, "Initial keyboard first draw was not observed")
        recorder.duration("keyboard_show_first_draw_proxy_first_ns", first.first, first.second)
        awaitSettledGeometry(liveButton("a"), activity, requireIme = true)
        repeat(warmups + cheapSamples) { iteration ->
            hideKeyboard(activity, manager)
            val measured = showToFirstDraw(activity, manager, "Warm keyboard first draw was not observed")
            awaitSettledGeometry(liveButton("a"), activity, requireIme = true)
            if (iteration >= warmups) {
                recorder.duration("keyboard_show_first_draw_proxy_warm_ns", measured.first, measured.second)
            }
        }
        await("Typing surface did not appear after show measurements") {
            runCatching { liveButton("a") }.isSuccess
        }
    }

    private fun measureKeyFeedbackAndCommit(activity: KeyboardEditorContractActivity) {
        main { activity.editor.setText(""); activity.editor.setSelection(0) }
        val expected = StringBuilder()
        repeat(warmups + cheapSamples) { iteration ->
            val letter = if (iteration % 2 == 0) "a" else "s"
            val expectedLength = main { activity.editor.length() + 1 }
            val commitEnd = AtomicLong(0)
            val committed = CountDownLatch(1)
            val watcher = object : TextWatcher {
                override fun beforeTextChanged(value: CharSequence?, start: Int, count: Int, after: Int) = Unit
                override fun onTextChanged(value: CharSequence?, start: Int, before: Int, count: Int) = Unit
                override fun afterTextChanged(value: Editable?) {
                    if (value?.length == expectedLength &&
                        commitEnd.compareAndSet(0, SystemClock.elapsedRealtimeNanos())) committed.countDown()
                }
            }
            main { activity.editor.addTextChangedListener(watcher) }
            val key = liveButton(letter)
            val target = touch(key)
            val feedback = DrawProbe(key.rootView) { key.isPressed }
            feedback.arm()
            var released = false
            try {
                val feedbackStart = feedback.begin()
                inject(target, MotionEvent.ACTION_DOWN)
                check(main { key.isPressed }) {
                    "Synthetic DOWN missed the settled key; cancelling before any hold action"
                }
                // Letter holds change the UI at 320 ms. A missing feedback
                // draw must cancel before that semantic boundary rather than
                // wait through the hold and contaminate later samples.
                val feedbackEnd = feedback.finish(
                    "Pressed-key feedback was not drawn before the hold-safety boundary",
                    feedbackHoldSafetyMillis,
                )
                check(feedbackEnd.first == feedbackStart)
                val commitStart = SystemClock.elapsedRealtimeNanos()
                inject(target, MotionEvent.ACTION_UP)
                released = true
                assertTrue("Key release did not commit text", committed.await(5, TimeUnit.SECONDS))
                expected.append(letter)
                if (iteration >= warmups) {
                    recorder.duration(
                        "key_press_feedback_first_draw_proxy_ns",
                        feedbackEnd.first,
                        feedbackEnd.second,
                    )
                    recorder.duration("key_text_commit_ns", commitStart, commitEnd.get())
                }
            } finally {
                if (!released) runCatching { inject(target, MotionEvent.ACTION_CANCEL) }
                feedback.close()
                main { activity.editor.removeTextChangedListener(watcher) }
            }
        }
        assertEquals("Synthetic key sequence changed or reordered", expected.toString(), main {
            activity.editor.text.toString()
        })
    }

    private fun measureSustainedTyping(activity: KeyboardEditorContractActivity) {
        main { activity.editor.setText(""); activity.editor.setSelection(0) }
        val service = liveButton("a").context as KeyboardIme
        val imeWindow = checkNotNull(service.window?.window) { "IME window was unavailable" }
        val frameThread = HandlerThread("utterleaf-performance-frames").apply { start() }
        val durations = mutableListOf<Long>()
        var overPeriod = 0L
        var callbackDrops = 0L
        val refreshRate = activity.display?.refreshRate?.takeIf { it > 0f } ?: 60f
        val refreshPeriod = (1_000_000_000.0 / refreshRate).toLong()
        val listener = Window.OnFrameMetricsAvailableListener { _, metrics, dropped ->
            val total = metrics.getMetric(FrameMetrics.TOTAL_DURATION)
            if (total > 0) synchronized(durations) {
                durations += total
                if (total > refreshPeriod) overPeriod++
                callbackDrops += dropped.toLong()
            }
        }
        main { imeWindow.addOnFrameMetricsAvailableListener(listener, Handler(frameThread.looper)) }
        try {
            val expected = StringBuilder(sustainedKeys)
            val eventTimes = mutableListOf<Long>()
            val cadenceStart = SystemClock.elapsedRealtimeNanos()
            repeat(sustainedKeys) { index ->
                val scheduled = cadenceStart + index * 100_000_000L
                while (true) {
                    val remaining = scheduled - SystemClock.elapsedRealtimeNanos()
                    if (remaining <= 0) break
                    SystemClock.sleep(maxOf(1L, remaining / 1_000_000L))
                }
                val letter = if (index % 2 == 0) "a" else "s"
                tap(liveButton(letter))
                expected.append(letter)
                eventTimes += SystemClock.elapsedRealtimeNanos()
            }
            await("Sustained typing did not commit every synthetic key") {
                main { activity.editor.text.toString() == expected.toString() }
            }
            eventTimes.zipWithNext().forEach { (before, after) ->
                recorder.duration("sustained_input_interval_ns", before, after)
            }
        } finally {
            main { imeWindow.removeOnFrameMetricsAvailableListener(listener) }
            frameThread.quitSafely()
            frameThread.join(5_000)
        }
        val captured = synchronized(durations) { durations.toList() }
        check(captured.isNotEmpty()) { "IME window produced no sustained frame metrics" }
        captured.forEach { recorder.value("sustained_frame_total_ns", it, "ns") }
        recorder.value("sustained_frames_over_refresh_period_count", overPeriod, "count")
        recorder.value("sustained_frame_callback_drops_count", callbackDrops, "count")
    }

    private fun measureSuggestionGeneration() {
        val work = SuggestionWork()
        val dictionary = app.resources.openRawResource(R.raw.wordlist_en).use { it.readBytes() }
        recorder.metadata("suggestion_dictionary_sha256", sha256(dictionary))
        recorder.metadata("suggestion_dictionary_size_bytes", dictionary.size)
        recorder.metadata(
            "suggestion_dictionary_word_count",
            dictionary.count { it == '\n'.code.toByte() } +
                if (dictionary.isNotEmpty() && dictionary.last() != '\n'.code.toByte()) 1 else 0,
        )
        dictionary.fill(0)
        // Load once outside every timed interval. The measured request still
        // traverses the real packaged engine and its production worker path.
        val engine = SuggestionRepository.load(app)
        val connection = object : InputConnectionWrapper(null, true) {
            override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence = "hel"
        }
        try {
            repeat(warmups + cheapSamples) { iteration ->
                val delivered = CountDownLatch(1)
                val end = AtomicLong(0)
                val failure = AtomicReference<Throwable?>()
                val start = SystemClock.elapsedRealtimeNanos()
                work.request(connection, iteration.toLong(), engine) { state ->
                    try {
                        check(state.composing == "hel" && state.candidates.isNotEmpty())
                        end.set(SystemClock.elapsedRealtimeNanos())
                    } catch (error: Throwable) {
                        failure.set(error)
                    } finally {
                        delivered.countDown()
                    }
                }
                assertTrue("Suggestion generation did not finish", delivered.await(5, TimeUnit.SECONDS))
                failure.get()?.let { throw it }
                if (iteration >= warmups) recorder.duration("suggestion_generation_ns", start, end.get())
            }
        } finally {
            work.close()
        }
    }

    private fun directTypingPanel(
        activity: Activity,
        options: KeyboardOptions,
        state: AtomicReference<SuggestionEngine.SuggestionState>,
    ): TypingPanel {
        val panel = main {
            TypingPanel(
                activity,
                options.copy(suggestions = true),
                { true }, {}, {}, {}, {}, {}, {},
                suggest = { state.get() },
                completeWord = { _, _ -> true },
            )
        }
        main {
            panel.reset(false, false, "Done")
            activity.setContentView(panel.view)
        }
        await("Direct typing panel did not lay out") { main { panel.view.isShown && panel.view.width > 0 } }
        return panel
    }

    private fun measureSuggestionRenderingAndTools(activity: Activity, options: KeyboardOptions) {
        val states = listOf(
            SuggestionEngine.SuggestionState("hel", listOf("hello", "help", "helmet")),
            SuggestionEngine.SuggestionState("wor", listOf("world", "work", "worry")),
        )
        val state = AtomicReference(states[0])
        val panel = directTypingPanel(activity, options, state)
        try {
            repeat(warmups + cheapSamples) { iteration ->
                val next = states[(iteration + 1) % states.size]
                val expected = "Complete with ${next.candidates.first()}"
                val probe = DrawProbe(panel.view) { hasButton(panel.view, expected) }
                probe.arm()
                val start = probe.begin()
                main { state.set(next); panel.refreshSuggestions() }
                val end = probe.finish("Suggestion row update was not drawn")
                check(end.first == start)
                if (iteration >= warmups) {
                    recorder.duration("suggestion_render_first_draw_proxy_ns", end.first, end.second)
                }
            }
            awaitSettledGeometry(button(panel.view, "Keyboard tools"))
            repeat(warmups + cheapSamples) { iteration ->
                val tools = button(panel.view, "Keyboard tools")
                val measured = tapUpToFirstDraw(
                    tools,
                    panel.view,
                    "Tools surface was not drawn",
                ) { hasButton(panel.view, "Close tools and settings") }
                if (iteration >= warmups) {
                    recorder.duration("tools_switch_first_draw_proxy_ns", measured.first, measured.second)
                }
                // Closing is setup for the next sample, not a measured user path.
                // Invoke its one callback directly so a rebuilt button's transient
                // global coordinates cannot contaminate or stall the open metric.
                val close = button(panel.view, "Close tools and settings")
                main { check(close.performClick()) { "Tools close callback was not installed" } }
                await("Typing surface did not return after Tools") { main { hasButton(panel.view, "Keyboard tools") } }
                awaitSettledGeometry(button(panel.view, "Keyboard tools"))
            }
        } finally {
            main { panel.dispose() }
        }
    }

    private fun awaitLeaseReleased() {
        await("Voice capture did not release its work lease") {
            if (WorkLease.acquire()) {
                WorkLease.release()
                true
            } else false
        }
    }

    private fun measureVoiceStartup(activity: Activity, modelContext: Context) {
        repeat(warmups + cheapSamples) { iteration ->
            val listening = CountDownLatch(1)
            val end = AtomicLong(0)
            val failure = AtomicReference<String?>()
            val panel = main {
                VoicePanel(activity, { false }, {}, { state, result, error ->
                    VoiceSession(
                        modelContext,
                        { update ->
                            state(update)
                            if (update.phase == CapturePhase.RECORDING && update.message.startsWith("Listening") &&
                                end.compareAndSet(0, SystemClock.elapsedRealtimeNanos())) listening.countDown()
                        },
                        { bytes -> failure.compareAndSet(null, "Capture unexpectedly produced ${bytes.length} characters"); result(bytes) },
                        { message -> failure.compareAndSet(null, message); error(message); listening.countDown() },
                    )
                })
            }
            main { activity.setContentView(panel.view) }
            await("Voice panel did not lay out") {
                runCatching { button(panel.view, "Start dictation").width > 0 }.getOrDefault(false)
            }
            val startButton = button(panel.view, "Start dictation")
            val target = touch(startButton)
            try {
                inject(target, MotionEvent.ACTION_DOWN)
                val start = SystemClock.elapsedRealtimeNanos()
                inject(target, MotionEvent.ACTION_UP)
                assertTrue("AudioRecord did not reach its real listening callback", listening.await(10, TimeUnit.SECONDS))
                check(failure.get() == null) { failure.get() ?: "Voice startup failed" }
                check(end.get() >= start) { "Voice startup callback timestamp was missing" }
                if (iteration >= warmups) recorder.duration("voice_capture_start_ns", start, end.get())
            } finally {
                main {
                    panel.clear()
                    activity.setContentView(FrameLayout(activity))
                }
                awaitLeaseReleased()
            }
        }
    }

    private fun parseWav(bytes: ByteArray): FloatArray {
        check(bytes.size >= 44 && String(bytes, 0, 4, Charsets.US_ASCII) == "RIFF")
        val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        var offset = 12
        while (offset + 8 <= bytes.size) {
            val type = String(bytes, offset, 4, Charsets.US_ASCII)
            val size = buffer.getInt(offset + 4)
            check(size >= 0 && offset + 8L + size <= bytes.size.toLong()) { "Invalid WAV chunk" }
            if (type == "fmt ") {
                check(buffer.getShort(offset + 8).toInt() == 1)
                check(buffer.getInt(offset + 12) == 16_000)
            } else if (type == "data") {
                return FloatArray(size / 2) { index ->
                    buffer.getShort(offset + 8 + index * 2) / 32768f
                }
            }
            offset += 8 + size + (size % 2)
        }
        error("WAV fixture did not contain PCM data")
    }

    private fun measureVoiceProcessing(modelPath: String, audio: FloatArray) {
        fun decode(verify: Boolean): Pair<Long, Long> {
            val start = SystemClock.elapsedRealtimeNanos()
            NativeEngine.reset()
            val bytes = NativeEngine.decode(modelPath, audio)
            val end = SystemClock.elapsedRealtimeNanos()
            assertNotNull("Known speech did not produce a result", bytes)
            try {
                if (verify) {
                    check(bytes!!.toString(Charsets.UTF_8).lowercase(Locale.US).contains("country")) {
                        "Known speech result did not contain the expected fixture word"
                    }
                }
            } finally {
                bytes?.fill(0)
            }
            return start to end
        }
        val sampling = AtomicBoolean(true)
        val sampler = Thread({
            while (sampling.get()) {
                val info = Debug.MemoryInfo()
                Debug.getMemoryInfo(info)
                recorder.value("memory_decode_total_pss_kb", info.totalPss.toLong(), "kb")
                SystemClock.sleep(100)
            }
        }, "utterleaf-performance-memory").apply { start() }
        try {
            val first = decode(true)
            recorder.duration("voice_processing_first_decode_ns", first.first, first.second)
            repeat(decodeSamples) {
                val measured = decode(true)
                recorder.duration("voice_processing_followup_decode_ns", measured.first, measured.second)
            }
        } finally {
            sampling.set(false)
            sampler.join(5_000)
        }
    }

    private fun measureVoiceInsertion(activity: Activity) {
        val target = main { EditText(activity) }
        repeat(warmups + cheapSamples) { iteration ->
            main { target.setText("") }
            val inserts = AtomicInteger(0)
            val panel = main {
                VoicePanel(activity, { value ->
                    inserts.incrementAndGet()
                    target.append(value)
                    true
                }, {}, { _, result, _ ->
                    object : CaptureSession {
                        override fun start() = result("synthetic result")
                        override fun stop() = Unit
                        override fun cancel() = Unit
                    }
                })
            }
            main { activity.setContentView(panel.view) }
            await("Insertion voice panel did not lay out") { main { panel.view.isShown && panel.view.width > 0 } }
            main { panel.startFromMicTap() }
            await("Synthetic result did not reach review") {
                runCatching { button(panel.view, "Insert text") }.isSuccess
            }
            val inserted = CountDownLatch(1)
            val end = AtomicLong(0)
            val watcher = object : TextWatcher {
                override fun beforeTextChanged(value: CharSequence?, start: Int, count: Int, after: Int) = Unit
                override fun onTextChanged(value: CharSequence?, start: Int, before: Int, count: Int) = Unit
                override fun afterTextChanged(value: Editable?) {
                    if (!value.isNullOrEmpty() && end.compareAndSet(0, SystemClock.elapsedRealtimeNanos())) {
                        inserted.countDown()
                    }
                }
            }
            main { target.addTextChangedListener(watcher) }
            try {
                val insert = button(panel.view, "Insert text")
                val touch = touch(insert)
                inject(touch, MotionEvent.ACTION_DOWN)
                val start = SystemClock.elapsedRealtimeNanos()
                inject(touch, MotionEvent.ACTION_UP)
                assertTrue("Voice result was not inserted", inserted.await(5, TimeUnit.SECONDS))
                assertEquals("Voice result inserted more than once", 1, inserts.get())
                if (iteration >= warmups) {
                    recorder.duration("voice_result_local_callback_insert_ns", start, end.get())
                }
            } finally {
                main {
                    target.removeTextChangedListener(watcher)
                    panel.clear()
                    activity.setContentView(FrameLayout(activity))
                }
            }
        }
    }

    private fun recordMemory(checkpoint: String) {
        val info = Debug.MemoryInfo()
        Debug.getMemoryInfo(info)
        recorder.value("memory_${checkpoint}_total_pss_kb", info.totalPss.toLong(), "kb")
        recorder.value(
            "memory_${checkpoint}_java_heap_kb",
            (Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory()) / 1024,
            "kb",
        )
        recorder.value(
            "memory_${checkpoint}_native_heap_kb",
            Debug.getNativeHeapAllocatedSize() / 1024,
            "kb",
        )
    }

    private fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(bytes).joinToString("") { "%02x".format(it) }

    private fun recordMetadata(
        activity: Activity,
        model: ModelStore.Spec,
        audioSha256: String,
        microphoneMode: String,
        keyboardOptions: KeyboardOptions,
    ) {
        val packageInfo = app.packageManager.getPackageInfo(app.packageName, 0)
        val metrics = activity.resources.displayMetrics
        recorder.metadata("package_name", app.packageName)
        recorder.metadata("version_name", packageInfo.versionName ?: "")
        recorder.metadata("version_code", packageInfo.longVersionCode)
        recorder.metadata("build_fingerprint", Build.FINGERPRINT)
        recorder.metadata("device_model", Build.MODEL)
        recorder.metadata("api_level", Build.VERSION.SDK_INT)
        recorder.metadata("supported_abis", Build.SUPPORTED_ABIS.toList())
        recorder.metadata("display_pixels", "${metrics.widthPixels}x${metrics.heightPixels}")
        recorder.metadata("density_dpi", metrics.densityDpi)
        recorder.metadata(
            "orientation",
            if (activity.resources.configuration.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE)
                "landscape" else "portrait",
        )
        recorder.metadata("refresh_rate_hz", activity.display?.refreshRate ?: 0f)
        recorder.metadata("locale", Locale.getDefault().toLanguageTag())
        recorder.metadata("model_id", model.id)
        recorder.metadata("model_sha256", model.sha256)
        recorder.metadata("model_size_bytes", model.size)
        recorder.metadata("audio_fixture_sha256", audioSha256)
        recorder.metadata("microphone_access_mode", microphoneMode)
        recorder.metadata("keyboard_options_canonical", keyboardOptions.toString())
        recorder.metadata("voice_hold_to_insert", false)
        recorder.metadata("emulator_only", true)
        recorder.metadata("physical_phone_evidence", false)
        recorder.metadata("first_draw_is_presentation_timing", false)
        recorder.metadata("warmup_count", warmups)
        recorder.metadata("cheap_sample_count", cheapSamples)
        recorder.metadata("decode_warmup_count", decodeWarmups)
        recorder.metadata("decode_first_sample_count", 1)
        recorder.metadata("decode_sample_count", decodeSamples)
        recorder.metadata("sustained_key_count", sustainedKeys)
        recorder.metadata("sustained_target_hz", 10)
        recorder.metadata("feedback_hold_safety_millis", feedbackHoldSafetyMillis)
        recorder.metadata(
            "decode_order_scope",
            "Each decode initializes the native model; first/followup distinguish run order and cache state only",
        )
        recorder.metadata(
            "voice_insert_scope",
            "VoicePanel callback to a local unattached EditText; excludes host InputConnection delivery",
        )
    }

    private fun deleteOwnedFixture(root: File, container: File) {
        val canonicalRoot = root.canonicalFile
        val canonicalContainer = container.canonicalFile
        check(canonicalRoot.parentFile == canonicalContainer && canonicalRoot.name == recorder.runId) {
            "Refusing to delete an unowned performance fixture"
        }
        if (canonicalRoot.exists()) check(canonicalRoot.deleteRecursively()) {
            "Could not remove the owned performance fixture"
        }
    }

    @Test
    fun recordApi35EmulatorBaseline() {
        check(Build.VERSION.SDK_INT == 35) { "Baseline contract requires the API 35 emulator" }
        val emulator = Build.FINGERPRINT.contains("generic", ignoreCase = true) ||
            Build.MODEL.contains("emulator", ignoreCase = true) ||
            Build.HARDWARE.contains("ranchu", ignoreCase = true) ||
            Build.HARDWARE.contains("goldfish", ignoreCase = true)
        check(emulator) { "Voice performance evidence is emulator-only; never run this fixture on a phone" }

        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        val keyboardId = manager.inputMethodList.single { it.serviceName == KeyboardIme::class.java.name }.id
        val previousKeyboard = Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
            ?.takeIf { it.isNotBlank() } ?: error("A restorable default IME is required")
        val wasEnabled = manager.enabledInputMethodList.any { it.id == keyboardId }
        val previousOptions = KeyboardOptions.load(app)
        val preferences = app.getSharedPreferences("keyboard", Context.MODE_PRIVATE)
        val heldPreferenceExisted = preferences.contains("voiceHoldToInsert")
        val previousHeldPreference = preferences.getBoolean("voiceHoldToInsert", false)
        val deterministicOptions = KeyboardOptions(
            haptics = false,
            repeatGuard = false,
            suggestions = false,
            autoCapitalize = false,
        )
        val packageHadMicrophone = app.checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED
        var adoptedMicrophone = false
        var activity: KeyboardEditorContractActivity? = null
        val fixtureContainer = File(app.cacheDir, "performance-fixtures")
        val fixtureRoot = File(fixtureContainer, recorder.runId)
        val modelContext = object : ContextWrapper(app) {
            override fun getNoBackupFilesDir(): File = fixtureRoot
        }
        var audio = FloatArray(0)
        var measurementFailure: Throwable? = null
        try {
            shell("ime enable $keyboardId")
            shell("ime set $keyboardId")
            ImeTestReadiness.awaitDefaultImeStable(app, manager, keyboardId, "Performance IME setup")
            deterministicOptions.save(app)
            preferences.edit().putBoolean("voiceHoldToInsert", false).commit()
            await("Deterministic keyboard options did not persist") {
                KeyboardOptions.load(app) == deterministicOptions
            }

            if (!packageHadMicrophone) {
                instrumentation.uiAutomation.adoptShellPermissionIdentity(Manifest.permission.RECORD_AUDIO)
                adoptedMicrophone = true
                check(app.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                    "Temporary microphone identity was not adopted; package grant state was left unchanged"
                }
            }

            check(fixtureContainer.mkdirs() || fixtureContainer.isDirectory)
            check(fixtureRoot.mkdir()) { "Could not create isolated performance model directory" }
            val assets = instrumentation.context.assets
            val model = assets.open("ggml-tiny.en.bin").use { input ->
                ModelStore.install(input, fixtureRoot, ModelStore.catalog.single { it.id == "tiny.en" })
            }
            val wav = assets.open("jfk.wav").use { it.readBytes() }
            val audioHash = sha256(wav)
            audio = parseWav(wav)
            wav.fill(0)

            val host = launchHost(manager)
            activity = host
            recordMetadata(
                host,
                model,
                audioHash,
                if (packageHadMicrophone) "existing_package_grant" else "temporary_shell_identity",
                deterministicOptions,
            )
            measureKeyboardShow(host, manager)
            recordMemory("idle")
            measureKeyFeedbackAndCommit(host)
            measureSustainedTyping(host)
            recordMemory("after_typing")
            hideKeyboard(host, manager)
            measureSuggestionGeneration()
            measureSuggestionRenderingAndTools(host, deterministicOptions)
            measureVoiceStartup(host, modelContext)
            measureVoiceProcessing(requireNotNull(ModelStore.verifiedFile(fixtureRoot)).absolutePath, audio)
            measureVoiceInsertion(host)
            recordMemory("after_voice")
        } catch (failure: Throwable) {
            measurementFailure = failure
            throw failure
        } finally {
            var cleanupFailure: Throwable? = null
            var cleanupCompleted = true
            fun clean(step: () -> Unit) {
                try {
                    step()
                } catch (error: Throwable) {
                    cleanupCompleted = false
                    if (measurementFailure != null) {
                        if (error !== measurementFailure) measurementFailure!!.addSuppressed(error)
                    } else if (cleanupFailure == null) {
                        cleanupFailure = error
                    } else if (error !== cleanupFailure) {
                        cleanupFailure!!.addSuppressed(error)
                    }
                }
            }
            clean {
                main { activity?.finish() }
                instrumentation.waitForIdleSync()
            }
            clean { NativeEngine.reset(); NativeEngine.cancel() }
            clean { audio.fill(0f) }
            clean { deleteOwnedFixture(fixtureRoot, fixtureContainer) }
            clean {
                previousOptions.save(app)
                if (heldPreferenceExisted) {
                    check(preferences.edit().putBoolean("voiceHoldToInsert", previousHeldPreference).commit())
                } else {
                    check(preferences.edit().remove("voiceHoldToInsert").commit())
                }
                await("Keyboard preferences were not restored") {
                    KeyboardOptions.load(app) == previousOptions &&
                        preferences.contains("voiceHoldToInsert") == heldPreferenceExisted &&
                        (!heldPreferenceExisted ||
                            preferences.getBoolean("voiceHoldToInsert", false) == previousHeldPreference)
                }
            }
            clean {
                shell("ime set $previousKeyboard")
                ImeTestReadiness.awaitDefaultImeStable(
                    app,
                    manager,
                    previousKeyboard,
                    "Previous IME restore after performance fixture",
                )
            }
            clean { if (!wasEnabled) shell("ime disable $keyboardId") }
            clean { if (adoptedMicrophone) instrumentation.uiAutomation.dropShellPermissionIdentity() }
            recorder.metadata("measurement_body_completed", measurementFailure == null)
            recorder.metadata("cleanup_completed", cleanupCompleted)
            try {
                recorder.flush()
            } catch (error: Throwable) {
                if (measurementFailure != null) measurementFailure!!.addSuppressed(error)
                else if (cleanupFailure == null) cleanupFailure = error
                else cleanupFailure!!.addSuppressed(error)
            }
            if (measurementFailure == null) cleanupFailure?.let { throw it }
        }
    }
}
