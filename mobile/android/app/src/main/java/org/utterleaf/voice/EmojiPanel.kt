package org.utterleaf.voice

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.InsetDrawable
import android.graphics.drawable.RippleDrawable
import android.graphics.drawable.StateListDrawable
import android.os.Handler
import android.os.Looper
import android.util.TypedValue
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import java.util.Collections
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/** Public catalog/font data only. No query, host text or selection enters this cache. */
internal data class EmojiData(val catalog: EmojiCatalog, val supported: Set<String>)

internal object EmojiRepository {
    private val main = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor { task ->
        Thread(task, "utterleaf-emoji-catalog").apply { isDaemon = true }
    }
    private val lock = Any()
    private var cached: EmojiData? = null
    private var loading = false
    private val waiting = mutableMapOf<AtomicBoolean, (EmojiData?) -> Unit>()

    fun load(context: Context, complete: (EmojiData?) -> Unit): () -> Unit {
        val cancelled = AtomicBoolean(false)
        val app = context.applicationContext
        synchronized(lock) {
            val ready = cached
            if (ready != null) main.post { if (!cancelled.get()) complete(ready) }
            else {
                waiting[cancelled] = complete
                if (!loading) {
                    loading = true
                    worker.execute {
                        val result = try {
                            val catalog = app.resources.openRawResource(R.raw.emoji_catalog)
                                .bufferedReader(Charsets.UTF_8).use { EmojiCatalog.parse(it) }
                            val paint = Paint().apply {
                                typeface = Typeface.create("sans-serif", Typeface.NORMAL)
                                textSize = 32f
                            }
                            EmojiData(catalog, Collections.unmodifiableSet(catalog.entries
                                .filter { paint.hasGlyph(it.sequence) }.map { it.sequence }.toSet()))
                        } catch (_: Exception) { null }
                        val callbacks = synchronized(lock) {
                            cached = result
                            loading = false
                            waiting.toList().also { waiting.clear() }
                        }
                        callbacks.forEach { (token, callback) ->
                            main.post { if (!token.get()) callback(result) }
                        }
                    }
                }
            }
        }
        return { cancelled.set(true); synchronized(lock) { waiting.remove(cancelled) }; Unit }
    }
}

