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
    data class Palette(val background: Int, val key: Int, val utility: Int, val ink: Int,
        val muted: Int, val accent: Int, val accentInk: Int)
    object KeyboardTokens {
        const val keyRadiusDp = 8
        const val brandedPillRadiusDp = 23
        const val secondaryHintSp = 9f
        const val bottomModeWidthDp = 58
        const val bottomPunctuationWidthDp = 48
        const val bottomActionWidthDp = 64
    }
    fun palette(context: Context, options: KeyboardOptions = KeyboardOptions.load(context)): Palette {
        val mode = when (options.theme) {
            ThemeMode.SYSTEM -> if (options.resolvedLight(context)) ThemeMode.LIGHT else ThemeMode.DARK
            else -> options.theme
        }
        return when (mode) {
            ThemeMode.LIGHT -> Palette(Color.rgb(232, 238, 235), Color.WHITE,
                Color.rgb(209, 223, 214), Color.rgb(23, 37, 29), Color.rgb(72, 96, 82),
                Color.rgb(37, 100, 61), Color.WHITE)
            ThemeMode.OLED -> Palette(Color.BLACK, Color.rgb(16, 20, 18),
                Color.rgb(7, 16, 11), Color.rgb(243, 248, 245), Color.rgb(170, 186, 175),
                Color.rgb(162, 223, 179), Color.rgb(8, 23, 14))
            else -> Palette(Color.rgb(23, 30, 32), Color.rgb(48, 58, 61),
                Color.rgb(36, 50, 45), Color.rgb(240, 245, 242), Color.rgb(178, 197, 185),
                Color.rgb(162, 223, 179), Color.rgb(16, 41, 27))
        }
    }
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
    fun column(context: Context, options: KeyboardOptions = KeyboardOptions.load(context)) = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setBackgroundColor(palette(context, options).background)
        val p = dp(context, 18); setPadding(p, p, p, p)
    }
    fun text(context: Context, value: String, size: Float = 16f,
        options: KeyboardOptions = KeyboardOptions.load(context)) = TextView(context).apply {
        text = value; textSize = size; setTextColor(palette(context, options).ink)
        setPadding(0, dp(context, 6), 0, dp(context, 6))
    }
    fun title(context: Context, value: String, options: KeyboardOptions = KeyboardOptions.load(context)) =
        text(context, value, 24f, options).apply { setTypeface(typeface, Typeface.BOLD) }
    fun button(context: Context, label: String, options: KeyboardOptions = KeyboardOptions.load(context),
        action: () -> Unit) = Button(context).apply {
        val colors = palette(context, options)
        text = label; isAllCaps = false; minHeight = dp(context, 48)
        backgroundTintList = ColorStateList(
            arrayOf(intArrayOf(android.R.attr.state_pressed), intArrayOf(android.R.attr.state_focused), intArrayOf()),
            intArrayOf(colors.accent, colors.accent, colors.utility))
        setTextColor(ColorStateList(arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
            intArrayOf(colors.muted, colors.ink)))
        setOnClickListener { action() }
    }
    fun mascot(context: Context) = ImageView(context).apply {
        setImageResource(org.utterleaf.voice.R.drawable.utterling_default)
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        layoutParams = LinearLayout.LayoutParams(dp(context, 72), dp(context, 72))
    }
}
