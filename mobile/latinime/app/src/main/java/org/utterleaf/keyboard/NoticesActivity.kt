package org.utterleaf.keyboard

import android.app.Activity
import android.app.AlertDialog
import android.content.res.AssetManager
import android.os.Bundle
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.view.ViewCompat
import com.android.inputmethod.latin.R
import org.json.JSONObject

/** Reads only the reviewed notice documents bundled with this application. */
class NoticesActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        title = getString(R.string.notices_title)
        val panel = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        panel.addView(TextView(this).apply {
            setText(R.string.notices_title)
            textSize = 24f
            ViewCompat.setAccessibilityHeading(this, true)
        })
        for (document in NoticeDocuments.read(assets)) {
            panel.addView(Button(this).apply {
                text = document.title
                setOnClickListener {
                    val body = TextView(this@NoticesActivity).apply {
                        text = assets.open("notices/${document.file}").bufferedReader(Charsets.UTF_8).use { it.readText() }
                        textSize = 16f
                        setTextIsSelectable(true)
                        setPadding(dp(20), dp(12), dp(20), dp(12))
                    }
                    val dialog = AlertDialog.Builder(this@NoticesActivity)
                        .setTitle(document.title)
                        .setView(ScrollView(this@NoticesActivity).apply { addView(body) })
                        .setPositiveButton(R.string.notices_close, null)
                        .create()
                    dialog.window?.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
                    dialog.show()
                }
            })
        }
        val page = ScrollView(this).apply { addView(panel) }
        page.applyContentInsets(dp(20))
        setContentView(page)
        ViewCompat.requestApplyInsets(page)
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
}

internal object NoticeDocuments {
    data class Document(val file: String, val title: String, val sha256: String)

    fun read(assets: AssetManager): List<Document> {
        val catalog = JSONObject(assets.open("notices/catalog.json").bufferedReader(Charsets.UTF_8).use { it.readText() })
        require(catalog.getInt("schema_version") == 1)
        val documents = catalog.getJSONArray("documents")
        return List(documents.length()) { index ->
            val entry = documents.getJSONObject(index)
            val file = entry.getString("file")
            require(file.matches(Regex("[A-Za-z0-9_-][A-Za-z0-9_.-]*\\.(txt|md|json)")) && !file.contains(".."))
            Document(file, entry.getString("title"), entry.getString("sha256"))
        }
    }
}
