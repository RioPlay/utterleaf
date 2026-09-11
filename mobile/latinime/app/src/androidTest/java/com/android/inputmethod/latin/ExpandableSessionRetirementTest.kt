package com.android.inputmethod.latin

import android.util.SparseArray
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.common.ComposedData
import com.android.inputmethod.latin.common.InputPointers
import com.android.inputmethod.latin.makedict.FormatSpec
import com.android.inputmethod.latin.settings.SettingsValuesForSuggestion
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.Locale
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import java.util.concurrent.locks.ReentrantReadWriteLock

/** Exercises wrapper delegation with an injected synthetic dictionary; no factory loading. */
@RunWith(AndroidJUnit4::class)
class ExpandableSessionRetirementTest {
    @Test fun retirementReachesNativeGateWhileWrapperWriteLockIsHeld() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val directory = File(context.cacheDir, "synthetic-expandable-retirement-${UUID.randomUUID()}")
        check(directory.mkdir())
        val path = File(directory, "fixture.dict")
        val dictionary = BinaryDictionary(path.absolutePath, false, Locale.US, Dictionary.TYPE_MAIN,
            FormatSpec.VERSION4.toLong(), mapOf("dictionary" to "synthetic-test", "locale" to "en_US", "version" to "1"))
        val wrapper = object : ExpandableBinaryDictionary(context, "synthetic-wrapper", Locale.US,
            Dictionary.TYPE_USER, path) {
            override fun loadInitialContentsLocked() = error("Synthetic test must not load a dynamic dictionary")
        }
        val dictionaryField = ExpandableBinaryDictionary::class.java.getDeclaredField("mBinaryDictionary")
            .apply { isAccessible = true }
        val wrapperLock = ExpandableBinaryDictionary::class.java.getDeclaredField("mLock")
            .apply { isAccessible = true }.get(wrapper) as ReentrantReadWriteLock
        val sessionsField = BinaryDictionary::class.java.getDeclaredField("mDicTraverseSessions")
            .apply { isAccessible = true }
        val locked = CountDownLatch(1)
        val release = CountDownLatch(1)
        val retired = CountDownLatch(1)
        val holdingLock = AtomicBoolean()
        val failure = AtomicReference<Throwable>()
        val lockOwner = Thread {
            wrapperLock.writeLock().lock()
            try {
                holdingLock.set(true); locked.countDown()
                check(release.await(5, TimeUnit.SECONDS))
            } catch (error: Throwable) { failure.compareAndSet(null, error) }
            finally { holdingLock.set(false); wrapperLock.writeLock().unlock() }
        }
        val retireCaller = Thread {
            try { wrapper.clearSession() } catch (error: Throwable) { failure.compareAndSet(null, error) }
            finally { retired.countDown() }
        }
        try {
            assertTrue(dictionary.addUnigramEntry("syntheticfixture", 200, false, false, false, 0))
            assertTrue(dictionary.flush())
            fun fileContents() = directory.walkTopDown().filter { it.isFile }
                .associate { it.relativeTo(directory).path to it.readBytes().toList() }
            val beforeFiles = fileContents()
            assertFalse(beforeFiles.isEmpty())
            assertNotNull(dictionary.getSuggestions(ComposedData(InputPointers(1), false, ""),
                NgramContext.EMPTY_PREV_WORDS_INFO, 0, SettingsValuesForSuggestion(true), 0, 1f, null))
            assertEquals(1, (sessionsField.get(dictionary) as SparseArray<*>).size())
            wrapperLock.writeLock().lock()
            try { dictionaryField.set(wrapper, dictionary) } finally { wrapperLock.writeLock().unlock() }
            lockOwner.start(); assertTrue(locked.await(5, TimeUnit.SECONDS))
            retireCaller.start()
            assertTrue("Retirement waited for the wrapper worker lock", retired.await(1, TimeUnit.SECONDS))
            failure.get()?.let { throw it }
            assertTrue("Wrapper lock must remain held during the assertions", holdingLock.get())
            assertEquals("Retirement was only queued behind the blocked wrapper worker", 0,
                (sessionsField.get(dictionary) as SparseArray<*>).size())
            assertTrue(dictionary.isValidDictionary)
            assertEquals(200, dictionary.getFrequency("syntheticfixture"))
            assertEquals(beforeFiles, fileContents())
        } finally {
            release.countDown(); lockOwner.join(5000); retireCaller.join(5000)
            // Avoid the asynchronous production close queue in this injected fixture.
            dictionaryField.set(wrapper, null)
            dictionary.close()
            check(directory.deleteRecursively())
        }
    }
}
