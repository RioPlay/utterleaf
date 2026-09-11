package org.utterleaf.keyboard.next.core

import android.os.Looper
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import android.icu.text.BreakIterator
import java.util.Locale
import java.util.ArrayDeque
import java.util.concurrent.atomic.AtomicReference

@JvmInline value class EditorSessionId(val value: Long)

/** Immutable permission to mutate exactly one revision of one editor session. */
data class EditorToken internal constructor(
    val session: EditorSessionId,
    val revision: Long,
    val privacyEpoch: Long,
    val policy: FieldPolicy,
)

enum class Outcome { APPLIED, STALE, REFUSED, UNAVAILABLE }
enum class SelectionUpdate { OWN_ACK, EXTERNAL, IGNORED }

fun interface MainThreadCheck { fun check() }

object AndroidMainThread : MainThreadCheck {
    override fun check() {
        check(Looper.myLooper() == Looper.getMainLooper()) { "EditorGateway must run on the main thread." }
    }
}

/**
 * The sole core owner of Android editor calls. Its callers receive tokens instead of
 * InputConnections, so delayed work cannot write a replacement editor.
 */
class EditorGateway(private val mainThread: MainThreadCheck = AndroidMainThread) {
    private var nextSession = 0L
    private var connection: InputConnection? = null
    private var state: State? = null
    private var manualIncognito = false
    private var privacyGeneration = 0L
    private val workerPermit = AtomicReference<EditorToken?>(null)

    private data class State(
        val session: EditorSessionId,
        val policy: FieldPolicy,
        val imeOptions: Int,
        var revision: Long,
        var selectionStart: Int,
        var selectionEnd: Int,
        var composingStart: Int = -1,
        var composingEnd: Int = -1,
        val expectedSelections: ArrayDeque<ExpectedSelection> = ArrayDeque(),
    )
    private data class ExpectedSelection(val start: Int, val end: Int, val composingStart: Int, val composingEnd: Int)

    fun open(
        connection: InputConnection?,
        inputType: Int?,
        imeOptions: Int,
        initialSelectionStart: Int,
        initialSelectionEnd: Int,
    ): EditorToken? {
        mainThread.check()
        retireInternal()
        if (connection == null) return null
        val policy = FieldPolicy.from(inputType, imeOptions)
        // N1 deliberately has no raw-terminal path.
        if (policy.raw) return null
        val opened = State(
            session = EditorSessionId(++nextSession),
            policy = policy,
            imeOptions = imeOptions,
            revision = 0L,
            selectionStart = initialSelectionStart,
            selectionEnd = initialSelectionEnd,
        )
        this.connection = connection
        state = opened
        return publishPermit(opened)
    }

    fun retire() {
        mainThread.check()
        retireInternal()
    }

    fun updateSelection(start: Int, end: Int, composingStart: Int, composingEnd: Int): SelectionUpdate {
        mainThread.check()
        val current = state ?: return SelectionUpdate.IGNORED
        val unchanged = current.selectionStart == start && current.selectionEnd == end &&
            current.composingStart == composingStart && current.composingEnd == composingEnd
        val matched = current.expectedSelections.firstOrNull {
            it.start == start && it.end == end && it.composingStart == composingStart && it.composingEnd == composingEnd
        }
        if (matched != null) {
            while (current.expectedSelections.isNotEmpty()) {
                val consumed = current.expectedSelections.removeFirst()
                if (consumed == matched) break
            }
            val predicted = current.expectedSelections.lastOrNull()
            current.selectionStart = predicted?.start ?: start
            current.selectionEnd = predicted?.end ?: end
            current.composingStart = predicted?.composingStart ?: composingStart
            current.composingEnd = predicted?.composingEnd ?: composingEnd
            return SelectionUpdate.OWN_ACK
        }
        if (unchanged) return SelectionUpdate.IGNORED
        current.selectionStart = start
        current.selectionEnd = end
        current.composingStart = composingStart
        current.composingEnd = composingEnd
        current.expectedSelections.clear()
        current.revision++
        publishPermit(current)
        return SelectionUpdate.EXTERNAL
    }

    fun setManualIncognito(enabled: Boolean) {
        mainThread.check()
        if (manualIncognito != enabled) {
            manualIncognito = enabled
            privacyGeneration++
            state?.let(::publishPermit) ?: workerPermit.set(null)
        }
    }

