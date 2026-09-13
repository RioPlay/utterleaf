"""Real libobs data decoding with a controlled runtime boundary; no OBS startup."""
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import struct
import sys
import unittest


class VendorTests(unittest.TestCase):
    def setUp(self):
        VENDOR.ul_vendor_test_reset(True)

    def dispatch(self, payload, *, operation="issue"):
        request = OBS.obs_data_create_from_json(json.dumps(payload).encode())
        response = OBS.obs_data_create()
        self.assertTrue(request and response)
        try:
            callback = {
                "status": VENDOR.ul_vendor_status,
                "issue": VENDOR.ul_vendor_issue,
                "prepare": VENDOR.ul_vendor_prepare,
            }[operation]
            callback(request, response, None)
            return json.loads(OBS.obs_data_get_json(response))
        finally:
            OBS.obs_data_release(request)
            OBS.obs_data_release(response)

    def test_issue_roundtrip_uses_exact_native_data(self):
        for pid, mask in [(5, 0), (0xFFFFFFFF, 63)]:
            with self.subTest(pid=pid, mask=mask):
                response = self.dispatch({**ISSUE, "clientPid": pid, "additionalMixMask": mask})
                expected = struct.pack("<4sBBBBI16s32s", b"ULAA", 1, 1, 0, mask, pid, SESSION, b"\x11" * 32)
                self.assertEqual(response, {"ok": True, "protocolVersion": 1, "challenge": expected.hex()})

    def test_invalid_issue_never_reaches_runtime(self):
        changes = [
            ("clientPid", True), ("clientPid", 4), ("clientPid", 0x100000000),
            ("clientPid", 5.0), ("clientPid", "5"), ("clientPid", []),
            ("additionalMixMask", False), ("additionalMixMask", -1), ("additionalMixMask", 64),
            ("additionalMixMask", 1.5), ("additionalMixMask", "1"),
            ("sessionId", ""), ("sessionId", "a"), ("sessionId", "a" * 31),
            ("sessionId", "a" * 33), ("sessionId", "AA" * 16), ("sessionId", "gg" * 16),
            ("sessionId", "00" * 16), ("sessionId", 123), ("sessionId", {}),
            ("extra", 1),
        ]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                VENDOR.ul_vendor_test_reset(True)
                self.assertEqual(self.dispatch({**ISSUE, field: value}), {"ok": False})
                self.assertEqual(VENDOR.ul_vendor_test_count(0), 0)
        for missing in ISSUE:
            with self.subTest(missing=missing):
                self.assertEqual(self.dispatch({k: v for k, v in ISSUE.items() if k != missing}), {"ok": False})
                self.assertEqual(VENDOR.ul_vendor_test_count(0), 0)

    def test_prepare_accepts_only_canonical_fixed_fields(self):
        payload = {"challenge": "ab" * 60, "proof": "12" * 32}
        self.assertEqual(self.dispatch(payload, operation="prepare"), {"ok": True, "protocolVersion": 1})
        self.assertEqual(VENDOR.ul_vendor_test_count(1), 1)
        self.assertEqual(VENDOR.ul_vendor_test_count(2), 0)
        for field in payload:
            for invalid in [True, 7, [], {}, "", "a", "A" * len(payload[field]), payload[field] + "0"]:
                with self.subTest(field=field, value=invalid):
                    VENDOR.ul_vendor_test_reset(True)
                    self.assertEqual(self.dispatch({**payload, field: invalid}, operation="prepare"), {"ok": False})
                    self.assertEqual(VENDOR.ul_vendor_test_count(1), 1)
                    self.assertEqual(VENDOR.ul_vendor_test_count(2), 1)
        for changed in [{}, {"challenge": payload["challenge"]}, {**payload, "extra": False}]:
            with self.subTest(changed=changed):
                VENDOR.ul_vendor_test_reset(True)
                self.assertEqual(self.dispatch(changed, operation="prepare"), {"ok": False})
                self.assertEqual(VENDOR.ul_vendor_test_count(2), 1)

    def test_closed_runtime_returns_only_generic_refusal(self):
        VENDOR.ul_vendor_test_reset(False)
        self.assertEqual(self.dispatch(ISSUE), {"ok": False})
        self.assertEqual(self.dispatch({"challenge": "ab" * 60, "proof": "12" * 32}, operation="prepare"), {"ok": False})
        self.assertEqual(VENDOR.ul_vendor_test_count(0), 0)
        self.assertEqual(VENDOR.ul_vendor_test_count(1), 0)

    def test_disabled_registration_gate_refuses_before_runtime(self):
        VENDOR.ul_vendor_set_enabled(False)
        self.assertEqual(self.dispatch(ISSUE), {"ok": False})
        self.assertEqual(self.dispatch({"challenge": "ab" * 60, "proof": "12" * 32}, operation="prepare"), {"ok": False})
        self.assertEqual(VENDOR.ul_vendor_test_count(0), 0)
        self.assertEqual(VENDOR.ul_vendor_test_count(1), 0)

    def test_defaults_do_not_authorize_a_request(self):
        request, response = OBS.obs_data_create(), OBS.obs_data_create()
        try:
            OBS.obs_data_set_default_int(request, b"clientPid", 5)
            OBS.obs_data_set_default_int(request, b"additionalMixMask", 0)
            OBS.obs_data_set_default_string(request, b"sessionId", SESSION.hex().encode())
            VENDOR.ul_vendor_issue(request, response, None)
            self.assertEqual(json.loads(OBS.obs_data_get_json(response)), {"ok": False})
            self.assertEqual(VENDOR.ul_vendor_test_count(0), 0)
        finally:
            OBS.obs_data_release(request)
            OBS.obs_data_release(response)

    def test_status_is_exact_read_only_compatibility_metadata(self):
        expected = {"ok": True, "protocolVersion": 1, "commandVersion": 1,
                    "audioVersion": 2, "maxBusMask": 63}
        self.assertEqual(self.dispatch({}, operation="status"), expected)
        self.assertEqual(self.dispatch({}, operation="status"), expected)
        self.assertEqual([VENDOR.ul_vendor_test_count(i) for i in range(3)], [0, 0, 0])
        self.assertEqual(self.dispatch({"extra": 1}, operation="status"), {"ok": False})
        self.assertEqual([VENDOR.ul_vendor_test_count(i) for i in range(3)], [0, 0, 0])

    def test_status_does_not_consume_issue_or_prepare(self):
        payload = {"challenge": "ab" * 60, "proof": "12" * 32}
        self.assertTrue(self.dispatch(ISSUE)["ok"])
        self.assertTrue(self.dispatch({}, operation="status")["ok"])
        self.assertTrue(self.dispatch(payload, operation="prepare")["ok"])
        self.assertEqual([VENDOR.ul_vendor_test_count(i) for i in range(3)], [1, 1, 0])

    def test_disabled_status_returns_only_generic_refusal(self):
        VENDOR.ul_vendor_set_enabled(False)
        self.assertEqual(self.dispatch({}, operation="status"), {"ok": False})
        self.assertEqual([VENDOR.ul_vendor_test_count(i) for i in range(3)], [0, 0, 0])


