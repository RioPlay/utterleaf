package org.utterleaf.voice

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.os.Build
import android.view.View
import android.view.WindowInsets
import android.widget.*

object Ui {
    val ink = Color.rgb(229, 238, 232)
    val green = Color.rgb(131, 218, 154)
    fun dp(context: Context, n: Int) = (n * context.resources.displayMetrics.density).toInt()
    /** Call once on a new app content root, never the window decor. Owns its subtree's insets. */
    @Suppress("DEPRECATION")
    fun applySystemInsets(view: View, navigationOnly: Boolean = false) {
        val left = view.paddingLeft; val top = view.paddingTop
        val right = view.paddingRight; val bottom = view.paddingBottom
        view.setOnApplyWindowInsetsListener { target, insets ->
            if (Build.VERSION.SDK_INT >= 30) {
                val types = (if (navigationOnly) WindowInsets.Type.navigationBars() else WindowInsets.Type.systemBars()) or
                    WindowInsets.Type.displayCutout()
                val safe = insets.getInsets(types)
                target.setPadding(left + safe.left, top + if (navigationOnly) 0 else safe.top,
                    right + safe.right, bottom + safe.bottom)
                // These simple native-view subtrees do not need another inset consumer.
                WindowInsets.CONSUMED
            } else {
                var safeLeft = insets.systemWindowInsetLeft
                var safeTop = insets.systemWindowInsetTop
                var safeRight = insets.systemWindowInsetRight
                var safeBottom = insets.systemWindowInsetBottom
                if (Build.VERSION.SDK_INT >= 28) {
                    // Keep all DisplayCutout API calls inside the SDK guard.
                    // A nullable cutout does not establish API availability for lint.
                    val cutout = insets.displayCutout
                    if (cutout != null) {
                        safeLeft = maxOf(safeLeft, cutout.safeInsetLeft)
                        safeTop = maxOf(safeTop, cutout.safeInsetTop)
                        safeRight = maxOf(safeRight, cutout.safeInsetRight)
                        safeBottom = maxOf(safeBottom, cutout.safeInsetBottom)
                    }
                }
                target.setPadding(left + safeLeft, top + if (navigationOnly) 0 else safeTop,
                    right + safeRight, bottom + safeBottom)
                val consumed = insets.consumeSystemWindowInsets().consumeStableInsets()
                if (Build.VERSION.SDK_INT >= 28) consumed.consumeDisplayCutout() else consumed
            }
        }
        if (view.isAttachedToWindow) view.requestApplyInsets()
        else view.addOnAttachStateChangeListener(object : View.OnAttachStateChangeListener {
            override fun onViewAttachedToWindow(attached: View) {
                attached.removeOnAttachStateChangeListener(this)
                attached.requestApplyInsets()
            }
            override fun onViewDetachedFromWindow(detached: View) = Unit
        })
    }
    fun column(context: Context) = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setBackgroundColor(Color.rgb(23, 30, 32))
        val p = dp(context, 18); setPadding(p, p, p, p)
    }
    fun text(context: Context, value: String, size: Float = 16f) = TextView(context).apply {
        text = value; textSize = size; setTextColor(ink)
        setPadding(0, dp(context, 6), 0, dp(context, 6))
    }
    fun title(context: Context, value: String) = text(context, value, 24f).apply { setTypeface(typeface, Typeface.BOLD) }
    fun button(context: Context, label: String, action: () -> Unit) = Button(context).apply {
        text = label; isAllCaps = false; minHeight = dp(context, 48)
        backgroundTintList = ColorStateList(
            arrayOf(intArrayOf(android.R.attr.state_pressed), intArrayOf(android.R.attr.state_focused), intArrayOf()),
            intArrayOf(Color.rgb(53, 92, 69), Color.rgb(53, 92, 69), Color.rgb(40, 51, 53)))
        setTextColor(ColorStateList(arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
            intArrayOf(Color.rgb(113, 137, 123), green)))
        setOnClickListener { action() }
    }
    fun mascot(context: Context) = ImageView(context).apply {
        setImageResource(org.utterleaf.voice.R.drawable.utterling_default)
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        layoutParams = LinearLayout.LayoutParams(dp(context, 72), dp(context, 72))
    }
}
