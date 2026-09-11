package com.android.inputmethod.latin.inputlogic

import android.content.Context
import android.text.InputType
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.InputAttributes
import com.android.inputmethod.latin.LatinIME
import com.android.inputmethod.latin.Suggest
import com.android.inputmethod.latin.SuggestedWords
import com.android.inputmethod.latin.settings.Settings
import com.android.inputmethod.latin.settings.SettingsValues
import org.utterleaf.keyboard.SuggestionDecoder
import org.junit.After
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/** Actual selection entry point with controlled worker/UI delivery and synthetic state. */
@RunWith(AndroidJUnit4::class)
class SelectionSessionRetirementTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val fixturePreferencesName = "selection-owner-${UUID.randomUUID()}"

    private fun createIme(): TestIme {
        val app = instrumentation.targetContext
        val info = EditorInfo().apply {
            packageName = app.packageName
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_AUTO_CORRECT
        }
        val values = SettingsValues(app,
            app.getSharedPreferences(fixturePreferencesName, Context.MODE_PRIVATE), app.resources,
            InputAttributes(info, false, app.packageName))
        // UIHandler reads its owner's settings when queuing resume work. Give this fake
        // service a real snapshot without initializing or changing the process singleton.
        val settings = Settings::class.java.getDeclaredConstructor()
            .apply { isAccessible = true }.newInstance()
        Settings::class.java.getDeclaredField("mSettingsValues")
            .apply { isAccessible = true }.set(settings, values)
        return TestIme().apply {
            LatinIME::class.java.getDeclaredField("mSettings")
                .apply { isAccessible = true }.set(this, settings)
            mEditorSession.start()
        }
    }

    @After fun removeFixturePreferences() {
        assertTrue(instrumentation.targetContext.deleteSharedPreferences(fixturePreferencesName))
    }
    private class TestIme : LatinIME() {
        var cleared = 0
        var rejectEditorLookup = false
        var editorLookups = 0
        var decode: (Suggest.OnGetSuggestedWordsCallback) -> Unit = {
            it.onGetSuggestedWords(SuggestedWords.getEmptyInstance())
        }
        override fun getCurrentInputConnection(): InputConnection? {
            editorLookups++
            check(!rejectEditorLookup) { "Inactive selection queried the host editor" }
            return null
        }
        override fun clearEditorTransientState() { cleared++ }
        override fun captureSuggestionRequest(style: Int, sequence: Int) = SuggestionDecoder { decode(it) }
        val logic get() = LatinIME::class.java.getDeclaredField("mInputLogic")
            .apply { isAccessible = true }.get(this) as InputLogic
    }
    private fun <T> main(block: () -> T): T {
        var result: Result<T>? = null
        instrumentation.runOnMainSync { result = runCatching(block) }
        return result!!.getOrThrow()
    }
    private fun await(latch: CountDownLatch) = assertTrue(latch.await(5, TimeUnit.SECONDS))
    private fun setField(owner: Any, name: String, value: Any) = owner.javaClass.getDeclaredField(name)
        .apply { isAccessible = true }.set(owner, value)
    private fun position(logic: InputLogic, value: Int) {
        setField(logic.mConnection, "mExpectedSelStart", value)
        setField(logic.mConnection, "mExpectedSelEnd", value)
    }

    @Test fun finishedSelectionDoesNotReloadCachesAndActiveNoViewSelectionStillWorks() {
        val ime = main { createIme() }
        try {
            main {
                val logic = ime.logic
                logic.mWordComposer.setBatchInputWord("synthetic-ended-composition")
                ime.mEditorSession.finish()
                logic.retireInput()
                ime.rejectEditorLookup = true
                assertFalse(logic.onUpdateSelection(3, 3, 1, 2, null))
                assertNull(ime.mEditorSession.capture())
                assertEquals(0, ime.editorLookups)
                assertEquals(0, ime.cleared)
                assertEquals("", logic.mWordComposer.typedWord)
                assertFalse(logic.mConnection.isConnected)
                val cache = logic.mConnection.javaClass
                    .getDeclaredField("mCommittedTextBeforeComposingText")
                    .apply { isAccessible = true }.get(logic.mConnection)
                assertEquals("", cache.toString())
                for (message in 0..12) assertFalse(ime.mHandler.hasMessages(message))

                // A token established by onStartInput is sufficient: no input view is created.
                ime.rejectEditorLookup = false
                ime.mEditorSession.start()
                position(logic, 3)
                assertTrue(logic.onUpdateSelection(3, 3, 1, 2, null))
                assertNotNull(ime.mEditorSession.capture())
                assertTrue(ime.editorLookups > 0)
                assertEquals(1, ime.cleared)
                ime.mHandler.removeAllMessages()
            }
        } finally { main { ime.logic.destroy(); ime.mHandler.removeAllMessages() } }
    }

    @Test fun expectedAndBelatedOwnSelectionUpdatesPreserveIdentityAndComposition() {
        val ime = main { createIme() }
        try {
            main {
                val logic = ime.logic
                logic.mWordComposer.setBatchInputWord("abc")
                position(logic, 3)
                val identity = ime.mEditorSession.capture()
                assertFalse(logic.onUpdateSelection(2, 2, 3, 3, null))
                assertFalse(logic.onUpdateSelection(1, 1, 2, 2, null))
                assertSame(identity, ime.mEditorSession.capture())
                assertEquals("abc", logic.mWordComposer.typedWord)
                assertEquals(0, ime.cleared)
            }
        } finally { main { ime.logic.destroy(); ime.mHandler.removeAllMessages() } }
    }

    @Test fun unexpectedSelectionRejectsOldTailAndStripButAcceptsNewCurrentWork() {
        val ime = main { createIme() }
        val logic = ime.logic
        val worker = InputLogicHandler(ime, logic)
        val captured = CountDownLatch(1)
        val completion = AtomicReference<Suggest.OnGetSuggestedWordsCallback>()
        val oldDelivered = AtomicInteger()
        ime.decode = { completion.set(it); captured.countDown() }
        main { setField(logic, "mInputLogicHandler", worker) }
        try {
            main {
                position(logic, 3)
                logic.mWordComposer.setBatchInputWord("abc")
                worker.onStartBatchInput()
                worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TAIL_BATCH, 1) {
                    oldDelivered.incrementAndGet()
                    ime.mHandler.showTailBatchInputResult(it)
                    ime.mHandler.showSuggestionStrip(it)
                }
            }
            await(captured)
            main {
                val oldIdentity = ime.mEditorSession.capture()
                ime.mHandler.showTailBatchInputResult(SuggestedWords.getEmptyInstance())
                ime.mHandler.showSuggestionStrip(SuggestedWords.getEmptyInstance())
                // A real selection range forces the existing reset path without Settings use.
                assertTrue(logic.onUpdateSelection(3, 3, 1, 2, null))
                assertFalse(ime.mEditorSession.isCurrent(oldIdentity))
                assertNotNull(ime.mEditorSession.capture())
                assertFalse(worker.isInBatchInput)
                assertEquals(1, ime.cleared)
                assertFalse(ime.mHandler.hasMessages(3)) // gesture/strip result
                assertFalse(ime.mHandler.hasMessages(6)) // tail result
                ime.mHandler.removeAllMessages() // Do not execute fake-service resume callbacks.
            }
            val drained = CountDownLatch(1)
            worker.mNonUIThreadHandler.post {
                completion.get().onGetSuggestedWords(SuggestedWords.getEmptyInstance())
                drained.countDown()
            }
            await(drained)
            assertEquals(0, oldDelivered.get())
            val current = CountDownLatch(1)
            ime.decode = { it.onGetSuggestedWords(SuggestedWords.getEmptyInstance()) }
            main { worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TYPING, 2) { current.countDown() } }
            await(current)
        } finally { main { logic.destroy(); ime.mHandler.removeAllMessages() } }
    }

    @Test fun unexpectedInsideWordMoveRetiresRequestsWithoutDiscardingComposingText() {
        val app = instrumentation.targetContext
        val preferencesName = "selection-fixture-${UUID.randomUUID()}"
        val ime = main { createIme() }
        try {
            main {
                val info = EditorInfo().apply {
                    packageName = app.packageName
                    inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_AUTO_CORRECT
                }
                val settings = SettingsValues(app,
                    app.getSharedPreferences(preferencesName, Context.MODE_PRIVATE), app.resources,
                    InputAttributes(info, false, app.packageName))
                assertTrue(settings.needsToLookupSuggestions())
                val logic = ime.logic
                logic.mWordComposer.setBatchInputWord("abc")
                position(logic, 3)
                val oldIdentity = ime.mEditorSession.capture()
                assertTrue(logic.onUpdateSelection(3, 3, 2, 2, settings))
                assertFalse(ime.mEditorSession.isCurrent(oldIdentity))
                assertEquals("abc", logic.mWordComposer.typedWord)
                assertTrue(logic.mWordComposer.isCursorFrontOrMiddleOfComposingWord)
                assertEquals(1, ime.cleared)
                ime.mHandler.removeAllMessages()
            }
        } finally {
            main { ime.logic.destroy(); ime.mHandler.removeAllMessages() }
            assertTrue(app.deleteSharedPreferences(preferencesName))
        }
    }
}
