package org.utterleaf.keyboard

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.keyboard.Key
import com.android.inputmethod.keyboard.Keyboard
import com.android.inputmethod.keyboard.internal.KeyboardIconsSet
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

/** JNI admission controls, not language quality or physical gesture recognition evidence. */
@RunWith(AndroidJUnit4::class)
class NativeSuggestionBoundaryControlTest {
    private fun fixture(test: (Long, Long, DicTraverseSession) -> Unit) {
        val directory = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir,
            "synthetic-jni-boundary-${UUID.randomUUID()}")
        check(directory.mkdir())
        val dictionary = BinaryDictionary(File(directory, "fixture.dict").absolutePath, false,
            Locale.US, Dictionary.TYPE_MAIN, FormatSpec.VERSION4.toLong(),
            mapOf("dictionary" to "synthetic-test", "locale" to "en_US", "version" to "1"))
        val keyboard = Keyboard(KeyboardParams().apply {
            GRID_WIDTH = 1; GRID_HEIGHT = 1
            mOccupiedWidth = 100; mOccupiedHeight = 100
            onAddKey(Key("a", KeyboardIconsSet.ICON_UNDEFINED, 'a'.code,
                null, null, 0, Key.BACKGROUND_TYPE_NORMAL, 0, 0, 100, 100, 0, 0))
        })
        val proximity = keyboard.proximityInfo
        val gate = proximity.javaClass.getDeclaredField("mNativeOperations")
            .apply { isAccessible = true }.get(proximity) as NativeOperationGate
        val lease = checkNotNull(proximity.acquireNativeOperation())
        try {
            assertTrue(dictionary.addUnigramEntry("a", 200, false, false, false, 0))
            assertTrue(dictionary.runWithNativeOperationForTesting {
                val handle = BinaryDictionary::class.java.getDeclaredField("mNativeDict")
                    .apply { isAccessible = true }.getLong(dictionary)
                assertNotEquals(0L, handle)
                assertNotEquals(0L, proximity.nativeProximityInfo)
                val session = DicTraverseSession(Locale.US, handle, 0)
                try { test(handle, proximity.nativeProximityInfo, session) }
                finally { session.close() }
            })
        } finally {
            lease.close(); gate.close(); dictionary.close()
            check(directory.deleteRecursively())
        }
    }

    private fun request(dict: Long, proximity: Long, session: DicTraverseSession,
                        size: Int, gesture: Boolean): Pair<Int, Float> {
        val count = intArrayOf(91)
        val weight = floatArrayOf(WEIGHT_SENTINEL)
        val args: Array<Any?> = arrayOf(
            dict, proximity, session.session,
            IntArray(size) { 50 }, IntArray(size) { 50 }, IntArray(size) { it * 8 },
            IntArray(size), IntArray(48) { if (it < size && !gesture) 'a'.code else -1 }, size,
            intArrayOf(if (gesture) 1 else 0, 0, 1, 0, 1000),
            arrayOfNulls<IntArray>(3), BooleanArray(3), 0,
            count, IntArray(48 * 18), IntArray(18), IntArray(18), IntArray(18), IntArray(1), weight)
        BinaryDictionary::class.java.declaredMethods.single { it.name == "getSuggestionsNative" }
            .apply { isAccessible = true }.invoke(null, *args)
        return count[0] to weight[0]
    }

    @Test fun validTapAndPredictionReachNativeOutputWhileTap48IsRejectedWhole() = fixture { dict, proximity, session ->
        val prediction = request(dict, proximity, session, 0, false)
        assertEquals(Dictionary.NOT_A_WEIGHT_OF_LANG_MODEL_VS_SPATIAL_MODEL, prediction.second, 0f)
        val tap47 = request(dict, proximity, session, 47, false)
        assertEquals("TypingScoring must produce its adjusted weight", 1f, tap47.second, 0f)
        assertTrue(tap47.first in 0..18)
        val tap48 = request(dict, proximity, session, 48, false)
        assertEquals(0, tap48.first)
        assertEquals(WEIGHT_SENTINEL, tap48.second, 0f)
        // The supported owner remains usable after the adjacent rejected boundary.
        assertEquals(1f, request(dict, proximity, session, 1, false).second, 0f)
    }

    @Test fun boundedGesturesReachSafeUnavailablePolicyWhileInvalidSizesAreRejected() = fixture { dict, proximity, session ->
        for (size in listOf(1, 4096)) {
            val unavailable = request(dict, proximity, session, size, true)
            assertEquals("Foundation has no gesture policy", 0, unavailable.first)
            assertEquals("Well-shaped request must reach empty native output", -1f, unavailable.second, 0f)
        }
        for (size in listOf(0, 4097)) {
            val rejected = request(dict, proximity, session, size, true)
            assertEquals(0, rejected.first)
            assertEquals("Invalid gesture must not enter output/decoding", WEIGHT_SENTINEL, rejected.second, 0f)
        }
    }

    companion object {
        // SuggestionsOutputUtils treats ANY negative weight as a request for adjustment.
        // TypingScoring returns 1; prediction/absent gesture policy output defaults to -1.
        // Rejected JNI input returns before the unconditional native weight output.
        private const val WEIGHT_SENTINEL = -1234f
    }
}
