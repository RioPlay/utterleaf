package org.utterleaf.voice

import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Rect
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.io.FileOutputStream
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ComposePanelTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext

    private fun descendants(view: View): List<View> = listOf(view) + if (view is ViewGroup)
        (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()

    private fun key(panel: TypingPanel, description: String): Button = descendants(panel.view)
        .filterIsInstance<Button>().single { it.contentDescription == description }

    private fun maybeKey(panel: TypingPanel, description: String): Button? = descendants(panel.view)
        .filterIsInstance<Button>().singleOrNull { it.contentDescription == description }

    private fun status(panel: TypingPanel): String = descendants(panel.view).filterIsInstance<TextView>()
        .map { it.text.toString() }.firstOrNull { it.startsWith("Compose") || it.contains("combination unavailable") }.orEmpty()

    private fun panel(
        attempts: MutableList<String>,
        options: KeyboardOptions = KeyboardOptions(),
        privateEditing: Boolean = false,
        accepted: () -> Boolean = { true },
        openDraft: (() -> Unit)? = null,
    ) = TypingPanel(app, options, { value -> attempts += value; accepted() }, {}, {}, {}, {}, {}, {},
        privateEditing = privateEditing, openDraft = openDraft).apply { reset(false, false, "Enter") }

    private fun openCompose(panel: TypingPanel, mark: String = "Acute compose mark") {
        if (maybeKey(panel, "Latin compose") == null) key(panel, "Keyboard tools").performClick()
        key(panel, "Latin compose").performClick()
        assertEquals("Compose: choose a mark", status(panel))
        key(panel, mark).performClick()
    }

    @Test fun tapRouteCommitsOnlyOneCompletedPairAndUnsupportedPairIsAtomic() = instrumentation.runOnMainSync {
        val attempts = mutableListOf<String>()
        val panel = panel(attempts)
        key(panel, "Keyboard tools").performClick()
        key(panel, "Latin compose").performClick()
        assertTrue(attempts.isEmpty())
        assertNotNull(key(panel, "Acute compose mark"))
        assertNotNull(key(panel, "Dot above compose mark"))
        key(panel, "Acute compose mark").performClick()
        assertEquals("Compose Acute: choose a letter", status(panel))
        key(panel, "q").performClick()
        assertTrue(attempts.isEmpty())
        assertEquals("Acute: combination unavailable", status(panel))
        key(panel, "e").performClick()
        assertEquals(listOf("é"), attempts)
        assertNull(maybeKey(panel, "Cancel compose"))
        key(panel, "e").performClick()
        assertEquals(listOf("é", "e"), attempts)
    }

    @Test fun shiftCapsCancelAndRejectedCommitHaveExplicitRecovery() = instrumentation.runOnMainSync {
        var accepted = false
        val attempts = mutableListOf<String>()
        val panel = panel(attempts, accepted = { accepted })
        openCompose(panel)
        key(panel, "Shift off").performClick()
        key(panel, "E").performClick()
        assertEquals(listOf("É"), attempts)
        assertNotNull(key(panel, "Cancel compose"))
        accepted = true
        key(panel, "E").performClick()
        assertEquals(listOf("É", "É"), attempts)
        assertNotNull(key(panel, "e"))

        val capsAttempts = mutableListOf<String>()
        val caps = panel(capsAttempts)
        key(caps, "Keyboard tools").performClick()
        key(caps, "Caps lock off").performClick()
        key(caps, "Latin compose").performClick()
        key(caps, "Acute compose mark").performClick()
        key(caps, "E").performClick()
        key(caps, "E").performClick()
        assertEquals(listOf("É", "E"), capsAttempts)

        openCompose(caps, "Tilde compose mark")
        key(caps, "Cancel compose").performClick()
        assertEquals(listOf("É", "E"), capsAttempts)
    }

    @Test fun privateDraftCanComposeWhileTerminalModeCannotEnterCompose() = instrumentation.runOnMainSync {
        val local = mutableListOf<String>()
        val privatePanel = panel(local, KeyboardOptions(terminal = true), privateEditing = true)
        openCompose(privatePanel, "Tilde compose mark")
        key(privatePanel, "n").performClick()
        assertEquals(listOf("ñ"), local)

        val terminalAttempts = mutableListOf<String>()
        val terminal = panel(terminalAttempts, KeyboardOptions(terminal = true))
        key(terminal, "Keyboard tools").performClick()
        val disabled = key(terminal, "Latin compose unavailable in terminal mode")
        assertFalse(disabled.isEnabled)
        disabled.performClick()
        assertTrue(terminalAttempts.isEmpty())
        assertNull(maybeKey(terminal, "Acute compose mark"))
    }

    @Test fun resetLayoutToolDetachAndDisposeInvalidatePendingButtons() {
        val attempts = mutableListOf<String>()
        lateinit var fixture: TypingPanel
        lateinit var staleReset: Button
        instrumentation.runOnMainSync {
            fixture = panel(attempts)
            openCompose(fixture)
            staleReset = key(fixture, "e")
            fixture.reset(false, false, "Enter")
            staleReset.performClick()
            openCompose(fixture)
            val staleLayout = key(fixture, "e")
            key(fixture, "Keyboard tools").performClick()
            key(fixture, "QWERTZ letter layout").performClick()
            staleLayout.performClick()
            openCompose(fixture)
            val staleAlignment = key(fixture, "e")
            key(fixture, "Keyboard tools").performClick()
            key(fixture, "Left hand layout").performClick()
            staleAlignment.performClick()
            openCompose(fixture)
            val staleDispose = key(fixture, "e")
            fixture.dispose()
            staleDispose.performClick()
            assertTrue(attempts.isEmpty())
        }

        val activity = instrumentation.startActivitySync(
            Intent(app, KeyboardTestActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        ) as KeyboardTestActivity
        try {
            instrumentation.runOnMainSync {
                val attached = panel(attempts)
                activity.addContentView(attached.view, ViewGroup.LayoutParams(-1, -2))
                openCompose(attached)
                val staleDetach = key(attached, "e")
                (attached.view.parent as ViewGroup).removeView(attached.view)
                staleDetach.performClick()
                assertTrue(attempts.isEmpty())
                activity.addContentView(attached.view, ViewGroup.LayoutParams(-1, -2))
                key(attached, "e").performClick()
                assertEquals(listOf("e"), attempts)
            }
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
        }
    }

    @Test fun ownedLargeComposeViewsFitThemesAndAlignments() = instrumentation.runOnMainSync {
        val directoryName = InstrumentationRegistry.getArguments().getString("composeScreenshots")
        directoryName?.let { require(it.matches(Regex("[a-zA-Z0-9_-]{1,32}"))) }
        for (light in listOf(false, true)) for (alignment in KeyboardAlignment.entries) {
            val attempts = mutableListOf<String>()
            val panel = panel(attempts, KeyboardOptions(large = true, light = light, alignment = alignment),
                openDraft = {})
            val width = Ui.dp(app, 412)
            val state = "compose-${if (light) "light" else "dark"}-${alignment.stored}"
            fun validateAndCapture(stage: String) {
                panel.view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                    View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
                panel.view.layout(0, 0, width, panel.view.measuredHeight)
                val visibleButtons = descendants(panel.view).filterIsInstance<Button>()
                    .filter { it.visibility == View.VISIBLE }
                assertTrue("$state $stage rendered no visible buttons", visibleButtons.isNotEmpty())
                visibleButtons.forEach { button ->
                    val bounds = Rect(0, 0, button.width, button.height)
                    panel.view.offsetDescendantRectToMyCoords(button, bounds)
                    assertTrue("$state $stage empty ${button.contentDescription}", bounds.width() > 0 && bounds.height() > 0)
                    assertTrue("$state $stage escaped ${button.contentDescription}: $bounds",
                        bounds.left >= 0 && bounds.right <= width && bounds.top >= 0 && bounds.bottom <= panel.view.height)
                }
                if (directoryName != null) {
                    val directory = File(checkNotNull(app.getExternalFilesDir(null)), directoryName)
                    check(directory.isDirectory || directory.mkdirs())
                    val bitmap = Bitmap.createBitmap(panel.view.width, panel.view.height, Bitmap.Config.ARGB_8888)
                    try {
                        panel.view.draw(Canvas(bitmap))
                        FileOutputStream(File(directory, "$state-$stage.png")).use {
                            bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
                        }
                    } finally {
                        bitmap.recycle()
                    }
                }
            }
            key(panel, "Keyboard tools").performClick()
            assertNotNull(key(panel, "Private draft"))
            validateAndCapture("tools")
            key(panel, "Latin compose").performClick()
            validateAndCapture("marks")
            key(panel, "Acute compose mark").performClick()
            validateAndCapture("letters")
        }
    }
}
