// SPDX-License-Identifier: GPL-2.0-or-later
#include <windows.h>

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "../src/plugin_state.h"

static BOOL WINAPI shim_GetModuleHandleExW(DWORD flags, LPCWSTR address,
                                            HMODULE *module);
static ul_pairing_result
shim_ul_pairing_store_open(ul_pairing_store **store_out);
static void shim_ul_pairing_cancel_init(ul_pairing_cancel *cancel);
static void shim_ul_pairing_cancel_request(ul_pairing_cancel *cancel);
static void shim_ul_pairing_store_destroy(ul_pairing_store *store);
static ul_pairing_result
shim_ul_pairing_store_claim_owner(ul_pairing_store *store);
static ul_pairing_result shim_ul_pairing_store_load(ul_pairing_store *store,
                                                    uint8_t key[32]);
static ul_pairing_result shim_ul_pairing_store_create(
    ul_pairing_store *store, const ul_pairing_cancel *cancel, uint8_t key[32]);
static ul_pairing_result shim_ul_pairing_store_replace(
    ul_pairing_store *store, const ul_pairing_cancel *cancel, uint8_t key[32]);
static ul_pairing_result shim_ul_pairing_store_export(
    ul_pairing_store *store, const wchar_t *destination,
    const ul_pairing_cancel *cancel);
static ul_pairing_result
shim_ul_pairing_store_forget(ul_pairing_store *store);
static ul_authorizer *shim_ul_authorizer_create(const uint8_t key[32]);
static bool shim_ul_authorizer_issue(ul_authorizer *authorizer,
                                     DWORD client_pid,
                                     const uint8_t session[16], uint8_t mask,
                                     uint8_t out_challenge[60]);
static ul_admission *shim_ul_authorizer_prepare(
    ul_authorizer *authorizer, const uint8_t *challenge, size_t challenge_size,
    const uint8_t *proof, size_t proof_size, ul_prepare_options *options);
static void shim_ul_authorizer_revoke(ul_authorizer *authorizer);
static void shim_ul_authorizer_release(ul_authorizer *authorizer);
static void shim_ul_authorizer_destroy(ul_authorizer *authorizer);
static int shim_ul_admission_authenticate(ul_admission *admission,
                                          DWORD timeout_ms);
static void shim_ul_admission_cancel(ul_admission *admission);
static HANDLE shim_ul_admission_pipe(const ul_admission *admission);

#define GetModuleHandleExW shim_GetModuleHandleExW
#define ul_pairing_store_open shim_ul_pairing_store_open
#define ul_pairing_cancel_init shim_ul_pairing_cancel_init
#define ul_pairing_cancel_request shim_ul_pairing_cancel_request
#define ul_pairing_store_destroy shim_ul_pairing_store_destroy
#define ul_pairing_store_claim_owner shim_ul_pairing_store_claim_owner
#define ul_pairing_store_load shim_ul_pairing_store_load
#define ul_pairing_store_create shim_ul_pairing_store_create
#define ul_pairing_store_replace shim_ul_pairing_store_replace
#define ul_pairing_store_export shim_ul_pairing_store_export
#define ul_pairing_store_forget shim_ul_pairing_store_forget
#define ul_authorizer_create shim_ul_authorizer_create
#define ul_authorizer_issue shim_ul_authorizer_issue
#define ul_authorizer_prepare shim_ul_authorizer_prepare
#define ul_authorizer_revoke shim_ul_authorizer_revoke
#define ul_authorizer_release shim_ul_authorizer_release
#define ul_authorizer_destroy shim_ul_authorizer_destroy
#define ul_admission_authenticate shim_ul_admission_authenticate
#define ul_admission_cancel shim_ul_admission_cancel
#define ul_admission_pipe shim_ul_admission_pipe
#define UL_PLUGIN_AUTH_TIMEOUT_MS 40u
#define UL_PLUGIN_READY_TIMEOUT_MS 40u
#include "../src/plugin_state.c"
#undef GetModuleHandleExW
#undef ul_pairing_store_open
#undef ul_pairing_cancel_init
#undef ul_pairing_cancel_request
#undef ul_pairing_store_destroy
#undef ul_pairing_store_claim_owner
#undef ul_pairing_store_load
#undef ul_pairing_store_create
#undef ul_pairing_store_replace
#undef ul_pairing_store_export
#undef ul_pairing_store_forget
#undef ul_authorizer_create
#undef ul_authorizer_issue
#undef ul_authorizer_prepare
#undef ul_authorizer_revoke
#undef ul_authorizer_release
#undef ul_authorizer_destroy
#undef ul_admission_authenticate
#undef ul_admission_cancel
#undef ul_admission_pipe

