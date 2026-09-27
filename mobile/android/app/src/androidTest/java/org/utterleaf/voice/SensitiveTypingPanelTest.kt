package org.utterleaf.voice

import android.content.Context
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Rect
import android.os.SystemClock
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.ViewGroup
import android.widget.Button
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class SensitiveTypingPanelTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context: Context = instrumentation.targetContext

    private val forbiddenDescriptions = setOf(
        "Undo", "Redo", "Cut", "Copy", "Select neighboring word", "Select all text",
        "Keyboard tools", "Editing tools", "Extra keys", "Keyboard settings",
        "Emoji", "Dictate", "Private draft", "Latin compose",
        "Accents and alternate characters", "Move cursor left", "Move cursor right",
        "Escape", "Tab", "Control off", "Alt off", "Function keys",
        "Number row on", "Number row off",
    )

    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) }
        else emptyList()

    private fun buttons(panel: TypingPanel) = descendants(panel.view).filterIsInstance<Button>()

    private fun key(panel: TypingPanel, description: String) =
        buttons(panel).single { it.contentDescription == description }

    private fun descriptions(panel: TypingPanel) = buttons(panel)
        .mapNotNull { it.contentDescription?.toString() }.toSet()

    private fun layout(panel: TypingPanel, widthDp: Int) {
        val width = Ui.dp(panel.view.context, widthDp)
        panel.view.measure(
            View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED),
        )
        panel.view.layout(0, 0, width, panel.view.measuredHeight)
    }

    private fun field(panel: TypingPanel, name: String): Any? =
        TypingPanel::class.java.getDeclaredField(name).run {
            isAccessible = true
            get(panel)
        }

    private fun dispatch(button: Button, action: Int, x: Float, y: Float, downTime: Long) {
        val event = MotionEvent.obtain(downTime, SystemClock.uptimeMillis(), action, x, y, 0)
        try {
            button.dispatchTouchEvent(event)
        } finally {
            event.recycle()
        }
    }

    private fun initializeDetachedDrawableState(view: View) {
        view.refreshDrawableState()
        view.jumpDrawablesToCurrentState()
        if (view is ViewGroup) {
            for (index in 0 until view.childCount) {
                initializeDetachedDrawableState(view.getChildAt(index))
            }
        }
    }

    private fun captureOwnedPanel(panel: TypingPanel, name: String) {
        val exportDirectory = requireNotNull(panel.view.context.getExternalFilesDir(null)) {
            "External files directory unavailable for synthetic sensitive-panel captures"
        }
        // This direct-render fixture is never attached to a Window. Initialize
        // every drawable with its real enabled state before drawing so the
        // primary action does not remain on StateListDrawable's initial
        // disabled branch merely because attach-time propagation never ran.
        initializeDetachedDrawableState(panel.view)
        val action = key(panel, "Done")
        assertTrue("Synthetic action key was unexpectedly disabled", action.isEnabled)
        assertTrue("Synthetic action key did not resolve its enabled view state",
            action.drawableState.contains(android.R.attr.state_enabled))
        assertTrue("Synthetic action background did not receive the enabled state",
            action.background.state.contains(android.R.attr.state_enabled))
        val bitmap = Bitmap.createBitmap(
            panel.view.width.coerceAtLeast(1),
            panel.view.height.coerceAtLeast(1),
            Bitmap.Config.ARGB_8888,
        )
        val saved = try {
            panel.view.draw(Canvas(bitmap))
            File(exportDirectory, name).outputStream().use { output ->
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, output)
            }
        } finally {
            bitmap.recycle()
        }
        assertTrue("Could not save synthetic sensitive-panel capture $name", saved)
    }

    private fun assertSensitiveSurface(panel: TypingPanel, managerExpected: Boolean) {
        val labels = descriptions(panel)
        assertTrue("Sensitive panel exposed ${labels.intersect(forbiddenDescriptions)}",
            labels.intersect(forbiddenDescriptions).isEmpty())
        assertFalse("Sensitive panel rendered a suggestion",
            labels.any { it.startsWith("Complete with ") })
        assertEquals(1, buttons(panel).count { it.contentDescription == "Paste" })
        assertEquals(1, buttons(panel).count { it.contentDescription == "Switch keyboard" })
        assertEquals(if (managerExpected) 1 else 0,
            buttons(panel).count { it.contentDescription == "Open password manager" })
        assertTrue(listOf("a", "Shift off", "Delete", "Space", "Switch letters and symbols")
            .all { it in labels })
    }

    @Test fun sensitiveModeKeepsExplicitInputWithoutRetainingOrInferringTypedContent() {
        instrumentation.runOnMainSync {
            val inserted = mutableListOf<String>()
            var eraseCalls = 0
            var enterCalls = 0
            val moves = mutableListOf<Boolean>()
            var dictateCalls = 0
            var settingsCalls = 0
            var switchCalls = 0
            var quickOptionCalls = 0
            var draftCalls = 0
            var passwordManagerCalls = 0
            var terminalCalls = 0
            var modifiedCalls = 0
            val editorActions = mutableListOf<EditorAction>()
            var suggestionReads = 0
            var suggestionRequests = 0
            var completionCalls = 0
            val selectionCalls = mutableListOf<String>()
            val selection = object : BackspaceSelection {
                override fun begin(): Boolean { selectionCalls += "begin"; return true }
                override fun move(left: Boolean): Boolean { selectionCalls += "move:$left"; return true }
                override fun finish(): Boolean { selectionCalls += "finish"; return true }
                override fun cancel() { selectionCalls += "cancel" }
            }
            val panel = TypingPanel(
                context,
                KeyboardOptions(numberRow = true, extraKeys = true, autoCapitalize = true,
                    repeatGuard = true),
                { inserted += it; true },
                { eraseCalls++ },
                { enterCalls++ },
                { moves += it },
                { dictateCalls++ },
                { settingsCalls++ },
                { switchCalls++ },
                terminalKey = { _, _, _, _ -> terminalCalls++; true },
                modifiedCommit = { _, _, _ -> modifiedCalls++; true },
                quickOptionsChanged = { quickOptionCalls++ },
                editorAction = { editorActions += it; true },
                privateEditing = false,
                openDraft = { draftCalls++ },
                actionAvailable = { true },
                rawField = false,
                openPasswordManager = { passwordManagerCalls++; true },
                suggest = {
                    suggestionReads++
                    SuggestionEngine.SuggestionState("secret", listOf("secret"))
                },
                completeWord = { _, _ -> completionCalls++; true },
                requestSuggestions = { suggestionRequests++ },
                backspaceSelection = selection,
                sensitiveField = true,
            )
            panel.reset(allowVoice = true, numeric = false, action = "Done", allowEmoji = true)

            assertSensitiveSurface(panel, managerExpected = true)
            assertTrue("Sensitive number-row preference was lost", "1" in descriptions(panel))
            assertEquals(0, suggestionReads)
            assertEquals(0, suggestionRequests)

            // Repeat guard must not cache or suppress manually repeated password characters.
            key(panel, "a").performClick()
            key(panel, "a").performClick()
            key(panel, ".").performClick()
            assertTrue("Sensitive punctuation armed automatic capitalization", "a" in descriptions(panel))
            key(panel, "a").performClick()

            // Manual Shift and Caps remain explicit user input.
            key(panel, "Shift off").performClick()
            key(panel, "A").performClick()
            assertTrue(key(panel, "Shift off").performLongClick())
            key(panel, "B").performClick()
            key(panel, "B").performClick()
            assertTrue(key(panel, "Shift on").performLongClick())

            // Literal alternates and symbols remain available without opening a Tools layer.
            assertTrue(key(panel, "e").performLongClick())
            key(panel, "é").performClick()
            key(panel, "1").performClick()
            key(panel, "Switch letters and symbols").performClick()
            key(panel, "@").performClick()
            key(panel, "Switch letters and symbols").performClick()
            key(panel, "Space").performClick()
            key(panel, "Delete").performClick()
            key(panel, "Done").performClick()
            key(panel, "Paste").performClick()
            key(panel, "Switch keyboard").performClick()
            key(panel, "Open password manager").performClick()

            assertEquals(listOf("a", "a", ".", "a", "A", "B", "B", "é", "1", "@", " "), inserted)
            assertEquals(1, eraseCalls)
            assertEquals(1, enterCalls)
            assertEquals(listOf(EditorAction.PASTE), editorActions)
            assertEquals(1, switchCalls)
            assertEquals(1, passwordManagerCalls)
            assertEquals(0, dictateCalls)
            assertEquals(0, settingsCalls)
            assertEquals(0, quickOptionCalls)
            assertEquals(0, draftCalls)
            assertEquals(0, terminalCalls)
            assertEquals(0, modifiedCalls)
            assertTrue(moves.isEmpty())
            assertTrue(selectionCalls.isEmpty())
            assertEquals(0, suggestionReads)
            assertEquals(0, suggestionRequests)
            assertEquals(0, completionCalls)
            assertEquals("Sensitive panel retained the last typed key", "", field(panel, "lastKey"))
            assertEquals("Sensitive panel retained a last-key timestamp", 0L, field(panel, "lastTime"))
            panel.dispose()
        }
    }

    @Test fun sensitiveModeRejectsHostContextGesturesWithoutDelays() {
        instrumentation.runOnMainSync {
            val inserted = mutableListOf<String>()
            val moves = mutableListOf<Boolean>()
            var eraseCalls = 0
            val selectionCalls = mutableListOf<String>()
            val selection = object : BackspaceSelection {
                override fun begin(): Boolean { selectionCalls += "begin"; return true }
                override fun move(left: Boolean): Boolean { selectionCalls += "move:$left"; return true }
                override fun finish(): Boolean { selectionCalls += "finish"; return true }
                override fun cancel() { selectionCalls += "cancel" }
            }
            val panel = TypingPanel(
                context,
                KeyboardOptions(deleteRepeat = true, repeatGuard = false),
                { inserted += it; true },
                { eraseCalls++ },
                {},
                { moves += it },
                {}, {}, {},
                backspaceSelection = selection,
                sensitiveField = true,
            )
            panel.reset(allowVoice = false, numeric = false, action = "Enter")
            layout(panel, 360)

            val space = key(panel, "Space")
            val spaceDown = SystemClock.uptimeMillis()
            val spaceX = space.width / 2f
            val spaceY = space.height / 2f
            val cursorStep = maxOf(ViewConfiguration.get(context).scaledTouchSlop, Ui.dp(context, 16)).toFloat()
            dispatch(space, MotionEvent.ACTION_DOWN, spaceX, spaceY, spaceDown)
            dispatch(space, MotionEvent.ACTION_MOVE, spaceX - cursorStep * 2, spaceY, spaceDown)
            dispatch(space, MotionEvent.ACTION_UP, spaceX - cursorStep * 2, spaceY, spaceDown)

            val delete = key(panel, "Delete")
            val deleteDown = SystemClock.uptimeMillis()
            val deleteX = delete.width - 2f
            val deleteY = delete.height / 2f
            val selectionStep = ViewConfiguration.get(context).scaledTouchSlop + 2f
            dispatch(delete, MotionEvent.ACTION_DOWN, deleteX, deleteY, deleteDown)
            dispatch(delete, MotionEvent.ACTION_MOVE, deleteX - selectionStep, deleteY, deleteDown)
            dispatch(delete, MotionEvent.ACTION_UP, deleteX - selectionStep, deleteY, deleteDown)

            assertTrue("Sensitive Space drag reached host cursor movement", moves.isEmpty())
            assertTrue("Sensitive Backspace swipe reached host selection", selectionCalls.isEmpty())
            assertEquals("A synchronous swipe unexpectedly became a held delete", 0, eraseCalls)
            assertTrue("A refused sensitive gesture inserted text", inserted.isEmpty())
            panel.dispose()
        }
    }

    @Test fun disposedOrdinaryControlsCannotCrossIntoSensitiveReplacement() {
        instrumentation.runOnMainSync {
            val inserted = mutableListOf<String>()
            var dictateCalls = 0
            var settingsCalls = 0
            var switchCalls = 0
            var draftCalls = 0
            val editorActions = mutableListOf<EditorAction>()
            val ordinary = TypingPanel(
                context,
                KeyboardOptions(extraKeys = true),
                { inserted += it; true }, {}, {}, {},
                { dictateCalls++ }, { settingsCalls++ }, { switchCalls++ },
                editorAction = { editorActions += it; true },
                openDraft = { draftCalls++ },
            )
            ordinary.reset(allowVoice = true, numeric = false, action = "Enter")
            val stale = mutableListOf(
                key(ordinary, "a"),
                key(ordinary, "Keyboard tools"),
                key(ordinary, "Editing tools"),
                key(ordinary, "Dictate"),
            )
            key(ordinary, "Keyboard tools").performClick()
            stale += key(ordinary, "Emoji")
            stale += key(ordinary, "Private draft")
            key(ordinary, "Editing tools").performClick()
            stale += key(ordinary, "Paste")
            stale += key(ordinary, "Extra keys")
            ordinary.dispose()

            val sensitive = TypingPanel(
                context, KeyboardOptions(extraKeys = true),
                { inserted += it; true }, {}, {}, {},
                { dictateCalls++ }, { settingsCalls++ }, { switchCalls++ },
                editorAction = { editorActions += it; true },
                openDraft = { draftCalls++ },
                sensitiveField = true,
            )
            sensitive.reset(allowVoice = true, numeric = false, action = "Enter", allowEmoji = true)
            assertSensitiveSurface(sensitive, managerExpected = false)
            stale.forEach { it.performClick() }

            assertTrue(inserted.isEmpty())
            assertTrue(editorActions.isEmpty())
            assertEquals(0, dictateCalls)
            assertEquals(0, settingsCalls)
            assertEquals(0, switchCalls)
            assertEquals(0, draftCalls)
            assertSensitiveSurface(sensitive, managerExpected = false)
            key(sensitive, "a").performClick()
            assertEquals(listOf("a"), inserted)
            sensitive.dispose()
        }
    }

    @Test fun sensitiveToolbarIsMinimalAndReachableInPortraitAndLandscape() {
        instrumentation.runOnMainSync {
            val configurations = listOf(
                Configuration.ORIENTATION_PORTRAIT to 320,
                Configuration.ORIENTATION_LANDSCAPE to 600,
            )
            for ((orientation, widthDp) in configurations) {
                val configured = Configuration(context.resources.configuration).apply {
                    this.orientation = orientation
                    screenWidthDp = widthDp
                }
                val panelContext = context.createConfigurationContext(configured)
                val panel = TypingPanel(
                    panelContext,
                    KeyboardOptions(extraKeys = true),
                    { true }, {}, {}, {}, {}, {}, {},
                    editorAction = { true },
                    openDraft = {},
                    openPasswordManager = { true },
                    suggest = { SuggestionEngine.SuggestionState("secret", listOf("secret")) },
                    requestSuggestions = {},
                    sensitiveField = true,
                )
                panel.reset(allowVoice = true, numeric = false, action = "Done", allowEmoji = true)
                layout(panel, widthDp)
                assertSensitiveSurface(panel, managerExpected = true)

                val toolbar = listOf("Paste", "Switch keyboard", "Open password manager").map {
                    val button = key(panel, it)
                    val bounds = Rect(0, 0, button.width, button.height)
                    panel.view.offsetDescendantRectToMyCoords(button, bounds)
                    assertTrue("$it was narrower than 48dp in $orientation",
                        bounds.width() >= Ui.dp(panelContext, 48))
                    assertTrue("$it was shorter than 48dp in $orientation",
                        bounds.height() >= Ui.dp(panelContext, 48))
                    assertTrue("$it escaped the sensitive panel in $orientation",
                        bounds.left >= 0 && bounds.right <= panel.view.width)
                    bounds
                }
                assertEquals("Sensitive actions split across rows in $orientation",
                    1, toolbar.map { it.top }.toSet().size)
                captureOwnedPanel(panel, if (orientation == Configuration.ORIENTATION_PORTRAIT)
                    "sensitive-portrait.png" else "sensitive-landscape.png")
                panel.dispose()
            }
        }
    }

    @Test fun sensitiveFlagDoesNotRedefineOrdinaryRawOrPrivateProfiles() {
        instrumentation.runOnMainSync {
            fun panel(privateEditing: Boolean = false, raw: Boolean = false): TypingPanel =
                TypingPanel(
                    context, KeyboardOptions(extraKeys = true),
                    { true }, {}, {}, {}, {}, {}, {},
                    privateEditing = privateEditing,
                    openDraft = {},
                    rawField = raw,
                ).also { it.reset(allowVoice = true, numeric = false, action = "Enter", allowEmoji = !raw) }

            val ordinary = panel()
            val raw = panel(raw = true)
            val private = panel(privateEditing = true)
            assertTrue(descriptions(ordinary).containsAll(
                setOf("Keyboard tools", "Editing tools", "Dictate")))
            assertTrue(descriptions(raw).containsAll(
                setOf("Keyboard tools", "Editing tools", "Dictate")))
            assertTrue(descriptions(private).containsAll(
                setOf("Keyboard tools", "Editing tools")))
            assertFalse(descriptions(private).any {
                it in setOf("Switch keyboard", "Private draft", "Dictate")
            })
            key(ordinary, "Keyboard tools").performClick()
            assertTrue(descriptions(ordinary).containsAll(setOf("Emoji", "Private draft", "Extra keys")))
            key(raw, "Keyboard tools").performClick()
            assertTrue(descriptions(raw).containsAll(setOf("Emoji", "Extra keys")))
            key(private, "Keyboard tools").performClick()
            assertTrue(descriptions(private).containsAll(setOf("Emoji", "Extra keys")))
            assertFalse(descriptions(private).any {
                it in setOf("Switch keyboard", "Private draft", "Dictate")
            })
            listOf(ordinary, raw, private).forEach { it.dispose() }
        }
    }
}
