package org.utterleaf.voice

import android.graphics.Rect
import android.os.Build
import android.view.View
import android.view.WindowInsets
import android.widget.Button
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.FileOutputStream

/** Focused geometry contracts for typing and inset regressions. */
@RunWith(AndroidJUnit4::class)
class KeyboardSpacingTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext

    private fun <T> main(block: () -> T): T {
        val result = java.util.concurrent.atomic.AtomicReference<T>()
        instrumentation.runOnMainSync { result.set(block()) }
        return result.get()
    }

    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is android.view.ViewGroup) (0 until view.childCount)
            .flatMap { descendants(view.getChildAt(it)) } else emptyList()

    private fun measure(panel: TypingPanel, widthDp: Int = 320): Int {
        val width = Ui.dp(app, widthDp)
        panel.view.measure(
            View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
        panel.view.layout(0, 0, width, panel.view.measuredHeight)
        return panel.view.height
    }

    private fun key(panel: TypingPanel, description: String): Button =
        descendants(panel.view).filterIsInstance<Button>().single { it.contentDescription == description }

    private fun bounds(panel: TypingPanel, description: String): Rect =
        Rect(0, 0, key(panel, description).width, key(panel, description).height).also {
            panel.view.offsetDescendantRectToMyCoords(key(panel, description), it)
        }

    /** Optional evidence of this panel only; never captures the host or system UI. */
    private fun capture(panel: TypingPanel, state: String) {
        val name = InstrumentationRegistry.getArguments().getString("r2Screenshots") ?: return
        if (Build.VERSION.SDK_INT < 29) return
        require(name.matches(Regex("[a-zA-Z0-9_-]{1,32}")))
        require(state.matches(Regex("[a-zA-Z0-9_-]{1,32}")))
        val directory = File(checkNotNull(app.getExternalFilesDir(null)), name)
        check(directory.isDirectory || directory.mkdirs()) { "Cannot create screenshot directory" }
        val bitmap = android.graphics.Bitmap.createBitmap(panel.view.width, panel.view.height,
            android.graphics.Bitmap.Config.ARGB_8888)
        try {
            panel.view.draw(android.graphics.Canvas(bitmap))
            FileOutputStream(File(directory, "spacing-$state.png")).use {
                check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it))
            }
        } finally {
            bitmap.recycle()
        }
    }

    private fun panel(
        options: KeyboardOptions = KeyboardOptions(),
        state: () -> SuggestionEngine.SuggestionState = {
            SuggestionEngine.SuggestionState.EMPTY
        },
        enabled: Boolean = true,
    ): TypingPanel = TypingPanel(
        app, options, { true }, {}, {}, {}, {}, {}, {},
        suggest = if (enabled) state else null,
        completeWord = if (enabled) { _, _ -> true } else null)

    @Test fun suggestionStripKeepsKeyGeometryAcrossCandidateStates() = main {
        var state = SuggestionEngine.SuggestionState.EMPTY
        val panel = panel(state = { state })
        panel.reset(false, false, "Enter")
        val emptyHeight = measure(panel)
        val emptySpace = bounds(panel, "Space")
        val emptyQ = bounds(panel, "q")
        capture(panel, "empty")

        state = SuggestionEngine.SuggestionState("q", emptyList())
        panel.refreshSuggestions()
        val noMatchHeight = measure(panel)
        val noMatchSpace = bounds(panel, "Space")
        val noMatchQ = bounds(panel, "q")
        assertTrue("No-match state must be represented accessibly",
            descendants(panel.view).filterIsInstance<TextView>().any { it.text == "No completions" })
        capture(panel, "no-match")

        state = SuggestionEngine.SuggestionState("q", listOf("quick"))
        panel.refreshSuggestions()
        val oneHeight = measure(panel)
        val oneSpace = bounds(panel, "Space")
        val oneQ = bounds(panel, "q")
        val oneChipCount = descendants(panel.view).filterIsInstance<Button>()
            .count { it.contentDescription == "Complete with quick" }
        capture(panel, "one")

        state = SuggestionEngine.SuggestionState("q", listOf("quick", "quiet", "quite"))
        panel.refreshSuggestions()
        val threeHeight = measure(panel)
        val threeSpace = bounds(panel, "Space")
        val threeQ = bounds(panel, "q")
        val threeChipCount = descendants(panel.view).filterIsInstance<Button>()
            .count { it.contentDescription?.toString()?.startsWith("Complete with ") == true }
        capture(panel, "three")

        assertEquals("Empty strip changed the keyboard height", emptyHeight, noMatchHeight)
        assertEquals("One completion changed the keyboard height", noMatchHeight, oneHeight)
        assertEquals("Three completions changed the keyboard height", oneHeight, threeHeight)
        assertEquals("Empty strip moved Space", emptySpace, noMatchSpace)
        assertEquals("One completion moved Space", noMatchSpace, oneSpace)
        assertEquals("Three completions moved Space", oneSpace, threeSpace)
        assertEquals("Expected three completion chips", 3, threeChipCount)
        assertEquals("Expected the current candidate set to contain quick", 1, oneChipCount)
        assertEquals("No-match moved q", emptyQ, noMatchQ)
        assertEquals("One completion moved q", noMatchQ, oneQ)
        assertEquals("Three completions moved q", oneQ, threeQ)
        state = SuggestionEngine.SuggestionState.EMPTY
        key(panel, "Space").performClick()
        val afterSpaceHeight = measure(panel)
        assertEquals("Space must not change the strip geometry", threeHeight, afterSpaceHeight)
        assertTrue("Empty strip must be represented accessibly",
            descendants(panel.view).filterIsInstance<TextView>().any { it.text == "Type a word" })
        capture(panel, "after-space")
    }

    @Test fun suggestionStripRemainsDeliberatelyAbsentWhenDisabledOrOnSymbols() = main {
        val disabled = panel(enabled = false)
        disabled.reset(false, false, "Enter")
        val disabledHeight = measure(disabled)
        assertFalse(descendants(disabled.view).any {
            it is Button && it.contentDescription?.toString()?.startsWith("Complete with ") == true
        })

        val enabled = panel()
        enabled.reset(false, false, "Enter")
        val enabledHeight = measure(enabled)
        assertEquals("Enabled letters reserve the fixed strip", Ui.dp(app, 40).toDouble(),
            (enabledHeight - disabledHeight).toDouble(), 1.0)

        val symbols = panel()
        symbols.reset(false, true, "Enter")
        val symbolsHeight = measure(symbols)
        val symbolsDisabled = panel(enabled = false)
        symbolsDisabled.reset(false, true, "Enter")
        val symbolsDisabledHeight = measure(symbolsDisabled)
        assertFalse(descendants(symbols.view).any {
            it is Button && it.contentDescription?.toString()?.startsWith("Complete with ") == true
        })
        assertEquals("Symbols must not reserve a suggestion strip", symbolsDisabledHeight, symbolsHeight)
    }

    @Test fun explicitBottomSpacingAddsOnlyTheRequestedPanelSpace() = main {
        fun height(bottomPaddingDp: Int): Int {
            val panel = panel(
                options = KeyboardOptions(bottomPaddingDp = bottomPaddingDp),
                enabled = false)
            panel.reset(false, false, "Enter")
            return measure(panel)
        }
        val base = height(0)
        val requested = 24
        assertEquals(Ui.dp(app, requested).toDouble(),
            (height(requested) - base).toDouble(), 1.0)
    }

    @Test fun privateDraftBottomSpacingIsAppliedOnceOutsideNestedTypingPanel() = main {
        fun height(bottomPaddingDp: Int): Int {
            val panel = PrivateDraftPanel(app, KeyboardOptions(bottomPaddingDp = bottomPaddingDp),
                { DraftInsertionResult.UNAVAILABLE }, {})
            val width = Ui.dp(app, 320)
            panel.view.measure(
                View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
            panel.view.layout(0, 0, width, panel.view.measuredHeight)
            return panel.view.height
        }
        val base = height(0)
        val requested = 24
        assertEquals(Ui.dp(app, requested).toDouble(),
            (height(requested) - base).toDouble(), 1.0)
    }

    @Test fun navigationInsetsPreserveBasePaddingWithoutAccumulation() = main {
        assumeTrue(Build.VERSION.SDK_INT >= 30)
        val insets = WindowInsets.Builder()
            .setInsets(WindowInsets.Type.statusBars(), android.graphics.Insets.of(0, 23, 0, 0))
            .setInsets(WindowInsets.Type.navigationBars(), android.graphics.Insets.of(7, 0, 11, 29))
            .build()
        val view = View(app).apply { setPadding(3, 0, 3, 4) }
        Ui.applySystemInsets(view, navigationOnly = true)
        repeat(2) {
            val remaining = view.dispatchApplyWindowInsets(insets)
            assertEquals(10, view.paddingLeft)
            assertEquals(0, view.paddingTop)
            assertEquals(14, view.paddingRight)
            assertEquals(33, view.paddingBottom)
            assertEquals(0, remaining.systemWindowInsetBottom)
        }
        view.dispatchApplyWindowInsets(WindowInsets.CONSUMED)
        assertEquals(listOf(3, 0, 3, 4),
            listOf(view.paddingLeft, view.paddingTop, view.paddingRight, view.paddingBottom))
    }
}