struct ul_pairing_store {
    int unused;
};

struct ul_admission {
    HANDLE cancelled;
    int authenticate_result;
};

struct ul_authorizer {
    bool outstanding;
    bool revoked;
    ul_admission *admission;
};

static bool fake_pin = true;
static ul_pairing_result fake_open_result = UL_PAIRING_OK;
static ul_pairing_result fake_claim_result = UL_PAIRING_OK;
static ul_pairing_result fake_load_result = UL_PAIRING_MISSING;
static ul_pairing_result fake_generate_result = UL_PAIRING_OK;
static ul_pairing_result fake_export_result = UL_PAIRING_OK;
static ul_pairing_result fake_forget_result = UL_PAIRING_OK;
static int fake_authenticate_result = UL_ADMISSION_AUTH_OK;
static bool fake_block_export;
static HANDLE fake_export_entered;
static bool fake_block_issue;
static HANDLE fake_issue_entered;
static HANDLE fake_issue_release;
static volatile LONG fake_release_count;
static volatile LONG fake_destroy_count;
static volatile LONG fake_store_destroy_count;

static int check(bool condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", message);
        return 1;
    }
    return 0;
}

static BOOL WINAPI shim_GetModuleHandleExW(DWORD flags, LPCWSTR address,
                                            HMODULE *module)
{
    (void)flags;
    (void)address;
    if (!fake_pin) {
        SetLastError(ERROR_MOD_NOT_FOUND);
        return FALSE;
    }
    *module = GetModuleHandleW(NULL);
    return TRUE;
}

static ul_pairing_result
shim_ul_pairing_store_open(ul_pairing_store **store_out)
{
    *store_out = NULL;
    if (fake_open_result != UL_PAIRING_OK)
        return fake_open_result;
    *store_out = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY,
                           sizeof(**store_out));
    return *store_out == NULL ? UL_PAIRING_IO_ERROR : UL_PAIRING_OK;
}

static void shim_ul_pairing_cancel_init(ul_pairing_cancel *cancel)
{
    InterlockedExchange(&cancel->requested, 0);
}

static void shim_ul_pairing_cancel_request(ul_pairing_cancel *cancel)
{
    InterlockedExchange(&cancel->requested, 1);
}

static void shim_ul_pairing_store_destroy(ul_pairing_store *store)
{
    HeapFree(GetProcessHeap(), 0, store);
    InterlockedIncrement(&fake_store_destroy_count);
}

static ul_pairing_result
shim_ul_pairing_store_claim_owner(ul_pairing_store *store)
{
    (void)store;
    return fake_claim_result;
}

static ul_pairing_result shim_ul_pairing_store_load(ul_pairing_store *store,
                                                    uint8_t key[32])
{
    (void)store;
    SecureZeroMemory(key, 32);
    if (fake_load_result == UL_PAIRING_OK)
        memset(key, 0x5a, 32);
    return fake_load_result;
}

static ul_pairing_result fake_generate(const ul_pairing_cancel *cancel,
                                       uint8_t key[32])
{
    SecureZeroMemory(key, 32);
    if (cancel != NULL &&
        InterlockedCompareExchange((volatile LONG *)&cancel->requested, 0, 0))
        return UL_PAIRING_CANCELLED;
    if (fake_generate_result == UL_PAIRING_OK) {
        memset(key, 0xa5, 32);
        fake_load_result = UL_PAIRING_OK;
    }
    return fake_generate_result;
}

