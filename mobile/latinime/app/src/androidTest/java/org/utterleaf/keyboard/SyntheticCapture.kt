package org.utterleaf.keyboard

import android.app.Activity
import android.content.Context
import android.content.pm.ApplicationInfo
import android.os.ParcelFileDescriptor
import android.view.View
import android.view.WindowManager
import android.view.inspector.WindowInspector
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.R
import org.junit.Assert.assertTrue

/** Optional synthetic-emulator evidence only. No capture override is packaged in the app. */
internal fun captureSyntheticUi(activity: Activity, name: String) {
    if (InstrumentationRegistry.getArguments().getString("captureScreenshots") != "true") return
    require(name.matches(Regex("[a-z-]+")))
    val instrumentation = InstrumentationRegistry.getInstrumentation()
    assertTrue(instrumentation.targetContext.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0)
    val restored = mutableListOf<Pair<View, Int>>()
    try {
        instrumentation.runOnMainSync {
            assertTrue(activity.window.decorView.isShown)
            assertTrue(activity.window.attributes.flags and WindowManager.LayoutParams.FLAG_SECURE != 0)
            activity.window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
            val roots = WindowInspector.getGlobalWindowViews().filter {
                it.isShown && it.findViewById<View>(R.id.keyboard_view) != null
            }
            for (root in roots) {
                val params = root.layoutParams as WindowManager.LayoutParams
                assertTrue(params.flags and WindowManager.LayoutParams.FLAG_SECURE != 0)
                restored += root to params.flags
                params.flags = params.flags and WindowManager.LayoutParams.FLAG_SECURE.inv()
                (root.context.getSystemService(Context.WINDOW_SERVICE) as WindowManager).updateViewLayout(root, params)
            }
        }
        instrumentation.uiAutomation.waitForIdle(100, 5_000)
        ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand(
            "screencap -p /data/local/tmp/utterleaf-$name.png"
        )).use { it.readBytes() }
    } finally {
        instrumentation.runOnMainSync {
            activity.window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
            for ((root, flags) in restored) {
                val params = root.layoutParams as WindowManager.LayoutParams
                params.flags = flags
                (root.context.getSystemService(Context.WINDOW_SERVICE) as WindowManager).updateViewLayout(root, params)
            }
        }
    }
}
