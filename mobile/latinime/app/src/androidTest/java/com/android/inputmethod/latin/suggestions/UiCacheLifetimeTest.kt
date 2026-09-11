package com.android.inputmethod.latin.suggestions

import android.view.ContextThemeWrapper
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.accessibility.AccessibilityUtils
import com.android.inputmethod.accessibility.MoreKeysKeyboardAccessibilityDelegate
import com.android.inputmethod.keyboard.Key
import com.android.inputmethod.keyboard.KeyDetector
import com.android.inputmethod.keyboard.internal.GestureFloatingTextDrawingPreview
import com.android.inputmethod.keyboard.internal.KeyboardParams
import com.android.inputmethod.latin.PunctuationSuggestions
import com.android.inputmethod.latin.R
import com.android.inputmethod.latin.SuggestedWords
import com.android.inputmethod.latin.SuggestedWords.SuggestedWordInfo
import com.android.inputmethod.latin.common.Constants
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Synthetic cache seeding verifies reference cleanup, not heap zeroization or TalkBack QA. */
@RunWith(AndroidJUnit4::class)
class UiCacheLifetimeTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private fun main(block: () -> Unit) {
        var failure: Throwable? = null
        instrumentation.runOnMainSync { try { block() } catch (error: Throwable) { failure = error } }
        failure?.let { throw it }
    }
    private fun field(target: Any, name: String): java.lang.reflect.Field {
        var type: Class<*>? = target.javaClass
        while (type != null) {
            try { return type.getDeclaredField(name).apply { isAccessible = true } }
            catch (_: NoSuchFieldException) { type = type.superclass }
        }
        error("Missing field $name")
    }
    @Suppress("UNCHECKED_CAST")
    private fun <T> read(target: Any, name: String): T = field(target, name).get(target) as T
    private fun write(target: Any, name: String, value: Any?) = field(target, name).set(target, value)
    private fun words(prefix: String) = PunctuationSuggestions.newPunctuationSuggestions(
        arrayOf("$prefix-one", "$prefix-two", "$prefix-three"))

    @Test fun terminalStripCleanupDropsPooledAndExpandedCachesAndAllowsReuse() = main {
        val context = ContextThemeWrapper(instrumentation.targetContext, R.style.KeyboardTheme_LXX_Dark)
        AccessibilityUtils.init(instrumentation.targetContext)
        val strip = SuggestionStripView(context, null)
        val original = words("synthetic-old")
        strip.setSuggestions(original, false)
        val wordViews = read<ArrayList<TextView>>(strip, "mWordViews")
        val debugViews = read<ArrayList<TextView>>(strip, "mDebugInfoViews")
        (wordViews + debugViews).forEach {
            it.text = "synthetic-retained"; it.contentDescription = "synthetic-description"
            it.tag = "synthetic-tag"
        }
        val builder = read<MoreSuggestions.Builder>(strip, "mMoreSuggestionsBuilder")
        val params = read<KeyboardParams>(builder, "mParams")
        val key = Key("synthetic-key", 0, Constants.CODE_OUTPUT_TEXT, "synthetic-output",
            "synthetic-hint", 0, Key.BACKGROUND_TYPE_NORMAL, 0, 0, 30, 30, 0, 0)
        params.onAddKey(key)
        write(builder, "mSuggestedWords", original)
        val constructor = MoreSuggestions::class.java.getDeclaredConstructor(params.javaClass, SuggestedWords::class.java)
            .apply { isAccessible = true }
        val expanded = constructor.newInstance(params, original)
        val pane = read<MoreSuggestionsView>(strip, "mMoreSuggestionsView")
        pane.setKeyboard(expanded)
        write(pane, "mCurrentKey", key)
        val delegate = MoreKeysKeyboardAccessibilityDelegate(pane, read<KeyDetector>(pane, "mKeyDetector"))
        delegate.setKeyboard(expanded)
        write(delegate, "mLastHoverKey", key)
        write(pane, "mAccessibilityDelegate", delegate)
        assertFalse(params.mSortedKeys.isEmpty())
        try {
            strip.clearEditorSession()
            assertTrue(read<SuggestedWords>(strip, "mSuggestedWords").isEmpty)
            (wordViews + debugViews).forEach {
                assertEquals("", it.text.toString()); assertNull(it.contentDescription); assertNull(it.tag)
            }
            assertTrue(read<SuggestedWords>(builder, "mSuggestedWords").isEmpty)
            assertTrue(params.mSortedKeys.isEmpty())
            assertTrue(pane.keyboard!!.sortedKeys.isEmpty())
            assertTrue((pane.keyboard as MoreSuggestions).mSuggestedWords.isEmpty)
            assertNull(read<Any?>(pane, "mCurrentKey"))
            assertNotSame(delegate, read<Any?>(pane, "mAccessibilityDelegate"))
            assertEquals(-1, read<Int>(pane, "mActivePointerId"))
            val later = words("synthetic-new")
            strip.setSuggestions(later, false)
            assertSame(later, read<SuggestedWords>(strip, "mSuggestedWords"))
            assertTrue(wordViews.any { it.text.toString().contains("synthetic-new") })
            strip.clearEditorSession()
            strip.clearEditorSession()
        } finally { strip.clearEditorSession() }
    }

    @Test fun accessibilityAndDisabledGesturePreviewRetireWordsWithoutEditorAccess() = main {
        val typed = SuggestedWordInfo("synthetic-typed", "", 1, SuggestedWordInfo.KIND_TYPED, null, -1, -1)
        val corrected = SuggestedWordInfo("synthetic-corrected", "", 2, SuggestedWordInfo.KIND_CORRECTION, null, -1, -1)
        val suggestions = SuggestedWords(arrayListOf(typed, corrected), null, typed, false, true,
            false, SuggestedWords.INPUT_STYLE_TYPING, 1)
        val accessibility = AccessibilityUtils.getInstance()
        accessibility.setAutoCorrection(suggestions)
        assertEquals("synthetic-typed", read<String>(accessibility, "mTypedWord"))
        accessibility.clearAutoCorrection()
        assertNull(read<Any?>(accessibility, "mTypedWord"))
        assertNull(read<Any?>(accessibility, "mAutoCorrectionWord"))
        val context = ContextThemeWrapper(instrumentation.targetContext, R.style.KeyboardTheme_LXX_Dark)
        val attributes = context.obtainStyledAttributes(R.styleable.MainKeyboardView)
        val preview = try { GestureFloatingTextDrawingPreview(attributes) } finally { attributes.recycle() }
        preview.setKeyboardViewGeometry(intArrayOf(0, 0), 300, 100)
        preview.setPreviewEnabled(true)
        preview.setSuggetedWords(suggestions)
        assertSame(suggestions, read<SuggestedWords>(preview, "mSuggestedWords"))
        preview.setPreviewEnabled(false)
        preview.dismissGestureFloatingPreviewText()
        assertTrue(read<SuggestedWords>(preview, "mSuggestedWords").isEmpty)
        preview.setPreviewEnabled(true)
        preview.setSuggetedWords(suggestions)
        preview.onDeallocateMemory()
        assertTrue(read<SuggestedWords>(preview, "mSuggestedWords").isEmpty)
    }
}
