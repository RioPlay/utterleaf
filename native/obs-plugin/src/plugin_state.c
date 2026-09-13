// SPDX-License-Identifier: GPL-2.0-or-later
#include "plugin_state.h"

#include <windows.h>

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifndef UL_PLUGIN_AUTH_TIMEOUT_MS
#define UL_PLUGIN_AUTH_TIMEOUT_MS 15000u
#endif

#ifndef UL_PLUGIN_READY_TIMEOUT_MS
#define UL_PLUGIN_READY_TIMEOUT_MS 15000u
#endif

typedef struct ul_plugin_runtime {
    SRWLOCK operation_lock;
    HANDLE leases_zero;
    volatile LONG leases;
    volatile LONG closing;
    volatile LONG mutation_active;
    ul_pairing_cancel mutation_cancel;
    ul_pairing_store *store;
    ul_authorizer *authorizer;
    HANDLE worker;
    HANDLE worker_cancel;
    ul_admission *worker_admission;
    volatile LONG worker_active;
    ul_plugin_status status;
    ul_pairing_result storage_result;
    bool owns_store;
} ul_plugin_runtime;

typedef struct ul_plugin_global {
    SRWLOCK lock;
    volatile LONG started;
    ul_plugin_runtime *runtime;
    ul_plugin_snapshot snapshot;
} ul_plugin_global;

static ul_plugin_global plugin_global = {
    SRWLOCK_INIT,
    0,
    NULL,
    {UL_PLUGIN_CLOSED, UL_PAIRING_CANCELLED, false, false}};

static void publish_runtime(ul_plugin_runtime *runtime)
{
    AcquireSRWLockExclusive(&plugin_global.lock);
    if (plugin_global.runtime == runtime &&
        InterlockedCompareExchange(&plugin_global.started, 0, 0) == 1) {
        plugin_global.snapshot.status = runtime->status;
        plugin_global.snapshot.storage_result = runtime->storage_result;
        plugin_global.snapshot.owns_store = runtime->owns_store;
        plugin_global.snapshot.admission_pending =
            InterlockedCompareExchange(&runtime->worker_active, 0, 0) != 0;
    }
    ReleaseSRWLockExclusive(&plugin_global.lock);
}

static ul_plugin_runtime *runtime_acquire(void)
{
    ul_plugin_runtime *runtime = NULL;

    AcquireSRWLockShared(&plugin_global.lock);
    if (InterlockedCompareExchange(&plugin_global.started, 0, 0) == 1 &&
        plugin_global.runtime != NULL &&
        InterlockedCompareExchange(&plugin_global.runtime->closing, 0, 0) == 0) {
        runtime = plugin_global.runtime;
        if (InterlockedIncrement(&runtime->leases) == 1)
            ResetEvent(runtime->leases_zero);
    }
    ReleaseSRWLockShared(&plugin_global.lock);
    return runtime;
}

static void runtime_release(ul_plugin_runtime *runtime)
{
    if (InterlockedDecrement(&runtime->leases) == 0)
        SetEvent(runtime->leases_zero);
}

static void mutation_begin(ul_plugin_runtime *runtime)
{
    ul_pairing_cancel_init(&runtime->mutation_cancel);
    InterlockedExchange(&runtime->mutation_active, 1);
    if (InterlockedCompareExchange(&runtime->closing, 0, 0) != 0)
        ul_pairing_cancel_request(&runtime->mutation_cancel);
}

static void mutation_end(ul_plugin_runtime *runtime)
{
    InterlockedExchange(&runtime->mutation_active, 0);
}

static DWORD WINAPI admission_worker(void *context)
{
    ul_plugin_runtime *runtime = (ul_plugin_runtime *)context;
    ul_admission *admission = runtime->worker_admission;
    HANDLE pipe = NULL;
    int result;

    result = ul_admission_authenticate(admission, UL_PLUGIN_AUTH_TIMEOUT_MS);
    if (result == UL_ADMISSION_AUTH_OK) {
        pipe = ul_admission_pipe(admission);
        (void)WaitForSingleObject(runtime->worker_cancel,
                                  UL_PLUGIN_READY_TIMEOUT_MS);
    }
    ul_admission_cancel(admission);
    if (pipe != NULL && pipe != INVALID_HANDLE_VALUE)
        (void)DisconnectNamedPipe(pipe);
    InterlockedExchange(&runtime->worker_active, 0);
    publish_runtime(runtime);
    return (DWORD)result;
}