static ul_pairing_result shim_ul_pairing_store_create(
    ul_pairing_store *store, const ul_pairing_cancel *cancel, uint8_t key[32])
{
    (void)store;
    return fake_generate(cancel, key);
}

static ul_pairing_result shim_ul_pairing_store_replace(
    ul_pairing_store *store, const ul_pairing_cancel *cancel, uint8_t key[32])
{
    (void)store;
    return fake_generate(cancel, key);
}

static ul_pairing_result shim_ul_pairing_store_export(
    ul_pairing_store *store, const wchar_t *destination,
    const ul_pairing_cancel *cancel)
{
    (void)store;
    (void)destination;
    if (fake_block_export) {
        SetEvent(fake_export_entered);
        while (InterlockedCompareExchange((volatile LONG *)&cancel->requested,
                                           0, 0) == 0)
            Sleep(1);
        return UL_PAIRING_CANCELLED;
    }
    return fake_export_result;
}

static ul_pairing_result
shim_ul_pairing_store_forget(ul_pairing_store *store)
{
    (void)store;
    if (fake_forget_result == UL_PAIRING_OK)
        fake_load_result = UL_PAIRING_MISSING;
    return fake_forget_result;
}

static ul_authorizer *shim_ul_authorizer_create(const uint8_t key[32])
{
    ul_authorizer *authorizer;

    if (key == NULL || key[0] == 0)
        return NULL;
    authorizer = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY,
                           sizeof(*authorizer));
    return authorizer;
}

static bool shim_ul_authorizer_issue(ul_authorizer *authorizer,
                                     DWORD client_pid,
                                     const uint8_t session[16], uint8_t mask,
                                     uint8_t out_challenge[60])
{
    if (fake_block_issue) {
        SetEvent(fake_issue_entered);
        if (WaitForSingleObject(fake_issue_release, 5000) != WAIT_OBJECT_0)
            return false;
    }
    if (authorizer == NULL || authorizer->revoked || client_pid < 5 ||
        session == NULL || mask > 63)
        return false;
    memset(out_challenge, 0x33, 60);
    authorizer->outstanding = true;
    return true;
}

static ul_admission *shim_ul_authorizer_prepare(
    ul_authorizer *authorizer, const uint8_t *challenge, size_t challenge_size,
    const uint8_t *proof, size_t proof_size, ul_prepare_options *options)
{
    ul_admission *admission;

    SecureZeroMemory(options, sizeof(*options));
    if (authorizer == NULL || authorizer->revoked || !authorizer->outstanding)
        return NULL;
    authorizer->outstanding = false;
    if (challenge == NULL || proof == NULL || challenge_size != 60 ||
        proof_size != 32 || challenge[0] != 0x33 || proof[0] != 0x44)
        return NULL;
    admission = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY,
                          sizeof(*admission));
    if (admission == NULL)
        return NULL;
    admission->cancelled = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (admission->cancelled == NULL) {
        HeapFree(GetProcessHeap(), 0, admission);
        return NULL;
    }
    admission->authenticate_result = fake_authenticate_result;
    authorizer->admission = admission;
    options->client_pid = 100;
    return admission;
}

static void shim_ul_authorizer_revoke(ul_authorizer *authorizer)
{
    if (authorizer == NULL)
        return;
    authorizer->revoked = true;
    if (authorizer->admission != NULL)
        SetEvent(authorizer->admission->cancelled);
}

static void shim_ul_authorizer_release(ul_authorizer *authorizer)
{
    if (authorizer == NULL || authorizer->admission == NULL)
        return;
    CloseHandle(authorizer->admission->cancelled);
    HeapFree(GetProcessHeap(), 0, authorizer->admission);
    authorizer->admission = NULL;
    InterlockedIncrement(&fake_release_count);
}

