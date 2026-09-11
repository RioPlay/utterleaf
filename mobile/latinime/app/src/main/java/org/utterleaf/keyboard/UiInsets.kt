package org.utterleaf.keyboard

import android.view.View
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

/** Apply once to a settings scroll root; child controls do not consume insets again. */
internal fun View.applyContentInsets(padding: Int) {
    // A parent may consume insets; retain comfortable spacing even without dispatch.
    setPadding(padding, padding, padding, padding)
    ViewCompat.setOnApplyWindowInsetsListener(this) { view, insets ->
        val safe = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
        val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
        view.setPadding(padding + safe.left, padding + safe.top, padding + safe.right, padding + maxOf(safe.bottom, ime.bottom))
        insets
    }
}
