package org.utterleaf.voice

import android.graphics.Rect
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class EmojiPanelTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext
    private val catalog by lazy {
        app.resources.openRawResource(R.raw.emoji_catalog).bufferedReader().use { EmojiCatalog.parse(it) }
    }
    private fun views(view: View): List<View> = listOf(view) + if (view is ViewGroup)
        (0 until view.childCount).flatMap { views(view.getChildAt(it)) } else emptyList()
    private fun key(panel: EmojiPanel, name: String) = views(panel.view).filterIsInstance<Button>()
        .single { it.contentDescription == name }
    private fun fixture(options: KeyboardOptions = KeyboardOptions(), supported: Set<String>? = null,
        commit: (String) -> Boolean = { true }, back: () -> Unit = {}) = EmojiPanel(app, options, commit, back) { ready ->
        ready(EmojiData(catalog, supported ?: catalog.entries.map { it.sequence }.toSet()));
        {}
    }
    private fun query(panel: EmojiPanel, text: String) {
        text.forEach { key(panel, if (it == ' ') "Emoji search space" else "Emoji search letter $it").performClick() }
    }
    private fun display(panel: EmojiPanel) = views(panel.view).filterIsInstance<TextView>()
        .single { it.tag == "emoji-query" }.text.toString()

    @Test fun localSearchPreservesTheEditorUntilOneExactEmojiTap() {
        val inserted = mutableListOf<String>()
        instrumentation.runOnMainSync {
            val panel = fixture(commit = { inserted.add(it); true })
            try {
                assertTrue(views(panel.view).none { it is EditText })
                key(panel, "Search emoji").performClick()
                val retainedLetter = key(panel, "Emoji search letter a")
                query(panel, "family")
                assertEquals("family", display(panel)); assertTrue(inserted.isEmpty())
                assertEquals("Emoji search: family", views(panel.view).single { it.tag == "emoji-query" }.contentDescription)
                // Query keys retain their views while only the result grid changes.
                assertSame(retainedLetter, key(panel, "Emoji search letter a"))
                val expected = catalog.search("family").first { it.sequence.contains('\u200d') }
                val next = key(panel, "Next emoji page")
                while (views(panel.view).filterIsInstance<Button>().none { it.contentDescription == expected.name }) {
                    assertTrue(next.isEnabled); next.performClick()
                }
                key(panel, expected.name).performClick()
                assertEquals(listOf(expected.sequence), inserted)
                assertEquals("family", display(panel))
                key(panel, "Delete emoji search letter").performClick(); assertEquals("famil", display(panel))
                key(panel, "Clear emoji search").performClick(); assertEquals("Search emoji · English names", display(panel))
                fun layoutAndLetterTop(): Int {
                    val width = Ui.dp(app, 300)
                    panel.view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                        View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
                    panel.view.layout(0, 0, width, panel.view.measuredHeight)
                    val rect = Rect()
                    key(panel, "Emoji search letter a").getDrawingRect(rect)
                    panel.view.offsetDescendantRectToMyCoords(key(panel, "Emoji search letter a"), rect)
                    return rect.top
                }
                val beforeEmpty = layoutAndLetterTop()
                query(panel, "zzzzzzzz")
                assertEquals(beforeEmpty, layoutAndLetterTop())
            } finally { panel.clear() }
        }
    }

    @Test fun queryLimitClearExitAndStaleControlsCannotInsert() {
        val inserted = mutableListOf<String>()
        instrumentation.runOnMainSync {
            var returned = 0
            val panel = fixture(commit = { inserted.add(it); true }, back = { returned++ })
            key(panel, "Search emoji").performClick()
            repeat(60) { key(panel, "Emoji search letter a").performClick() }
            assertEquals(48, display(panel).length)
            key(panel, "Clear emoji search").performClick()
            query(panel, "grinning face")
            val oldResult = key(panel, "grinning face")
            key(panel, "Emoji search letter x").performClick()
            oldResult.performClick(); assertTrue(inserted.isEmpty())
            val oldLetter = key(panel, "Emoji search letter a")
            val oldReturn = key(panel, "Return from emoji to letters")
            oldReturn.performClick()
            assertEquals(1, returned); assertEquals(0, panel.view.childCount)
            oldResult.performClick(); oldLetter.performClick(); oldReturn.performClick()
            assertTrue(inserted.isEmpty()); assertEquals(1, returned)
        }
    }

    @Test fun categoryVariantPagingCommitsAnExistingToneSequenceOnly() {
        val selected = catalog.entries.first { entry ->
            entry.isCanonical && catalog.familyVariants(entry).size > 6
        }
        val members = catalog.familyVariants(selected)
        val inserted = mutableListOf<String>()
        instrumentation.runOnMainSync {
            val panel = fixture(supported = members.map { it.sequence }.toSet(), commit = { inserted.add(it); true })
            try {
                key(panel, "Emoji categories").performClick()
                key(panel, "Emoji category: People").performClick()
                key(panel, selected.name + "; choose variation").performClick()
                val expected = members.last()
                while (views(panel.view).filterIsInstance<Button>().none { it.contentDescription == expected.name }) {
                    assertTrue(key(panel, "Next emoji page").isEnabled)
                    key(panel, "Next emoji page").performClick()
                }
                key(panel, expected.name).performClick()
                assertEquals(listOf(expected.sequence), inserted)
                key(panel, "Back from emoji variants").performClick()
                assertNotNull(key(panel, selected.name + "; choose variation"))
            } finally { panel.clear() }
        }
    }

    @Test fun filteredEmptyFailureAndRejectedCommitHaveNoFallback() {
        instrumentation.runOnMainSync {
            var cancelled = 0
            var ready: ((EmojiData?) -> Unit)? = null
            val pending = EmojiPanel(app, KeyboardOptions(), { fail("Pending loader committed"); false }, {}) {
                ready = it;
                { cancelled++ }
            }
            pending.clear()
            ready!!(EmojiData(catalog, catalog.entries.map { it.sequence }.toSet()))
            assertEquals(1, cancelled); assertEquals(0, pending.view.childCount)
            val failed = EmojiPanel(app, KeyboardOptions(), { false }, {}) { it(null); {} }
            assertTrue(views(failed.view).filterIsInstance<TextView>().any { it.text.toString().contains("unavailable") })
            assertTrue(key(failed, "Return from emoji to letters").isEnabled)
            failed.clear()
            val empty = fixture(supported = emptySet())
            assertTrue(views(empty.view).filterIsInstance<TextView>().any { it.text.toString().contains("supported by this device") })
            empty.clear()
            var attempts = 0
            val rejected = fixture(commit = { attempts++; false })
            key(rejected, "grinning face").performClick()
            assertEquals(1, attempts); assertNotNull(key(rejected, "grinning face"))
            rejected.clear()
        }
    }

    @Test fun allLayoutsAndThemesKeepBrowseSearchAndCategoriesWithinBounds() {
        instrumentation.runOnMainSync {
            for (layout in LetterLayout.entries) for (light in listOf(false, true)) for (width in listOf(300, 600)) {
                val panel = fixture(KeyboardOptions(large = true, light = light, letterLayout = layout))
                fun assertBounds() {
                    val pixels = Ui.dp(app, width)
                    panel.view.measure(View.MeasureSpec.makeMeasureSpec(pixels, View.MeasureSpec.EXACTLY),
                        View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
                    panel.view.layout(0, 0, pixels, panel.view.measuredHeight)
                    val rects = views(panel.view).filterIsInstance<Button>().map { button ->
                        assertFalse(button.contentDescription.isNullOrBlank())
                        Rect(0, 0, button.width, button.height).also { panel.view.offsetDescendantRectToMyCoords(button, it) }
                    }
                    rects.forEachIndexed { index, rect ->
                        assertFalse(rect.isEmpty); assertTrue(rect.left >= 0 && rect.right <= pixels)
                        assertTrue(rect.top >= 0 && rect.bottom <= panel.view.height)
                        rects.drop(index + 1).forEach { assertFalse(Rect.intersects(rect, it)) }
                    }
                }
                try {
                    assertBounds()
                    key(panel, "Search emoji").performClick(); query(panel, "heart"); assertBounds()
                    val keyWidth = key(panel, "Emoji search letter ${layout.top.first()}").width
                    layout.rows.joinToString("").forEach { letter ->
                        assertEquals("Search changed the letter width between rows", keyWidth.toDouble(),
                            key(panel, "Emoji search letter $letter").width.toDouble(), 1.0)
                    }
                    key(panel, "Emoji categories").performClick(); assertBounds()
                } finally { panel.clear() }
            }
        }
    }

    @Test fun rawFieldDisablesEntryAndResetInvalidatesTheOpenPicker() {
        instrumentation.runOnMainSync {
            val inserted = mutableListOf<String>()
            val typing = TypingPanel(app, KeyboardOptions(), { inserted.add(it); true }, {}, {}, {}, {}, {}, {})
            fun key(name: String) = views(typing.view).filterIsInstance<Button>().single { it.contentDescription == name }
            typing.reset(false, false, "Enter", allowEmoji = false)
            assertFalse(key("Emoji unavailable in raw input").isEnabled)
            typing.reset(false, false, "Enter")
            key("Emoji").performClick()
            val oldReturn = key("Return from emoji to letters")
            typing.reset(false, false, "Enter", allowEmoji = false)
            oldReturn.performClick()
            assertFalse(key("Emoji unavailable in raw input").isEnabled)
            assertTrue(inserted.isEmpty())
        }
    }
}
