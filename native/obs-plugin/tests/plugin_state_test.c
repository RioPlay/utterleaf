// SPDX-License-Identifier: GPL-2.0-or-later
#include <windows.h>

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "../src/plugin_state.h"
#include "../src/session_protocol.h"
#include "../src/audio_stream.h"

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
static int shim_ul_admission_read_exact(ul_admission *admission, void *buffer,
                                        DWORD size, DWORD timeout_ms);
static int shim_ul_admission_write_all(ul_admission *admission,
                                       const void *buffer, DWORD size,
                                       DWORD timeout_ms);
static int shim_ul_admission_probe(ul_admission *admission, DWORD *available);
static void shim_ul_admission_cancel(ul_admission *admission);
static HANDLE shim_ul_admission_pipe(const ul_admission *admission);
static HANDLE WINAPI shim_CreateEventW(LPSECURITY_ATTRIBUTES attributes,
                                       BOOL manual, BOOL initial,
                                       LPCWSTR name);
static ul_audio_capture *shim_ul_audio_capture_create_worker(
    const ul_audio_capture_spec *spec);
static void shim_ul_audio_capture_retain(ul_audio_capture *capture);
static void shim_ul_audio_capture_release(ul_audio_capture *capture);
static bool shim_ul_audio_capture_activate(ul_audio_capture *capture);
static void shim_ul_audio_capture_deactivate(ul_audio_capture *capture);
static int shim_ul_audio_stream_run(ul_audio_capture *capture,
    const ul_audio_capture_spec *spec, ul_admission *admission,
    const uint8_t session[16], HANDLE stop_event, HANDLE cleanup_complete,
    ul_audio_disarm_callback disarm, void *disarm_context);
static int shim_ul_audio_stream_finish_empty_disarm(
    ul_admission *admission, const uint8_t session[16],
    HANDLE cleanup_complete);
static int shim_ul_audio_stream_run_disarmed(
    ul_audio_capture *capture, const ul_audio_capture_spec *spec,
    ul_admission *admission, const uint8_t session[16], HANDLE stop_event,
    HANDLE cleanup_complete);

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
#define ul_admission_read_exact shim_ul_admission_read_exact
#define ul_admission_write_all shim_ul_admission_write_all
#define ul_admission_probe shim_ul_admission_probe
#define ul_admission_cancel shim_ul_admission_cancel
#define ul_admission_pipe shim_ul_admission_pipe
#define CreateEventW shim_CreateEventW
#define ul_audio_capture_create_worker shim_ul_audio_capture_create_worker
#define ul_audio_capture_retain shim_ul_audio_capture_retain
#define ul_audio_capture_release shim_ul_audio_capture_release
#define ul_audio_capture_activate shim_ul_audio_capture_activate
#define ul_audio_capture_deactivate shim_ul_audio_capture_deactivate
#define ul_audio_stream_run shim_ul_audio_stream_run
#define ul_audio_stream_finish_empty_disarm shim_ul_audio_stream_finish_empty_disarm
#define ul_audio_stream_run_disarmed shim_ul_audio_stream_run_disarmed
#define UL_PLUGIN_AUTH_TIMEOUT_MS 40u
#define UL_PLUGIN_READY_TIMEOUT_MS 40u
#define UL_PLUGIN_START_TIMEOUT_MS 80u
#define UL_PLUGIN_CAPTURE_TIMEOUT_MS 80u
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
#undef ul_admission_read_exact
#undef ul_admission_write_all
#undef ul_admission_probe
#undef ul_admission_cancel
#undef ul_admission_pipe
#undef CreateEventW
#undef ul_audio_capture_create_worker
#undef ul_audio_capture_retain
#undef ul_audio_capture_release
#undef ul_audio_capture_activate
#undef ul_audio_capture_deactivate
#undef ul_audio_stream_run
#undef ul_audio_stream_finish_empty_disarm
#undef ul_audio_stream_run_disarmed

struct ul_pairing_store {
    int unused;
};

struct ul_admission {
    HANDLE cancelled;
    int authenticate_result;
    bool command_ready;
    uint8_t command[UL_SESSION_COMMAND_BYTES];
};

struct ul_authorizer {
    bool outstanding;
    bool revoked;
    ul_admission *admission;
    uint8_t session[16];
    uint8_t mask;
};

struct ul_audio_capture {
    volatile LONG refs;
    volatile LONG deactivate_count;
    bool active;
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
static bool fake_arm_command;
static int fake_arm_command_corrupt;
static bool fake_schedule_result = true;
static DWORD fake_probe_available;
static int fake_probe_result = UL_ADMISSION_AUTH_OK;
static HANDLE fake_schedule_entered;
static HANDLE fake_reply_written;
static uintptr_t fake_scheduled_generation;
static uint8_t fake_reply[UL_SESSION_COMMAND_BYTES];
static unsigned fake_create_event_count;
static unsigned fake_create_event_fail_at;
static volatile LONG fake_capture_create_count;
static volatile LONG fake_capture_free_count;
static volatile LONG fake_capture_activate_count;
static volatile LONG fake_capture_deactivate_count;
static volatile LONG fake_stream_count;
static volatile LONG fake_cleanup_count;
static volatile LONG fake_empty_disarm_count;
static volatile LONG fake_stream_disarm_count;
static bool fake_stream_requests_disarm;
static bool fake_cleanup_schedule_result = true;
static bool fake_capture_create_result = true;
static bool fake_capture_activate_result = true;
static bool fake_capture_schedule_result = true;
static bool fake_hold_after_stop;
static int fake_stream_result = UL_AUDIO_STREAM_OK;
static HANDLE fake_capture_schedule_entered;
static HANDLE fake_cleanup_entered;
static HANDLE fake_disarm_read_entered;
static HANDLE fake_disarm_read_release;
static HANDLE fake_stream_entered;
static HANDLE fake_stream_release;
static HANDLE fake_reply_release;
static bool fake_block_reply;
static uintptr_t fake_capture_generation;
static bool fake_create_after_reply;

static int check(bool condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", message);
        return 1;
    }
    return 0;
}