static void shim_ul_authorizer_destroy(ul_authorizer *authorizer)
{
    if (authorizer == NULL)
        return;
    shim_ul_authorizer_release(authorizer);
    SecureZeroMemory(authorizer, sizeof(*authorizer));
    HeapFree(GetProcessHeap(), 0, authorizer);
    InterlockedIncrement(&fake_destroy_count);
}

static int shim_ul_admission_authenticate(ul_admission *admission,
                                          DWORD timeout_ms)
{
    if (admission->authenticate_result == UL_ADMISSION_AUTH_OK)
        return UL_ADMISSION_AUTH_OK;
    if (WaitForSingleObject(admission->cancelled, timeout_ms) == WAIT_OBJECT_0)
        return UL_ADMISSION_CANCELLED;
    return admission->authenticate_result;
}

static void shim_ul_admission_cancel(ul_admission *admission)
{
    SetEvent(admission->cancelled);
}

static HANDLE shim_ul_admission_pipe(const ul_admission *admission)
{
    (void)admission;
    return NULL;
}

static DWORD WINAPI export_thread(void *unused)
{
    (void)unused;
    return (DWORD)ul_plugin_export(L"C:\\transfer.ulpair");
}

typedef struct issue_thread_context {
    uint8_t session[16];
    uint8_t challenge[60];
} issue_thread_context;

static DWORD WINAPI issue_thread(void *context)
{
    issue_thread_context *issue = (issue_thread_context *)context;

    return ul_plugin_issue(100, issue->session, 0, issue->challenge) ? 1u : 0u;
}

static DWORD WINAPI close_thread(void *unused)
{
    (void)unused;
    ul_plugin_close();
    return 0;
}

static bool bytes_are_zero(const uint8_t *bytes, size_t size)
{
    size_t index;

    for (index = 0; index < size; ++index) {
        if (bytes[index] != 0)
            return false;
    }
    return true;
}

static int scenario_pin_failure(void)
{
    ul_plugin_snapshot snapshot;
    uint8_t challenge[60];
    uint8_t session[16] = {1};
    int failures = 0;

    fake_pin = false;
    failures += check(!ul_plugin_start(), "pin failure rejected start");
    failures += check(!ul_plugin_start(), "pin failure permanently closes");
    snapshot = ul_plugin_get_status();
    failures += check(snapshot.status == UL_PLUGIN_CLOSED,
                      "pin failure remains closed");
    failures += check(!ul_plugin_issue(100, session, 0, challenge),
                      "late issue rejected");
    ul_plugin_close();
    return failures;
}

static int scenario_reload_and_close(void)
{
    ul_plugin_snapshot snapshot;
    bool saved = true;
    int failures = 0;

    failures += check(ul_plugin_start(), "first start succeeds");
    failures += check(!ul_plugin_start(), "second start rejected");
    snapshot = ul_plugin_get_status();
    failures += check(snapshot.status == UL_PLUGIN_UNPAIRED &&
                          snapshot.owns_store,
                      "unpaired owner snapshot");
    ul_plugin_stop_accepting();
    snapshot = ul_plugin_get_status();
    failures += check(snapshot.status == UL_PLUGIN_CLOSED &&
                          InterlockedCompareExchange(&fake_store_destroy_count,
                                                     0, 0) == 0,
                      "stop accepting is nonblocking and retains cleanup");
    ul_plugin_stop_accepting();
    ul_plugin_close();
    failures += check(InterlockedCompareExchange(&fake_store_destroy_count,
                                                 0, 0) == 1,
                      "close cleans runtime after staged stop");
    failures += check(!ul_plugin_start(), "restart after close rejected");
    failures += check(ul_plugin_pair(L"C:\\x", false, &saved) ==
                          UL_PAIRING_CANCELLED &&
                          !saved,
                      "late pair rejected and output cleared");
    snapshot = ul_plugin_get_status();
    failures += check(snapshot.status == UL_PLUGIN_CLOSED &&
                          !snapshot.owns_store && !snapshot.admission_pending,
                      "closed snapshot stable");
    return failures;
}

