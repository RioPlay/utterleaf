"""Verify native runtime, PCM components and optional libobs with synthetic data."""
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build", type=Path, help="Reviewed development build for libobs dispatch checks")
    parser.add_argument("--headers", type=Path, help="Pinned public-header cache used by --build")
    parser.add_argument("--ui", action="store_true", help="Also run the bounded native dialog fixture (needs a Windows desktop)")
    args = parser.parse_args()
    if (args.build is None) != (args.headers is None):
        parser.error("--build and --headers must be supplied together")
    if sys.platform != "win32":
        raise SystemExit("These native admission checks require Windows")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # A failed rerun must not leave a previous passing receipt in place.
    receipt_path = output / "test-receipt.json"
    receipt_path.unlink(missing_ok=True)
    compiler = args.toolchain.resolve() / "bin/x86_64-w64-mingw32-clang.exe"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    commands = []
    logs = []
    sources = [ROOT / name for name in (
        "src/handshake.c", "src/handshake.h", "src/admission.c", "src/admission.h",
        "src/session_protocol.c", "src/session_protocol.h", "tests/session_protocol_test.c",
        "src/audio_protocol.c", "src/audio_protocol.h", "tests/audio_protocol_test.c",
        "tests/test_audio_protocol.py", "src/audio_queue.c", "src/audio_queue.h",
        "tests/audio_queue_test.c", "src/audio_convert.c", "src/audio_convert.h",
        "tests/audio_convert_test.c", "tests/audio_convert.def", "tests/test_audio_convert.py",
        "src/audio_capture.c", "src/audio_capture.h", "tests/audio_capture_test.c",
        "src/audio_stream.c", "src/audio_stream.h", "tests/audio_stream_test.c",
        "tests/audio_stream_routing_test.c",
        "src/audio_metadata.c", "src/audio_metadata.h", "tests/audio_metadata_test.c",
        "src/frontend_dispatch.c", "src/frontend_dispatch.h", "tests/frontend_dispatch_test.c",
        "tests/frontend_dispatch_fault_test.c",
        "tests/admission_io_test.c", "tests/admission_io_fault_test.c",
        "src/crypto.c", "src/crypto.h",
        "src/authorization.c", "src/authorization.h",
        "src/pairing_store.c", "src/pairing_store.h",
        "src/plugin_state.c", "src/plugin_state.h", "tests/plugin_state_test.c",
        "src/vendor_dispatch.c", "src/vendor_dispatch.h", "tests/vendor_dispatch_shim.c",
        "src/bridge.c", "tests/bridge_test.c",
        "src/pairing_ui.c", "src/pairing_ui.h", "src/bridge.rc", "src/bridge.manifest",
        "tests/pairing_ui_test.c", "tools/test_pairing_ui.py",
        "tests/vendor_dispatch.def", "tests/test_vendor_dispatch.py", "dependencies.json",
        "tests/handshake_test.c", "tests/handshake_failure_test.c",
        "tests/admission_identity_test.c",
        "tests/crypto_test.c", "tests/authorization_test.c",
        "tests/authorization.def", "tests/test_authorization.py",
        "tests/pairing_store_test.c", "tests/pairing_store.def", "tests/test_pairing_interop.py",
        "tests/admission.def", "tests/test_admission.py", "tools/test_native.py",
    )]
    source_hashes = {str(path.relative_to(ROOT)): digest(path) for path in sources}
    desktop_tests = (
        "tests/test_obs_audio_pipe.py", "tests/test_obs_audio_arm.py",
        "tests/test_obs_audio_disarm.py", "tests/test_obs_protocol.py", "tests/test_obs_session.py",
        "tests/test_obs_mix.py", "tests/test_obs_routing_protocol.py",
        "tests/test_obs_routing_session.py", "tests/test_obs_routing_store.py",
        "tests/test_obs_transcription_routing.py", "tests/test_obs_routing_pipe.py",
        "tests/test_obs_controller_routing.py",
        "tests/test_windows_pipe.py", "tests/test_obs_control_status.py",
        "tests/test_obs_control.py", "tests/test_obs_control_enrollment.py",
        "tests/test_obs_websocket.py", "tests/test_obs_websocket_disconnect.py",
        "tests/test_obs_controller.py", "tests/test_obs_transcription.py",
        "tests/test_capture_store.py", "tests/test_capture_store_live.py",
        "tests/test_continuous_capture.py", "tests/test_transcribe_limits.py",
        "tests/test_transcribe.py", "tests/test_transcript.py", "tests/test_file_streaming.py",
    )
    # The controller/recognizer now reaches model, configuration and hardware
    # helpers as well as the transport. Bind the small flat desktop source tree
    # so its transitive imports cannot silently escape this development receipt.
    def client_inputs():
        return sorted((REPO / "utterleaf").glob("*.py")) + [
            REPO / name for name in (*desktop_tests, "tests/windows_pipe_server.py")]

    client_sources = client_inputs()
    client_hashes = {str(path.relative_to(REPO)): digest(path) for path in client_sources}
    dispatch_inputs = {}
    if args.build is not None:
        build, headers = args.build.resolve(), args.headers.resolve()
        build_receipt_path = build / "build-receipt.json"
        build_receipt = json.loads(build_receipt_path.read_text(encoding="utf-8"))
        dispatch_inputs[build_receipt_path] = digest(build_receipt_path)
        # Bind dispatch to the same current source and verified public headers
        # as the linked DLL; no independent unreviewed SDK path is accepted.
        for name, expected in build_receipt["source"].items():
            path = (ROOT / name).resolve()
            if not path.is_relative_to(ROOT) or digest(path) != expected:
                raise ValueError("The reviewed development build source changed")
            dispatch_inputs[path] = expected
        lock = json.loads((ROOT / "dependencies.json").read_text(encoding="utf-8"))
        if build_receipt["inputs"] != lock["resources"]:
            raise ValueError("Build headers differ from the current dependency lock")
        for name, resource in lock["resources"].items():
            path = (headers / name).resolve()
            if (not path.is_relative_to(headers) or path.stat().st_size != resource["bytes"]
                    or digest(path) != resource["sha256"]):
                raise ValueError("A pinned dispatch header changed")
            dispatch_inputs[path] = resource["sha256"]
        runtime = Path(build_receipt["obs_runtime"]["path"]).resolve()
        dispatch_inputs[runtime] = build_receipt["obs_runtime"]["sha256"]
        for name in ("obsconfig.h", "libobs.dll.a"):
            dispatch_inputs[build / name] = build_receipt["generated"][name]
        if any(digest(path) != expected for path, expected in dispatch_inputs.items()):
            raise ValueError("A reviewed dispatch input changed")

    def run(name: str, arguments: list[str | Path], timeout: int = 60) -> None:
        command = [str(arg) for arg in arguments]
        commands.append(command)
        result = subprocess.run(command, cwd=output, env=env, capture_output=True,
                                text=True, timeout=timeout)
        log = result.stdout + result.stderr
        log_path = output / (name + ".log")
        log_path.write_text(log, encoding="utf-8")
        logs.append(log_path)
        if result.returncode:
            raise RuntimeError(f"{name} failed ({result.returncode}); see its local log")
        print(f"{name}: passed", flush=True)

    flags = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror"]
    fixed = output / "handshake_test.exe"
    fault = output / "handshake_failure_test.exe"
    dll = output / "utterleaf-admission-test.dll"
    identity = output / "admission_identity_test.exe"
    crypto = output / "crypto_test.exe"
    authorization_dll = output / "utterleaf-authorization-test.dll"
    authorization_state = output / "authorization_test.exe"
    pairing_dll = output / "utterleaf-pairing-store-test.dll"
    pairing_state = output / "pairing_store_test.exe"
    plugin_state = output / "plugin_state_test.exe"
    session_protocol = output / "session_protocol_test.exe"
    audio_protocol = output / "audio_protocol_test.exe"
    audio_queue = output / "audio_queue_test.exe"
    audio_stream = output / "audio_stream_test.exe"
    audio_stream_routing = output / "audio_stream_routing_test.exe"
    frontend_dispatch = output / "frontend_dispatch_test.exe"
    frontend_fault = output / "frontend_dispatch_fault_test.exe"
    admission_io = output / "admission_io_test.exe"
    admission_io_fault = output / "admission_io_fault_test.exe"
    run("compiler", [compiler, "--version"])
    run("desktop-audio-pipe-tests", [sys.executable, "-m", "pytest",
                                     *(REPO / name for name in desktop_tests)])
    run("audio-protocol-build", [*flags, ROOT / "src/audio_protocol.c",
                                  ROOT / "tests/audio_protocol_test.c", "-o", audio_protocol])
    # ULAP validation imports NumPy; retain the caller's desktop virtualenv.
    run("audio-protocol-interop", [sys.executable, ROOT / "tests/test_audio_protocol.py",
                                    "--executable", audio_protocol])
    run("audio-queue-build", [*flags, "-D_M_X64=100", ROOT / "tests/audio_queue_test.c",
                               "-o", audio_queue])
    run("audio-queue-test", [audio_queue])
    run("audio-stream-build", [*flags, "-D_M_X64=100",
                                 "-DUL_AUDIO_RUNTIME_VERSION=1",
                                 "-DUL_AUDIO_STREAM_FIRST_TIMEOUT_MS=60",
                                 "-DUL_AUDIO_STREAM_IDLE_TIMEOUT_MS=60",
                                 "-DUL_AUDIO_STREAM_WRITE_TIMEOUT_MS=40",
                                 "-DUL_AUDIO_STREAM_ACK_TIMEOUT_MS=40",
                                 "-DUL_AUDIO_STREAM_POLL_MS=1",
                                 "-DUL_AUDIO_STREAM_DRAIN_TIMEOUT_MS=100",
                                 ROOT / "src/audio_stream.c", ROOT / "src/audio_protocol.c",
                                 ROOT / "src/session_protocol.c", ROOT / "tests/audio_stream_test.c",
                                 "-o", audio_stream])
    run("audio-stream-test", [audio_stream])
    run("audio-stream-routing-build", [*flags, "-D_M_X64=100", "-DUL_AUDIO_RUNTIME_VERSION=2",
                                         "-DUL_AUDIO_STREAM_FIRST_TIMEOUT_MS=60",
                                         "-DUL_AUDIO_STREAM_IDLE_TIMEOUT_MS=60",
                                         "-DUL_AUDIO_STREAM_WRITE_TIMEOUT_MS=40",
                                         "-DUL_AUDIO_STREAM_ACK_TIMEOUT_MS=40",
                                         "-DUL_AUDIO_STREAM_POLL_MS=1",
                                         "-DUL_AUDIO_STREAM_DRAIN_TIMEOUT_MS=100",
                                         "-DUL_AUDIO_STREAM_METADATA_POLL_MS=1",
                                         ROOT / "src/audio_stream.c", ROOT / "src/audio_protocol.c",
                                         ROOT / "src/session_protocol.c",
                                         ROOT / "tests/audio_stream_routing_test.c",
                                         "-o", audio_stream_routing])
    run("audio-stream-routing-test", [audio_stream_routing])
    run("frontend-dispatch-build", [*flags, "-D_M_X64=100",
                                     ROOT / "src/frontend_dispatch.c",
                                     ROOT / "tests/frontend_dispatch_test.c", "-luser32",
                                     "-o", frontend_dispatch])
    run("frontend-dispatch-test", [frontend_dispatch])
    run("frontend-dispatch-fault-build", [*flags, "-D_M_X64=100",
                                           ROOT / "tests/frontend_dispatch_fault_test.c",
                                           "-luser32", "-o", frontend_fault])
    run("frontend-dispatch-fault-test", [frontend_fault])
    run("session-protocol-build", [*flags, ROOT / "src/session_protocol.c",
                                    ROOT / "tests/session_protocol_test.c", "-o", session_protocol])
    run("session-protocol-test", [session_protocol])
    run("admission-io-build", [*flags, "-D_M_X64=100", "-municode", ROOT / "src/admission.c",
                                ROOT / "src/crypto.c", ROOT / "src/handshake.c",
                                ROOT / "src/session_protocol.c",
                                ROOT / "tests/admission_io_test.c", "-ladvapi32", "-lbcrypt",
                                "-o", admission_io])
    run("admission-io-test", [admission_io])
    run("admission-io-fault-build", [*flags, "-D_M_X64=100", ROOT / "src/crypto.c",
                                      ROOT / "src/handshake.c",
                                      ROOT / "tests/admission_io_fault_test.c",
                                      "-ladvapi32", "-lbcrypt", "-o", admission_io_fault])
    run("admission-io-fault-test", [admission_io_fault])
    run("handshake-build", [*flags, ROOT / "src/crypto.c", ROOT / "src/handshake.c",
                           ROOT / "tests/handshake_test.c", "-lbcrypt", "-o", fixed])
    run("handshake-test", [fixed])
    run("crypto-build", [*flags, ROOT / "src/crypto.c", ROOT / "tests/crypto_test.c",
                          "-lbcrypt", "-o", crypto])
    run("crypto-test", [crypto])
    run("authorization-state-build", [*flags, ROOT / "tests/authorization_test.c",
                                       "-o", authorization_state])
    run("authorization-state-test", [authorization_state])
    run("plugin-state-build", [*flags, "-D_M_X64=100", ROOT / "tests/plugin_state_test.c",
                                ROOT / "src/session_protocol.c",
                                "-o", plugin_state])
    run("plugin-state-test", [plugin_state])
    functions = (
        "BCryptOpenAlgorithmProvider", "BCryptGetProperty", "BCryptCreateHash",
        "BCryptHashData", "BCryptFinishHash", "BCryptDestroyHash",
        "BCryptCloseAlgorithmProvider", "GetProcessHeap", "HeapAlloc", "HeapFree",
    )
    fault_obj = output / "handshake_failure.obj"
    crypto_fault_obj = output / "crypto_failure.obj"
    shim_obj = output / "handshake_shims.obj"
    run("crypto-fault-object", [*flags, *[f"-D{name}=shim_{name}" for name in functions],
                               "-c", ROOT / "src/crypto.c", "-o", crypto_fault_obj])
    run("handshake-fault-object", [*flags, "-c", ROOT / "src/handshake.c", "-o", fault_obj])
    run("handshake-fault-shims", [*flags, "-c", ROOT / "tests/handshake_failure_test.c",
                                 "-o", shim_obj])
    run("handshake-fault-link", [compiler, crypto_fault_obj, fault_obj, shim_obj, "-o", fault])
    run("handshake-fault-test", [fault])
    run("admission-identity-build", [*flags, ROOT / "src/crypto.c", ROOT / "tests/admission_identity_test.c",
                                     ROOT / "src/handshake.c", "-ladvapi32", "-lbcrypt",
                                     "-o", identity])
    run("admission-identity-test", [identity])
    run("admission-build", [*flags, "-shared", ROOT / "src/crypto.c", ROOT / "src/admission.c",
                            ROOT / "src/handshake.c", ROOT / "tests/admission.def",
                            "-ladvapi32", "-lbcrypt", "-o", dll])
    # The outer process timeout bounds fixture failures, including a stalled
    # native operation that must retain its OVERLAPPED buffers until completion.
    run("admission-test", [sys._base_executable, ROOT / "tests/test_admission.py", dll])
    run("authorization-build", [*flags, "-shared", ROOT / "src/crypto.c",
                                 ROOT / "src/authorization.c", ROOT / "src/admission.c",
                                 ROOT / "src/handshake.c", ROOT / "tests/authorization.def",
                                 "-ladvapi32", "-lbcrypt", "-o", authorization_dll])
    run("authorization-test", [sys._base_executable, ROOT / "tests/test_authorization.py",
                                authorization_dll])
    pairing_libraries = ["-lbcrypt", "-lcrypt32", "-ladvapi32", "-lshell32", "-lole32", "-luuid"]
    # The maintained state/fault fixture includes pairing_store.c directly for
    # test-only Win32 substitutions. The separate DLL compiles normal sources.
    run("pairing-state-build", [*flags, ROOT / "src/crypto.c", ROOT / "tests/pairing_store_test.c",
                                 *pairing_libraries, "-o", pairing_state])
    run("pairing-state-test", [pairing_state])
    run("pairing-build", [*flags, "-shared", ROOT / "src/crypto.c", ROOT / "src/pairing_store.c",
                           ROOT / "tests/pairing_store.def", *pairing_libraries, "-o", pairing_dll])
    run("pairing-interop-test", [sys._base_executable, ROOT / "tests/test_pairing_interop.py",
                                  pairing_dll, authorization_dll])
    artifacts = [fixed, fault, identity, dll, crypto, authorization_state, authorization_dll,
                 pairing_state, pairing_dll, plugin_state, session_protocol, admission_io,
                 admission_io_fault, audio_protocol, audio_queue, audio_stream, audio_stream_routing,
                 frontend_dispatch, frontend_fault]
    if args.build is not None:
        convert_stub = output / "audio_convert_stub_test.exe"
        convert_dll = output / "utterleaf-audio-convert-test.dll"
        convert_flags = [*flags, f"-I{headers / 'libobs'}", f"-I{build}"]
        run("audio-convert-stub-build", [*convert_flags, ROOT / "tests/audio_convert_test.c",
                                          "-o", convert_stub])
        run("audio-convert-stub-test", [convert_stub])
        run("audio-convert-libobs-build", [*convert_flags, "-DUL_AUDIO_CONVERT_REAL", "-shared",
                                            ROOT / "src/audio_convert.c",
                                            ROOT / "tests/audio_convert_test.c",
                                            ROOT / "tests/audio_convert.def", build / "libobs.dll.a",
                                            "-Wl,--exclude-all-symbols", "-o", convert_dll])
        run("audio-convert-libobs-test", [sys._base_executable, ROOT / "tests/test_audio_convert.py",
                                           runtime, convert_dll])
        artifacts.extend((convert_stub, convert_dll))
        capture_test = output / "audio_capture_test.exe"
        capture_flags = [*flags, "-D_M_X64=100", f"-I{headers / 'libobs'}",
                         f"-I{headers / 'frontend/api'}", f"-I{build}"]
        run("audio-capture-build", [*capture_flags, ROOT / "tests/audio_capture_test.c",
                                     ROOT / "src/audio_queue.c",
                                     "-o", capture_test])
        run("audio-capture-test", [capture_test])
        artifacts.append(capture_test)
        metadata_test = output / "audio_metadata_test.exe"
        run("audio-metadata-build", [*capture_flags, ROOT / "tests/audio_metadata_test.c",
                                      "-o", metadata_test])
        run("audio-metadata-test", [metadata_test])
        artifacts.append(metadata_test)
        bridge_test = output / "bridge_test.exe"
        run("bridge-wrapper-build", [*flags, "-D_M_X64=100", f"-I{headers / 'libobs'}",
                                     f"-I{headers / 'frontend/api'}", f"-I{headers / 'obs-websocket'}",
                                     f"-I{build}", ROOT / "tests/bridge_test.c", "-o", bridge_test])
        run("bridge-wrapper-test", [bridge_test])
        artifacts.append(bridge_test)
        vendor_dll = output / "utterleaf-vendor-test.dll"
        run("vendor-dispatch-build", [*flags, "-D_M_X64=100", "-shared",
                                      f"-I{headers / 'libobs'}", f"-I{build}",
                                      ROOT / "src/vendor_dispatch.c", ROOT / "tests/vendor_dispatch_shim.c",
                                      ROOT / "tests/vendor_dispatch.def", build / "libobs.dll.a",
                                      "-o", vendor_dll])
        run("vendor-dispatch-test", [sys._base_executable, ROOT / "tests/test_vendor_dispatch.py",
                                     runtime, vendor_dll])
        artifacts.append(vendor_dll)
    if args.ui:
        run("pairing-ui-acceptance", [sys._base_executable, ROOT / "tools/test_pairing_ui.py",
                                      "--toolchain", args.toolchain, "--output", output / "pairing-ui"], timeout=60)
        artifacts.append(output / "pairing-ui/pairing-ui-receipt.json")
    if source_hashes != {str(path.relative_to(ROOT)): digest(path) for path in sources}:
        raise RuntimeError("Source changed during native verification")
    if client_hashes != {str(path.relative_to(REPO)): digest(path) for path in client_inputs()}:
        raise RuntimeError("Client source changed during native verification")
    if any(digest(path) != expected for path, expected in dispatch_inputs.items()):
        raise RuntimeError("Reviewed dispatch inputs changed during verification")
    receipt = {
        "schema": 2, "scope": "pairing/admission/Arm/Disarm, read-only compatibility, desktop controller and live local recognition fixtures; optional libobs dispatch and synthetic capture/conversion; no OBS application, model loading or audio devices",
        "desktop_audio_pipe": "passed: Windows pipe, controller, transport, receiver, committed-window recognition, bounded model output and cancellation fixtures",
        "audio_stream": "passed: synthetic bounded transport fixture",
        "audio_metadata": "passed: bounded observation and lifecycle fixture" if args.build is not None else "not run: supply --build and --headers",
        "frontend_dispatch": "passed: real Windows message-only window fixture",
        "audio_capture": "passed: pinned public OBS SDK synthetic fixture" if args.build is not None else "not run: supply --build and --headers",
        "vendor_dispatch": "passed" if args.build is not None else "not run: supply --build and --headers",
        "audio_conversion": "passed: synthetic libobs and fault fixtures" if args.build is not None else "not run: supply --build and --headers",
        "native_dialog": "passed" if args.ui else "not run: supply --ui on a Windows desktop",
        "dispatch_inputs": {str(path): expected for path, expected in dispatch_inputs.items()},
        "sources": source_hashes, "client_sources": client_hashes,
        "compiler_sha256": digest(compiler),
        "artifacts": {str(path.relative_to(output)): digest(path) for path in artifacts},
        "logs": {path.name: digest(path) for path in logs},
        "commands": commands,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
