package org.utterleaf.keyboard

import android.content.ComponentName
import android.content.Intent
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.view.accessibility.AccessibilityNodeInfo
import android.view.inspector.WindowInspector
import android.widget.Button
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.security.MessageDigest

@RunWith(AndroidJUnit4::class)
class PackagedNoticesTest {
    @Test fun allCatalogDocumentsArePackagedWithMatchingHashesAndUpstreamNotices() {
        val assets = InstrumentationRegistry.getInstrumentation().targetContext.assets
        val documents = NoticeDocuments.read(assets)
        assertTrue(documents.size >= 13)
        assertEquals(documents.size, documents.map { it.file }.toSet().size)
        assertEquals(documents.map { it.file }.toSet() + "catalog.json", assets.list("notices")!!.toSet())
        for (document in documents) {
            val bytes = assets.open("notices/${document.file}").use { it.readBytes() }
            assertTrue(document.file, bytes.isNotEmpty())
            val hash = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
            assertEquals(document.file, document.sha256, hash)
        }
        val notice = assets.open("notices/AOSP-NOTICE.txt").bufferedReader().use { it.readText() }
        val javaNotice = assets.open("notices/AOSP-JAVA-NOTICE.txt").bufferedReader().use { it.readText() }
        assertEquals(notice, javaNotice)
        assertTrue(notice.contains("Lexiteria"))
        val modifications = assets.open("notices/UTTERLEAF-NOTICE.md").bufferedReader().use { it.readText() }
        assertTrue(modifications.contains("127336e9f29d69607eab55982324b210279ae8c5"))
    }

    @Test fun localNoticeViewerIsInternalAndSecureAndOpensBundledText() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        @Suppress("DEPRECATION")
        val info = context.packageManager.getActivityInfo(ComponentName(context, NoticesActivity::class.java), 0)
        assertFalse(info.exported)
        val activity = instrumentation.startActivitySync(Intent(context, NoticesActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as NoticesActivity
        try {
            val decor = activity.window.decorView
            fun readReady(): Boolean {
                var ready = false
                instrumentation.runOnMainSync {
                    ready = decor.isAttachedToWindow && decor.isLaidOut && decor.isShown &&
                        activity.hasWindowFocus()
                }
                return ready
            }
            val readinessDeadline = SystemClock.uptimeMillis() + 5_000L
            while (SystemClock.uptimeMillis() < readinessDeadline && !readReady()) {
                instrumentation.waitForIdleSync()
                SystemClock.sleep(100L)
            }
            var roots = ""
            var omittedRoots = 0
            var ready = false
            instrumentation.runOnMainSync {
                ready = decor.isAttachedToWindow && decor.isLaidOut && decor.isShown &&
                    activity.hasWindowFocus()
                val allRoots = WindowInspector.getGlobalWindowViews()
                val shownRoots = allRoots.take(8)
                omittedRoots = allRoots.size - shownRoots.size
                roots = shownRoots.joinToString { root ->
                    "${root.context.packageName}/${root.javaClass.name}#${root.windowId} " +
                        "attached=${root.isAttachedToWindow},laidOut=${root.isLaidOut},shown=${root.isShown}," +
                        "focused=${root.hasWindowFocus()}"
                }
            }
            assertTrue(
                "Notice activity window not ready: ready=$ready, root=$roots, " +
                    "omittedRoots=$omittedRoots",
                ready)
            instrumentation.runOnMainSync {
                assertTrue(activity.window.attributes.flags and WindowManager.LayoutParams.FLAG_SECURE != 0)
                val buttons = descendants(activity.window.decorView).filterIsInstance<Button>()
                val documents = NoticeDocuments.read(activity.assets)
                assertEquals(documents.size, buttons.size)
                val aosp = buttons.single { it.text == "AOSP LatinIME notice" }
                assertTrue(aosp.performClick())
            }
            instrumentation.waitForIdleSync()
            val device = instrumentation.uiAutomation
            var root = device.rootInActiveWindow
            var matches = emptyList<AccessibilityNodeInfo>()
            val textDeadline = SystemClock.uptimeMillis() + 5_000L
            while (SystemClock.uptimeMillis() < textDeadline && matches.isEmpty()) {
                root?.recycle()
                root = device.rootInActiveWindow
                matches = root?.findAccessibilityNodeInfosByText("Lexiteria").orEmpty()
                if (matches.isEmpty()) android.os.SystemClock.sleep(100L)
            }
            try {
                assertNotNull(root)
                assertTrue("The dialog exposes the bundled notice text", matches.isNotEmpty())
                @Suppress("DEPRECATION")
                matches.forEach { it.recycle() }
            } finally {
                @Suppress("DEPRECATION")
                root?.recycle()
            }
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
        }
    }

    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()
}