/* operation_lock is held. */
static bool reap_worker(ul_plugin_runtime *runtime)
{
    DWORD wait_result;

    if (runtime->worker == NULL)
        return true;
    wait_result = WaitForSingleObject(runtime->worker, 0);
    if (wait_result == WAIT_TIMEOUT)
        return false;
    if (wait_result != WAIT_OBJECT_0)
        return false;
    CloseHandle(runtime->worker);
    runtime->worker = NULL;
    runtime->worker_admission = NULL;
    ul_authorizer_release(runtime->authorizer);
    ResetEvent(runtime->worker_cancel);
    return true;
}

/* operation_lock is held; this permanently retires the current generation. */
static void retire_authorizer(ul_plugin_runtime *runtime)
{
    if (runtime->authorizer == NULL)
        return;
    SetEvent(runtime->worker_cancel);
    ul_authorizer_revoke(runtime->authorizer);
    if (runtime->worker != NULL) {
        (void)WaitForSingleObject(runtime->worker, INFINITE);
        CloseHandle(runtime->worker);
        runtime->worker = NULL;
        runtime->worker_admission = NULL;
    }
    InterlockedExchange(&runtime->worker_active, 0);
    ul_authorizer_destroy(runtime->authorizer);
    runtime->authorizer = NULL;
    ResetEvent(runtime->worker_cancel);
}

bool ul_plugin_start(void)
{
    ul_plugin_runtime *runtime = NULL;
    HMODULE module = NULL;
    uint8_t key[UL_PAIRING_KEY_BYTES];
    ul_pairing_result result;

    SecureZeroMemory(key, sizeof(key));
    if (InterlockedCompareExchange(&plugin_global.started, 1, 0) != 0)
        return false;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_PIN |
                                GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,
                            (LPCWSTR)(const void *)&plugin_global, &module))
        goto permanent_failure;
    (void)module;
    runtime = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*runtime));
    if (runtime == NULL)
        goto permanent_failure;
    InitializeSRWLock(&runtime->operation_lock);
    runtime->leases_zero = CreateEventW(NULL, TRUE, TRUE, NULL);
    runtime->worker_cancel = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (runtime->leases_zero == NULL || runtime->worker_cancel == NULL)
        goto fail;
    result = ul_pairing_store_open(&runtime->store);
    if (result != UL_PAIRING_OK) {
        runtime->status = UL_PLUGIN_STORAGE_ERROR;
        runtime->storage_result = result;
        goto ready;
    }
    result = ul_pairing_store_claim_owner(runtime->store);
    if (result != UL_PAIRING_OK) {
        runtime->status = result == UL_PAIRING_IN_USE ? UL_PLUGIN_IN_USE
                                                     : UL_PLUGIN_STORAGE_ERROR;
        runtime->storage_result = result;
        ul_pairing_store_destroy(runtime->store);
        runtime->store = NULL;
        goto ready;
    }
    runtime->owns_store = true;
    result = ul_pairing_store_load(runtime->store, key);
    if (result == UL_PAIRING_OK) {
        runtime->authorizer = ul_authorizer_create(key);
        if (runtime->authorizer == NULL) {
            runtime->status = UL_PLUGIN_STORAGE_ERROR;
            runtime->storage_result = UL_PAIRING_IO_ERROR;
        } else {
            runtime->status = UL_PLUGIN_PAIRED;
            runtime->storage_result = UL_PAIRING_OK;
        }
    } else if (result == UL_PAIRING_MISSING) {
        runtime->status = UL_PLUGIN_UNPAIRED;
        runtime->storage_result = result;
    } else {
        runtime->status = UL_PLUGIN_STORAGE_ERROR;
        runtime->storage_result = result;
    }

