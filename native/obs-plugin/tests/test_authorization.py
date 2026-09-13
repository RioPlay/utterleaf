"""Capability proof through native admission to disposable Windows peers."""
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import secrets
import sys
import time
import unittest

import test_admission as _admission
from utterleaf.obs_authorization import create_prepare_proof

KEY = b"k" * 32  # Public fixture capability.
BytePointer = ctypes.POINTER(ctypes.c_ubyte)


def buffer(data):
    return (ctypes.c_ubyte * len(data)).from_buffer_copy(data)


class Options(ctypes.Structure):
    _fields_ = [("client_pid", ctypes.c_ulong), ("session", ctypes.c_ubyte * 16),
                ("additional_mix_mask", ctypes.c_ubyte)]


class AuthorizationTests(_admission.AdmissionTests):
    @classmethod
    def setUpClass(cls):
        _admission.DLL_PATH = DLL_PATH
        super().setUpClass()
        signatures = {
            "create": ([BytePointer], ctypes.c_void_p),
            "issue": ([ctypes.c_void_p, ctypes.c_ulong, BytePointer, ctypes.c_ubyte, BytePointer], ctypes.c_bool),
            "prepare": ([ctypes.c_void_p, BytePointer, ctypes.c_size_t, BytePointer,
                         ctypes.c_size_t, ctypes.POINTER(Options)], ctypes.c_void_p),
            "is_active": ([ctypes.c_void_p], ctypes.c_bool),
            "revoke": ([ctypes.c_void_p], None),
            "release": ([ctypes.c_void_p], None),
            "destroy": ([ctypes.c_void_p], None),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(cls.dll, "ul_authorizer_" + name)
            fn.argtypes, fn.restype = args, result

    def setUp(self):
        super().setUp()
        self.authorizers = []

    def tearDown(self):
        for auth in self.authorizers:
            self.dll.ul_authorizer_revoke(auth)
        # This terminates peers and joins workers. If a worker fails to drain,
        # never free its storage: propagate to the enclosing process timeout.
        super().tearDown()
        for auth in self.authorizers:
            self.dll.ul_authorizer_destroy(auth)

    def authorizer(self):
        auth = self.dll.ul_authorizer_create(buffer(KEY))
        self.assertTrue(auth)
        self.authorizers.append(auth)
        return auth

    def issue(self, auth, pid, session, mask=9):
        output = buffer(b"\xa5" * 60)
        valid = self.dll.ul_authorizer_issue(auth, pid, buffer(session), mask, output)
        if not valid:
            self.assertEqual(bytes(output), b"\0" * 60)
            return None
        return bytes(output)

    def signed(self, challenge, pid, session, mask=9):
        return create_prepare_proof(KEY, challenge, client_pid=pid,
                                    session_id=session, additional_mix_mask=mask)

    def prepare(self, auth, challenge, proof):
        options = Options()
        ctypes.memset(ctypes.byref(options), 0xA5, ctypes.sizeof(options))
        server = self.dll.ul_authorizer_prepare(auth, buffer(challenge), len(challenge),
                                                buffer(proof), len(proof), ctypes.byref(options))
        if not server:
            self.assertEqual(bytes(options), b"\0" * ctypes.sizeof(options))
        # Borrowed: only the authorizer destroys this admission, not base tearDown.
        return server, options

    def request(self, mode="valid"):
        session = secrets.token_bytes(16)
        peer = self.child(mode, session)
        auth = self.authorizer()
        challenge = self.issue(auth, peer.pid, session)
        self.assertIsNotNone(challenge)
        return auth, peer, session, challenge, self.signed(challenge, peer.pid, session)

    def test_authorizer_valid_proof_reaches_exact_peer_once(self):
        auth, peer, session, challenge, proof = self.request()
        self.assertFalse(self.dll.ul_authorizer_is_active(auth))
        server, options = self.prepare(auth, challenge, proof)
        self.assertTrue(server)
        self.assertEqual((options.client_pid, bytes(options.session), options.additional_mix_mask),
                         (peer.pid, session, 9))
        self.assertTrue(self.dll.ul_authorizer_is_active(auth))
        self.assertFalse(self.prepare(auth, challenge, proof)[0])
        self.assertIsNone(self.issue(auth, peer.pid, session))
        worker, result = self.start(server)
        self.go(peer)
        self.assertEqual(self.result(worker, result), 0)
        self.assertEqual(json.loads(peer.stdout.readline()), {"ack_valid": True})
        self.assertEqual(self.dll.ul_admission_read_count(server), 56)
        self.dll.ul_authorizer_release(auth)
        self.assertFalse(self.dll.ul_authorizer_is_active(auth))
        self.assertFalse(self.prepare(auth, challenge, proof)[0])
        fresh = self.issue(auth, peer.pid, session)
        self.assertIsNotNone(fresh)
        self.assertNotEqual(fresh, challenge)

    def test_authorizer_bad_proof_consumes_attempt(self):
        auth, _peer, _session, challenge, proof = self.request()
        wrong = bytes([proof[0] ^ 1]) + proof[1:]
        self.assertFalse(self.prepare(auth, challenge, wrong)[0])
        self.assertFalse(self.prepare(auth, challenge, proof)[0])
        self.assertFalse(self.dll.ul_authorizer_is_active(auth))

    def test_authorizer_malformed_lengths_consume_attempt(self):
        for challenge_size, proof_size in ((59, 32), (61, 32), (60, 31), (60, 33)):
            with self.subTest(lengths=(challenge_size, proof_size)):
                auth, _peer, _session, challenge, proof = self.request()
                bad_challenge = (challenge + b"x")[:challenge_size]
                bad_proof = (proof + b"x")[:proof_size]
                self.assertFalse(self.prepare(auth, bad_challenge, bad_proof)[0])
                self.assertFalse(self.prepare(auth, challenge, proof)[0])

    def test_authorizer_different_issue_cannot_replace_challenge(self):
        auth, peer, session, challenge, proof = self.request()
        self.assertEqual(self.issue(auth, peer.pid, session), challenge)
        self.assertIsNone(self.issue(auth, peer.pid, secrets.token_bytes(16)))
        self.assertTrue(self.prepare(auth, challenge, proof)[0])

    def test_authorizer_correctly_signed_unissued_fields_rejected(self):
        auth, peer, session, challenge, _proof = self.request()
        changed = bytearray(challenge)
        changed[7] = 3
        proof = self.signed(bytes(changed), peer.pid, session, 3)
        self.assertFalse(self.prepare(auth, bytes(changed), proof)[0])
        self.assertFalse(self.dll.ul_authorizer_is_active(auth))

    def test_authorizer_signed_pid_still_rejects_other_pipe_client(self):
        auth, _peer, session, challenge, proof = self.request()
        stranger = self.child("valid", session)
        server, _ = self.prepare(auth, challenge, proof)
        self.assertTrue(server)
        worker, result = self.start(server)
        self.go(stranger)
        self.assertEqual(self.result(worker, result), 1)
        self.assertEqual(self.dll.ul_admission_read_count(server), 0)

    def test_authorizer_revoke_cancels_partial_hello(self):
        auth, peer, _session, challenge, proof = self.request("partial")
        server, _ = self.prepare(auth, challenge, proof)
        self.assertTrue(server)
        worker, result = self.start(server)
        self.go(peer)
        self.assertEqual(peer.stdout.readline().strip(), "partial")
        deadline = time.monotonic() + 2
        while self.dll.ul_admission_read_count(server) < 32 and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(self.dll.ul_admission_read_count(server), 32)
        self.dll.ul_authorizer_revoke(auth)
        self.assertEqual(self.result(worker, result), 2)
        self.assertFalse(self.dll.ul_admission_pipe(server))
        self.assertFalse(self.dll.ul_authorizer_is_active(auth))

    def test_authorizer_revoke_and_release_invalidate_challenges(self):
        for action in ("revoke", "release"):
            with self.subTest(action=action):
                auth, peer, session, challenge, proof = self.request()
                getattr(self.dll, "ul_authorizer_" + action)(auth)
                self.assertFalse(self.prepare(auth, challenge, proof)[0])
                fresh = self.issue(auth, peer.pid, session)
                self.assertEqual(fresh is None, action == "revoke")

    def test_authorizer_dead_process_creation_failure_consumes_proof(self):
        auth, peer, _session, challenge, proof = self.request()
        peer.terminate()
        peer.wait(10)
        self.assertFalse(self.prepare(auth, challenge, proof)[0])
        self.assertFalse(self.prepare(auth, challenge, proof)[0])
        self.assertFalse(self.dll.ul_authorizer_is_active(auth))

    def test_authorizer_bad_issue_parameters_leave_zero_output(self):
        auth = self.authorizer()
        session = secrets.token_bytes(16)
        for pid, value, mask in ((0, session, 0), (4, session, 0),
                                  (os.getpid(), session, 0),
                                  (12345, b"\0" * 16, 0), (12345, session, 64)):
            self.assertIsNone(self.issue(auth, pid, value, mask))


def load_tests(loader, tests, pattern):
    # Reuse the peer/worker fixture without rerunning the inherited admission
    # test cases; those run separately against their own explicit DLL.
    return unittest.TestSuite(AuthorizationTests(name) for name in sorted(AuthorizationTests.__dict__)
                              if name.startswith("test_authorizer_"))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Supply the explicitly built authorization test DLL path")
    DLL_PATH = Path(sys.argv.pop())
    unittest.main(verbosity=2)
