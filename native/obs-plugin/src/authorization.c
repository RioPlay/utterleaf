// SPDX-License-Identifier: GPL-2.0-or-later
#include "authorization.h"

#include "crypto.h"

#include <bcrypt.h>
#include <windows.h>

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define UL_AUTHORIZATION_TTL_MS 15000ULL

static const uint8_t UL_AUTHORIZATION_DOMAIN[] =
    "Utterleaf OBS prepare authorization v1";
static const uint8_t UL_AUTHORIZATION_MAGIC[4] = {'U', 'L', 'A', 'A'};

struct ul_authorizer {
    SRWLOCK lock;
    uint8_t key[32];
    uint8_t challenge[UL_AUTHORIZATION_CHALLENGE_BYTES];
    ULONGLONG challenge_started;
    ul_admission *admission;
    bool challenge_pending;
    bool revoked;
};

static bool bytes_are_zero(const uint8_t *bytes, size_t size)
{
    uint8_t combined = 0u;
    size_t index;

    for (index = 0; index < size; ++index)
        combined |= bytes[index];
    return combined == 0u;
}

static bool constant_equal(const uint8_t *left, const uint8_t *right,
                           size_t size)
{
    volatile uint8_t difference = 0u;
    size_t index;

    for (index = 0; index < size; ++index)
        difference |= (uint8_t)(left[index] ^ right[index]);
    return difference == 0u;
}

static void store_u32_le(uint8_t output[4], DWORD value)
{
    output[0] = (uint8_t)(value & 0xffu);
    output[1] = (uint8_t)((value >> 8) & 0xffu);
    output[2] = (uint8_t)((value >> 16) & 0xffu);
    output[3] = (uint8_t)((value >> 24) & 0xffu);
}

static DWORD load_u32_le(const uint8_t input[4])
{
    return (DWORD)input[0] | ((DWORD)input[1] << 8) |
           ((DWORD)input[2] << 16) | ((DWORD)input[3] << 24);
}

static void build_challenge_prefix(uint8_t challenge[28], DWORD client_pid,
                                   const uint8_t session[16],
                                   uint8_t additional_mix_mask)
{
    memcpy(challenge, UL_AUTHORIZATION_MAGIC, sizeof(UL_AUTHORIZATION_MAGIC));
    challenge[4] = 1u;
    challenge[5] = 1u;
    challenge[6] = 0u;
    challenge[7] = additional_mix_mask;
    store_u32_le(challenge + 8, client_pid);
    memcpy(challenge + 12, session, 16u);
}

static bool challenge_is_valid(const ul_authorizer *authorizer,
                               ULONGLONG now)
{
    return authorizer->challenge_pending &&
           now - authorizer->challenge_started < UL_AUTHORIZATION_TTL_MS;
}

static void clear_challenge(ul_authorizer *authorizer)
{
    SecureZeroMemory(authorizer->challenge, sizeof(authorizer->challenge));
    authorizer->challenge_started = 0u;
    authorizer->challenge_pending = false;
}

ul_authorizer *ul_authorizer_create(const uint8_t key[32])
{
    ul_authorizer *authorizer;

    if (key == NULL || bytes_are_zero(key, 32u))
        return NULL;
    authorizer = (ul_authorizer *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY,
                                            sizeof(*authorizer));
    if (authorizer == NULL)
        return NULL;
    InitializeSRWLock(&authorizer->lock);
    memcpy(authorizer->key, key, sizeof(authorizer->key));
    return authorizer;
}

