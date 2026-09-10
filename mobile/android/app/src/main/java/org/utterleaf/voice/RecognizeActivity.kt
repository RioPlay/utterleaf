package org.utterleaf.voice

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.speech.RecognizerIntent
import android.view.WindowManager

class RecognizeActivity : Activity() {
    private var panel: VoicePanel? = null
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setResult(RESULT_CANCELED)
        if (intent.action != RecognizerIntent.ACTION_RECOGNIZE_SPEECH || callingPackage == null) { finish(); return }
        val language = intent.getStringExtra(RecognizerIntent.EXTRA_LANGUAGE)
        if (language != null && !language.equals("en", true) && !language.startsWith("en-", true) && !language.startsWith("en_", true)) {
            android.widget.Toast.makeText(this, "This preview supports English only.", android.widget.Toast.LENGTH_LONG).show()
            finish(); return
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        panel = VoicePanel(this, { text ->
            setResult(RESULT_OK, Intent().putStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS, arrayListOf(text)))
            finish(); true
        }, { finish() })
        setContentView(panel!!.view)
        Ui.applySystemInsets(panel!!.view)
    }
    override fun onPause() { panel?.clear(); super.onPause() }
    override fun onDestroy() { panel?.clear(); super.onDestroy() }
}
