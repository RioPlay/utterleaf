package org.utterleaf.voice.lifecyclehost

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.content.pm.PermissionInfo
import android.os.Bundle
import android.os.Process
import android.os.SystemClock
import android.provider.Settings
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.view.inputmethod.InputMethodManager
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.filters.SdkSuppress
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Cross-process lifecycle evidence driven by an editor that survives the IME.
 * Every value typed here is a fixed synthetic sentinel.
 */
@RunWith(AndroidJUnit4::class)
@SdkSuppress(minSdkVersion = 29)
class ImeLifecycleHostTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val host = instrumentation.targetContext
    private val automation = instrumentation.uiAutomation

    private companion object {
        const val PRODUCT_PACKAGE = "org.utterleaf.voice"
        const val KEYBOARD_SERVICE = "org.utterleaf.voice.KeyboardIme"
        const val PRODUCT_EDITOR = "org.utterleaf.voice.KeyboardTestActivity"
        const val PRODUCT_EDITOR_HINT = "Synthetic keyboard test"
        const val HOST_EDITOR_HINT = "Synthetic lifecycle host editor"
        const val FIXTURE_PERMISSION = "org.utterleaf.voice.permission.DEBUG_LIFECYCLE_HOST"
        const val TIMEOUT_MILLIS = 15_000L
    }

    private fun shell(command: String) = android.os.ParcelFileDescriptor.AutoCloseInputStream(
        automation.executeShellCommand(command),
    ).bufferedReader().use { it.readText().trim() }

    private fun <T> main(block: () -> T): T {
        var result: Result<T>? = null
        instrumentation.runOnMainSync { result = runCatching(block) }
        return result!!.getOrThrow()
    }

    private fun await(message: String, diagnostics: () -> String = { "" }, condition: () -> Boolean) {
        val deadline = SystemClock.elapsedRealtime() + TIMEOUT_MILLIS
        while (SystemClock.elapsedRealtime() < deadline) {
            if (condition()) return
            SystemClock.sleep(50)
        }
        val details = runCatching(diagnostics).getOrElse { "diagnostics failed: ${it.message}" }
        throw AssertionError(if (details.isBlank()) message else "$message; $details")
    }

    private fun find(root: AccessibilityNodeInfo, predicate: (AccessibilityNodeInfo) -> Boolean): AccessibilityNodeInfo? {
        if (predicate(root)) return root
        for (index in 0 until root.childCount) {
            root.getChild(index)?.let { child -> find(child, predicate)?.let { return it } }
        }
        return null
    }

    private fun imeNode(description: String): AccessibilityNodeInfo? {
        if (android.os.Build.VERSION.SDK_INT >= 34) automation.clearCache()
        return automation.windows.asSequence()
            .filter { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD }
            .mapNotNull { window -> window.root?.let { root ->
                find(root) {
                    it.isVisibleToUser && it.contentDescription?.toString() == description
                }
            } }
            .firstOrNull()
    }

    private fun editorNode(packageName: String, hint: String): AccessibilityNodeInfo? {
        if (android.os.Build.VERSION.SDK_INT >= 34) automation.clearCache()
        return automation.windows.asSequence()
            .filter { it.type == AccessibilityWindowInfo.TYPE_APPLICATION }
            .mapNotNull { window -> window.root?.let { root ->
                find(root) { node ->
                    node.packageName?.toString() == packageName &&
                        node.className?.toString() == android.widget.EditText::class.java.name &&
                        (node.hintText?.toString() == hint || node.contentDescription?.toString() == hint) &&
                        node.isVisibleToUser
                }
            } }
            .firstOrNull()
    }

    private fun foregroundPackage(): String? {
        if (android.os.Build.VERSION.SDK_INT >= 34) automation.clearCache()
        return automation.windows.asSequence()
            .firstOrNull { it.type == AccessibilityWindowInfo.TYPE_APPLICATION && it.isActive }
            ?.root?.packageName?.toString()
    }

    private fun pressIme(description: String): AccessibilityNodeInfo {
        var target: AccessibilityNodeInfo? = null
        await("Missing enabled IME control $description", ::imeDiagnostics) {
            imeNode(description)?.takeIf { it.isEnabled && it.isClickable }?.also { target = it } != null
        }
        val node = checkNotNull(target)
        if (!node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
            throw AssertionError("Enabled IME control $description rejected its single click")
        }
        instrumentation.waitForIdleSync()
        return node
    }

    private fun setEditorTextOnce(node: AccessibilityNodeInfo, value: String, phase: String) {
        val arguments = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value)
        }
        if (!node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)) {
            throw AssertionError("$phase editor rejected its single synthetic set-text action")
        }
        instrumentation.waitForIdleSync()
    }

    private fun clickEditorOnce(node: AccessibilityNodeInfo, phase: String) {
        if (!node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
            throw AssertionError("$phase editor rejected its single focus/show click")
        }
        instrumentation.waitForIdleSync()
    }

    private fun imeDiagnostics(): String = "defaultIme=${defaultIme()}, " +
        "labels={editing=${imeNode("Editing tools") != null}, " +
        "closeEditing=${imeNode("Close editing tools") != null}, " +
        "lowercaseX=${imeNode("x") != null}, " +
        "shiftOff=${imeNode("Shift off") != null}, shiftOn=${imeNode("Shift on") != null}}"

    private fun assertDailySurface(phase: String, requireShiftOff: Boolean = true) {
        await("$phase did not restore the daily keyboard surface", ::imeDiagnostics) {
            imeNode("Editing tools") != null && imeNode("Close editing tools") == null &&
                imeNode("x") != null &&
                (!requireShiftOff || (imeNode("Shift off") != null && imeNode("Shift on") == null))
        }
    }

    private fun openEditingTools() {
        pressIme("Editing tools")
        await("Editing tools did not open after their single click", ::imeDiagnostics) {
            imeNode("Close editing tools") != null && imeNode("x") == null
        }
    }

    private fun armShiftAndCaptureLiteral(): AccessibilityNodeInfo {
        pressIme("Shift off")
        await("Shift did not arm after its single click", ::imeDiagnostics) {
            imeNode("Shift on") != null && imeNode("X") != null
        }
        return checkNotNull(imeNode("X"))
    }

    private fun invokeStaleOnce(node: AccessibilityNodeInfo) {
        runCatching { node.performAction(AccessibilityNodeInfo.ACTION_CLICK) }
        instrumentation.waitForIdleSync()
        SystemClock.sleep(100)
    }

    private fun currentActivity(
        scenario: ActivityScenario<LifecycleHostActivity>,
    ): LifecycleHostActivity {
        var current: LifecycleHostActivity? = null
        scenario.onActivity { current = it }
        return checkNotNull(current)
    }

    private fun showHostInitially(
        scenario: ActivityScenario<LifecycleHostActivity>,
        manager: InputMethodManager,
        value: String,
    ): LifecycleHostActivity {
        val activity = currentActivity(scenario)
        await("Lifecycle host never acquired window focus") {
            main { activity.hasWindowFocus() }
        }
        scenario.onActivity {
            it.editor.setText(value)
            it.editor.setSelection(value.length)
            it.editor.requestFocus()
        }
        await("Lifecycle host editor never became active") {
            main { manager.isActive(activity.editor) }
        }
        var accepted = false
        scenario.onActivity {
            manager.restartInput(it.editor)
            accepted = manager.showSoftInput(it.editor, InputMethodManager.SHOW_IMPLICIT)
        }
        await(
            "Lifecycle host keyboard did not appear after one restart/show request",
            { "showAccepted=$accepted, active=${main { manager.isActive(activity.editor) }}, ${imeDiagnostics()}" },
        ) { imeNode("Editing tools") != null }
        return activity
    }

    private fun showHostAfterTransitionOnce(
        scenario: ActivityScenario<LifecycleHostActivity>,
        expected: LifecycleHostActivity,
        manager: InputMethodManager,
        phase: String,
    ) {
        await("$phase did not return to the original lifecycle host") {
            main { expected.hasWindowFocus() }
        }
        assertSame(expected, currentActivity(scenario))
        scenario.onActivity { it.editor.requestFocus() }
        await("$phase host editor did not become active") {
            main { manager.isActive(expected.editor) }
        }
        var accepted = false
        scenario.onActivity {
            accepted = manager.showSoftInput(it.editor, InputMethodManager.SHOW_IMPLICIT)
        }
        await(
            "$phase keyboard did not appear after one show request",
            { "showAccepted=$accepted, active=${main { manager.isActive(expected.editor) }}, ${imeDiagnostics()}" },
        ) { imeNode("Editing tools") != null }
    }

    private fun launchProductEditor(
        scenario: ActivityScenario<LifecycleHostActivity>,
    ) {
        val intent = Intent().setComponent(ComponentName(PRODUCT_PACKAGE, PRODUCT_EDITOR))
        scenario.onActivity { it.startActivity(intent) }
        await(
            "Signature-protected product editor did not become foreground",
            { "foreground=${foregroundPackage()}, editorPresent=${editorNode(PRODUCT_PACKAGE, PRODUCT_EDITOR_HINT) != null}" },
        ) { foregroundPackage() == PRODUCT_PACKAGE && editorNode(PRODUCT_PACKAGE, PRODUCT_EDITOR_HINT) != null }
    }

    private fun returnToHost() {
        host.startActivity(
            Intent(host, LifecycleHostActivity::class.java).addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP,
            ),
        )
    }

    private fun productEditorText(): String? = editorNode(PRODUCT_PACKAGE, PRODUCT_EDITOR_HINT)
        ?.text?.toString()

    private fun assertDebugFixtureContract() {
        val manager = host.packageManager
        val component = ComponentName(PRODUCT_PACKAGE, PRODUCT_EDITOR)
        val activity = manager.getActivityInfo(component, 0)
        assertTrue("Synthetic product editor is not exported in debug", activity.exported)
        assertEquals(FIXTURE_PERMISSION, activity.permission)
        val permission = manager.getPermissionInfo(FIXTURE_PERMISSION, 0)
        assertEquals(
            PermissionInfo.PROTECTION_SIGNATURE,
            permission.protectionLevel and PermissionInfo.PROTECTION_MASK_BASE,
        )
        assertEquals(PackageManager.SIGNATURE_MATCH, manager.checkSignatures(host.packageName, PRODUCT_PACKAGE))
        val own = manager.getPackageInfo(host.packageName, PackageManager.GET_PERMISSIONS)
        assertEquals(setOf(FIXTURE_PERMISSION), own.requestedPermissions.orEmpty().toSet())
        assertEquals(0, own.applicationInfo!!.flags and ApplicationInfo.FLAG_ALLOW_BACKUP)
    }

    private fun defaultIme(): String? = Settings.Secure.getString(
        host.contentResolver,
        Settings.Secure.DEFAULT_INPUT_METHOD,
    )

    private fun enabledImes(): Set<String> = shell("ime list -s")
        .lineSequence().map { it.trim() }.filter { it.isNotEmpty() }.toSet()

    private fun awaitDefaultIme(expected: String?, phase: String) {
        val deadline = SystemClock.elapsedRealtime() + TIMEOUT_MILLIS
        var matchingSince: Long? = null
        var observed: String? = null
        while (SystemClock.elapsedRealtime() < deadline) {
            val now = SystemClock.elapsedRealtime()
            observed = defaultIme()
            if (observed == expected) {
                val since = matchingSince ?: now.also { matchingSince = it }
                if (now - since >= 250) return
            } else {
                matchingSince = null
            }
            SystemClock.sleep(50)
        }
        throw AssertionError("$phase did not stabilize: expected=$expected, observed=$observed")
    }

    private fun cleanupPreserving(primaryFailure: Throwable?, vararg steps: () -> Unit) {
        var cleanupFailure: Throwable? = null
        steps.forEach { step ->
            try {
                step()
            } catch (error: Throwable) {
                if (primaryFailure != null) {
                    if (error !== primaryFailure) primaryFailure.addSuppressed(error)
                } else if (cleanupFailure == null) {
                    cleanupFailure = error
                } else if (error !== cleanupFailure) {
                    cleanupFailure!!.addSuppressed(error)
                }
            }
        }
        cleanupFailure?.let { throw it }
    }

    private fun withKeyboard(block: (InputMethodManager) -> Unit) {
        val manager = host.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        val info = manager.inputMethodList.single {
            it.packageName == PRODUCT_PACKAGE && it.serviceName == KEYBOARD_SERVICE
        }
        val id = info.id
        require(id.matches(Regex("[A-Za-z0-9_.]+/[A-Za-z0-9_.$]+")))
        val previousDefault = defaultIme()
        val previousEnabled = enabledImes()
        val flags = automation.serviceInfo.flags
        var primaryFailure: Throwable? = null
        try {
            automation.serviceInfo = automation.serviceInfo.apply {
                this.flags = flags or AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            }
            shell("ime enable $id")
            shell("ime set $id")
            awaitDefaultIme(id, "Lifecycle host IME setup")
            block(manager)
        } catch (error: Throwable) {
            primaryFailure = error
            throw error
        } finally {
            cleanupPreserving(
                primaryFailure,
                {
                    if (foregroundPackage() == PRODUCT_PACKAGE) returnToHost()
                },
                {
                    if (previousDefault.isNullOrBlank()) {
                        shell("settings delete secure default_input_method")
                    } else {
                        shell("ime set $previousDefault")
                    }
                    awaitDefaultIme(previousDefault, "Previous IME restore")
                },
                { if (id !in previousEnabled) shell("ime disable $id") },
                {
                    await("Enabled IME set did not restore", { "expected=$previousEnabled, observed=${enabledImes()}" }) {
                        enabledImes() == previousEnabled
                    }
                },
                { automation.serviceInfo = automation.serviceInfo.apply { this.flags = flags } },
            )
        }
    }

    private fun productUid(): Int {
        val value = shell("run-as $PRODUCT_PACKAGE id -u")
        return value.toIntOrNull() ?: throw AssertionError("Could not verify debug product UID: $value")
    }

    private fun productPids(): List<Int> = shell("pidof $PRODUCT_PACKAGE")
        .split(Regex("\\s+")).mapNotNull { it.toIntOrNull() }

    private fun verifyProductPid(pid: Int, uid: Int) {
        assertTrue("PID $pid is not owned by $PRODUCT_PACKAGE", pid in productPids())
        val status = shell("run-as $PRODUCT_PACKAGE cat /proc/$pid/status")
        val observed = Regex("(?m)^Uid:\\s+(\\d+)").find(status)?.groupValues?.get(1)?.toIntOrNull()
        assertEquals("PID $pid UID mismatch", uid, observed)
    }

    private fun replacementPid(oldPid: Int, uid: Int): Int? {
        val candidates = productPids().filter { it != oldPid }
        if (candidates.size != 1) return null
        return candidates.single().takeIf {
            runCatching { verifyProductPid(it, uid) }.isSuccess
        }
    }

    @Test
    fun crossApplicationTransitionsResetToolsAndModifiersWithoutStaleInput() = withKeyboard { manager ->
        assertDebugFixtureContract()
        ActivityScenario.launch(LifecycleHostActivity::class.java).use { scenario ->
            val activity = showHostInitially(scenario, manager, "source ")
            openEditingTools()
            assertTrue("Editing layer was not active before the application transition",
                imeNode("Close editing tools") != null)

            launchProductEditor(scenario)
            var product = checkNotNull(editorNode(PRODUCT_PACKAGE, PRODUCT_EDITOR_HINT))
            setEditorTextOnce(product, "target ", "Product")
            product = checkNotNull(editorNode(PRODUCT_PACKAGE, PRODUCT_EDITOR_HINT))
            clickEditorOnce(product, "Product")
            await("Product editor did not receive input focus") {
                editorNode(PRODUCT_PACKAGE, PRODUCT_EDITOR_HINT)?.isFocused == true
            }
            assertDailySurface("Cross-application transition")
            pressIme("x")
            await("Fresh keyboard did not type into the product editor") {
                productEditorText() == "target x"
            }
            val staleUppercase = armShiftAndCaptureLiteral()

            returnToHost()
            showHostAfterTransitionOnce(scenario, activity, manager, "Return cross-application transition")
            assertDailySurface("Return cross-application transition")
            invokeStaleOnce(staleUppercase)
            assertEquals("Stale product key reached the restored host", "source ", main {
                activity.editor.text.toString()
            })
            pressIme("x")
            await("Fresh keyboard did not type into the restored host") {
                main { activity.editor.text.toString() == "source x" }
            }
        }
    }

    @Test
    fun imeProcessDeathRebindsSameHostWithFreshTransientState() = withKeyboard { manager ->
        ActivityScenario.launch(LifecycleHostActivity::class.java).use { scenario ->
            val activity = showHostInitially(scenario, manager, "seed ")
            pressIme("a")
            await("Baseline literal did not reach the surviving host") {
                main { activity.editor.text.toString() == "seed a" }
            }
            val staleUppercase = armShiftAndCaptureLiteral()
            val hostPid = Process.myPid()
            val productUid = productUid()
            val oldPids = productPids()
            assertEquals("Expected one product process before the exact PID kill", 1, oldPids.size)
            val oldPid = oldPids.single()
            assertFalse("Lifecycle host unexpectedly shares the IME process", hostPid == oldPid)
            verifyProductPid(oldPid, productUid)

            shell("run-as $PRODUCT_PACKAGE kill -9 $oldPid")
            await("Verified IME PID remained alive after SIGKILL", { "productPids=${productPids()}" }) {
                oldPid !in productPids()
            }

            var newPid: Int? = null
            val automaticDeadline = SystemClock.elapsedRealtime() + 3_000
            while (SystemClock.elapsedRealtime() < automaticDeadline && newPid == null) {
                val candidate = replacementPid(oldPid, productUid)
                if (candidate != null && imeNode("Editing tools") != null) newPid = candidate
                else SystemClock.sleep(50)
            }
            if (newPid == null) {
                scenario.onActivity { it.editor.requestFocus() }
                await("Surviving editor did not remain active after IME death") {
                    main { manager.isActive(activity.editor) }
                }
                var accepted = false
                scenario.onActivity {
                    accepted = manager.showSoftInput(it.editor, InputMethodManager.SHOW_IMPLICIT)
                }
                await(
                    "IME did not rebind after one same-field show request",
                    { "showAccepted=$accepted, productPids=${productPids()}, ${imeDiagnostics()}" },
                ) {
                    replacementPid(oldPid, productUid)?.also { newPid = it } != null &&
                        imeNode("Editing tools") != null
                }
            }
            val reboundPid = checkNotNull(newPid)
            verifyProductPid(reboundPid, productUid)
            assertFalse("IME rebound reused its killed PID", reboundPid == oldPid)
            assertEquals("Lifecycle host process changed across IME death", hostPid, Process.myPid())
            assertSame("Lifecycle host Activity changed across IME death", activity, currentActivity(scenario))
            assertEquals("Host text changed across IME death", "seed a", main {
                activity.editor.text.toString()
            })
            assertEquals("Host selection changed across IME death", "seed a".length, main {
                activity.editor.selectionStart
            })
            assertDailySurface("IME process rebound")
            invokeStaleOnce(staleUppercase)
            assertEquals("Stale pre-death key reached the surviving host", "seed a", main {
                activity.editor.text.toString()
            })
            pressIme("b")
            await("Fresh rebound keyboard did not type into the surviving host") {
                main { activity.editor.text.toString() == "seed ab" }
            }
            pressIme("Delete")
            await("Fresh rebound keyboard did not delete from the surviving host") {
                main { activity.editor.text.toString() == "seed a" }
            }
        }
    }
}