static HANDLE WINAPI shim_CreateEventW(LPSECURITY_ATTRIBUTES attributes,
                                       BOOL manual, BOOL initial,
                                       LPCWSTR name)
{
    fake_create_event_count++;
    if (fake_create_event_fail_at != 0u &&
        fake_create_event_count == fake_create_event_fail_at) {
        SetLastError(ERROR_NOT_ENOUGH_MEMORY);
        return NULL;
    }
    return CreateEventW(attributes, manual, initial, name);
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
    memcpy(authorizer->session, session, sizeof(authorizer->session));
    authorizer->mask = mask;
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
    if (fake_arm_command) {
        memcpy(admission->command, "ULAC", 4);
        admission->command[4] = 1;
        admission->command[5] = 1;
        memcpy(admission->command + 8, authorizer->session, 16);
        admission->command[24] = authorizer->mask;
        if (fake_arm_command_corrupt == 1)
            admission->command[8] ^= 0x80;
        else if (fake_arm_command_corrupt == 2)
            admission->command[24] ^= 1;
        admission->command_ready = true;
    }
    authorizer->admission = admission;
    options->client_pid = 100;
    memcpy(options->session, authorizer->session, sizeof(options->session));
    options->additional_mix_mask = authorizer->mask;
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

static int shim_ul_admission_read_exact(ul_admission *admission, void *buffer,
                                        DWORD size, DWORD timeout_ms)
{
    DWORD waited;

    if (buffer == NULL || size != sizeof(admission->command))
        return UL_ADMISSION_IO_ERROR;
    if (admission->command_ready) {
        if (admission->command[5] == 4u && fake_disarm_read_entered != NULL) {
            SetEvent(fake_disarm_read_entered);
            if (WaitForSingleObject(fake_disarm_read_release, 2000u) !=
                WAIT_OBJECT_0)
                return UL_ADMISSION_TIMEOUT;
        }
        memcpy(buffer, admission->command, size);
        admission->command_ready = false;
        fake_probe_available = 0u;
        return UL_ADMISSION_AUTH_OK;
    }
    waited = WaitForSingleObject(admission->cancelled, timeout_ms);
    SecureZeroMemory(buffer, size);
    return waited == WAIT_OBJECT_0 ? UL_ADMISSION_CANCELLED
                                   : UL_ADMISSION_TIMEOUT;
}

static int shim_ul_admission_write_all(ul_admission *admission,
                                       const void *buffer, DWORD size,
                                       DWORD timeout_ms)
{
    (void)timeout_ms;
    if (WaitForSingleObject(admission->cancelled, 0) == WAIT_OBJECT_0)
        return UL_ADMISSION_CANCELLED;
    if (buffer == NULL || size != sizeof(fake_reply))
        return UL_ADMISSION_IO_ERROR;
    memcpy(fake_reply, buffer, size);
    if (fake_reply_written != NULL)
        SetEvent(fake_reply_written);
    if (fake_block_reply && fake_reply_release != NULL &&
        WaitForSingleObject(fake_reply_release, 2000) != WAIT_OBJECT_0)
        return UL_ADMISSION_TIMEOUT;
    return UL_ADMISSION_AUTH_OK;
}

static int shim_ul_admission_probe(ul_admission *admission, DWORD *available)
{
    if (WaitForSingleObject(admission->cancelled, 0) == WAIT_OBJECT_0)
        return UL_ADMISSION_CANCELLED;
    if (available == NULL)
        return UL_ADMISSION_IO_ERROR;
    *available = fake_probe_available;
    return fake_probe_result;
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

static ul_audio_capture *shim_ul_audio_capture_create_worker(
    const ul_audio_capture_spec *spec)
{
    ul_audio_capture *capture;
    (void)spec;
    InterlockedIncrement(&fake_capture_create_count);
    fake_create_after_reply = fake_reply_written != NULL &&
        WaitForSingleObject(fake_reply_written, 0) == WAIT_OBJECT_0 &&
        (!fake_block_reply || (fake_reply_release != NULL &&
         WaitForSingleObject(fake_reply_release, 0) == WAIT_OBJECT_0));
    if (!fake_capture_create_result)
        return NULL;
    capture = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*capture));
    if (capture != NULL)
        capture->refs = 1;
    return capture;
}

static void shim_ul_audio_capture_retain(ul_audio_capture *capture)
{
    if (capture != NULL)
        InterlockedIncrement(&capture->refs);
}

static void shim_ul_audio_capture_release(ul_audio_capture *capture)
{
    if (capture != NULL && InterlockedDecrement(&capture->refs) == 0) {
        HeapFree(GetProcessHeap(), 0, capture);
        InterlockedIncrement(&fake_capture_free_count);
    }
}

static bool shim_ul_audio_capture_activate(ul_audio_capture *capture)
{
    if (capture == NULL || !fake_capture_activate_result)
        return false;
    capture->active = true;
    InterlockedIncrement(&fake_capture_activate_count);
    return true;
}

static void shim_ul_audio_capture_deactivate(ul_audio_capture *capture)
{
    if (capture == NULL)
        return;
    capture->active = false;
    InterlockedIncrement(&capture->deactivate_count);
    InterlockedIncrement(&fake_capture_deactivate_count);
}

static int shim_ul_audio_stream_run(ul_audio_capture *capture,
    const ul_audio_capture_spec *spec, ul_admission *admission,
    const uint8_t exact_session[16], HANDLE stop_event,
    HANDLE cleanup_complete, ul_audio_disarm_callback disarm,
    void *disarm_context)
{
    HANDLE waits[3] = {stop_event, admission->cancelled, fake_stream_release};
    DWORD waited;
    (void)spec;
    (void)exact_session;
    InterlockedIncrement(&fake_stream_count);
    if (fake_stream_entered != NULL)
        SetEvent(fake_stream_entered);
    if (fake_stream_requests_disarm) {
        ul_audio_disarm_action action;
        shim_ul_audio_capture_deactivate(capture);
        action = disarm(disarm_context);
        InterlockedIncrement(&fake_stream_disarm_count);
        if (action == UL_AUDIO_DISARM_ACCEPTED &&
            WaitForSingleObject(cleanup_complete, 2000u) != WAIT_OBJECT_0)
            return UL_AUDIO_STREAM_INCOMPLETE;
        return action == UL_AUDIO_DISARM_REJECTED
                   ? UL_AUDIO_STREAM_TRANSPORT_ERROR : UL_AUDIO_STREAM_OK;
    }
    waited = WaitForMultipleObjects(fake_stream_release == NULL ? 2u : 3u,
                                    waits, FALSE, 2000u);
    if (waited == WAIT_OBJECT_0 && fake_hold_after_stop &&
        fake_stream_release != NULL)
        (void)WaitForSingleObject(fake_stream_release, 2000u);
    shim_ul_audio_capture_deactivate(capture);
    if (waited == WAIT_OBJECT_0)
        return fake_stream_result;
    return UL_AUDIO_STREAM_TRANSPORT_ERROR;
}

