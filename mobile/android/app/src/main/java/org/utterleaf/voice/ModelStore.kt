package org.utterleaf.voice

import java.io.File
import java.io.InputStream
import java.security.MessageDigest
import java.util.LinkedHashMap
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.ThreadFactory
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

object WorkLease {
    private val busy = AtomicBoolean(false)
    fun acquire() = busy.compareAndSet(false, true)
    fun release() { busy.set(false) }
}

/** Only reviewed English GGML files whose bytes were verified in this process reach native code. */
object ModelStore {
    const val SIZE = 77704715L
    const val SHA256 = "921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f"
    const val URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin"
    data class Spec(val id: String, val size: Long, val sha256: String, val description: String) {
        val filename get() = "ggml-$id.bin"
        val url get() = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$filename"
    }
    sealed class Readiness {
        object Missing : Readiness()
        data class Checking(val spec: Spec?) : Readiness()
        data class Ready(val spec: Spec, val file: File) : Readiness()
        data class Invalid(val spec: Spec?) : Readiness()
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
    private const val LEGACY = "tiny.en.bin"
    private const val MAX_CACHE_ENTRIES = 24
    private const val MAX_PENDING_VERIFICATIONS = 16

    private data class Fingerprint(
        val path: String,
        val length: Long,
        val modified: Long,
        val specId: String,
    )
    private data class Candidate(
        val directory: File,
        val directoryKey: String,
        val spec: Spec,
        val file: File,
        val fingerprint: Fingerprint,
        val generation: Long,
    )
    private data class Flight(
        val fingerprint: Fingerprint,
        val generation: Long,
    )
    private sealed class ActiveCandidate {
        object Missing : ActiveCandidate()
        data class Invalid(val spec: Spec?) : ActiveCandidate()
        data class Present(val spec: Spec, val file: File) : ActiveCandidate()
    }
    private class Observation(val callback: (Readiness) -> Unit) : AutoCloseable {
        private var open = true

        @Synchronized fun deliver(current: () -> Readiness): Boolean {
            if (!open) return false
            return try {
                callback(current())
                true
            } catch (_: RuntimeException) {
                open = false
                false
            }
        }
        @Synchronized override fun close() { open = false }
    }

    private val mutationLock = Any()
    private val cacheLock = Any()
    private val verified = object : LinkedHashMap<Fingerprint, Boolean>(16, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<Fingerprint, Boolean>?) =
            size > MAX_CACHE_ENTRIES
    }
    private val inFlight = mutableSetOf<Flight>()
    private val generations = mutableMapOf<String, Long>()
    private val observers = mutableMapOf<String, MutableSet<Observation>>()
    private val verifier = ThreadPoolExecutor(
        1, 1, 0L, TimeUnit.MILLISECONDS,
        ArrayBlockingQueue<Runnable>(MAX_PENDING_VERIFICATIONS),
        ThreadFactory { task -> Thread(task, "utterleaf-model-verify").apply { isDaemon = true } },
        ThreadPoolExecutor.AbortPolicy(),
    )

    private fun slot(directory: File, spec: Spec) = File(File(directory, SLOT_DIR), spec.filename)
    private fun legacy(directory: File) = File(directory, LEGACY)
    private fun active(directory: File) = File(directory, ACTIVE)
    private fun canonical(file: File) = try { file.canonicalFile } catch (_: Exception) { file.absoluteFile }
    private fun directoryKey(directory: File) = canonical(directory).path
    private fun pathKey(file: File) = canonical(file).path

    /** Storage-path compatibility helper. A caller must not pass its result to native code. */
    fun file(directory: File): File {
        val id = activeId(directory)
        val spec = catalog.singleOrNull { it.id == id }
        if (spec != null) {
            val candidate = slot(directory, spec)
            if (candidate.isFile && candidate.length() == spec.size) return candidate
            val old = legacy(directory)
            if (old.isFile && old.length() == spec.size) return old
            return candidate
        }
        return legacy(directory)
    }

    /** Fast active-model state. Unknown bytes start one coalesced background verification. */
    fun readiness(directory: File): Readiness = currentReadiness(directory, schedule = true)