static int scenario_close_fallback(void)
{
    int failures = 0;

    failures += check(ul_plugin_start(), "fallback start");
    ul_plugin_close();
    failures += check(InterlockedCompareExchange(&fake_store_destroy_count,
                                                 0, 0) == 1,
                      "close directly stops and cleans runtime");
    return failures;
}

static int scenario_start_states(void)
{
    ul_plugin_snapshot snapshot;
    int failures = 0;

    fake_claim_result = UL_PAIRING_IN_USE;
    failures += check(ul_plugin_start(), "in-use start exposes status");
    snapshot = ul_plugin_get_status();
    failures += check(snapshot.status == UL_PLUGIN_IN_USE &&
                          snapshot.storage_result == UL_PAIRING_IN_USE &&
                          !snapshot.owns_store,
                      "in-use snapshot");
    ul_plugin_close();
    return failures;
}

static int scenario_pair_phases(void)
{
    ul_plugin_snapshot snapshot;
    uint8_t challenge[60];
    uint8_t proof[32] = {0x44};
    uint8_t session[16] = {1};
    bool saved = true;
    int failures = 0;

    failures += check(ul_plugin_start(), "pair start");
    fake_generate_result = UL_PAIRING_IO_ERROR;
    failures += check(ul_plugin_pair(L"C:\\x", false, &saved) ==
                          UL_PAIRING_IO_ERROR &&
                          !saved,
                      "precommit create failure not saved");
    snapshot = ul_plugin_get_status();
    failures += check(snapshot.status == UL_PLUGIN_UNPAIRED,
                      "precommit failure keeps old state");
    fake_generate_result = UL_PAIRING_OK;
    fake_export_result = UL_PAIRING_IO_ERROR;
    failures += check(ul_plugin_pair(L"C:\\x", false, &saved) ==
                          UL_PAIRING_IO_ERROR &&
                          saved,
                      "export failure reports durable save");
    snapshot = ul_plugin_get_status();
    failures += check(snapshot.status == UL_PLUGIN_PAIRED &&
                          snapshot.storage_result == UL_PAIRING_IO_ERROR,
                      "export failure leaves paired status");
    fake_generate_result = UL_PAIRING_CRYPTO_ERROR;
    saved = true;
    failures += check(ul_plugin_issue(100, session, 0, challenge),
                      "issue remains available before failed replace");
    failures += check(ul_plugin_pair(L"C:\\y", true, &saved) ==
                          UL_PAIRING_CRYPTO_ERROR &&
                          !saved,
                      "precommit replace failure not saved");
    snapshot = ul_plugin_get_status();
    failures += check(snapshot.status == UL_PLUGIN_PAIRED,
                      "failed replace restores old authorizer");
    failures += check(ul_plugin_prepare(challenge, sizeof(challenge), proof,
                                        sizeof(proof)),
                      "failed replace preserves current generation");
    fake_generate_result = UL_PAIRING_POSTCOMMIT_INVALID;
    saved = true;
    failures += check(ul_plugin_pair(L"C:\\z", true, &saved) ==
                          UL_PAIRING_POSTCOMMIT_INVALID &&
                          !saved,
                      "postcommit uncertainty is not reported saved");
    snapshot = ul_plugin_get_status();
    failures += check(snapshot.status == UL_PLUGIN_STORAGE_ERROR &&
                          snapshot.storage_result ==
                              UL_PAIRING_POSTCOMMIT_INVALID,
                      "postcommit uncertainty disables authorization");
    ul_plugin_close();
    return failures;
}

