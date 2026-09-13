// SPDX-License-Identifier: GPL-2.0-or-later
#include "crypto.h"

#include <windows.h>
#include <bcrypt.h>

#include <string.h>

bool ul_hmac_sha256(const uint8_t key[32], const uint8_t *domain,
                    size_t domain_size, const uint8_t *data, size_t data_size,
                    uint8_t output[32])
{
    BCRYPT_ALG_HANDLE algorithm = NULL;
    BCRYPT_HASH_HANDLE hash = NULL;
    PUCHAR hash_object = NULL;
    DWORD hash_object_size = 0;
    DWORD result_size = 0;
    NTSTATUS status;
    uint8_t owned_key[32];
    uint8_t digest[32];
    bool success = false;

    if (output == NULL)
        return false;
    SecureZeroMemory(output, 32u);
    if (key == NULL || domain == NULL || data == NULL ||
        domain_size < 1u || domain_size > 64u ||
        data_size < 1u || data_size > 256u)
        return false;

    memcpy(owned_key, key, sizeof(owned_key));
    status = BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM,
                                         NULL, BCRYPT_ALG_HANDLE_HMAC_FLAG);
    if (status != 0)
        goto cleanup;
    status = BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH,
                               (PUCHAR)&hash_object_size,
                               sizeof(hash_object_size), &result_size, 0);
    if (status != 0 || result_size != sizeof(hash_object_size) ||
        hash_object_size < 1u || hash_object_size > 1024u)
        goto cleanup;
    hash_object = (PUCHAR)HeapAlloc(GetProcessHeap(), 0, hash_object_size);
    if (hash_object == NULL)
        goto cleanup;
    status = BCryptCreateHash(algorithm, &hash, hash_object, hash_object_size,
                              owned_key, sizeof(owned_key), 0);
    if (status != 0)
        goto cleanup;
    status = BCryptHashData(hash, (PUCHAR)domain, (ULONG)domain_size, 0);
    if (status != 0)
        goto cleanup;
    status = BCryptHashData(hash, (PUCHAR)data, (ULONG)data_size, 0);
    if (status != 0)
        goto cleanup;
    status = BCryptFinishHash(hash, digest, sizeof(digest), 0);
    if (status != 0)
        goto cleanup;
    memcpy(output, digest, sizeof(digest));
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
    SecureZeroMemory(owned_key, sizeof(owned_key));
    SecureZeroMemory(digest, sizeof(digest));
    if (!success)
        SecureZeroMemory(output, 32u);
    return success;
}
