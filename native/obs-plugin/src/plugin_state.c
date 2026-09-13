// SPDX-License-Identifier: GPL-2.0-or-later
#include "plugin_state.h"
#include "session_protocol.h"
#include "audio_stream.h"

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

#ifndef UL_PLUGIN_START_TIMEOUT_MS
#define UL_PLUGIN_START_TIMEOUT_MS 30000u
#endif

#ifndef UL_PLUGIN_CAPTURE_TIMEOUT_MS
#define UL_PLUGIN_CAPTURE_TIMEOUT_MS 5000u
#endif
#ifndef UL_PLUGIN_COMMAND_TIMEOUT_MS
#define UL_PLUGIN_COMMAND_TIMEOUT_MS 1000u
#endif

typedef struct ul_plugin_runtime {
    SRWLOCK operation_lock;
    SRWLOCK session_lock;
    HANDLE leases_zero;
    volatile LONG leases;
    volatile LONG closing;
    volatile LONG mutation_active;
    ul_pairing_cancel mutation_cancel;
    ul_pairing_store *store;
    ul_authorizer *authorizer;
    HANDLE worker;
    HANDLE worker_cancel;
    HANDLE arm_result;
    HANDLE capture_result;
    HANDLE cleanup_complete;
    HANDLE stream_stop;
    ul_admission *worker_admission;
    ul_prepare_options session_options;
    uintptr_t session_generation;
    uint64_t stream_epoch;
    uint64_t pending_epoch;
    ULONGLONG ready_started;
    ULONGLONG stream_starting_at;
    ULONGLONG stream_started_at;
    ul_session_phase session_phase;
    ul_arm_scheduler schedule_arm;
    ul_arm_scheduler schedule_capture;
    ul_arm_scheduler schedule_cleanup;
    ul_audio_capture_spec capture_spec;
    ul_audio_capture *capture;
    bool capture_spec_ready;
    bool capture_spec_valid;
    bool capture_attach_done;
    bool capture_attached;
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

/* session_lock is held; never joins or acquires operation_lock. Admission is
 * removed under this same lock before the authorizer can destroy it. */
static void session_cancel_locked(ul_plugin_runtime *runtime)
{
    runtime->session_phase = UL_SESSION_TERMINAL;
    SetEvent(runtime->worker_cancel);
    SetEvent(runtime->arm_result);
    SetEvent(runtime->capture_result);
    SetEvent(runtime->cleanup_complete);
    if (runtime->capture != NULL)
        ul_audio_capture_deactivate(runtime->capture);
    if (runtime->worker_admission != NULL)
        ul_admission_cancel(runtime->worker_admission);
}

static void session_cancel(ul_plugin_runtime *runtime)
{
    AcquireSRWLockExclusive(&runtime->session_lock);
    session_cancel_locked(runtime);
    ReleaseSRWLockExclusive(&runtime->session_lock);
}

static void session_release(ul_plugin_runtime *runtime)
{
    AcquireSRWLockExclusive(&runtime->session_lock);
    runtime->worker_admission = NULL;
    runtime->session_phase = UL_SESSION_NONE;
    runtime->capture_spec_ready = runtime->capture_spec_valid = false;
    runtime->capture_attach_done = runtime->capture_attached = false;
    SecureZeroMemory(&runtime->capture_spec, sizeof(runtime->capture_spec));
    SecureZeroMemory(&runtime->session_options, sizeof(runtime->session_options));
    ReleaseSRWLockExclusive(&runtime->session_lock);
}

static DWORD ready_remaining(ULONGLONG started)
{
    ULONGLONG elapsed = GetTickCount64() - started;
    return elapsed >= UL_PLUGIN_READY_TIMEOUT_MS ? 0u :
           UL_PLUGIN_READY_TIMEOUT_MS - (DWORD)elapsed;
}

static ul_audio_disarm_action request_disarm_runtime(
    ul_plugin_runtime *runtime, bool *was_attached)
{
    ul_arm_scheduler cleanup = NULL;
    uintptr_t generation = 0u;
    ul_audio_disarm_action action = UL_AUDIO_DISARM_REJECTED;
    AcquireSRWLockExclusive(&runtime->session_lock);
    if (was_attached != NULL)
        *was_attached = false;
    if (runtime->session_phase == UL_SESSION_STARTED &&
        InterlockedCompareExchange(&runtime->closing, 0, 0) == 0) {
        if (was_attached != NULL)
            *was_attached = runtime->capture_attached;
        runtime->session_phase = UL_SESSION_DISARMING;
        ResetEvent(runtime->cleanup_complete);
        cleanup = runtime->schedule_cleanup;
        generation = runtime->session_generation;
        action = UL_AUDIO_DISARM_ACCEPTED;
    } else if (runtime->session_phase == UL_SESSION_DRAINING) {
        action = UL_AUDIO_DISARM_ALREADY_STOPPING;
    }
    ReleaseSRWLockExclusive(&runtime->session_lock);
    if (action == UL_AUDIO_DISARM_ACCEPTED &&
        (cleanup == NULL || !cleanup(generation))) {
        session_cancel(runtime);
        return UL_AUDIO_DISARM_REJECTED;
    }
    return action;
}

static ul_audio_disarm_action request_disarm(void *context)
{
    return request_disarm_runtime(context, NULL);
}

static int read_disarm(ul_admission *admission, const uint8_t session[16])
{
    uint8_t command[UL_SESSION_COMMAND_BYTES];
    int result = ul_admission_read_exact(admission, command, sizeof(command),
                                         UL_PLUGIN_COMMAND_TIMEOUT_MS);
    if (result != UL_ADMISSION_AUTH_OK)
        return result;
    return ul_session_disarm_request(command, sizeof(command), session)
               ? UL_ADMISSION_AUTH_OK : UL_ADMISSION_REJECTED;
}

/* The worker owns the initial capture reference. Frontend attach takes an
 * independent reference and never borrows this runtime across OBS calls. */
static int capture_worker(ul_plugin_runtime *runtime, ul_admission *admission)
{
    ul_audio_capture_spec spec;
    ul_audio_capture *capture;
    ul_arm_scheduler attach, cleanup;
    uintptr_t generation;
    HANDLE waits[2] = {runtime->worker_cancel, runtime->capture_result};
    ULONGLONG started = GetTickCount64();
    ULONGLONG elapsed;
    DWORD waited;
    bool accepted;
    int result = UL_ADMISSION_REJECTED;

    AcquireSRWLockShared(&runtime->session_lock);
    spec = runtime->capture_spec;
    generation = runtime->session_generation;
    attach = runtime->schedule_capture;
    cleanup = runtime->schedule_cleanup;
    accepted = runtime->session_phase == UL_SESSION_STARTED &&
               runtime->capture_spec_ready && runtime->capture_spec_valid &&
               InterlockedCompareExchange(&runtime->closing, 0, 0) == 0;
    ReleaseSRWLockShared(&runtime->session_lock);
    if (!accepted || attach == NULL || cleanup == NULL)
        return UL_ADMISSION_REJECTED;
    capture = ul_audio_capture_create_worker(&spec);
    if (capture == NULL)
        return UL_ADMISSION_REJECTED;
    AcquireSRWLockExclusive(&runtime->session_lock);
    accepted = runtime->session_phase == UL_SESSION_STARTED &&
               runtime->session_generation == generation &&
               InterlockedCompareExchange(&runtime->closing, 0, 0) == 0;
    if (accepted) {
        runtime->capture = capture;
        runtime->capture_attach_done = runtime->capture_attached = false;
        ResetEvent(runtime->capture_result);
    }
    ReleaseSRWLockExclusive(&runtime->session_lock);
    if (!accepted || !attach(generation))
        goto done;
    for (;;) {
        DWORD available = 0u;
        DWORD slice;
        elapsed = GetTickCount64() - started;
        if (elapsed >= UL_PLUGIN_CAPTURE_TIMEOUT_MS) {
            result = UL_ADMISSION_TIMEOUT;
            goto done;
        }
        slice = UL_PLUGIN_CAPTURE_TIMEOUT_MS - (DWORD)elapsed;
        if (slice > 25u)
            slice = 25u;
        waited = WaitForMultipleObjects(2, waits, FALSE, slice);
        if (waited == WAIT_OBJECT_0) {
            result = UL_ADMISSION_CANCELLED;
            goto done;
        }
        if (waited == WAIT_OBJECT_0 + 1u)
            break;
        if (waited != WAIT_TIMEOUT) {
            result = UL_ADMISSION_CANCELLED;
            goto done;
        }
        result = ul_admission_probe(admission, &available);
        if (result != UL_ADMISSION_AUTH_OK)
            goto done;
        if (available != 0u) {
            ul_audio_disarm_action action;
            bool was_attached = false;
            result = read_disarm(admission, runtime->session_options.session);
            if (result != UL_ADMISSION_AUTH_OK)
                goto done;
            ul_audio_capture_deactivate(capture);
            action = request_disarm_runtime(runtime, &was_attached);
            if (action == UL_AUDIO_DISARM_REJECTED) {
                result = UL_ADMISSION_REJECTED;
                goto done;
            }
            if (action == UL_AUDIO_DISARM_ALREADY_STOPPING) {
                result = UL_ADMISSION_REJECTED;
                goto done;
            }
            result = was_attached
                ? ul_audio_stream_run_disarmed(
                      capture, &spec, admission,
                      runtime->session_options.session, runtime->stream_stop,
                      runtime->cleanup_complete)
                : ul_audio_stream_finish_empty_disarm(
                      admission, runtime->session_options.session,
                      runtime->cleanup_complete);
            result = result == UL_AUDIO_STREAM_OK ? UL_ADMISSION_AUTH_OK
                                                   : UL_ADMISSION_REJECTED;
            goto done;
        }
    }
    AcquireSRWLockShared(&runtime->session_lock);
    accepted = runtime->capture == capture && runtime->capture_attach_done &&
               runtime->capture_attached &&
               (runtime->session_phase == UL_SESSION_STARTED ||
                runtime->session_phase == UL_SESSION_DRAINING) &&
               InterlockedCompareExchange(&runtime->closing, 0, 0) == 0;
    ReleaseSRWLockShared(&runtime->session_lock);
    if (accepted) {
        int streamed = ul_audio_stream_run(capture, &spec, admission,
            runtime->session_options.session, runtime->stream_stop,
            runtime->cleanup_complete, request_disarm, runtime);
        result = streamed == UL_AUDIO_STREAM_OK ? UL_ADMISSION_AUTH_OK : UL_ADMISSION_REJECTED;
    }
done:
    ul_audio_capture_deactivate(capture);
    AcquireSRWLockExclusive(&runtime->session_lock);
    if (runtime->capture == capture)
        runtime->capture = NULL;
    ReleaseSRWLockExclusive(&runtime->session_lock);
    ul_audio_capture_release(capture);
    /* Posting never waits for the frontend, including when that thread is
     * joining us during revocation. A stale generation cannot detach new hooks. */
    (void)cleanup(generation);
    return result;
}

static int session_worker(ul_plugin_runtime *runtime, ul_admission *admission)
{
    uint8_t command[UL_SESSION_COMMAND_BYTES];
    ul_arm_scheduler scheduler;
    uintptr_t generation;
    HANDLE waits[2] = {runtime->worker_cancel, runtime->arm_result};
    ULONGLONG started = GetTickCount64();
    DWORD remaining, waited;
    bool accepted;
    int result;

    AcquireSRWLockExclusive(&runtime->session_lock);
    runtime->ready_started = started;
    ReleaseSRWLockExclusive(&runtime->session_lock);
    result = ul_admission_read_exact(admission, command, sizeof(command),
                                     UL_PLUGIN_READY_TIMEOUT_MS);
    if (result != UL_ADMISSION_AUTH_OK)
        return result;
    if (!ul_session_arm_request(command, sizeof(command),
            runtime->session_options.session,
            runtime->session_options.additional_mix_mask))
        return UL_ADMISSION_REJECTED;

    AcquireSRWLockExclusive(&runtime->session_lock);
    accepted = runtime->session_phase == UL_SESSION_READY &&
               InterlockedCompareExchange(&runtime->closing, 0, 0) == 0;
    scheduler = runtime->schedule_arm;
    generation = runtime->session_generation;
    if (accepted) {
        runtime->pending_epoch = runtime->stream_epoch;
        runtime->session_phase = UL_SESSION_ARM_PENDING;
    }
    ReleaseSRWLockExclusive(&runtime->session_lock);
    if (!accepted)
        return UL_ADMISSION_REJECTED;
    if (scheduler == NULL || !scheduler(generation)) {
        AcquireSRWLockExclusive(&runtime->session_lock);
        if (runtime->session_phase == UL_SESSION_ARM_PENDING) {
            runtime->session_phase = UL_SESSION_TERMINAL;
            SetEvent(runtime->arm_result);
        }
        ReleaseSRWLockExclusive(&runtime->session_lock);
    }
    remaining = ready_remaining(started);
    if (remaining == 0u)
        return UL_ADMISSION_TIMEOUT;
    waited = WaitForMultipleObjects(2, waits, FALSE, remaining);
    if (waited != WAIT_OBJECT_0 + 1u)
        return waited == WAIT_TIMEOUT ? UL_ADMISSION_TIMEOUT : UL_ADMISSION_CANCELLED;
    AcquireSRWLockShared(&runtime->session_lock);
    accepted = runtime->session_phase == UL_SESSION_ARMED ||
               runtime->session_phase == UL_SESSION_STARTING ||
               runtime->session_phase == UL_SESSION_STARTED;
    ReleaseSRWLockShared(&runtime->session_lock);
    remaining = ready_remaining(started);
    if (remaining == 0u)
        return UL_ADMISSION_TIMEOUT;
    if (!ul_session_arm_reply(runtime->session_options.session,
            runtime->session_options.additional_mix_mask, accepted, command))
        return UL_ADMISSION_REJECTED;
    result = ul_admission_write_all(admission, command, sizeof(command), remaining);
    if (result != UL_ADMISSION_AUTH_OK || !accepted)
        return result == UL_ADMISSION_AUTH_OK ? UL_ADMISSION_REJECTED : result;

    /* Armed waiting has no duration cutoff. Capture scheduling is reachable
     * only after the entire accepted Arm reply has been written above. */
    for (;;) {
        DWORD available = 0;
        bool start_expired = false;
        bool capture_ready = false;
        waited = WaitForSingleObject(runtime->worker_cancel, 50u);
        if (waited != WAIT_TIMEOUT)
            return UL_ADMISSION_CANCELLED;
        AcquireSRWLockExclusive(&runtime->session_lock);
        if (runtime->session_phase == UL_SESSION_STARTING &&
            GetTickCount64() - runtime->stream_starting_at >= UL_PLUGIN_START_TIMEOUT_MS) {
            session_cancel_locked(runtime);
            start_expired = true;
        }
        if (runtime->session_phase == UL_SESSION_STARTED) {
            capture_ready = runtime->capture_spec_ready;
            if (!capture_ready && GetTickCount64() - runtime->stream_started_at >=
                UL_PLUGIN_CAPTURE_TIMEOUT_MS) {
                session_cancel_locked(runtime);
                start_expired = true;
            }
        }
        ReleaseSRWLockExclusive(&runtime->session_lock);
        if (start_expired)
            return UL_ADMISSION_TIMEOUT;
        result = ul_admission_probe(admission, &available);
        if (result != UL_ADMISSION_AUTH_OK)
            return result;
        if (available != 0u) {
            result = read_disarm(admission, runtime->session_options.session);
            if (result != UL_ADMISSION_AUTH_OK)
                return result;
            AcquireSRWLockExclusive(&runtime->session_lock);
            accepted = (runtime->session_phase == UL_SESSION_ARMED ||
                        runtime->session_phase == UL_SESSION_STARTING ||
                        runtime->session_phase == UL_SESSION_STARTED) &&
                       runtime->capture == NULL &&
                       InterlockedCompareExchange(&runtime->closing, 0, 0) == 0;
            if (accepted)
                runtime->session_phase = UL_SESSION_DISARMING;
            ReleaseSRWLockExclusive(&runtime->session_lock);
            if (!accepted)
                return UL_ADMISSION_REJECTED;
            result = ul_audio_stream_finish_empty_disarm(
                admission, runtime->session_options.session, NULL);
            return result == UL_AUDIO_STREAM_OK ? UL_ADMISSION_AUTH_OK
                                                 : UL_ADMISSION_REJECTED;
        }
        if (capture_ready)
            return capture_worker(runtime, admission);
    }
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
        result = session_worker(runtime, admission);
    }
    session_cancel(runtime);
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
    session_release(runtime);
    ul_authorizer_release(runtime->authorizer);
    ResetEvent(runtime->worker_cancel);
    return true;
}

