package org.utterleaf.voice

import java.util.Locale

/** User-facing copy for a reviewed model; the Spec remains the stable identity. */
internal data class ModelPresentation(
    val name: String,
    val tradeoff: String,
) {
    companion object {
        fun forSpec(spec: ModelStore.Spec) = when (spec.id) {
            "tiny.en" -> ModelPresentation("Compact English", "Lowest resource use")
            "base.en" -> ModelPresentation("Medium English", "Moderate resource use")
            "small.en" -> ModelPresentation("Large English", "Highest resource use")
            else -> ModelPresentation("English speech model", "Resource use varies")
        }

        fun sizeLabel(size: Long) = String.format(Locale.US, "%.1f MB", size / 1_000_000.0)
    }

    fun summary(spec: ModelStore.Spec) = "$name · ${sizeLabel(spec.size)}"

    fun technicalDetails(spec: ModelStore.Spec) = listOf(
        "Technical identifier: ${spec.id}",
        "Language: English",
        "Format: GGML",
        "File name: ${spec.filename}",
        "Expected size: ${spec.size} bytes",
        "SHA-256: ${spec.sha256}",
        "Storage: Utterleaf private app storage",
    ).joinToString("\n")
}