static int shim_ul_audio_stream_finish_empty_disarm(
    ul_admission *admission, const uint8_t exact_session[16],
    HANDLE cleanup_complete)
{
    (void)admission;
    (void)exact_session;
    InterlockedIncrement(&fake_empty_disarm_count);
    if (cleanup_complete != NULL &&
        WaitForSingleObject(cleanup_complete, 2000u) != WAIT_OBJECT_0)
        return UL_AUDIO_STREAM_INCOMPLETE;
    return UL_AUDIO_STREAM_OK;
}

static int shim_ul_audio_stream_run_disarmed(
    ul_audio_capture *capture, const ul_audio_capture_spec *spec,
    ul_admission *admission, const uint8_t exact_session[16], HANDLE stop_event,
    HANDLE cleanup_complete)
{
    (void)capture;
    (void)spec;
    (void)admission;
    (void)exact_session;
    (void)stop_event;
    InterlockedIncrement(&fake_stream_disarm_count);
    return WaitForSingleObject(cleanup_complete, 2000u) == WAIT_OBJECT_0
               ? UL_AUDIO_STREAM_OK : UL_AUDIO_STREAM_INCOMPLETE;
}

static bool queued_arm_scheduler(uintptr_t generation)
{
    fake_scheduled_generation = generation;
    if (fake_schedule_entered != NULL)
        SetEvent(fake_schedule_entered);
    return fake_schedule_result;
}

static bool queued_capture_scheduler(uintptr_t generation)
{
    fake_capture_generation = generation;
    if (fake_capture_schedule_entered != NULL)
        SetEvent(fake_capture_schedule_entered);
    return fake_capture_schedule_result;
}

