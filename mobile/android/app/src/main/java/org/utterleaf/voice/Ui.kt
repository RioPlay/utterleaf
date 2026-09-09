package org.utterleaf.voice

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.view.View
import android.widget.*

object Ui {
    val ink = Color.rgb(229, 238, 232)
    val green = Color.rgb(131, 218, 154)
    fun dp(context: Context, n: Int) = (n * context.resources.displayMetrics.density).toInt()
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
