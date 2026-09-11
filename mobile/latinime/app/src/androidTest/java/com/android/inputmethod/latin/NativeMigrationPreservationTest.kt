package com.android.inputmethod.latin

import android.content.Context
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.makedict.FormatSpec
import com.android.inputmethod.latin.utils.ExecutorUtils
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Locale
import java.util.UUID
import java.util.concurrent.TimeUnit
import java.util.concurrent.CountDownLatch

/** Candidate conversion is distinct from the intentionally unavailable production replacement. */
@RunWith(AndroidJUnit4::class)
class NativeMigrationPreservationTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val attributes = mapOf("dictionary" to "synthetic-migration", "locale" to "en_US", "version" to "1")
    private fun fixture(empty: Boolean = false, format: Int = FormatSpec.VERSION402,
        test: (BinaryDictionary, File, File) -> Unit) {
        val root = File(context.cacheDir, "synthetic-migration-${UUID.randomUUID()}")
        check(root.mkdir())
        val path = File(root, "source.dict")
        val dictionary = BinaryDictionary(path.absolutePath, false, Locale.US, Dictionary.TYPE_MAIN,
            format.toLong(), attributes)
        try {
            assertTrue(dictionary.isValidDictionary)
            if (!empty) {
                assertTrue(dictionary.addUnigramEntry("firstcanary", 200, false, false, false, 0))
                assertTrue(dictionary.addUnigramEntry("nextcanary", 180, false, false, false, 0))
                assertTrue(dictionary.addNgramEntry(NgramContext(NgramContext.WordInfo("firstcanary")),
                    "nextcanary", 170, 0))
            }
            assertTrue(dictionary.flushWithGC())
            test(dictionary, path, root)
        } finally { dictionary.close(); check(root.deleteRecursively()) }
    }
    private fun snapshot(root: File) = root.walkTopDown().filter { it.isFile }.associate {
        it.relativeTo(root).invariantSeparatorsPath to MessageDigest.getInstance("SHA-256")
            .digest(it.readBytes()).joinToString("") { byte -> "%02x".format(byte) }
    }
    private fun handle(dictionary: BinaryDictionary) = BinaryDictionary::class.java
        .getDeclaredField("mNativeDict").apply { isAccessible = true }.getLong(dictionary)
    private fun candidate(dictionary: BinaryDictionary, destination: File): Boolean {
        var copied = false
        assertTrue(dictionary.runWithNativeOperationForTesting {
            copied = BinaryDictionary::class.java.declaredMethods.single { it.name == "migrateNative" }
                .apply { isAccessible = true }
                .invoke(null, handle(dictionary), destination.absolutePath, FormatSpec.VERSION403.toLong()) as Boolean
        })
        return copied
    }

    @Test fun productionMigrationRejectsBeforeAnyOwnerOrFilesystemChanges() = fixture { dictionary, _, root ->
        val before = snapshot(root)
        val original = handle(dictionary)
        repeat(2) { assertFalse(dictionary.migrateTo(FormatSpec.VERSION403)) }
        assertEquals(original, handle(dictionary))
        assertTrue(dictionary.isValidDictionary)
        assertEquals(FormatSpec.VERSION402, dictionary.formatVersion)
        assertEquals(200, dictionary.getFrequency("firstcanary"))
        assertEquals(before, snapshot(root))
        assertEquals(listOf("source.dict"), root.list()!!.sorted())
    }

    @Test fun privateCandidateCopies402To403WithoutReplacingSource() = fixture { dictionary, path, root ->
        val before = snapshot(path)
        val destination = File(root, "candidate.dict")
        assertTrue(candidate(dictionary, destination))
        val copied = BinaryDictionary(destination.absolutePath, 0, destination.length(), false,
            Locale.US, Dictionary.TYPE_MAIN, true)
        try {
            assertTrue(copied.isValidDictionary)
            assertEquals(FormatSpec.VERSION403, copied.formatVersion)
            assertEquals(200, copied.getFrequency("firstcanary"))
            assertEquals(180, copied.getFrequency("nextcanary"))
            assertEquals(dictionary.getNgramProbability(NgramContext(NgramContext.WordInfo("firstcanary")), "nextcanary"),
                copied.getNgramProbability(NgramContext(NgramContext.WordInfo("firstcanary")), "nextcanary"))
            assertTrue(copied.isValidNgram(NgramContext(NgramContext.WordInfo("firstcanary")), "nextcanary"))
        } finally { copied.close() }
        assertEquals(200, dictionary.getFrequency("firstcanary"))
        assertEquals(before, snapshot(path))
    }

    @Test fun emptyCandidateSucceedsAndFailedDestinationDoesNotReportSuccessOrChangeSource() {
        fixture(empty = true) { dictionary, path, root ->
            val before = snapshot(path)
            val destination = File(root, "empty-candidate.dict")
            assertTrue(candidate(dictionary, destination))
            val copied = BinaryDictionary(destination.absolutePath, 0, destination.length(), false,
                Locale.US, Dictionary.TYPE_MAIN, true)
            try {
                assertTrue(copied.isValidDictionary)
                assertEquals(FormatSpec.VERSION403, copied.formatVersion)
                assertEquals(Dictionary.NOT_A_PROBABILITY, copied.getFrequency("absentcanary"))
            } finally { copied.close() }
            assertEquals(before, snapshot(path))
        }
        fixture { dictionary, _, root ->
            val before = snapshot(root)
            assertFalse(candidate(dictionary, File(root, "missing-parent/candidate.dict")))
            assertEquals(200, dictionary.getFrequency("firstcanary"))
            assertEquals(before, snapshot(root))
        }
    }

    private class LegacyExpandable(context: Context, path: File) : ExpandableBinaryDictionary(
        context, "synthetic-preservation", Locale.US, Dictionary.TYPE_MAIN, path) {
        var initialLoads = 0
        override fun loadInitialContentsLocked() { initialLoads++ }
        fun requestAutomaticRebuild() { setNeedsToRecreate() }
    }
    private fun drainKeyboardExecutor() {
        // Production uses this single-thread executor; a queued barrier follows the real reload.
        ExecutorUtils.getBackgroundExecutor(ExecutorUtils.KEYBOARD).submit {}.get(5, TimeUnit.SECONDS)
    }
    private fun markUnavailable(wrapper: LegacyExpandable, owner: BinaryDictionary) {
        // Exercise the retirement boundary deterministically, without corrupting a native parser.
        ExpandableBinaryDictionary::class.java.getDeclaredMethod(
            "retireCorruptedDictionary", BinaryDictionary::class.java)
            .apply { isAccessible = true }.invoke(wrapper, owner)
    }
    @Test fun queuedMutationsAndFlushDoNotTouchOwnerAfterCorruptionRetirementIsRequested() =
        fixture(format = FormatSpec.VERSION403) { _, path, root ->
            val wrapper = LegacyExpandable(context, path)
            val release = CountDownLatch(1)
            try {
                wrapper.reloadDictionaryIfRequired()
                drainKeyboardExecutor()
                val owner = wrapper.binaryDictionary!!
                val before = snapshot(root)
                val entered = CountDownLatch(1)
                val executor = ExecutorUtils.getBackgroundExecutor(ExecutorUtils.KEYBOARD)
                executor.submit { entered.countDown(); check(release.await(5, TimeUnit.SECONDS)) }
                assertTrue(entered.await(5, TimeUnit.SECONDS))
                wrapper.addUnigramEntry("blockedcanary", 220, false, false, 0)
                wrapper.removeUnigramEntryDynamically("firstcanary")
                wrapper.addNgramEntry(NgramContext(NgramContext.WordInfo("nextcanary")),
                    "firstcanary", 210, 0)
                wrapper.updateEntriesForWord(NgramContext.EMPTY_PREV_WORDS_INFO,
                    "blockedcanary", true, 1, 0)
                wrapper.runGCIfRequired(false)
                wrapper.asyncFlushBinaryDictionary()
                // Probe precedes retirement: this distinguishes skipped updates from an update
                // that was merely discarded by a later close without being flushed.
                val probe = executor.submit<Boolean> {
                    owner.getFrequency("blockedcanary") == Dictionary.NOT_A_PROBABILITY &&
                        owner.getFrequency("firstcanary") == 200 &&
                        !owner.isValidNgram(NgramContext(NgramContext.WordInfo("nextcanary")), "firstcanary")
                }
                markUnavailable(wrapper, owner)
                release.countDown()
                assertTrue(probe.get(5, TimeUnit.SECONDS))
                drainKeyboardExecutor()
                assertNull(wrapper.binaryDictionary)
                assertEquals(0L, handle(owner))
                assertEquals(before, snapshot(root))
            } finally { release.countDown(); wrapper.close(); drainKeyboardExecutor() }
        }

    @Test fun explicitClearReplacesBlockedOwnerAndStaleRetirementCannotCloseReplacement() =
        fixture(format = FormatSpec.VERSION403) { _, path, _ ->
            val wrapper = LegacyExpandable(context, path)
            val release = CountDownLatch(1)
            try {
                wrapper.reloadDictionaryIfRequired()
                drainKeyboardExecutor()
                val oldOwner = wrapper.binaryDictionary!!
                val entered = CountDownLatch(1)
                ExecutorUtils.getBackgroundExecutor(ExecutorUtils.KEYBOARD).submit {
                    entered.countDown(); check(release.await(5, TimeUnit.SECONDS))
                }
                assertTrue(entered.await(5, TimeUnit.SECONDS))
                wrapper.clear()
                markUnavailable(wrapper, oldOwner)
                release.countDown()
                drainKeyboardExecutor()
                val replacement = wrapper.binaryDictionary!!
                assertNotSame(oldOwner, replacement)
                assertEquals(0L, handle(oldOwner))
                assertTrue(replacement.isValidDictionary)
                wrapper.addUnigramEntry("freshcanary", 190, false, false, 0)
                wrapper.asyncFlushBinaryDictionary()
                drainKeyboardExecutor()
                assertSame(replacement, wrapper.binaryDictionary)
                assertEquals(190, replacement.getFrequency("freshcanary"))
            } finally { release.countDown(); wrapper.close(); drainKeyboardExecutor() }
        }
    @Test fun actualAsyncReloadTwicePreservesLegacyFilesWithoutRecreation() = fixture { dictionary, path, root ->
        val before = snapshot(root)
        val wrapper = LegacyExpandable(context, path)
        try {
            repeat(2) {
                wrapper.reloadDictionaryIfRequired()
                drainKeyboardExecutor()
                assertNull(wrapper.binaryDictionary)
                assertEquals(0, wrapper.initialLoads)
                assertEquals(before, snapshot(root))
                assertEquals(200, dictionary.getFrequency("firstcanary"))
            }
        } finally { wrapper.close(); drainKeyboardExecutor() }
    }

    @Test fun malformedAndUnsupportedExistingFilesArePreservedAcrossReloadAttempts() {
        for (unsupported in listOf(false, true)) {
            val root = File(context.cacheDir, "synthetic-unavailable-${UUID.randomUUID()}")
            check(root.mkdir())
            val path = File(root, "unavailable.dict")
            check(path.mkdir())
            File(path, "unavailable.dict.header").writeBytes(if (unsupported)
                ByteBuffer.allocate(13).order(ByteOrder.BIG_ENDIAN)
                    .putInt(0x9BC13AFEL.toInt()).putShort(401.toShort()).putShort(0.toShort())
                    .putInt(12).put(0.toByte()).array()
                else byteArrayOf(1, 2, 3))
            File(path, "synthetic-user-data").writeText("preserve-this-synthetic-canary")
            val before = snapshot(root)
            val wrapper = LegacyExpandable(context, path)
            try {
                repeat(2) {
                    wrapper.reloadDictionaryIfRequired()
                    drainKeyboardExecutor()
                    assertNull(wrapper.binaryDictionary)
                    assertEquals(0, wrapper.initialLoads)
                    assertEquals(before, snapshot(root))
                }
                // The explicit clear API remains separate from failed automatic recovery.
                wrapper.clear()
                drainKeyboardExecutor()
                assertTrue(wrapper.binaryDictionary!!.isValidDictionary)
                assertFalse(File(path, "synthetic-user-data").exists())
            } finally {
                wrapper.close(); drainKeyboardExecutor(); check(root.deleteRecursively())
            }
        }
    }

    @Test fun valid403StillLoadsAndAutomaticRebuildFlagCannotDeleteExistingData() =
        fixture(format = FormatSpec.VERSION403) { _, path, root ->
            val before = snapshot(root)
            val wrapper = LegacyExpandable(context, path)
            try {
                wrapper.reloadDictionaryIfRequired()
                drainKeyboardExecutor()
                assertNotNull(wrapper.binaryDictionary)
                assertEquals(200, wrapper.binaryDictionary!!.getFrequency("firstcanary"))
                assertEquals(0, wrapper.initialLoads)
                wrapper.requestAutomaticRebuild()
                repeat(2) {
                    wrapper.reloadDictionaryIfRequired()
                    drainKeyboardExecutor()
                    assertNull(wrapper.binaryDictionary)
                    assertEquals(0, wrapper.initialLoads)
                    assertEquals(before, snapshot(root))
                }
            } finally { wrapper.close(); drainKeyboardExecutor() }
        }
}