static int scenario_prepare_and_forget(void)
{
    uint8_t challenge[60];
    uint8_t proof[32] = {0x44};
    uint8_t session[16] = {1};
    ul_plugin_snapshot snapshot;
    int failures = 0;

    fake_load_result = UL_PAIRING_OK;
    failures += check(ul_plugin_start(), "paired start");
    failures += check(ul_plugin_issue(100, session, 3, challenge),
                      "issue challenge");
    failures += check(!ul_plugin_prepare(NULL, 0, NULL, 0),
                      "malformed prepare rejected");
    failures += check(!ul_plugin_prepare(challenge, sizeof(challenge), proof,
                                         sizeof(proof)),
                      "malformed prepare consumed challenge");
    failures += check(ul_plugin_issue(100, session, 3, challenge),
                      "fresh issue after consumption");
    failures += check(ul_plugin_prepare(challenge, sizeof(challenge), proof,
                                        sizeof(proof)),
                      "prepare starts worker");
    snapshot = ul_plugin_get_status();
    failures += check(snapshot.admission_pending, "worker published pending");
    fake_forget_result = UL_PAIRING_IO_ERROR;
    failures += check(ul_plugin_forget() == UL_PAIRING_IO_ERROR,
                      "forget reports durable deletion failure");
    snapshot = ul_plugin_get_status();
    failures += check(snapshot.status == UL_PLUGIN_STORAGE_ERROR &&
                          !snapshot.admission_pending,
                      "failed forget remains revoked and idle");
    failures += check(!ul_plugin_issue(100, session, 3, challenge),
                      "failed forget cannot restore dispatch");
    fake_forget_result = UL_PAIRING_OK;
    failures += check(ul_plugin_forget() == UL_PAIRING_OK,
                      "forget retry succeeds");
    snapshot = ul_plugin_get_status();
    failures += check(snapshot.status == UL_PLUGIN_UNPAIRED,
                      "forget retry publishes unpaired");
    failures += check(InterlockedCompareExchange(&fake_destroy_count, 0, 0) > 0,
                      "forget destroyed revoked generation");
    ul_plugin_close();
    return failures;
}

static int scenario_worker_expiry(void)
{
    uint8_t challenge[60];
    uint8_t proof[32] = {0x44};
    uint8_t session[16] = {1};
    ul_plugin_snapshot snapshot;
    ULONGLONG deadline;
    int failures = 0;

    fake_load_result = UL_PAIRING_OK;
    failures += check(ul_plugin_start(), "expiry start");
    failures += check(ul_plugin_issue(100, session, 0, challenge) &&
                          ul_plugin_prepare(challenge, sizeof(challenge), proof,
                                            sizeof(proof)),
                      "expiry prepare");
    deadline = GetTickCount64() + 2000;
    do {
        snapshot = ul_plugin_get_status();
        if (!snapshot.admission_pending)
            break;
        Sleep(2);
    } while (GetTickCount64() < deadline);
    failures += check(!snapshot.admission_pending,
                      "READY worker autonomously expires");
    deadline = GetTickCount64() + 2000;
    while (InterlockedCompareExchange(&fake_release_count, 0, 0) == 0 &&
           GetTickCount64() < deadline) {
        (void)ul_plugin_get_status();
        Sleep(1);
    }
    failures += check(InterlockedCompareExchange(&fake_release_count, 0, 0) == 1,
                      "status reaps completed worker once");
    ul_plugin_close();
    return failures;
}

static int scenario_close_cancels_mutation(void)
{
    HANDLE thread;
    DWORD wait_result;
    DWORD exit_code = UL_PAIRING_IO_ERROR;
    int failures = 0;

    fake_load_result = UL_PAIRING_OK;
    fake_block_export = true;
    fake_export_entered = CreateEventW(NULL, TRUE, FALSE, NULL);
    failures += check(fake_export_entered != NULL && ul_plugin_start(),
                      "mutation start");
    if (failures != 0)
        return failures;
    thread = CreateThread(NULL, 0, export_thread, NULL, 0, NULL);
    failures += check(thread != NULL, "create mutation thread");
    failures += check(WaitForSingleObject(fake_export_entered, 2000) ==
                          WAIT_OBJECT_0,
                      "mutation entered store");
    ul_plugin_close();
    wait_result = WaitForSingleObject(thread, 2000);
    failures += check(wait_result == WAIT_OBJECT_0,
                      "close drains cancelled mutation");
    if (wait_result != WAIT_OBJECT_0)
        ExitProcess(1);
    failures += check(GetExitCodeThread(thread, &exit_code) &&
                          exit_code == UL_PAIRING_CANCELLED,
                      "drained mutation observed cancellation");
    CloseHandle(thread);
    CloseHandle(fake_export_entered);
    return failures;
}

