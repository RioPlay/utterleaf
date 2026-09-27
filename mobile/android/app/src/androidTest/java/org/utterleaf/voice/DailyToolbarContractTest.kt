package org.utterleaf.voice

import android.content.Context
import android.content.res.Configuration
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class DailyToolbarContractTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context: Context = instrumentation.targetContext

    private fun buttons(view: View): List<Button> = when (view) {
        is Button -> listOf(view)
        is ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
        else -> emptyList()
    }

    private fun descriptions(panel: TypingPanel) = buttons(panel.view)
        .mapNotNull { it.contentDescription?.toString() }.toSet()

    private fun panel(
        panelContext: Context = context,
        privateEditing: Boolean = false,
        allowVoice: Boolean = true,
        raw: Boolean = false,
        sensitive: Boolean = false,
        draft: (() -> Unit)? = {},
        password: (() -> Boolean)? = null,
        available: (EditorAction) -> Boolean = { true },
    ) = TypingPanel(panelContext, KeyboardOptions(extraKeys = true), { true }, {}, {}, {}, {}, {}, {},
        editorAction = { true }, privateEditing = privateEditing, openDraft = draft,
        actionAvailable = available, rawField = raw, openPasswordManager = password,
        sensitiveField = sensitive).also {
        it.reset(allowVoice, numeric = false, action = "Enter")
    }

    @Test fun dailyActionsHaveExplicitFieldProfileContracts() {
        instrumentation.runOnMainSync {
            val daily = setOf("Keyboard tools", "Editing tools")
            val advanced = setOf("Undo", "Redo", "Select neighboring word", "Cut", "Copy",
                "Paste", "Emoji", "Extra keys", "Private draft", "Open password manager")

            val ordinary = panel()
            assertTrue(descriptions(ordinary).containsAll(daily + "Dictate"))
            assertTrue("Advanced actions must not crowd the daily surface",
                descriptions(ordinary).intersect(advanced).isEmpty())

            val password = panel(allowVoice = false, sensitive = true, draft = null, password = { true })
            val passwordActions = descriptions(password)
            assertTrue(passwordActions.intersect(daily + advanced + setOf("Dictate", "Switch keyboard")) ==
                setOf("Paste", "Open password manager", "Switch keyboard"))

            val raw = panel(allowVoice = false, raw = true, draft = null) { false }
            assertTrue(descriptions(raw).containsAll(daily + "Dictate"))
            assertTrue(descriptions(raw).intersect(advanced).isEmpty())
            buttons(raw.view).single { it.contentDescription == "Editing tools" }.performClick()
            for (action in listOf("Undo", "Redo", "Cut", "Copy", "Paste", "Select neighboring word")) {
                assertFalse("$action must explain unavailability by being disabled in raw input",
                    buttons(raw.view).single { it.contentDescription == action }.isEnabled)
            }

            val private = panel(privateEditing = true, draft = null) { action ->
                action in setOf(EditorAction.UNDO, EditorAction.REDO, EditorAction.SELECT_ALL)
            }
            val privateActions = descriptions(private)
            assertTrue(privateActions.containsAll(daily))
            assertTrue(privateActions.intersect(setOf("Cut", "Copy", "Paste", "Private draft", "Dictate",
                "Open password manager")).isEmpty())

            listOf(ordinary, password, raw, private).forEach { it.dispose() }
        }
    }

    @Test fun dailyStripKeepsAccessibleTargetsInPortraitAndLandscapeWidths() {
        instrumentation.runOnMainSync {
            val configurations = listOf(
                Configuration.ORIENTATION_PORTRAIT to listOf(320, 360, 411),
                Configuration.ORIENTATION_LANDSCAPE to listOf(600, 800),
            )
            for ((orientation, widths) in configurations) for (widthDp in widths) {
                val configured = Configuration(context.resources.configuration).apply {
                    this.orientation = orientation
                }
                val panelContext = context.createConfigurationContext(configured)
                val panel = panel(panelContext = panelContext)
                val width = Ui.dp(panelContext, widthDp)
                panel.view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                    View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
                panel.view.layout(0, 0, width, panel.view.measuredHeight)
                for (description in listOf("Keyboard tools", "Editing tools", "Dictate")) {
                    val button = buttons(panel.view).single { it.contentDescription == description }
                    assertTrue("$description was narrower than 48dp at ${widthDp}dp width",
                        button.measuredWidth >= Ui.dp(panelContext, 48))
                    assertTrue("$description lost its 48dp touch height",
                        button.measuredHeight >= Ui.dp(panelContext, 48))
                }
                panel.dispose()
            }
        }
    }

    @Test fun toolsDisclosesSecondaryDestinationsAndEditReturnsInOneTap() {
        instrumentation.runOnMainSync {
            val panel = panel()
            buttons(panel.view).single { it.contentDescription == "Keyboard tools" }.performClick()
            assertTrue(descriptions(panel).containsAll(setOf("Editing tools", "Emoji", "Private draft", "Extra keys")))

            buttons(panel.view).single { it.contentDescription == "Editing tools" }.performClick()
            assertTrue(descriptions(panel).containsAll(setOf("Undo", "Redo", "Cut", "Copy", "Paste",
                "Select neighboring word", "Close editing tools")))
            buttons(panel.view).single { it.contentDescription == "Close editing tools" }.performClick()
            assertTrue(descriptions(panel).containsAll(setOf("Keyboard tools", "Editing tools", "Dictate")))
            panel.dispose()
        }
    }
}
