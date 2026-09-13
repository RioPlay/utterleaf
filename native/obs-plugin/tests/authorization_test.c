// SPDX-License-Identifier: GPL-2.0-or-later
#include <windows.h>
#include <bcrypt.h>

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct ul_admission ul_admission;

ULONGLONG WINAPI shim_GetTickCount64(void);
NTSTATUS WINAPI shim_BCryptGenRandom(BCRYPT_ALG_HANDLE algorithm, PUCHAR output,
                                     ULONG size, ULONG flags);
bool shim_ul_hmac_sha256(const uint8_t key[32], const uint8_t *domain,
                         size_t domain_size, const uint8_t *data,
                         size_t data_size, uint8_t output[32]);
ul_admission *shim_ul_admission_create(DWORD pid,
                                        const uint8_t session[16]);
void shim_ul_admission_cancel(ul_admission *admission);
void shim_ul_admission_destroy(ul_admission *admission);

#define GetTickCount64 shim_GetTickCount64
#define BCryptGenRandom shim_BCryptGenRandom
#define ul_hmac_sha256 shim_ul_hmac_sha256
#define ul_admission_create shim_ul_admission_create
#define ul_admission_cancel shim_ul_admission_cancel
#define ul_admission_destroy shim_ul_admission_destroy
#include "../src/authorization.c"

struct ul_admission {
    unsigned marker;
};

static struct ul_admission fake_admission = {0x554c4141u};
static ULONGLONG fake_ticks;
static ULONGLONG hmac_tick_advance;
static ULONGLONG create_tick_advance;
static unsigned rng_calls;
static unsigned hmac_calls;
static unsigned create_calls;
static unsigned cancel_calls;
static unsigned destroy_calls;
static bool rng_fails;
static bool hmac_fails;
static bool create_fails;
static DWORD created_pid;
static uint8_t created_session[16];

static const uint8_t TEST_KEY[32] = {
    1u,  2u,  3u,  4u,  5u,  6u,  7u,  8u,
    9u,  10u, 11u, 12u, 13u, 14u, 15u, 16u,
    17u, 18u, 19u, 20u, 21u, 22u, 23u, 24u,
    25u, 26u, 27u, 28u, 29u, 30u, 31u, 32u,
};
static const uint8_t TEST_SESSION[16] = {
    16u, 15u, 14u, 13u, 12u, 11u, 10u, 9u,
    8u,  7u,  6u,  5u,  4u,  3u,  2u,  1u,
};

static int check(bool condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", message);
        return 1;
    }
    return 0;
}

static void reset_fakes(void)
{
    fake_ticks = 100u;
    hmac_tick_advance = 0u;
    create_tick_advance = 0u;
    rng_calls = 0u;
    hmac_calls = 0u;
    create_calls = 0u;
    cancel_calls = 0u;
    destroy_calls = 0u;
    rng_fails = false;
    hmac_fails = false;
    create_fails = false;
    created_pid = 0u;
    SecureZeroMemory(created_session, sizeof(created_session));
}

static void compute_proof(const uint8_t key[32], const uint8_t *domain,
                          size_t domain_size, const uint8_t *data,
                          size_t data_size, uint8_t output[32])
{
    size_t index;

    for (index = 0; index < 32u; ++index)
        output[index] = (uint8_t)(key[index] ^ data[index % data_size] ^
                                  domain[index % domain_size] ^ 0x5au);
}

ULONGLONG WINAPI shim_GetTickCount64(void)
{
    return fake_ticks;
}

NTSTATUS WINAPI shim_BCryptGenRandom(BCRYPT_ALG_HANDLE algorithm, PUCHAR output,
                                     ULONG size, ULONG flags)
{
    ULONG index;

    ++rng_calls;
    if (algorithm != NULL || output == NULL || size != 32u ||
        flags != BCRYPT_USE_SYSTEM_PREFERRED_RNG)
        return (NTSTATUS)-1;
    for (index = 0; index < size; ++index)
        output[index] = (uint8_t)(0x80u + index + rng_calls);
    return rng_fails ? (NTSTATUS)-1 : 0;
}

