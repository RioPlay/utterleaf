package org.utterleaf.voice

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.widget.*

class VoicePanel(context: Context, private val insert: (String) -> Boolean, private val leave: () -> Unit) {
    val view = Ui.column(context)
    private val handler = Handler(Looper.getMainLooper())
    private val gate = TakeGate()
    private var session: VoiceSession? = null
    private var transcript = ""
    private val status = Ui.text(context, "Microphone off · English · local processing")
    private val preview = Ui.text(context, "Tap Speak when you are ready.")
    private val speak = Ui.button(context, "Speak") { begin() }
    private val stop = Ui.button(context, "Stop") { session?.stop() }
    private val send = Ui.button(context, "Insert") {
        if (transcript.isNotBlank()) {
            if (insert(transcript)) { clear(); status.text = "Inserted · microphone off" }
            else status.text = "Could not insert into this field. Text stays here until you discard or leave."
        }
    }
    private val expire = Runnable { clear(); status.text = "Preview expired · microphone off" }
    init {
        view.addView(Ui.text(context, "Utterleaf Voice", 20f))
        view.addView(status)
        view.addView(ScrollView(context).apply { addView(preview) },
            LinearLayout.LayoutParams(-1, Ui.dp(context, 72)))
        val actions = LinearLayout(context)
        listOf(speak, stop, send).forEach { actions.addView(it, LinearLayout.LayoutParams(0, -2, 1f)) }
        view.addView(actions)
        val secondary = LinearLayout(context)
        secondary.addView(Ui.button(context, "Discard") { clear(); status.text = "Discarded · microphone off" }, LinearLayout.LayoutParams(0, -2, 1f))
        secondary.addView(Ui.button(context, "Back to keyboard") { clear(); leave() }, LinearLayout.LayoutParams(0, -2, 1f))
        view.addView(secondary)
        stop.isEnabled = false; send.isEnabled = false
    }
    private fun begin() {
        clear()
        val token = gate.next()
        speak.isEnabled = false; stop.isEnabled = true
        session = VoiceSession(view.context.applicationContext,
            { if (gate.accepts(token)) status.text = it },
            { if (gate.accepts(token)) {
                transcript = it; preview.text = it
                status.text = "Microphone off · preview expires in 2 minutes"
                stop.isEnabled = false; speak.isEnabled = true; send.isEnabled = true
                handler.postDelayed(expire, 120000)
            } },
            { if (gate.accepts(token)) { status.text = it; stop.isEnabled = false; speak.isEnabled = true } })
        session!!.start()
    }
    fun clear() {
        gate.invalidate(); session?.cancel(); session = null
        transcript = ""; preview.text = "Tap Speak when you are ready."
        handler.removeCallbacks(expire)
        speak.isEnabled = true; stop.isEnabled = false; send.isEnabled = false
    }
}
