package org.utterleaf.keyboard

import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.content.pm.PermissionInfo
import android.graphics.Rect
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import android.util.Log
import android.view.InputDevice
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.view.WindowInsets
import android.view.inputmethod.InputMethodManager
import android.view.inspector.WindowInspector
import android.widget.EditText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.keyboard.MainKeyboardView
import com.android.inputmethod.keyboard.KeyboardSwitcher
import com.android.inputmethod.latin.LatinIME
import com.android.inputmethod.latin.common.Constants
import com.android.inputmethod.latin.R
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Real framework IME and touch dispatch, using only disposable synthetic input. */
@RunWith(AndroidJUnit4::class)
class FoundationImeTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext

    private fun shell(command: String) = ParcelFileDescriptor.AutoCloseInputStream(
        instrumentation.uiAutomation.executeShellCommand(command)
    ).bufferedReader().use { it.readText().trim() }

    private fun <T> main(block: () -> T): T {
        var result: Result<T>? = null
        instrumentation.runOnMainSync { result = runCatching(block) }
        return result!!.getOrThrow()
    }

    private fun await(message: String, diagnostics: (() -> String)? = null,
        condition: () -> Boolean) {
        val deadline = SystemClock.uptimeMillis() + 10_000
        while (SystemClock.uptimeMillis() < deadline) {
            instrumentation.waitForIdleSync()
            if (main(condition)) return
            // Polling interval, not a timing assumption about gesture recognition.
            SystemClock.sleep(20)
        }
        fail(message + main {
            diagnostics?.invoke() ?: run {
                val view = keyboard()
                "; keyboard=${view?.keyboard?.mId}, height=${view?.height}, bottom=" +
                    view?.rootView?.findViewById<View>(R.id.main_keyboard_frame)?.paddingBottom
            }
        })
    }

    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) }
        else emptyList()

    private fun keyboard() = WindowInspector.getGlobalWindowViews()
        .flatMap(::descendants).filterIsInstance<MainKeyboardView>()
        .singleOrNull { it.isShown && it.isLaidOut && !it.isLayoutRequested &&
            it.width > 0 && it.height > 0 && it.keyboard != null }

    private fun touch(code: Int) {
        await("Keyboard key unavailable: $code") { keyboard()?.keyboard?.getKey(code) != null }
        val point = main {
            val view = keyboard()!!
            val key = view.keyboard!!.getKey(code)!!
            val location = IntArray(2)
            view.getLocationOnScreen(location)
            val point = floatArrayOf(location[0] + view.paddingLeft + key.x + key.width / 2f,
                location[1] + view.paddingTop + key.y + key.height / 2f)
            val visible = Rect()
            val hasVisibleRect = view.getLocalVisibleRect(visible)
            visible.offset(location[0], location[1])
            val rootLocation = IntArray(2)
            view.rootView.getLocationOnScreen(rootLocation)
            val metrics = view.context.getSystemService(WindowManager::class.java).maximumWindowMetrics
            val displayBounds = metrics.bounds
            val navigation = metrics.windowInsets.getInsets(WindowInsets.Type.navigationBars())
            val safeBounds = Rect(displayBounds.left + navigation.left,
                displayBounds.top + navigation.top, displayBounds.right - navigation.right,
                displayBounds.bottom - navigation.bottom)
            // Synthetic key coordinates only; no editor text or user content is logged.
            val geometry = "code=$code point=${point.contentToString()} view=${location.contentToString()} " +
                "size=${view.width}x${view.height} padding=${view.paddingLeft},${view.paddingTop} " +
                "key=${key.x},${key.y},${key.width},${key.height} visible=$visible " +
                "root=${rootLocation.contentToString()}/${view.rootView.width}x${view.rootView.height} " +
                "display=$displayBounds navigation=$navigation safe=$safeBounds"
            Log.i("FoundationImeTouch", geometry)
            assertTrue("Synthetic key center outside visible keyboard: $geometry",
                hasVisibleRect && visible.contains(point[0].toInt(), point[1].toInt()))
            // A center obscured by navigation is a geometry failure, even if the IME draws there.
            assertTrue("Synthetic key center overlaps navigation: $geometry",
                safeBounds.contains(point[0].toInt(), point[1].toInt()))
            point
        }
        val down = SystemClock.uptimeMillis()
        for (action in listOf(MotionEvent.ACTION_DOWN, MotionEvent.ACTION_UP)) {
            val event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, point[0], point[1], 0)
            event.source = InputDevice.SOURCE_TOUCHSCREEN
            try { assertTrue(instrumentation.uiAutomation.injectInputEvent(event, true)) }
            finally { event.recycle() }
        }
        instrumentation.waitForIdleSync()
    }

    @Test fun installedCapabilitiesAreRestricted() {
        val info = app.packageManager.getPackageInfo(app.packageName,
            PackageManager.GET_PERMISSIONS or PackageManager.GET_SERVICES or PackageManager.GET_PROVIDERS or
                PackageManager.GET_RECEIVERS)
        val receiverPermission = "${app.packageName}.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION"
        assertEquals(setOf("android.permission.VIBRATE", receiverPermission), info.requestedPermissions.orEmpty().toSet())
        assertEquals(PermissionInfo.PROTECTION_SIGNATURE,
            app.packageManager.getPermissionInfo(receiverPermission, 0).protectionLevel and PermissionInfo.PROTECTION_MASK_BASE)
        assertEquals(0, info.applicationInfo!!.flags and ApplicationInfo.FLAG_ALLOW_BACKUP)
        // AndroidX installs compiled performance profiles locally; it is not a data provider.
        assertEquals(listOf("androidx.startup.InitializationProvider"), info.providers.orEmpty().map { it.name })
        assertTrue(info.providers.orEmpty().none { it.exported })
        val receiver = info.receivers.orEmpty().single()
        assertEquals("androidx.profileinstaller.ProfileInstallReceiver", receiver.name)
        assertEquals("android.permission.DUMP", receiver.permission)
        val service = info.services.orEmpty().single()
        assertEquals(UtterleafIme::class.java.name, service.name)
        assertEquals("android.permission.BIND_INPUT_METHOD", service.permission)
    }

    @Test fun realTouchTypesDeletesAndSwitchesFields() {
        val component = "${app.packageName}/${UtterleafIme::class.java.name}"
        val previous = shell("settings get secure default_input_method")
        val wasEnabled = shell("ime list -s").lineSequence().any { it == component }
        val animationScales = listOf("window_animation_scale", "transition_animation_scale", "animator_duration_scale")
            .associateWith { shell("settings get global $it") }
        var activity: FoundationActivity? = null
        val comfort = ComfortPreferences(app)
        val originalComfort = comfort.read()
        try {
            comfort.save(originalComfort.copy(heightPercent = 100, bottomSpaceDp = 0))
            // Coordinate assertions target the settled layout, not moving window surfaces.
            animationScales.keys.forEach { shell("settings put global $it 0") }
            shell("ime enable $component")
            shell("ime set $component")
            activity = instrumentation.startActivitySync(Intent(app, FoundationActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as FoundationActivity
            val screen = activity
            val fields = main { descendants(screen.findViewById(android.R.id.content)).filterIsInstance<EditText>() }
            assertEquals(2, fields.size)
            assertTrue(main { screen.window.attributes.flags and WindowManager.LayoutParams.FLAG_SECURE != 0 })
            val manager = app.getSystemService(InputMethodManager::class.java)
            fun show(field: EditText) {
                main { field.requestFocus() }
                await("Editor window was not ready for the IME") {
                    field.isAttachedToWindow && field.hasWindowFocus() && field.hasFocus()
                }
                // Establish the framework's served editor once after its window and focus settle.
                // This is fixture setup, not a retry: the following active and visible assertions
                // still require the selected IME to own and show the field.
                main { manager.restartInput(field) }
                await("Editor was not ready for the IME", diagnostics = {
                    "; attached=${field.isAttachedToWindow}, windowFocus=${field.hasWindowFocus()}, " +
                        "fieldFocus=${field.hasFocus()}, active=${manager.isActive(field)}"
                }) {
                    manager.isActive(field)
                }
                main { manager.showSoftInput(field, InputMethodManager.SHOW_IMPLICIT) }
                // A laid-out keyboard can precede its input surface becoming visible.
                // Do not inject the first key while the framework is still showing it.
                await("IME did not appear") {
                    keyboard() != null && manager.isActive(field) &&
                        screen.window.decorView.rootWindowInsets?.isVisible(WindowInsets.Type.ime()) == true
                }
            }
            show(fields[0])
            // Inspect the actual framework-created service without a production test hook.
            val ime = main {
                val owner = KeyboardSwitcher::class.java.getDeclaredField("mLatinIME")
                owner.isAccessible = true
                owner.get(KeyboardSwitcher.getInstance()) as LatinIME
            }
            var firstSession = ime.mEditorSession.capture()
            assertTrue(ime.mEditorSession.isCurrent(firstSession))
            assertFalse("An unintegrated voice engine must not have a shortcut key",
                main { keyboard()!!.keyboard!!.mId.mHasShortcutKey })
            touch('a'.code)
            touch('b'.code)
            touch(' '.code)
            try {
                await("Literal input did not reach the editor") { fields[0].text.toString() == "ab " }
            } catch (failure: AssertionError) {
                throw AssertionError("Synthetic fixture result: " + main {
                    "text=[${fields[0].text}], inputType=${fields[0].inputType}, keyboard=${keyboard()?.keyboard?.mId}"
                }, failure)
            }
            touch(Constants.CODE_DELETE)
            await("Delete did not remove the space") { fields[0].text.toString() == "ab" }
            touch('q'.code)
            await("Top row did not reach editor") { fields[0].text.toString() == "abq" }
            touch(Constants.CODE_DELETE)
            await("Delete did not remove top-row input") { fields[0].text.toString() == "ab" }
            main {
                val view = keyboard()!!
                val strip = view.rootView.findViewById<View>(R.id.suggestion_strip_view)
                val topView = if (strip?.isShown == true) strip else view
                val location = IntArray(2)
                topView.getLocationInWindow(location)
                val reported = android.inputmethodservice.InputMethodService.Insets()
                ime.onComputeInsets(reported)
                assertEquals("Reported content excludes visible top row", location[1], reported.contentTopInsets)
                assertEquals("Reported visible region excludes top row", location[1], reported.visibleTopInsets)
                val key = view.keyboard!!.getKey('q'.code)!!
                view.getLocationInWindow(location)
                assertTrue("Top-row center is outside reported touchable region", reported.touchableRegion.contains(
                    location[0] + view.paddingLeft + key.x + key.width / 2,
                    location[1] + view.paddingTop + key.y + key.height / 2))
            }
            val logic = main {
                LatinIME::class.java.getDeclaredField("mInputLogic").apply { isAccessible = true }
                    .get(ime) as com.android.inputmethod.latin.inputlogic.InputLogic
            }
            val beforeCursorMove = main { ime.mEditorSession.capture() }
            assertNotNull(beforeCursorMove)
            main { fields[0].setSelection(1) }
            await("IME did not observe the moved cursor") { logic.mConnection.expectedSelectionStart == 1 }
            main {
                assertFalse("Cursor movement left old decoder work valid",
                    ime.mEditorSession.isCurrent(beforeCursorMove))
            }
            touch('x'.code)
            await("Typing after cursor retirement lost the editor position") { fields[0].text.toString() == "axb" }
            touch(Constants.CODE_DELETE)
            await("Delete after cursor retirement failed") { fields[0].text.toString() == "ab" }
            main {
                val beforeSubtype = ime.mEditorSession.capture()
                assertNotNull(beforeSubtype)
                ime.onCurrentInputMethodSubtypeChanged(
                    com.android.inputmethod.latin.RichInputMethodManager.getInstance().currentSubtype.rawSubtype)
                assertFalse("Subtype left the previous decoder identity valid", ime.mEditorSession.isCurrent(beforeSubtype))
                assertEquals(1, logic.mConnection.expectedSelectionStart)
                assertEquals('a'.code, logic.mConnection.codePointBeforeCursor)
            }
            touch('x'.code)
            await("Typing after subtype reset lost the current cursor") { fields[0].text.toString() == "axb" }
            touch(Constants.CODE_DELETE)
            await("Delete after subtype reset failed") { fields[0].text.toString() == "ab" }
            main {
                // Deterministic reproduction of the deferred equivalent-editor callback path
                // in the real service. This does not simulate physical device rotation.
                val parcel = android.os.Parcel.obtain()
                val restartInfo = try {
                    ime.currentInputEditorInfo.writeToParcel(parcel, 0)
                    parcel.setDataPosition(0)
                    android.view.inputmethod.EditorInfo.CREATOR.createFromParcel(parcel)
                } finally { parcel.recycle() }
                restartInfo.initialSelStart = fields[0].selectionStart
                restartInfo.initialSelEnd = fields[0].selectionEnd
                val handlerClass = LatinIME.UIHandler::class.java
                val pending = handlerClass.getDeclaredField("MSG_PENDING_IMS_CALLBACK")
                    .apply { isAccessible = true }.getInt(null)
                handlerClass.getDeclaredField("mAppliedEditorInfo").apply { isAccessible = true }
                    .set(ime.mHandler, restartInfo)
                ime.mHandler.sendEmptyMessageDelayed(pending, 60_000)
                try {
                    ime.onFinishInput()
                    assertTrue(logic.isInputStateRetired)
                    assertEquals(Constants.NOT_A_CODE, logic.mConnection.codePointBeforeCursor)
                    ime.onStartInput(restartInfo, true)
                    ime.onStartInputView(restartInfo, true)
                    assertFalse("Equivalent-editor coalescing skipped retired state setup", logic.isInputStateRetired)
                    assertEquals(restartInfo.initialSelStart, logic.mConnection.expectedSelectionStart)
                    assertEquals('a'.code, logic.mConnection.codePointBeforeCursor)
                } finally { ime.mHandler.removeMessages(pending) }
            }
            touch('x'.code)
            await("Typing after deferred retirement recovery failed") { fields[0].text.toString() == "axb" }
            touch(Constants.CODE_DELETE)
            await("Delete after deferred retirement recovery failed") { fields[0].text.toString() == "ab" }
            firstSession = ime.mEditorSession.capture()
            show(fields[1])
            // isActive/visible may precede the service receiving its start-input callback.
            await("Field switch did not invalidate the prior IME session") {
                !ime.mEditorSession.isCurrent(firstSession) && ime.mEditorSession.capture() != null
            }
            val secondSession = ime.mEditorSession.capture()
            touch('c'.code)
            touch(' '.code)
            await("Field switch did not redirect input") {
                fields[0].text.toString() == "ab" && fields[1].text.toString() == "c "
            }
            main {
                fields[1].setText("")
                fields[1].inputType = android.text.InputType.TYPE_CLASS_TEXT or
                    android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
                manager.restartInput(fields[1])
            }
            await("Password layout did not become active") { keyboard()?.keyboard?.mId?.passwordInput() == true }
            assertFalse(ime.mEditorSession.isCurrent(secondSession))
            touch('d'.code)
            touch(Constants.CODE_DELETE)
            touch('e'.code)
            await("Privacy protection broke literal password editing") { fields[1].text.toString() == "e" }
            val viewBeforeDeallocation = main { keyboard()!! }
            val beforeHide = ime.mEditorSession.capture()
            main { manager.hideSoftInputFromWindow(fields[1].windowToken, 0) }
            await("Hide did not invalidate pending editor work") {
                !ime.mEditorSession.isCurrent(beforeHide) &&
                    screen.window.decorView.rootWindowInsets?.isVisible(WindowInsets.Type.ime()) == false
            }
            main {
                LatinIME::class.java.getDeclaredMethod("deallocateMemory").apply {
                    isAccessible = true
                }.invoke(ime)
            }
            show(fields[1])
            await("Keyboard did not reuse its deallocated view") {
                keyboard() === viewBeforeDeallocation &&
                    ime.mEditorSession.isCurrent(ime.mEditorSession.capture())
            }
            touch('r'.code)
            await("Typing failed after owner-valid deallocation") { fields[1].text.toString() == "er" }
            touch(Constants.CODE_DELETE)
            await("Delete failed after owner-valid deallocation") { fields[1].text.toString() == "e" }
            val originalView = main { keyboard()!! }
            val originalHeight = main { originalView.height }
            comfort.save(originalComfort.copy(heightPercent = 125, bottomSpaceDp = 24))
            main { manager.restartInput(fields[1]) }
            val bottomPixels = (24 * app.resources.displayMetrics.density).toInt()
            await("Comfort settings did not reach the live keyboard") {
                val view = keyboard()
                view != null && view === originalView && view.height > originalHeight &&
                    view.rootView.findViewById<View>(R.id.main_keyboard_frame)?.paddingBottom == bottomPixels
            }
            comfort.reset()
            main { manager.restartInput(fields[1]) }
            await("Reset did not restore live keyboard geometry") {
                val view = keyboard()
                view != null && view.height == originalHeight &&
                    view.rootView.findViewById<View>(R.id.main_keyboard_frame)?.paddingBottom == 0
            }
            assertEquals("e", main { fields[1].text.toString() })
            val beforeTheme = main { keyboard()!! }
            comfort.save(ComfortOptions(lightTheme = true))
            main { manager.restartInput(fields[1]) }
            await("Theme did not replace the live keyboard view") {
                keyboard()?.let { it !== beforeTheme } == true
            }
            touch('f'.code)
            await("Typing stopped after comfort changes") { fields[1].text.toString() == "ef" }
            touch(Constants.CODE_DELETE)
            await("Delete stopped after comfort changes") { fields[1].text.toString() == "e" }
            captureSyntheticUi(screen, "keyboard-foundation")
        } finally {
            comfort.save(originalComfort)
            activity?.let { main { it.finish() } }
            if (previous != "null" && previous.isNotBlank()) shell("ime set $previous")
            if (!wasEnabled) shell("ime disable $component")
            animationScales.forEach { (key, value) ->
                shell(if (value == "null") "settings delete global $key" else "settings put global $key $value")
            }
        }
    }
}