bool shim_ul_hmac_sha256(const uint8_t key[32], const uint8_t *domain,
                         size_t domain_size, const uint8_t *data,
                         size_t data_size, uint8_t output[32])
{
    ++hmac_calls;
    fake_ticks += hmac_tick_advance;
    if (key == NULL || domain == NULL ||
        domain_size != sizeof(UL_AUTHORIZATION_DOMAIN) || data == NULL ||
        data_size != UL_AUTHORIZATION_CHALLENGE_BYTES || output == NULL ||
        hmac_fails) {
        if (output != NULL)
            SecureZeroMemory(output, 32u);
        return false;
    }
    compute_proof(key, domain, domain_size, data, data_size, output);
    return true;
}

ul_admission *shim_ul_admission_create(DWORD pid, const uint8_t session[16])
{
    ++create_calls;
    fake_ticks += create_tick_advance;
    created_pid = pid;
    memcpy(created_session, session, sizeof(created_session));
    return create_fails ? NULL : &fake_admission;
}

void shim_ul_admission_cancel(ul_admission *admission)
{
    if (admission == &fake_admission)
        ++cancel_calls;
}

void shim_ul_admission_destroy(ul_admission *admission)
{
    if (admission == &fake_admission)
        ++destroy_calls;
}

static ul_authorizer *new_authorizer(void)
{
    return ul_authorizer_create(TEST_KEY);
}

static bool issue(ul_authorizer *authorizer, uint8_t output[60])
{
    return ul_authorizer_issue(authorizer, 1234u, TEST_SESSION, 9u, output);
}

static void sign_challenge(const uint8_t challenge[60], uint8_t proof[32])
{
    compute_proof(TEST_KEY, UL_AUTHORIZATION_DOMAIN,
                  sizeof(UL_AUTHORIZATION_DOMAIN), challenge, 60u, proof);
}

static bool all_zero(const void *value, size_t size)
{
    const uint8_t *bytes = (const uint8_t *)value;
    size_t index;

    for (index = 0; index < size; ++index) {
        if (bytes[index] != 0u)
            return false;
    }
    return true;
}

static int test_create_and_issue(void)
{
    uint8_t zero_key[32] = {0};
    uint8_t zero_session[16] = {0};
    uint8_t challenge[60];
    uint8_t repeated[60];
    uint8_t changed_session[16];
    ul_authorizer *authorizer;
    unsigned index;
    int failures = 0;

    reset_fakes();
    failures += check(ul_authorizer_create(NULL) == NULL,
                      "null key rejected");
    failures += check(ul_authorizer_create(zero_key) == NULL,
                      "zero key rejected");
    authorizer = new_authorizer();
    failures += check(authorizer != NULL, "authorizer created");
    if (authorizer == NULL)
        return failures;

    memset(challenge, 0xa5, sizeof(challenge));
    failures += check(!ul_authorizer_issue(authorizer, 0u, TEST_SESSION, 0u,
                                           challenge) &&
                          all_zero(challenge, sizeof(challenge)),
                      "PID zero rejected with zero output");
    memset(challenge, 0xa5, sizeof(challenge));
    failures += check(!ul_authorizer_issue(authorizer, 3u, TEST_SESSION, 0u,
                                           challenge) &&
                          all_zero(challenge, sizeof(challenge)),
                      "PID below five rejected with zero output");
    memset(challenge, 0xa5, sizeof(challenge));
    failures += check(!ul_authorizer_issue(authorizer, GetCurrentProcessId(),
                                           TEST_SESSION, 0u, challenge) &&
                          all_zero(challenge, sizeof(challenge)),
                      "self PID rejected with zero output");
    memset(challenge, 0xa5, sizeof(challenge));
    failures += check(!ul_authorizer_issue(authorizer, 1234u, zero_session, 0u,
                                           challenge) &&
                          all_zero(challenge, sizeof(challenge)),
                      "zero session rejected with zero output");
    memset(challenge, 0xa5, sizeof(challenge));
    failures += check(!ul_authorizer_issue(authorizer, 1234u, TEST_SESSION, 64u,
                                           challenge) &&
                          all_zero(challenge, sizeof(challenge)),
                      "mix mask rejected with zero output");
    failures += check(issue(authorizer, challenge), "valid challenge issued");
    failures += check(memcmp(challenge, "ULAA", 4u) == 0 &&
                          challenge[4] == 1u && challenge[5] == 1u &&
                          challenge[6] == 0u && challenge[7] == 9u &&
                          load_u32_le(challenge + 8) == 1234u &&
                          memcmp(challenge + 12, TEST_SESSION, 16u) == 0,
                      "canonical challenge fields");
    for (index = 0; index < 32u; ++index)
        failures += check(challenge[28u + index] ==
                              (uint8_t)(0x81u + index),
                          "CNG nonce bytes retained");
    failures += check(issue(authorizer, repeated) && rng_calls == 1u &&
                          memcmp(repeated, challenge, sizeof(repeated)) == 0,
                      "matching issue is idempotent");
    memcpy(changed_session, TEST_SESSION, sizeof(changed_session));
    changed_session[0] ^= 1u;
    memset(repeated, 0xa5, sizeof(repeated));
    failures += check(!ul_authorizer_issue(authorizer, 1234u, changed_session,
                                           9u, repeated) &&
                          all_zero(repeated, sizeof(repeated)) && rng_calls == 1u,
                      "different issue cannot replace live challenge");
    ul_authorizer_destroy(authorizer);
    return failures;
}

