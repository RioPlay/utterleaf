package org.utterleaf.keyboard.recoveryhost

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.Process
import android.os.SystemClock
import android.text.InputType
import android.util.AtomicFile
import android.view.MotionEvent
import android.view.WindowInsets
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONObject
import java.io.File
import java.util.UUID

/** Disposable, separate-process synthetic editor; never part of the keyboard APK. */
class RecoveryHostActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private val instance = UUID.randomUUID().toString()
    private lateinit var field: EditText
    private lateinit var status: AtomicFile
    private var generation = 0L
    private var initialShowRequested = false
    private val report = object : Runnable {
        override fun run() {
            publish()
            handler.postDelayed(this, 100)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val token = intent.getStringExtra("probeToken")
        if (token == null || !token.matches(Regex("[a-f0-9]{32}"))) {
            finish()
            return
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        val directory = File(noBackupFilesDir, "ime-recovery-$token")
        check(directory.mkdir()) { "A recovery fixture must use a fresh token" }
        status = AtomicFile(File(directory, "state.json"))
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val padding = (24 * resources.displayMetrics.density).toInt()
            setPadding(padding, padding * 3, padding, padding)
        }
        layout.addView(TextView(this).apply { text = "Disposable synthetic IME recovery editor" })
        field = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            imeOptions = EditorInfo.IME_FLAG_NO_EXTRACT_UI or EditorInfo.IME_FLAG_FORCE_ASCII
            isSaveEnabled = false
            importantForAutofill = android.view.View.IMPORTANT_FOR_AUTOFILL_NO
            setSingleLine(true)
            hint = "Synthetic input only"
            setOnTouchListener { _, event ->
                if (event.actionMasked == MotionEvent.ACTION_UP) {
                    post { showKeyboard() }
                }
                false // Let EditText perform its normal focus, selection and click handling.
            }
        }
        layout.addView(field, LinearLayout.LayoutParams(-1, -2))
        setContentView(layout)
        field.requestFocus()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus && ::field.isInitialized && !initialShowRequested) {
            initialShowRequested = true
            field.post { showKeyboard() }
        }
    }

    private fun showKeyboard() {
        field.requestFocus()
        getSystemService(InputMethodManager::class.java)
            .showSoftInput(field, InputMethodManager.SHOW_IMPLICIT)
    }

    override fun onResume() {
        super.onResume()
        if (::status.isInitialized) handler.post(report)
    }

    override fun onPause() {
        handler.removeCallbacks(report)
        super.onPause()
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    private fun publish() {
        if (!field.isLaidOut) return
        val location = IntArray(2)
        field.getLocationOnScreen(location)
        val root = window.decorView
        val insets = root.rootWindowInsets
        val value = JSONObject()
            .put("host_pid", Process.myPid()).put("instance", instance)
            .put("text", field.text.toString())
            .put("selection_start", field.selectionStart).put("selection_end", field.selectionEnd)
            .put("ime_visible", insets?.isVisible(WindowInsets.Type.ime()) == true)
            .put("ime_bottom", insets?.getInsets(WindowInsets.Type.ime())?.bottom ?: 0)
            .put("field_center", JSONObject().put("x", location[0] + field.width / 2)
                .put("y", location[1] + field.height / 2))
            .put("window_width", root.width).put("window_height", root.height)
            .put("generation", ++generation).put("uptime_ms", SystemClock.uptimeMillis())
        val stream = status.startWrite()
        try {
            stream.write(value.toString().toByteArray(Charsets.UTF_8))
            status.finishWrite(stream)
        } catch (failure: Throwable) {
            status.failWrite(stream)
            throw failure
        }
    }
}
