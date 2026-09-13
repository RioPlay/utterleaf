package org.utterleaf.voice

import android.annotation.SuppressLint
import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.os.Build
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView

/** UNAVAILABLE means no host call; UNCONFIRMED means a call may have changed the host. */
enum class DraftInsertionResult { INSERTED, UNAVAILABLE, UNCONFIRMED }

/** Temporary, clipboard-free editing. The owner supplies the only route to the host. */
class PrivateDraftPanel(
    private val context: Context,
    private val options: KeyboardOptions,
    private val insert: (String) -> DraftInsertionResult,
    private val exit: () -> Unit,
) {
    private val surface = Color.parseColor(if (options.light) "#E8EEEB" else "#171E20")
    private val paper = Color.parseColor(if (options.light) "#FFFFFF" else "#303A3D")
    private val ink = Color.parseColor(if (options.light) "#17251D" else "#F0F5F2")
    private val muted = Color.parseColor(if (options.light) "#486052" else "#B2C5B9")
    private val accent = Color.parseColor(if (options.light) "#25643D" else "#A2DFB3")
    private val accentInk = Color.parseColor(if (options.light) "#FFFFFF" else "#10291B")
    private var disposed = false
    private var inserting = false
    private var unconfirmed = false
    private var ready = false

    val view = FrameLayout(context).apply {
        tag = "private-draft-panel"
        setBackgroundColor(surface)
        isSaveEnabled = false
        isSaveFromParentEnabled = false
    }
    private val column = object : LinearLayout(context) {
        override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
            val available = View.MeasureSpec.getSize(widthMeasureSpec)
            val mode = View.MeasureSpec.getMode(widthMeasureSpec)
            val minimum = Ui.dp(context, 320)
            val width = if (mode == View.MeasureSpec.UNSPECIFIED ||
                options.alignment == KeyboardAlignment.FULL || available <= minimum) available
            else ((available.toLong() * 82L) / 100L).toInt()
                .coerceIn(minimum, minOf(Ui.dp(context, 360), available))
            super.onMeasure(if (mode == View.MeasureSpec.UNSPECIFIED) widthMeasureSpec
                else View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY), heightMeasureSpec)
        }
    }.apply {
        tag = "private-draft-column"
        orientation = LinearLayout.VERTICAL
        layoutDirection = View.LAYOUT_DIRECTION_LTR
        setPadding(0, Ui.dp(context, 6), 0, Ui.dp(context, options.bottomPaddingDp.coerceIn(0, 80)))
    }
    private val editor = PrivateDraftEditor(context) { if (ready && !disposed) refresh() }
    private val status = TextView(context).apply {
        tag = "private-draft-status"
        textSize = if (options.large) 15f else 13f
        setTextColor(muted)
        accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        visibility = View.GONE
    }
    private val insertButton = button("Insert", "Insert private draft", primary = true) { insertDraft() }
    private val clearButton = button("Clear", "Clear private draft") {
        if (!inserting) {
            unconfirmed = false
            status.visibility = View.GONE
            editor.clearDraft()
        }
    }
    private val discardButton = button("Discard", "Discard private draft") {
        if (!inserting) { clear(); exit() }
    }
    private val retryButton = button("Enable another insert", "Enable another insert") {
        if (!inserting && unconfirmed) {
            unconfirmed = false
            status.text = "Ready for one more attempt. Insert only if the text is missing."
            refresh()
        }
    }.apply { visibility = View.GONE }
    private val typing = TypingPanel(context,
        options.copy(alignment = KeyboardAlignment.FULL, bottomPaddingDp = 0),
        commit = { text -> edit { editor.replace(text) } },
        erase = { edit { editor.erase() }; Unit },
        enter = { edit { editor.replace("\n") }; Unit },
        move = { left -> edit { editor.navigate(if (left) KeyEvent.KEYCODE_DPAD_LEFT else KeyEvent.KEYCODE_DPAD_RIGHT) }; Unit },
        dictate = {}, settings = {}, switchKeyboard = {},
        terminalKey = { code, ctrl, alt, select ->
            !ctrl && !alt && edit { editor.navigate(code, select) }
        },
        editorAction = { action -> edit { editor.action(action) } },
        privateEditing = true,
        actionAvailable = { action -> !disposed && !inserting && when (action) {
            EditorAction.UNDO -> editor.canUndo
            EditorAction.REDO -> editor.canRedo
            EditorAction.SELECT_ALL -> editor.current.text.isNotEmpty()
            else -> false
        } },
    )

    init {
        val header = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(Ui.dp(context, 10), 0, Ui.dp(context, 10), Ui.dp(context, 6))
            addView(TextView(context).apply {
                text = "Private draft"
                textSize = if (options.large) 22f else 20f
                setTextColor(ink)
                setTypeface(typeface, Typeface.BOLD)
                if (Build.VERSION.SDK_INT >= 28) isAccessibilityHeading = true
            })
            addView(TextView(context).apply {
                text = "Stays here until Insert. Clears when the keyboard closes or the field changes."
                textSize = if (options.large) 15f else 13f
                setTextColor(muted)
            })
        }
        column.addView(header)
        editor.view.apply {
            tag = "private-draft-text"
            hint = "Write a private draft"
            textSize = if (options.large) 22f else 18f
            setTextColor(ink)
            setHintTextColor(muted)
            gravity = Gravity.TOP or Gravity.START
            setPadding(Ui.dp(context, 12), Ui.dp(context, 8), Ui.dp(context, 12), Ui.dp(context, 8))
            background = shape(paper)
        }
        column.addView(editor.view, LinearLayout.LayoutParams(-1, Ui.dp(context, if (options.large) 112 else 96)).apply {
            setMargins(Ui.dp(context, 6), 0, Ui.dp(context, 6), Ui.dp(context, 4))
        })
        column.addView(LinearLayout(context).apply {
            setPadding(Ui.dp(context, 3), 0, Ui.dp(context, 3), 0)
            listOf(insertButton, clearButton, discardButton).forEach { control ->
                addView(control, LinearLayout.LayoutParams(0, -2, 1f).apply {
                    setMargins(Ui.dp(context, 3), 0, Ui.dp(context, 3), 0)
                })
            }
        })
        column.addView(status, LinearLayout.LayoutParams(-1, -2).apply {
            setMargins(Ui.dp(context, 10), Ui.dp(context, 4), Ui.dp(context, 10), 0)
        })
        column.addView(retryButton, LinearLayout.LayoutParams(-1, -2).apply {
            setMargins(Ui.dp(context, 6), Ui.dp(context, 4), Ui.dp(context, 6), 0)
        })
        typing.reset(allowVoice = false, numeric = false, action = "Enter")
        column.addView(typing.view, LinearLayout.LayoutParams(-1, -2).apply { topMargin = Ui.dp(context, 4) })
        view.addView(column, FrameLayout.LayoutParams(-2, -2, columnGravity()))
        view.addOnAttachStateChangeListener(object : View.OnAttachStateChangeListener {
            override fun onViewAttachedToWindow(v: View) = Unit
            override fun onViewDetachedFromWindow(v: View) = clear()
        })
        ready = true
        refresh()
    }

    @SuppressLint("RtlHardcoded") // Explicit physical one-hand preference.
    private fun columnGravity() = Gravity.TOP or
        if (options.alignment == KeyboardAlignment.RIGHT) Gravity.RIGHT else Gravity.LEFT

    private fun edit(operation: () -> Boolean): Boolean {
        if (disposed || inserting) return false
        val accepted = operation()
        if (!accepted) {
            status.text = "That edit is unavailable. If the draft is full, remove some text to keep writing."
            status.visibility = View.VISIBLE
        }
        return accepted
    }

    private fun insertDraft() {
        if (disposed || inserting || unconfirmed) return
        val text = editor.current.text
        if (text.isEmpty()) return
        inserting = true
        refresh()
        val result = try { insert(text) } catch (_: Exception) { DraftInsertionResult.UNCONFIRMED }
        // A host call can trigger a field change synchronously.
        if (disposed) return
        inserting = false
        when (result) {
            DraftInsertionResult.INSERTED -> { clear(); exit(); return }
            DraftInsertionResult.UNAVAILABLE -> status.text = "Insertion is unavailable. Your draft stays here."
            DraftInsertionResult.UNCONFIRMED -> {
                unconfirmed = true
                status.text = "The app did not confirm insertion. Check the field before another attempt."
            }
        }
        status.visibility = View.VISIBLE
        refresh()
    }

    private fun refresh() {
        val hasText = !disposed && editor.current.text.isNotEmpty()
        insertButton.isEnabled = hasText && !inserting && !unconfirmed
        clearButton.isEnabled = hasText && !inserting
        discardButton.isEnabled = !disposed && !inserting
        retryButton.visibility = if (!disposed && unconfirmed) View.VISIBLE else View.GONE
        retryButton.isEnabled = !disposed && !inserting && unconfirmed
        typing.refreshEditorActions()
    }

    /** Drops owned text/history and invalidates callbacks even if never attached. */
    fun clear() {
        if (disposed) return
        disposed = true
        editor.dispose()
        typing.dispose()
        status.text = ""
        status.visibility = View.GONE
        refresh()
        column.removeAllViews()
    }

    private fun shape(color: Int) = GradientDrawable().apply {
        setColor(color)
        cornerRadius = Ui.dp(context, 12).toFloat()
    }

    private fun button(label: String, description: String, primary: Boolean = false, action: () -> Unit) =
        Button(context).apply {
            text = label
            contentDescription = description
            isAllCaps = false
            textSize = if (options.large) 18f else 16f
            minWidth = 0
            minimumWidth = 0
            minHeight = Ui.dp(context, if (options.large) 56 else 48)
            minimumHeight = minHeight
            setPadding(Ui.dp(context, 5), Ui.dp(context, 4), Ui.dp(context, 5), Ui.dp(context, 4))
            background = RippleDrawable(ColorStateList.valueOf(if (options.light) 0x22000000 else 0x33FFFFFF),
                shape(if (primary) accent else paper), null)
            setTextColor(ColorStateList(arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
                intArrayOf(if (primary) accentInk and 0x00FFFFFF or 0x66000000 else muted,
                    if (primary) accentInk else ink)))
            setOnClickListener { if (!disposed && isEnabled) action() }
        }
}