    private fun currentReadiness(directory: File, schedule: Boolean): Readiness = when (val current = resolveActive(directory)) {
        ActiveCandidate.Missing -> Readiness.Missing
        is ActiveCandidate.Invalid -> Readiness.Invalid(current.spec)
        is ActiveCandidate.Present -> readinessFor(directory, current.spec, current.file, schedule)
    }

    /** Passive per-model state for setup/chooser rendering; never starts hashing. */
    fun storedReadiness(directory: File, spec: Spec): Readiness {
        require(spec in catalog) { "Choose a supported English model." }
        val candidate = candidateForSpec(directory, spec)
        if (candidate == null) return if (hasStoredFile(directory, spec)) Readiness.Invalid(spec) else Readiness.Missing
        return readinessFor(directory, spec, candidate, schedule = false)
    }

    fun verifiedFile(directory: File): File? = (readiness(directory) as? Readiness.Ready)?.file
    fun installed(directory: File): Spec? = (readiness(directory) as? Readiness.Ready)?.spec
    fun ready(directory: File) = readiness(directory) is Readiness.Ready

    /** Only already-verified entries are exposed. This method never starts background I/O. */
    fun available(directory: File): List<Spec> = catalog.filter { spec ->
        val stored = candidateForSpec(directory, spec) ?: return@filter false
        val candidate = snapshot(directory, spec, stored) ?: return@filter false
        cached(candidate) == true
    }

    /** Metadata-only presence for recovery UI. Presence is never evidence of trust. */
    fun hasStoredFile(directory: File, spec: Spec): Boolean {
        require(spec in catalog) { "Choose a supported English model." }
        if (slot(directory, spec).isFile) return true
        val old = legacy(directory)
        if (!old.isFile) return false
        val matching = catalog.singleOrNull { it.size == old.length() }
        return matching == spec || (matching == null && spec == catalog.first())
    }

    /** Explicit expanded-chooser scan. Calls are coalesced and the executor queue is bounded. */
    fun verifyAvailableAsync(directory: File) {
        var shouldNotify = false
        catalog.forEach { spec ->
            val candidate = candidateForSpec(directory, spec)
            if (candidate != null) {
                val value = readinessFor(directory, spec, candidate, schedule = true)
                shouldNotify = shouldNotify || value !is Readiness.Ready
            } else if (hasStoredFile(directory, spec)) shouldNotify = true
        }
        if (shouldNotify) notifyObservers(directory)
    }

    fun observe(directory: File, callback: (Readiness) -> Unit): AutoCloseable {
        val key = directoryKey(directory)
        val observer = Observation(callback)
        synchronized(cacheLock) { observers.getOrPut(key) { mutableSetOf() }.add(observer) }
        // Resolve state only after entering this observer's delivery gate. A delayed notification
        // therefore cannot replay an older snapshot after a newer one. Hashing starts outside it.
        if (!observer.deliver { currentReadiness(directory, schedule = false) }) removeObserver(key, observer)
        else readiness(directory)
        return AutoCloseable {
            observer.close()
            removeObserver(key, observer)
        }
    }

    fun select(directory: File, selected: Spec): Boolean {
        require(selected in catalog) { "Choose a supported English model." }
        if (verifiedCandidate(directory, selected) == null) return false
        val published = synchronized(mutationLock) {
            // Re-resolve after waiting for a concurrent import/remove.
            verifiedCandidate(directory, selected)?.let { publishActive(directory, selected) } == true
        }
        if (published) notifyObservers(directory)
        return published
    }

    fun remove(directory: File, selected: Spec): Boolean {
        require(selected in catalog) { "Choose a supported English model." }
        val removedPaths = mutableListOf<File>()
        val success = synchronized(mutationLock) {
            val stored = slot(directory, selected)
            val old = legacy(directory)
            val pointer = activeId(directory)
            val legacySpec = old.takeIf { it.isFile }?.let { file ->
                catalog.singleOrNull { it.size == file.length() }
            }
            val removeLegacy = old.isFile && if (legacySpec != null) {
                legacySpec == selected
            } else {
                pointer == selected.id || (pointer == null && selected == catalog.first())
            }
            val storedDeleted = if (stored.exists()) stored.delete().also { if (it) removedPaths += stored } else true
            val legacyDeleted = if (removeLegacy) old.delete().also { if (it) removedPaths += old } else true
            storedDeleted && legacyDeleted
        }
        removedPaths.forEach(::invalidatePath)
        notifyObservers(directory)
        return success
    }