static int scenario_close_drains_issue(void)
{
    issue_thread_context issue = {{1}, {0}};
    uint8_t late_challenge[60];
    uint8_t late_session[16] = {2};
    ul_plugin_snapshot snapshot;
    HANDLE dispatch = NULL;
    HANDLE closing = NULL;
    ULONGLONG deadline;
    DWORD dispatch_exit = 0;
    DWORD close_exit = 1;
    DWORD wait_result;
    int failures = 0;

    fake_load_result = UL_PAIRING_OK;
    fake_block_issue = true;
    fake_issue_entered = CreateEventW(NULL, TRUE, FALSE, NULL);
    fake_issue_release = CreateEventW(NULL, TRUE, FALSE, NULL);
    failures += check(fake_issue_entered != NULL && fake_issue_release != NULL &&
                          ul_plugin_start(),
                      "dispatch drain start");
    if (failures != 0) {
        if (fake_issue_entered != NULL)
            CloseHandle(fake_issue_entered);
        if (fake_issue_release != NULL)
            CloseHandle(fake_issue_release);
        return failures;
    }

    dispatch = CreateThread(NULL, 0, issue_thread, &issue, 0, NULL);
    failures += check(dispatch != NULL, "create blocked dispatch thread");
    if (dispatch == NULL) {
        ul_plugin_close();
        CloseHandle(fake_issue_entered);
        CloseHandle(fake_issue_release);
        return failures;
    }
    wait_result = WaitForSingleObject(fake_issue_entered, 2000);
    failures += check(wait_result == WAIT_OBJECT_0,
                      "public dispatch entered authorizer");
    if (wait_result != WAIT_OBJECT_0) {
        SetEvent(fake_issue_release);
        if (WaitForSingleObject(dispatch, 2000) != WAIT_OBJECT_0)
            ExitProcess(1);
        ul_plugin_close();
        CloseHandle(dispatch);
        CloseHandle(fake_issue_entered);
        CloseHandle(fake_issue_release);
        return failures;
    }

    closing = CreateThread(NULL, 0, close_thread, NULL, 0, NULL);
    failures += check(closing != NULL, "create close thread");
    if (closing == NULL) {
        SetEvent(fake_issue_release);
        if (WaitForSingleObject(dispatch, 2000) != WAIT_OBJECT_0)
            ExitProcess(1);
        ul_plugin_close();
        CloseHandle(dispatch);
        CloseHandle(fake_issue_entered);
        CloseHandle(fake_issue_release);
        return failures;
    }

    deadline = GetTickCount64() + 2000;
    do {
        snapshot = ul_plugin_get_status();
        if (snapshot.status == UL_PLUGIN_CLOSED)
            break;
        Sleep(1);
    } while (GetTickCount64() < deadline);
    failures += check(snapshot.status == UL_PLUGIN_CLOSED,
                      "close shuts gate during in-flight dispatch");
    failures += check(WaitForSingleObject(closing, 50) == WAIT_TIMEOUT,
                      "close waits for in-flight dispatch");

    memset(late_challenge, 0xa5, sizeof(late_challenge));
    failures += check(!ul_plugin_issue(101, late_session, 0, late_challenge),
                      "closed gate refuses late dispatch");
    failures += check(bytes_are_zero(late_challenge, sizeof(late_challenge)),
                      "late dispatch returns zero challenge");

    SetEvent(fake_issue_release);
    wait_result = WaitForSingleObject(dispatch, 2000);
    failures += check(wait_result == WAIT_OBJECT_0,
                      "in-flight dispatch drains after release");
    if (wait_result != WAIT_OBJECT_0)
        ExitProcess(1);
    wait_result = WaitForSingleObject(closing, 2000);
    failures += check(wait_result == WAIT_OBJECT_0,
                      "close completes after dispatch drain");
    if (wait_result != WAIT_OBJECT_0)
        ExitProcess(1);
    failures += check(GetExitCodeThread(dispatch, &dispatch_exit) &&
                          dispatch_exit == 1,
                      "in-flight dispatch completes before destruction");
    failures += check(GetExitCodeThread(closing, &close_exit) && close_exit == 0,
                      "close thread exits successfully");
    snapshot = ul_plugin_get_status();
    failures += check(snapshot.status == UL_PLUGIN_CLOSED &&
                          !snapshot.owns_store && !snapshot.admission_pending,
                      "drained runtime remains closed");
    failures += check(InterlockedCompareExchange(&fake_destroy_count, 0, 0) == 1,
                      "authorizer destroyed once after dispatch");
    failures += check(
        InterlockedCompareExchange(&fake_store_destroy_count, 0, 0) == 1,
        "store destroyed once after dispatch");

    CloseHandle(dispatch);
    CloseHandle(closing);
    CloseHandle(fake_issue_entered);
    CloseHandle(fake_issue_release);
    return failures;
}