ready:
    SecureZeroMemory(key, sizeof(key));
    AcquireSRWLockExclusive(&plugin_global.lock);
    if (InterlockedCompareExchange(&plugin_global.started, 0, 0) != 1) {
        ReleaseSRWLockExclusive(&plugin_global.lock);
        AcquireSRWLockExclusive(&runtime->operation_lock);
        retire_authorizer(runtime);
        if (runtime->store != NULL)
            ul_pairing_store_destroy(runtime->store);
        ReleaseSRWLockExclusive(&runtime->operation_lock);
        CloseHandle(runtime->worker_cancel);
        CloseHandle(runtime->leases_zero);
        SecureZeroMemory(runtime, sizeof(*runtime));
        HeapFree(GetProcessHeap(), 0, runtime);
        return false;
    }
    plugin_global.runtime = runtime;
    plugin_global.snapshot.status = runtime->status;
    plugin_global.snapshot.storage_result = runtime->storage_result;
    plugin_global.snapshot.owns_store = runtime->owns_store;
    plugin_global.snapshot.admission_pending = false;
    ReleaseSRWLockExclusive(&plugin_global.lock);
    return true;

fail:
    SecureZeroMemory(key, sizeof(key));
    if (runtime->worker_cancel != NULL)
        CloseHandle(runtime->worker_cancel);
    if (runtime->leases_zero != NULL)
        CloseHandle(runtime->leases_zero);
    SecureZeroMemory(runtime, sizeof(*runtime));
    HeapFree(GetProcessHeap(), 0, runtime);
permanent_failure:
    InterlockedExchange(&plugin_global.started, 2);
    return false;
}

void ul_plugin_stop_accepting(void)
{
    ul_plugin_runtime *runtime;

    AcquireSRWLockExclusive(&plugin_global.lock);
    InterlockedExchange(&plugin_global.started, 2);
    runtime = plugin_global.runtime;
    plugin_global.snapshot.status = UL_PLUGIN_CLOSED;
    plugin_global.snapshot.storage_result = UL_PAIRING_CANCELLED;
    plugin_global.snapshot.owns_store = false;
    plugin_global.snapshot.admission_pending = false;
    if (runtime != NULL)
        InterlockedExchange(&runtime->closing, 1);
    ReleaseSRWLockExclusive(&plugin_global.lock);
    if (runtime == NULL)
        return;
    if (InterlockedCompareExchange(&runtime->mutation_active, 0, 0) != 0)
        ul_pairing_cancel_request(&runtime->mutation_cancel);
    SetEvent(runtime->worker_cancel);
}

void ul_plugin_close(void)
{
    ul_plugin_runtime *runtime;

    ul_plugin_stop_accepting();
    AcquireSRWLockExclusive(&plugin_global.lock);
    runtime = plugin_global.runtime;
    plugin_global.runtime = NULL;
    ReleaseSRWLockExclusive(&plugin_global.lock);
    if (runtime == NULL)
        return;

    AcquireSRWLockExclusive(&runtime->operation_lock);
    retire_authorizer(runtime);
    ReleaseSRWLockExclusive(&runtime->operation_lock);
    (void)WaitForSingleObject(runtime->leases_zero, INFINITE);
    AcquireSRWLockExclusive(&runtime->operation_lock);
    if (runtime->store != NULL)
        ul_pairing_store_destroy(runtime->store);
    runtime->store = NULL;
    ReleaseSRWLockExclusive(&runtime->operation_lock);
    CloseHandle(runtime->worker_cancel);
    CloseHandle(runtime->leases_zero);
    SecureZeroMemory(runtime, sizeof(*runtime));
    HeapFree(GetProcessHeap(), 0, runtime);
}

ul_plugin_snapshot ul_plugin_get_status(void)
{
    ul_plugin_snapshot snapshot;
    ul_plugin_runtime *runtime = runtime_acquire();

    if (runtime != NULL) {
        if (TryAcquireSRWLockExclusive(&runtime->operation_lock)) {
            (void)reap_worker(runtime);
            ReleaseSRWLockExclusive(&runtime->operation_lock);
        }
        runtime_release(runtime);
    }

    AcquireSRWLockShared(&plugin_global.lock);
    snapshot = plugin_global.snapshot;
    ReleaseSRWLockShared(&plugin_global.lock);
    return snapshot;
}

