package org.utterleaf.keyboard.next

import android.content.pm.PackageManager
import android.content.pm.PermissionInfo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.utterleaf.keyboard.next.settings.LocalPrivacyStorage
import java.io.File

@RunWith(AndroidJUnit4::class)
class CapabilityTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    @Test fun keyboardHasNoCaptureNetworkStorageOrDiscoveryCapabilities() {
        val info = context.packageManager.getPackageInfo(context.packageName,
            PackageManager.GET_PERMISSIONS or PackageManager.GET_SERVICES or PackageManager.GET_RECEIVERS or PackageManager.GET_PROVIDERS)
        val signaturePermission = "${context.packageName}.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION"
        assertEquals(setOf(signaturePermission), info.requestedPermissions.orEmpty().toSet())
        assertEquals(PermissionInfo.PROTECTION_SIGNATURE,
            context.packageManager.getPermissionInfo(signaturePermission, 0).protectionLevel and PermissionInfo.PROTECTION_MASK_BASE)
        assertEquals(1, info.services.orEmpty().size)
        val service = info.services.orEmpty().single()
        assertEquals("${context.packageName}.NextKeyboardIme", service.name)
        assertEquals("android.permission.BIND_INPUT_METHOD", service.permission)
        // AndroidX installs baseline profiles. Any new component or weaker boundary fails here.
        val receiver = info.receivers.orEmpty().single()
        assertEquals("androidx.profileinstaller.ProfileInstallReceiver", receiver.name)
        assertEquals("android.permission.DUMP", receiver.permission)
        assertTrue(receiver.exported)
        assertTrue(receiver.enabled)
        assertFalse(receiver.directBootAware)
        val provider = info.providers.orEmpty().single()
        assertEquals("androidx.startup.InitializationProvider", provider.name)
        assertEquals("${context.packageName}.androidx-startup", provider.authority)
        assertFalse(provider.exported)
        assertFalse(provider.grantUriPermissions)
        assertNull(provider.readPermission)
        assertNull(provider.writePermission)
    }

    @Test fun atomicPrivacyReopenResetIsolationAndMalformedRecord() {
        // Task-owned synthetic test directory; does not mutate the real preference file.
        val dir = File(context.cacheDir, "privacy-storage-test").apply { mkdirs() }
        val record = File(dir, "privacy.v1")
        val backup = File(dir, "privacy.v1.bak")
        val userAsset = File(dir, "synthetic-model.keep")
        try {
            record.delete(); backup.delete()
            userAsset.writeText("synthetic asset")
            val store = LocalPrivacyStorage(dir)
            assertFalse(store.read())
            store.write(true)
            assertTrue(LocalPrivacyStorage(dir).read())
            assertEquals("synthetic asset", userAsset.readText())
            record.writeText("invalid\n")
            assertTrue(runCatching { store.read() }.isFailure)
            store.write(false)
            assertFalse(LocalPrivacyStorage(dir).read())
        } finally {
            record.delete(); backup.delete(); userAsset.delete(); dir.delete()
        }
    }
}
