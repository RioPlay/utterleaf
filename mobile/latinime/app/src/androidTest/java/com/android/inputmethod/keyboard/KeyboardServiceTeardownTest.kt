package com.android.inputmethod.keyboard

import android.view.ContextThemeWrapper
import android.view.View
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.keyboard.internal.DrawingProxy
import com.android.inputmethod.keyboard.internal.PointerTrackerQueue
import com.android.inputmethod.keyboard.internal.TimerHandler
import com.android.inputmethod.latin.LatinIME
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Test
import org.junit.runner.RunWith

/** Verifies process-static keyboard state cannot let an old service tear down its successor. */
@RunWith(AndroidJUnit4::class)
class KeyboardServiceTeardownTest {
    private class TestIme : LatinIME()

    private val drawingProxy = object : DrawingProxy {
        override fun onKeyPressed(key: Key, withPreview: Boolean) = Unit
        override fun onKeyReleased(key: Key, withAnimation: Boolean) = Unit
        override fun showMoreKeysKeyboard(key: Key, tracker: PointerTracker): MoreKeysPanel? = null
        override fun startWhileTypingAnimation(fadeInOrOut: Int) = Unit
        override fun showSlidingKeyInputPreview(tracker: PointerTracker?) = Unit
        override fun showGestureTrail(tracker: PointerTracker, showsFloatingPreviewText: Boolean) = Unit
        override fun dismissGestureFloatingPreviewTextWithoutDelay() = Unit
    }

    private fun field(owner: Class<*>, name: String) = owner.getDeclaredField(name).apply {
        isAccessible = true
    }

    @Test fun staleTeardownLeavesSuccessorAndSilentQueueCleanupDetachesEverything() {
        var failure: Throwable? = null
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            try {
                val switcher = KeyboardSwitcher::class.java.getDeclaredConstructor().apply {
                    isAccessible = true
                }.newInstance()
                val ownerField = field(KeyboardSwitcher::class.java, "mLatinIME")
                val frameField = field(KeyboardSwitcher::class.java, "mMainKeyboardFrame")
                val themeContextField = field(KeyboardSwitcher::class.java, "mThemeContext")
                val listenerField = field(PointerTracker::class.java, "sListener")
                val queueField = field(PointerTracker::class.java, "sPointerTrackerQueue")
                val queue = queueField.get(null) as PointerTrackerQueue
                val backing = field(PointerTrackerQueue::class.java,
                    "mExpandableArrayOfActivePointers").get(queue) as ArrayList<*>
                val oldListener = listenerField.get(null)
                val oldQueue = backing.toList()
                val queueSizeField = field(PointerTrackerQueue::class.java, "mArraySize")
                val oldQueueSize = queueSizeField.getInt(queue)
                val trackers = field(PointerTracker::class.java, "sTrackers").get(null) as ArrayList<*>
                val oldTrackers = trackers.toList()
                val timerField = field(PointerTracker::class.java, "sTimerProxy")
                val oldTimer = timerField.get(null)
                val drawingField = field(PointerTracker::class.java, "sDrawingProxy")
                val oldDrawing = drawingField.get(null)
                val gestureField = field(PointerTracker::class.java, "sInGesture")
                val oldInGesture = gestureField.getBoolean(null)
                try {
                    val destroyed = TestIme()
                    val successor = TestIme()
                    val successorListener = object : KeyboardActionListener.Adapter() {}
                    val element = object : PointerTrackerQueue.Element {
                        var phantomUps = 0
                        override fun isModifier() = false
                        override fun isInDraggingFinger() = false
                        override fun onPhantomUpEvent(eventTime: Long) { phantomUps++ }
                        override fun cancelTrackingForAction() = Unit
                    }

                    val successorFrame = View(InstrumentationRegistry.getInstrumentation().targetContext)
                    ownerField.set(switcher, successor)
                    frameField.set(switcher, successorFrame)
                    themeContextField.set(switcher, ContextThemeWrapper(
                        InstrumentationRegistry.getInstrumentation().targetContext, 0))
                    PointerTracker.setKeyboardActionListener(successorListener)
                    timerField.set(null, TimerHandler(drawingProxy, 1_000, 0))
                    drawingField.set(null, drawingProxy)
                    queue.clear()
                    queue.add(element)

                    // Both delayed memory release and framework destruction from the old owner
                    // must leave the replacement listener and queue intact.
                    switcher.deallocateMemory(destroyed)
                    switcher.onDestroy(destroyed)
                    assertSame(successor, ownerField.get(switcher))
                    assertSame(successorListener, listenerField.get(null))
                    assertEquals(1, queue.size())

                    // Valid deallocation silently retires pointer instances and their queue,
                    // while retaining the live view's timer/drawing/listener wiring for reuse.
                    switcher.deallocateMemory(successor)
                    assertEquals(0, queue.size())
                    assertSame(successorListener, listenerField.get(null))
                    assertSame(drawingProxy, drawingField.get(null))
                    assertSame(successorFrame, frameField.get(switcher))

                    switcher.onDestroy(successor)
                    assertNull(ownerField.get(switcher))
                    assertNull(frameField.get(switcher))
                    assertNull(themeContextField.get(switcher))
                    assertSame(KeyboardActionListener.EMPTY_LISTENER, listenerField.get(null))
                    assertNull(timerField.get(null))
                    assertNull(drawingField.get(null))
                    assertEquals(0, queue.size())
                    assertEquals("Queue backing entries retain destroyed pointer state", 0, backing.size)
                    assertEquals("Teardown must not synthesize input through a successor", 0,
                        element.phantomUps)
                } finally {
                    @Suppress("UNCHECKED_CAST")
                    val mutableBacking = backing as ArrayList<PointerTrackerQueue.Element>
                    mutableBacking.clear()
                    oldQueue.forEach { mutableBacking.add(it as PointerTrackerQueue.Element) }
                    queueSizeField.setInt(queue, oldQueueSize)
                    @Suppress("UNCHECKED_CAST")
                    val mutableTrackers = trackers as ArrayList<PointerTracker>
                    mutableTrackers.clear()
                    oldTrackers.forEach { mutableTrackers.add(it as PointerTracker) }
                    listenerField.set(null, oldListener)
                    timerField.set(null, oldTimer)
                    drawingField.set(null, oldDrawing)
                    gestureField.setBoolean(null, oldInGesture)
                }
            } catch (error: Throwable) {
                failure = error
            }
        }
        failure?.let { throw it }
    }

    @Test fun cancelAllMessagesAlsoCancelsTypingAndDoubleTapState() {
        var failure: Throwable? = null
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            try {
                val timer = TimerHandler(drawingProxy, 60_000, 0)
                val typingMessage = field(TimerHandler::class.java, "MSG_TYPING_STATE_EXPIRED")
                    .getInt(null)
                timer.sendMessageDelayed(timer.obtainMessage(typingMessage), 60_000)
                timer.startDoubleTapShiftKeyTimer()
                assertEquals(true, timer.isTypingState)
                assertEquals(true, timer.isInDoubleTapShiftKeyTimeout)
                timer.cancelAllMessages()
                assertEquals(false, timer.isTypingState)
                assertEquals(false, timer.isInDoubleTapShiftKeyTimeout)
            } catch (error: Throwable) {
                failure = error
            }
        }
        failure?.let { throw it }
    }
}