ul_pairing_result ul_plugin_pair(const wchar_t *destination, bool replace,
                                 bool *pairing_saved)
{
    ul_plugin_runtime *runtime;
    uint8_t key[UL_PAIRING_KEY_BYTES];
    ul_pairing_result result;

    if (pairing_saved != NULL)
        *pairing_saved = false;
    if (pairing_saved == NULL || destination == NULL)
        return UL_PAIRING_INVALID_ARGUMENT;
    runtime = runtime_acquire();
    if (runtime == NULL)
        return UL_PAIRING_CANCELLED;
    SecureZeroMemory(key, sizeof(key));
    AcquireSRWLockExclusive(&runtime->operation_lock);
    if (InterlockedCompareExchange(&runtime->closing, 0, 0) != 0) {
        result = UL_PAIRING_CANCELLED;
        goto cleanup;
    }
    if (!runtime->owns_store || runtime->store == NULL) {
        result = runtime->status == UL_PLUGIN_IN_USE ? UL_PAIRING_IN_USE
                                                    : runtime->storage_result;
        goto cleanup;
    }
    if (replace && runtime->status != UL_PLUGIN_PAIRED) {
        result = runtime->status == UL_PLUGIN_UNPAIRED
                     ? UL_PAIRING_MISSING
                     : runtime->storage_result;
        goto cleanup;
    }
    if (!replace && runtime->status != UL_PLUGIN_UNPAIRED) {
        result = runtime->status == UL_PLUGIN_PAIRED
                     ? UL_PAIRING_EXISTS
                     : runtime->storage_result;
        goto cleanup;
    }
    mutation_begin(runtime);
    result = replace ? ul_pairing_store_replace(runtime->store,
                                                 &runtime->mutation_cancel, key)
                     : ul_pairing_store_create(runtime->store,
                                                &runtime->mutation_cancel, key);
    mutation_end(runtime);
    if (result != UL_PAIRING_OK) {
        if (result == UL_PAIRING_POSTCOMMIT_INVALID) {
            retire_authorizer(runtime);
            runtime->status = UL_PLUGIN_STORAGE_ERROR;
            runtime->storage_result = result;
        } else {
            runtime->storage_result = result;
        }
        goto publish;
    }
    retire_authorizer(runtime);
    runtime->authorizer = ul_authorizer_create(key);
    SecureZeroMemory(key, sizeof(key));
    if (runtime->authorizer == NULL) {
        runtime->status = UL_PLUGIN_STORAGE_ERROR;
        runtime->storage_result = UL_PAIRING_IO_ERROR;
        result = UL_PAIRING_IO_ERROR;
        goto publish;
    }
    runtime->status = UL_PLUGIN_PAIRED;
    runtime->storage_result = UL_PAIRING_OK;
    *pairing_saved = true;
    if (InterlockedCompareExchange(&runtime->closing, 0, 0) != 0) {
        result = UL_PAIRING_CANCELLED;
        goto publish;
    }
    mutation_begin(runtime);
    result = ul_pairing_store_export(runtime->store, destination,
                                     &runtime->mutation_cancel);
    mutation_end(runtime);
    runtime->storage_result = result;

publish:
    publish_runtime(runtime);
cleanup:
    SecureZeroMemory(key, sizeof(key));
    ReleaseSRWLockExclusive(&runtime->operation_lock);
    runtime_release(runtime);
    return result;
}

ul_pairing_result ul_plugin_export(const wchar_t *destination)
{
    ul_plugin_runtime *runtime;
    ul_pairing_result result;

    if (destination == NULL)
        return UL_PAIRING_INVALID_ARGUMENT;
    runtime = runtime_acquire();
    if (runtime == NULL)
        return UL_PAIRING_CANCELLED;
    AcquireSRWLockExclusive(&runtime->operation_lock);
    if (InterlockedCompareExchange(&runtime->closing, 0, 0) != 0) {
        result = UL_PAIRING_CANCELLED;
    } else if (!runtime->owns_store || runtime->store == NULL) {
        result = runtime->status == UL_PLUGIN_IN_USE ? UL_PAIRING_IN_USE
                                                    : runtime->storage_result;
    } else if (runtime->status != UL_PLUGIN_PAIRED) {
        result = runtime->status == UL_PLUGIN_UNPAIRED
                     ? UL_PAIRING_MISSING
                     : runtime->storage_result;
    } else {
        mutation_begin(runtime);
        result = ul_pairing_store_export(runtime->store, destination,
                                         &runtime->mutation_cancel);
        mutation_end(runtime);
        runtime->storage_result = result;
        publish_runtime(runtime);
    }
    ReleaseSRWLockExclusive(&runtime->operation_lock);
    runtime_release(runtime);
    return result;
}

