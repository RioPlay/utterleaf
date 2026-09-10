package org.utterleaf.voice

import java.io.File
import java.io.InputStream
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicBoolean

object WorkLease {
    private val busy = AtomicBoolean(false)
    fun acquire() = busy.compareAndSet(false, true)
    fun release() { busy.set(false) }
}

/** Only reviewed English GGML files reach native code. Imports never fetch a URL. */
object ModelStore {
    const val SIZE = 77704715L
    const val SHA256 = "921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f"
    const val URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin"
    data class Spec(val id: String, val size: Long, val sha256: String, val description: String) {
        val filename get() = "ggml-$id.bin"
        val url get() = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$filename"
    }
    // Verified against the publisher's raw Git LFS pointers, 2026-09-09:
    // https://huggingface.co/ggerganov/whisper.cpp/raw/main/ggml-{tiny,base,small}.en.bin
    val catalog = listOf(
        Spec("tiny.en", SIZE, SHA256, "Smallest download · a good starting point"),
        Spec("base.en", 147964211L, "a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002", "Larger model · more memory and processing"),
        Spec("small.en", 487614201L, "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d", "Largest option · best suited to more capable phones")
    )
    private const val SLOT_DIR = "models"
    private const val ACTIVE = "active-model"
    // Keep the original private path so upgrading preserves already verified tiny.en installs.
    private fun slot(directory: File, spec: Spec) = File(File(directory, SLOT_DIR), spec.filename)
    private fun active(directory: File) = File(directory, ACTIVE)
    fun file(directory: File): File {
        val id = active(directory).takeIf { it.isFile }?.readText()?.trim()
        val spec = catalog.singleOrNull { it.id == id }
        if (spec != null) {
            val candidate = slot(directory, spec)
            if (candidate.isFile && candidate.length() == spec.size) return candidate
            val legacy = File(directory, "tiny.en.bin")
            if (legacy.isFile && legacy.length() == spec.size) return legacy
            return candidate
        }
        return File(directory, "tiny.en.bin")
    }
    // Sizes are unique. This identifies a private, previously verified install; it is not
    // an import-validation substitute. External bytes always pass the full hash below.
    fun installed(directory: File): Spec? {
        val id = active(directory).takeIf { it.isFile }?.readText()?.trim()
        if (id != null) {
            val spec = catalog.singleOrNull { it.id == id }
            if (spec != null && file(directory).isFile && file(directory).length() == spec.size) return spec
            return null
        }
        return File(directory, "tiny.en.bin").takeIf { it.isFile }?.let { stored ->
            catalog.singleOrNull { it.size == stored.length() }
        }
    }
    fun ready(directory: File) = installed(directory) != null
    fun available(directory: File): List<Spec> = catalog.filter { spec ->
        val stored = slot(directory, spec)
        (stored.isFile && stored.length() == spec.size) ||
            (File(directory, "tiny.en.bin").isFile && File(directory, "tiny.en.bin").length() == spec.size)
    }
    @Synchronized fun select(directory: File, selected: Spec): Boolean {
        require(selected in catalog) { "Choose a supported English model." }
        val stored = slot(directory, selected)
        val legacy = File(directory, "tiny.en.bin")
        if (!((stored.isFile && stored.length() == selected.size) ||
                (legacy.isFile && legacy.length() == selected.size))) return false
        return publishActive(directory, selected)
    }
    @Synchronized fun remove(directory: File, selected: Spec): Boolean {
        require(selected in catalog) { "Choose a supported English model." }
        val isActive = active(directory).takeIf { it.isFile }?.readText()?.trim() == selected.id ||
            (active(directory).isFile.not() && installed(directory)?.id == selected.id)
        val stored = slot(directory, selected)
        val legacy = File(directory, "tiny.en.bin")
        val deleted = if (stored.exists()) stored.delete() else true
        // A legacy file can satisfy the same active ID; remove it too so deletion cannot revive it.
        val legacyDeleted = if (legacy.isFile && legacy.length() == selected.size) legacy.delete() else true
        // Keep an active pointer after deletion so readiness stays false instead of falling back.
        return deleted && legacyDeleted && (isActive || !stored.exists())
    }
    @Synchronized
    fun install(input: InputStream, directory: File, selected: Spec? = null): Spec {
        require(selected == null || selected in catalog) { "Choose a supported English model." }
        directory.mkdirs()
        val pending = File(directory, "model-import.tmp")
        try {
            val digest = MessageDigest.getInstance("SHA-256")
            var size = 0L
            pending.outputStream().use { out ->
                val buffer = ByteArray(65536)
                while (true) {
                    val n = input.read(buffer)
                    if (n < 0) break
                    size += n
                    require(size <= (selected?.size ?: catalog.maxOf { it.size })) { "Model exceeds the selected model size." }
                    digest.update(buffer, 0, n)
                    out.write(buffer, 0, n)
                }
                out.fd.sync()
            }
            val hash = digest.digest().joinToString("") { "%02x".format(it) }
            val spec = selected ?: catalog.singleOrNull { it.size == size }
            require(spec != null && size == spec.size && hash == spec.sha256) {
                "Model verification failed. Choose the original supported English GGML file."
            }
            val destination = slot(directory, spec)
            destination.parentFile.mkdirs()
            java.nio.file.Files.move(pending.toPath(), destination.toPath(),
                java.nio.file.StandardCopyOption.ATOMIC_MOVE, java.nio.file.StandardCopyOption.REPLACE_EXISTING)
            require(publishActive(directory, spec)) { "Could not select the verified model." }
            return spec
        } finally { pending.delete() }
    }
    private fun publishActive(directory: File, spec: Spec): Boolean {
        directory.mkdirs()
        val pending = File(directory, "$ACTIVE.tmp")
        return try {
            pending.outputStream().use { out ->
                out.write(spec.id.toByteArray())
                out.fd.sync()
            }
            java.nio.file.Files.move(pending.toPath(), active(directory).toPath(),
                java.nio.file.StandardCopyOption.ATOMIC_MOVE, java.nio.file.StandardCopyOption.REPLACE_EXISTING)
            true
        } finally { pending.delete() }
    }
}
