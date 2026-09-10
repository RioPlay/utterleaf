package org.utterleaf.voice

import android.view.View
import android.view.ViewGroup
import android.widget.Button
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AlternatePanelTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private fun buttons(view: View): List<Button> = when (view) {
        is Button -> listOf(view)
        is ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
        else -> emptyList()
    }
    private fun key(panel: TypingPanel, label: String) = buttons(panel.view).single { it.contentDescription == label }
    private fun panel(inserted: MutableList<String>, hints: Boolean = true) =
        TypingPanel(context, KeyboardOptions(secondaryHints = hints), { inserted.add(it); true }, {}, {}, {}, {}, {}, {})
            .apply { reset(false, false, "Enter") }

    @Test fun holdSelectsOneAccentAndConsumesShift() = instrumentation.runOnMainSync {
        val inserted = mutableListOf<String>(); val panel = panel(inserted)
        key(panel, "Shift off").performClick()
        val original = key(panel, "E")
        assertTrue(original.performLongClick())
        original.performClick() // Late release of replaced key must not type E.
        assertTrue(inserted.isEmpty())
        key(panel, "É").performClick()
        key(panel, "e").performClick()
        assertEquals(listOf("É", "e"), inserted)
    }

    @Test fun tapRouteAndCancelNeedNoLongPress() = instrumentation.runOnMainSync {
        val inserted = mutableListOf<String>(); val panel = panel(inserted, false)
        assertNull((key(panel, "a") as HintedKey).secondaryHint)
        key(panel, "Keyboard tools").performClick()
        key(panel, "Accents and alternate characters").performClick()
        key(panel, "n").performClick()
        key(panel, "ñ").performClick()
        key(panel, "a").performLongClick()
        key(panel, "Cancel alternate characters").performClick()
        assertEquals(listOf("ñ"), inserted)
        assertNotNull(key(panel, "a"))
    }

    @Test fun resetInvalidatesOldAlternateButtonsAndRetainsLiteralNumbers() = instrumentation.runOnMainSync {
        val inserted = mutableListOf<String>(); val panel = panel(inserted)
        assertEquals("@", (key(panel, "a") as HintedKey).secondaryHint)
        key(panel, "a").performLongClick()
        val stale = key(panel, "á")
        panel.reset(false, true, "Next")
        stale.performClick()
        key(panel, "1").performClick()
        assertEquals(listOf("1"), inserted)
    }

    @Test fun rejectedAlternateDoesNotFallbackOrDismissPicker() = instrumentation.runOnMainSync {
        val attempts = mutableListOf<String>()
        val panel = TypingPanel(context, KeyboardOptions(), { attempts.add(it); false }, {}, {}, {}, {}, {}, {})
        panel.reset(false, false, "Enter")
        key(panel, "e").performLongClick()
        key(panel, "é").performClick()
        assertEquals(listOf("é"), attempts)
        assertNotNull(key(panel, "Cancel alternate characters"))
    }

    @Test fun alternateChoicesFitNarrowLayoutsAndKeepSpokenLabels() = instrumentation.runOnMainSync {
        for (large in listOf(false, true)) for (light in listOf(false, true)) {
            val panel = TypingPanel(context, KeyboardOptions(large = large, light = light), { true }, {}, {}, {}, {}, {}, {})
            panel.reset(false, false, "Enter")
            key(panel, "a").performLongClick()
            val width = Ui.dp(context, 320)
            panel.view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
            panel.view.layout(0, 0, width, panel.view.measuredHeight)
            for (button in buttons(panel.view)) {
                assertFalse(button.contentDescription.isNullOrBlank())
                assertTrue(button.isFocusable)
                val bounds = android.graphics.Rect(0, 0, button.width, button.height)
                panel.view.offsetDescendantRectToMyCoords(button, bounds)
                assertTrue(bounds.left >= 0 && bounds.right <= width)
                assertTrue(bounds.top >= 0 && bounds.bottom <= panel.view.height)
            }
        }
    }
}
