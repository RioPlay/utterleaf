"""Canonical capability proof and refusal of unexpected request bindings."""
import struct

import pytest

from utterleaf.obs_authorization import ObsAuthorizationError, create_prepare_proof

KEY = b"k" * 32  # Public fixture values, never user credentials.
SESSION = bytes(range(16))
CHALLENGE = struct.pack("<4sBBBBI16s32s", b"ULAA", 1, 1, 0, 9, 12345, SESSION, b"n" * 32)


def proof(key=KEY, challenge=CHALLENGE, **kwargs):
    options = dict(client_pid=12345, session_id=SESSION, additional_mix_mask=9)
    options.update(kwargs)
    return create_prepare_proof(key, challenge, **options)


def test_fixed_vector():
    # Independently computed with .NET HMACSHA256; native CNG also consumes it.
    assert proof().hex() == "4e61a5f34c3eaa55f9d3bfd9053cbdc3916595706b2de3e09898bc6d359d41dc"
    assert len(proof()) == 32


def test_mutable_key_is_preserved_and_nonce_changes_proof():
    key = bytearray(KEY)
    assert proof(key) == proof()
    assert key == KEY
    assert proof(challenge=CHALLENGE[:-1] + b"x") != proof()


@pytest.mark.parametrize("offset", [0, 4, 5, 6, 7, 8, 12])
def test_rejects_tampered_request_binding(offset):
    changed = bytearray(CHALLENGE)
    changed[offset] ^= 1
    with pytest.raises(ObsAuthorizationError, match="Invalid OBS authorization challenge"):
        proof(challenge=bytes(changed))


@pytest.mark.parametrize("challenge", [b"", CHALLENGE[:-1], CHALLENGE + b"x", bytearray(CHALLENGE), None])
def test_rejects_noncanonical_challenge(challenge):
    with pytest.raises(ObsAuthorizationError):
        proof(challenge=challenge)


@pytest.mark.parametrize("key", [b"", b"\0" * 32, b"k" * 31, b"k" * 33, None, "private-fixture"])
def test_rejects_invalid_key_without_exposing_it(key):
    with pytest.raises(ObsAuthorizationError) as exc:
        proof(key=key)
    assert str(exc.value) == "Invalid OBS pairing capability"


@pytest.mark.parametrize("kwargs", [
    {"client_pid": True}, {"client_pid": 0}, {"client_pid": 4},
    {"client_pid": 0x100000000}, {"client_pid": -1},
    {"session_id": b"\0" * 16}, {"session_id": b"x"},
    {"additional_mix_mask": True}, {"additional_mix_mask": -1},
    {"additional_mix_mask": 64},
])
def test_rejects_invalid_local_parameters(kwargs):
    with pytest.raises(ObsAuthorizationError, match="Invalid local OBS authorization request"):
        proof(**kwargs)