static bool queued_cleanup_scheduler(uintptr_t generation)
{
    fake_capture_generation = generation;
    InterlockedIncrement(&fake_cleanup_count);
    if (fake_cleanup_entered != NULL)
        SetEvent(fake_cleanup_entered);
    return fake_cleanup_schedule_result;
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

static bool wait_phase(ul_session_phase expected, DWORD timeout_ms)
{
    ULONGLONG deadline = GetTickCount64() + timeout_ms;

    do {
        if (ul_plugin_session_status() == expected)
            return true;
        Sleep(1);
    } while (GetTickCount64() < deadline);
    return ul_plugin_session_status() == expected;
}

static bool wait_worker_inactive(DWORD timeout_ms)
{
    ULONGLONG deadline = GetTickCount64() + timeout_ms;
    ul_plugin_snapshot snapshot;

    do {
        snapshot = ul_plugin_get_status();
        if (!snapshot.admission_pending) {
            HANDLE worker = plugin_global.runtime == NULL
                                ? NULL
                                : plugin_global.runtime->worker;
            return worker == NULL ||
                   WaitForSingleObject(worker, timeout_ms) == WAIT_OBJECT_0;
        }
        Sleep(1);
    } while (GetTickCount64() < deadline);
    if (ul_plugin_get_status().admission_pending)
        return false;
    return plugin_global.runtime == NULL || plugin_global.runtime->worker == NULL ||
           WaitForSingleObject(plugin_global.runtime->worker, timeout_ms) ==
               WAIT_OBJECT_0;
}

static bool wait_current_worker_signaled(DWORD timeout_ms)
{
    ul_plugin_runtime *runtime = plugin_global.runtime;
    HANDLE worker = runtime == NULL ? NULL : runtime->worker;

    return worker != NULL &&
           WaitForSingleObject(worker, timeout_ms) == WAIT_OBJECT_0;
}

static int prepare_arm(const uint8_t session[16], uint8_t mask)
{
    uint8_t challenge[60];
    uint8_t proof[32] = {0x44};
    int failures = 0;

    ResetEvent(fake_schedule_entered);
    ResetEvent(fake_reply_written);
    SecureZeroMemory(fake_reply, sizeof(fake_reply));
    fake_scheduled_generation = 0;
    failures += check(ul_plugin_issue(100, session, mask, challenge),
                      "Arm issue succeeds");
    failures += check(ul_plugin_prepare(challenge, sizeof(challenge), proof,
                                        sizeof(proof)),
                      "Arm prepare succeeds");
    failures += check(WaitForSingleObject(fake_schedule_entered, 2000) ==
                          WAIT_OBJECT_0,
                      "Arm scheduler receives queued generation");
    failures += check(fake_scheduled_generation != 0,
                      "Arm scheduler receives nonzero generation");
    failures += check(wait_phase(UL_SESSION_ARM_PENDING, 2000),
                      "Arm reaches pending phase");
    return failures;
}

static bool queue_disarm(const uint8_t session[16])
{
    ul_plugin_runtime *runtime = plugin_global.runtime;
    ul_admission *admission;
    if (runtime == NULL)
        return false;
    AcquireSRWLockShared(&runtime->session_lock);
    admission = runtime->worker_admission;
    if (admission != NULL) {
        SecureZeroMemory(admission->command, sizeof(admission->command));
        memcpy(admission->command, "ULAC", 4u);
        admission->command[4] = 1u;
        admission->command[5] = 4u;
        memcpy(admission->command + 8u, session, 16u);
        admission->command_ready = true;
        MemoryBarrier();
        fake_probe_available = UL_SESSION_COMMAND_BYTES;
    }
    ReleaseSRWLockShared(&runtime->session_lock);
    return admission != NULL;
}

static int start_arm_runtime(void)
{
    int failures = 0;

    fake_load_result = UL_PAIRING_OK;
    fake_arm_command = true;
    fake_schedule_entered = CreateEventW(NULL, TRUE, FALSE, NULL);
    fake_reply_written = CreateEventW(NULL, TRUE, FALSE, NULL);
    failures += check(fake_schedule_entered != NULL &&
                          fake_reply_written != NULL,
                      "create deterministic Arm events");
    failures += check(ul_plugin_start(), "Arm runtime starts paired");
    failures += check(ul_plugin_set_arm_scheduler(queued_arm_scheduler),
                      "install Arm scheduler once before worker");
    return failures;
}

static void close_arm_events(void)
{
    if (fake_schedule_entered != NULL)
        CloseHandle(fake_schedule_entered);
    if (fake_reply_written != NULL)
        CloseHandle(fake_reply_written);
    fake_schedule_entered = NULL;
    fake_reply_written = NULL;
}

static ul_audio_capture_spec capture_spec(uint8_t primary, uint8_t mask)
{
    ul_audio_capture_spec spec = {48000u, 2u, 2u, primary, mask,
                                  (uintptr_t)0x1111u, (uintptr_t)0x2222u};
    return spec;
}

static int start_capture_runtime(void)
{
    int failures = start_arm_runtime();
    fake_capture_schedule_entered = CreateEventW(NULL, TRUE, FALSE, NULL);
    fake_cleanup_entered = CreateEventW(NULL, TRUE, FALSE, NULL);
    fake_stream_entered = CreateEventW(NULL, TRUE, FALSE, NULL);
    fake_stream_release = CreateEventW(NULL, TRUE, FALSE, NULL);
    fake_reply_release = CreateEventW(NULL, TRUE, FALSE, NULL);
    failures += check(fake_capture_schedule_entered != NULL &&
                          fake_cleanup_entered != NULL &&
                          fake_stream_entered != NULL &&
                          fake_stream_release != NULL &&
                          fake_reply_release != NULL,
                      "create capture coordination events");
    failures += check(ul_plugin_set_capture_schedulers(
                          queued_capture_scheduler, queued_cleanup_scheduler),
                      "install capture schedulers before worker");
    return failures;
}

static void close_capture_events(void)
{
    CloseHandle(fake_capture_schedule_entered);
    CloseHandle(fake_cleanup_entered);
    CloseHandle(fake_stream_entered);
    CloseHandle(fake_stream_release);
    CloseHandle(fake_reply_release);
    fake_capture_schedule_entered = fake_cleanup_entered = NULL;
    fake_stream_entered = fake_stream_release = fake_reply_release = NULL;
    close_arm_events();
}

static int reach_capture_started(uint8_t session[16], uint8_t mask,
                                 uintptr_t *generation)
{
    uint8_t observed_mask = 0xffu;
    int failures = prepare_arm(session, mask);
    ul_plugin_arm_checked(fake_scheduled_generation, true);
    failures += check(WaitForSingleObject(fake_reply_written, 2000) ==
                          WAIT_OBJECT_0,
                      "accepted Arm reply completes before capture");
    ul_plugin_stream_event(UL_STREAM_STARTING);
    ul_plugin_stream_event(UL_STREAM_STARTED);
    failures += check(wait_phase(UL_SESSION_STARTED, 2000),
                      "capture generation reaches STARTED");
    failures += check(ul_plugin_capture_inspect_request(generation,
                                                        &observed_mask) &&
                          observed_mask == mask,
                      "current STARTED generation requests exact mask");
    return failures;
}

static int scenario_arm_valid(void)
{
    uint8_t session[16] = {0x21, 2, 3, 4};
    uint8_t expected[UL_SESSION_COMMAND_BYTES];
    ul_plugin_snapshot snapshot;
    int failures = start_arm_runtime();

    failures += prepare_arm(session, 37);
    ul_plugin_arm_checked(fake_scheduled_generation, true);
    failures += check(WaitForSingleObject(fake_reply_written, 2000) ==
                          WAIT_OBJECT_0,
                      "committed Arm reply written");
    failures += check(ul_session_arm_reply(session, 37, true, expected) &&
                          memcmp(fake_reply, expected, sizeof(expected)) == 0,
                      "Arm reply binds exact prepared session and mask");
    failures += check(wait_phase(UL_SESSION_ARMED, 2000),
                      "idle callback commits Arm");
    Sleep(120);
    snapshot = ul_plugin_get_status();
    failures += check(snapshot.admission_pending &&
                          ul_plugin_session_status() == UL_SESSION_ARMED,
                      "armed session persists beyond READY timeout");
    ul_plugin_stream_event(UL_STREAM_STARTING);
    failures += check(ul_plugin_session_status() == UL_SESSION_STARTING,
                      "post-Arm STARTING accepted");
    ul_plugin_stream_event(UL_STREAM_STARTED);
    failures += check(ul_plugin_session_status() == UL_SESSION_STARTED,
                      "ordered STARTED accepted once");
    ul_plugin_stream_event(UL_STREAM_STOPPING);
    failures += check(wait_phase(UL_SESSION_TERMINAL, 2000),
                      "stop terminates active consent");
    ul_plugin_close();
    close_arm_events();
    return failures;
}

static int scenario_arm_ordering(void)
{
    uint8_t session[16] = {0x31};
    uint8_t expected[UL_SESSION_COMMAND_BYTES];
    int failures = start_arm_runtime();

    failures += prepare_arm(session, 3);
    ul_plugin_arm_checked(fake_scheduled_generation, false);
    failures += check(WaitForSingleObject(fake_reply_written, 2000) ==
                          WAIT_OBJECT_0,
                      "busy Arm writes refusal");
    failures += check(ul_session_arm_reply(session, 3, false, expected) &&
                          memcmp(fake_reply, expected, sizeof(expected)) == 0,
                      "already-busy Arm reply is exact refusal");
    failures += check(wait_worker_inactive(2000),
                      "busy refusal retires worker");

    session[0]++;
    failures += prepare_arm(session, 4);
    ul_plugin_stream_event(UL_STREAM_STARTING);
    failures += check(wait_phase(UL_SESSION_TERMINAL, 2000),
                      "STARTING before callback refuses pending Arm");
    failures += check(WaitForSingleObject(fake_reply_written, 2000) ==
                          WAIT_OBJECT_0 &&
                          ul_session_arm_reply(session, 4, false, expected) &&
                          fake_reply[25] == 2 &&
                          memcmp(fake_reply, expected, sizeof(expected)) == 0,
                      "STARTING race returns exact status-2 refusal");
    ul_plugin_arm_checked(fake_scheduled_generation, true);
    failures += check(wait_worker_inactive(2000),
                      "late callback cannot revive STARTING race");

    session[0]++;
    failures += prepare_arm(session, 5);
    ul_plugin_arm_checked(fake_scheduled_generation, true);
    failures += check(WaitForSingleObject(fake_reply_written, 2000) ==
                          WAIT_OBJECT_0 &&
                          wait_phase(UL_SESSION_ARMED, 2000),
                      "fresh Arm commits after retired race");
    ul_plugin_stream_event(UL_STREAM_STARTED);
    failures += check(wait_phase(UL_SESSION_TERMINAL, 2000),
                      "STARTED without STARTING is terminal");
    ul_plugin_close();
    close_arm_events();
    return failures;
}

static int scenario_arm_stale_and_commands(void)
{
    uint8_t session[16] = {0x41};
    uintptr_t stale_generation;
    int failures = start_arm_runtime();

    failures += prepare_arm(session, 6);
    stale_generation = fake_scheduled_generation;
    failures += check(wait_worker_inactive(2000),
                      "unanswered Arm expires at READY deadline");
    session[0]++;
    failures += prepare_arm(session, 7);
    ul_plugin_arm_checked(stale_generation, true);
    failures += check(ul_plugin_session_status() == UL_SESSION_ARM_PENDING,
                      "late callback cannot arm new generation");
    ul_plugin_arm_checked(fake_scheduled_generation, true);
    failures += check(WaitForSingleObject(fake_reply_written, 2000) ==
                          WAIT_OBJECT_0 &&
                          wait_phase(UL_SESSION_ARMED, 2000),
                      "current generation still arms");
    fake_probe_available = UL_SESSION_COMMAND_BYTES;
    failures += check(wait_worker_inactive(2000),
                      "duplicate command bytes terminate armed worker");

    fake_probe_available = 0;
    session[0]++;
    failures += prepare_arm(session, 8);
    ul_plugin_arm_checked(fake_scheduled_generation, true);
    failures += check(WaitForSingleObject(fake_reply_written, 2000) ==
                          WAIT_OBJECT_0,
                      "EOF case Arm reply written");
    fake_probe_result = UL_ADMISSION_IO_ERROR;
    failures += check(wait_worker_inactive(2000),
                      "authenticated EOF terminates armed worker");
    ul_plugin_close();
    close_arm_events();
    return failures;
}

static int scenario_arm_start_timeout(void)
{
    uint8_t session[16] = {0x39};
    int failures = start_arm_runtime();

    failures += prepare_arm(session, 15);
    ul_plugin_arm_checked(fake_scheduled_generation, true);
    failures += check(WaitForSingleObject(fake_reply_written, 2000) ==
                          WAIT_OBJECT_0 &&
                          wait_phase(UL_SESSION_ARMED, 2000),
                      "start-timeout session arms");
    ul_plugin_stream_event(UL_STREAM_STARTING);
    failures += check(ul_plugin_session_status() == UL_SESSION_STARTING,
                      "start-timeout session records STARTING");
    failures += check(wait_current_worker_signaled(2000) &&
                          ul_plugin_session_status() == UL_SESSION_TERMINAL,
                      "missing matching STARTED terminally expires worker");
    ul_plugin_stream_event(UL_STREAM_STARTED);
    failures += check(ul_plugin_session_status() == UL_SESSION_TERMINAL,
                      "late STARTED cannot resurrect expired generation");

    session[0]++;
    failures += prepare_arm(session, 16);
    ul_plugin_arm_checked(fake_scheduled_generation, true);
    failures += check(WaitForSingleObject(fake_reply_written, 2000) ==
                          WAIT_OBJECT_0 &&
                          wait_phase(UL_SESSION_ARMED, 2000),
                      "new manual session arms after STARTING timeout");
    ul_plugin_close();
    close_arm_events();
    return failures;
}

static int scenario_arm_bound_command(void)
{
    uint8_t session[16] = {0x51};
    uint8_t challenge[60];
    uint8_t proof[32] = {0x44};
    int failures = start_arm_runtime();

    fake_arm_command_corrupt = 1;
    failures += check(ul_plugin_issue(100, session, 9, challenge) &&
                          ul_plugin_prepare(challenge, sizeof(challenge), proof,
                                            sizeof(proof)),
                      "submit wrong-session Arm command");
    failures += check(wait_worker_inactive(2000),
                      "wrong prepared session is refused");
    fake_arm_command_corrupt = 2;
    session[0]++;
    failures += check(ul_plugin_issue(100, session, 10, challenge) &&
                          ul_plugin_prepare(challenge, sizeof(challenge), proof,
                                            sizeof(proof)),
                      "submit wrong-mask Arm command");
    failures += check(wait_worker_inactive(2000),
                      "wrong prepared mix mask is refused");
    ul_plugin_close();
    close_arm_events();
    return failures;
}

static int scenario_arm_teardown(void)
{
    uint8_t session[16] = {0x61};
    bool saved = false;
    LONG releases;
    int failures = start_arm_runtime();

    failures += prepare_arm(session, 11);
    releases = InterlockedCompareExchange(&fake_release_count, 0, 0);
    failures += check(ul_plugin_forget() == UL_PAIRING_OK,
                      "forget completes while Arm callback pending");
    failures += check(InterlockedCompareExchange(&fake_release_count, 0, 0) >
                          releases,
                      "forget cancels and joins pending Arm worker");
    failures += check(ul_plugin_pair(L"C:\\new.ulpair", false, &saved) ==
                          UL_PAIRING_OK && saved,
                      "re-pair after forget");

    session[0]++;
    failures += prepare_arm(session, 12);
    releases = InterlockedCompareExchange(&fake_release_count, 0, 0);
    saved = false;
    failures += check(ul_plugin_pair(L"C:\\replace.ulpair", true, &saved) ==
                          UL_PAIRING_OK && saved,
                      "replace completes while Arm callback pending");
    failures += check(InterlockedCompareExchange(&fake_release_count, 0, 0) >
                          releases,
                      "replace cancels and joins pending Arm worker");

    session[0]++;
    failures += prepare_arm(session, 13);
    ul_plugin_stop_accepting();
    failures += check(wait_worker_inactive(2000),
                      "stop accepting cancels pending Arm worker");
    ul_plugin_close();
    close_arm_events();
    return failures;
}

static int scenario_arm_close_pending(void)
{
    uint8_t session[16] = {0x71};
    int failures = start_arm_runtime();

    failures += prepare_arm(session, 14);
    ul_plugin_close();
    failures += check(ul_plugin_get_status().status == UL_PLUGIN_CLOSED &&
                          ul_plugin_session_status() == UL_SESSION_NONE,
                      "close joins pending Arm and closes public gate");
    close_arm_events();
    return failures;
}

static int scenario_capture_clean(void)
{
    uint8_t session[16] = {0x81, 2, 3};
    ul_audio_capture_spec spec = capture_spec(0u, 5u);
    ul_audio_capture *borrowed;
    uintptr_t generation = 0u;
    uint8_t observed_mask = 0xffu;
    DWORD before = 0u, after = 0u;
    int failures;

    GetProcessHandleCount(GetCurrentProcess(), &before);
    failures = start_capture_runtime();
    fake_block_reply = true;
    failures += prepare_arm(session, 4u);
    ul_plugin_arm_checked(fake_scheduled_generation, true);
    failures += check(WaitForSingleObject(fake_reply_written, 2000) ==
                          WAIT_OBJECT_0,
                      "capture sees Arm reply write in flight");
    ul_plugin_stream_event(UL_STREAM_STARTING);
    ul_plugin_stream_event(UL_STREAM_STARTED);
    failures += check(ul_plugin_capture_inspect_request(&generation,
                                                        &observed_mask) &&
                          generation == fake_scheduled_generation &&
                          observed_mask == 4u,
                      "inspection may copy metadata while reply is in flight");
    ul_plugin_capture_inspected(generation, &spec);
    Sleep(20u);
    failures += check(InterlockedCompareExchange(&fake_capture_create_count, 0, 0) == 0,
                      "capture is not created before full accepted Arm reply");
    SetEvent(fake_reply_release);
    failures += check(WaitForSingleObject(fake_capture_schedule_entered, 2000) ==
                          WAIT_OBJECT_0 && fake_create_after_reply,
                      "capture create and attach schedule follow reply completion");
    borrowed = ul_plugin_capture_retain(generation);
    failures += check(borrowed != NULL && borrowed->refs == 2,
                      "frontend takes an independent capture reference");
    ul_plugin_capture_attached(generation, borrowed, true);
    shim_ul_audio_capture_release(borrowed);
    failures += check(WaitForSingleObject(fake_stream_entered, 2000) ==
                          WAIT_OBJECT_0 &&
                          InterlockedCompareExchange(&fake_capture_activate_count, 0, 0) == 1,
                      "matching attach activates and enters stream worker");
    fake_hold_after_stop = true;
    ul_plugin_stream_event(UL_STREAM_STOPPING);
    failures += check(wait_phase(UL_SESSION_DRAINING, 2000),
                      "STOPPING preserves worker for clean drain and End ACK");
    ul_plugin_stream_event(UL_STREAM_STOPPED);
    failures += check(ul_plugin_session_status() == UL_SESSION_DRAINING,
                      "duplicate STOPPED does not abort clean End");
    SetEvent(fake_stream_release);
    failures += check(wait_worker_inactive(2000) &&
                          WaitForSingleObject(fake_cleanup_entered, 2000) ==
                              WAIT_OBJECT_0,
                      "clean stream retires worker and queues cleanup without UI wait");
    ul_plugin_close();
    close_capture_events();
    GetProcessHandleCount(GetCurrentProcess(), &after);
    failures += check(before == after,
                      "capture result and stream stop handles close with runtime");
    return failures;
}

static int scenario_capture_failures(void)
{
    uint8_t session[16] = {0x91};
    ul_audio_capture_spec spec = capture_spec(0u, 1u);
    ul_audio_capture *stale, *current;
    uintptr_t generation = 0u, stale_generation;
    int failures = start_capture_runtime();

    failures += reach_capture_started(session, 0u, &generation);
    ul_plugin_capture_inspected(generation, NULL);
    failures += check(wait_worker_inactive(2000) &&
                          InterlockedCompareExchange(&fake_capture_create_count, 0, 0) == 0,
                      "failed inspection retires without capture creation");

    session[0]++;
    ResetEvent(fake_capture_schedule_entered);
    failures += reach_capture_started(session, 0u, &generation);
    ul_plugin_capture_inspected(generation, &spec);
    failures += check(WaitForSingleObject(fake_capture_schedule_entered, 2000) ==
                          WAIT_OBJECT_0,
                      "valid inspection schedules attachment");
    stale_generation = generation;
    stale = ul_plugin_capture_retain(stale_generation);
    failures += check(stale != NULL, "pending frontend retain succeeds");
    failures += check(wait_worker_inactive(2000) && stale->refs == 1,
                      "missing attach times out while retained frontend reference survives");

    session[0]++;
    ResetEvent(fake_capture_schedule_entered);
    ResetEvent(fake_stream_entered);
    failures += reach_capture_started(session, 0u, &generation);
    failures += check(generation != stale_generation,
                      "new preparation advances capture generation and resets flags");
    ul_plugin_capture_inspected(generation, &spec);
    failures += check(WaitForSingleObject(fake_capture_schedule_entered, 2000) ==
                          WAIT_OBJECT_0,
                      "new generation schedules independent attach");
    ul_plugin_capture_attached(stale_generation, stale, true);
    current = ul_plugin_capture_retain(generation);
    failures += check(current != NULL && current != stale,
                      "stale attach reply cannot bind new generation");
    ul_plugin_capture_attached(generation, current, false);
    shim_ul_audio_capture_release(current);
    failures += check(wait_worker_inactive(2000) &&
                          InterlockedCompareExchange(&fake_stream_count, 0, 0) == 0,
                      "explicit attach refusal never enters stream");
    shim_ul_audio_capture_release(stale);
    failures += check(InterlockedCompareExchange(&fake_capture_free_count, 0, 0) >= 2,
                      "worker and independent frontend capture references release");

    session[0]++;
    ResetEvent(fake_capture_schedule_entered);
    failures += reach_capture_started(session, 0u, &generation);
    ul_plugin_capture_inspected(generation, &spec);
    failures += check(WaitForSingleObject(fake_capture_schedule_entered, 2000) ==
                          WAIT_OBJECT_0,
                      "stop-before-attach case reaches queued frontend work");
    current = ul_plugin_capture_retain(generation);
    ul_plugin_stream_event(UL_STREAM_STOPPING);
    failures += check(wait_worker_inactive(2000),
                      "stop before attach is incomplete and cancels worker");
    ul_plugin_capture_attached(generation, current, true);
    shim_ul_audio_capture_release(current);
    failures += check(InterlockedCompareExchange(&fake_stream_count, 0, 0) == 0 &&
                          InterlockedCompareExchange(&fake_capture_activate_count, 0, 0) == 0,
                      "late stop-before-attach reply cannot activate capture");

    session[0]++;
    ResetEvent(fake_capture_schedule_entered);
    ResetEvent(fake_stream_entered);
    ResetEvent(fake_cleanup_entered);
    failures += reach_capture_started(session, 0u, &generation);
    ul_plugin_capture_inspected(generation, &spec);
    failures += check(WaitForSingleObject(fake_capture_schedule_entered, 2000) ==
                          WAIT_OBJECT_0,
                      "short stream schedules attach");
    current = ul_plugin_capture_retain(generation);
    fake_stream_result = UL_AUDIO_STREAM_INCOMPLETE;
    ul_plugin_capture_attached(generation, current, true);
    shim_ul_audio_capture_release(current);
    failures += check(WaitForSingleObject(fake_stream_entered, 2000) ==
                          WAIT_OBJECT_0,
                      "short stream enters transport after attach");
    ul_plugin_stream_event(UL_STREAM_STOPPED);
    failures += check(wait_worker_inactive(2000) &&
                          InterlockedCompareExchange(&fake_stream_count, 0, 0) == 1 &&
                          WaitForSingleObject(fake_cleanup_entered, 0) == WAIT_OBJECT_0,
                      "short stream returns incomplete and still queues cleanup");
    ul_plugin_close();
    close_capture_events();
    return failures;
}

static int scenario_capture_cancel(void)
{
    uint8_t session[16] = {0xa1};
    ul_audio_capture_spec spec = capture_spec(0u, 1u);
    ul_audio_capture *borrowed;
    uintptr_t generation = 0u;
    LONG free_before;
    int failures = start_capture_runtime();

    failures += reach_capture_started(session, 0u, &generation);
    ul_plugin_capture_inspected(generation, &spec);
    failures += check(WaitForSingleObject(fake_capture_schedule_entered, 2000) ==
                          WAIT_OBJECT_0,
                      "cancel case schedules capture attach");
    borrowed = ul_plugin_capture_retain(generation);
    ul_plugin_capture_attached(generation, borrowed, true);
    failures += check(WaitForSingleObject(fake_stream_entered, 2000) ==
                          WAIT_OBJECT_0,
                      "cancel case enters audio stream");
    free_before = InterlockedCompareExchange(&fake_capture_free_count, 0, 0);
    ul_plugin_close();
    failures += check(borrowed != NULL && borrowed->refs == 1 &&
                          InterlockedCompareExchange(&fake_capture_free_count, 0, 0) ==
                              free_before &&
                          WaitForSingleObject(fake_cleanup_entered, 0) ==
                              WAIT_OBJECT_0,
                      "hard close cancels I/O and worker while frontend retain survives");
    shim_ul_audio_capture_release(borrowed);
    failures += check(InterlockedCompareExchange(&fake_capture_free_count, 0, 0) ==
                          free_before + 1,
                      "frontend releases retained capture after runtime close");
    close_capture_events();
    return failures;
}

static int scenario_disarm_lifecycle(void)
{
    uint8_t session[16] = {0xb1, 2, 3};
    ul_audio_capture_spec spec = capture_spec(0u, 1u);
    ul_audio_capture *borrowed;
    uintptr_t generation = 0u;
    int failures = start_capture_runtime();

    failures += prepare_arm(session, 0u);
    ul_plugin_arm_checked(fake_scheduled_generation, true);
    failures += check(WaitForSingleObject(fake_reply_written, 2000u) ==
                          WAIT_OBJECT_0 && wait_phase(UL_SESSION_ARMED, 2000u),
                      "pre-Start Disarm reaches ARMED");
    failures += check(queue_disarm(session) && wait_worker_inactive(2000u) &&
                          InterlockedCompareExchange(&fake_empty_disarm_count,
                                                     0, 0) == 1 &&
                          InterlockedCompareExchange(&fake_capture_create_count,
                                                     0, 0) == 0,
                      "pre-Start Disarm sends empty terminal without capture");

    session[0]++;
    ResetEvent(fake_capture_schedule_entered);
    ResetEvent(fake_cleanup_entered);
    failures += reach_capture_started(session, 0u, &generation);
    ul_plugin_capture_inspected(generation, &spec);
    failures += check(WaitForSingleObject(fake_capture_schedule_entered, 2000u) ==
                          WAIT_OBJECT_0,
                      "attach-race Disarm reaches queued attach");
    borrowed = ul_plugin_capture_retain(generation);
    failures += check(borrowed != NULL && queue_disarm(session) &&
                          WaitForSingleObject(fake_cleanup_entered, 2000u) ==
                              WAIT_OBJECT_0 &&
                          wait_phase(UL_SESSION_DISARMING, 2000u),
                      "Disarm while attach pending queues frontend detach");
    ul_plugin_capture_cleanup_complete(generation + 1u);
    Sleep(20u);
    failures += check(ul_plugin_get_status().admission_pending,
                      "stale cleanup completion cannot release Disarm");
    ul_plugin_capture_attached(generation, borrowed, true);
    failures += check(InterlockedCompareExchange(&fake_capture_activate_count,
                                                 0, 0) == 0,
                      "late attach completion cannot activate DISARMING capture");
    ul_plugin_capture_cleanup_complete(generation);
    shim_ul_audio_capture_release(borrowed);
    failures += check(wait_worker_inactive(2000u) &&
                          InterlockedCompareExchange(&fake_empty_disarm_count,
                                                     0, 0) == 2,
                      "matching detach permits empty Disarmed terminal");

    session[0]++;
    ResetEvent(fake_capture_schedule_entered);
    ResetEvent(fake_cleanup_entered);
    fake_disarm_read_entered = CreateEventW(NULL, TRUE, FALSE, NULL);
    fake_disarm_read_release = CreateEventW(NULL, TRUE, FALSE, NULL);
    failures += check(fake_disarm_read_entered != NULL &&
                          fake_disarm_read_release != NULL,
                      "create blocked Disarm read coordination");
    failures += reach_capture_started(session, 0u, &generation);
    ul_plugin_capture_inspected(generation, &spec);
    failures += check(WaitForSingleObject(fake_capture_schedule_entered, 2000u) ==
                          WAIT_OBJECT_0,
                      "blocked-read race reaches queued attach");
    borrowed = ul_plugin_capture_retain(generation);
    failures += check(borrowed != NULL && queue_disarm(session) &&
                          WaitForSingleObject(fake_disarm_read_entered, 2000u) ==
                              WAIT_OBJECT_0,
                      "Disarm read blocks while frontend owns capture reference");
    ul_plugin_capture_attached(generation, borrowed, true);
    shim_ul_audio_capture_release(borrowed);
    failures += check(InterlockedCompareExchange(&fake_capture_activate_count,
                                                 0, 0) == 1,
                      "attach commits before blocked Disarm parses");
    SetEvent(fake_disarm_read_release);
    failures += check(WaitForSingleObject(fake_cleanup_entered, 2000u) ==
                          WAIT_OBJECT_0 &&
                          wait_phase(UL_SESSION_DISARMING, 2000u),
                      "parsed Disarm serializes after committed attach");
    ul_plugin_capture_cleanup_complete(generation);
    failures += check(wait_worker_inactive(2000u) &&
                          InterlockedCompareExchange(&fake_stream_disarm_count,
                                                     0, 0) == 1 &&
                          InterlockedCompareExchange(&fake_empty_disarm_count,
                                                     0, 0) == 2,
                      "committed attach uses stopped-queue drain, not empty shortcut");
    CloseHandle(fake_disarm_read_entered);
    CloseHandle(fake_disarm_read_release);
    fake_disarm_read_entered = fake_disarm_read_release = NULL;

    session[0]++;
    ResetEvent(fake_capture_schedule_entered);
    ResetEvent(fake_cleanup_entered);
    ResetEvent(fake_stream_entered);
    fake_stream_requests_disarm = true;
    failures += reach_capture_started(session, 0u, &generation);
    ul_plugin_capture_inspected(generation, &spec);
    failures += check(WaitForSingleObject(fake_capture_schedule_entered, 2000u) ==
                          WAIT_OBJECT_0,
                      "active Disarm reaches capture attach");
    borrowed = ul_plugin_capture_retain(generation);
    ul_plugin_capture_attached(generation, borrowed, true);
    shim_ul_audio_capture_release(borrowed);
    failures += check(WaitForSingleObject(fake_cleanup_entered, 2000u) ==
                          WAIT_OBJECT_0 &&
                          wait_phase(UL_SESSION_DISARMING, 2000u),
                      "active Disarm commits once and queues detach");
    ul_plugin_stream_event(UL_STREAM_STOPPING);
    ul_plugin_stream_event(UL_STREAM_STOPPED);
    failures += check(wait_worker_inactive(2000u) &&
                          InterlockedCompareExchange(&fake_stream_disarm_count,
                                                     0, 0) == 2,
                      "concurrent OBS stop completes detach without cancelling End");
    fake_stream_requests_disarm = false;

    session[0]++;
    ResetEvent(fake_capture_schedule_entered);
    ResetEvent(fake_cleanup_entered);
    failures += reach_capture_started(session, 0u, &generation);
    ul_plugin_capture_inspected(generation, &spec);
    failures += check(WaitForSingleObject(fake_capture_schedule_entered, 2000u) ==
                          WAIT_OBJECT_0,
                      "cleanup-post failure reaches pending attach");
    fake_cleanup_schedule_result = false;
    failures += check(queue_disarm(session), "queue cleanup-post failure Disarm");
    failures += check(wait_phase(UL_SESSION_TERMINAL, 2000u),
                      "failed cleanup post leaves session terminal");
    failures += check(wait_worker_inactive(2000u),
                      "failed cleanup post cancels without deadlock");
    failures += check(InterlockedCompareExchange(&fake_empty_disarm_count,
                                                 0, 0) == 2,
                      "failed cleanup post emits no empty End");
    fake_cleanup_schedule_result = true;
    ul_plugin_close();
    close_capture_events();
    return failures;
}

static int scenario_capture_event_failure(DWORD event_number)
{
    DWORD before = 0u, after = 0u;
    int failures = 0;
    GetProcessHandleCount(GetCurrentProcess(), &before);
    fake_create_event_fail_at = event_number;
    failures += check(!ul_plugin_start(), "session event failure rejects start");
    GetProcessHandleCount(GetCurrentProcess(), &after);
    failures += check(before == after,
                      "partial session event creation closes every handle");
    return failures;
}

static int scenario_disarm_close_pending(void)
{
    uint8_t session[16] = {0xc1, 2, 3};
    ul_audio_capture_spec spec = capture_spec(0u, 1u);
    ul_audio_capture *borrowed;
    uintptr_t generation = 0u;
    ULONGLONG before;
    int failures = start_capture_runtime();
    fake_stream_requests_disarm = true;
    failures += reach_capture_started(session, 0u, &generation);
    ul_plugin_capture_inspected(generation, &spec);
    failures += check(WaitForSingleObject(fake_capture_schedule_entered, 2000u) ==
                          WAIT_OBJECT_0,
                      "pending-close Disarm reaches attach");
    borrowed = ul_plugin_capture_retain(generation);
    ul_plugin_capture_attached(generation, borrowed, true);
    shim_ul_audio_capture_release(borrowed);
    failures += check(WaitForSingleObject(fake_cleanup_entered, 2000u) ==
                          WAIT_OBJECT_0 &&
                          wait_phase(UL_SESSION_DISARMING, 2000u),
                      "pending-close Disarm waits for frontend cleanup");
    before = GetTickCount64();
    ul_plugin_stop_accepting();
    ul_plugin_close();
    failures += check(GetTickCount64() - before < 1000u,
                      "close cancellation wakes cleanup wait and joins promptly");
    ul_plugin_capture_cleanup_complete(generation);
    failures += check(ul_plugin_get_status().status == UL_PLUGIN_CLOSED,
                      "late cleanup completion is inert after close");
    fake_stream_requests_disarm = false;
    close_capture_events();
    return failures;
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
    if (strcmp(scenario, "arm-valid") == 0)
        return scenario_arm_valid();
    if (strcmp(scenario, "arm-order") == 0)
        return scenario_arm_ordering();
    if (strcmp(scenario, "arm-start-timeout") == 0)
        return scenario_arm_start_timeout();
    if (strcmp(scenario, "arm-stale") == 0)
        return scenario_arm_stale_and_commands();
    if (strcmp(scenario, "arm-bound") == 0)
        return scenario_arm_bound_command();
    if (strcmp(scenario, "arm-teardown") == 0)
        return scenario_arm_teardown();
    if (strcmp(scenario, "arm-close") == 0)
        return scenario_arm_close_pending();
    if (strcmp(scenario, "capture-clean") == 0)
        return scenario_capture_clean();
    if (strcmp(scenario, "capture-failures") == 0)
        return scenario_capture_failures();
    if (strcmp(scenario, "capture-cancel") == 0)
        return scenario_capture_cancel();
    if (strcmp(scenario, "capture-event-fail") == 0)
        return scenario_capture_event_failure(4u);
    if (strcmp(scenario, "cleanup-event-fail") == 0)
        return scenario_capture_event_failure(5u);
    if (strcmp(scenario, "stream-event-fail") == 0)
        return scenario_capture_event_failure(6u);
    if (strcmp(scenario, "disarm-lifecycle") == 0)
        return scenario_disarm_lifecycle();
    if (strcmp(scenario, "disarm-close") == 0)
        return scenario_disarm_close_pending();
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
        L"expiry", L"cancel", L"dispatch", L"arm-valid", L"arm-order",
        L"arm-start-timeout", L"arm-stale", L"arm-bound", L"arm-teardown",
        L"arm-close", L"capture-clean", L"capture-failures",
        L"capture-cancel", L"capture-event-fail", L"cleanup-event-fail",
        L"stream-event-fail", L"disarm-lifecycle", L"disarm-close"};
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
