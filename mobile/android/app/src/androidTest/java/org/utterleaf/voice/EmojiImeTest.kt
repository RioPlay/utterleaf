package org.utterleaf.voice

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Rect
import android.provider.Settings
import android.text.Selection
import android.view.View
import android.view.ViewGroup
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.atomic.AtomicReference
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class EmojiImeTest {
    private data class OwnedGeometry(val surfaceWidth: Int, val left: Int, val right: Int) {
        val width: Int get() = right - left
    }

    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext

    private fun shell(command: String) = android.os.ParcelFileDescriptor.AutoCloseInputStream(
        instrumentation.uiAutomation.executeShellCommand(command),
    ).bufferedReader().use { it.readText() }

    private fun <T> main(block: () -> T): T {
        val result = AtomicReference<T>()
        instrumentation.runOnMainSync { result.set(block()) }
        return result.get()
    }

    private fun await(message: String, condition: () -> Boolean) {
        val deadline = android.os.SystemClock.elapsedRealtime() + 10_000
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            if (condition()) return
            Thread.sleep(50)
        }
        throw AssertionError(message)
    }

    private fun findNode(description: String): AccessibilityNodeInfo? {
        fun find(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
            if (node.contentDescription?.toString() == description) return node
            for (index in 0 until node.childCount) node.getChild(index)?.let(::find)?.let { return it }
            return null
        }
        return instrumentation.uiAutomation.windows.asSequence()
            .filter { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD }
            .mapNotNull { it.root?.let(::find) }
            .firstOrNull()
    }

    private fun press(description: String) {
        await("Missing enabled $description") { findNode(description)?.isEnabled == true }
        val deadline = android.os.SystemClock.elapsedRealtime() + 2_000
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            if (findNode(description)?.performAction(AccessibilityNodeInfo.ACTION_CLICK) == true) {
                instrumentation.waitForIdleSync()
                return
            }
            Thread.sleep(50)
        }
        throw AssertionError("Could not press $description")
    }

    private fun typeQuery(value: String, unchanged: () -> Unit = {}) {
        value.forEach { character ->
            press(if (character == ' ') "Emoji search space" else "Emoji search letter $character")
            unchanged()
        }
    }

    private fun queryText(): String? = main {
        android.view.inspector.WindowInspector.getGlobalWindowViews()
            .flatMap(::descendants)
            .filterIsInstance<TextView>()
            .singleOrNull { it.tag == "emoji-query" }
            ?.text?.toString()
    }

    private fun currentKeyboardSurface(): KeyboardSurface = main {
        android.view.inspector.WindowInspector.getGlobalWindowViews()
            .flatMap(::descendants)
            .filterIsInstance<KeyboardSurface>()
            .single { it.isShown }
    }

    private fun launch(raw: Boolean = false, password: Boolean = false): KeyboardEditorContractActivity {
        val activity = instrumentation.startActivitySync(
            Intent(app, KeyboardEditorContractActivity::class.java)
                .putExtra("ime_options", EditorInfo.IME_ACTION_DONE)
                .putExtra("raw", raw)
                .putExtra("password", password)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        ) as KeyboardEditorContractActivity
        await("Editor activity never acquired window focus") { main { activity.hasWindowFocus() } }
        main { activity.editor.requestFocus() }
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        await("Editor never became active") { main { manager.isActive(activity.editor) } }
        main { manager.showSoftInput(activity.editor, InputMethodManager.SHOW_IMPLICIT) }
        await("Typing keyboard did not appear") {
            findNode(if (raw) "Emoji unavailable in raw input" else "Emoji") != null
        }
        return activity
    }

    private fun close(activity: KeyboardEditorContractActivity) {
        main { activity.finish() }
        await("Previous IME session did not close") {
            findNode("Keyboard tools") == null && findNode("Return from emoji to letters") == null
        }
    }

    private fun withKeyboard(block: (InputMethodManager) -> Unit) {
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        val id = manager.inputMethodList.single { it.serviceName == KeyboardIme::class.java.name }.id
        val previous = Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
        val enabled = manager.enabledInputMethodList.any { it.id == id }
        val options = KeyboardOptions.load(app)
        val automation = instrumentation.uiAutomation
        val flags = automation.serviceInfo.flags
        try {
            automation.serviceInfo = automation.serviceInfo.apply {
                this.flags = flags or AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            }
            shell("ime enable $id")
            shell("ime set $id")
            KeyboardOptions().save(app)
            await("Typing IME was not selected") {
                Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD) == id
            }
            block(manager)
        } finally {
            if (!previous.isNullOrBlank()) shell("ime set $previous")
            if (!enabled) shell("ime disable $id")
            options.save(app)
            automation.serviceInfo = automation.serviceInfo.apply { this.flags = flags }
        }
    }

    @Test fun searchIsLocalAndOneExplicitEmojiReplacesSelectionExactlyOnce() = withKeyboard {
        val clipboard = app.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clipboardText = "synthetic emoji clipboard"
        clipboard.setPrimaryClip(ClipData.newPlainText("emoji-test", clipboardText))
        val emoji = "👩🏽‍⚕️"
        var opened: KeyboardEditorContractActivity? = null
        try {
            val activity = launch()
            opened = activity
            val original = "before SELECT after"
            val selectionStart = original.indexOf("SELECT")
            val selectionEnd = selectionStart + "SELECT".length
            main {
                activity.editor.setText(original)
                Selection.setSelection(activity.editor.text, selectionStart, selectionEnd)
            }
            press("Emoji")
            press("Search emoji")
            typeQuery("woman health worker medium skin tone") {
                main {
                    assertEquals(original, activity.editor.text.toString())
                    assertEquals(selectionStart, activity.editor.selectionStart)
                    assertEquals(selectionEnd, activity.editor.selectionEnd)
                    assertEquals(EditorInfo.IME_ACTION_NONE, activity.action)
                }
            }
            assertEquals("woman health worker medium skin tone", queryText())
            assertEquals(clipboardText, clipboard.primaryClip?.getItemAt(0)?.text?.toString())

            val chosen = findNode("woman health worker: medium skin tone")
            assertNotNull("Expected API 35 glyph was not offered", chosen)
            assertTrue(chosen!!.performAction(AccessibilityNodeInfo.ACTION_CLICK))
            await("Chosen emoji did not replace the selection exactly once") {
                main { activity.editor.text.toString() == "before $emoji after" }
            }
            Thread.sleep(200)
            main {
                assertEquals("before $emoji after", activity.editor.text.toString())
                assertEquals(EditorInfo.IME_ACTION_NONE, activity.action)
            }
            assertEquals(clipboardText, clipboard.primaryClip?.getItemAt(0)?.text?.toString())

            press("Return from emoji to letters")
            chosen.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            Thread.sleep(200)
            assertEquals("Detached emoji result inserted text", "before $emoji after",
                main { activity.editor.text.toString() })
            press("x")
            await("ABC did not return to ordinary typing") {
                main { activity.editor.text.toString() == "before ${emoji}x after" }
            }
            press("Edit actions")
            press("Paste")
            await("Explicit Paste did not use the unchanged synthetic clipboard") {
                main { activity.editor.text.toString() == "before ${emoji}x$clipboardText after" }
            }
            assertEquals(clipboardText, clipboard.primaryClip?.getItemAt(0)?.text?.toString())
            assertEquals(EditorInfo.IME_ACTION_NONE, main { activity.action })
        } finally {
            clipboard.clearPrimaryClip()
            opened?.let(::close)
        }
    }

    @Test fun hideFieldChangeRawAndPasswordClearOrGateEmojiState() = withKeyboard { manager ->
        var activity = launch()
        try {
            press("Emoji")
            press("Search emoji")
            typeQuery("wave")
            assertEquals("wave", queryText())
            val surface = currentKeyboardSurface()
            val service = surface.context as KeyboardIme
            val ownedQuery = main {
                descendants(surface).filterIsInstance<TextView>().single { it.tag == "emoji-query" }
            }
            val staleFieldKey = checkNotNull(findNode("Emoji search letter z"))
            main {
                service.onStartInput(EditorInfo().apply {
                    inputType = android.text.InputType.TYPE_CLASS_TEXT
                }, false)
                assertEquals("", ownedQuery.text.toString())
                assertFalse(ownedQuery.isAttachedToWindow)
                assertFalse(surface.isAttachedToWindow)
            }
            staleFieldKey.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            Thread.sleep(200)
            assertEquals("", main { activity.editor.text.toString() })
        } finally {
            close(activity)
        }

        activity = launch()
        try {
            press("Emoji")
            press("Search emoji")
            typeQuery("wave")
            assertEquals("wave", queryText())
            val stale = checkNotNull(findNode("Emoji search letter z"))
            main { manager.hideSoftInputFromWindow(activity.editor.windowToken, 0) }
            await("IME did not hide") { findNode("Emoji") == null && findNode("Return from emoji to letters") == null }
            stale.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            Thread.sleep(200)
            assertEquals("", main { activity.editor.text.toString() })
            main { manager.showSoftInput(activity.editor, InputMethodManager.SHOW_IMPLICIT) }
            await("Typing keyboard did not return after hide") { findNode("Emoji")?.isEnabled == true }
            press("Emoji")
            press("Search emoji")
            assertEquals("Search emoji · English names", queryText())
        } finally {
            close(activity)
        }

        KeyboardOptions(terminal = true).save(app)
        activity = launch(raw = true)
        try {
            val emoji = checkNotNull(findNode("Emoji unavailable in raw input"))
            assertFalse(emoji.isEnabled)
            assertFalse(emoji.performAction(AccessibilityNodeInfo.ACTION_CLICK))
            assertEquals(android.view.KeyEvent.KEYCODE_UNKNOWN, main { activity.rawKey })
        } finally {
            close(activity)
        }

        KeyboardOptions().save(app)
        activity = launch(password = true)
        try {
            press("Emoji")
            press("Search emoji")
            assertEquals("Search emoji · English names", queryText())
            typeQuery("wave")
            press("waving hand")
            await("Explicit password-field emoji was not inserted") {
                main { activity.editor.text.toString() == "👋" }
            }
            assertEquals(EditorInfo.IME_ACTION_NONE, main { activity.action })
        } finally {
            close(activity)
        }

        activity = launch()
        try {
            press("Emoji")
            press("Search emoji")
            assertEquals("Search emoji · English names", queryText())
            assertEquals("", main { activity.editor.text.toString() })
        } finally {
            close(activity)
        }
    }

    @Test fun ownedKeyboardCapturesBrowseSearchAndVariantsAcrossThemesAndColumns() = withKeyboard {
        val captureName = InstrumentationRegistry.getArguments().getString("emojiScreenshots")
        captureName?.let { require(it.matches(Regex("[a-zA-Z0-9_-]{1,32}"))) }
        val supportsNarrowColumn = app.resources.displayMetrics.widthPixels > Ui.dp(app, 320)
        for (light in listOf(false, true)) {
            for (alignment in KeyboardAlignment.entries) {
                KeyboardOptions(light = light, alignment = alignment).save(app)
                val activity = launch()
                val width = if (alignment == KeyboardAlignment.FULL) "wide"
                    else if (supportsNarrowColumn) "narrow" else "fallback-full"
                val state = "emoji-${if (light) "light" else "dark"}-${alignment.stored}-$width"
                try {
                    press("Emoji")
                    await("Browse view did not load") { findNode("grinning face") != null }
                    val browse = captureOwnedKeyboard("$state-browse", captureName)
                    assertAlignedGeometry(state, alignment, browse)
                    press("Search emoji")
                    typeQuery("wave")
                    await("Search result did not appear") { findNode("waving hand") != null }
                    val search = captureOwnedKeyboard("$state-search", captureName)
                    assertEquals("$state search moved its horizontal column", browse, search)
                    press("Browse emoji")
                    press("Emoji categories")
                    press("Emoji category: People")
                    await("Variant family did not appear") { findNode("waving hand; choose variation") != null }
                    press("waving hand; choose variation")
                    await("Variant view did not open") { findNode("Back from emoji variants") != null }
                    val variants = captureOwnedKeyboard("$state-variants", captureName)
                    assertEquals("$state variants moved their horizontal column", browse, variants)
                } finally {
                    close(activity)
                }
            }
        }
    }

    private fun assertAlignedGeometry(state: String, alignment: KeyboardAlignment, geometry: OwnedGeometry) {
        val minimum = Ui.dp(app, 320)
        val maximum = Ui.dp(app, 360)
        val expectedWidth = if (alignment == KeyboardAlignment.FULL || geometry.surfaceWidth <= minimum) {
            geometry.surfaceWidth
        } else {
            ((geometry.surfaceWidth.toLong() * 82L) / 100L).toInt()
                .coerceIn(minimum, minOf(maximum, geometry.surfaceWidth))
        }
        assertEquals("$state content width", expectedWidth, geometry.width)
        if (alignment != KeyboardAlignment.RIGHT) assertEquals("$state left edge", 0, geometry.left)
        if (alignment == KeyboardAlignment.RIGHT) assertEquals("$state right edge", geometry.surfaceWidth, geometry.right)
    }

    private fun captureOwnedKeyboard(state: String, directoryName: String?): OwnedGeometry {
        val keyboard = main {
            android.view.inspector.WindowInspector.getGlobalWindowViews()
                .flatMap(::descendants)
                .filterIsInstance<KeyboardSurface>()
                .single { it.isShown }
        }
        val geometry = main {
            val content = keyboard.getChildAt(0) as ViewGroup
            val buttons = descendants(content).filterIsInstance<Button>().filter { it.isShown && it.isEnabled }
            val bounds = buttons.map { button ->
                Rect(0, 0, button.width, button.height).also { content.offsetDescendantRectToMyCoords(button, it) }
            }
            bounds.forEach { rect ->
                assertTrue("$state enabled button escaped its content column: $rect",
                    rect.width() > 0 && rect.height() > 0 && rect.left >= 0 && rect.right <= content.width &&
                        rect.top >= 0 && rect.bottom <= content.height)
            }
            bounds.forEachIndexed { index, rect ->
                bounds.drop(index + 1).forEach { other ->
                    assertFalse("$state enabled buttons overlap: $rect / $other", Rect.intersects(rect, other))
                }
            }
            OwnedGeometry(keyboard.width, content.left, content.right)
        }
        assertTrue("$state keyboard has no renderable size",
            keyboard.width > 0 && keyboard.height > 0 && geometry.width > 0)
        if (directoryName == null) return geometry
        val directory = File(checkNotNull(app.getExternalFilesDir(null)), directoryName)
        check(directory.isDirectory || directory.mkdirs()) { "Cannot create emoji screenshot directory" }
        val bitmap = main {
            Bitmap.createBitmap(keyboard.width, keyboard.height, Bitmap.Config.ARGB_8888).also {
                keyboard.draw(Canvas(it))
            }
        }
        try {
            FileOutputStream(File(directory, "$state-keyboard.png")).use {
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
            }
        } finally {
            bitmap.recycle()
        }
        return geometry
    }

    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is android.view.ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) }
        else emptyList()
}