static int run_child(const char *scenario)
{
    if (strcmp(scenario, "pin") == 0)
        return scenario_pin_failure();
    if (strcmp(scenario, "reload") == 0)
        return scenario_reload_and_close();
    if (strcmp(scenario, "fallback") == 0)
        return scenario_close_fallback();
    if (strcmp(scenario, "states") == 0)
        return scenario_start_states();
    if (strcmp(scenario, "pair") == 0)
        return scenario_pair_phases();
    if (strcmp(scenario, "prepare") == 0)
        return scenario_prepare_and_forget();
    if (strcmp(scenario, "expiry") == 0)
        return scenario_worker_expiry();
    if (strcmp(scenario, "cancel") == 0)
        return scenario_close_cancels_mutation();
    if (strcmp(scenario, "dispatch") == 0)
        return scenario_close_drains_issue();
    return 1;
}

static int spawn_scenario(const wchar_t *executable, const wchar_t *scenario)
{
    STARTUPINFOW startup;
    PROCESS_INFORMATION process;
    wchar_t command[32768];
    DWORD exit_code = 1;

    SecureZeroMemory(&startup, sizeof(startup));
    SecureZeroMemory(&process, sizeof(process));
    SecureZeroMemory(command, sizeof(command));
    startup.cb = sizeof(startup);
    if (_snwprintf(command, 32768, L"\"%ls\" %ls", executable, scenario) < 0)
        return 1;
    if (!CreateProcessW(executable, command, NULL, NULL, FALSE, 0, NULL, NULL,
                        &startup, &process))
        return 1;
    if (WaitForSingleObject(process.hProcess, 10000) != WAIT_OBJECT_0)
        ExitProcess(1);
    if (!GetExitCodeProcess(process.hProcess, &exit_code))
        exit_code = 1;
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return exit_code == 0 ? 0 : 1;
}

int main(int argc, char **argv)
{
    static const wchar_t *scenarios[] = {
        L"pin", L"reload", L"fallback", L"states", L"pair", L"prepare",
        L"expiry", L"cancel", L"dispatch"};
    wchar_t executable[32768];
    size_t index;
    int failures = 0;

    if (argc == 2)
        return run_child(argv[1]) == 0 ? 0 : 1;
    if (GetModuleFileNameW(NULL, executable, 32768) == 0)
        return 1;
    for (index = 0; index < sizeof(scenarios) / sizeof(scenarios[0]); ++index)
        failures += spawn_scenario(executable, scenarios[index]);
    if (failures == 0)
        puts("plugin state tests passed");
    return failures == 0 ? 0 : 1;
}
