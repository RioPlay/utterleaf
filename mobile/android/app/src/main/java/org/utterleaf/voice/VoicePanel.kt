package org.utterleaf.voice

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.text.Editable
import android.text.InputFilter
import android.text.InputType
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.inputmethod.BaseInputConnection
import android.widget.*

class VoicePanel(private val context: Context, private val insert: (String) -> Boolean, private val leave: () -> Unit,
    private val createSession: ((CaptureStatus) -> Unit, (String) -> Unit, (String) -> Unit) -> CaptureSession =
        { state, result, error -> VoiceSession(context.applicationContext, state, result, error) }) {
    private enum class Mode { IDLE, CAPTURE, PROCESSING, REVIEW, EDIT }
    val view = Ui.column(context)
    private val handler = Handler(Looper.getMainLooper())
    private val gate = TakeGate()
    private var mode = Mode.IDLE
    private var session: CaptureSession? = null
    private var autoInsert = false
    private var released = false
    private var disposed = false
    private var editingGeneration = 0
    private var holdPointer = -1
    private var pendingHold: Runnable? = null
    private var activeHold = false
    private var inhibitUntil = 0L
    private var rearm: Runnable? = null
    private var micEntryUsed = false
    private var transcriptExpanded = false
    private val stateIcon = ImageView(context).apply {
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        scaleType = ImageView.ScaleType.FIT_CENTER
    }
    private val status = Ui.text(context, "Microphone off · English · local processing")
    private val preview = EditText(context).apply {
        hint = "Your transcript"
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        filters = arrayOf(InputFilter.LengthFilter(16000))
        isSaveEnabled = false; showSoftInputOnFocus = false
        isVerticalScrollBarEnabled = true
        importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
        setTextColor(Ui.ink); setHintTextColor(Ui.ink)
        gravity = android.view.Gravity.TOP
    }
    private val transcriptKeyListener = preview.keyListener
    // This connection dispatches only to our own transcript, never to the host app.
    private val localEditor = object : BaseInputConnection(preview, true) {
        override fun getEditable(): Editable = preview.text
        override fun sendKeyEvent(event: KeyEvent): Boolean = when (event.action) {
            KeyEvent.ACTION_DOWN -> preview.onKeyDown(event.keyCode, event)
            KeyEvent.ACTION_UP -> preview.onKeyUp(event.keyCode, event)
            else -> false
        }
    }
    private val editingKeys = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
    private val primary = Ui.button(context, "Speak") {
        if (!disposed && android.os.SystemClock.uptimeMillis() >= inhibitUntil) when (mode) {
            Mode.IDLE -> begin(false)
            Mode.CAPTURE -> stopCapture()
            Mode.REVIEW -> insertReview()
            Mode.EDIT -> { editingGeneration++; editingKeys.removeAllViews(); mode = Mode.REVIEW; updateControls() }
            Mode.PROCESSING -> Unit
        }
    }
    private val edit = Ui.button(context, "Edit transcript") { beginEditing() }
    private val transcriptSize = Ui.button(context, "Expand transcript") {
        if (!disposed && (mode == Mode.REVIEW || mode == Mode.EDIT)) {
            transcriptExpanded = !transcriptExpanded
            updateControls()
        }
    }
    private val modelChoice = Ui.button(context, "Speech model") { chooseModel() }
    private val modelOptions = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
    private val keep = Ui.button(context, "Keep reviewing") { if (mode == Mode.REVIEW || mode == Mode.EDIT) scheduleExpiry() }
    private val holdMode = CheckBox(context).apply {
        text = "Hold to speak and insert on release"; setTextColor(Ui.ink); minHeight = Ui.dp(context, 48)
        isChecked = context.getSharedPreferences("keyboard", Context.MODE_PRIVATE).getBoolean("voiceHoldToInsert", false)
        setOnCheckedChangeListener { _, value ->
            context.getSharedPreferences("keyboard", Context.MODE_PRIVATE).edit().putBoolean("voiceHoldToInsert", value).apply()
            updateControls()
        }
    }
    private val warning = Runnable {
        if (mode == Mode.REVIEW || mode == Mode.EDIT) {
            status.text = "Preview clears in 30 seconds. Tap Keep reviewing for more time."
            keep.visibility = View.VISIBLE
            status.announceForAccessibility(status.text)
        }
    }
    private val expire = Runnable { clear(); status.text = "Preview expired · microphone off" }

    init {
        val heading = LinearLayout(context).apply { gravity = android.view.Gravity.CENTER_VERTICAL }
        heading.addView(stateIcon, LinearLayout.LayoutParams(Ui.dp(context, 32), Ui.dp(context, 32)).apply {
            marginEnd = Ui.dp(context, 8)
        })
        heading.addView(Ui.text(context, "Utterleaf Voice", 20f))
        view.addView(heading); view.addView(status); view.addView(modelChoice); view.addView(modelOptions)
        view.addView(preview, LinearLayout.LayoutParams(-1, Ui.dp(context, 96)))
        val reviewActions = LinearLayout(context)
        reviewActions.addView(transcriptSize, LinearLayout.LayoutParams(0, -2, 1f))
        reviewActions.addView(edit, LinearLayout.LayoutParams(0, -2, 1f))
        view.addView(reviewActions)
        view.addView(editingKeys); view.addView(keep)
        // Keep the primary action the same distance above the bottom of the panel.
        view.addView(primary, LinearLayout.LayoutParams(-1, Ui.dp(context, 56)))
        view.addView(holdMode)
        val secondary = LinearLayout(context)
        secondary.addView(Ui.button(context, "Discard") { clear(); status.text = "Discarded · microphone off" }, LinearLayout.LayoutParams(0, -2, 1f))
        secondary.addView(Ui.button(context, "Back to keyboard") { clear(); leave() }, LinearLayout.LayoutParams(0, -2, 1f))
        view.addView(secondary)
        primary.setOnTouchListener { _, event -> handleHold(event) }
        view.addOnAttachStateChangeListener(object : View.OnAttachStateChangeListener {
            override fun onViewAttachedToWindow(v: View) = Unit
            override fun onViewDetachedFromWindow(v: View) { disposed = true; clear() }
        })
        updateControls()
    }
    private fun cancelHold() {
        pendingHold?.let { primary.removeCallbacks(it) }; pendingHold = null
        holdPointer = -1; activeHold = false; primary.isPressed = false
    }
    private fun handleHold(event: MotionEvent): Boolean {
        if (disposed || android.os.SystemClock.uptimeMillis() < inhibitUntil) return true
        if (holdPointer < 0 && !(holdMode.isChecked && mode == Mode.IDLE)) return false
        if (event.actionMasked == MotionEvent.ACTION_DOWN) {
            cancelHold()
            if (event.pointerCount != 1 || !inside(event)) return true
            holdPointer = event.getPointerId(0); primary.isPressed = true
            val task = Runnable {
                pendingHold = null
                if (holdPointer >= 0 && primary.isAttachedToWindow && mode == Mode.IDLE && !disposed) {
                    activeHold = true; begin(true)
                }
            }
            pendingHold = task; primary.postDelayed(task, ViewConfiguration.getLongPressTimeout().toLong())
            return true
        }
        if (event.pointerCount != 1 || holdPointer < 0 || event.getPointerId(0) != holdPointer || !inside(event) ||
            event.actionMasked == MotionEvent.ACTION_CANCEL || event.actionMasked == MotionEvent.ACTION_POINTER_DOWN) {
            val abort = activeHold; cancelHold(); if (abort) clear(); return true
        }
        if (event.actionMasked == MotionEvent.ACTION_UP) {
            val finishedHold = activeHold; cancelHold()
            if (finishedHold) {
                released = true
                if (mode == Mode.CAPTURE) stopCapture() else if (mode == Mode.REVIEW) insertReview()
            }
        }
        return true
    }
    private fun inside(event: MotionEvent) = event.x.isFinite() && event.y.isFinite() &&
        event.x >= 0 && event.x < primary.width && event.y >= 0 && event.y < primary.height

    /** Called only by an explicit keyboard mic action, never by an IME lifecycle callback. */
    fun startFromMicTap() {
        if (disposed || micEntryUsed || mode != Mode.IDLE) return
        micEntryUsed = true
        // A tap opens a review take, even if the separate hold control is enabled.
        begin(false)
    }

    private fun begin(automatic: Boolean) {
        if (disposed || mode != Mode.IDLE) return
        val token = gate.next()
        autoInsert = automatic; released = false; mode = Mode.CAPTURE; updateControls()
        val candidate = createSession(
            { update -> if (gate.accepts(token) && (mode == Mode.CAPTURE || mode == Mode.PROCESSING)) {
                // Capture can end at its limit without a Stop tap. Never infer phase from UI copy.
                if (update.phase == CapturePhase.PROCESSING) {
                    mode = Mode.PROCESSING; updateControls(); status.text = update.message
                } else if (mode == Mode.CAPTURE) status.text = update.message
            } },
            { text -> if (gate.accepts(token) && (mode == Mode.CAPTURE || mode == Mode.PROCESSING)) {
                session = null
                if (text.length > 16000 || text.isBlank()) {
                    cancelHold(); mode = Mode.IDLE; autoInsert = false
                    status.text = "No usable transcript. Try a shorter take."; updateControls()
                } else {
                    preview.setText(text); preview.setSelection(preview.length()); transcriptExpanded = false
                    mode = Mode.REVIEW; updateControls(); scheduleExpiry()
                    if (autoInsert && released) insertReview()
                }
            } },
            { message -> if (gate.accepts(token)) {
                cancelHold(); autoInsert = false; session = null; mode = Mode.IDLE
                status.text = message; updateControls()
            } })
        if (gate.accepts(token) && mode == Mode.CAPTURE) { session = candidate; candidate.start() }
        else candidate.cancel()
    }
    private fun stopCapture() {
        if (mode != Mode.CAPTURE) return
        mode = Mode.PROCESSING; updateControls(); session?.stop()
    }
    private fun insertReview() {
        if (disposed || mode != Mode.REVIEW) return
        val text = preview.text.toString()
        if (text.isBlank()) { status.text = "The transcript is empty. Edit it or discard this take."; return }
        autoInsert = false // A rejected automatic insertion requires an explicit retry.
        if (insert(text)) {
            clear(); status.text = "Inserted · microphone off"
            inhibitUntil = android.os.SystemClock.uptimeMillis() + 400
            val token = gate.next()
            rearm = Runnable { if (gate.accepts(token) && !disposed) updateControls() }.also { handler.postDelayed(it, 400) }
            updateControls()
        } else { status.text = "Could not insert into this field. Edit, retry, or discard this preview."; updateControls() }
    }
    private fun beginEditing() {
        if (disposed || mode != Mode.REVIEW) return
        autoInsert = false; cancelHold(); transcriptExpanded = false; mode = Mode.EDIT; scheduleExpiry()
        val token = ++editingGeneration
        fun current() = !disposed && mode == Mode.EDIT && editingGeneration == token
        val panel = TypingPanel(context, KeyboardOptions.load(context),
            { text -> current() && TerminalInput.printable(localEditor, text) },
            { if (current()) TerminalInput.send(localEditor, KeyEvent.KEYCODE_DEL) },
            { if (current()) TerminalInput.printable(localEditor, "\n") },
            { left -> if (current()) TerminalInput.send(localEditor, if (left) KeyEvent.KEYCODE_DPAD_LEFT else KeyEvent.KEYCODE_DPAD_RIGHT) },
            {}, {}, {},
            { code, ctrl, alt, shift -> current() &&
                if (shift && !ctrl && !alt && code in listOf(KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT,
                        KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_MOVE_HOME, KeyEvent.KEYCODE_MOVE_END))
                    TerminalInput.select(localEditor, code) else TerminalInput.send(localEditor, code, ctrl, alt, shift) },
            { text, ctrl, alt -> current() && TerminalInput.printable(localEditor, text, ctrl, alt) })
        panel.reset(false, false, "Enter"); editingKeys.addView(panel.view)
        updateControls(); preview.requestFocus()
    }
    private fun updateControls() {
        val models = ModelStore.available(context.noBackupFilesDir)
        modelChoice.visibility = if (mode == Mode.IDLE && models.size > 1) View.VISIBLE else View.GONE
        modelChoice.isEnabled = mode == Mode.IDLE && !disposed
        if (mode != Mode.IDLE) modelOptions.removeAllViews()
        modelChoice.text = "Model · ${ModelStore.installed(context.noBackupFilesDir)?.id ?: "choose"}"
        stateIcon.setImageResource(when (mode) {
            Mode.CAPTURE -> R.drawable.voice_recording
            Mode.PROCESSING -> R.drawable.voice_busy
            else -> R.drawable.voice_idle
        })
        primary.text = when (mode) { Mode.IDLE -> if (holdMode.isChecked) "Hold to speak" else "Speak"; Mode.CAPTURE -> "Stop"; Mode.PROCESSING -> "Transcribing…"; Mode.REVIEW -> "Insert"; Mode.EDIT -> "Use edits" }
        primary.contentDescription = primary.text
        primary.isEnabled = !disposed && mode != Mode.PROCESSING && android.os.SystemClock.uptimeMillis() >= inhibitUntil
        preview.visibility = if (mode == Mode.REVIEW || mode == Mode.EDIT) View.VISIBLE else View.GONE
        // Read-only review must still allow scrolling and selection.
        preview.keyListener = if (mode == Mode.EDIT) transcriptKeyListener else null
        preview.setTextIsSelectable(true)
        preview.isCursorVisible = mode == Mode.EDIT
        transcriptSize.visibility = if (mode == Mode.REVIEW || mode == Mode.EDIT) View.VISIBLE else View.GONE
        transcriptSize.text = if (transcriptExpanded) "Collapse transcript" else "Expand transcript"
        (preview.layoutParams as? LinearLayout.LayoutParams)?.let { params ->
            val expandedHeight = (context.resources.configuration.screenHeightDp / 3).coerceIn(96, 220)
            val height = Ui.dp(context, if (transcriptExpanded) expandedHeight else 96)
            if (params.height != height) { params.height = height; preview.layoutParams = params }
        }
        edit.visibility = if (mode == Mode.REVIEW && !activeHold) View.VISIBLE else View.GONE
        if (mode != Mode.REVIEW && mode != Mode.EDIT) keep.visibility = View.GONE
        holdMode.visibility = if (mode == Mode.IDLE && !disposed) View.VISIBLE else View.GONE
        holdMode.isEnabled = mode == Mode.IDLE && !disposed
    }
    private fun scheduleExpiry() {
        handler.removeCallbacks(warning); handler.removeCallbacks(expire)
        keep.visibility = View.GONE
        status.text = "Microphone off · preview clears in 2 minutes"
        handler.postDelayed(warning, 90000); handler.postDelayed(expire, 120000)
    }
    private fun chooseModel() {
        if (disposed || mode != Mode.IDLE) return
        val models = ModelStore.available(context.noBackupFilesDir)
        val selected = ModelStore.installed(context.noBackupFilesDir)
        val token = gate.next()
        if (modelOptions.childCount > 0) { modelOptions.removeAllViews(); return }
        models.forEach { spec ->
                val profile = when (spec.id) { "tiny.en" -> "Fast"; "base.en" -> "Balanced"; else -> "Larger · more memory and time" }
                modelOptions.addView(Ui.button(context, "$profile · ${spec.id}") {
                if (!disposed && mode == Mode.IDLE && gate.accepts(token)) {
                    if (WorkLease.acquire()) {
                        try { status.text = if (ModelStore.select(context.noBackupFilesDir, spec))
                            "${spec.id} selected · microphone off" else "Model unavailable. Open setup to import it." }
                        catch (_: Exception) { status.text = "Could not switch models. Try again in setup." }
                        finally { WorkLease.release() }
                        updateControls()
                    } else status.text = "Wait for the current take or import to finish."
                    gate.invalidate()
                    modelOptions.removeAllViews()
                }
            }.apply { isSelected = spec == selected })
        }
    }
    fun clear() {
        modelOptions.removeAllViews()
        rearm?.let { handler.removeCallbacks(it) }; rearm = null; inhibitUntil = 0
        gate.invalidate(); cancelHold(); autoInsert = false; released = false
        session?.cancel(); session = null; editingGeneration++; editingKeys.removeAllViews()
        preview.setText(""); transcriptExpanded = false; mode = Mode.IDLE
        handler.removeCallbacks(warning); handler.removeCallbacks(expire)
        status.text = "Microphone off · English · local processing"; updateControls()
    }
}
