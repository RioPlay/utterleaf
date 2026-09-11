package com.android.inputmethod.latin.inputlogic

import android.os.Looper
import android.view.inputmethod.InputConnection
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.*
import com.android.inputmethod.latin.common.InputPointers
import com.android.inputmethod.latin.utils.RecapitalizeStatus
import org.utterleaf.keyboard.SuggestionDecoder
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.lang.reflect.Proxy
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

@RunWith(AndroidJUnit4::class)
class InputLogicLifetimeTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private fun <T> main(block: () -> T): T {
        var result: Result<T>? = null
        instrumentation.runOnMainSync { result = runCatching(block) }
        return result!!.getOrThrow()
    }
    private class TestIme : LatinIME() {
        val decoded = AtomicInteger()
        override fun captureSuggestionRequest(style: Int, sequence: Int) = SuggestionDecoder {
            decoded.incrementAndGet(); it.onGetSuggestedWords(SuggestedWords.getEmptyInstance())
        }
    }
    private fun field(owner: Any, name: String) = owner.javaClass.getDeclaredField(name).apply { isAccessible = true }
    private fun logic(ime: LatinIME) = LatinIME::class.java.getDeclaredField("mInputLogic")
        .apply { isAccessible = true }.get(ime) as InputLogic

    @Test fun destroyReleasesLocalTextAndConnectionWithoutCallingHost() {
        val ime = main { TestIme() }
        val logic = logic(ime)
        try {
            main {
                logic.mWordComposer.setBatchInputPointers(InputPointers(1).apply { addPointer(11, 21, 1, 31) })
                logic.mWordComposer.setBatchInputWord("synthetic-composition")
                field(logic, "mEnteredText").set(logic, "synthetic-entered")
                field(logic, "mWordBeingCorrectedByCursor").set(logic, "synthetic-correction")
                val recap = field(logic, "mRecapitalizeStatus").get(logic) as RecapitalizeStatus
                recap.start(0, 9, "synthetic", Locale.US, intArrayOf(' '.code))
                logic.mCurrentlyPressedHardwareKeys.add(42L)
                val connection = logic.mConnection
                val before = field(connection, "mCommittedTextBeforeComposingText").get(connection) as StringBuilder
                val composing = field(connection, "mComposingText").get(connection) as StringBuilder
                before.append("synthetic-before"); composing.append("synthetic-composing")
                val host = Proxy.newProxyInstance(InputConnection::class.java.classLoader,
                    arrayOf(InputConnection::class.java)) { _, method, _ -> error("Teardown called host: ${method.name}") }
                field(connection, "mIC").set(connection, host)
                logic.destroy()
                logic.destroy()
                assertEquals("", logic.mWordComposer.typedWord)
                assertEquals(0, logic.mWordComposer.inputPointers.pointerSize)
                assertSame(LastComposedWord.NOT_A_COMPOSED_WORD, logic.mLastComposedWord)
                assertTrue(logic.mSuggestedWords.isEmpty())
                assertNull(field(logic, "mEnteredText").get(logic))
                assertNull(field(logic, "mWordBeingCorrectedByCursor").get(logic))
                assertEquals("", recap.recapitalizedString)
                assertFalse(recap.isStarted)
                assertTrue(logic.mCurrentlyPressedHardwareKeys.isEmpty())
                assertNull(field(connection, "mIC").get(connection))
                assertNotSame(before, field(connection, "mCommittedTextBeforeComposingText").get(connection))
                assertEquals("", field(connection, "mCommittedTextBeforeComposingText").get(connection).toString())
                assertNotSame(composing, field(connection, "mComposingText").get(connection))
                assertEquals("", field(connection, "mComposingText").get(connection).toString())
            }
        } finally { main { ime.mHandler.removeAllMessages() } }
    }

    @Test fun destroyDropsQueuedDecodeAndRefusesNewWorkWithoutWaitingForRunningTask() {
        val ime = main { TestIme().apply { mEditorSession.start() } }
        val logic = logic(ime)
        val worker = InputLogicHandler(ime, logic)
        field(logic, "mInputLogicHandler").set(logic, worker)
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val delivered = AtomicInteger()
        worker.mNonUIThreadHandler.post { entered.countDown(); release.await(5, TimeUnit.SECONDS) }
        assertTrue(entered.await(5, TimeUnit.SECONDS))
        try {
            main {
                worker.onStartBatchInput()
                worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TYPING, 1) { delivered.incrementAndGet() }
                logic.destroy()
                worker.onStartBatchInput()
                assertFalse(worker.isInBatchInput)
                worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TYPING, 2) { delivered.incrementAndGet() }
            }
            release.countDown()
            worker.mNonUIThreadHandler.looper.thread.join(5000)
            assertFalse("Destroyed IME retained its suggestion thread", worker.mNonUIThreadHandler.looper.thread.isAlive)
            assertEquals(0, ime.decoded.get())
            assertEquals(0, delivered.get())
        } finally {
            release.countDown(); worker.destroy()
            main { ime.mEditorSession.finish(); ime.mHandler.removeAllMessages() }
        }
    }
}