static int test_expiry_boundaries(void)
{
    uint8_t challenge[60];
    uint8_t proof[32];
    ul_prepare_options options;
    ul_authorizer *authorizer;
    int failures = 0;

    reset_fakes();
    authorizer = new_authorizer();
    failures += check(authorizer != NULL && issue(authorizer, challenge),
                      "14999 challenge issued");
    sign_challenge(challenge, proof);
    fake_ticks += 14999u;
    failures += check(ul_authorizer_prepare(authorizer, challenge,
                                            sizeof(challenge), proof,
                                            sizeof(proof), &options) ==
                          &fake_admission,
                      "14999 milliseconds remains valid");
    ul_authorizer_release(authorizer);
    ul_authorizer_destroy(authorizer);

    reset_fakes();
    authorizer = new_authorizer();
    failures += check(authorizer != NULL && issue(authorizer, challenge),
                      "15000 challenge issued");
    sign_challenge(challenge, proof);
    memset(&options, 0xa5, sizeof(options));
    fake_ticks += 15000u;
    failures += check(ul_authorizer_prepare(authorizer, challenge,
                                            sizeof(challenge), proof,
                                            sizeof(proof), &options) == NULL &&
                          create_calls == 0u && all_zero(&options, sizeof(options)),
                      "15000 milliseconds is expired");
    ul_authorizer_destroy(authorizer);
    return failures;
}

static int test_attempt_consumption(void)
{
    uint8_t challenge[60];
    uint8_t changed[60];
    uint8_t proof[32];
    ul_prepare_options options;
    ul_authorizer *authorizer;
    int failures = 0;

    reset_fakes();
    authorizer = new_authorizer();
    failures += check(authorizer != NULL && issue(authorizer, challenge),
                      "bad proof challenge issued");
    sign_challenge(challenge, proof);
    proof[0] ^= 1u;
    failures += check(ul_authorizer_prepare(authorizer, challenge, 60u, proof,
                                            32u, &options) == NULL &&
                          create_calls == 0u &&
                          !authorizer->challenge_pending,
                      "bad proof consumed without admission");
    proof[0] ^= 1u;
    failures += check(ul_authorizer_prepare(authorizer, challenge, 60u, proof,
                                            32u, &options) == NULL &&
                          create_calls == 0u,
                      "valid replay rejected");

    failures += check(issue(authorizer, challenge),
                      "malformed attempt challenge issued");
    sign_challenge(challenge, proof);
    failures += check(ul_authorizer_prepare(authorizer, challenge, 59u, proof,
                                            32u, &options) == NULL &&
                          create_calls == 0u &&
                          !authorizer->challenge_pending,
                      "malformed length consumed");

    failures += check(issue(authorizer, challenge),
                      "mismatch challenge issued");
    memcpy(changed, challenge, sizeof(changed));
    changed[7] ^= 1u;
    sign_challenge(changed, proof);
    failures += check(ul_authorizer_prepare(authorizer, changed, 60u, proof, 32u,
                                            &options) == NULL &&
                          create_calls == 0u &&
                          !authorizer->challenge_pending,
                      "mismatched signed fields consumed");
    ul_authorizer_destroy(authorizer);
    return failures;
}

