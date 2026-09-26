package org.utterleaf.voice

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelPresentationTest {
    @Test fun catalogUsesDistinctEnglishNamesAndResourceOnlyTradeoffs() {
        val presentations = ModelStore.catalog.map { ModelPresentation.forSpec(it) }

        assertEquals(
            listOf("Compact English", "Medium English", "Large English"),
            presentations.map { it.name },
        )
        assertEquals(
            listOf("Lowest resource use", "Moderate resource use", "Highest resource use"),
            presentations.map { it.tradeoff },
        )
        assertEquals(
            listOf("77.7 MB", "148.0 MB", "487.6 MB"),
            ModelStore.catalog.map { ModelPresentation.sizeLabel(it.size) },
        )
    }

    @Test fun normalSummaryHidesImplementationDetailsUntilExplicitlyRequested() {
        ModelStore.catalog.forEach { spec ->
            val presentation = ModelPresentation.forSpec(spec)
            val summary = "${presentation.summary(spec)}\n${presentation.tradeoff}"

            assertFalse(summary.contains(spec.id))
            assertFalse(summary.contains(spec.filename))
            assertFalse(summary.contains(spec.sha256))

            val details = presentation.technicalDetails(spec)
            assertTrue(details.contains("Technical identifier: ${spec.id}"))
            assertTrue(details.contains("File name: ${spec.filename}"))
            assertTrue(details.contains("Expected size: ${spec.size} bytes"))
            assertTrue(details.contains("SHA-256: ${spec.sha256}"))
            assertTrue(details.contains("Storage: Utterleaf private app storage"))
        }
    }
}
