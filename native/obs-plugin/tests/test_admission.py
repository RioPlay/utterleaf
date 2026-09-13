"""Explicit native DLL acceptance with disposable Windows child peers; no OBS."""
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import ctypes
import hmac
import json
from pathlib import Path
import secrets
import struct
import subprocess
import sys
import threading
import time
import unittest


def client(mode: str, session: bytes) -> None:
    from utterleaf import windows_pipe

    print("ready", flush=True)
    if sys.stdin.readline().strip() != "go":
        return
    pipe = None
    try:
        deadline = time.monotonic() + 8
        pipe = windows_pipe.connect(
            "\\\\.\\pipe\\Utterleaf.OBS." + session.hex(),
            cancelled=lambda: False, deadline=deadline,
        )
        if mode == "stall":
            print("connected", flush=True)
            sys.stdin.readline()
            return
        header = struct.pack("<4sBBH16s", b"ULAH", 1, 1, 0, session)
        hello = header + b"s" * 32  # Public fixture key, never a user credential.
        if mode == "partial":
            pipe.write_all(hello[:32], deadline=deadline)
            print("partial", flush=True)
            sys.stdin.readline()
            return
        if mode == "malformed":
            hello = b"FAIL" + hello[4:]
        pipe.write_all(hello, deadline=deadline)
        reply = bytearray()
        while len(reply) < 56:
            reply.extend(pipe.read(56 - len(reply), deadline=deadline))
        expected = struct.pack("<4sBBH16s", b"ULAH", 1, 2, 0, session)
        expected += hmac.digest(b"s" * 32,
                                b"Utterleaf OBS audio server ack v1\0" + header,
                                "sha256")
        print(json.dumps({"ack_valid": hmac.compare_digest(reply, expected)}), flush=True)
    except Exception:
        print(json.dumps({"ack_valid": False}), flush=True)
    finally:
        if pipe is not None:
            pipe.close()


class AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dll = ctypes.CDLL(str(DLL_PATH.resolve()))
        cls.dll.ul_admission_create.argtypes = [ctypes.c_ulong, ctypes.POINTER(ctypes.c_ubyte)]
        cls.dll.ul_admission_create.restype = ctypes.c_void_p
        cls.dll.ul_admission_authenticate.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        cls.dll.ul_admission_authenticate.restype = ctypes.c_int
        for name in ("cancel", "destroy"):
            fn = getattr(cls.dll, "ul_admission_" + name)
            fn.argtypes = [ctypes.c_void_p]
            fn.restype = None
        cls.dll.ul_admission_read_count.argtypes = [ctypes.c_void_p]
        cls.dll.ul_admission_read_count.restype = ctypes.c_ulong
        cls.dll.ul_admission_pipe.argtypes = [ctypes.c_void_p]
        cls.dll.ul_admission_pipe.restype = ctypes.c_void_p

    def setUp(self):
        self.children = []
        self.servers = []
        self.workers = []

    def tearDown(self):
        for server in self.servers:
            self.dll.ul_admission_cancel(server)
        for child in self.children:
            if child.poll() is None:
                child.terminate()
            child.communicate(timeout=10)
        for worker in self.workers:
            worker.join(10)
        # Never release storage still owned by a native pending operation.
        if any(worker.is_alive() for worker in self.workers):
            raise RuntimeError("Native cancellation failed to drain; process-level timeout required")
        for server in self.servers:
            self.dll.ul_admission_destroy(server)

    def child(self, mode: str, session: bytes):
        peer = subprocess.Popen(
            # Windows venv python.exe can be a launcher whose child opens the
            # pipe. Admission must bind to the actual OS process, so launch the
            # base interpreter directly; the scoped PYTHONPATH supplies source.
            [sys._base_executable, str(Path(__file__).resolve()), "--client", mode, session.hex()],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.children.append(peer)
        self.assertEqual(peer.stdout.readline().strip(), "ready")
        return peer

    def create(self, pid: int, session: bytes):
        identifier = (ctypes.c_ubyte * 16).from_buffer_copy(session)
        server = self.dll.ul_admission_create(pid, identifier)
        self.assertTrue(server)
        self.servers.append(server)
        return server

    def start(self, server, timeout=5000):
        result = []
        worker = threading.Thread(
            target=lambda: result.append(self.dll.ul_admission_authenticate(server, timeout)),
            daemon=True,
        )
        self.workers.append(worker)
        worker.start()
        return worker, result

    def result(self, worker, result):
        worker.join(10)
        self.assertFalse(worker.is_alive(), "Native authentication did not return")
        self.assertEqual(len(result), 1)
        return result[0]

    def go(self, peer):
        peer.stdin.write("go\n")
        peer.stdin.flush()

    def test_expected_process_gets_exact_ack_once(self):
        session = secrets.token_bytes(16)
        peer = self.child("valid", session)
        server = self.create(peer.pid, session)
        self.assertFalse(self.dll.ul_admission_pipe(server))
        worker, result = self.start(server)
        self.go(peer)
        self.assertEqual(self.result(worker, result), 0)
        self.assertEqual(json.loads(peer.stdout.readline()), {"ack_valid": True})
        self.assertEqual(self.dll.ul_admission_read_count(server), 56)
        self.assertTrue(self.dll.ul_admission_pipe(server))
        self.assertNotEqual(self.dll.ul_admission_authenticate(server, 500), 0)
        self.assertEqual(self.dll.ul_admission_read_count(server), 56)

    def test_other_process_is_rejected_before_read(self):
        session = secrets.token_bytes(16)
        expected = self.child("valid", session)
        stranger = self.child("valid", session)
        server = self.create(expected.pid, session)
        worker, result = self.start(server)
        self.go(stranger)
        self.assertEqual(self.result(worker, result), 1)
        self.assertEqual(self.dll.ul_admission_read_count(server), 0)
        self.assertFalse(self.dll.ul_admission_pipe(server))

    def test_cancel_after_authentication_prevents_new_pipe_borrow(self):
        session = secrets.token_bytes(16)
        peer = self.child("valid", session)
        server = self.create(peer.pid, session)
        worker, result = self.start(server)
        self.go(peer)
        self.assertEqual(self.result(worker, result), 0)
        self.assertTrue(self.dll.ul_admission_pipe(server))
        self.dll.ul_admission_cancel(server)
        self.assertFalse(self.dll.ul_admission_pipe(server))
        self.assertNotEqual(self.dll.ul_admission_authenticate(server, 500), 0)

    def test_exited_expected_process_cannot_be_replaced(self):
        session = secrets.token_bytes(16)
        expected = self.child("valid", session)
        server = self.create(expected.pid, session)
        expected.terminate()
        expected.wait(10)
        stranger = self.child("valid", session)
        worker, result = self.start(server)
        self.go(stranger)
        self.assertNotEqual(self.result(worker, result), 0)
        self.assertEqual(self.dll.ul_admission_read_count(server), 0)

    def test_cancel_before_connect_consumes_session(self):
        session = secrets.token_bytes(16)
        peer = self.child("valid", session)
        server = self.create(peer.pid, session)
        self.dll.ul_admission_cancel(server)
        worker, result = self.start(server)
        self.assertEqual(self.result(worker, result), 2)
        self.assertEqual(self.dll.ul_admission_read_count(server), 0)
        self.assertNotEqual(self.dll.ul_admission_authenticate(server, 500), 0)

    def test_connected_silent_client_times_out(self):
        session = secrets.token_bytes(16)
        peer = self.child("stall", session)
        server = self.create(peer.pid, session)
        worker, result = self.start(server, 800)
        self.go(peer)
        self.assertEqual(peer.stdout.readline().strip(), "connected")
        self.assertEqual(self.result(worker, result), 3)
        self.assertEqual(self.dll.ul_admission_read_count(server), 0)

    def test_no_connection_times_out_and_consumes_session(self):
        session = secrets.token_bytes(16)
        peer = self.child("valid", session)
        server = self.create(peer.pid, session)
        worker, result = self.start(server, 80)
        self.assertEqual(self.result(worker, result), 3)
        self.assertEqual(self.dll.ul_admission_read_count(server), 0)
        self.assertFalse(self.dll.ul_admission_pipe(server))
        self.assertNotEqual(self.dll.ul_admission_authenticate(server, 500), 0)

    def test_invalid_timeouts_consume_session_without_read(self):
        for timeout in (0, 30001):
            with self.subTest(timeout=timeout):
                session = secrets.token_bytes(16)
                peer = self.child("valid", session)
                server = self.create(peer.pid, session)
                self.assertEqual(self.dll.ul_admission_authenticate(server, timeout), 4)
                self.assertEqual(self.dll.ul_admission_read_count(server), 0)
                self.assertNotEqual(self.dll.ul_admission_authenticate(server, 500), 0)

    def test_cancel_partial_hello_drains_native_read(self):
        session = secrets.token_bytes(16)
        peer = self.child("partial", session)
        server = self.create(peer.pid, session)
        worker, result = self.start(server)
        self.go(peer)
        self.assertEqual(peer.stdout.readline().strip(), "partial")
        deadline = time.monotonic() + 2
        while self.dll.ul_admission_read_count(server) < 32 and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(self.dll.ul_admission_read_count(server), 32)
        self.dll.ul_admission_cancel(server)
        self.assertEqual(self.result(worker, result), 2)
        self.assertFalse(self.dll.ul_admission_pipe(server))

    def test_malformed_hello_is_terminal(self):
        session = secrets.token_bytes(16)
        peer = self.child("malformed", session)
        server = self.create(peer.pid, session)
        worker, result = self.start(server)
        self.go(peer)
        self.assertNotEqual(self.result(worker, result), 0)
        self.assertEqual(self.dll.ul_admission_read_count(server), 56)
        self.assertFalse(self.dll.ul_admission_pipe(server))

    def test_second_instance_cannot_take_name(self):
        session = secrets.token_bytes(16)
        peer = self.child("valid", session)
        self.create(peer.pid, session)
        identifier = (ctypes.c_ubyte * 16).from_buffer_copy(session)
        duplicate = self.dll.ul_admission_create(peer.pid, identifier)
        if duplicate:
            self.servers.append(duplicate)
        self.assertFalse(duplicate)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--client":
        client(sys.argv[2], bytes.fromhex(sys.argv[3]))
    else:
        if len(sys.argv) != 2:
            raise SystemExit("Supply the explicitly built admission test DLL path")
        DLL_PATH = Path(sys.argv.pop())
        unittest.main(verbosity=2)