bool ul_authorizer_issue(
    ul_authorizer *authorizer, DWORD client_pid, const uint8_t session[16],
    uint8_t additional_mix_mask,
    uint8_t out_challenge[UL_AUTHORIZATION_CHALLENGE_BYTES])
{
    uint8_t session_copy[16];
    uint8_t requested_prefix[28];
    ULONGLONG now;
    bool success = false;

    if (out_challenge == NULL)
        return false;
    if (session == NULL) {
        SecureZeroMemory(out_challenge, UL_AUTHORIZATION_CHALLENGE_BYTES);
        return false;
    }
    memcpy(session_copy, session, sizeof(session_copy));
    SecureZeroMemory(out_challenge, UL_AUTHORIZATION_CHALLENGE_BYTES);
    if (authorizer == NULL || client_pid < 5u ||
        client_pid == GetCurrentProcessId() || additional_mix_mask > 63u ||
        bytes_are_zero(session_copy, sizeof(session_copy)))
        goto cleanup;

    build_challenge_prefix(requested_prefix, client_pid, session_copy,
                           additional_mix_mask);
    AcquireSRWLockExclusive(&authorizer->lock);
    now = GetTickCount64();
    if (authorizer->revoked || authorizer->admission != NULL)
        goto unlock;
    if (authorizer->challenge_pending) {
        if (!challenge_is_valid(authorizer, now)) {
            clear_challenge(authorizer);
        } else if (constant_equal(authorizer->challenge, requested_prefix,
                                  sizeof(requested_prefix))) {
            memcpy(out_challenge, authorizer->challenge,
                   UL_AUTHORIZATION_CHALLENGE_BYTES);
            success = true;
            goto unlock;
        } else {
            goto unlock;
        }
    }

    memcpy(authorizer->challenge, requested_prefix, sizeof(requested_prefix));
    if (BCryptGenRandom(NULL, authorizer->challenge + 28, 32u,
                        BCRYPT_USE_SYSTEM_PREFERRED_RNG) != 0) {
        clear_challenge(authorizer);
        goto unlock;
    }
    authorizer->challenge_started = now;
    authorizer->challenge_pending = true;
    memcpy(out_challenge, authorizer->challenge,
           UL_AUTHORIZATION_CHALLENGE_BYTES);
    success = true;

unlock:
    ReleaseSRWLockExclusive(&authorizer->lock);
cleanup:
    if (!success)
        SecureZeroMemory(out_challenge, UL_AUTHORIZATION_CHALLENGE_BYTES);
    SecureZeroMemory(session_copy, sizeof(session_copy));
    SecureZeroMemory(requested_prefix, sizeof(requested_prefix));
    return success;
}

