"""Internal pairing-capability proof; no enrollment, storage, transport or audio.

Callers must first verify and authenticate the native OBS server, then provide
their own process/session/mix selection. This proves possession of a separately
enrolled capability, not executable identity. Keep the key out of JSON/logs.
"""
from __future__ import annotations

import hmac
import struct

CHALLENGE_BYTES = 60
PROOF_BYTES = 32
_CHALLENGE = struct.Struct("<4sBBBBI16s32s")
_DOMAIN = b"Utterleaf OBS prepare authorization v1\0"


class ObsAuthorizationError(ValueError):
    """A local request or remote challenge is invalid; never include its data."""


def create_prepare_proof(
    key: bytes | bytearray,
    challenge: bytes,
    *,
    client_pid: int,
    session_id: bytes,
    additional_mix_mask: int = 0,
) -> bytes:
    """Sign one matching canonical challenge with a 32-byte pairing capability.

    The caller owns the key and must not mutate it during this call. We erase
    our mutable key copy, but Python/OpenSSL secret erasure is not guaranteed.
    Only the proof and public challenge may be sent in a vendor request.
    """
    if (
        type(client_pid) is not int
        or not 5 <= client_pid <= 0xFFFFFFFF
        or type(session_id) is not bytes
        or len(session_id) != 16
        or not any(session_id)
        or type(additional_mix_mask) is not int
        or not 0 <= additional_mix_mask <= 63
    ):
        raise ObsAuthorizationError("Invalid local OBS authorization request")
    if (
        type(key) not in (bytes, bytearray)
        or len(key) != PROOF_BYTES
        or not any(key)
    ):
        raise ObsAuthorizationError("Invalid OBS pairing capability")
    if type(challenge) is not bytes or len(challenge) != CHALLENGE_BYTES:
        raise ObsAuthorizationError("Invalid OBS authorization challenge")
    magic, version, operation, reserved, mask, pid, session, _nonce = _CHALLENGE.unpack(challenge)
    if (
        magic != b"ULAA"
        or version != 1
        or operation != 1
        or reserved != 0
        or mask != additional_mix_mask
        or pid != client_pid
        or session != session_id
    ):
        raise ObsAuthorizationError("Invalid OBS authorization challenge")
    owned_key = bytearray(key)
    try:
        return hmac.digest(owned_key, _DOMAIN + challenge, "sha256")
    finally:
        owned_key[:] = b"\0" * len(owned_key)
