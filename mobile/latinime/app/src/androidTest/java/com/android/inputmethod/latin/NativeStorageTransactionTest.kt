package com.android.inputmethod.latin

import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.utterleaf.keyboard.StorageFaults
import java.io.File
import java.security.MessageDigest
import java.util.Locale
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class NativeStorageTransactionTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private fun handle(dictionary: BinaryDictionary) = BinaryDictionary::class.java
        .getDeclaredField("mNativeDict").apply { isAccessible = true }.getLong(dictionary)
    private fun open(path: File) = BinaryDictionary(path.absolutePath, 0, path.length(), false,
        Locale.US, Dictionary.TYPE_MAIN, true)
    private fun hashes(path: File) = path.walkTopDown().filter { it.isFile }.associate {
        it.relativeTo(path).invariantSeparatorsPath to MessageDigest.getInstance("SHA-256")
            .digest(it.readBytes()).toList()
    }
    private fun fixture(format: Int, test: (BinaryDictionary, File, File) -> Unit) {
        val root = File(context.cacheDir, "synthetic-storage-${UUID.randomUUID()}")
        check(root.mkdir())
        val path = File(root, "canary.dict")
        val dictionary = BinaryDictionary(path.absolutePath, false, Locale.US, Dictionary.TYPE_MAIN,
            format.toLong(), mapOf("dictionary" to "synthetic-storage", "locale" to "en_US", "version" to "1"))
        try {
            assertTrue(dictionary.addUnigramEntry("oldcanary", 200, false, false, false, 0))
            assertTrue(dictionary.flushWithGC())
            test(dictionary, path, root)
        } finally { dictionary.close(); check(root.deleteRecursively()) }
    }
    private fun configure(dictionary: BinaryDictionary, stage: Int, mode: Int) {
        assertTrue(dictionary.runWithNativeOperationForTesting {
            StorageFaults.configureNative(handle(dictionary), stage, mode)
        })
    }

    @Test fun failuresPreserveCompleteDiskGenerationsAndQuarantinePrivateOwner() {
        for (format in listOf(402, 403)) for (stage in 1..7) fixture(format) { dictionary, path, root ->
            val originalHandle = handle(dictionary)
            val originalFiles = hashes(path)
            assertTrue(dictionary.addUnigramEntry("newcanary", 210, false, false, false, 0))
            configure(dictionary, stage, 1)
            assertFalse("format=$format stage=$stage", dictionary.flushWithGC())
            assertEquals(originalHandle, handle(dictionary))
            assertTrue(dictionary.isCorrupted)
            assertFalse(dictionary.isValidDictionary)
            assertFalse(dictionary.flushWithGCIfHasUpdated())
            assertTrue(dictionary.runWithNativeOperationForTesting {
                // The separately registered traversal JNI must reject an unavailable policy.
                val traversal = DicTraverseSession(Locale.US, originalHandle, 0)
                traversal.close()
                assertEquals(0L, traversal.session)
            })
            assertEquals(Dictionary.NOT_A_PROBABILITY, dictionary.getFrequency("oldcanary"))
            assertFalse(dictionary.addUnigramEntry("unavailablecanary", 220, false, false, false, 0))
            val fresh = open(path)
            try {
                assertTrue(fresh.isValidDictionary)
                assertEquals(200, fresh.getFrequency("oldcanary"))
                assertEquals(if (stage < 5) Dictionary.NOT_A_PROBABILITY else 210,
                    fresh.getFrequency("newcanary"))
                if (stage < 5) assertEquals(originalFiles, hashes(path))
                if (stage == 5 || stage == 6) {
                    val backup = File(root, "canary.dict.utterleaf-stage/canary.dict")
                    assertEquals(originalFiles, hashes(backup))
                }
                // A fresh owner can clean only recognized staged data after validating/syncing
                // the current generation; the old unavailable owner is never reused.
                assertTrue(fresh.addUnigramEntry("recoveredcanary", 190, false, false, false, 0))
                assertTrue(fresh.flush())
                assertEquals(190, fresh.getFrequency("recoveredcanary"))
                assertFalse(File(root, "canary.dict.utterleaf-stage").exists())
            } finally { fresh.close() }
        }
    }

    @Test fun aSecondLoadedOwnerCannotOverwriteANewerGeneration() {
        for (format in listOf(402, 403)) fixture(format) { first, path, _ ->
            val stale = open(path)
            try {
                assertTrue(first.addUnigramEntry("firstwriter", 210, false, false, false, 0))
                assertTrue(first.flush())
                val published = hashes(path)
                assertTrue(stale.addUnigramEntry("stalewriter", 220, false, false, false, 0))
                assertFalse(stale.flushWithGC())
                assertEquals(published, hashes(path))
                val fresh = open(path)
                try {
                    assertEquals(210, fresh.getFrequency("firstwriter"))
                    assertEquals(Dictionary.NOT_A_PROBABILITY, fresh.getFrequency("stalewriter"))
                } finally { fresh.close() }
            } finally { stale.close() }
        }
    }

    @Test fun overlappingWriterAdmissionReturnsPromptlyWithoutDisturbingPausedPublish() =
        fixture(403) { first, path, _ ->
            val second = open(path)
            val worker = Executors.newSingleThreadExecutor()
            val contender = Executors.newSingleThreadExecutor()
            var pausedHandle = 0L
            try {
                assertTrue(first.addUnigramEntry("firstwriter", 210, false, false, false, 0))
                assertTrue(second.addUnigramEntry("secondwriter", 220, false, false, false, 0))
                configure(first, 4, 2)
                pausedHandle = handle(first)
                val result = worker.submit<Boolean> { first.flush() }
                val deadline = SystemClock.elapsedRealtime() + 5000
                while (StorageFaults.reachedNative(pausedHandle) != 4 && SystemClock.elapsedRealtime() < deadline) {
                    SystemClock.sleep(5)
                }
                assertEquals(4, StorageFaults.reachedNative(pausedHandle))
                // Another thread owns the native lease; busy must not mean unavailable.
                assertTrue(first.isValidDictionary)
                val start = SystemClock.elapsedRealtime()
                assertFalse(contender.submit<Boolean> { second.flush() }.get(1, TimeUnit.SECONDS))
                assertTrue(SystemClock.elapsedRealtime() - start < 1000)
                StorageFaults.releaseNative(pausedHandle)
                pausedHandle = 0
                assertTrue(result.get(5, TimeUnit.SECONDS))
                assertEquals(210, first.getFrequency("firstwriter"))
            } finally {
                if (pausedHandle != 0L) StorageFaults.releaseNative(pausedHandle)
                worker.shutdown(); check(worker.awaitTermination(5, TimeUnit.SECONDS))
                contender.shutdown(); check(contender.awaitTermination(5, TimeUnit.SECONDS))
                second.close()
            }
        }

    @Test fun unrecognizedStagingAndAdditionalUserFilesArePreserved() {
        for (insideOriginal in listOf(false, true)) fixture(403) { dictionary, path, root ->
            val directory = if (insideOriginal) path else File(root, "canary.dict.utterleaf-stage").also {
                check(it.mkdir())
            }
            File(directory, "synthetic-user-data").writeText("synthetic retained data")
            val before = hashes(root)
            assertTrue(dictionary.addUnigramEntry("newcanary", 210, false, false, false, 0))
            assertFalse(dictionary.flush())
            assertEquals(before, hashes(root))
        }
    }
}