/** Local search keys never call the editor. Only a selected catalog entry can commit. */
internal class EmojiPanel(private val context: Context, private val options: KeyboardOptions,
    private val commit: (String) -> Boolean, private val returnToTyping: () -> Unit,
    load: ((EmojiData?) -> Unit) -> (() -> Unit) = { EmojiRepository.load(context, it) }) {
    val view = object : LinearLayout(context) {
        override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
            val width = View.MeasureSpec.getSize(widthMeasureSpec)
            if (View.MeasureSpec.getMode(widthMeasureSpec) != View.MeasureSpec.UNSPECIFIED && width > 0) {
                val count = (width / Ui.dp(context, 48).coerceAtLeast(1)).coerceIn(1, 8)
                if (columns != count) { columns = count; page = 0; render() }
            }
            super.onMeasure(widthMeasureSpec, heightMeasureSpec)
        }
    }.apply {
        orientation = LinearLayout.VERTICAL
        layoutDirection = View.LAYOUT_DIRECTION_LTR
    }
    private val keyColor = Color.parseColor(if (options.light) "#FFFFFF" else "#303A3D")
    private val utility = Color.parseColor(if (options.light) "#D1DFD6" else "#24322D")
    private val ink = Color.parseColor(if (options.light) "#17251D" else "#F0F5F2")
    private val accent = Color.parseColor(if (options.light) "#25643D" else "#A2DFB3")
    private val accentInk = Color.parseColor(if (options.light) "#FFFFFF" else "#10291B")
    private val keyHeight = if (options.keyHeightDp == 0) { if (options.large) 66 else 54 }
        else options.keyHeightDp.coerceIn(48, 80)
    private var disposed = false
    private var generation = 0
    private var resultGeneration = 0
    private var columns = 6
    private var data: EmojiData? = null
    private var loading = true
    private var searchOpen = false
    private var categoriesOpen = false
    private var category = ""
    private var query = ""
    private var family: EmojiEntry? = null
    private var page = 0
    private var results: List<EmojiEntry> = emptyList()
    private var resultArea: LinearLayout? = null
    private var queryLabel: TextView? = null
    private var pageLabel: TextView? = null
    private var previous: Button? = null
    private var next: Button? = null
    private var failure: Toast? = null
    private var cancelLoad: () -> Unit = {}

    init {
        render()
        view.addOnAttachStateChangeListener(object : View.OnAttachStateChangeListener {
            override fun onViewAttachedToWindow(v: View) = Unit
            override fun onViewDetachedFromWindow(v: View) { clear() }
        })
        cancelLoad = load { loaded ->
            if (!disposed) {
                data = loaded; loading = false
                category = loaded?.catalog?.categories?.firstOrNull().orEmpty()
                render()
            }
        }
    }

    fun clear() {
        if (disposed) return
        disposed = true; generation++; resultGeneration++
        cancelLoad(); failure?.cancel(); failure = null
        query = ""; family = null; results = emptyList(); data = null
        queryLabel?.text = ""; queryLabel = null
        view.removeAllViews()
    }

    private fun shape(color: Int) = GradientDrawable().apply {
        setColor(color); cornerRadius = Ui.dp(context, 9).toFloat()
    }

    private fun row(parent: LinearLayout = view) = LinearLayout(context).also {
        it.orientation = LinearLayout.HORIZONTAL; it.isBaselineAligned = false
        parent.addView(it, LinearLayout.LayoutParams(-1, -2))
    }

    private fun button(row: LinearLayout, label: String, description: String = label,
        height: Int = 48, ordinary: Boolean = false, weight: Float = 1f,
        action: () -> Unit): Button {
        val token = generation
        return Button(context).apply {
            text = label; contentDescription = description; isAllCaps = false
            minWidth = 0; minimumWidth = 0; minHeight = 0; minimumHeight = 0
            setPadding(0, 0, 0, 0); includeFontPadding = false; gravity = Gravity.CENTER
            setSingleLine(); setHorizontallyScrolling(false)
            setAutoSizeTextTypeUniformWithConfiguration(12,
                if (ordinary) (if (options.large) 30 else 26) else (if (options.large) 16 else 14),
                1, TypedValue.COMPLEX_UNIT_SP)
            typeface = Typeface.create("sans-serif", Typeface.NORMAL)
            val states = StateListDrawable().apply {
                addState(intArrayOf(android.R.attr.state_selected), shape(accent))
                addState(intArrayOf(android.R.attr.state_focused), shape(accent))
                addState(intArrayOf(), shape(if (ordinary) keyColor else utility))
            }
            background = InsetDrawable(RippleDrawable(ColorStateList.valueOf(0x40808080), states,
                shape(Color.WHITE)), Ui.dp(context, 2), Ui.dp(context, 3), Ui.dp(context, 2), Ui.dp(context, 3))
            backgroundTintList = null; stateListAnimator = null
            setTextColor(ColorStateList(arrayOf(intArrayOf(-android.R.attr.state_enabled),
                intArrayOf(android.R.attr.state_selected), intArrayOf(android.R.attr.state_focused), intArrayOf()),
                intArrayOf(Color.parseColor(if (options.light) "#66766B" else "#97A79E"), accentInk, accentInk, ink)))
            isSoundEffectsEnabled = false; isHapticFeedbackEnabled = options.haptics
            setOnClickListener {
                if (disposed || token != generation) return@setOnClickListener
                failure?.cancel(); failure = null
                if (options.haptics) performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                action()
            }
            row.addView(this, LinearLayout.LayoutParams(0, Ui.dp(context, height), weight))
        }
    }

    private fun label(text: String, parent: LinearLayout = view, weight: Float? = null): TextView =
        TextView(context).apply {
            this.text = text; textSize = if (options.large) 16f else 14f; setTextColor(ink)
            gravity = Gravity.CENTER; maxLines = 2
            setPadding(Ui.dp(context, 4), Ui.dp(context, 2), Ui.dp(context, 4), Ui.dp(context, 2))
            val params = if (weight == null) LinearLayout.LayoutParams(-1, Ui.dp(context, 40))
                else LinearLayout.LayoutParams(0, Ui.dp(context, 48), weight)
            parent.addView(this, params)
        }

    private fun render() {
        if (disposed) return
        generation++; resultGeneration++
        view.removeAllViews(); resultArea = null; queryLabel = null
        pageLabel = null; previous = null; next = null
        val header = row()
        button(header, "ABC", "Return from emoji to letters") { clear(); returnToTyping() }
        button(header, "Categories", "Emoji categories") {
            categoriesOpen = !categoriesOpen; family = null; page = 0; render()
        }.apply { isSelected = categoriesOpen; isEnabled = data != null }
        button(header, if (searchOpen) "Browse" else "Search", "${if (searchOpen) "Browse" else "Search"} emoji") {
            searchOpen = !searchOpen; categoriesOpen = false; family = null; query = ""; page = 0; render()
        }.apply { isEnabled = data != null }
        if (loading || data == null) {
            label(if (loading) "Loading local emoji…" else "Emoji unavailable. Return to typing and try again.")
            return
        }
        if (categoriesOpen) {
            label("Choose an emoji category")
            data!!.catalog.categories.chunked(3).forEach { categories ->
                val line = row()
                categories.forEach { value ->
                    button(line, categoryLabel(value), "Emoji category: ${categoryLabel(value)}", height = keyHeight) {
                        category = value; categoriesOpen = false; searchOpen = false; query = ""; family = null; page = 0; render()
                    }.isSelected = value == category
                }
            }
            return
        }
        if (family != null) {
            val back = row()
            button(back, "Back", "Back from emoji variants") { family = null; page = 0; render() }
            label("Choose a variation", back, 3f)
        } else if (searchOpen) {
            queryLabel = label("")
            queryLabel!!.tag = "emoji-query"
        } else label(categoryLabel(category))
        resultArea = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL; view.addView(this) }
        if (searchOpen && family == null) {
            options.letterLayout.rows.forEach { letters ->
                val line = row()
                val edge = (10 - letters.length) / 2f
                fun edgeSpace() {
                    if (edge > 0f) line.addView(View(context).apply {
                        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
                    }, LinearLayout.LayoutParams(0, 1, edge))
                }
                edgeSpace()
                letters.forEach { letter ->
                    button(line, letter.toString(), "Emoji search letter $letter", height = keyHeight, ordinary = true) {
                        if (query.length < 48) { query += letter; page = 0; updateResults() }
                    }
                }
                edgeSpace()
            }
            val local = row()
            button(local, "Clear", "Clear emoji search") { query = ""; page = 0; updateResults() }
            button(local, "Space", "Emoji search space", weight = 2f) {
                if (query.isNotEmpty() && query.length < 48 && !query.endsWith(' ')) {
                    query += " "; page = 0; updateResults()
                }
            }
            button(local, "Delete", "Delete emoji search letter") {
                if (query.isNotEmpty()) { query = query.dropLast(1); page = 0; updateResults() }
            }
        }
        val paging = row()
        previous = button(paging, "Previous", "Previous emoji page") { page--; updateResults() }
        pageLabel = label("", paging, 1f)
        next = button(paging, "Next", "Next emoji page") { page++; updateResults() }
        updateResults()
    }

    private fun updateResults() {
        if (disposed) return
        val current = data ?: return
        resultGeneration++
        val token = resultGeneration
        queryLabel?.apply {
            text = if (query.isEmpty()) "Search emoji · English names" else query
            contentDescription = if (query.isEmpty()) "Emoji search: empty. English names."
                else "Emoji search: $query"
        }
        val selected = family
        results = (if (selected != null) current.catalog.familyVariants(selected)
            else if (searchOpen && query.isNotBlank()) current.catalog.search(query, 4096)
            else current.catalog.categoryEntries(category)).filter { it.sequence in current.supported }
        val rows = if (searchOpen && selected == null) 1 else 4
        val count = columns * rows
        val pages = ((results.size + count - 1) / count).coerceAtLeast(1)
        page = page.coerceIn(0, pages - 1)
        val visible = results.drop(page * count).take(count)
        resultArea?.removeAllViews()
        val area = resultArea ?: return
        // Empty/filter results must not move the query keys underneath a finger.
        area.layoutParams = LinearLayout.LayoutParams(-1, Ui.dp(context, rows * keyHeight))
        if (visible.isEmpty()) {
            label(if (searchOpen && query.isNotBlank()) "No matching emoji supported by this device."
                else "No emoji in this category are supported by this device.", area)
        } else {
            repeat(rows) { index ->
                val line = row(area)
                repeat(columns) { column ->
                    val entry = visible.getOrNull(index * columns + column)
                    if (entry == null) line.addView(View(context).apply {
                        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
                    }, LinearLayout.LayoutParams(0, Ui.dp(context, keyHeight), 1f))
                    else {
                        val variants = selected == null && !(searchOpen && query.isNotBlank()) &&
                            current.catalog.familyVariants(entry).count { it.sequence in current.supported } > 1
                        button(line, entry.sequence, entry.name + if (variants) "; choose variation" else "",
                            height = keyHeight, ordinary = true) {
                            if (token != resultGeneration) return@button
                            if (variants) { family = entry; page = 0; render() }
                            else if (!commit(entry.sequence)) {
                                failure = Toast.makeText(context, "Emoji could not be inserted", Toast.LENGTH_SHORT)
                                    .also { it.show() }
                                view.announceForAccessibility("Emoji could not be inserted")
                            }
                        }
                    }
                }
            }
        }
        pageLabel?.text = context.getString(R.string.emoji_page_count, page + 1, pages)
        pageLabel?.contentDescription = "Emoji page ${page + 1} of $pages"
        previous?.isEnabled = page > 0; next?.isEnabled = page + 1 < pages
    }

    private fun categoryLabel(value: String) = when (value) {
        "smileys-emotion" -> "Smileys"
        "people-body" -> "People"
        "animals-nature" -> "Nature"
        "food-drink" -> "Food"
        "travel-places" -> "Travel"
        "activities" -> "Activities"
        "objects" -> "Objects"
        "symbols" -> "Symbols"
        "flags" -> "Flags"
        else -> value
    }
}