ul_admission *ul_authorizer_prepare(
    ul_authorizer *authorizer, const uint8_t *challenge, size_t challenge_size,
    const uint8_t *proof, size_t proof_size, ul_prepare_options *options)
{
    uint8_t supplied_challenge[UL_AUTHORIZATION_CHALLENGE_BYTES];
    uint8_t supplied_proof[UL_AUTHORIZATION_PROOF_BYTES];
    uint8_t expected_proof[UL_AUTHORIZATION_PROOF_BYTES];
    uint8_t consumed_challenge[UL_AUTHORIZATION_CHALLENGE_BYTES];
    ULONGLONG challenge_started = 0u;
    bool inputs_complete;
    bool locked = false;
    ul_admission *discarded_admission = NULL;
    ul_admission *result = NULL;

    SecureZeroMemory(supplied_challenge, sizeof(supplied_challenge));
    SecureZeroMemory(supplied_proof, sizeof(supplied_proof));
    SecureZeroMemory(expected_proof, sizeof(expected_proof));
    SecureZeroMemory(consumed_challenge, sizeof(consumed_challenge));
    inputs_complete = challenge != NULL &&
                      challenge_size == sizeof(supplied_challenge) &&
                      proof != NULL && proof_size == sizeof(supplied_proof) &&
                      options != NULL;
    if (challenge != NULL && challenge_size == sizeof(supplied_challenge))
        memcpy(supplied_challenge, challenge, sizeof(supplied_challenge));
    if (proof != NULL && proof_size == sizeof(supplied_proof))
        memcpy(supplied_proof, proof, sizeof(supplied_proof));
    if (options != NULL)
        SecureZeroMemory(options, sizeof(*options));
    if (authorizer == NULL)
        goto cleanup;

    AcquireSRWLockExclusive(&authorizer->lock);
    locked = true;
    if (authorizer->revoked || authorizer->admission != NULL ||
        !authorizer->challenge_pending)
        goto cleanup;

    memcpy(consumed_challenge, authorizer->challenge,
           sizeof(consumed_challenge));
    challenge_started = authorizer->challenge_started;
    if (!challenge_is_valid(authorizer, GetTickCount64())) {
        clear_challenge(authorizer);
        goto cleanup;
    }
    clear_challenge(authorizer);
    if (!inputs_complete ||
        !constant_equal(supplied_challenge, consumed_challenge,
                        sizeof(consumed_challenge)) ||
        !ul_hmac_sha256(authorizer->key, UL_AUTHORIZATION_DOMAIN,
                        sizeof(UL_AUTHORIZATION_DOMAIN), consumed_challenge,
                        sizeof(consumed_challenge), expected_proof) ||
        !constant_equal(supplied_proof, expected_proof,
                        sizeof(expected_proof)))
        goto cleanup;
    if (GetTickCount64() - challenge_started >= UL_AUTHORIZATION_TTL_MS)
        goto cleanup;

    result = ul_admission_create(load_u32_le(consumed_challenge + 8),
                                 consumed_challenge + 12);
    if (result == NULL)
        goto cleanup;
    if (GetTickCount64() - challenge_started >= UL_AUTHORIZATION_TTL_MS) {
        discarded_admission = result;
        result = NULL;
        goto cleanup;
    }
    authorizer->admission = result;
    options->client_pid = load_u32_le(consumed_challenge + 8);
    memcpy(options->session, consumed_challenge + 12,
           sizeof(options->session));
    options->additional_mix_mask = consumed_challenge[7];

cleanup:
    if (locked)
        ReleaseSRWLockExclusive(&authorizer->lock);
    if (discarded_admission != NULL)
        ul_admission_destroy(discarded_admission);
    if (result == NULL && options != NULL)
        SecureZeroMemory(options, sizeof(*options));
    SecureZeroMemory(supplied_challenge, sizeof(supplied_challenge));
    SecureZeroMemory(supplied_proof, sizeof(supplied_proof));
    SecureZeroMemory(expected_proof, sizeof(expected_proof));
    SecureZeroMemory(consumed_challenge, sizeof(consumed_challenge));
    return result;
}

bool ul_authorizer_is_active(ul_authorizer *authorizer)
{
    bool active;

    if (authorizer == NULL)
        return false;
    AcquireSRWLockExclusive(&authorizer->lock);
    active = !authorizer->revoked && authorizer->admission != NULL;
    ReleaseSRWLockExclusive(&authorizer->lock);
    return active;
}

void ul_authorizer_revoke(ul_authorizer *authorizer)
{
    ul_admission *admission;

    if (authorizer == NULL)
        return;
    AcquireSRWLockExclusive(&authorizer->lock);
    authorizer->revoked = true;
    clear_challenge(authorizer);
    SecureZeroMemory(authorizer->key, sizeof(authorizer->key));
    admission = authorizer->admission;
    ReleaseSRWLockExclusive(&authorizer->lock);

    if (admission != NULL)
        ul_admission_cancel(admission);
}

void ul_authorizer_release(ul_authorizer *authorizer)
{
    ul_admission *admission;

    if (authorizer == NULL)
        return;
    AcquireSRWLockExclusive(&authorizer->lock);
    clear_challenge(authorizer);
    admission = authorizer->admission;
    authorizer->admission = NULL;
    ReleaseSRWLockExclusive(&authorizer->lock);

    if (admission != NULL) {
        ul_admission_cancel(admission);
        ul_admission_destroy(admission);
    }
}

void ul_authorizer_destroy(ul_authorizer *authorizer)
{
    if (authorizer == NULL)
        return;
    ul_authorizer_revoke(authorizer);
    ul_authorizer_release(authorizer);
    SecureZeroMemory(authorizer, sizeof(*authorizer));
    HeapFree(GetProcessHeap(), 0, authorizer);
}
