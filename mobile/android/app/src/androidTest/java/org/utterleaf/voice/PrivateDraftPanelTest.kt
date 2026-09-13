package org.utterleaf.voice

import android.graphics.Rect
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PrivateDraftPanelTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext

    private fun descendants(view: View): List<View> = listOf(view) + if (view is ViewGroup)
        (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()

    private fun buttons(panel: PrivateDraftPanel) = descendants(panel.view).filterIsInstance<Button>()

    private fun key(panel: PrivateDraftPanel, description: String) = buttons(panel)
        .single { it.contentDescription == description }

    private fun editor(panel: PrivateDraftPanel) = descendants(panel.view).filterIsInstance<EditText>()
        .single { it.tag == "private-draft-text" }

    private fun status(panel: PrivateDraftPanel) = descendants(panel.view).filterIsInstance<TextView>()
        .single { it.tag == "private-draft-status" }

    private fun awaitButton(panel: PrivateDraftPanel, description: String): Button {
        val deadline = SystemClock.elapsedRealtime() + 10_000
        while (SystemClock.elapsedRealtime() < deadline) {
            var found: Button? = null
            instrumentation.runOnMainSync {
                found = buttons(panel).firstOrNull { it.contentDescription == description }
            }
            if (found != null) return found!!
            Thread.sleep(25)
        }
        throw AssertionError("Missing $description")
    }

    @Test fun ownedTypingEditingAndEmojiNeverCallTheHostInsertionRoute() {
        val attempts = mutableListOf<String>()
        lateinit var panel: PrivateDraftPanel
        var created: PrivateDraftPanel? = null
        try {
            instrumentation.runOnMainSync {
                panel = PrivateDraftPanel(app, KeyboardOptions(), {
                    attempts += it
                    DraftInsertionResult.UNAVAILABLE
                }, {})
                created = panel
                assertEquals("", editor(panel).text.toString())
                assertFalse(key(panel, "Insert private draft").isEnabled)
                assertFalse(key(panel, "Clear private draft").isEnabled)
                assertTrue(key(panel, "Discard private draft").isEnabled)

                key(panel, "a").performClick()
                key(panel, "b").performClick()
                key(panel, "Keyboard tools").performClick()
                key(panel, "Move cursor left").performClick()
                key(panel, "Delete").performClick()
                key(panel, "Keyboard tools").performClick()
                key(panel, "Edit actions").performClick()
                key(panel, "Undo").performClick()
                assertEquals("ab", editor(panel).text.toString())
                assertTrue(attempts.isEmpty())
                key(panel, "Close edit actions").performClick()
                key(panel, "Emoji").performClick()
            }

            val emoji = awaitButton(panel, "grinning face")
            instrumentation.runOnMainSync {
                emoji.performClick()
                assertEquals("a😀b", editor(panel).text.toString())
                assertTrue(attempts.isEmpty())
                panel.clear()
            }
        } finally {
            created?.let { instrumentation.runOnMainSync { it.clear() } }
        }
    }

    @Test fun insertionOutcomesRetainOrDisposeExactlyAsAcknowledged() {
        val outcomes = ArrayDeque(listOf(
            DraftInsertionResult.UNAVAILABLE,
            DraftInsertionResult.UNCONFIRMED,
            DraftInsertionResult.INSERTED,
        ))
        val attempts = mutableListOf<String>()
        var exits = 0
        instrumentation.runOnMainSync {
            val panel = PrivateDraftPanel(app, KeyboardOptions(), {
                attempts += it
                outcomes.removeFirst()
            }, { exits++ })
            val staleInsert = key(panel, "Insert private draft")
            listOf("c", "a", "f", "e").forEach { key(panel, it).performClick() }

            staleInsert.performClick()
            assertEquals(listOf("cafe"), attempts)
            assertEquals("cafe", editor(panel).text.toString())
            assertTrue(staleInsert.isEnabled)
            assertTrue(status(panel).text.toString().contains("stays here"))

            staleInsert.performClick()
            assertEquals(2, attempts.size)
            assertFalse(staleInsert.isEnabled)
            assertTrue(status(panel).text.toString().contains("did not confirm"))
            val acknowledge = key(panel, "Enable another insert")
            acknowledge.performClick()
            assertEquals("Acknowledgement attempted insertion", 2, attempts.size)
            assertTrue(staleInsert.isEnabled)

            staleInsert.performClick()
            assertEquals(3, attempts.size)
            assertEquals(1, exits)
            assertTrue(buttons(panel).isEmpty())
            staleInsert.performClick()
            acknowledge.performClick()
            assertEquals(3, attempts.size)
            assertEquals(1, exits)
        }
    }

    @Test fun clearAndDiscardRemoveTextHistoryAndInvalidateStaleControls() {
        val attempts = mutableListOf<String>()
        var exits = 0
        instrumentation.runOnMainSync {
            val panel = PrivateDraftPanel(app, KeyboardOptions(), {
                attempts += it
                DraftInsertionResult.INSERTED
            }, { exits++ })
            val staleLetter = key(panel, "x")
            staleLetter.performClick()
            key(panel, "Clear private draft").performClick()
            assertEquals("", editor(panel).text.toString())
            assertFalse(key(panel, "Insert private draft").isEnabled)
            key(panel, "Keyboard tools").performClick()
            key(panel, "Edit actions").performClick()
            assertFalse(key(panel, "Undo").isEnabled)
            key(panel, "Close edit actions").performClick()
            staleLetter.performClick()
            val discard = key(panel, "Discard private draft")
            val insert = key(panel, "Insert private draft")
            discard.performClick()
            assertEquals(1, exits)
            assertTrue(buttons(panel).isEmpty())
            staleLetter.performClick()
            insert.performClick()
            discard.performClick()
            assertTrue(attempts.isEmpty())
            assertEquals(1, exits)
        }
    }

    @Test fun largeLabelsBothThemesAndEveryAlignmentStayInTheirOwnedColumn() {
        instrumentation.runOnMainSync {
            for (light in listOf(false, true)) for (alignment in KeyboardAlignment.entries) {
                val state = "${if (light) "light" else "dark"}-${alignment.stored}"
                val panel = PrivateDraftPanel(app, KeyboardOptions(
                    large = true,
                    light = light,
                    alignment = alignment,
                    bottomPaddingDp = 24,
                ), { DraftInsertionResult.UNAVAILABLE }, {})
                try {
                    val width = Ui.dp(app, 600)
                    panel.view.measure(
                        View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                        View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED),
                    )
                    panel.view.layout(0, 0, width, panel.view.measuredHeight)
                    val column = descendants(panel.view).filterIsInstance<ViewGroup>()
                        .single { it.tag == "private-draft-column" }
                    val expected = ((width.toLong() * 82L) / 100L).toInt()
                        .coerceIn(Ui.dp(app, 320), Ui.dp(app, 360))
                    assertEquals("$state column width", if (alignment == KeyboardAlignment.FULL) width else expected,
                        column.width)
                    if (alignment != KeyboardAlignment.RIGHT) assertEquals("$state left", 0, column.left)
                    if (alignment == KeyboardAlignment.RIGHT) assertEquals("$state right", width, column.right)
                    assertNotNull(descendants(panel.view).singleOrNull { it.tag == "private-draft-text" })
                    buttons(panel).filter { it.isEnabled && it.visibility == View.VISIBLE }.forEach { button ->
                        val bounds = Rect(0, 0, button.width, button.height)
                        column.offsetDescendantRectToMyCoords(button, bounds)
                        assertTrue("$state button escaped column: $bounds",
                            bounds.width() > 0 && bounds.height() > 0 && bounds.left >= 0 &&
                                bounds.right <= column.width && bounds.top >= 0 && bounds.bottom <= column.height)
                    }
                } finally {
                    panel.clear()
                }
            }
        }
    }
}