    fun currentToken(): EditorToken? {
        mainThread.check()
        return state?.let(::token)
    }

    fun currentPolicy(): FieldPolicy? {
        mainThread.check()
        return state?.policy
    }

    fun effectiveIncognito(): Boolean {
        mainThread.check()
        return manualIncognito || state?.policy?.forcedIncognito == true
    }

    fun commit(token: EditorToken, text: String): Outcome {
        mainThread.check()
        if (!isCurrent(token)) return Outcome.STALE
        if (text.isEmpty() || text.length > MAX_COMMIT_CODE_POINTS * 2 || !wellFormedUtf16(text) ||
            text.codePointCount(0, text.length) > MAX_COMMIT_CODE_POINTS) return Outcome.REFUSED
        val target = connection ?: return Outcome.UNAVAILABLE
        val captured = state ?: return Outcome.STALE
        return try {
            if (!target.commitText(text, 1)) Outcome.UNAVAILABLE
            else if (!stillCurrent(captured, target, token)) Outcome.STALE
            else advanceAfterCommit(captured, text)
        } catch (_: RuntimeException) {
            Outcome.UNAVAILABLE
        }
    }

    /**
     * Deletes through direct editor APIs. Sensitive fields never query surrounding
     * text: selected metadata deletes by replacement; a known collapsed caret deletes
     * one code point. Ordinary fields use a bounded character boundary and refuse
     * truncation/malformed input rather than guessing a grapheme boundary.
     */
    fun backspace(token: EditorToken): Outcome {
        mainThread.check()
        if (!isCurrent(token)) return Outcome.STALE
        val target = connection ?: return Outcome.UNAVAILABLE
        val current = state ?: return Outcome.STALE
        if (current.selectionStart < 0 || current.selectionEnd < 0) return Outcome.REFUSED
        return try {
            if (current.selectionStart != current.selectionEnd) {
                if (!target.commitText("", 1)) Outcome.UNAVAILABLE
                else if (!stillCurrent(current, target, token)) Outcome.STALE
                else advanceAfterCommit(current, "")
            } else if (!current.policy.permitsContext) {
                if (!target.deleteSurroundingTextInCodePoints(1, 0)) Outcome.UNAVAILABLE
                else if (!stillCurrent(current, target, token)) Outcome.STALE
                else advanceUnknownSelection(current)
            } else {
                val rawBefore = target.getTextBeforeCursor(MAX_DELETE_CONTEXT, 0) ?: return Outcome.UNAVAILABLE
                if (!stillCurrent(current, target, token)) return Outcome.STALE
                if (rawBefore.length >= MAX_DELETE_CONTEXT) return Outcome.REFUSED
                val before = rawBefore.toString()
                if (before.isEmpty() || before.length >= MAX_DELETE_CONTEXT || !wellFormedUtf16(before)) return Outcome.REFUSED
                val iterator = BreakIterator.getCharacterInstance(Locale.ROOT)
                iterator.setText(before)
                val end = iterator.last()
                val start = iterator.previous()
                if (start == BreakIterator.DONE || start >= end) return Outcome.REFUSED
                val codePoints = before.codePointCount(start, end)
                val utf16Count = end - start
                if (codePoints <= 0 || utf16Count <= 0 || current.selectionStart < utf16Count) return Outcome.REFUSED
                if (!target.deleteSurroundingTextInCodePoints(codePoints, 0)) Outcome.UNAVAILABLE
                else if (!stillCurrent(current, target, token)) Outcome.STALE
                else advanceAfterKnownDelete(current, current.selectionStart - utf16Count)
            }
        } catch (_: RuntimeException) {
            Outcome.UNAVAILABLE
        }
    }

