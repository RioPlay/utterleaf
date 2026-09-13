// SPDX-License-Identifier: GPL-2.0-or-later
#include "handshake.h"

#include <windows.h>
#include <bcrypt.h>

#include <string.h>

static const uint8_t ULAH_MAGIC[4] = {'U', 'L', 'A', 'H'};
static const uint8_t ULAH_DOMAIN[] = "Utterleaf OBS audio server ack v1";

static bool constant_equal(const uint8_t *left, const uint8_t *right,
                           size_t size)
{
    uint8_t difference = 0;
    size_t index;

    for (index = 0; index < size; ++index)
        difference |= (uint8_t)(left[index] ^ right[index]);
    return difference == 0;
}

bool ul_handshake_ack(const uint8_t *hello, size_t hello_size,
                      const uint8_t expected_session[16],
                      uint8_t ack[ULAH_HANDSHAKE_BYTES])
{
    BCRYPT_ALG_HANDLE algorithm = NULL;
    BCRYPT_HASH_HANDLE hash = NULL;
    PUCHAR hash_object = NULL;
    DWORD hash_object_size = 0;
    DWORD result_size = 0;
    NTSTATUS status;
    uint8_t canonical[24];
    uint8_t secret[32];
    uint8_t digest[32];
    bool success = false;

    if (ack == NULL)
        return false;
    SecureZeroMemory(ack, ULAH_HANDSHAKE_BYTES);
    if (hello == NULL || expected_session == NULL ||
        hello_size != ULAH_HANDSHAKE_BYTES)
        return false;
    if (!constant_equal(hello, ULAH_MAGIC, sizeof(ULAH_MAGIC)) ||
        hello[4] != 1u || hello[5] != 1u || hello[6] != 0u || hello[7] != 0u ||
        !constant_equal(hello + 8, expected_session, 16u))
        return false;

    memcpy(canonical, hello, sizeof(canonical));
    memcpy(secret, hello + sizeof(canonical), sizeof(secret));
    memcpy(ack, canonical, sizeof(canonical));
    ack[5] = 2u;

    status = BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM,
                                         NULL, BCRYPT_ALG_HANDLE_HMAC_FLAG);
    if (status != 0)
        goto cleanup;
    status = BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH,
                               (PUCHAR)&hash_object_size,
                               sizeof(hash_object_size), &result_size, 0);
    if (status != 0 || result_size != sizeof(hash_object_size) ||
        hash_object_size == 0u || hash_object_size > 1024u)
        goto cleanup;
    hash_object = (PUCHAR)HeapAlloc(GetProcessHeap(), 0, hash_object_size);
    if (hash_object == NULL)
        goto cleanup;
    status = BCryptCreateHash(algorithm, &hash, hash_object, hash_object_size,
                              secret, sizeof(secret), 0);
    if (status != 0)
        goto cleanup;
    status = BCryptHashData(hash, (PUCHAR)ULAH_DOMAIN,
                            (ULONG)sizeof(ULAH_DOMAIN), 0);
    if (status != 0)
        goto cleanup;
    status = BCryptHashData(hash, canonical, sizeof(canonical), 0);
    if (status != 0)
        goto cleanup;
    status = BCryptFinishHash(hash, digest, sizeof(digest), 0);
    if (status != 0)
        goto cleanup;
    memcpy(ack + sizeof(canonical), digest, sizeof(digest));
    success = true;

cleanup:
    if (hash != NULL)
        BCryptDestroyHash(hash);
    if (algorithm != NULL)
        BCryptCloseAlgorithmProvider(algorithm, 0);
    if (hash_object != NULL) {
        SecureZeroMemory(hash_object, hash_object_size);
        HeapFree(GetProcessHeap(), 0, hash_object);
    }
    SecureZeroMemory(secret, sizeof(secret));
    SecureZeroMemory(digest, sizeof(digest));
    SecureZeroMemory(canonical, sizeof(canonical));
    if (!success)
        SecureZeroMemory(ack, ULAH_HANDSHAKE_BYTES);
    return success;
}