/* operation_lock is held; this permanently retires the current generation. */
static void retire_authorizer(ul_plugin_runtime *runtime)
{
    if (runtime->authorizer == NULL)
        return;
    session_cancel(runtime);
    ul_authorizer_revoke(runtime->authorizer);
    if (runtime->worker != NULL) {
        (void)WaitForSingleObject(runtime->worker, INFINITE);
        CloseHandle(runtime->worker);
        runtime->worker = NULL;
    }
    session_release(runtime);
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
    InitializeSRWLock(&runtime->session_lock);
    runtime->leases_zero = CreateEventW(NULL, TRUE, TRUE, NULL);
    runtime->worker_cancel = CreateEventW(NULL, TRUE, FALSE, NULL);
    runtime->arm_result = CreateEventW(NULL, TRUE, FALSE, NULL);
    runtime->capture_result = CreateEventW(NULL, TRUE, FALSE, NULL);
    runtime->cleanup_complete = CreateEventW(NULL, TRUE, FALSE, NULL);
    runtime->stream_stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (runtime->leases_zero == NULL || runtime->worker_cancel == NULL ||
        runtime->arm_result == NULL || runtime->capture_result == NULL ||
        runtime->cleanup_complete == NULL ||
        runtime->stream_stop == NULL)
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
        CloseHandle(runtime->arm_result);
        CloseHandle(runtime->capture_result);
        CloseHandle(runtime->cleanup_complete);
        CloseHandle(runtime->stream_stop);
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
    if (runtime->capture_result != NULL)
        CloseHandle(runtime->capture_result);
    if (runtime->cleanup_complete != NULL)
        CloseHandle(runtime->cleanup_complete);
    if (runtime->stream_stop != NULL)
        CloseHandle(runtime->stream_stop);
    if (runtime->arm_result != NULL)
        CloseHandle(runtime->arm_result);
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
    if (runtime != NULL) {
        InterlockedExchange(&runtime->closing, 1);
        session_cancel(runtime);
        if (InterlockedCompareExchange(&runtime->mutation_active, 0, 0) != 0)
            ul_pairing_cancel_request(&runtime->mutation_cancel);
    }
    ReleaseSRWLockExclusive(&plugin_global.lock);
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
    CloseHandle(runtime->arm_result);
    CloseHandle(runtime->capture_result);
    CloseHandle(runtime->cleanup_complete);
    CloseHandle(runtime->stream_stop);
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
        runtime->worker != NULL || runtime->session_generation == UINTPTR_MAX)
        goto cleanup;
    admission = ul_authorizer_prepare(runtime->authorizer, challenge,
                                      challenge_size, proof, proof_size,
                                      &options);
    if (admission == NULL ||
        InterlockedCompareExchange(&runtime->closing, 0, 0) != 0)
        goto cleanup;
    ResetEvent(runtime->worker_cancel);
    ResetEvent(runtime->arm_result);
    ResetEvent(runtime->capture_result);
    ResetEvent(runtime->cleanup_complete);
    ResetEvent(runtime->stream_stop);
    AcquireSRWLockExclusive(&runtime->session_lock);
    runtime->worker_admission = admission;
    runtime->session_options = options;
    runtime->session_generation++;
    runtime->session_phase = UL_SESSION_READY;
    ReleaseSRWLockExclusive(&runtime->session_lock);
    InterlockedExchange(&runtime->worker_active, 1);
    runtime->worker = CreateThread(NULL, 0, admission_worker, runtime, 0, NULL);
    if (runtime->worker == NULL) {
        InterlockedExchange(&runtime->worker_active, 0);
        session_release(runtime);
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

bool ul_plugin_set_arm_scheduler(ul_arm_scheduler scheduler)
{
    ul_plugin_runtime *runtime = runtime_acquire();
    bool accepted = false;
    if (runtime == NULL || scheduler == NULL) {
        if (runtime != NULL)
            runtime_release(runtime);
        return false;
    }
    AcquireSRWLockExclusive(&runtime->operation_lock);
    AcquireSRWLockExclusive(&runtime->session_lock);
    if (runtime->schedule_arm == NULL && runtime->worker == NULL &&
        InterlockedCompareExchange(&runtime->closing, 0, 0) == 0) {
        runtime->schedule_arm = scheduler;
        accepted = true;
    }
    ReleaseSRWLockExclusive(&runtime->session_lock);
    ReleaseSRWLockExclusive(&runtime->operation_lock);
    runtime_release(runtime);
    return accepted;
}

bool ul_plugin_set_capture_schedulers(ul_arm_scheduler attach,
                                      ul_arm_scheduler cleanup)
{
    ul_plugin_runtime *runtime = runtime_acquire();
    bool accepted = false;
    if (runtime == NULL)
        return false;
    AcquireSRWLockExclusive(&runtime->operation_lock);
    AcquireSRWLockExclusive(&runtime->session_lock);
    if (attach != NULL && cleanup != NULL && runtime->worker == NULL &&
        runtime->schedule_capture == NULL && runtime->schedule_cleanup == NULL &&
        InterlockedCompareExchange(&runtime->closing, 0, 0) == 0) {
        runtime->schedule_capture = attach;
        runtime->schedule_cleanup = cleanup;
        accepted = true;
    }
    ReleaseSRWLockExclusive(&runtime->session_lock);
    ReleaseSRWLockExclusive(&runtime->operation_lock);
    runtime_release(runtime);
    return accepted;
}

bool ul_plugin_capture_inspect_request(uintptr_t *generation, uint8_t *mask)
{
    ul_plugin_runtime *runtime = runtime_acquire();
    bool accepted = false;
    if (runtime == NULL)
        return false;
    AcquireSRWLockShared(&runtime->session_lock);
    if (generation != NULL && mask != NULL &&
        runtime->session_phase == UL_SESSION_STARTED && !runtime->capture_spec_ready &&
        runtime->schedule_capture != NULL && runtime->schedule_cleanup != NULL &&
        InterlockedCompareExchange(&runtime->closing, 0, 0) == 0) {
        *generation = runtime->session_generation;
        *mask = runtime->session_options.additional_mix_mask;
        accepted = true;
    }
    ReleaseSRWLockShared(&runtime->session_lock);
    runtime_release(runtime);
    return accepted;
}

void ul_plugin_capture_inspected(uintptr_t generation,
                                 const ul_audio_capture_spec *spec)
{
    ul_plugin_runtime *runtime = runtime_acquire();
    if (runtime == NULL)
        return;
    AcquireSRWLockExclusive(&runtime->session_lock);
    if (runtime->session_generation == generation &&
        runtime->session_phase == UL_SESSION_STARTED && !runtime->capture_spec_ready) {
        runtime->capture_spec_ready = true;
        runtime->capture_spec_valid = spec != NULL;
        if (spec != NULL)
            runtime->capture_spec = *spec;
    }
    ReleaseSRWLockExclusive(&runtime->session_lock);
    runtime_release(runtime);
}

ul_audio_capture *ul_plugin_capture_retain(uintptr_t generation)
{
    ul_plugin_runtime *runtime = runtime_acquire();
    ul_audio_capture *capture = NULL;
    if (runtime == NULL)
        return NULL;
    AcquireSRWLockShared(&runtime->session_lock);
    if (runtime->session_generation == generation &&
        runtime->session_phase == UL_SESSION_STARTED &&
        !runtime->capture_attach_done && runtime->capture != NULL &&
        InterlockedCompareExchange(&runtime->closing, 0, 0) == 0) {
        capture = runtime->capture;
        ul_audio_capture_retain(capture);
    }
    ReleaseSRWLockShared(&runtime->session_lock);
    runtime_release(runtime);
    return capture;
}

void ul_plugin_capture_attached(uintptr_t generation,
                                ul_audio_capture *capture, bool success)
{
    ul_plugin_runtime *runtime = runtime_acquire();
    if (runtime == NULL)
        return;
    AcquireSRWLockExclusive(&runtime->session_lock);
    if (runtime->session_generation == generation && capture != NULL &&
        runtime->capture == capture && !runtime->capture_attach_done) {
        runtime->capture_attach_done = true;
        runtime->capture_attached = success &&
            runtime->session_phase == UL_SESSION_STARTED &&
            InterlockedCompareExchange(&runtime->closing, 0, 0) == 0 &&
            ul_audio_capture_activate(capture);
        SetEvent(runtime->capture_result);
    }
    ReleaseSRWLockExclusive(&runtime->session_lock);
    runtime_release(runtime);
}

void ul_plugin_capture_cleanup_complete(uintptr_t generation)
{
    ul_plugin_runtime *runtime = runtime_acquire();
    if (runtime == NULL)
        return;
    AcquireSRWLockExclusive(&runtime->session_lock);
    if (generation == runtime->session_generation &&
        runtime->session_phase == UL_SESSION_DISARMING) {
        runtime->capture_attached = false;
        SetEvent(runtime->cleanup_complete);
    }
    ReleaseSRWLockExclusive(&runtime->session_lock);
    runtime_release(runtime);
}

void ul_plugin_capture_stop_frontend(void)
{
    ul_plugin_runtime *runtime = runtime_acquire();
    if (runtime == NULL)
        return;
    AcquireSRWLockExclusive(&runtime->session_lock);
    if (runtime->capture != NULL)
        ul_audio_capture_deactivate(runtime->capture);
    ReleaseSRWLockExclusive(&runtime->session_lock);
    runtime_release(runtime);
}

void ul_plugin_arm_checked(uintptr_t generation, bool idle)
{
    ul_plugin_runtime *runtime = runtime_acquire();
    if (runtime == NULL)
        return;
    AcquireSRWLockExclusive(&runtime->session_lock);
    if (generation == runtime->session_generation &&
        runtime->session_phase == UL_SESSION_ARM_PENDING) {
        runtime->session_phase = idle &&
            runtime->stream_epoch == runtime->pending_epoch &&
            runtime->stream_epoch != UINT64_MAX &&
            ready_remaining(runtime->ready_started) != 0u &&
            InterlockedCompareExchange(&runtime->closing, 0, 0) == 0 ?
            UL_SESSION_ARMED : UL_SESSION_TERMINAL;
        SetEvent(runtime->arm_result);
    }
    ReleaseSRWLockExclusive(&runtime->session_lock);
    runtime_release(runtime);
}

void ul_plugin_stream_event(ul_stream_event event)
{
    ul_plugin_runtime *runtime = runtime_acquire();
    if (runtime == NULL)
        return;
    AcquireSRWLockExclusive(&runtime->session_lock);
    if (event < UL_STREAM_STARTING || event > UL_STREAM_STOPPED ||
        runtime->stream_epoch == UINT64_MAX) {
        session_cancel_locked(runtime);
    } else {
        runtime->stream_epoch++;
        if (runtime->session_phase != UL_SESSION_NONE &&
            runtime->session_phase != UL_SESSION_TERMINAL) {
            if (runtime->session_phase == UL_SESSION_DISARMING) {
                if (event == UL_STREAM_STOPPING || event == UL_STREAM_STOPPED)
                    SetEvent(runtime->cleanup_complete);
            } else if (event == UL_STREAM_STARTING && runtime->session_phase == UL_SESSION_ARMED) {
                runtime->session_phase = UL_SESSION_STARTING;
                runtime->stream_starting_at = GetTickCount64();
            } else if (event == UL_STREAM_STARTED && runtime->session_phase == UL_SESSION_STARTING &&
                       GetTickCount64() - runtime->stream_starting_at < UL_PLUGIN_START_TIMEOUT_MS) {
                runtime->session_phase = UL_SESSION_STARTED;
                runtime->stream_started_at = GetTickCount64();
            } else if ((event == UL_STREAM_STOPPING || event == UL_STREAM_STOPPED) &&
                       runtime->session_phase == UL_SESSION_STARTED && runtime->capture_attached) {
                if (runtime->capture != NULL)
                    ul_audio_capture_deactivate(runtime->capture);
                runtime->session_phase = UL_SESSION_DRAINING;
                SetEvent(runtime->stream_stop);
            } else if ((event == UL_STREAM_STOPPING || event == UL_STREAM_STOPPED) &&
                       runtime->session_phase == UL_SESSION_DRAINING) {
                /* A duplicate STOPPED must not cancel a terminal packet that
                 * is still being acknowledged by the client. */
            } else if (runtime->session_phase == UL_SESSION_ARM_PENDING) {
                /* A valid Arm is refused while its verified pipe is still
                 * usable. Lifecycle teardown retains the cancel-first path. */
                runtime->session_phase = UL_SESSION_TERMINAL;
                SetEvent(runtime->arm_result);
            } else
                session_cancel_locked(runtime);
        }
    }
    ReleaseSRWLockExclusive(&runtime->session_lock);
    runtime_release(runtime);
}

ul_session_phase ul_plugin_session_status(void)
{
    ul_plugin_runtime *runtime = runtime_acquire();
    ul_session_phase phase = UL_SESSION_NONE;
    if (runtime != NULL) {
        AcquireSRWLockShared(&runtime->session_lock);
        phase = runtime->session_phase;
        ReleaseSRWLockShared(&runtime->session_lock);
        runtime_release(runtime);
    }
    return phase;
}