    fun install(input: InputStream, directory: File, selected: Spec? = null): Spec {
        require(selected == null || selected in catalog) { "Choose a supported English model." }
        val installed = synchronized(mutationLock) {
            directory.mkdirs()
            val pending = File(directory, "model-import.tmp")
            try {
                val digest = MessageDigest.getInstance("SHA-256")
                var size = 0L
                pending.outputStream().use { out ->
                    val buffer = ByteArray(65536)
                    try {
                        while (true) {
                            val n = input.read(buffer)
                            if (n < 0) break
                            size += n
                            require(size <= (selected?.size ?: catalog.maxOf { it.size })) {
                                "Model exceeds the selected model size."
                            }
                            digest.update(buffer, 0, n)
                            out.write(buffer, 0, n)
                        }
                        out.fd.sync()
                    } finally { buffer.fill(0) }
                }
                val hash = digest.digest().joinToString("") { "%02x".format(it) }
                val spec = selected ?: catalog.singleOrNull { it.size == size }
                require(spec != null && size == spec.size && hash == spec.sha256) {
                    "Model verification failed. Choose the original supported English GGML file."
                }
                val destination = slot(directory, spec)
                checkNotNull(destination.parentFile).mkdirs()
                java.nio.file.Files.move(
                    pending.toPath(), destination.toPath(),
                    java.nio.file.StandardCopyOption.ATOMIC_MOVE,
                    java.nio.file.StandardCopyOption.REPLACE_EXISTING,
                )
                invalidatePath(destination)
                seedVerified(directory, spec, destination)
                require(publishActive(directory, spec)) { "Could not select the verified model." }
                spec
            } finally { pending.delete() }
        }
        notifyObservers(directory)
        return installed
    }

    private fun readinessFor(directory: File, spec: Spec, stored: File, schedule: Boolean): Readiness {
        val candidate = snapshot(directory, spec, stored) ?: return Readiness.Invalid(spec)
        return when (cached(candidate)) {
            true -> Readiness.Ready(spec, candidate.file)
            false -> Readiness.Invalid(spec)
            null -> {
                if (schedule) schedule(candidate)
                Readiness.Checking(spec)
            }
        }
    }

    private fun resolveActive(directory: File): ActiveCandidate {
        val pointer = active(directory)
        if (pointer.isFile) {
            val spec = catalog.singleOrNull { it.id == activeId(directory) }
                ?: return ActiveCandidate.Invalid(null)
            return candidateForSpec(directory, spec)?.let { ActiveCandidate.Present(spec, it) }
                ?: if (hasStoredFile(directory, spec)) ActiveCandidate.Invalid(spec) else ActiveCandidate.Missing
        }
        val old = legacy(directory)
        if (!old.isFile) return ActiveCandidate.Missing
        val spec = catalog.singleOrNull { it.size == old.length() } ?: return ActiveCandidate.Invalid(null)
        return ActiveCandidate.Present(spec, old)
    }

    private fun candidateForSpec(directory: File, spec: Spec): File? {
        val stored = slot(directory, spec)
        if (stored.isFile && stored.length() == spec.size) return stored
        val old = legacy(directory)
        if (old.isFile && old.length() == spec.size) return old
        return null
    }

    private fun verifiedCandidate(directory: File, spec: Spec): File? {
        val stored = candidateForSpec(directory, spec) ?: return null
        val candidate = snapshot(directory, spec, stored) ?: return null
        return if (cached(candidate) == true) candidate.file else null
    }