static int test_faults_and_deadlines(void)
{
    uint8_t challenge[60];
    uint8_t proof[32];
    ul_prepare_options options;
    ul_authorizer *authorizer;
    int failures = 0;

    reset_fakes();
    authorizer = new_authorizer();
    rng_fails = true;
    memset(challenge, 0xa5, sizeof(challenge));
    failures += check(!issue(authorizer, challenge) &&
                          all_zero(challenge, sizeof(challenge)) &&
                          all_zero(authorizer->challenge,
                                   sizeof(authorizer->challenge)) &&
                          !authorizer->challenge_pending,
                      "RNG failure clears challenge and output");
    rng_fails = false;
    failures += check(issue(authorizer, challenge), "HMAC fault issue");
    sign_challenge(challenge, proof);
    hmac_fails = true;
    failures += check(ul_authorizer_prepare(authorizer, challenge, 60u, proof,
                                            32u, &options) == NULL &&
                          create_calls == 0u,
                      "HMAC failure creates no admission");
    hmac_fails = false;

    failures += check(issue(authorizer, challenge), "create fault issue");
    sign_challenge(challenge, proof);
    create_fails = true;
    failures += check(ul_authorizer_prepare(authorizer, challenge, 60u, proof,
                                            32u, &options) == NULL &&
                          create_calls == 1u &&
                          !ul_authorizer_is_active(authorizer),
                      "admission create failure consumes proof");
    create_fails = false;

    failures += check(issue(authorizer, challenge), "slow HMAC issue");
    sign_challenge(challenge, proof);
    hmac_tick_advance = 15000u;
    failures += check(ul_authorizer_prepare(authorizer, challenge, 60u, proof,
                                            32u, &options) == NULL &&
                          create_calls == 1u,
                      "expiry during HMAC creates no admission");
    hmac_tick_advance = 0u;

    failures += check(issue(authorizer, challenge), "slow create issue");
    sign_challenge(challenge, proof);
    create_tick_advance = 15000u;
    failures += check(ul_authorizer_prepare(authorizer, challenge, 60u, proof,
                                            32u, &options) == NULL &&
                          create_calls == 2u && destroy_calls == 1u &&
                          !ul_authorizer_is_active(authorizer),
                      "expiry during create destroys unexposed admission");
    create_tick_advance = 0u;
    ul_authorizer_destroy(authorizer);
    return failures;
}

static int test_release_and_revoke(void)
{
    uint8_t challenge[60];
    uint8_t proof[32];
    uint8_t saved_key[32];
    ul_prepare_options options;
    ul_authorizer *authorizer;
    int failures = 0;

    reset_fakes();
    authorizer = new_authorizer();
    failures += check(authorizer != NULL, "release authorizer created");
    if (authorizer == NULL)
        return failures;
    memcpy(saved_key, authorizer->key, sizeof(saved_key));
    failures += check(issue(authorizer, challenge),
                      "release challenge issued");
    ul_authorizer_release(authorizer);
    failures += check(!authorizer->challenge_pending &&
                          all_zero(authorizer->challenge,
                                   sizeof(authorizer->challenge)) &&
                          memcmp(authorizer->key, saved_key,
                                 sizeof(saved_key)) == 0 &&
                          !authorizer->revoked,
                      "release clears challenge and retains key");
    failures += check(issue(authorizer, challenge), "issue after release");
    sign_challenge(challenge, proof);
    failures += check(ul_authorizer_prepare(authorizer, challenge, 60u, proof,
                                            32u, &options) == &fake_admission &&
                          ul_authorizer_is_active(authorizer),
                      "prepare before revoke");
    ul_authorizer_revoke(authorizer);
    failures += check(authorizer->revoked &&
                          all_zero(authorizer->key, sizeof(authorizer->key)) &&
                          all_zero(authorizer->challenge,
                                   sizeof(authorizer->challenge)) &&
                          !ul_authorizer_is_active(authorizer) &&
                          cancel_calls == 1u,
                      "revoke wipes key and cancels admission");
    memset(challenge, 0xa5, sizeof(challenge));
    failures += check(!issue(authorizer, challenge) &&
                          all_zero(challenge, sizeof(challenge)),
                      "revoked authorizer remains unusable");
    ul_authorizer_release(authorizer);
    failures += check(cancel_calls == 2u && destroy_calls == 1u,
                      "release destroys revoked admission");
    ul_authorizer_destroy(authorizer);
    SecureZeroMemory(saved_key, sizeof(saved_key));
    return failures;
}