ul_pairing_result ul_plugin_forget(void)
{
    ul_plugin_runtime *runtime = runtime_acquire();
    ul_pairing_result result;

    if (runtime == NULL)
        return UL_PAIRING_CANCELLED;
    AcquireSRWLockExclusive(&runtime->operation_lock);
    if (InterlockedCompareExchange(&runtime->closing, 0, 0) != 0) {
        result = UL_PAIRING_CANCELLED;
        goto cleanup;
    }
    if (!runtime->owns_store || runtime->store == NULL) {
        result = runtime->status == UL_PLUGIN_IN_USE ? UL_PAIRING_IN_USE
                                                    : runtime->storage_result;
        goto cleanup;
    }
    retire_authorizer(runtime);
    mutation_begin(runtime);
    result = ul_pairing_store_forget(runtime->store);
    mutation_end(runtime);
    if (result == UL_PAIRING_OK || result == UL_PAIRING_MISSING) {
        runtime->status = UL_PLUGIN_UNPAIRED;
    } else {
        runtime->status = UL_PLUGIN_STORAGE_ERROR;
    }
    runtime->storage_result = result;
    publish_runtime(runtime);

cleanup:
    ReleaseSRWLockExclusive(&runtime->operation_lock);
    runtime_release(runtime);
    return result;
}

bool ul_plugin_issue(
    DWORD client_pid, const uint8_t session[16], uint8_t additional_mix_mask,
    uint8_t out_challenge[UL_AUTHORIZATION_CHALLENGE_BYTES])
{
    ul_plugin_runtime *runtime;
    bool success = false;

    if (out_challenge == NULL)
        return false;
    SecureZeroMemory(out_challenge, UL_AUTHORIZATION_CHALLENGE_BYTES);
    runtime = runtime_acquire();
    if (runtime == NULL)
        return false;
    if (!TryAcquireSRWLockExclusive(&runtime->operation_lock)) {
        runtime_release(runtime);
        return false;
    }
    if (InterlockedCompareExchange(&runtime->closing, 0, 0) == 0 &&
        runtime->status == UL_PLUGIN_PAIRED && runtime->owns_store &&
        runtime->authorizer != NULL && reap_worker(runtime) &&
        runtime->worker == NULL) {
        success = ul_authorizer_issue(runtime->authorizer, client_pid, session,
                                      additional_mix_mask, out_challenge);
    }
    ReleaseSRWLockExclusive(&runtime->operation_lock);
    runtime_release(runtime);
    return success;
}

bool ul_plugin_prepare(const uint8_t *challenge, size_t challenge_size,
                       const uint8_t *proof, size_t proof_size)
{
    ul_plugin_runtime *runtime = runtime_acquire();
    ul_prepare_options options;
    ul_admission *admission;
    bool success = false;

    SecureZeroMemory(&options, sizeof(options));
    if (runtime == NULL)
        return false;
    if (!TryAcquireSRWLockExclusive(&runtime->operation_lock)) {
        runtime_release(runtime);
        return false;
    }
    if (InterlockedCompareExchange(&runtime->closing, 0, 0) != 0 ||
        runtime->status != UL_PLUGIN_PAIRED || !runtime->owns_store ||
        runtime->authorizer == NULL || !reap_worker(runtime) ||
        runtime->worker != NULL)
        goto cleanup;
    admission = ul_authorizer_prepare(runtime->authorizer, challenge,
                                      challenge_size, proof, proof_size,
                                      &options);
    SecureZeroMemory(&options, sizeof(options));
    if (admission == NULL ||
        InterlockedCompareExchange(&runtime->closing, 0, 0) != 0)
        goto cleanup;
    ResetEvent(runtime->worker_cancel);
    runtime->worker_admission = admission;
    InterlockedExchange(&runtime->worker_active, 1);
    runtime->worker = CreateThread(NULL, 0, admission_worker, runtime, 0, NULL);
    if (runtime->worker == NULL) {
        InterlockedExchange(&runtime->worker_active, 0);
        runtime->worker_admission = NULL;
        ul_authorizer_release(runtime->authorizer);
        goto cleanup;
    }
    publish_runtime(runtime);
    success = true;

cleanup:
    SecureZeroMemory(&options, sizeof(options));
    ReleaseSRWLockExclusive(&runtime->operation_lock);
    runtime_release(runtime);
    return success;
}
