package org.utterleaf.voice

import java.io.Reader
import java.text.Normalizer
import java.util.Collections
import java.util.Locale

enum class EmojiCategory(val id: String, val label: String) {
    SMILEYS_EMOTION("smileys-emotion", "Smileys & Emotion"),
    PEOPLE_BODY("people-body", "People & Body"),
    ANIMALS_NATURE("animals-nature", "Animals & Nature"),
    FOOD_DRINK("food-drink", "Food & Drink"),
    TRAVEL_PLACES("travel-places", "Travel & Places"),
    ACTIVITIES("activities", "Activities"),
    OBJECTS("objects", "Objects"),
    SYMBOLS("symbols", "Symbols"),
    FLAGS("flags", "Flags");

    companion object {
        private val byId = entries.associateBy(EmojiCategory::id)
        fun fromId(id: String): EmojiCategory? = byId[id]
    }
}

data class EmojiEntry(
    val sequence: String,
    val name: String,
    val category: EmojiCategory,
    val subgroup: String,
    val keywords: List<String>,
    val familyKey: String,
    val isCanonical: Boolean,
)

/** Immutable, bounded runtime view of the generated Unicode emoji resource. */
class EmojiCatalog private constructor(parsedEntries: List<EmojiEntry>) {
    val entries: List<EmojiEntry> = immutableList(parsedEntries)
    val categories: List<String> = immutableList(
        parsedEntries.map { it.category.id }.distinct(),
    )

    private val families: Map<String, List<EmojiEntry>> = parsedEntries
        .groupBy(EmojiEntry::familyKey)
        .mapValues { (_, values) -> immutableList(values) }
    private val categoryRepresentatives: Map<EmojiCategory, List<EmojiEntry>> = EmojiCategory.entries.associateWith { category ->
        immutableList(parsedEntries.filter { it.category == category && it.isCanonical })
    }
    private val searchRows = parsedEntries.mapIndexed { index, entry -> SearchRow(index, entry) }

    fun categoryEntries(category: String): List<EmojiEntry> =
        EmojiCategory.fromId(category)?.let { categoryRepresentatives[it] }.orEmpty()

    fun categoryEntries(category: EmojiCategory): List<EmojiEntry> = categoryRepresentatives[category].orEmpty()

    fun familyVariants(entry: EmojiEntry): List<EmojiEntry> =
        families[entry.familyKey].orEmpty()

    fun search(query: String, limit: Int = MAX_SEARCH_LIMIT): List<EmojiEntry> {
        require(query.length <= MAX_QUERY_LENGTH) { "emoji query exceeds $MAX_QUERY_LENGTH characters" }
        require(limit in 0..MAX_SEARCH_LIMIT) { "emoji search limit outside 0..$MAX_SEARCH_LIMIT" }
        if (limit == 0) return emptyList()
        val normalized = normalizeQuery(query)
        if (normalized.isEmpty()) return emptyList()
        val queryTokens = normalized.split(' ')
        return immutableList(searchRows.asSequence()
            .mapNotNull { row -> row.rank(normalized, queryTokens)?.let { rank -> Ranked(rank, row.index, row.entry) } }
            .sortedWith(compareBy<Ranked>({ it.rank }, { it.index }))
            .take(limit)
            .map(Ranked::entry)
            .toList())
    }

    private data class Ranked(val rank: Int, val index: Int, val entry: EmojiEntry)

    private data class SearchRow(val index: Int, val entry: EmojiEntry) {
        private val name = normalizeQuery(entry.name)
        private val keywords = entry.keywords.map(::normalizeQuery)
        private val words = (name.split(' ') + keywords.flatMap { it.split(' ') }).filter(String::isNotEmpty)

        fun rank(query: String, tokens: List<String>): Int? = when {
            name == query -> 0
            keywords.any { it == query } -> 1
            name.startsWith(query) -> 2
            keywords.any { it.startsWith(query) } -> 3
            tokens.all { token -> words.any { word -> word.startsWith(token) } } -> 4
            name.contains(query) -> 5
            keywords.any { it.contains(query) } -> 6
            else -> null
        }
    }