typedef struct prepare_thread {
    ul_authorizer *authorizer;
    HANDLE start;
    uint8_t challenge[60];
    uint8_t proof[32];
    ul_prepare_options options;
    ul_admission *result;
} prepare_thread;

static DWORD WINAPI prepare_worker(LPVOID opaque)
{
    prepare_thread *thread = (prepare_thread *)opaque;

    if (WaitForSingleObject(thread->start, 5000u) != WAIT_OBJECT_0)
        return 1u;
    thread->result = ul_authorizer_prepare(
        thread->authorizer, thread->challenge, sizeof(thread->challenge),
        thread->proof, sizeof(thread->proof), &thread->options);
    return 0u;
}

static int test_concurrent_prepare(void)
{
    uint8_t challenge[60];
    uint8_t proof[32];
    prepare_thread threads[2];
    HANDLE handles[2] = {NULL, NULL};
    HANDLE start = NULL;
    ul_authorizer *authorizer;
    DWORD index;
    unsigned winners = 0u;
    int failures = 0;

    reset_fakes();
    authorizer = new_authorizer();
    failures += check(authorizer != NULL, "concurrent authorizer created");
    if (authorizer == NULL)
        goto cleanup;
    if (!issue(authorizer, challenge)) {
        failures += check(false, "concurrent challenge issued");
        goto cleanup;
    }
    sign_challenge(challenge, proof);
    start = CreateEventW(NULL, TRUE, FALSE, NULL);
    failures += check(start != NULL, "concurrent start event created");
    if (authorizer == NULL || start == NULL)
        goto cleanup;
    for (index = 0u; index < 2u; ++index) {
        SecureZeroMemory(&threads[index], sizeof(threads[index]));
        threads[index].authorizer = authorizer;
        threads[index].start = start;
        memcpy(threads[index].challenge, challenge, sizeof(challenge));
        memcpy(threads[index].proof, proof, sizeof(proof));
        handles[index] = CreateThread(NULL, 0u, prepare_worker, &threads[index],
                                      0u, NULL);
        failures += check(handles[index] != NULL, "prepare thread created");
    }
    if (handles[0] == NULL || handles[1] == NULL)
        goto cleanup;
    SetEvent(start);
    if (WaitForMultipleObjects(2u, handles, TRUE, 5000u) != WAIT_OBJECT_0) {
        failures += check(false, "prepare threads completed");
        goto cleanup;
    }
    for (index = 0u; index < 2u; ++index) {
        DWORD exit_code = 1u;
        failures += check(GetExitCodeThread(handles[index], &exit_code) &&
                              exit_code == 0u,
                          "prepare thread wait succeeded");
        if (threads[index].result != NULL)
            ++winners;
        else
            failures += check(all_zero(&threads[index].options,
                                       sizeof(threads[index].options)),
                              "losing prepare output zeroed");
    }
    failures += check(winners == 1u && create_calls == 1u && hmac_calls == 1u,
                      "exactly one concurrent prepare wins");

cleanup:
    if (start != NULL)
        SetEvent(start);
    if (handles[0] != NULL) {
        if (WaitForSingleObject(handles[0], 5000u) != WAIT_OBJECT_0) {
            fputs("FAIL: first prepare thread did not drain\n", stderr);
            fflush(stderr);
            ExitProcess(1u);
        }
        CloseHandle(handles[0]);
    }
    if (handles[1] != NULL) {
        if (WaitForSingleObject(handles[1], 5000u) != WAIT_OBJECT_0) {
            fputs("FAIL: second prepare thread did not drain\n", stderr);
            fflush(stderr);
            ExitProcess(1u);
        }
        CloseHandle(handles[1]);
    }
    if (start != NULL)
        CloseHandle(start);
    if (authorizer != NULL) {
        ul_authorizer_release(authorizer);
        ul_authorizer_destroy(authorizer);
    }
    return failures;
}

int main(void)
{
    int failures = 0;

    failures += test_create_and_issue();
    failures += test_expiry_boundaries();
    failures += test_attempt_consumption();
    failures += test_faults_and_deadlines();
    failures += test_release_and_revoke();
    failures += test_concurrent_prepare();
    if (failures == 0)
        puts("authorization state/fault tests passed");
    return failures == 0 ? 0 : 1;
}
