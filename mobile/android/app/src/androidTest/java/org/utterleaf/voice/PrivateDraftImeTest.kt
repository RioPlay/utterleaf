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
import android.text.InputType
import android.text.Selection
import android.view.View
import android.view.ViewGroup
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.view.inputmethod.InputMethodSubtype
import android.widget.Button
import android.widget.EditText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.atomic.AtomicReference
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PrivateDraftImeTest {
    private data class OwnedGeometry(val panelWidth: Int, val left: Int, val right: Int) {
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

    private fun descendants(view: View): List<View> = listOf(view) + if (view is ViewGroup)
        (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()

    private fun draftPanelOnMain(): View =
        android.view.inspector.WindowInspector.getGlobalWindowViews()
            .flatMap(::descendants)
            .single { it.tag == "private-draft-panel" && it.isShown }

    private fun currentDraftPanel(): View = main(::draftPanelOnMain)

    private fun draftEditor(panel: View): EditText = descendants(panel).filterIsInstance<EditText>()
            .single { it.tag == "private-draft-text" }

    private fun currentDraftEditor(): EditText = currentDraftPanel().let { panel -> main { draftEditor(panel) } }

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
        main {
            manager.restartInput(activity.editor)
            manager.showSoftInput(activity.editor, InputMethodManager.SHOW_IMPLICIT)
        }
        await("Typing keyboard did not appear") {
            findNode(if (raw) "Emoji unavailable in raw input" else "Keyboard tools") != null
        }
        return activity
    }

    private fun close(activity: KeyboardEditorContractActivity) {
        main { activity.finish() }
        await("Previous IME session did not close") {
            findNode("Keyboard tools") == null && findNode("Insert private draft") == null
        }
    }

    private fun openDraft() {
        press("Keyboard tools")
        press("Private draft")
        await("Private draft panel did not appear") { findNode("Insert private draft") != null }
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

    @Test fun exactUtf16SelectionReplacementOccursOnceWithoutSubmitOrClipboard() = withKeyboard {
        val clipboard = app.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val sentinel = "synthetic private-IME clipboard"
        clipboard.setPrimaryClip(ClipData.newPlainText("private-ime-test", sentinel))
        var opened: KeyboardEditorContractActivity? = null
        try {
            val activity = launch()
            opened = activity
            val original = "before SELECT after"
            val start = original.indexOf("SELECT")
            val end = start + "SELECT".length
            main {
                activity.editor.setText(original)
                Selection.setSelection(activity.editor.text, end, start)
            }
            openDraft()
            press("a")
            press("b")
            press("Emoji")
            press("grinning face")
            press("Return from emoji to letters")
            press("Enter")
            press("c")
            press("d")
            val draft = "ab😀\ncd"
            val staleInsert = checkNotNull(findNode("Insert private draft"))
            val draftEditor = currentDraftEditor()
            main {
                assertEquals(draft, draftEditor.text.toString())
                assertEquals(original, activity.editor.text.toString())
                assertEquals(start, minOf(activity.editor.selectionStart, activity.editor.selectionEnd))
                assertEquals(end, maxOf(activity.editor.selectionStart, activity.editor.selectionEnd))
                assertEquals(EditorInfo.IME_ACTION_NONE, activity.action)
            }
            assertEquals(sentinel, clipboard.primaryClip?.getItemAt(0)?.text?.toString())
            press("Insert private draft")
            await("Final draft did not replace the current selection exactly once") {
                main { activity.editor.text.toString() == "before $draft after" }
            }
            staleInsert.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            Thread.sleep(200)
            main {
                assertEquals("before $draft after", activity.editor.text.toString())
                assertEquals(EditorInfo.IME_ACTION_NONE, activity.action)
            }
            assertEquals(sentinel, clipboard.primaryClip?.getItemAt(0)?.text?.toString())
        } finally {
            clipboard.clearPrimaryClip()
            opened?.let(::close)
        }
    }

    @Test fun fieldSubtypeAndHideClearDraftAndMakeOldButtonsHarmless() = withKeyboard { manager ->
        fun assertCleared(triggerName: String, trigger: (KeyboardIme, KeyboardEditorContractActivity) -> Unit) {
            val activity = launch()
            try {
                main { activity.editor.setText("host-$triggerName") }
                openDraft()
                val panel = currentDraftPanel()
                val draft = currentDraftEditor()
                val staleInsert = checkNotNull(findNode("Insert private draft"))
                val staleLetter = checkNotNull(findNode("x"))
                staleLetter.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                await("$triggerName draft did not accept its local key") { main { draft.text.toString() == "x" } }
                val service = panel.context as KeyboardIme
                main { trigger(service, activity) }
                await("$triggerName did not detach the private draft") { !main { panel.isAttachedToWindow } }
                main { assertEquals("", draft.text.toString()) }
                staleLetter.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                staleInsert.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                Thread.sleep(100)
                main { assertEquals("host-$triggerName", activity.editor.text.toString()) }
            } finally {
                close(activity)
            }
        }

        assertCleared("field") { service, _ ->
            service.onStartInput(EditorInfo().apply { inputType = InputType.TYPE_CLASS_TEXT }, false)
        }
        assertCleared("subtype") { service, _ ->
            KeyboardIme::class.java.getDeclaredMethod(
                "onCurrentInputMethodSubtypeChanged",
                InputMethodSubtype::class.java,
            ).apply { isAccessible = true }.invoke(
                service,
                InputMethodSubtype.InputMethodSubtypeBuilder().build(),
            )
        }
        assertCleared("hide") { _, activity -> manager.hideSoftInputFromWindow(activity.editor.windowToken, 0) }
    }

    @Test fun finishAndWindowCallbacksClearOnceAndRemainIdempotent() = withKeyboard {
        val activity = launch()
        try {
            main { activity.editor.setText("host-finish") }
            openDraft()
            val panel = currentDraftPanel()
            val draft = currentDraftEditor()
            val staleInsert = checkNotNull(findNode("Insert private draft"))
            press("x")
            await("Finish draft did not accept its local key") { main { draft.text.toString() == "x" } }
            val service = panel.context as KeyboardIme
            main {
                service.onFinishInput()
                service.onFinishInputView(false)
                service.onWindowHidden()
            }
            await("Finish callbacks did not detach the private draft") { !main { panel.isAttachedToWindow } }
            main { assertEquals("", draft.text.toString()) }
            staleInsert.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            Thread.sleep(100)
            main { assertEquals("host-finish", activity.editor.text.toString()) }
        } finally {
            close(activity)
        }
    }

    @Test fun rawAndPasswordFieldsCannotEnterDraftAndOrdinaryReopeningStartsEmpty() = withKeyboard {
        KeyboardOptions(terminal = true).save(app)
        await("Terminal preference was not stored for raw input") { KeyboardOptions.load(app).terminal }
        var activity = launch(raw = true)
        try {
            press("Keyboard tools")
            assertEquals(null, findNode("Private draft"))
            assertEquals(android.view.KeyEvent.KEYCODE_UNKNOWN, main { activity.rawKey })
        } finally {
            close(activity)
        }

        KeyboardOptions().save(app)
        activity = launch(password = true)
        try {
            press("Keyboard tools")
            assertEquals(null, findNode("Private draft"))
            assertEquals("", main { activity.editor.text.toString() })
        } finally {
            close(activity)
        }

        activity = launch()
        try {
            main { activity.editor.setText("host text must not be imported") }
            openDraft()
            val firstDraft = currentDraftEditor()
            main { assertEquals("", firstDraft.text.toString()) }
            press("x")
            press("Discard private draft")
            openDraft()
            val reopenedDraft = currentDraftEditor()
            main {
                assertEquals("", reopenedDraft.text.toString())
                assertEquals("host text must not be imported", activity.editor.text.toString())
            }
        } finally {
            close(activity)
        }
    }

    @Test fun ownedLargeDraftViewCoversBothThemesAndEveryAlignment() = withKeyboard {
        val captureName = InstrumentationRegistry.getArguments().getString("draftScreenshots")
        captureName?.let { require(it.matches(Regex("[a-zA-Z0-9_-]{1,32}"))) }
        for (light in listOf(false, true)) for (alignment in KeyboardAlignment.entries) {
            KeyboardOptions(large = true, light = light, alignment = alignment).save(app)
            val activity = launch()
            val state = "draft-${if (light) "light" else "dark"}-${alignment.stored}"
            try {
                openDraft()
                press("x")
                val geometry = captureOwnedDraft(state, captureName)
                val minimum = Ui.dp(app, 320)
                val expected = if (alignment == KeyboardAlignment.FULL || geometry.panelWidth <= minimum) {
                    geometry.panelWidth
                } else {
                    ((geometry.panelWidth.toLong() * 82L) / 100L).toInt()
                        .coerceIn(minimum, minOf(Ui.dp(app, 360), geometry.panelWidth))
                }
                assertEquals("$state width", expected, geometry.width)
                if (alignment != KeyboardAlignment.RIGHT) assertEquals("$state left", 0, geometry.left)
                if (alignment == KeyboardAlignment.RIGHT) assertEquals("$state right", geometry.panelWidth, geometry.right)
            } finally {
                close(activity)
            }
        }
    }

    private fun captureOwnedDraft(state: String, directoryName: String?): OwnedGeometry {
        val panel = currentDraftPanel()
        val geometry = main {
            val column = descendants(panel).filterIsInstance<ViewGroup>()
                .single { it.tag == "private-draft-column" }
            assertEquals("$state panel horizontal scroll", 0, panel.scrollX)
            assertEquals("$state panel vertical scroll", 0, panel.scrollY)
            val controls = descendants(column).filterIsInstance<Button>().filter { it.isShown && it.isEnabled }
            controls.forEach { button ->
                val bounds = Rect(0, 0, button.width, button.height)
                column.offsetDescendantRectToMyCoords(button, bounds)
                assertTrue("$state enabled button escaped its column: $bounds",
                    bounds.width() > 0 && bounds.height() > 0 && bounds.left >= 0 &&
                        bounds.right <= column.width && bounds.top >= 0 && bounds.bottom <= column.height)
            }
            OwnedGeometry(panel.width, column.left, column.right)
        }
        assertTrue("$state panel has no renderable size", panel.width > 0 && panel.height > 0 && geometry.width > 0)
        if (directoryName == null) return geometry
        val directory = File(checkNotNull(app.getExternalFilesDir(null)), directoryName)
        check(directory.isDirectory || directory.mkdirs()) { "Cannot create private-draft screenshot directory" }
        val bitmap = main {
            Bitmap.createBitmap(panel.width, panel.height, Bitmap.Config.ARGB_8888).also { panel.draw(Canvas(it)) }
        }
        try {
            FileOutputStream(File(directory, "$state-panel.png")).use {
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
            }
        } finally {
            bitmap.recycle()
        }
        return geometry
    }
}
