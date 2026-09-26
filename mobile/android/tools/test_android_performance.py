import json
import unittest

import android_performance as performance


def metadata(run_id="run-1"):
    values = {
        "package_name": "org.utterleaf.voice",
        "version_name": "test",
        "version_code": 1,
        "build_fingerprint": "synthetic/fingerprint",
        "device_model": "emulator",
        "api_level": 35,
        "supported_abis": "x86_64",
        "display_pixels": "1080x2400",
        "density_dpi": 420,
        "orientation": "portrait",
        "refresh_rate_hz": 60.0,
        "locale": "en-US",
        "model_id": "tiny.en",
        "model_sha256": "0" * 64,
        "model_size_bytes": 77_704_715,
        "audio_fixture_sha256": "1" * 64,
        "suggestion_dictionary_sha256": "2" * 64,
        "suggestion_dictionary_size_bytes": 100,
        "suggestion_dictionary_word_count": 10,
        "keyboard_options_canonical": "KeyboardOptions(synthetic)",
        "voice_hold_to_insert": False,
        "measurement_body_completed": True,
        "cleanup_completed": True,
        "recorded_counts": {},
    }
    return {
        "schema": performance.SCHEMA,
        "kind": "metadata",
        "run_id": run_id,
        "clock": "android.os.SystemClock.elapsedRealtimeNanos",
        "values": values,
    }


def complete_records(run_id="run-1"):
    header = metadata(run_id)
    records = [header]
    counts = dict(performance.EXACT_SAMPLE_COUNTS)
    counts.update(performance.MINIMUM_SAMPLE_COUNTS)
    for metric, count in counts.items():
        unit = "kb" if "pss_kb" in metric else "count" if metric.endswith("_count") else "ns"
        for index in range(count):
            start = 1_000_000 + len(records) * 100
            value = index + 1
            records.append({
                "schema": performance.SCHEMA,
                "kind": "sample",
                "run_id": run_id,
                "record_id": f"{run_id}:{metric}:{index}",
                "metric": metric,
                "index": index,
                "value": value,
                "unit": unit,
                "elapsed_realtime_ns": start,
            })
    header["values"]["recorded_counts"] = counts
    return records


class AndroidPerformanceTest(unittest.TestCase):
    def test_reads_prefixed_and_xml_escaped_records(self):
        records = complete_records()
        lines = []
        for index, record in enumerate(records):
            encoded = json.dumps(record)
            if index == 0:
                encoded = encoded.replace('"', "&quot;")
            lines.append(f"09-26 I/UtterleafPerf: {performance.MARKER}{encoded} suffix")
        parsed = performance.parse_records_text("\n".join(lines))
        parsed_metadata, samples = performance.validate_records(parsed)
        self.assertEqual("run-1", parsed_metadata["run_id"])
        self.assertEqual(len(records) - 1, len(samples))

    def test_nearest_rank_and_median_are_explicit(self):
        values = list(range(1, 21))
        self.assertEqual(19, performance.nearest_rank_p95(values))
        samples = [
            {"metric": "m", "unit": "ns", "value": value}
            for value in [1, 2, 100, 101]
        ]
        summary = performance.summarize(samples)["m"]
        self.assertEqual(51.0, summary["median"])
        self.assertEqual(101, summary["p95_nearest_rank"])

    def test_writes_raw_metadata_and_summaries_without_thresholds(self):
        records = complete_records()
        payloads, _ = performance.report_payloads(records, host={"git_commit": "abc"})
        self.assertIn("raw.jsonl", payloads)
        self.assertEqual("abc", json.loads(payloads["metadata.json"])["host"]["git_commit"])
        summary = json.loads(payloads["summary.json"])
        self.assertEqual(30, summary["key_text_commit_ns"]["n"])
        markdown = payloads["summary.md"]
        self.assertIn("no performance pass/fail thresholds", markdown)
        self.assertIn("display-presentation", markdown)

    def test_rejects_mixed_runs_duplicate_samples_and_missing_counts(self):
        mixed = complete_records()
        mixed[-1]["run_id"] = "other"
        with self.assertRaisesRegex(performance.EvidenceError, "one non-empty run_id"):
            performance.validate_records(mixed)

        duplicate = complete_records()
        duplicate.append(dict(duplicate[-1]))
        duplicate[0]["values"]["recorded_counts"][duplicate[-1]["metric"]] += 1
        with self.assertRaisesRegex(performance.EvidenceError, "Duplicate sample"):
            performance.validate_records(duplicate)

        incomplete = complete_records()
        removed = incomplete.pop()
        incomplete[0]["values"]["recorded_counts"][removed["metric"]] -= 1
        with self.assertRaisesRegex(performance.EvidenceError, "expected at least"):
            performance.validate_records(incomplete)

    def test_rejects_malformed_record(self):
        with self.assertRaisesRegex(performance.EvidenceError, "Malformed"):
            performance.parse_records_text(performance.MARKER + "{not json}")

    def test_requires_completed_cleanup_and_exact_host_provenance(self):
        records = complete_records()
        records[0]["values"]["cleanup_completed"] = False
        with self.assertRaisesRegex(performance.EvidenceError, "state restoration"):
            performance.validate_records(records)

        host = {
            "apk_sha256": "a" * 64,
            "apk_size_bytes": 1,
            "git_commit": "b" * 40,
            "git_dirty": True,
            "adb_version": "Android Debug Bridge version 1",
            "adb_build_fingerprint": "synthetic/fingerprint",
            "adb_avd_name": "UtterleafFoundation35",
            "adb_supported_abis": "x86_64",
            "adb_serial": "emulator-5554",
            "instrumentation_command": "emulator -no-audio; gradlew -PutterleafPerformance=true",
        }
        performance.validate_host_provenance(host)
        host["instrumentation_command"] = "gradlew -PutterleafPerformance=true"
        with self.assertRaisesRegex(performance.EvidenceError, "-no-audio"):
            performance.validate_host_provenance(host)


if __name__ == "__main__":
    unittest.main()
