package org.utterleaf.voice

import android.content.Intent
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
            Thread.sleep(android.view.ViewConfiguration.getLongPressTimeout().toLong() + 100)
            instrumentation.waitForIdleSync(); assertEquals(1, main { fake.started }); return button
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
                val panel = VoicePanel(activity, { inserted.add(it); accept }, {}, { _, result, _ -> results.add(result); fake })
                panel.view.addOnLayoutChangeListener { _, l, t, r, b, _, _, _, _ -> if (r > l && b > t) laidOut.countDown() }
                activity.setContentView(panel.view)
                Fixture(activity, panel, fake, results, inserted)
            }
            assertTrue(laidOut.await(5, java.util.concurrent.TimeUnit.SECONDS)); instrumentation.waitForIdleSync()
            test(fixture)
        } finally { main { activity.finish() }; instrumentation.waitForIdleSync(); prefs.edit().putBoolean("voiceHoldToInsert", old).commit() }
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
    @Test fun shortTapDoesNotCaptureAndExtraFingerCancelsHold() = withPanel { f ->
        f.holdMode(); val primary = f.key("Hold to speak")
        f.touch(primary, MotionEvent.ACTION_DOWN); f.touch(primary, MotionEvent.ACTION_UP)
        Thread.sleep(android.view.ViewConfiguration.getLongPressTimeout().toLong() + 100)
        assertEquals(0, main { f.fake.started })
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
}