    companion object {
        const val MAX_QUERY_LENGTH = 48
        const val MAX_SEARCH_LIMIT = 4096
        const val MAX_ENTRIES = 4096
        const val MAX_CATALOG_CHARS = 1_000_000
        const val MAX_LINE_CHARS = 4096
        const val MAX_SEQUENCE_CODEPOINTS = 32
        const val MAX_KEYWORDS = 128

        private const val MAGIC = "# utterleaf-emoji-catalog-v1"
        private const val SPDX_HEADER = "# SPDX-License-Identifier: Unicode-3.0"
        private const val UNICODE_HEADER = "# unicode=17.0"
        private const val CLDR_HEADER = "# cldr=48@acd6d88ae493633240e19a87a721076a8a75c310"
        private const val KEYWORD_SEPARATOR = '|'
        private val combiningMarks = Regex("\\p{M}+")
        private val separators = Regex("[^\\p{L}\\p{N}]+")

        fun parse(text: String): EmojiCatalog = parse(text.reader())

        /** Parses without closing [reader]; the caller owns its lifecycle. */
        fun parse(reader: Reader): EmojiCatalog {
            val lines = readBoundedLines(reader)
            require(lines.take(4) == listOf(MAGIC, SPDX_HEADER, UNICODE_HEADER, CLDR_HEADER)) {
                "invalid emoji catalog header"
            }
            val countLine = lines.getOrNull(4)?.takeIf { it.startsWith("# count=") }
                ?: throw IllegalArgumentException("missing emoji catalog count")
            val expectedCount = countLine.removePrefix("# count=").toIntOrNull()
                ?: throw IllegalArgumentException("invalid emoji catalog count")
            require(expectedCount in 1..MAX_ENTRIES) { "emoji catalog count outside bounds" }

            val rawEntries = lines.asSequence()
                .filter { it.isNotEmpty() && !it.startsWith('#') }
                .mapIndexed { index, line -> parseEntry(line, index + 1) }
                .toList()
            require(rawEntries.size == expectedCount) { "emoji catalog count mismatch" }
            require(rawEntries.map(RawEntry::sequence).toSet().size == rawEntries.size) {
                "duplicate emoji sequence"
            }

            val canonicalByFamily = rawEntries.groupBy(RawEntry::familyKey).mapValues { (_, family) ->
                family.firstOrNull { !containsSkinTone(it.sequence) } ?: family.first()
            }
            val entries = rawEntries.map { raw ->
                EmojiEntry(
                    sequence = raw.sequence,
                    name = raw.name,
                    category = raw.category,
                    subgroup = raw.subgroup,
                    keywords = immutableList(raw.keywords),
                    familyKey = raw.familyKey,
                    isCanonical = canonicalByFamily.getValue(raw.familyKey) === raw,
                )
            }
            return EmojiCatalog(entries)
        }

        fun normalizeQuery(value: String): String {
            val decomposed = Normalizer.normalize(value, Normalizer.Form.NFKD)
            return separators.replace(combiningMarks.replace(decomposed, ""), " ")
                .trim()
                .lowercase(Locale.ROOT)
        }

        private data class RawEntry(
            val sequence: String,
            val category: EmojiCategory,
            val subgroup: String,
            val familyKey: String,
            val name: String,
            val keywords: List<String>,
        )

        private fun parseEntry(line: String, lineNumber: Int): RawEntry {
            val fields = line.split('\t')
            require(fields.size == 6) { "emoji catalog line $lineNumber has ${fields.size} fields" }
            val sequenceCodepoints = parseCodepoints(fields[0], lineNumber)
            val familyCodepoints = parseCodepoints(fields[3], lineNumber)
            val calculatedFamily = sequenceCodepoints.filterNot { it == 0xFE0F || it in 0x1F3FB..0x1F3FF }
            require(calculatedFamily == familyCodepoints) { "emoji catalog line $lineNumber has invalid family" }
            val category = EmojiCategory.fromId(fields[1])
                ?: throw IllegalArgumentException("emoji catalog line $lineNumber has unknown category")
            require(fields[2].isNotBlank() && fields[2].length <= 128) { "invalid emoji subgroup" }
            require(fields[4].isNotBlank() && fields[4].length <= 256) { "invalid emoji name" }
            val keywords = fields[5].split(KEYWORD_SEPARATOR)
            require(keywords.size in 1..MAX_KEYWORDS && keywords.all { it.isNotBlank() && it.length <= 128 }) {
                "invalid emoji keywords"
            }
            require(keywords.distinct().size == keywords.size) { "duplicate emoji keyword" }
            return RawEntry(
                sequence = codepointString(sequenceCodepoints),
                category = category,
                subgroup = fields[2],
                familyKey = fields[3],
                name = fields[4],
                keywords = keywords,
            )
        }

        private fun parseCodepoints(field: String, lineNumber: Int): List<Int> {
            val parts = field.split(' ')
            require(parts.size in 1..MAX_SEQUENCE_CODEPOINTS && parts.none(String::isEmpty)) {
                "emoji catalog line $lineNumber has invalid sequence length"
            }
            return parts.map { value ->
                require(value.matches(Regex("[0-9A-F]{1,6}"))) { "invalid code point on emoji catalog line $lineNumber" }
                val codepoint = value.toInt(16)
                require(codepoint in 0..0x10FFFF && codepoint !in 0xD800..0xDFFF) {
                    "invalid Unicode scalar on emoji catalog line $lineNumber"
                }
                codepoint
            }
        }

        private fun codepointString(codepoints: List<Int>): String {
            val values = codepoints.toIntArray()
            return String(values, 0, values.size)
        }

        private fun containsSkinTone(value: String): Boolean =
            value.codePoints().anyMatch { it in 0x1F3FB..0x1F3FF }

        private fun readBoundedLines(reader: Reader): List<String> {
            val lines = mutableListOf<String>()
            val line = StringBuilder()
            var total = 0
            while (true) {
                val value = reader.read()
                if (value == -1) break
                total += 1
                require(total <= MAX_CATALOG_CHARS) { "emoji catalog exceeds character bound" }
                if (value.toChar() == '\n') {
                    lines += line.toString().removeSuffix("\r")
                    line.setLength(0)
                } else {
                    line.append(value.toChar())
                    require(line.length <= MAX_LINE_CHARS) { "emoji catalog line exceeds bound" }
                }
            }
            if (line.isNotEmpty()) lines += line.toString().removeSuffix("\r")
            return lines
        }

        private fun <T> immutableList(values: Collection<T>): List<T> =
            Collections.unmodifiableList(ArrayList(values))
    }
}
