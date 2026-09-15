package org.utterleaf.voice

import android.os.Handler
import android.os.Looper
import android.view.View

/**
 * Repeats an action while a key stays held: the tap click fires once, a
 * long-press starts the bounded repeat loop until the view detaches or
 * [cancel] is called. Long-press is consumed only while repeating is armed.
 */
internal class ArrowRepeater(
    private val view: View,
    private val action: () -> Unit) : View.OnAttachStateChangeListener {
    private val handler = Handler(Looper.getMainLooper())
    private var running = false
    private val step = object : Runnable {
        override fun run() {
            action()
            handler.postDelayed(this, PERIOD_MS)
        }
    }

    init {
        view.setOnLongClickListener {
            if (running) return@setOnLongClickListener true
            running = true
            action()
            handler.postDelayed(step, PERIOD_MS)
            true
        }
        view.addOnAttachStateChangeListener(this)
    }

    fun cancel() {
        handler.removeCallbacksAndMessages(null)
        running = false
    }

    override fun onViewAttachedToWindow(v: View) = Unit
    override fun onViewDetachedFromWindow(v: View) = cancel()

    companion object {
        private const val PERIOD_MS = 55L
    }
}
