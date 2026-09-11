package org.utterleaf.keyboard

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.keyboard.Keyboard
import com.android.inputmethod.keyboard.internal.KeyboardParams
import com.android.inputmethod.latin.BinaryDictionary
import com.android.inputmethod.latin.Dictionary
import com.android.inputmethod.latin.DicTraverseSession
import com.android.inputmethod.latin.makedict.FormatSpec
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.Locale
import java.util.UUID
import java.lang.reflect.InvocationTargetException

/** Calls the private JNI entry with real owned handles and malformed synthetic arrays. */
@RunWith(AndroidJUnit4::class)
class NativeSuggestionBoundsTest {
    private fun fixture(test: (Long, Long, DicTraverseSession) -> Unit) {
        val directory = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir,
            "synthetic-jni-bounds-${UUID.randomUUID()}")
        check(directory.mkdir())
        val dictionary = BinaryDictionary(File(directory, "fixture.dict").absolutePath, false,
            Locale.US, Dictionary.TYPE_MAIN, FormatSpec.VERSION4.toLong(),
            mapOf("dictionary" to "synthetic-test", "locale" to "en_US", "version" to "1"))
        val keyboard = Keyboard(KeyboardParams().apply {
            GRID_WIDTH = 1; GRID_HEIGHT = 1
            mOccupiedWidth = 100; mOccupiedHeight = 100
            mMostCommonKeyWidth = 10; mMostCommonKeyHeight = 10
        })
        val proximity = keyboard.proximityInfo
        val proximityLease = checkNotNull(proximity.acquireNativeOperation())
        try {
            assertTrue(dictionary.runWithNativeOperationForTesting {
                val pointer = BinaryDictionary::class.java.getDeclaredField("mNativeDict")
                    .apply { isAccessible = true }.getLong(dictionary)
                assertNotEquals(0L, pointer)
                val session = DicTraverseSession(Locale.US, pointer, 0)
                try { test(pointer, proximity.nativeProximityInfo, session) }
                finally { session.close() }
            })
        } finally {
            proximityLease.close(); dictionary.close()
            check(directory.deleteRecursively())
        }
    }

    private fun arguments(dict: Long, proximity: Long, session: DicTraverseSession): Array<Any?> = arrayOf(
        dict, proximity, session.session,
        IntArray(48), IntArray(48), IntArray(48), IntArray(48), IntArray(48), 0,
        intArrayOf(0, 0, 1, 0, 1000), arrayOfNulls<IntArray>(3), BooleanArray(3), 0,
        intArrayOf(7), IntArray(48 * 18), IntArray(18), IntArray(18), IntArray(18),
        IntArray(1), floatArrayOf(-1f))

    private fun invoke(args: Array<Any?>) {
        val method = BinaryDictionary::class.java.declaredMethods.single { it.name == "getSuggestionsNative" }
            .apply { isAccessible = true }
        method.invoke(null, *args)
    }

    @Test fun malformedCountsAndInputShapesReturnNoSuggestions() = fixture { dict, proximity, session ->
        val mutations = listOf<Pair<String, (Array<Any?>) -> Unit>>(
            "negative size" to { it[8] = -1 },
            "huge size" to { it[8] = Int.MAX_VALUE },
            "over gesture budget" to {
                it[8] = 4097; it[9] = intArrayOf(1, 0, 1, 0, 1000)
                for (index in 3..6) it[index] = IntArray(4097)
            },
            "empty gesture" to { it[9] = intArrayOf(1, 0, 1, 0, 1000) },
            "tap word at native limit" to { it[8] = 48 },
            "negative context count" to { it[12] = -1 },
            "oversized context count" to { it[12] = 4 },
            "short context container" to { it[12] = 2; it[10] = arrayOfNulls<IntArray>(1) },
            "short context flags" to { it[12] = 2; it[11] = BooleanArray(1) },
            "oversized context word" to { it[12] = 1; it[10] = arrayOf(IntArray(49)) },
            "short options" to { it[9] = IntArray(4) },
            "oversized options" to { it[9] = IntArray(6) },
            "oversized codepoints" to { it[7] = IntArray(49) },
            "short codepoint buffer" to { it[7] = IntArray(47) },
            "short coordinates" to { it[8] = 1; it[3] = IntArray(0) },
            "missing proximity for typing" to { it[8] = 1; it[1] = 0L }
        )
        for ((label, mutate) in mutations) {
            val args = arguments(dict, proximity, session)
            mutate(args)
            invoke(args)
            assertEquals(label, 0, (args[13] as IntArray)[0])
        }
        // Rejection must leave the same native owners usable for a later valid prediction.
        invoke(arguments(dict, proximity, session))
    }

    @Test fun missingOrShortJniBuffersAreRejectedWithoutPendingExceptions() = fixture { dict, proximity, session ->
        for (index in listOf(3, 4, 5, 6, 7, 9, 10, 11, 14, 15, 16, 17, 18, 19)) {
            val args = arguments(dict, proximity, session)
            args[index] = null
            invoke(args)
            assertEquals("null buffer $index", 0, (args[13] as IntArray)[0])
        }
        for (index in 14..19) {
            val args = arguments(dict, proximity, session)
            args[index] = if (index == 19) FloatArray(0) else IntArray(0)
            invoke(args)
            assertEquals("short output $index", 0, (args[13] as IntArray)[0])
        }
        for (count in listOf(null, IntArray(0))) {
            val args = arguments(dict, proximity, session)
            args[13] = count
            invoke(args)
        }
        invoke(arguments(dict, proximity, session))
    }

    @Test fun malformedSharedContextThrowsBeforeDictionaryMutation() = fixture { dict, _, _ ->
        val methods = BinaryDictionary::class.java.declaredMethods
        val update = methods.single { it.name == "updateEntriesForWordWithNgramContextNative" }
            .apply { isAccessible = true }
        val frequency = methods.single { it.name == "getProbabilityNative" }.apply { isAccessible = true }
        val target = "synthetic".map { it.code }.toIntArray()
        assertEquals(Dictionary.NOT_A_PROBABILITY, frequency.invoke(null, dict, target))
        for ((previous, flags) in listOf(
            arrayOfNulls<IntArray>(4) to BooleanArray(4),
            arrayOfNulls<IntArray>(2) to BooleanArray(1),
            arrayOf(IntArray(49)) to BooleanArray(1)
        )) {
            try {
                update.invoke(null, dict, previous, flags, target, true, 1, 0)
                fail("Malformed context entered a native dictionary mutation")
            } catch (failure: InvocationTargetException) {
                assertTrue(failure.cause is IllegalArgumentException)
            }
            assertEquals(Dictionary.NOT_A_PROBABILITY, frequency.invoke(null, dict, target))
        }
    }
}
