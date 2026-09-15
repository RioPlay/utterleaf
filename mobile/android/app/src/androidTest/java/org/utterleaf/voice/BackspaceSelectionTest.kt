package org.utterleaf.voice

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.os.SystemClock
import android.provider.Settings
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.FrameLayout
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.lang.reflect.Proxy

@RunWith(AndroidJUnit4::class)
class BackspaceSelectionTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext
    private fun <T> main(block: () -> T): T {
        val result = java.util.concurrent.atomic.AtomicReference<T>()
        instrumentation.runOnMainSync { result.set(block()) }
        return result.get()
    }
    private fun shell(command: String) = android.os.ParcelFileDescriptor.AutoCloseInputStream(
        instrumentation.uiAutomation.executeShellCommand(command)).bufferedReader().use { it.readText() }
    private fun await(message: String, condition: () -> Boolean) {
        val deadline = SystemClock.elapsedRealtime() + 5_000
        while (SystemClock.elapsedRealtime() < deadline) { if (condition()) return; Thread.sleep(25) }
        throw AssertionError(message)
    }
    private fun key(label: String): AccessibilityNodeInfo? {
        fun find(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
            if (node.contentDescription?.toString() == label && node.isClickable) return node
            for (i in 0 until node.childCount) node.getChild(i)?.let(::find)?.let { return it }
            return null
        }
        return instrumentation.uiAutomation.windows.asSequence().filter { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD }
            .mapNotNull { it.root?.let(::find) }.firstOrNull()
    }
    private fun press(label: String) {
        await("Missing $label") { key(label)?.isEnabled == true }
        val deadline = SystemClock.elapsedRealtime() + 2_000
        while (SystemClock.elapsedRealtime() < deadline) {
            if (key(label)?.performAction(AccessibilityNodeInfo.ACTION_CLICK) == true) {
                instrumentation.waitForIdleSync()
                return
            }
            Thread.sleep(50)
        }
        throw AssertionError("Could not press $label")
    }
    private fun withKeyboard(block: () -> Unit) {
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        val id = manager.inputMethodList.single { it.serviceName == KeyboardIme::class.java.name }.id
        val previous = Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
        val enabled = manager.enabledInputMethodList.any { it.id == id }; val options = KeyboardOptions.load(app)
        val flags = instrumentation.uiAutomation.serviceInfo.flags
        try {
            instrumentation.uiAutomation.serviceInfo = instrumentation.uiAutomation.serviceInfo.apply {
                this.flags = flags or android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS }
            shell("ime enable $id"); shell("ime set $id")
            options.copy(deleteRepeat = true, repeatGuard = false).save(app)
            block()
        } finally {
            if (!previous.isNullOrBlank()) shell("ime set $previous"); if (!enabled) shell("ime disable $id")
            options.save(app); instrumentation.uiAutomation.serviceInfo = instrumentation.uiAutomation.serviceInfo.apply { this.flags = flags }
        }
    }
    private fun launch(password: Boolean = false, raw: Boolean = false): KeyboardEditorContractActivity {
        val activity = instrumentation.startActivitySync(Intent(app, KeyboardEditorContractActivity::class.java)
            .putExtra("ime_options", EditorInfo.IME_ACTION_DONE).putExtra("password", password).putExtra("raw", raw)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as KeyboardEditorContractActivity
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        // A cold CI emulator can hand out window focus late; nudge the activity
        // until the window actually reports focus.
        await("editor focus") {
            if (!activity.hasWindowFocus()) activity.editor.requestFocus()
            activity.hasWindowFocus()
        }
        main { activity.editor.requestFocus(); manager.showSoftInput(activity.editor, 0) }
        await("keyboard") { key("Delete") != null }; return activity
    }

    private fun liveDelete(): Button = main {
        fun find(view: View): Button? = when {
            view is Button && view.isShown && view.contentDescription?.toString() == "Delete" -> view
            view is android.view.ViewGroup -> (0 until view.childCount).firstNotNullOfOrNull { find(view.getChildAt(it)) }
            else -> null
        }
        val root = android.view.inspector.WindowInspector.getGlobalWindowViews().single {
            (it.layoutParams as? android.view.WindowManager.LayoutParams)?.type ==
                android.view.WindowManager.LayoutParams.TYPE_INPUT_METHOD
        }
        find(root) ?: error("Missing live Delete")
    }

    /**
     * The editor restart rebuilds the IME asynchronously; under load a gesture
     * aimed at the previous panel dies silently. Require the same Delete button
     * across two polls before driving any drag against it.
     */
    private fun stableDelete(): Button {
        var stable: Button? = null
        await("Delete key did not stabilize after restart") {
            val current = runCatching { liveDelete() }.getOrNull()
            val same = current != null && current === stable
            stable = current
            same
        }
        return stable ?: liveDelete()
    }

    private fun dispatch(button: Button, action: Int, x: Float, y: Float, down: Long) = main {
        val event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, x, y, 0)
        try { assertTrue("Delete touch was not consumed", button.dispatchTouchEvent(event)) }
        finally { event.recycle() }
    }

    private fun imeOffsets(button: Button): Pair<Int, Int> = main {
        val service = button.context as KeyboardIme
        fun offset(name: String) = KeyboardIme::class.java.getDeclaredField(name).run {
            isAccessible = true
            getInt(service)
        }
        offset("selectionStart") to offset("selectionEnd")
    }

    private fun hostSelectionSettled(button: Button): Boolean = main {
        val service = button.context as KeyboardIme
        val selection = KeyboardIme::class.java.getDeclaredField("backspaceSelection").run {
            isAccessible = true
            get(service)
        } ?: return@main false
        fun field(name: String) = selection.javaClass.getDeclaredField(name).apply { isAccessible = true }
        field("pendingLeft").get(selection) == null &&
            field("desiredUnits").getInt(selection) == field("confirmedUnits").getInt(selection)
    }

    private data class DirectFixture(val activity: Activity, val button: Button)

    private fun directFixture(): DirectFixture {
        val activity = instrumentation.startActivitySync(Intent(app, KeyboardSettingsActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        lateinit var button: Button
        val laidOut = java.util.concurrent.CountDownLatch(1)
        main {
            val host = FrameLayout(activity)
            button = Button(activity)
            button.addOnLayoutChangeListener { _, left, top, right, bottom, _, _, _, _ ->
                if (right > left && bottom > top) laidOut.countDown()
            }
            host.addView(button, FrameLayout.LayoutParams(Ui.dp(activity, 180), Ui.dp(activity, 64)))
            activity.setContentView(host)
        }
        assertTrue("Direct Delete key was not laid out", laidOut.await(5, java.util.concurrent.TimeUnit.SECONDS))
        return DirectFixture(activity, button)
    }

    private fun event(action: Int, x: Float, y: Float, down: Long): MotionEvent =
        MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, x, y, 0)

    private fun send(button: Button, event: MotionEvent) {
        try { assertTrue(button.dispatchTouchEvent(event)) } finally { event.recycle() }
    }

    private fun pointerDown(x: Float, y: Float, down: Long): MotionEvent {
        val properties = arrayOf(
            MotionEvent.PointerProperties().apply { id = 0; toolType = MotionEvent.TOOL_TYPE_FINGER },
            MotionEvent.PointerProperties().apply { id = 1; toolType = MotionEvent.TOOL_TYPE_FINGER },
        )
        val coordinates = arrayOf(
            MotionEvent.PointerCoords().apply { this.x = x; this.y = y; pressure = 1f; size = 1f },
            MotionEvent.PointerCoords().apply { this.x = x + 8f; this.y = y; pressure = 1f; size = 1f },
        )
        return MotionEvent.obtain(down, SystemClock.uptimeMillis(),
            MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT),
            2, properties, coordinates, 0, 0, 1f, 1f, 0, 0, 0, 0)
    }

    private class RecordingSelection(var allowBegin: Boolean = true, var allowFinish: Boolean = true) : BackspaceSelection {
        var begins = 0
        val moves = mutableListOf<Boolean>()
        var finishes = 0
        var cancels = 0
        override fun begin(): Boolean { begins++; return allowBegin }
        override fun move(left: Boolean): Boolean { moves += left; return true }
        override fun finish(): Boolean { finishes++; return allowFinish }
        override fun cancel() { cancels++ }
    }

    private data class ConnectionSpy(val value: InputConnection, val calls: MutableList<Pair<String, List<Any?>>>)

    private fun connectionSpy(commitAccepted: Boolean = true): ConnectionSpy {
        val calls = mutableListOf<Pair<String, List<Any?>>>()
        val value = Proxy.newProxyInstance(javaClass.classLoader, arrayOf(InputConnection::class.java)) { _, method, args ->
            calls += method.name to args.orEmpty().toList()
            when {
                method.name == "commitText" -> commitAccepted
                method.returnType == Boolean::class.javaPrimitiveType -> true
                method.returnType == Int::class.javaPrimitiveType -> 0
                else -> null
            }
        } as InputConnection
        return ConnectionSpy(value, calls)
    }

    @Test fun directGestureHonorsThresholdStepsStationaryReversalAndRelease() {
        val fixture = directFixture()
        try { main {
            val button = fixture.button
            val selection = RecordingSelection()
            var clicks = 0
            button.setOnClickListener { clicks++ }
            DeleteRepeater().attach(button, false, selection) { error("Repeat must stay disabled") }
            val startX = button.width - 4f
            val startY = button.height / 2f
            val slop = ViewConfiguration.get(button.context).scaledTouchSlop.toFloat()
            val step = maxOf(slop.toInt(), Ui.dp(button.context, 16)).toFloat()

            var down = SystemClock.uptimeMillis()
            send(button, event(MotionEvent.ACTION_DOWN, startX, startY, down))
            send(button, event(MotionEvent.ACTION_MOVE, startX - slop, startY, down))
            assertEquals("The exact touch-slop boundary must remain a pending tap", 0, selection.begins)
            send(button, event(MotionEvent.ACTION_MOVE, startX - slop - 1f, startY, down))
            assertEquals(1, selection.begins)
            assertTrue("Crossing touch slop must not invent a partial step", selection.moves.isEmpty())
            send(button, event(MotionEvent.ACTION_MOVE, startX - step - 1f, startY, down))
            assertEquals(listOf(true), selection.moves)
            send(button, event(MotionEvent.ACTION_MOVE, startX - step - 1f, startY, down))
            assertEquals("A stationary move must do nothing", listOf(true), selection.moves)
            send(button, event(MotionEvent.ACTION_MOVE, startX + step * 3f, startY, down))
            assertEquals("Reversal may retreat only to the origin", listOf(true, false), selection.moves)
            send(button, event(MotionEvent.ACTION_UP, startX, startY, down))
            assertEquals(0, selection.finishes)
            assertEquals(1, selection.cancels)
            assertEquals(0, clicks)

            down = SystemClock.uptimeMillis()
            send(button, event(MotionEvent.ACTION_DOWN, startX, startY, down))
            send(button, event(MotionEvent.ACTION_MOVE, startX - step * 2f - 1f, startY, down))
            send(button, event(MotionEvent.ACTION_UP, startX - step * 2f - 1f, startY, down))
            assertEquals("A valid release may occur left of the key", 1, selection.finishes)
            assertEquals(0, clicks)
        } } finally { main { fixture.activity.finish() } }
    }

    @Test fun directGestureCapsEachEventAndTheWholeGesture() {
        val fixture = directFixture()
        try { main {
            val button = fixture.button
            val selection = RecordingSelection()
            DeleteRepeater().attach(button, false, selection) { error("Repeat must stay disabled") }
            val startX = button.width - 4f
            val startY = button.height / 2f
            val slop = ViewConfiguration.get(button.context).scaledTouchSlop.toFloat()
            val step = maxOf(slop.toInt(), Ui.dp(button.context, 16)).toFloat()
            val down = SystemClock.uptimeMillis()
            send(button, event(MotionEvent.ACTION_DOWN, startX, startY, down))
            send(button, event(MotionEvent.ACTION_MOVE, startX - slop - 1f, startY, down))
            repeat(5) { send(button, event(MotionEvent.ACTION_MOVE, -100_000f, startY, down)) }
            assertEquals("A gesture must stop extending at 256 units", 256, selection.moves.count { it })
            val atCap = selection.moves.size
            send(button, event(MotionEvent.ACTION_MOVE, -100_000f, startY, down))
            assertEquals("Motion beyond the total cap must be inert", atCap, selection.moves.size)
            send(button, event(MotionEvent.ACTION_MOVE, 100_000f, startY, down))
            assertEquals("One event may reverse at most 64 units", 64, selection.moves.drop(atCap).count { !it })
            repeat(3) { send(button, event(MotionEvent.ACTION_MOVE, 100_000f, startY, down)) }
            assertEquals(256, selection.moves.count { !it })
            send(button, event(MotionEvent.ACTION_UP, startX, startY, down))
            assertEquals(0, selection.finishes)
            assertEquals(1, selection.cancels)
        } } finally { main { fixture.activity.finish() } }
    }

    @Test fun directGestureCancellationAndRefusalNeverBecomeDelete() {
        val fixture = directFixture()
        try { main {
            val button = fixture.button
            val startX = button.width - 4f
            val startY = button.height / 2f
            val step = maxOf(ViewConfiguration.get(button.context).scaledTouchSlop, Ui.dp(button.context, 16)).toFloat()
            var clicks = 0
            button.setOnClickListener { clicks++ }

            fun attach(selection: RecordingSelection): DeleteRepeater = DeleteRepeater().also {
                it.attach(button, false, selection) { error("Repeat must stay disabled") }
            }
            var selection = RecordingSelection()
            attach(selection)
            var down = SystemClock.uptimeMillis()
            send(button, event(MotionEvent.ACTION_DOWN, startX, startY, down))
            send(button, event(MotionEvent.ACTION_MOVE, startX - step - 1f, startY, down))
            send(button, event(MotionEvent.ACTION_CANCEL, startX - step - 1f, startY, down))
            assertEquals(1, selection.cancels)

            selection = RecordingSelection()
            attach(selection)
            down = SystemClock.uptimeMillis()
            send(button, event(MotionEvent.ACTION_DOWN, startX, startY, down))
            send(button, event(MotionEvent.ACTION_MOVE, startX - step - 1f, startY, down))
            send(button, pointerDown(startX - step - 1f, startY, down))
            send(button, event(MotionEvent.ACTION_UP, startX - step - 1f, startY, down))
            assertEquals(1, selection.cancels)
            assertEquals(0, selection.finishes)

            selection = RecordingSelection()
            val invalidated = attach(selection)
            down = SystemClock.uptimeMillis()
            send(button, event(MotionEvent.ACTION_DOWN, startX, startY, down))
            send(button, event(MotionEvent.ACTION_MOVE, startX - step - 1f, startY, down))
            invalidated.cancel() // Panel rebuild, detach and lifecycle paths converge here.
            send(button, event(MotionEvent.ACTION_UP, startX - step - 1f, startY, down))
            assertEquals(1, selection.cancels)
            assertEquals("A stale release after invalidation must stay harmless", 0, selection.finishes)

            selection = RecordingSelection()
            attach(selection)
            down = SystemClock.uptimeMillis()
            send(button, event(MotionEvent.ACTION_DOWN, startX, startY, down))
            send(button, event(MotionEvent.ACTION_MOVE, startX - 1f, startY + step + 1f, down))
            send(button, event(MotionEvent.ACTION_UP, startX - 1f, startY + step + 1f, down))
            assertEquals("Predominantly vertical motion must not begin selection", 0, selection.begins)

            selection = RecordingSelection()
            attach(selection)
            down = SystemClock.uptimeMillis()
            send(button, event(MotionEvent.ACTION_DOWN, startX, startY, down))
            send(button, event(MotionEvent.ACTION_MOVE, startX - step - 1f, startY, down))
            send(button, event(MotionEvent.ACTION_MOVE, startX - step - 1f,
                startY + Ui.dp(button.context, 48) + 1f, down))
            send(button, event(MotionEvent.ACTION_UP, startX - step - 1f, startY, down))
            assertEquals(1, selection.cancels)
            assertEquals(0, selection.finishes)

            selection = RecordingSelection(allowBegin = false)
            attach(selection)
            down = SystemClock.uptimeMillis()
            send(button, event(MotionEvent.ACTION_DOWN, startX, startY, down))
            send(button, event(MotionEvent.ACTION_MOVE, startX - step - 1f, startY, down))
            send(button, event(MotionEvent.ACTION_UP, startX - step - 1f, startY, down))
            assertEquals(1, selection.begins)
            assertEquals("A refused editor operation must consume the stream", 0, clicks)

            selection = RecordingSelection(allowFinish = false)
            var unavailable = 0
            DeleteRepeater().attach(button, false, selection, selectionUnavailable = { unavailable++ }) {
                error("Repeat must stay disabled")
            }
            down = SystemClock.uptimeMillis()
            send(button, event(MotionEvent.ACTION_DOWN, startX, startY, down))
            send(button, event(MotionEvent.ACTION_MOVE, startX - step - 1f, startY, down))
            send(button, event(MotionEvent.ACTION_UP, startX - step - 1f, startY, down))
            assertEquals(1, selection.finishes)
            assertEquals(1, selection.cancels)
            assertEquals("Only a refused final deletion should report unavailable", 1, unavailable)
        } } finally { main { fixture.activity.finish() } }
    }

    @Test fun swipeAndHeldRepeatCannotOwnTheSameStream() {
        val fixture = directFixture()
        try {
            val selection = RecordingSelection()
            val erases = mutableListOf<Long>()
            var clicks = 0
            val repeater = DeleteRepeater()
            val button = fixture.button
            val startX = main { button.width - 4f }
            val startY = main { button.height / 2f }
            val step = main { maxOf(ViewConfiguration.get(button.context).scaledTouchSlop, Ui.dp(button.context, 16)).toFloat() }
            main {
                button.setOnClickListener { clicks++ }
                repeater.attach(button, true, selection) { erases += SystemClock.uptimeMillis() }
                val down = SystemClock.uptimeMillis()
                send(button, event(MotionEvent.ACTION_DOWN, startX, startY, down))
                send(button, event(MotionEvent.ACTION_MOVE, startX - step - 1f, startY, down))
            }
            UiAwait.remains("Selection must cancel every pending repeat callback") { erases.isEmpty() }
            main {
                val down = SystemClock.uptimeMillis()
                send(button, event(MotionEvent.ACTION_UP, startX - step - 1f, startY, down))
                send(button, event(MotionEvent.ACTION_DOWN, startX, startY, down))
            }
            UiAwait.until("Held repeat did not acquire the next stream") { erases.isNotEmpty() }
            val beforeMove = erases.size
            main {
                val down = SystemClock.uptimeMillis()
                send(button, event(MotionEvent.ACTION_MOVE, startX - step - 1f, startY, down))
                send(button, event(MotionEvent.ACTION_UP, startX - step - 1f, startY, down))
            }
            assertEquals("A held stream must never convert to selection", 1, selection.begins)
            assertTrue(erases.size >= beforeMove)
            assertEquals(0, clicks)
        } finally { main { fixture.activity.finish() } }
    }

    @Test fun hostContractRequiresConfirmationAndRejectsStaleConnections() {
        val accepted = connectionSpy()
        var current = true
        var connection: InputConnection? = accepted.value
        var offsets = 3 to 3
        var selection = HostBackspaceSelection({ current }, { connection }, { offsets })
        assertTrue(selection.begin())
        assertTrue(selection.move(true))
        selection.update(2, 3)
        assertTrue(selection.finish())
        assertEquals(1, accepted.calls.count { it.first == "commitText" })
        assertTrue("The selection contract must not read host text", accepted.calls.none {
            it.first in listOf("getTextBeforeCursor", "getTextAfterCursor", "getSelectedText", "getSurroundingText")
        })

        val rejected = connectionSpy(commitAccepted = false)
        connection = rejected.value; offsets = 3 to 3
        selection = HostBackspaceSelection({ current }, { connection }, { offsets })
        assertTrue(selection.begin()); assertTrue(selection.move(true)); selection.update(2, 3)
        assertFalse(selection.finish())
        selection.cancel()
        assertEquals(1, rejected.calls.count { it.first == "commitText" })
        assertEquals("A rejected delete must restore only through the captured connection", 1,
            rejected.calls.count { it.first == "setSelection" })

        val delayed = connectionSpy()
        connection = delayed.value; offsets = 3 to 3
        selection = HostBackspaceSelection({ current }, { connection }, { offsets })
        assertTrue(selection.begin()); assertTrue(selection.move(true)); selection.update(2, 3)
        assertTrue(selection.move(true))
        assertFalse("An earlier confirmation must not authorize a later pending move", selection.finish())
        selection.cancel()
        assertEquals(0, delayed.calls.count { it.first == "commitText" })

        val pendingOld = connectionSpy()
        val pendingReplacement = connectionSpy()
        connection = pendingOld.value; offsets = 3 to 3
        selection = HostBackspaceSelection({ current }, { connection }, { offsets })
        assertTrue(selection.begin()); assertTrue(selection.move(true)); assertTrue(selection.move(true))
        val oldNavigationCalls = pendingOld.calls.count { it.first == "sendKeyEvent" }
        connection = pendingReplacement.value
        selection.update(2, 3)
        assertFalse("A replacement connection must invalidate a pending confirmation", selection.finish())
        selection.cancel()
        assertEquals("A stale callback must not pump another request into the old connection",
            oldNavigationCalls, pendingOld.calls.count { it.first == "sendKeyEvent" })
        assertEquals(0, pendingReplacement.calls.count { it.first in listOf("commitText", "setSelection", "sendKeyEvent") })

        val stale = connectionSpy()
        val replacement = connectionSpy()
        connection = stale.value; current = true; offsets = 3 to 3
        selection = HostBackspaceSelection({ current }, { connection }, { offsets })
        assertTrue(selection.begin()); assertTrue(selection.move(true)); selection.update(2, 3)
        current = false; connection = replacement.value
        assertFalse(selection.finish())
        selection.cancel()
        assertEquals(0, stale.calls.count { it.first in listOf("commitText", "setSelection") })
        assertEquals(0, replacement.calls.count { it.first in listOf("commitText", "setSelection") })
    }

    @Test fun privateDraftPreviewPreservesEveryNamedGraphemeAndDeletesLocally() = main {
        for (unit in listOf("b", "😀", "é", "👩‍👩‍👧‍👦")) {
            val editor = PrivateDraftEditor(app)
            val value = "A${unit}Z"
            assertTrue(editor.replace(value))
            editor.view.setSelection(value.length - 1)
            val selection = editor.backspaceSelection()
            assertTrue(selection.begin())
            assertTrue(selection.move(true))
            assertEquals(unit, editor.current.text.substring(editor.current.selectionStart, editor.current.selectionEnd))
            assertTrue(selection.move(false))
            assertEquals(editor.current.selectionStart, editor.current.selectionEnd)
            assertFalse(selection.finish())
            selection.cancel()
            assertEquals(value, editor.current.text)

            assertTrue(selection.begin())
            assertTrue(selection.move(true))
            assertTrue(selection.finish())
            assertEquals("AZ", editor.current.text)
            editor.dispose()
        }
    }

    @Test fun privateDraftCancellationRestoresOriginWithoutDeleting() = main {
        val editor = PrivateDraftEditor(app)
        assertTrue(editor.replace("abc")); editor.view.setSelection(3)
        val selection = editor.backspaceSelection()
        assertTrue(selection.begin()); assertTrue(selection.move(true)); selection.cancel()
        assertEquals("abc", editor.current.text)
        assertEquals(3, editor.current.selectionStart)
        assertEquals(3, editor.current.selectionEnd)
        assertTrue(selection.begin()); assertTrue(selection.move(true))
        editor.dispose()
        selection.cancel()
        assertEquals("", editor.current.text)
        assertEquals(0, editor.current.selectionStart)
    }

    @Test fun hostImeBackspaceDragPreviewsUnicodeAndDeletesOnceOnRelease() = withKeyboard {
        val activity = launch()
        try {
            val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
            for (unit in listOf("b", "😀", "é", "👩‍👩‍👧‍👦")) {
                val value = "A${unit}Z"
                val origin = value.length - 1
                main {
                    activity.editor.setText(value); activity.editor.setSelection(origin)
                    manager.restartInput(activity.editor)
                    manager.showSoftInput(activity.editor, InputMethodManager.SHOW_IMPLICIT)
                }
                await("Keyboard did not return for $unit") { key("Delete") != null }
                val button = stableDelete()
                await("IME did not observe the collapsed caret before $unit") {
                    imeOffsets(button) == (origin to origin)
                }
                val x = main { button.width - 4f }
                val y = main { button.height / 2f }
                val step = main { maxOf(ViewConfiguration.get(button.context).scaledTouchSlop,
                    Ui.dp(button.context, 16)).toFloat() }
                val down = SystemClock.uptimeMillis()
                dispatch(button, MotionEvent.ACTION_DOWN, x, y, down)
                dispatch(button, MotionEvent.ACTION_MOVE, x - step - 1f, y, down)
                await("drag did not preview the complete $unit range") { main {
                    minOf(activity.editor.selectionStart, activity.editor.selectionEnd) == 1 &&
                        maxOf(activity.editor.selectionStart, activity.editor.selectionEnd) == origin
                } }
                await("IME did not confirm the complete $unit preview") {
                    val offsets = imeOffsets(button)
                    minOf(offsets.first, offsets.second) == 1 && maxOf(offsets.first, offsets.second) == origin
                }
                dispatch(button, MotionEvent.ACTION_UP, x - step - 1f, y, down)
                Thread.sleep(300)
                val final = main {
                    Triple(activity.editor.text.toString(), activity.editor.selectionStart, activity.editor.selectionEnd)
                }
                assertEquals("Release changed more than the exact $unit preview: $final", "AZ", final.first)
            }

            main { activity.editor.setText("abcd"); activity.editor.setSelection(4) }
            main {
                manager.restartInput(activity.editor)
                manager.showSoftInput(activity.editor, InputMethodManager.SHOW_IMPLICIT)
            }
            await("Keyboard did not return for cancellation") { key("Delete") != null }
            val button = stableDelete()
            val x = main { button.width - 4f }
            val y = main { button.height / 2f }
            val step = main { maxOf(ViewConfiguration.get(button.context).scaledTouchSlop,
                Ui.dp(button.context, 16)).toFloat() }
            await("IME did not observe the cancellation origin") { imeOffsets(button) == (4 to 4) }
            val down = SystemClock.uptimeMillis()
            dispatch(button, MotionEvent.ACTION_DOWN, x, y, down)
            dispatch(button, MotionEvent.ACTION_MOVE, x - step - 1f, y, down)
            await("cancel fixture did not preview") { main {
                minOf(activity.editor.selectionStart, activity.editor.selectionEnd) == 3 &&
                    maxOf(activity.editor.selectionStart, activity.editor.selectionEnd) == 4
            } }
            await("IME did not confirm the cancellation preview") {
                val offsets = imeOffsets(button)
                minOf(offsets.first, offsets.second) == 3 && maxOf(offsets.first, offsets.second) == 4
            }
            dispatch(button, MotionEvent.ACTION_CANCEL, x - step - 1f, y, down)
            await("same-session cancellation did not restore the caret") { main {
                activity.editor.text.toString() == "abcd" && activity.editor.selectionStart == 4 &&
                    activity.editor.selectionEnd == 4
            } }

            main {
                activity.editor.setText("abXY"); activity.editor.setSelection(2)
                manager.restartInput(activity.editor)
                manager.showSoftInput(activity.editor, InputMethodManager.SHOW_IMPLICIT)
            }
            await("Keyboard did not return for overshoot reversal") { key("Delete") != null }
            val overshootButton = stableDelete()
            await("IME did not observe the overshoot origin") { imeOffsets(overshootButton) == (2 to 2) }
            val overshootX = main { overshootButton.width - 4f }
            val overshootY = main { overshootButton.height / 2f }
            val overshootStep = main { maxOf(ViewConfiguration.get(overshootButton.context).scaledTouchSlop,
                Ui.dp(overshootButton.context, 16)).toFloat() }
            val overshootDown = SystemClock.uptimeMillis()
            dispatch(overshootButton, MotionEvent.ACTION_DOWN, overshootX, overshootY, overshootDown)
            dispatch(overshootButton, MotionEvent.ACTION_MOVE, overshootX - overshootStep * 80f,
                overshootY, overshootDown)
            await("Long leftward motion did not stop at the host boundary") { main {
                minOf(activity.editor.selectionStart, activity.editor.selectionEnd) == 0 &&
                    maxOf(activity.editor.selectionStart, activity.editor.selectionEnd) == 2
            } }
            await("Host selection requests did not settle at the boundary") { hostSelectionSettled(overshootButton) }
            dispatch(overshootButton, MotionEvent.ACTION_MOVE, overshootX + overshootStep * 80f,
                overshootY, overshootDown)
            await("Rightward reversal crossed the origin into forward text") { main {
                activity.editor.selectionStart == 2 && activity.editor.selectionEnd == 2
            } }
            await("Host reversal requests did not settle at the origin") { hostSelectionSettled(overshootButton) }
            assertEquals("abXY", main { activity.editor.text.toString() })
            dispatch(overshootButton, MotionEvent.ACTION_UP, overshootX, overshootY, overshootDown)
        } finally { main { activity.finish() } }
    }

    @Test fun passwordAndRawFieldsRefuseSwipeButKeepBackspace() {
        withKeyboard {
            val activity = launch(password = true)
            try {
                main { activity.editor.setText("secret"); activity.editor.setSelection(6) }
                Thread.sleep(150)
                val button = stableDelete(); val x = main { button.width - 4f }; val y = main { button.height / 2f }
                val step = main { maxOf(ViewConfiguration.get(button.context).scaledTouchSlop,
                    Ui.dp(button.context, 16)).toFloat() }
                var down = SystemClock.uptimeMillis()
                dispatch(button, MotionEvent.ACTION_DOWN, x, y, down)
                dispatch(button, MotionEvent.ACTION_MOVE, x - step - 1f, y, down)
                dispatch(button, MotionEvent.ACTION_UP, x - step - 1f, y, down)
                Thread.sleep(200)
                assertEquals("A password-field swipe must not delete", "secret", main { activity.editor.text.toString() })
                down = SystemClock.uptimeMillis()
                dispatch(button, MotionEvent.ACTION_DOWN, x, y, down)
                dispatch(button, MotionEvent.ACTION_UP, x, y, down)
                await("Password-field Backspace tap regressed") { main { activity.editor.text.toString() == "secre" } }
            } finally { main { activity.finish() } }
        }
        withKeyboard {
            val activity = launch(raw = true)
            try {
                val value = "raw"
                main { activity.editor.setText(value); activity.editor.setSelection(value.length) }
                Thread.sleep(150)
                val button = liveDelete(); val x = main { button.width - 4f }; val y = main { button.height / 2f }
                val step = main { maxOf(ViewConfiguration.get(button.context).scaledTouchSlop,
                    Ui.dp(button.context, 16)).toFloat() }
                var down = SystemClock.uptimeMillis()
                dispatch(button, MotionEvent.ACTION_DOWN, x, y, down)
                dispatch(button, MotionEvent.ACTION_MOVE, x - step - 1f, y, down)
                dispatch(button, MotionEvent.ACTION_UP, x - step - 1f, y, down)
                Thread.sleep(200)
                assertEquals("A raw-field swipe must not delete", value,
                    main { activity.editor.text.toString() })
                down = SystemClock.uptimeMillis()
                dispatch(button, MotionEvent.ACTION_DOWN, x, y, down)
                dispatch(button, MotionEvent.ACTION_UP, x, y, down)
                await("Raw Backspace tap regressed") {
                    main { activity.editor.text.toString() == value.dropLast(1) }
                }
            } finally { main { activity.finish() } }
        }
    }

    @Test fun livePanelOpenImmediatelyRefusesSelectionGesture() = withKeyboard {
        val activity = launch()
        try {
            val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
            main {
                activity.editor.setText("abcd"); activity.editor.setSelection(4)
                manager.restartInput(activity.editor)
                manager.showSoftInput(activity.editor, InputMethodManager.SHOW_IMPLICIT)
            }
            await("Keyboard did not return for the extra-keys panel") { key("Delete") != null }
            press("Extra keys")
            await("The panel did not reveal its accessory keys") {
                key("Control off") != null && key("Left arrow") != null && key("Delete") != null
            }
            val button = stableDelete()
            val x = main { button.width - 4f }; val y = main { button.height / 2f }
            val step = main { maxOf(ViewConfiguration.get(button.context).scaledTouchSlop,
                Ui.dp(button.context, 16)).toFloat() }
            val down = SystemClock.uptimeMillis()
            dispatch(button, MotionEvent.ACTION_DOWN, x, y, down)
            dispatch(button, MotionEvent.ACTION_MOVE, x - step - 1f, y, down)
            dispatch(button, MotionEvent.ACTION_UP, x - step - 1f, y, down)
            Thread.sleep(200)
            assertEquals("A live panel-open swipe must not delete", "abcd",
                main { activity.editor.text.toString() })
        } finally { main { activity.finish() } }
    }

}
