package org.utterleaf.keyboard

import android.os.ParcelFileDescriptor
import android.os.Process
import android.os.SystemClock
import android.util.AtomicFile
import android.view.View
import android.view.ViewGroup
import android.view.inspector.WindowInspector
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.filters.SdkSuppress
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.keyboard.KeyboardSwitcher
import com.android.inputmethod.keyboard.MainKeyboardView
import com.android.inputmethod.latin.LatinIME
import com.android.inputmethod.latin.common.Constants
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** External-controller-only calibration. Expected to terminate by SIGKILL, never pass alone. */
@RunWith(AndroidJUnit4::class)
@SdkSuppress(minSdkVersion = 30)
class ImeProcessRecoveryProbeTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()

    private fun <T> main(block: () -> T): T {
        var result: Result<T>? = null
        instrumentation.runOnMainSync { result = runCatching(block) }
        return result!!.getOrThrow()
    }

    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) }
        else emptyList()

    private fun keyboard(): MainKeyboardView? = WindowInspector.getGlobalWindowViews()
        .flatMap(::descendants).filterIsInstance<MainKeyboardView>()
        .singleOrNull { it.isShown && it.isLaidOut && !it.isLayoutRequested &&
            it.width > 0 && it.height > 0 && it.keyboard != null }

    private fun write(file: File, value: JSONObject) {
        val atomic = AtomicFile(file)
        val output = atomic.startWrite()
        try {
            output.write(value.toString().toByteArray(Charsets.UTF_8))
            atomic.finishWrite(output)
        } catch (failure: Throwable) {
            atomic.failWrite(output)
            throw failure
        }
    }

    @Test fun prepareActualImeForExternalDeath() {
        val token = InstrumentationRegistry.getArguments().getString("recoveryToken")
        assumeTrue("Requires external emulator PID-killing controller", token != null)
        require(token!!.matches(Regex("[a-f0-9]{32}")))
        val emulator = ParcelFileDescriptor.AutoCloseInputStream(
            instrumentation.uiAutomation.executeShellCommand("getprop ro.kernel.qemu")
        ).bufferedReader().use { it.readText().trim() }
        assertEquals("The recovery probe only supports an emulator", "1", emulator)
        val app = instrumentation.targetContext
        assertEquals("org.utterleaf.keyboard.experimental", app.packageName)
        val directory = File(app.noBackupFilesDir, "ime-recovery-$token")
        check(directory.mkdir()) { "A recovery fixture must use a fresh token" }
        write(File(directory, "waiting.json"), JSONObject().put("ime_pid", Process.myPid())
            .put("token", token).put("uptime_ms", SystemClock.uptimeMillis()))
        val deadline = SystemClock.uptimeMillis() + 90_000
        var ready: JSONObject? = null
        while (ready == null && SystemClock.uptimeMillis() < deadline) {
            instrumentation.waitForIdleSync()
            ready = main {
                val view = keyboard() ?: return@main null
                val owner = KeyboardSwitcher::class.java.getDeclaredField("mLatinIME")
                    .apply { isAccessible = true }.get(KeyboardSwitcher.getInstance()) as? LatinIME
                if (owner?.currentInputEditorInfo?.packageName !=
                    "org.utterleaf.keyboard.recoveryhost") return@main null
                val location = IntArray(2)
                view.getLocationOnScreen(location)
                val keys = JSONObject()
                for ((name, code) in listOf("a" to 'a'.code, "b" to 'b'.code,
                    "space" to ' '.code, "delete" to Constants.CODE_DELETE)) {
                    val key = view.keyboard!!.getKey(code) ?: return@main null
                    keys.put(name, JSONObject()
                        .put("x", location[0] + view.paddingLeft + key.x + key.width / 2)
                        .put("y", location[1] + view.paddingTop + key.y + key.height / 2))
                }
                JSONObject().put("ime_pid", Process.myPid()).put("token", token)
                    .put("keys", keys).put("uptime_ms", SystemClock.uptimeMillis())
                    .put("keyboard", JSONObject().put("x", location[0]).put("y", location[1])
                        .put("width", view.width).put("height", view.height))
            }
            if (ready == null) SystemClock.sleep(50)
        }
        val calibration = checkNotNull(ready) {
            "Actual IME did not attach to the separate synthetic host"
        }
        write(File(directory, "ready.json"), calibration)
        // The controller observes readiness, proves baseline touch input, then kills this PID.
        // Restarting instrumentation afterward would interfere with framework service recovery.
        SystemClock.sleep(90_000)
        fail("External controller did not kill the prepared IME process")
    }
}