    fun enter(token: EditorToken): Outcome {
        mainThread.check()
        if (!isCurrent(token)) return Outcome.STALE
        val target = connection ?: return Outcome.UNAVAILABLE
        val current = state ?: return Outcome.STALE
        val action = current.imeOptions and EditorInfo.IME_MASK_ACTION
        val actionAllowed = current.imeOptions and EditorInfo.IME_FLAG_NO_ENTER_ACTION == 0 && action in setOf(
            EditorInfo.IME_ACTION_GO, EditorInfo.IME_ACTION_SEARCH, EditorInfo.IME_ACTION_SEND,
            EditorInfo.IME_ACTION_NEXT, EditorInfo.IME_ACTION_DONE, EditorInfo.IME_ACTION_PREVIOUS,
        )
        return try {
            if (actionAllowed) {
                if (!target.performEditorAction(action)) Outcome.UNAVAILABLE
                else if (!stillCurrent(current, target, token)) Outcome.STALE
                else advanceUnknownSelection(current)
            } else if (target.commitText("\n", 1)) {
                if (!stillCurrent(current, target, token)) Outcome.STALE else advanceAfterCommit(current, "\n")
            } else {
                Outcome.UNAVAILABLE
            }
        } catch (_: RuntimeException) {
            Outcome.UNAVAILABLE
        }
    }

    /** Used by async ports before work and on their main-thread publication callback. */
    internal fun accepts(token: EditorToken, requireSuggestionPolicy: Boolean = false): Boolean {
        mainThread.check()
        return isCurrent(token) && (!requireSuggestionPolicy || token.policy.permitsSuggestions) && !effectiveIncognito()
    }

    /** Worker-safe immutable gate. It reads no editor connection or mutable session state. */
    internal fun workerPermits(token: EditorToken): Boolean =
        workerPermit.get() == token && token.policy.permitsSuggestions

    private fun isCurrent(token: EditorToken): Boolean {
        val current = state ?: return false
        return current.session == token.session && current.revision == token.revision &&
            token.privacyEpoch == privacyGeneration && current.policy == token.policy
    }

    private fun token(current: State) = EditorToken(
        session = current.session,
        revision = current.revision,
        privacyEpoch = privacyGeneration,
        policy = current.policy,
    )

    private fun advanceAfterCommit(current: State, text: String): Outcome {
        current.revision++
        if (current.selectionStart >= 0 && current.selectionEnd >= 0) {
            val next = minOf(current.selectionStart, current.selectionEnd) + text.length
            current.selectionStart = next
            current.selectionEnd = next
            recordExpected(current, next, next)
        }
        publishPermit(current)
        return Outcome.APPLIED
    }

    private fun advanceUnknownSelection(current: State): Outcome {
        current.revision++
        current.expectedSelections.clear()
        current.selectionStart = -1
        current.selectionEnd = -1
        current.composingStart = -1
        current.composingEnd = -1
        publishPermit(current)
        return Outcome.APPLIED
    }

    private fun advanceAfterKnownDelete(current: State, next: Int): Outcome {
        current.revision++
        current.selectionStart = next
        current.selectionEnd = next
        current.composingStart = -1
        current.composingEnd = -1
        recordExpected(current, next, next)
        publishPermit(current)
        return Outcome.APPLIED
    }

    private fun recordExpected(current: State, start: Int, end: Int) {
        if (current.expectedSelections.size == MAX_PENDING_SELECTION_ACKS) {
            current.expectedSelections.clear()
            current.selectionStart = -1
            current.selectionEnd = -1
            return
        }
        current.expectedSelections.addLast(ExpectedSelection(start, end, -1, -1))
    }

    private fun stillCurrent(captured: State, target: InputConnection, token: EditorToken): Boolean =
        state === captured && connection === target && isCurrent(token)

    private fun retireInternal() {
        connection = null
        state = null
        privacyGeneration++
        workerPermit.set(null)
    }

    private fun wellFormedUtf16(text: String): Boolean {
        var index = 0
        while (index < text.length) {
            val unit = text[index]
            if (unit.isHighSurrogate()) {
                if (index + 1 == text.length || !text[index + 1].isLowSurrogate()) return false
                index += 2
            } else {
                if (unit.isLowSurrogate()) return false
                index++
            }
        }
        return true
    }

    private fun publishPermit(current: State): EditorToken {
        val token = token(current)
        workerPermit.set(if (!manualIncognito && !current.policy.forcedIncognito) token else null)
        return token
    }

    private companion object {
        const val MAX_DELETE_CONTEXT = 128
        const val MAX_COMMIT_CODE_POINTS = 4096
        const val MAX_PENDING_SELECTION_ACKS = 16
    }
}