if __name__ == "__main__":
    runtime, fixture = map(Path, sys.argv[1:3])
    sys.argv = sys.argv[:1]
    SESSION = bytes(range(1, 17))
    ISSUE = {"clientPid": 5, "sessionId": SESSION.hex(), "additionalMixMask": 0}
    with os.add_dll_directory(str(runtime.parent)):
        OBS = ctypes.CDLL(str(runtime), winmode=0x1100)
        VENDOR = ctypes.CDLL(str(fixture), winmode=0x1100)
        for name, arguments, result in [
            ("obs_data_create", [], ctypes.c_void_p),
            ("obs_data_create_from_json", [ctypes.c_char_p], ctypes.c_void_p),
            ("obs_data_get_json", [ctypes.c_void_p], ctypes.c_char_p),
            ("obs_data_release", [ctypes.c_void_p], None),
            ("obs_data_set_default_int", [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_longlong], None),
            ("obs_data_set_default_string", [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p], None),
        ]:
            getattr(OBS, name).argtypes, getattr(OBS, name).restype = arguments, result
        for name in ["ul_vendor_status", "ul_vendor_issue", "ul_vendor_prepare"]:
            getattr(VENDOR, name).argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            getattr(VENDOR, name).restype = None
        VENDOR.ul_vendor_test_reset.argtypes, VENDOR.ul_vendor_test_reset.restype = [ctypes.c_bool], None
        VENDOR.ul_vendor_set_enabled.argtypes, VENDOR.ul_vendor_set_enabled.restype = [ctypes.c_bool], None
        VENDOR.ul_vendor_test_count.argtypes, VENDOR.ul_vendor_test_count.restype = [ctypes.c_uint], ctypes.c_uint
        unittest.main()
