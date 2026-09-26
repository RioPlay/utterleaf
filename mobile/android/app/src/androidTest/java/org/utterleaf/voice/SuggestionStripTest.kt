package org.utterleaf.voice

import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.text.InputType
import android.view.accessibility.AccessibilityNodeInfo
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.InputConnectionWrapper
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference
import java.util.Collections

/**
 * Live-IME evidence for the suggestion strip: completions of the composing
 * word, tap-to-complete, and the restricted-field gates. These checks run the
 * real typing IME against the contract activity's editor.
 */
@RunWith(AndroidJUnit4::class)
class SuggestionStripTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext

    private fun <T> main(block: () -> T): T {
        val result = java.util.concurrent.atomic.AtomicReference<T>()
        instrumentation.runOnMainSync { result.set(block()) }
        return result.get()
    }

    private fun await(message: String, condition: () -> Boolean) {
        val deadline = android.os.SystemClock.elapsedRealtime() + 10_000
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            if (condition()) return
            Thread.sleep(50)
        }
        throw AssertionError(message)
    }

    private fun node(label: String): AccessibilityNodeInfo? {
        fun find(current: AccessibilityNodeInfo): AccessibilityNodeInfo? {
            if (current.contentDescription?.toString() == label && current.isClickable && current.isVisibleToUser) return current
            for (index in 0 until current.childCount) current.getChild(index)?.let(::find)?.let { return it }
            return null
        }
        return instrumentation.uiAutomation.windows.asSequence()
            .filter { it.type == android.view.accessibility.AccessibilityWindowInfo.TYPE_INPUT_METHOD }
            .mapNotNull { it.root?.let(::find) }.firstOrNull()
    }

    private fun press(label: String) {
        await("Could not press $label") {
            node(label)?.let { it.isEnabled && it.performAction(AccessibilityNodeInfo.ACTION_CLICK) } == true
        }
        instrumentation.waitForIdleSync()
    }

    private fun key(label: String) = node(label)

    private fun descendants(view: View): List<View> = listOf(view) + if (view is ViewGroup)
        (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()

    private fun currentService(): KeyboardIme = main {
        android.view.inspector.WindowInspector.getGlobalWindowViews().flatMap(::descendants)
            .filterIsInstance<android.widget.Button>().single { it.isShown && it.contentDescription == "Editing tools" }
            .context as KeyboardIme
    }

    private fun hasSuggestionRequester(service: KeyboardIme): Boolean =
        KeyboardIme::class.java.getDeclaredField("requestSuggestions").run {
            isAccessible = true
            get(service) != null
        }

    private fun restartWithInputType(activity: KeyboardEditorContractActivity, inputType: Int) {
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        main {
            activity.editor.inputType = inputType
            activity.editor.setText("")
            activity.editor.setSelection(0)
            manager.restartInput(activity.editor)
            manager.showSoftInput(activity.editor, InputMethodManager.SHOW_IMPLICIT)
        }
        await("Typing keyboard did not return after editor metadata changed") {
            key("Editing tools") != null && main { manager.isActive(activity.editor) }
        }
    }

    private fun complete(service: KeyboardIme, composing: String, candidate: String): Boolean {
        val generation = KeyboardIme::class.java.getDeclaredField("uiGeneration").run {
            isAccessible = true
            getLong(service)
        }
        return KeyboardIme::class.java.getDeclaredMethod(
            "completeSuggestion", String::class.java, String::class.java, Long::class.javaPrimitiveType
        ).run {
            isAccessible = true
            invoke(service, composing, candidate, generation) as Boolean
        }
    }

    private fun shell(command: String) = android.os.ParcelFileDescriptor.AutoCloseInputStream(
        instrumentation.uiAutomation.executeShellCommand(command)).bufferedReader().use { it.readText() }

    /** Enable and select Utterleaf's typing IME; restore the previous default when done. */
    private fun withKeyboard(block: () -> Unit) {
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        val id = manager.inputMethodList.single { it.serviceName == KeyboardIme::class.java.name }.id
        val previous = Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
        val wasEnabled = manager.enabledInputMethodList.any { it.id == id }
        val options = KeyboardOptions.load(app)
        val automation = instrumentation.uiAutomation
        val flags = automation.serviceInfo.flags
        var primaryFailure: Throwable? = null
        try {
            automation.serviceInfo = automation.serviceInfo.apply {
                this.flags = flags or android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            }
            shell("ime enable $id"); shell("ime set $id")
            ImeTestReadiness.awaitDefaultImeStable(app, manager, id, "Typing IME setup")
            block()
        } catch (error: Throwable) {
            primaryFailure = error
            throw error
        } finally {
            ImeTestReadiness.cleanupPreserving(
                primaryFailure,
                {
                    if (!previous.isNullOrBlank()) {
                        shell("ime set $previous")
                        ImeTestReadiness.awaitDefaultImeStable(app, manager, previous, "Previous IME restore")
                    }
                },
                { if (!wasEnabled) shell("ime disable $id") },
                { options.save(app) },
                { automation.serviceInfo = automation.serviceInfo.apply { this.flags = flags } },
            )
        }
    }

    private fun launch(raw: Boolean = false, password: Boolean = false): KeyboardEditorContractActivity {
        val activity = instrumentation.startActivitySync(Intent(app, KeyboardEditorContractActivity::class.java)
            .putExtra("ime_options", EditorInfo.IME_ACTION_DONE).putExtra("raw", raw)
            .putExtra("password", password).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        ) as KeyboardEditorContractActivity
        try {
            await("Editor activity never acquired window focus") { main { activity.hasWindowFocus() } }
            val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
            main { activity.editor.requestFocus() }
            await("Editor never became active") { main { manager.isActive(activity.editor) } }
            main {
                manager.restartInput(activity.editor)
                manager.showSoftInput(activity.editor, InputMethodManager.SHOW_IMPLICIT)
            }
            await("Typing keyboard did not appear after one restart/show request") {
                key(if (password) "Delete" else "Editing tools") != null
            }
            return activity
        } catch (error: Throwable) {
            try {
                main { activity.finish() }
                instrumentation.waitForIdleSync()
            } catch (cleanup: Throwable) {
                if (cleanup !== error) error.addSuppressed(cleanup)
            }
            throw error
        }
    }

    private fun close(activity: KeyboardEditorContractActivity, password: Boolean = false) {
        main { activity.finish() }
        await("Previous IME session did not close") {
            key(if (password) "Delete" else "Editing tools") == null
        }
    }

    private fun keyDescriptions(): List<String> {
        val found = mutableListOf<String>()
        fun walk(current: AccessibilityNodeInfo) {
            if (found.size < 200) current.contentDescription?.let { description -> found.add(description.toString()) }
            for (index in 0 until current.childCount) current.getChild(index)?.let(::walk)
        }
        instrumentation.uiAutomation.windows
            .filter { it.type == android.view.accessibility.AccessibilityWindowInfo.TYPE_INPUT_METHOD }
            .forEach { it.root?.let(::walk) }
        return found
    }

    private class EditorTextProbe(
        private val text: String,
        private val reportedLength: Int = text.length,
        private val throwOnLength: Boolean = false,
        private val throwAtIndex: Int? = null,
        private val onCharacterRead: () -> Unit = {},
    ) : CharSequence {
        val characterReads = AtomicInteger()
        val stringConversions = AtomicInteger()
        val subsequences = AtomicInteger()
        override val length: Int
            get() {
                if (throwOnLength) throw IllegalStateException("Synthetic unreadable length")
                return reportedLength
            }
        override fun get(index: Int): Char {
            characterReads.incrementAndGet()
            onCharacterRead()
            if (index == throwAtIndex) throw IllegalStateException("Synthetic unreadable character")
            return text[index]
        }
        override fun subSequence(startIndex: Int, endIndex: Int): CharSequence {
            subsequences.incrementAndGet()
            return text.subSequence(startIndex, endIndex)
        }
        override fun toString(): String {
            stringConversions.incrementAndGet()
            return text
        }
    }

    @Test fun stripCompletesTheComposingWordThroughTheEditor() {
        withKeyboard {
            KeyboardOptions().save(app)
            val activity = launch()
            try {
                for (letter in "hel") press(letter.toString())
                val deadline = android.os.SystemClock.elapsedRealtime() + 10_000
                var candidate: String? = null
                while (android.os.SystemClock.elapsedRealtime() < deadline) {
                    candidate = candidate ?: keyDescriptions().firstOrNull { it.startsWith("Complete with ") }
                    if (candidate != null) break
                    Thread.sleep(50)
                }
                if (candidate == null) {
                    throw AssertionError("Strip did not offer a completion for hel; shown=${keyDescriptions()}")
                }
                press(candidate)
                await("Tapping the completion did not commit through the editor") {
                    main { activity.editor.text.toString() } == candidate.removePrefix("Complete with ") + " "
                }
            } finally {
                close(activity)
            }
        }
    }

    @Test fun preferenceAndRestrictedFieldsGateTheStrip() {
        var activity: KeyboardEditorContractActivity? = null
        var activityIsPassword = false
        withKeyboard {
            try {
                KeyboardOptions(suggestions = false).save(app)
                activity = launch()
                for (letter in "hel") press(letter.toString())
                instrumentation.waitForIdleSync()
                assertTrue("Strip rendered while suggestions were disabled",
                    keyDescriptions().none { it.startsWith("Complete with ") })
                close(activity!!)
                activity = null

                KeyboardOptions().save(app)
                activityIsPassword = true
                activity = launch(password = true)
                await("Password keyboard did not appear") { key("Delete") != null }
                for (description in listOf("Keyboard tools", "Editing tools", "Extra keys", "Emoji",
                    "Dictate", "Private draft")) {
                    assertTrue("$description leaked into password input", key(description) == null)
                }
                for (letter in "hel") press(letter.toString())
                instrumentation.waitForIdleSync()
                assertTrue("Strip rendered on a password field",
                    keyDescriptions().none { it.startsWith("Complete with ") })
                close(activity!!, password = true)
                activity = null
                activityIsPassword = false

                activity = launch(raw = true)
                await("Raw keyboard did not appear") { key("Editing tools") != null }
                assertTrue("Strip rendered on a raw field",
                    keyDescriptions().none { it.startsWith("Complete with ") })
            } finally {
                activity?.let { close(it, password = activityIsPassword) }
            }
        }
    }

    @Test fun sameEditorMetadataRestartsGateHostManagedSuggestionsWithoutBlockingTyping() {
        withKeyboard {
            KeyboardOptions().save(app)
            val activity = launch()
            try {
                for (letter in "hel") press(letter.toString())
                await("Ordinary editor did not expose a real completion before metadata changed") {
                    keyDescriptions().any { it.startsWith("Complete with ") }
                }
                val ordinaryService = currentService()
                assertTrue("Ordinary editor did not install its suggestion requester",
                    main { hasSuggestionRequester(ordinaryService) })

                val gatedTypes = listOf(
                    "NO_SUGGESTIONS" to
                        (InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS),
                    "AUTO_COMPLETE" to
                        (InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_AUTO_COMPLETE),
                    "EMAIL_ADDRESS" to
                        (InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS),
                    "WEB_EMAIL_ADDRESS" to
                        (InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_WEB_EMAIL_ADDRESS),
                    "URI" to (InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI),
                )
                gatedTypes.forEach { (name, inputType) ->
                    restartWithInputType(activity, inputType)
                    val service = currentService()
                    await("$name restart retained the suggestion requester") {
                        main { !hasSuggestionRequester(service) }
                    }
                    UiAwait.remains("$name restart restored the suggestion requester") {
                        !hasSuggestionRequester(service)
                    }
                    assertTrue("$name editor retained a stale candidate strip",
                        keyDescriptions().none { it.startsWith("Complete with ") })

                    for (letter in "hel") press(letter.toString())
                    await("Regular typing failed for the $name editor") {
                        main { activity.editor.text.toString() == "hel" }
                    }
                    assertFalse("$name typing restored the suggestion requester",
                        main { hasSuggestionRequester(service) })
                    assertTrue("$name editor rendered an Utterleaf candidate strip",
                        keyDescriptions().none { it.startsWith("Complete with ") })
                }

                restartWithInputType(activity, InputType.TYPE_CLASS_TEXT)
                val restoredService = currentService()
                await("Ordinary metadata did not restore the suggestion requester") {
                    main { hasSuggestionRequester(restoredService) }
                }
                for (letter in "hel") press(letter.toString())
                await("Ordinary metadata did not restore real completions") {
                    keyDescriptions().any { it.startsWith("Complete with ") }
                }
            } finally {
                close(activity)
            }
        }
    }

    @Test fun editorInfoAdapterMatchesPrimitiveSuggestionResolution() {
        val cases = listOf(
            InputType.TYPE_CLASS_TEXT to EditorInfo.IME_ACTION_DONE,
            (InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS) to
                EditorInfo.IME_ACTION_SEARCH,
            (InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_AUTO_COMPLETE) to
                EditorInfo.IME_ACTION_NEXT,
            (InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS) to
                EditorInfo.IME_ACTION_DONE,
            (InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_WEB_EMAIL_ADDRESS) to
                EditorInfo.IME_ACTION_NEXT,
            (InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI) to
                EditorInfo.IME_ACTION_GO,
        )

        assertEquals(EditorCapabilities.resolve(null), EditorCapabilities.from(null))
        cases.forEach { (inputType, imeOptions) ->
            val info = EditorInfo().apply {
                this.inputType = inputType
                this.imeOptions = imeOptions
            }
            assertEquals("Adapter diverged for inputType=$inputType",
                EditorCapabilities.resolve(inputType, imeOptions), EditorCapabilities.from(info))
        }
        assertFalse(EditorCapabilities.from(EditorInfo().apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        }).suggestions)
        assertFalse(EditorCapabilities.from(EditorInfo().apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_AUTO_COMPLETE
        }).suggestions)
        assertFalse(EditorCapabilities.from(EditorInfo().apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
        }).suggestions)
        assertFalse(EditorCapabilities.from(EditorInfo().apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_WEB_EMAIL_ADDRESS
        }).suggestions)
        assertFalse(EditorCapabilities.from(EditorInfo().apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        }).suggestions)
    }

    @Test fun completionRejectsSameLengthDifferentWordAfterCaretMove() {
        withKeyboard {
            KeyboardOptions().save(app)
            val activity = launch()
            try {
                main {
                    activity.editor.setText("cat")
                    activity.editor.setSelection(3)
                }
                instrumentation.waitForIdleSync()
                assertFalse("A chip must not replace a different same-length word",
                    complete(currentService(), "hel", "hello"))
                assertEquals("cat", main { activity.editor.text.toString() })
            } finally {
                close(activity)
            }
        }
    }

    @Test fun completionRejectsSelectedText() {
        val unreadableSelection = object : InputConnectionWrapper(null, true) {
            override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence =
                throw AssertionError("Selected text must be rejected before reading the editor")
        }
        assertFalse(completeSuggestionTransaction(unreadableSelection, "hel", "help", false))
        withKeyboard {
            KeyboardOptions().save(app)
            val activity = launch()
            try {
                main {
                    activity.editor.setText("hel rest")
                    activity.editor.setSelection(3, 8)
                }
                instrumentation.waitForIdleSync()
                assertFalse("A chip must not replace selected text",
                    complete(currentService(), "hel", "help"))
                assertEquals("hel rest", main { activity.editor.text.toString() })
            } finally {
                close(activity)
            }
        }
    }

    @Test fun slowSuggestionReadDoesNotBlockTheCaller() {
        val started = CountDownLatch(1)
        val release = CountDownLatch(1)
        val completed = CountDownLatch(1)
        val engine = SuggestionEngine(listOf("hello", "help", "world"))
        val slow = object : InputConnectionWrapper(null, true) {
            override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence {
                started.countDown()
                release.await(3, TimeUnit.SECONDS)
                return "hel"
            }
        }
        val work = SuggestionWork()
        try {
            val returned = CountDownLatch(1)
            Thread {
                instrumentation.runOnMainSync {
                    work.request(slow, 1L, engine) { completed.countDown() }
                    returned.countDown()
                }
            }.start()
            assertTrue("Suggestion read did not start", started.await(1, TimeUnit.SECONDS))
            assertTrue("Slow suggestion read blocked the IME main thread", returned.await(1, TimeUnit.SECONDS))
            release.countDown()
            assertTrue("Slow suggestion result never arrived", completed.await(3, TimeUnit.SECONDS))
        } finally {
            release.countDown()
            work.close()
        }
    }

    @Test fun newerSuggestionRequestSupersedesAnOlderRead() {
        val started = CountDownLatch(1)
        val release = CountDownLatch(1)
        val delivered = Collections.synchronizedList(mutableListOf<Int>())
        var calls = 0
        val engine = SuggestionEngine(listOf("hello", "help", "world"))
        val slow = object : InputConnectionWrapper(null, true) {
            override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence {
                calls++
                if (calls == 1) {
                    started.countDown()
                    release.await(3, TimeUnit.SECONDS)
                }
                return if (calls == 1) "old" else "hel"
            }
        }
        val work = SuggestionWork()
        try {
            work.request(slow, 1L, engine) { delivered += 0 }
            assertTrue(started.await(1, TimeUnit.SECONDS))
            for (request in 1..20) work.request(slow, 1L, engine) { delivered += request }
            release.countDown()
            await("Latest suggestion request was lost") { delivered.contains(20) }
            instrumentation.waitForIdleSync()
            assertEquals("Only active and latest reads may run", 2, calls)
            assertEquals("Only the newest result may be delivered", listOf(20), delivered.toList())
        } finally {
            release.countDown()
            work.close()
        }
    }

    @Test fun externalCaretUpdateRefreshesVisibleCandidates() {
        withKeyboard {
            KeyboardOptions().save(app)
            val activity = launch()
            try {
                for (letter in "hel") press(letter.toString())
                press("Space")
                for (letter in "wor") press(letter.toString())
                await("Initial completion did not appear") {
                    keyDescriptions().any { it.startsWith("Complete with wor", ignoreCase = true) }
                }
                val wordCandidates = keyDescriptions().filter { it.startsWith("Complete with ") }
                main {
                    activity.editor.setSelection(3)
                }
                await("External editor update did not refresh completions") {
                    val descriptions = keyDescriptions()
                    descriptions.any { it.startsWith("Complete with hel", ignoreCase = true) } &&
                        descriptions.none { it in wordCandidates }
                }
            } finally {
                close(activity)
            }
        }
    }

    @Test fun invalidatedOrClosedSuggestionReadsCannotDeliver() {
        val engine = SuggestionEngine(listOf("hello", "help", "world"))
        fun runInvalidation(close: Boolean) {
            val started = CountDownLatch(1)
            val release = CountDownLatch(1)
            val delivered = CountDownLatch(1)
            val slow = object : InputConnectionWrapper(null, true) {
                override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence {
                    started.countDown()
                    release.await(3, TimeUnit.SECONDS)
                    return "hel"
                }
            }
            val work = SuggestionWork()
            try {
                work.request(slow, 1L, engine) { delivered.countDown() }
                assertTrue(started.await(1, TimeUnit.SECONDS))
                if (close) work.close() else work.invalidate()
                release.countDown()
                assertFalse("Stale suggestion result was delivered", delivered.await(500, TimeUnit.MILLISECONDS))
            } finally {
                release.countDown()
                work.close()
            }
        }
        runInvalidation(close = false)
        runInvalidation(close = true)
    }

    @Test fun failedCandidateInsertNeverRetriesOrAppendsTheOriginalWord() {
        for (throwing in listOf(false, true)) {
            var editorText = "hel"
            var deletes = 0
            var commits = 0
            var begins = 0
            var ends = 0
            val connection = object : InputConnectionWrapper(null, true) {
                override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence {
                    assertEquals(SuggestionEngine.MAX_COMPOSING, length)
                    return editorText
                }
                override fun getTextAfterCursor(length: Int, flags: Int): CharSequence {
                    assertEquals(1, length)
                    return ""
                }
                override fun beginBatchEdit(): Boolean { begins++; return true }
                override fun deleteSurroundingText(beforeLength: Int, afterLength: Int): Boolean {
                    deletes++
                    editorText = editorText.dropLast(beforeLength)
                    return true
                }
                override fun commitText(text: CharSequence?, newCursorPosition: Int): Boolean {
                    commits++
                    editorText += text.toString()
                    if (throwing) throw IllegalStateException("simulated post-mutation failure")
                    return false
                }
                override fun endBatchEdit(): Boolean { ends++; return true }
            }
            assertFalse(completeSuggestionTransaction(connection, "hel", "hello", true))
            assertEquals("A refused editor must not receive an appended restore", "hello ", editorText)
            assertEquals(1, deletes)
            assertEquals("Candidate commit must be attempted once", 1, commits)
            assertEquals(1, begins)
            assertEquals("Accepted batch must end once", 1, ends)
        }
    }

    @Test fun completionRejectsUnreadableOrOversizedContextBeforeEditing() {
        fun assertRejected(
            composing: String = "hel",
            before: () -> CharSequence? = { "hel" },
            after: () -> CharSequence? = { "" },
            expectedBeforeReads: Int = 1,
            expectedAfterReads: Int = 1,
        ) {
            var beforeReads = 0
            var afterReads = 0
            var mutations = 0
            val connection = object : InputConnectionWrapper(null, true) {
                override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence? {
                    assertEquals(SuggestionEngine.MAX_COMPOSING, length)
                    beforeReads++
                    return before()
                }
                override fun getTextAfterCursor(length: Int, flags: Int): CharSequence? {
                    assertEquals(1, length)
                    afterReads++
                    return after()
                }
                override fun beginBatchEdit(): Boolean { mutations++; return true }
                override fun deleteSurroundingText(beforeLength: Int, afterLength: Int): Boolean {
                    mutations++; return true
                }
                override fun commitText(text: CharSequence?, newCursorPosition: Int): Boolean {
                    mutations++; return true
                }
                override fun endBatchEdit(): Boolean { mutations++; return true }
            }
            assertFalse(completeSuggestionTransaction(connection, composing, "hello", true))
            assertEquals(expectedBeforeReads, beforeReads)
            assertEquals(expectedAfterReads, afterReads)
            assertEquals("Broken context reached a destructive editor call", 0, mutations)
        }

        assertRejected(composing = "a".repeat(SuggestionEngine.MAX_COMPOSING + 1),
            expectedBeforeReads = 0, expectedAfterReads = 0)
        assertRejected(before = { null }, expectedAfterReads = 0)
        assertRejected(before = { throw IllegalStateException("closed") }, expectedAfterReads = 0)
        val unreadableLength = EditorTextProbe("hel", throwOnLength = true)
        assertRejected(before = { unreadableLength }, expectedAfterReads = 0)
        val oversizedBefore = EditorTextProbe("", reportedLength = SuggestionEngine.MAX_COMPOSING + 1)
        assertRejected(before = { oversizedBefore }, expectedAfterReads = 0)
        assertEquals(0, oversizedBefore.characterReads.get())
        assertEquals(0, oversizedBefore.stringConversions.get())
        assertEquals(0, oversizedBefore.subsequences.get())
        assertRejected(after = { null })
        assertRejected(after = { throw IllegalStateException("closed") })
        val unreadableCharacter = EditorTextProbe(".", throwAtIndex = 0)
        assertRejected(after = { unreadableCharacter })
        val oversizedAfter = EditorTextProbe("", reportedLength = 2)
        assertRejected(after = { oversizedAfter })
        assertEquals(0, oversizedAfter.characterReads.get())
        assertEquals(0, oversizedAfter.stringConversions.get())
        assertEquals(0, oversizedAfter.subsequences.get())
    }

    @Test fun completionCopiesOnlyBoundedCharactersWithoutHostConversions() {
        val before = EditorTextProbe("hel")
        val after = EditorTextProbe(".")
        var committed = ""
        val connection = object : InputConnectionWrapper(null, true) {
            override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence = before
            override fun getTextAfterCursor(length: Int, flags: Int): CharSequence = after
            override fun beginBatchEdit(): Boolean = true
            override fun deleteSurroundingText(beforeLength: Int, afterLength: Int): Boolean = true
            override fun commitText(text: CharSequence?, newCursorPosition: Int): Boolean {
                committed = text.toString()
                return true
            }
            override fun endBatchEdit(): Boolean = true
        }

        assertTrue(completeSuggestionTransaction(connection, "hel", "hello", true))
        assertEquals("hello", committed)
        assertEquals(3, before.characterReads.get())
        assertEquals(1, after.characterReads.get())
        assertEquals(0, before.stringConversions.get() + after.stringConversions.get())
        assertEquals(0, before.subsequences.get() + after.subsequences.get())
    }

    @Test fun interruptedEditorContextFailsClosedAndPreservesTheThreadSignal() {
        val complete = CountDownLatch(1)
        val accepted = AtomicReference<Boolean>()
        val interrupted = AtomicBoolean(false)
        val failure = AtomicReference<Throwable?>()
        val worker = Thread({
            try {
                val connection = object : InputConnectionWrapper(null, true) {
                    override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence =
                        throw InterruptedException("Synthetic context cancellation")
                    override fun beginBatchEdit(): Boolean =
                        throw AssertionError("Interrupted context reached a destructive editor call")
                }
                accepted.set(completeSuggestionTransaction(connection, "hel", "hello", true))
                interrupted.set(Thread.currentThread().isInterrupted)
            } catch (error: Throwable) {
                failure.set(error)
            } finally {
                complete.countDown()
            }
        }, "utterleaf-interrupted-context-test")
        worker.start()

        assertTrue("Interrupted context check did not finish", complete.await(3, TimeUnit.SECONDS))
        worker.join(1_000)
        assertFalse("Interrupted context worker remained alive", worker.isAlive)
        assertNull(failure.get())
        assertEquals(false, accepted.get())
        assertTrue("Interrupted status was swallowed", interrupted.get())
    }

    @Test fun completionBalancesEveryBatchAttemptAndRequiresAnAcceptedBegin() {
        for (throwing in listOf(false, true)) {
            var begins = 0
            var destructiveCalls = 0
            var ends = 0
            val rejectedBegin = object : InputConnectionWrapper(null, true) {
                override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence = "hel"
                override fun getTextAfterCursor(length: Int, flags: Int): CharSequence = ""
                override fun beginBatchEdit(): Boolean {
                    begins++
                    if (throwing) throw IllegalStateException("closed")
                    return false
                }
                override fun deleteSurroundingText(beforeLength: Int, afterLength: Int): Boolean {
                    destructiveCalls++; return true
                }
                override fun commitText(text: CharSequence?, newCursorPosition: Int): Boolean {
                    destructiveCalls++; return true
                }
                override fun endBatchEdit(): Boolean { ends++; return true }
            }
            assertFalse(completeSuggestionTransaction(rejectedBegin, "hel", "hello", true))
            assertEquals(1, begins)
            assertEquals("Rejected batch must prevent mutation", 0, destructiveCalls)
            assertEquals("Every begin attempt must be balanced", 1, ends)
        }

        for (throwing in listOf(false, true)) {
            var begins = 0
            var deletes = 0
            var commits = 0
            var ends = 0
            val rejectedEnd = object : InputConnectionWrapper(null, true) {
                override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence = "hel"
                override fun getTextAfterCursor(length: Int, flags: Int): CharSequence = ""
                override fun beginBatchEdit(): Boolean { begins++; return true }
                override fun deleteSurroundingText(beforeLength: Int, afterLength: Int): Boolean {
                    deletes++; return true
                }
                override fun commitText(text: CharSequence?, newCursorPosition: Int): Boolean {
                    commits++; return true
                }
                override fun endBatchEdit(): Boolean {
                    ends++
                    if (throwing) throw IllegalStateException("closed")
                    return false
                }
            }
            assertFalse(completeSuggestionTransaction(rejectedEnd, "hel", "hello", true))
            assertEquals(1, begins)
            assertEquals(1, deletes)
            assertEquals(1, commits)
            assertEquals("Accepted batch must be ended once", 1, ends)
        }
    }

    @Test fun suggestionWorkerRejectsHostContextBeyondTheRequestedBound() {
        val delivered = AtomicReference<SuggestionEngine.SuggestionState>()
        val complete = CountDownLatch(1)
        val oversized = EditorTextProbe("", reportedLength = SuggestionEngine.MAX_COMPOSING + 1)
        val connection = object : InputConnectionWrapper(null, true) {
            override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence {
                assertEquals(SuggestionEngine.MAX_COMPOSING, length)
                return oversized
            }
        }
        val work = SuggestionWork()
        try {
            work.request(connection, 1L, SuggestionEngine(listOf("alpha"))) { state ->
                delivered.set(state)
                complete.countDown()
            }
            assertTrue("Oversized context result was not delivered as empty",
                complete.await(3, TimeUnit.SECONDS))
            assertEquals(SuggestionEngine.SuggestionState.EMPTY, delivered.get())
            assertEquals(0, oversized.characterReads.get())
            assertEquals(0, oversized.stringConversions.get())
            assertEquals(0, oversized.subsequences.get())
        } finally {
            work.close()
        }
    }

    @Test fun suggestionWorkerRecoversAfterAThrowingContextObject() {
        val brokenStarted = CountDownLatch(1)
        val brokenText = EditorTextProbe("hel", throwAtIndex = 0,
            onCharacterRead = { brokenStarted.countDown() })
        val broken = object : InputConnectionWrapper(null, true) {
            override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence = brokenText
        }
        val valid = object : InputConnectionWrapper(null, true) {
            override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence = "hel"
        }
        val delivered = AtomicReference<SuggestionEngine.SuggestionState>()
        val complete = CountDownLatch(1)
        val work = SuggestionWork()
        try {
            work.request(broken, 1L, SuggestionEngine(listOf("hello"))) {}
            assertTrue("Broken context read never started", brokenStarted.await(1, TimeUnit.SECONDS))
            work.request(valid, 1L, SuggestionEngine(listOf("hello"))) { state ->
                delivered.set(state)
                complete.countDown()
            }
            assertTrue("Suggestion worker wedged after a context failure",
                complete.await(3, TimeUnit.SECONDS))
            assertEquals("hel", delivered.get().composing)
            assertEquals(listOf("hello"), delivered.get().candidates)
        } finally {
            work.close()
        }
    }

    @Test fun completionAddsOneTypingSpaceUnlessPunctuationAlreadyFollows() {
        fun complete(after: String): String {
            var committed = ""
            val connection = object : InputConnectionWrapper(null, true) {
                override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence = "hel"
                override fun getTextAfterCursor(length: Int, flags: Int): CharSequence = after.take(length)
                override fun beginBatchEdit(): Boolean = true
                override fun deleteSurroundingText(beforeLength: Int, afterLength: Int): Boolean = true
                override fun commitText(text: CharSequence?, newCursorPosition: Int): Boolean {
                    committed = text.toString(); return true
                }
                override fun endBatchEdit(): Boolean = true
            }
            assertTrue(completeSuggestionTransaction(connection, "hel", "hello", true))
            return committed
        }
        assertEquals("hello ", complete(""))
        assertEquals("hello ", complete("world"))
        assertEquals("hello", complete(" "))
        assertEquals("hello", complete("."))
    }
}
