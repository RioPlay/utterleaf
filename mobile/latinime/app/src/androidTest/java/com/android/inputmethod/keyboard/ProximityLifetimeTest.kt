package com.android.inputmethod.keyboard

import android.content.Context
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.keyboard.internal.KeyboardParams
import com.android.inputmethod.latin.*
import com.android.inputmethod.latin.common.ComposedData
import com.android.inputmethod.latin.common.InputPointers
import com.android.inputmethod.latin.settings.SettingsValuesForSuggestion
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/** Deterministic finalizer retirement during facade decoding, without relying on GC timing. */
@RunWith(AndroidJUnit4::class)
class ProximityLifetimeTest {
    @Test fun unsizedKeyboardDoesNotEnterDecoder() {
        val keyboard = Keyboard(KeyboardParams().apply { GRID_WIDTH = 1; GRID_HEIGHT = 1 })
        assertEquals(0L, keyboard.proximityInfo.nativeProximityInfo)
        val dictionary = object : Dictionary(Dictionary.TYPE_MAIN, Locale.US) {
            override fun isInDictionary(word: String) = false
            override fun getSuggestions(data: ComposedData, context: NgramContext, handle: Long,
                settings: SettingsValuesForSuggestion, session: Int, weight: Float, weights: FloatArray?):
                ArrayList<SuggestedWords.SuggestedWordInfo>? = error("Unsized keyboard entered decoder")
        }
        val facilitator = object : DictionaryFacilitatorImpl() {
            override fun createMainDictionary(context: Context, locale: Locale): Dictionary = dictionary
            override fun executeDictionaryLoad(task: Runnable) { task.run() }
        }
        try {
            facilitator.resetDictionaries(InstrumentationRegistry.getInstrumentation().targetContext,
                Locale.US, false, false, false, null, "", null)
            assertTrue(facilitator.getSuggestionResults(ComposedData(InputPointers(1), false, ""),
                NgramContext.EMPTY_PREV_WORDS_INFO, keyboard.proximityInfo, SettingsValuesForSuggestion(true),
                0, SuggestedWords.INPUT_STYLE_TYPING).isEmpty())
        } finally { facilitator.closeDictionaries() }
    }

    private fun retirementDuringDecode(throws: Boolean) {
        val keyboard = Keyboard(KeyboardParams().apply {
            GRID_WIDTH = 1; GRID_HEIGHT = 1
            mOccupiedWidth = 100; mOccupiedHeight = 100
            mMostCommonKeyWidth = 10; mMostCommonKeyHeight = 10
        })
        val proximity = keyboard.proximityInfo
        val nativePointer = ProximityInfo::class.java.getDeclaredField("mNativeProximityInfo")
            .apply { isAccessible = true }
        val finalizeMethod = ProximityInfo::class.java.getDeclaredMethod("finalize")
            .apply { isAccessible = true }
        assertNotEquals(0L, nativePointer.getLong(proximity))
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val completed = CountDownLatch(1)
        val failure = AtomicReference<Throwable>()
        val dictionary = object : Dictionary(Dictionary.TYPE_MAIN, Locale.US) {
            override fun isInDictionary(word: String) = false
            override fun getSuggestions(data: ComposedData, context: NgramContext, handle: Long,
                settings: SettingsValuesForSuggestion, session: Int, weight: Float, weights: FloatArray?):
                ArrayList<SuggestedWords.SuggestedWordInfo>? {
                assertEquals(nativePointer.getLong(proximity), handle)
                entered.countDown()
                check(release.await(5, TimeUnit.SECONDS))
                assertNotEquals("Proximity resource retired during decoder use", 0L, nativePointer.getLong(proximity))
                if (throws) throw IllegalStateException("synthetic decoder failure")
                return null
            }
        }
        val facilitator = object : DictionaryFacilitatorImpl() {
            override fun createMainDictionary(context: Context, locale: Locale): Dictionary = dictionary
            override fun executeDictionaryLoad(task: Runnable) { task.run() }
        }
        facilitator.resetDictionaries(InstrumentationRegistry.getInstrumentation().targetContext,
            Locale.US, false, false, false, null, "", null)
        val worker = Thread {
            try {
                facilitator.getSuggestionResults(ComposedData(InputPointers(1), false, ""),
                    NgramContext.EMPTY_PREV_WORDS_INFO, proximity, SettingsValuesForSuggestion(true),
                    0, SuggestedWords.INPUT_STYLE_TYPING)
                if (throws) fail("Expected decoder exception")
            } catch (error: Throwable) {
                if (!(throws && error is IllegalStateException && error.message == "synthetic decoder failure"))
                    failure.set(error)
            } finally { completed.countDown() }
        }
        worker.start()
        try {
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            finalizeMethod.invoke(proximity)
            assertNotEquals(0L, nativePointer.getLong(proximity))
            release.countDown()
            assertTrue(completed.await(5, TimeUnit.SECONDS))
            failure.get()?.let { throw it }
            assertEquals(0L, nativePointer.getLong(proximity))
            // A retired owner cannot supply a handle to another decoder.
            assertTrue(facilitator.getSuggestionResults(ComposedData(InputPointers(1), false, ""),
                NgramContext.EMPTY_PREV_WORDS_INFO, proximity, SettingsValuesForSuggestion(true),
                0, SuggestedWords.INPUT_STYLE_TYPING).isEmpty())
        } finally {
            release.countDown(); worker.join(5000); facilitator.closeDictionaries()
            finalizeMethod.invoke(proximity)
        }
    }

    @Test fun proximityRetirementWaitsForAdmittedDecoder() = retirementDuringDecode(false)
    @Test fun decoderExceptionStillReleasesProximityOwner() = retirementDuringDecode(true)
}
