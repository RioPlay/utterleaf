package org.utterleaf.keyboard.next

import android.app.Activity
import android.os.Bundle
import android.text.InputType
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.LinearLayout
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsAnimationCompat

/** Disposable debug-only host; production has no practice/history buffer yet. */
class CoreTestActivity : Activity() {
    private val imeAnimations = mutableSetOf<WindowInsetsAnimationCompat>()
    val imeAnimating: Boolean get() = imeAnimations.isNotEmpty()
    lateinit var first: EditText
    lateinit var second: EditText
    lateinit var password: EditText
    lateinit var privateField: EditText
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        val column = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20, 80, 20, 0) }
        fun field(hint: String, type: Int, options: Int = EditorInfo.IME_ACTION_NONE): EditText = EditText(this).also {
            it.id = android.view.View.generateViewId()
            it.hint = hint; it.inputType = type; it.imeOptions = options
            it.isSaveEnabled = false; column.addView(it)
        }
        first = field("Synthetic first", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE)
        second = field("Synthetic second", InputType.TYPE_CLASS_TEXT)
        password = field("Synthetic password", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD)
        privateField = field("Synthetic private", InputType.TYPE_CLASS_TEXT, EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING)
        setContentView(column)
        ViewCompat.setOnApplyWindowInsetsListener(column) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            view.setPadding(20 + bars.left, 20 + bars.top, 20 + bars.right, bars.bottom)
            insets
        }
        ViewCompat.setWindowInsetsAnimationCallback(column, object : WindowInsetsAnimationCompat.Callback(DISPATCH_MODE_CONTINUE_ON_SUBTREE) {
            override fun onPrepare(animation: WindowInsetsAnimationCompat) {
                if (animation.typeMask and WindowInsetsCompat.Type.ime() != 0) imeAnimations += animation
            }
            override fun onProgress(insets: WindowInsetsCompat, runningAnimations: MutableList<WindowInsetsAnimationCompat>) = insets
            override fun onEnd(animation: WindowInsetsAnimationCompat) { imeAnimations -= animation }
        })
    }
    override fun onStop() {
        listOf(first, second, password, privateField).forEach { it.text.clear() }
        super.onStop()
    }
}
