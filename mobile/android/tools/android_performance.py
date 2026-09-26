"""Normalize opt-in Android performance evidence without creating pass thresholds.

The instrumentation fixture writes one JSON object per logcat line after the
``UTTERLEAF_PERF_V1`` marker.  This tool keeps those on-device timestamps
separate from host metadata and produces reviewable raw and aggregate files.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import statistics
import subprocess
from pathlib import Path
from typing import Any, Iterable, Sequence


MARKER = "UTTERLEAF_PERF_V1 "
SCHEMA = "utterleaf.performance.v1"

# These are evidence-completeness requirements, not latency or memory limits.
EXACT_SAMPLE_COUNTS = {
    "keyboard_show_first_draw_proxy_first_ns": 1,
    "keyboard_show_first_draw_proxy_warm_ns": 30,
    "key_press_feedback_first_draw_proxy_ns": 30,
    "key_text_commit_ns": 30,
    "suggestion_generation_ns": 30,
    "suggestion_render_first_draw_proxy_ns": 30,
    "tools_switch_first_draw_proxy_ns": 30,
    "voice_capture_start_ns": 30,
    "voice_processing_first_decode_ns": 1,
    "voice_processing_followup_decode_ns": 5,
    "voice_result_local_callback_insert_ns": 30,
    "memory_idle_total_pss_kb": 1,
    "memory_after_typing_total_pss_kb": 1,
    "memory_after_voice_total_pss_kb": 1,
    "sustained_frames_over_refresh_period_count": 1,
}
MINIMUM_SAMPLE_COUNTS = {
    "memory_decode_total_pss_kb": 1,
    "sustained_frame_total_ns": 1,
    "sustained_input_interval_ns": 199,
}


class EvidenceError(ValueError):
    """The captured log cannot support a trustworthy baseline report."""


def _input_files(inputs: Sequence[Path]) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        if item.is_file():
            files.append(item)
        elif item.is_dir():
            raise EvidenceError(
                f"Choose exact logcat/UTP document files, not a directory that may duplicate records: {item}"
            )
        else:
            raise EvidenceError(f"Evidence input does not exist: {item}")
    return sorted(set(files))


def read_records(inputs: Sequence[Path]) -> list[dict[str, Any]]:
    """Extract marked JSON objects from plain logcat or UTP text/XML files."""

    records: list[dict[str, Any]] = []
    for path in _input_files(inputs):
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            raise EvidenceError(f"Could not read {path}: {error}") from error
        records.extend(parse_records_text(content, source=str(path)))
    if not records:
        raise EvidenceError("No UTTERLEAF_PERF_V1 records found")
    return records


def parse_records_text(content: str, *, source: str = "text") -> list[dict[str, Any]]:
    """Parse marked records from one text payload (also useful for unit tests)."""

    decoder = json.JSONDecoder()
    parsed: list[dict[str, Any]] = []
    # XML reports entity-escape logcat quotes.  raw_decode safely stops at any
    # surrounding XML or logcat suffix after the complete object.
    content = html.unescape(content)
    cursor = 0
    while True:
        marker = content.find(MARKER, cursor)
        if marker < 0:
            break
        candidate = content[marker + len(MARKER) :].lstrip()
        try:
            record, consumed = decoder.raw_decode(candidate)
        except json.JSONDecodeError as error:
            raise EvidenceError(f"Malformed performance record in {source}: {error}") from error
        if not isinstance(record, dict):
            raise EvidenceError(f"Performance record in {source} is not an object")
        parsed.append(record)
        cursor = marker + len(MARKER) + len(candidate[:consumed])
    return parsed


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise EvidenceError(f"{label} must be finite and non-negative")
    return number


def validate_records(records: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not records:
        raise EvidenceError("No performance records supplied")
    schemas = {record.get("schema") for record in records}
    if schemas != {SCHEMA}:
        raise EvidenceError(f"Expected only schema {SCHEMA}, found {sorted(map(str, schemas))}")
    run_ids = {record.get("run_id") for record in records}
    if len(run_ids) != 1 or None in run_ids or "" in run_ids:
        raise EvidenceError("Evidence must contain exactly one non-empty run_id")

    metadata_records = [record for record in records if record.get("kind") == "metadata"]
    if len(metadata_records) != 1:
        raise EvidenceError(f"Expected one metadata record, found {len(metadata_records)}")
    metadata = metadata_records[0]
    if metadata.get("clock") != "android.os.SystemClock.elapsedRealtimeNanos":
        raise EvidenceError("Instrumentation clock metadata is missing or unsupported")
    values = metadata.get("values")
    if not isinstance(values, dict):
        raise EvidenceError("Metadata values must be an object")
    required_metadata = {
        "package_name",
        "version_name",
        "version_code",
        "build_fingerprint",
        "device_model",
        "api_level",
        "supported_abis",
        "display_pixels",
        "density_dpi",
        "orientation",
        "refresh_rate_hz",
        "locale",
        "model_id",
        "model_sha256",
        "model_size_bytes",
        "audio_fixture_sha256",
        "suggestion_dictionary_sha256",
        "suggestion_dictionary_size_bytes",
        "suggestion_dictionary_word_count",
        "keyboard_options_canonical",
        "voice_hold_to_insert",
        "recorded_counts",
        "measurement_body_completed",
        "cleanup_completed",
    }
    missing_metadata = sorted(required_metadata - set(values))
    if missing_metadata:
        raise EvidenceError(f"Metadata is missing: {', '.join(missing_metadata)}")
    if values.get("measurement_body_completed") is not True:
        raise EvidenceError("Instrumentation did not complete its measurement body")
    if values.get("cleanup_completed") is not True:
        raise EvidenceError("Instrumentation did not complete state restoration and owned cleanup")
    if values.get("voice_hold_to_insert") is not False:
        raise EvidenceError("Voice hold mode must be disabled for comparable samples")

    samples = [record for record in records if record.get("kind") == "sample"]
    unexpected_kinds = sorted({str(record.get("kind")) for record in records} - {"metadata", "sample"})
    if unexpected_kinds:
        raise EvidenceError(f"Unexpected record kinds: {', '.join(unexpected_kinds)}")

    identities: set[tuple[str, int]] = set()
    units: dict[str, str] = {}
    counts: dict[str, int] = {}
    for sample in samples:
        metric = sample.get("metric")
        index = sample.get("index")
        unit = sample.get("unit")
        if not isinstance(metric, str) or not metric:
            raise EvidenceError("Every sample needs a non-empty metric")
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise EvidenceError(f"{metric} has an invalid index")
        identity = (metric, index)
        if identity in identities:
            raise EvidenceError(f"Duplicate sample {metric}[{index}]")
        identities.add(identity)
        if unit not in {"ns", "kb", "count"}:
            raise EvidenceError(f"{metric} has unsupported unit {unit!r}")
        if metric in units and units[metric] != unit:
            raise EvidenceError(f"{metric} mixes units {units[metric]!r} and {unit!r}")
        units[metric] = unit
        _finite_number(sample.get("value"), f"{metric}[{index}].value")
        elapsed = sample.get("elapsed_realtime_ns")
        start = sample.get("start_elapsed_realtime_ns")
        end = sample.get("end_elapsed_realtime_ns")
        if elapsed is not None:
            _finite_number(elapsed, f"{metric}[{index}].elapsed_realtime_ns")
        elif start is not None and end is not None:
            start_value = _finite_number(start, f"{metric}[{index}].start_elapsed_realtime_ns")
            end_value = _finite_number(end, f"{metric}[{index}].end_elapsed_realtime_ns")
            if end_value < start_value:
                raise EvidenceError(f"{metric}[{index}] ends before it starts")
            if abs((end_value - start_value) - float(sample["value"])) > 1.0:
                raise EvidenceError(f"{metric}[{index}] duration does not match its endpoints")
        else:
            raise EvidenceError(f"{metric}[{index}] needs a point timestamp or duration endpoints")
        counts[metric] = counts.get(metric, 0) + 1

    for metric, expected in EXACT_SAMPLE_COUNTS.items():
        actual = counts.get(metric, 0)
        if actual != expected:
            raise EvidenceError(f"{metric} expected {expected} samples, found {actual}")
    for metric, minimum in MINIMUM_SAMPLE_COUNTS.items():
        actual = counts.get(metric, 0)
        if actual < minimum:
            raise EvidenceError(f"{metric} expected at least {minimum} samples, found {actual}")
    for metric, count in counts.items():
        indices = sorted(index for sample_metric, index in identities if sample_metric == metric)
        if indices != list(range(count)):
            raise EvidenceError(f"{metric} sample indices are not contiguous from zero")

    claimed_counts = values.get("recorded_counts")
    if not isinstance(claimed_counts, dict):
        raise EvidenceError("recorded_counts must be an object")
    normalized_claims = {str(key): int(value) for key, value in claimed_counts.items()}
    if normalized_claims != counts:
        raise EvidenceError("Metadata recorded_counts does not match the sample records")
    return metadata, samples


def nearest_rank_p95(values: Sequence[float]) -> float:
    if not values:
        raise EvidenceError("Cannot summarize an empty sample set")
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def summarize(samples: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        grouped.setdefault(sample["metric"], []).append(sample)
    summary: dict[str, dict[str, Any]] = {}
    for metric, metric_samples in sorted(grouped.items()):
        values = [float(sample["value"]) for sample in metric_samples]
        summary[metric] = {
            "unit": metric_samples[0]["unit"],
            "n": len(values),
            "min": min(values),
            "median": statistics.median(values),
            "p95_nearest_rank": nearest_rank_p95(values),
            "max": max(values),
        }
    return summary


def _run(command: Sequence[str], cwd: Path | None = None) -> str | None:
    try:
        result = subprocess.run(
            list(command), cwd=cwd, check=True, capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def host_metadata(
    *, apk: Path | None = None, repo: Path | None = None, adb: Path | None = None,
    serial: str | None = None, command: str | None = None,
) -> dict[str, Any]:
    """Collect non-timing provenance; failures remain explicit nulls."""

    result: dict[str, Any] = {"instrumentation_command": command}
    if apk is not None:
        if not apk.is_file():
            raise EvidenceError(f"APK does not exist: {apk}")
        result["apk_path"] = str(apk.resolve())
        result["apk_size_bytes"] = apk.stat().st_size
        result["apk_sha256"] = _sha256(apk)
    if repo is not None:
        result["git_commit"] = _run(["git", "rev-parse", "HEAD"], repo)
        status = _run(["git", "status", "--porcelain"], repo)
        result["git_dirty"] = None if status is None else bool(status)
    if adb is not None:
        if not adb.is_file():
            raise EvidenceError(f"adb does not exist: {adb}")
        prefix = [str(adb)] + (["-s", serial] if serial else [])
        result["adb_version"] = _run([str(adb), "version"])
        properties = {
            "adb_build_fingerprint": "ro.build.fingerprint",
            "adb_avd_name": "ro.boot.qemu.avd_name",
            "adb_supported_abis": "ro.product.cpu.abilist",
            "adb_hardware_gpu": "ro.hardware.egl",
        }
        for key, prop in properties.items():
            result[key] = _run(prefix + ["shell", "getprop", prop])
        result["adb_serial"] = serial
    return result


def write_report(
    records: Sequence[dict[str, Any]], output: Path, *, host: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    payloads, aggregates = report_payloads(records, host=host)
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        (output / name).write_text(payload, encoding="utf-8")
    return aggregates


def report_payloads(
    records: Sequence[dict[str, Any]], *, host: dict[str, Any] | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Render report files without doing I/O, keeping formatting independently testable."""

    metadata, samples = validate_records(records)
    if host and host.get("adb_build_fingerprint"):
        device_fingerprint = metadata["values"]["build_fingerprint"]
        if host["adb_build_fingerprint"] != device_fingerprint:
            raise EvidenceError("Host adb fingerprint does not match instrumentation metadata")
    aggregates = summarize(samples)
    normalized = [metadata, *samples]
    raw = "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in normalized
    )
    merged_metadata = {
        "schema": SCHEMA,
        "run_id": metadata["run_id"],
        "clock": metadata["clock"],
        "device_and_fixture": metadata["values"],
        "host": host or {},
    }
    lines = [
        "# Utterleaf Android performance baseline",
        "",
        "All latency samples use Android elapsedRealtimeNanos boundaries. Values are descriptive;",
        "this report applies no performance pass/fail thresholds. First-draw metrics are UI draw",
        "proxies, not display-presentation timing or physical-phone evidence.",
        "",
        "| Metric | Unit | n | Min | Median | p95 (nearest rank) | Max |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for metric, item in aggregates.items():
        lines.append(
            f"| `{metric}` | {item['unit']} | {item['n']} | {item['min']:g} | "
            f"{item['median']:g} | {item['p95_nearest_rank']:g} | {item['max']:g} |"
        )
    return ({
        "raw.jsonl": raw,
        "metadata.json": json.dumps(merged_metadata, indent=2, sort_keys=True) + "\n",
        "summary.json": json.dumps(aggregates, indent=2, sort_keys=True) + "\n",
        "summary.md": "\n".join(lines) + "\n",
    }, aggregates)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True, help="UTP/logcat file or directory")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument(
        "--command",
        required=True,
        help="Exact emulator launch and instrumentation commands; metadata only",
    )
    return parser


def validate_host_provenance(host: dict[str, Any]) -> None:
    required = {
        "apk_sha256",
        "apk_size_bytes",
        "git_commit",
        "git_dirty",
        "adb_version",
        "adb_build_fingerprint",
        "adb_avd_name",
        "adb_supported_abis",
        "adb_serial",
        "instrumentation_command",
    }
    missing = sorted(key for key in required if host.get(key) is None or host.get(key) == "")
    if missing:
        raise EvidenceError(f"Host provenance is missing: {', '.join(missing)}")
    command = str(host["instrumentation_command"])
    if "-PutterleafPerformance=true" not in command:
        raise EvidenceError("Command provenance must show the explicit performance opt-in")
    if "-no-audio" not in command:
        raise EvidenceError("Command provenance must show the emulator's -no-audio launch constraint")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    records = read_records(args.input)
    host = host_metadata(
        apk=args.apk, repo=args.repo, adb=args.adb, serial=args.serial, command=args.command,
    )
    validate_host_provenance(host)
    write_report(records, args.output, host=host)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
