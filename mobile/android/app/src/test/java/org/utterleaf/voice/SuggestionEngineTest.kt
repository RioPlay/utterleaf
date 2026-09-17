package org.utterleaf.voice

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SuggestionEngineTest {
    private val engine = SuggestionEngine(listOf(
        "the", "there", "their", "they", "hello", "help", "hell", "helping", "world"))

    @Test fun completionsFollowFrequencyRank() {
        assertEquals(listOf("hello", "help", "hell"), engine.completions("hel"))
    }

    @Test fun composingCaseIsPreserved() {
        assertEquals(listOf("Hello", "Help", "Hell"), engine.completions("Hel"))
        assertEquals(listOf("HELLO", "HELP", "HELL"), engine.completions("HEL"))
    }

    @Test fun exactWordIsExcludedButLongerWordsRemain() {
        assertEquals(listOf("there", "their", "they"), engine.completions("the"))
    }

    @Test fun nonLettersAndBoundsRefuse() {
        assertTrue(engine.completions("").isEmpty())
        assertTrue(engine.completions("hél").isEmpty())
        assertTrue(engine.completions("hel1").isEmpty())
        assertTrue(engine.completions("a".repeat(33)).isEmpty())
        assertTrue(engine.completions("zzzz").isEmpty())
    }

    @Test fun maxBoundsResults() {
        assertEquals(3, engine.completions("hel", 3).size)
        assertEquals(2, engine.completions("hel", 2).size)
    }
}
