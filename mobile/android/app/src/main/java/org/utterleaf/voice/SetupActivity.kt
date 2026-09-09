package org.utterleaf.voice

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.widget.ScrollView
import android.widget.TextView

class SetupActivity : Activity() {
    private lateinit var status: TextView
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val column = Ui.column(this)
        column.addView(Ui.mascot(this))
        column.addView(Ui.title(this, "Let ideas speak."))
        column.addView(Ui.text(this, "Utterleaf Voice · Android preview", 18f))
        column.addView(Ui.text(this, "Private voice input for compatible keyboards. No Internet permission, accounts, or saved recordings."))
        status = Ui.text(this, readiness())
        column.addView(status)
        column.addView(Ui.text(this, "1 · Import the English model", 19f))
        column.addView(Ui.text(this, "Download ggml-tiny.en.bin (77.7 MB) in your browser, then import it. Utterleaf verifies its SHA-256 before use. About 156 MB free space is needed while importing."))
        column.addView(Ui.button(this, "Open model download in browser") {
            AlertDialog.Builder(this).setTitle("Open Hugging Face?")
                .setMessage("Your browser will connect to Hugging Face to download the English model. Utterleaf itself has no Internet permission.")
                .setNegativeButton("Cancel", null).setPositiveButton("Open browser") { _, _ ->
                    try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(ModelStore.URL))) }
                    catch (_: android.content.ActivityNotFoundException) { status.text = "No browser available. Transfer ggml-tiny.en.bin from another device." }
                }.show()
        })
        column.addView(Ui.button(this, "Import downloaded model") {
            try { startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE); type = "*/*"
            }, 10) } catch (_: android.content.ActivityNotFoundException) { status.text = "No document picker is available." }
        })
        column.addView(Ui.text(this, "2 · Allow your microphone", 19f))
        column.addView(Ui.button(this, "Allow microphone") {
            if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
                status.text = "Microphone permission granted. Capture starts only when you tap Speak."
            else requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 11)
        })
        column.addView(Ui.button(this, "Open app permissions") {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
        })
        column.addView(Ui.text(this, "3 · Enable voice input", 19f))
        column.addView(Ui.button(this, "Open keyboard settings") { startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)) })
        column.addView(Ui.text(this, "Enable Utterleaf Voice, then select it using the keyboard switcher. Compatible keyboards may open it from their microphone button. Gboard and Samsung Keyboard do not offer this integration."))
        column.addView(Ui.text(this, "English only in this preview. Each take is limited to 120 seconds with a countdown. Preview text expires after two minutes and is cleared when you leave or change fields. No automatic clipboard writes. Password fields are blocked by our IME."))
        column.addView(Ui.button(this, "Delete imported model") {
            AlertDialog.Builder(this).setTitle("Delete the model?").setMessage("You will need to import it again to dictate.")
                .setNegativeButton("Cancel", null).setPositiveButton("Delete") { _, _ ->
                    if (WorkLease.acquire()) {
                        try { status.text = if (!ModelStore.file(noBackupFilesDir).exists() || ModelStore.file(noBackupFilesDir).delete()) "Model deleted." else "Could not delete model. Try again." }
                        finally { WorkLease.release() }
                    } else status.text = "Wait for the current take or import to finish."
                }.show()
        })
        column.addView(Ui.button(this, "Licenses and privacy") {
            AlertDialog.Builder(this).setTitle("Utterleaf Voice")
                .setMessage(assets.open("NOTICE.txt").bufferedReader().use { it.readText() })
                .setNeutralButton("Full licenses") { _, _ ->
                    val licenses = listOf("UTTERLEAF-LICENSE.txt", "WHISPER-LICENSE.txt", "MODEL-LICENSE.txt", "LIBCXX-LICENSE.txt")
                        .joinToString("\n\n") { name -> name + "\n\n" + assets.open(name).bufferedReader().use { it.readText() } }
                    AlertDialog.Builder(this).setTitle("Third-party licenses").setMessage(licenses).setPositiveButton("Close", null).show()
                }
                .setPositiveButton("Close", null).show()
        })
        setContentView(ScrollView(this).apply { addView(column) })
        window.decorView.setOnApplyWindowInsetsListener { view, insets ->
            view.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop,
                insets.systemWindowInsetRight, insets.systemWindowInsetBottom); insets
        }
    }
    private fun readiness() = if (ModelStore.ready(noBackupFilesDir)) "English model installed · microphone off" else "Model not installed · microphone off"
    @Deprecated("Platform callback")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != 10 || resultCode != RESULT_OK) return
        val uri = data?.data ?: return
        if (!WorkLease.acquire()) { status.text = "Wait for the current take or import to finish."; return }
        status.text = "Importing and verifying locally…"
        val app = applicationContext
        Thread({
            val message = try {
                app.contentResolver.openInputStream(uri).use { input ->
                    requireNotNull(input) { "Could not open the selected file." }
                    ModelStore.install(input, app.noBackupFilesDir)
                }
                "English model verified and installed."
            } catch (_: Exception) { "Import failed. Choose the original ggml-tiny.en.bin file and check free storage. Existing model kept." }
            finally { WorkLease.release() }
            runOnUiThread { if (!isDestroyed) status.text = message }
        }, "utterleaf-import").start()
    }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        status.text = if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) "Microphone allowed. Enable Utterleaf Voice in keyboard settings."
                      else "Microphone permission is off. Use Open app permissions if Android no longer shows the prompt."
    }
}