    private fun snapshot(directory: File, spec: Spec, stored: File): Candidate? {
        if (!stored.isFile || stored.length() != spec.size) return null
        val resolvedDirectory = canonical(directory)
        val resolvedFile = canonical(stored)
        val path = resolvedFile.path
        val fingerprint = Fingerprint(path, resolvedFile.length(), resolvedFile.lastModified(), spec.id)
        if (!resolvedFile.isFile || fingerprint.length != spec.size) return null
        return synchronized(cacheLock) {
            Candidate(
                resolvedDirectory, resolvedDirectory.path, spec, resolvedFile, fingerprint,
                generations[path] ?: 0L,
            )
        }
    }

    private fun cached(candidate: Candidate): Boolean? = synchronized(cacheLock) {
        if (candidate.generation != (generations[candidate.fingerprint.path] ?: 0L)) null
        else verified[candidate.fingerprint]
    }

    private fun schedule(candidate: Candidate) {
        val flight = Flight(candidate.fingerprint, candidate.generation)
        val submit = synchronized(cacheLock) {
            if (verified.containsKey(candidate.fingerprint) || !inFlight.add(flight)) false else true
        }
        if (!submit) return
        try {
            verifier.execute { verify(candidate) }
        } catch (_: RejectedExecutionException) {
            synchronized(cacheLock) { inFlight.remove(flight) }
        }
    }

    private fun verify(candidate: Candidate) {
        val matches = try { sha256(candidate.file) == candidate.spec.sha256 } catch (_: Exception) { false }
        val current = snapshot(candidate.directory, candidate.spec, candidate.file)
        val flight = Flight(candidate.fingerprint, candidate.generation)
        synchronized(cacheLock) {
            inFlight.remove(flight)
            if (current != null && current.fingerprint == candidate.fingerprint &&
                current.generation == candidate.generation &&
                candidate.generation == (generations[candidate.fingerprint.path] ?: 0L)
            ) verified[candidate.fingerprint] = matches
        }
        notifyObservers(candidate.directory)
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(65536)
            try {
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    digest.update(buffer, 0, count)
                }
            } finally { buffer.fill(0) }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    private fun seedVerified(directory: File, spec: Spec, stored: File) {
        val candidate = snapshot(directory, spec, stored) ?: return
        synchronized(cacheLock) { verified[candidate.fingerprint] = true }
    }

    private fun invalidatePath(file: File) {
        val path = pathKey(file)
        synchronized(cacheLock) {
            generations[path] = (generations[path] ?: 0L) + 1L
            verified.keys.removeAll { it.path == path }
            inFlight.removeAll { it.fingerprint.path == path }
        }
    }

    private fun notifyObservers(directory: File) {
        val key = directoryKey(directory)
        val recipients = synchronized(cacheLock) { observers[key]?.toList().orEmpty() }
        if (recipients.isEmpty()) return
        recipients.forEach { observer ->
            if (!observer.deliver { currentReadiness(directory, schedule = false) }) removeObserver(key, observer)
        }
        // A callback may have changed the active model; schedule any now-needed verification only
        // after all callback gates have been released.
        readiness(directory)
    }

    private fun removeObserver(key: String, observer: Observation) {
        synchronized(cacheLock) {
            observers[key]?.let { values ->
                values.remove(observer)
                if (values.isEmpty()) observers.remove(key)
            }
        }
    }

    private fun activeId(directory: File): String? {
        val pointer = active(directory)
        if (!pointer.isFile) return null
        return try {
            pointer.inputStream().buffered().use { input ->
                val bytes = ByteArray(129)
                val count = input.read(bytes)
                if (count <= 0 || count > 128 || input.read() >= 0) null
                else bytes.copyOf(count).toString(Charsets.UTF_8).trim().takeIf { it.isNotEmpty() }
            }
        } catch (_: Exception) { null }
    }

    private fun publishActive(directory: File, spec: Spec): Boolean {
        directory.mkdirs()
        val pending = File(directory, "$ACTIVE.tmp")
        return try {
            pending.outputStream().use { out ->
                out.write(spec.id.toByteArray())
                out.fd.sync()
            }
            java.nio.file.Files.move(
                pending.toPath(), active(directory).toPath(),
                java.nio.file.StandardCopyOption.ATOMIC_MOVE,
                java.nio.file.StandardCopyOption.REPLACE_EXISTING,
            )
            true
        } finally { pending.delete() }
    }
}
