package org.utterleaf.voice

import android.content.Context
import android.content.res.Configuration
import android.graphics.Rect
import android.os.Build
import android.view.View
import android.view.WindowInsets
import android.widget.Button
import android.widget.LinearLayout
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
        panelContext: Context = app,
        options: KeyboardOptions = KeyboardOptions(),
        state: () -> SuggestionEngine.SuggestionState = {
            SuggestionEngine.SuggestionState.EMPTY
        },
        enabled: Boolean = true,
    ): TypingPanel = TypingPanel(
        panelContext, options, { true }, {}, {}, {}, {}, {}, {},
        suggest = if (enabled) state else null,
        completeWord = if (enabled) { _, _ -> true } else null)

    @Test fun suggestionStripKeepsKeyGeometryAcrossCandidateStates() = main {
        var state = SuggestionEngine.SuggestionState.EMPTY
        val panel = panel(state = { state })
        fun dailyControlBounds() = listOf("Keyboard tools", "Editing tools", "Dictate")
            .associateWith { bounds(panel, it) }
        panel.reset(false, false, "Enter")
        val emptyHeight = measure(panel)
        val emptySpace = bounds(panel, "Space")
        val emptyQ = bounds(panel, "q")
        val emptyControls = dailyControlBounds()
        val emptySuggestionSlots = descendants(panel.view).filterIsInstance<HintedKey>()
            .filter { it.visualRole == KeyVisualRole.SUGGESTION }
        assertEquals("Daily strip must retain three predictable suggestion slots",
            3, emptySuggestionSlots.size)
        assertTrue("Empty suggestion slots must stay quiet without collapsing",
            emptySuggestionSlots.all { it.visibility == View.INVISIBLE && it.measuredWidth > 0 })
        capture(panel, "empty")

        state = SuggestionEngine.SuggestionState("q", emptyList())
        panel.refreshSuggestions()
        val noMatchHeight = measure(panel)
        val noMatchSpace = bounds(panel, "Space")
        val noMatchQ = bounds(panel, "q")
        val noMatchControls = dailyControlBounds()
        assertFalse("No-match state must not add instructional filler",
            descendants(panel.view).filterIsInstance<TextView>().any { it.text == "No completions" })
        capture(panel, "no-match")

        state = SuggestionEngine.SuggestionState("q", listOf("quick"))
        panel.refreshSuggestions()
        val oneHeight = measure(panel)
        val oneSpace = bounds(panel, "Space")
        val oneQ = bounds(panel, "q")
        val oneControls = dailyControlBounds()
        val oneChipCount = descendants(panel.view).filterIsInstance<Button>()
            .count { it.contentDescription == "Complete with quick" }
        capture(panel, "one")

        state = SuggestionEngine.SuggestionState("q", listOf("quick", "quiet", "quite"))
        panel.refreshSuggestions()
        val threeHeight = measure(panel)
        val threeSpace = bounds(panel, "Space")
        val threeQ = bounds(panel, "q")
        val threeControls = dailyControlBounds()
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
        val visibleSuggestionSlots = descendants(panel.view).filterIsInstance<HintedKey>()
            .filter { it.visualRole == KeyVisualRole.SUGGESTION && it.visibility == View.VISIBLE }
        assertEquals("Expected three visible suggestion slots", 3, visibleSuggestionSlots.size)
        val suggestionWidths = visibleSuggestionSlots.map { it.width }
        assertTrue("Suggestion slots must divide their region evenly",
            suggestionWidths.max() - suggestionWidths.min() <= 1)
        assertTrue("Suggestion slots must retain 48dp touch widths",
            visibleSuggestionSlots.all { it.width >= Ui.dp(app, 48) })
        assertTrue("Completions must use the quiet suggestion visual role",
            visibleSuggestionSlots.all { it.background.isStateful })
        fun assertPressedDiffers(label: String, button: Button) {
            val normal = android.graphics.Bitmap.createBitmap(button.width, button.height,
                android.graphics.Bitmap.Config.ARGB_8888)
            val pressed = android.graphics.Bitmap.createBitmap(button.width, button.height,
                android.graphics.Bitmap.Config.ARGB_8888)
            try {
                button.isPressed = false; button.jumpDrawablesToCurrentState()
                button.draw(android.graphics.Canvas(normal))
                button.isPressed = true; button.jumpDrawablesToCurrentState()
                button.draw(android.graphics.Canvas(pressed))
                assertFalse("$label pressed state was visually indistinguishable", normal.sameAs(pressed))
            } finally {
                button.isPressed = false; button.jumpDrawablesToCurrentState()
                normal.recycle(); pressed.recycle()
            }
        }
        assertPressedDiffers("Suggestion", visibleSuggestionSlots.first())
        assertPressedDiffers("Letter key", key(panel, "q"))
        assertEquals("No-match moved q", emptyQ, noMatchQ)
        assertEquals("One completion moved q", noMatchQ, oneQ)
        assertEquals("Three completions moved q", oneQ, threeQ)
        assertEquals("No-match moved daily controls", emptyControls, noMatchControls)
        assertEquals("One completion moved daily controls", noMatchControls, oneControls)
        assertEquals("Three completions moved daily controls", oneControls, threeControls)
        state = SuggestionEngine.SuggestionState.EMPTY
        key(panel, "Space").performClick()
        val afterSpaceHeight = measure(panel)
        assertEquals("Space must not change the strip geometry", threeHeight, afterSpaceHeight)
        val clearedSlots = descendants(panel.view).filterIsInstance<HintedKey>()
            .filter { it.visualRole == KeyVisualRole.SUGGESTION }
        assertTrue("Hidden suggestions must not retain stale candidate text",
            clearedSlots.all { it.visibility == View.INVISIBLE && !it.isEnabled &&
                it.text.isEmpty() && it.contentDescription.isNullOrEmpty() })
        assertFalse("Empty strip must not add instructional filler",
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
        assertEquals("Inline suggestions must not add another toolbar row",
            disabledHeight, enabledHeight)

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

    @Test fun bottomRowHasNoUnassignedTouchRegionOutsideExplicitSplitChannel() = main {
        val configurations = listOf(
            Triple(Configuration.ORIENTATION_PORTRAIT, 320, false),
            Triple(Configuration.ORIENTATION_LANDSCAPE, 600, false),
            Triple(Configuration.ORIENTATION_LANDSCAPE, 600, true),
        )
        for ((orientation, widthDp, split) in configurations) {
            val configured = Configuration(app.resources.configuration).apply {
                this.orientation = orientation
            }
            val panelContext = app.createConfigurationContext(configured)
            val alignments = if (split) listOf(KeyboardAlignment.FULL) else KeyboardAlignment.entries
            for (alignment in alignments) {
                val panel = panel(panelContext,
                    KeyboardOptions(numberRow = false, alignment = alignment,
                        splitLandscape = split), enabled = false)
                panel.reset(false, false, "Enter")
                val width = Ui.dp(panelContext, widthDp)
                panel.view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                    View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
                panel.view.layout(0, 0, width, panel.view.measuredHeight)

                val bottom = descendants(panel.view).filterIsInstance<Button>()
                    .first { it.contentDescription == "Space" }.parent as LinearLayout
                val children = (0 until bottom.childCount).map { bottom.getChildAt(it) }
                if (split) {
                    assertEquals("Split bottom row must contain exactly one intentional center channel",
                        1, children.count { it !is Button })
                    assertTrue("Split bottom row contains another inert slot",
                        children.filterIsInstance<Button>().all { it.isClickable && it.isFocusable })
                } else {
                    assertTrue("$orientation/$alignment bottom row contains an inert slot",
                        children.all { it is Button && it.isClickable && it.isFocusable })
                }
                assertEquals(0, children.first().left)
                assertEquals(bottom.width, children.last().right)
                children.zipWithNext().forEach { (left, right) ->
                    assertEquals("$orientation/$alignment/split=$split bottom row has a dead gap",
                        left.right, right.left)
                }
                assertTrue(descendants(panel.view).filterIsInstance<Button>()
                    .mapNotNull { it.contentDescription?.toString() }
                    .containsAll(setOf(",", "Space", ".")))
                listOf("Switch letters and symbols", ",", "Space", ".", "Enter").forEach { description ->
                    val targets = descendants(panel.view).filterIsInstance<Button>()
                        .filter { it.contentDescription == description }
                    assertTrue("$orientation/$alignment/split=$split $description was absent",
                        targets.isNotEmpty())
                    assertTrue("$orientation/$alignment/split=$split $description was narrower than 48dp",
                        targets.all { it.width >= Ui.dp(panelContext, 48) })
                    assertTrue("$orientation/$alignment/split=$split $description was shorter than 48dp",
                        targets.all { it.height >= Ui.dp(panelContext, 48) })
                }
                val action = key(panel, "Enter")
                assertTrue("$orientation/$alignment/split=$split action key was disabled", action.isEnabled)
                assertEquals(KeyVisualRole.ACTION, (action as HintedKey).visualRole)
                val bitmap = android.graphics.Bitmap.createBitmap(action.width, action.height,
                    android.graphics.Bitmap.Config.ARGB_8888)
                val focused = android.graphics.Bitmap.createBitmap(action.width, action.height,
                    android.graphics.Bitmap.Config.ARGB_8888)
                try {
                    action.background.draw(android.graphics.Canvas(bitmap))
                    assertTrue("$orientation/$alignment/split=$split action key lost its primary fill",
                        bitmap.getPixel(action.width / 2, action.height / 2) !=
                            Ui.palette(panelContext, KeyboardOptions(numberRow = false,
                                alignment = alignment, splitLandscape = split)).background)
                    bitmap.eraseColor(android.graphics.Color.TRANSPARENT)
                    action.draw(android.graphics.Canvas(bitmap))
                    action.isFocusableInTouchMode = true
                    assertTrue("$orientation/$alignment/split=$split action did not accept focus",
                        action.requestFocus())
                    action.jumpDrawablesToCurrentState()
                    action.draw(android.graphics.Canvas(focused))
                    assertFalse("$orientation/$alignment/split=$split action focus was visually indistinguishable",
                        bitmap.sameAs(focused))
                } finally {
                    action.clearFocus(); action.jumpDrawablesToCurrentState()
                    bitmap.recycle(); focused.recycle()
                }
                panel.dispose()
            }
        }
    }

    @Test fun narrowFullWidthKeepsBroadSpaceAlongsideMinimumSideTargets() = main {
        val panel = panel(options = KeyboardOptions(alignment = KeyboardAlignment.FULL), enabled = false)
        panel.reset(false, false, "Previous")
        measure(panel, 320)

        val letterWidth = bounds(panel, "q").width()
        val spaceWidth = bounds(panel, "Space").width()
        assertTrue("320dp Space must remain at least four letter keys wide",
            spaceWidth >= letterWidth * 4)
        listOf("Switch letters and symbols", ",", ".", "Previous").forEach { description ->
            assertTrue("320dp $description must retain a 48dp target",
                bounds(panel, description).width() >= Ui.dp(app, 48))
        }
        val action = key(panel, "Previous")
        val availableLabelWidth = action.width - action.compoundPaddingLeft - action.compoundPaddingRight
        assertTrue("Previous action label must fit its minimum target",
            action.paint.measureText(action.text.toString()) <= availableLabelWidth + 1)
        panel.dispose()
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
