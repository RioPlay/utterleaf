package org.utterleaf.voice

import android.content.Context
import android.content.res.Configuration
import android.graphics.Rect
import android.view.MotionEvent
import android.view.View
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
import java.io.FileOutputStream

@RunWith(AndroidJUnit4::class)
class SplitKeyboardTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()

    private fun context(orientation: Int, widthDp: Int): Context {
        val configuration = Configuration(instrumentation.targetContext.resources.configuration).apply {
            this.orientation = orientation
            screenWidthDp = widthDp
            screenHeightDp = if (orientation == Configuration.ORIENTATION_LANDSCAPE) 411 else 914
        }
        return instrumentation.targetContext.createConfigurationContext(configuration)
    }

    private fun buttons(view: View): List<Button> = when (view) {
        is Button -> listOf(view)
        is ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
        else -> emptyList()
    }

    private fun panel(context: Context, options: KeyboardOptions, typed: MutableList<String> = mutableListOf(),
        staged: ((KeyboardOptions) -> Unit)? = null): TypingPanel = TypingPanel(context, options,
        { typed += it; true }, {}, {}, {}, {}, {}, {}, stageOptions = staged).apply {
        reset(false, false, "Enter")
    }

    private fun layout(panel: TypingPanel, widthDp: Int) {
        val width = Ui.dp(panel.view.context, widthDp)
        panel.view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
        panel.view.layout(0, 0, width, panel.view.measuredHeight)
    }

    private fun bounds(panel: TypingPanel, description: String): Rect {
        val key = buttons(panel.view).single { it.contentDescription == description }
        return Rect(0, 0, key.width, key.height).also { panel.view.offsetDescendantRectToMyCoords(key, it) }
    }

    @Test fun splitCreatesAnInactiveCenterGapAndKeepsEveryTypingKey() {
        instrumentation.runOnMainSync {
            val typed = mutableListOf<String>()
            val context = context(Configuration.ORIENTATION_LANDSCAPE, 914)
            val panel = panel(context, KeyboardOptions(splitLandscape = true), typed)
            layout(panel, 914)

            InstrumentationRegistry.getArguments().getString("r2Screenshots")?.let { name ->
                require(name.matches(Regex("[a-zA-Z0-9_-]{1,32}")))
                val directory = File(checkNotNull(instrumentation.targetContext.getExternalFilesDir(null)), name)
                check(directory.isDirectory || directory.mkdirs())
                val bitmap = android.graphics.Bitmap.createBitmap(panel.view.width, panel.view.height,
                    android.graphics.Bitmap.Config.ARGB_8888)
                try {
                    panel.view.draw(android.graphics.Canvas(bitmap))
                    FileOutputStream(File(directory, "split-landscape.png")).use {
                        bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it)
                    }
                } finally { bitmap.recycle() }
            }

            val descriptions = buttons(panel.view).map { it.contentDescription.toString() }
            "qwertyuiopasdfghjklzxcvbnm1234567890".forEach { character ->
                assertTrue("Missing $character", character.toString() in descriptions)
            }
            assertEquals(2, descriptions.count { it == "Space" })
            val left = bounds(panel, "t")
            val right = bounds(panel, "y")
            assertTrue("Landscape split gap is too narrow", right.left - left.right >= Ui.dp(context, 68))
            assertTrue(left.right < panel.view.width / 2)
            assertTrue(right.left > panel.view.width / 2)

            val down = MotionEvent.obtain(1L, 1L, MotionEvent.ACTION_DOWN,
                panel.view.width / 2f, left.centerY().toFloat(), 0)
            val up = MotionEvent.obtain(1L, 2L, MotionEvent.ACTION_UP,
                panel.view.width / 2f, left.centerY().toFloat(), 0)
            try {
                panel.view.dispatchTouchEvent(down)
                panel.view.dispatchTouchEvent(up)
            } finally {
                down.recycle(); up.recycle()
            }
            assertTrue("Center gap accepted a key press", typed.isEmpty())

            buttons(panel.view).single { it.contentDescription == "Switch letters and symbols" }.performClick()
            layout(panel, 914)
            val symbols = buttons(panel.view).map { it.contentDescription.toString() }
            "1234567890@#$%&-+()/*\"':;!?_".forEach { character ->
                assertTrue("Missing symbol $character", character.toString() in symbols)
            }
        }
    }

    @Test fun portraitFallsBackToTheStandardLayout() {
        instrumentation.runOnMainSync {
            val context = context(Configuration.ORIENTATION_PORTRAIT, 411)
            val panel = panel(context, KeyboardOptions(splitLandscape = true))
            layout(panel, 411)
            val left = bounds(panel, "t")
            val right = bounds(panel, "y")
            assertTrue("Portrait unexpectedly kept the split gap", right.left - left.right < Ui.dp(context, 20))
            assertEquals(1, buttons(panel.view).count { it.contentDescription == "Space" })
        }
    }

    @Test fun splitAndOneHandChoicesCannotConflict() {
        instrumentation.runOnMainSync {
            val context = context(Configuration.ORIENTATION_LANDSCAPE, 914)
            var staged = KeyboardOptions()
            val panel = panel(context, staged, staged = { staged = it })
            layout(panel, 914)
            fun key(description: String) = buttons(panel.view).single { it.contentDescription == description }

            key("Keyboard tools").performClick()
            key("Split keyboard in landscape").performClick()
            assertTrue(staged.splitLandscape)
            assertEquals(KeyboardAlignment.FULL, staged.alignment)
            key("Left hand layout").performClick()
            assertFalse(staged.splitLandscape)
            assertEquals(KeyboardAlignment.LEFT, staged.alignment)
        }
    }
}
