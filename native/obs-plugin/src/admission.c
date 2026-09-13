// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0600
#endif

#include "admission.h"
#include "handshake.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define UL_MAX_TOKEN_BYTES 65536u
#define UL_MAX_SID_BYTES 68u
#define UL_IO_POLL_MS 50u
#define UL_PIPE_BUFFER_BYTES 4096u

typedef struct ul_identity {
    PSID user_sid;
    DWORD user_sid_size;
    PSID logon_sid;
    DWORD logon_sid_size;
    DWORD session_id;
    LUID authentication_id;
} ul_identity;

struct ul_admission {
    HANDLE pipe;
    HANDLE cancel_event;
    HANDLE expected_process;
    DWORD expected_pid;
    ULONGLONG expected_creation_time;
    uint8_t expected_session[16];
    ul_identity expected_identity;
    ul_identity server_identity;
    volatile LONG cancelled;
    volatile LONG consumed;
    volatile LONG authenticated;
    volatile LONG read_count;
    uint8_t hello[ULAH_HANDSHAKE_BYTES];
    uint8_t ack[ULAH_HANDSHAKE_BYTES];
};

typedef enum ul_operation_result {
    UL_OPERATION_OK,
    UL_OPERATION_CANCELLED,
    UL_OPERATION_TIMEOUT,
    UL_OPERATION_IO_ERROR,
} ul_operation_result;

static void secure_heap_free(void *memory, SIZE_T size)
{
    if (memory != NULL) {
        SecureZeroMemory(memory, size);
        HeapFree(GetProcessHeap(), 0, memory);
    }
}

static void identity_clear(ul_identity *identity)
{
    if (identity == NULL)
        return;
    secure_heap_free(identity->user_sid, identity->user_sid_size);
    secure_heap_free(identity->logon_sid, identity->logon_sid_size);
    SecureZeroMemory(identity, sizeof(*identity));
}

static BOOL token_information(HANDLE token, TOKEN_INFORMATION_CLASS kind,
                              void **buffer_out, DWORD *size_out)
{
    DWORD needed = 0;
    DWORD returned = 0;
    void *buffer;

    *buffer_out = NULL;
    *size_out = 0;
    if (GetTokenInformation(token, kind, NULL, 0, &needed) ||
        GetLastError() != ERROR_INSUFFICIENT_BUFFER || needed == 0u ||
        needed > UL_MAX_TOKEN_BYTES)
        return FALSE;
    buffer = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, needed);
    if (buffer == NULL)
        return FALSE;
    if (!GetTokenInformation(token, kind, buffer, needed, &returned) ||
        returned == 0u || returned > needed) {
        secure_heap_free(buffer, needed);
        return FALSE;
    }
    *buffer_out = buffer;
    *size_out = returned;
    return TRUE;
}

static BOOL bounded_sid(const void *buffer, DWORD buffer_size, PSID sid,
                        DWORD *sid_size)
{
    uintptr_t begin = (uintptr_t)buffer;
    uintptr_t candidate = (uintptr_t)sid;
    const uint8_t *sid_bytes = (const uint8_t *)sid;
    DWORD offset;
    DWORD length;

    if (buffer == NULL || sid == NULL || buffer_size < 8u ||
        candidate < begin || candidate - begin > buffer_size - 8u)
        return FALSE;
    offset = (DWORD)(candidate - begin);
    if (sid_bytes[0] != SID_REVISION ||
        sid_bytes[1] > SID_MAX_SUB_AUTHORITIES)
        return FALSE;
    length = 8u + ((DWORD)sid_bytes[1] * sizeof(DWORD));
    if (length > UL_MAX_SID_BYTES || length > buffer_size - offset ||
        !IsValidSid(sid) || GetLengthSid(sid) != length)
        return FALSE;
    *sid_size = length;
    return TRUE;
}

static PSID copy_bounded_sid(PSID sid, DWORD sid_size)
{
    PSID copy;

    if (sid == NULL || sid_size == 0u || sid_size > UL_MAX_SID_BYTES)
        return NULL;
    copy = (PSID)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sid_size);
    if (copy == NULL)
        return NULL;
    if (!CopySid(sid_size, copy, sid)) {
        secure_heap_free(copy, sid_size);
        return NULL;
    }
    return copy;
}

static BOOL snapshot_identity(HANDLE process, ul_identity *identity)
{
    HANDLE token = NULL;
    void *user_buffer = NULL;
    void *groups_buffer = NULL;
    void *session_buffer = NULL;
    void *statistics_buffer = NULL;
    DWORD user_size = 0;
    DWORD groups_size = 0;
    DWORD session_size = 0;
    DWORD statistics_size = 0;
    TOKEN_USER *user;
    TOKEN_GROUPS *groups;
    TOKEN_STATISTICS *statistics;
    PSID logon_sid = NULL;
    DWORD user_sid_size = 0;
    DWORD logon_sid_size = 0;
    DWORD group_count;
    DWORD group_index;
    SIZE_T groups_needed;
    BOOL success = FALSE;

    SecureZeroMemory(identity, sizeof(*identity));
    if (!OpenProcessToken(process, TOKEN_QUERY, &token))
        goto cleanup;
    if (!token_information(token, TokenUser, &user_buffer, &user_size) ||
        user_size < sizeof(TOKEN_USER))
        goto cleanup;
    user = (TOKEN_USER *)user_buffer;
    if (!bounded_sid(user_buffer, user_size, user->User.Sid, &user_sid_size))
        goto cleanup;

    if (!token_information(token, TokenLogonSid, &groups_buffer, &groups_size) ||
        groups_size < offsetof(TOKEN_GROUPS, Groups))
        goto cleanup;
    groups = (TOKEN_GROUPS *)groups_buffer;
    group_count = groups->GroupCount;
    if (group_count == 0u ||
        group_count > (UL_MAX_TOKEN_BYTES / sizeof(SID_AND_ATTRIBUTES)))
        goto cleanup;
    groups_needed = offsetof(TOKEN_GROUPS, Groups) +
                    ((SIZE_T)group_count * sizeof(SID_AND_ATTRIBUTES));
    if (groups_needed > groups_size)
        goto cleanup;
    for (group_index = 0; group_index < group_count; ++group_index) {
        SID_AND_ATTRIBUTES *group = &groups->Groups[group_index];
        DWORD candidate_size = 0;

        if ((group->Attributes & SE_GROUP_LOGON_ID) != SE_GROUP_LOGON_ID)
            continue;
        if (logon_sid != NULL ||
            !bounded_sid(groups_buffer, groups_size, group->Sid,
                         &candidate_size))
            goto cleanup;
        logon_sid = group->Sid;
        logon_sid_size = candidate_size;
    }
    if (logon_sid == NULL)
        goto cleanup;

    if (!token_information(token, TokenSessionId, &session_buffer,
                           &session_size) ||
        session_size < sizeof(DWORD))
        goto cleanup;
    if (!token_information(token, TokenStatistics, &statistics_buffer,
                           &statistics_size) ||
        statistics_size < sizeof(TOKEN_STATISTICS))
        goto cleanup;
    statistics = (TOKEN_STATISTICS *)statistics_buffer;

    identity->user_sid = copy_bounded_sid(user->User.Sid, user_sid_size);
    if (identity->user_sid == NULL)
        goto cleanup;
    identity->user_sid_size = user_sid_size;
    identity->logon_sid = copy_bounded_sid(logon_sid, logon_sid_size);
    if (identity->logon_sid == NULL)
        goto cleanup;
    identity->logon_sid_size = logon_sid_size;
    memcpy(&identity->session_id, session_buffer, sizeof(identity->session_id));
    identity->authentication_id = statistics->AuthenticationId;
    success = TRUE;

cleanup:
    if (token != NULL)
        CloseHandle(token);
    secure_heap_free(user_buffer, user_size);
    secure_heap_free(groups_buffer, groups_size);
    secure_heap_free(session_buffer, session_size);
    secure_heap_free(statistics_buffer, statistics_size);
    if (!success)
        identity_clear(identity);
    return success;
}

static BOOL identities_equal(const ul_identity *left,
                             const ul_identity *right)
{
    return left->user_sid != NULL && right->user_sid != NULL &&
           left->logon_sid != NULL && right->logon_sid != NULL &&
           EqualSid(left->user_sid, right->user_sid) &&
           EqualSid(left->logon_sid, right->logon_sid) &&
           left->session_id == right->session_id &&
           left->authentication_id.LowPart ==
               right->authentication_id.LowPart &&
           left->authentication_id.HighPart ==
               right->authentication_id.HighPart;
}

static BOOL process_is_alive(HANDLE process)
{
    return WaitForSingleObject(process, 0) == WAIT_TIMEOUT;
}

static BOOL process_creation_time(HANDLE process, ULONGLONG *result)
{
    FILETIME creation;
    FILETIME exit_time;
    FILETIME kernel_time;
    FILETIME user_time;
    ULARGE_INTEGER value;

    if (!GetProcessTimes(process, &creation, &exit_time, &kernel_time,
                         &user_time))
        return FALSE;
    value.LowPart = creation.dwLowDateTime;
    value.HighPart = creation.dwHighDateTime;
    if (value.QuadPart == 0u)
        return FALSE;
    *result = value.QuadPart;
    return TRUE;
}

static BOOL build_pipe_name(const uint8_t session[16], WCHAR name[64])
{
    static const WCHAR prefix[] = L"\\\\.\\pipe\\Utterleaf.OBS.";
    static const WCHAR hex[] = L"0123456789abcdef";
    size_t prefix_size = (sizeof(prefix) / sizeof(prefix[0])) - 1u;
    size_t index;

    if (prefix_size + 32u + 1u > 64u)
        return FALSE;
    memcpy(name, prefix, prefix_size * sizeof(WCHAR));
    for (index = 0; index < 16u; ++index) {
        name[prefix_size + (index * 2u)] = hex[session[index] >> 4];
        name[prefix_size + (index * 2u) + 1u] = hex[session[index] & 0x0fu];
    }
    name[prefix_size + 32u] = L'\0';
    return TRUE;
}

static PACL build_logon_dacl(PSID logon_sid, DWORD logon_sid_size,
                             DWORD *acl_size_out)
{
    SIZE_T needed = sizeof(ACL) + sizeof(ACCESS_ALLOWED_ACE) - sizeof(DWORD) +
                    logon_sid_size;
    PACL acl;

    *acl_size_out = 0;
    if (logon_sid == NULL || logon_sid_size == 0u ||
        logon_sid_size > UL_MAX_SID_BYTES || needed > 1024u)
        return NULL;
    acl = (PACL)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, needed);
    if (acl == NULL)
        return NULL;
    if (!InitializeAcl(acl, (DWORD)needed, ACL_REVISION) ||
        !AddAccessAllowedAceEx(acl, ACL_REVISION, 0,
                               GENERIC_READ | GENERIC_WRITE, logon_sid)) {
        secure_heap_free(acl, needed);
        return NULL;
    }
    *acl_size_out = (DWORD)needed;
    return acl;
}

static ul_operation_result progress_result(const ul_admission *admission,
                                           ULONGLONG started,
                                           DWORD timeout_ms,
                                           DWORD *remaining)
{
    ULONGLONG elapsed;

    if (InterlockedCompareExchange(
            (volatile LONG *)&admission->cancelled, 0, 0) != 0)
        return UL_OPERATION_CANCELLED;
    elapsed = GetTickCount64() - started;
    if (elapsed >= timeout_ms) {
        *remaining = 0;
        return UL_OPERATION_TIMEOUT;
    }
    *remaining = timeout_ms - (DWORD)elapsed;
    return UL_OPERATION_OK;
}

static void drain_cancelled_io(HANDLE pipe, OVERLAPPED *overlapped)
{
    DWORD transferred = 0;

    CancelIoEx(pipe, overlapped);
    for (;;) {
        DWORD error;
        DWORD waited;

        if (GetOverlappedResult(pipe, overlapped, &transferred, FALSE))
            return;
        error = GetLastError();
        if (error != ERROR_IO_INCOMPLETE)
            return;
        waited = WaitForSingleObject(overlapped->hEvent, UL_IO_POLL_MS);
        if (waited == WAIT_OBJECT_0)
            Sleep(1);
        else if (waited == WAIT_FAILED)
            Sleep(UL_IO_POLL_MS);
    }
}

static ul_operation_result await_overlapped(ul_admission *admission,
                                            OVERLAPPED *overlapped,
                                            ULONGLONG started,
                                            DWORD timeout_ms,
                                            DWORD *transferred)
{
    HANDLE waits[2] = {overlapped->hEvent, admission->cancel_event};
    BOOL signalled_but_incomplete = FALSE;

    for (;;) {
        DWORD error;
        DWORD remaining = 0;
        DWORD wait_ms;
        DWORD waited;
        ul_operation_result progress;

        if (GetOverlappedResult(admission->pipe, overlapped, transferred,
                                FALSE)) {
            progress = progress_result(admission, started, timeout_ms,
                                       &remaining);
            return progress;
        }
        error = GetLastError();
        if (error != ERROR_IO_INCOMPLETE) {
            progress = progress_result(admission, started, timeout_ms,
                                       &remaining);
            return progress == UL_OPERATION_OK ? UL_OPERATION_IO_ERROR
                                               : progress;
        }
        progress = progress_result(admission, started, timeout_ms, &remaining);
        if (progress != UL_OPERATION_OK) {
            drain_cancelled_io(admission->pipe, overlapped);
            return progress;
        }
        wait_ms = remaining < UL_IO_POLL_MS ? remaining : UL_IO_POLL_MS;
        if (signalled_but_incomplete) {
            waited = WaitForSingleObject(admission->cancel_event, wait_ms);
            signalled_but_incomplete = FALSE;
            if (waited == WAIT_OBJECT_0)
                continue;
            if (waited == WAIT_FAILED) {
                drain_cancelled_io(admission->pipe, overlapped);
                return UL_OPERATION_IO_ERROR;
            }
        } else {
            waited = WaitForMultipleObjects(2, waits, FALSE, wait_ms);
            if (waited == WAIT_OBJECT_0)
                signalled_but_incomplete = TRUE;
            else if (waited == WAIT_OBJECT_0 + 1u)
                continue;
            else if (waited != WAIT_TIMEOUT) {
                drain_cancelled_io(admission->pipe, overlapped);
                return UL_OPERATION_IO_ERROR;
            }
        }
    }
}

static void initialize_overlapped(OVERLAPPED *overlapped, HANDLE event)
{
    SecureZeroMemory(overlapped, sizeof(*overlapped));
    overlapped->hEvent = event;
    ResetEvent(event);
}

static ul_operation_result connect_pipe(ul_admission *admission,
                                        OVERLAPPED *overlapped,
                                        ULONGLONG started,
                                        DWORD timeout_ms)
{
    DWORD transferred = 0;
    DWORD error;
    DWORD remaining = 0;
    ul_operation_result progress =
        progress_result(admission, started, timeout_ms, &remaining);

    if (progress != UL_OPERATION_OK)
        return progress;
    initialize_overlapped(overlapped, overlapped->hEvent);
    if (ConnectNamedPipe(admission->pipe, overlapped))
        return progress_result(admission, started, timeout_ms, &remaining);
    error = GetLastError();
    if (error == ERROR_PIPE_CONNECTED)
        return progress_result(admission, started, timeout_ms, &remaining);
    if (error != ERROR_IO_PENDING)
        return UL_OPERATION_IO_ERROR;
    return await_overlapped(admission, overlapped, started, timeout_ms,
                            &transferred);
}

static ul_operation_result read_pipe(ul_admission *admission,
                                     OVERLAPPED *overlapped, void *buffer,
                                     DWORD size, ULONGLONG started,
                                     DWORD timeout_ms, DWORD *transferred)
{
    DWORD remaining = 0;
    ul_operation_result progress =
        progress_result(admission, started, timeout_ms, &remaining);

    if (progress != UL_OPERATION_OK)
        return progress;
    initialize_overlapped(overlapped, overlapped->hEvent);
    *transferred = 0;
    if (ReadFile(admission->pipe, buffer, size, NULL, overlapped)) {
        if (!GetOverlappedResult(admission->pipe, overlapped, transferred,
                                 FALSE))
            return UL_OPERATION_IO_ERROR;
        return progress_result(admission, started, timeout_ms, &remaining);
    }
    if (GetLastError() != ERROR_IO_PENDING)
        return UL_OPERATION_IO_ERROR;
    return await_overlapped(admission, overlapped, started, timeout_ms,
                            transferred);
}

static ul_operation_result write_pipe(ul_admission *admission,
                                      OVERLAPPED *overlapped,
                                      const void *buffer, DWORD size,
                                      ULONGLONG started, DWORD timeout_ms,
                                      DWORD *transferred)
{
    DWORD remaining = 0;
    ul_operation_result progress =
        progress_result(admission, started, timeout_ms, &remaining);

    if (progress != UL_OPERATION_OK)
        return progress;
    initialize_overlapped(overlapped, overlapped->hEvent);
    *transferred = 0;
    if (WriteFile(admission->pipe, buffer, size, NULL, overlapped)) {
        if (!GetOverlappedResult(admission->pipe, overlapped, transferred,
                                 FALSE))
            return UL_OPERATION_IO_ERROR;
        return progress_result(admission, started, timeout_ms, &remaining);
    }
    if (GetLastError() != ERROR_IO_PENDING)
        return UL_OPERATION_IO_ERROR;
    return await_overlapped(admission, overlapped, started, timeout_ms,
                            transferred);
}

static BOOL peer_is_expected(ul_admission *admission)
{
    DWORD actual_pid = 0;
    ULONGLONG creation_time = 0;
    ul_identity actual_identity;
    BOOL valid = FALSE;

    SecureZeroMemory(&actual_identity, sizeof(actual_identity));
    if (!GetNamedPipeClientProcessId(admission->pipe, &actual_pid) ||
        actual_pid != admission->expected_pid ||
        !process_is_alive(admission->expected_process) ||
        !process_creation_time(admission->expected_process, &creation_time) ||
        creation_time != admission->expected_creation_time ||
        !snapshot_identity(admission->expected_process, &actual_identity))
        goto cleanup;
    valid = identities_equal(&actual_identity, &admission->expected_identity) &&
            identities_equal(&actual_identity, &admission->server_identity) &&
            process_is_alive(admission->expected_process);

cleanup:
    identity_clear(&actual_identity);
    return valid;
}

static int operation_to_public(ul_operation_result result)
{
    if (result == UL_OPERATION_CANCELLED)
        return UL_ADMISSION_CANCELLED;
    if (result == UL_OPERATION_TIMEOUT)
        return UL_ADMISSION_TIMEOUT;
    return UL_ADMISSION_IO_ERROR;
}

ul_admission *ul_admission_create(DWORD expected_pid,
                                  const uint8_t session[16])
{
    ul_admission *admission = NULL;
    PACL dacl = NULL;
    DWORD dacl_size = 0;
    SECURITY_DESCRIPTOR descriptor;
    SECURITY_ATTRIBUTES attributes;
    WCHAR pipe_name[64];

    if (session == NULL || expected_pid == 0u || expected_pid == 4u ||
        expected_pid == GetCurrentProcessId())
        return NULL;
    admission = (ul_admission *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY,
                                          sizeof(*admission));
    if (admission == NULL)
        return NULL;
    admission->expected_pid = expected_pid;
    memcpy(admission->expected_session, session,
           sizeof(admission->expected_session));
    admission->pipe = INVALID_HANDLE_VALUE;
    admission->expected_process = OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, expected_pid);
    if (admission->expected_process == NULL ||
        !process_is_alive(admission->expected_process) ||
        !process_creation_time(admission->expected_process,
                               &admission->expected_creation_time) ||
        !snapshot_identity(admission->expected_process,
                           &admission->expected_identity) ||
        !snapshot_identity(GetCurrentProcess(), &admission->server_identity) ||
        !identities_equal(&admission->expected_identity,
                          &admission->server_identity))
        goto failure;
    admission->cancel_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (admission->cancel_event == NULL || !build_pipe_name(session, pipe_name))
        goto failure;
    dacl = build_logon_dacl(admission->server_identity.logon_sid,
                            admission->server_identity.logon_sid_size,
                            &dacl_size);
    if (dacl == NULL ||
        !InitializeSecurityDescriptor(&descriptor,
                                      SECURITY_DESCRIPTOR_REVISION) ||
        !SetSecurityDescriptorDacl(&descriptor, TRUE, dacl, FALSE))
        goto failure;
    attributes.nLength = sizeof(attributes);
    attributes.lpSecurityDescriptor = &descriptor;
    attributes.bInheritHandle = FALSE;
    admission->pipe = CreateNamedPipeW(
        pipe_name,
        PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE |
            FILE_FLAG_OVERLAPPED,
        PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_REJECT_REMOTE_CLIENTS, 1,
        UL_PIPE_BUFFER_BYTES, UL_PIPE_BUFFER_BYTES, 0, &attributes);
    secure_heap_free(dacl, dacl_size);
    dacl = NULL;
    if (admission->pipe == INVALID_HANDLE_VALUE)
        goto failure;
    SecureZeroMemory(pipe_name, sizeof(pipe_name));
    return admission;

failure:
    secure_heap_free(dacl, dacl_size);
    SecureZeroMemory(pipe_name, sizeof(pipe_name));
    ul_admission_destroy(admission);
    return NULL;
}

int ul_admission_authenticate(ul_admission *admission, DWORD timeout_ms)
{
    HANDLE io_event = NULL;
    OVERLAPPED overlapped;
    ULONGLONG started;
    size_t offset;
    int result = UL_ADMISSION_IO_ERROR;
    ul_operation_result operation;

    if (admission == NULL)
        return UL_ADMISSION_IO_ERROR;
    if (InterlockedCompareExchange(&admission->consumed, 1, 0) != 0)
        return UL_ADMISSION_REJECTED;
    if (timeout_ms == 0u || timeout_ms > 30000u)
        goto cleanup;
    started = GetTickCount64();
    io_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (io_event == NULL)
        goto cleanup;
    SecureZeroMemory(&overlapped, sizeof(overlapped));
    overlapped.hEvent = io_event;

    operation = connect_pipe(admission, &overlapped, started, timeout_ms);
    if (operation != UL_OPERATION_OK) {
        result = operation_to_public(operation);
        goto cleanup;
    }
    if (!peer_is_expected(admission)) {
        DWORD remaining = 0;
        operation = progress_result(admission, started, timeout_ms, &remaining);
        result = operation == UL_OPERATION_OK ? UL_ADMISSION_REJECTED
                                              : operation_to_public(operation);
        goto cleanup;
    }

    offset = 0;
    while (offset < ULAH_HANDSHAKE_BYTES) {
        DWORD transferred = 0;
        DWORD remaining = 0;

        operation = progress_result(admission, started, timeout_ms, &remaining);
        if (operation != UL_OPERATION_OK) {
            result = operation_to_public(operation);
            goto cleanup;
        }
        if (!peer_is_expected(admission)) {
            operation = progress_result(admission, started, timeout_ms,
                                        &remaining);
            result = operation == UL_OPERATION_OK
                         ? UL_ADMISSION_REJECTED
                         : operation_to_public(operation);
            goto cleanup;
        }
        operation = read_pipe(admission, &overlapped,
                              admission->hello + offset,
                              (DWORD)(ULAH_HANDSHAKE_BYTES - offset), started,
                              timeout_ms, &transferred);
        if (operation != UL_OPERATION_OK) {
            result = operation_to_public(operation);
            goto cleanup;
        }
        if (transferred == 0u ||
            transferred > (DWORD)(ULAH_HANDSHAKE_BYTES - offset))
            goto cleanup;
        InterlockedExchangeAdd(&admission->read_count, (LONG)transferred);
        offset += transferred;
    }
    if (!ul_handshake_ack(admission->hello, ULAH_HANDSHAKE_BYTES,
                          admission->expected_session, admission->ack)) {
        result = UL_ADMISSION_REJECTED;
        goto cleanup;
    }

    offset = 0;
    while (offset < ULAH_HANDSHAKE_BYTES) {
        DWORD transferred = 0;
        DWORD remaining = 0;

        operation = progress_result(admission, started, timeout_ms, &remaining);
        if (operation != UL_OPERATION_OK) {
            result = operation_to_public(operation);
            goto cleanup;
        }
        if (!peer_is_expected(admission)) {
            operation = progress_result(admission, started, timeout_ms,
                                        &remaining);
            result = operation == UL_OPERATION_OK
                         ? UL_ADMISSION_REJECTED
                         : operation_to_public(operation);
            goto cleanup;
        }
        operation = write_pipe(admission, &overlapped,
                               admission->ack + offset,
                               (DWORD)(ULAH_HANDSHAKE_BYTES - offset), started,
                               timeout_ms, &transferred);
        if (operation != UL_OPERATION_OK) {
            result = operation_to_public(operation);
            goto cleanup;
        }
        if (transferred == 0u ||
            transferred > (DWORD)(ULAH_HANDSHAKE_BYTES - offset))
            goto cleanup;
        offset += transferred;
    }
    {
        DWORD remaining = 0;
        operation = progress_result(admission, started, timeout_ms, &remaining);
    }
    if (operation != UL_OPERATION_OK) {
        result = operation_to_public(operation);
        goto cleanup;
    }
    InterlockedExchange(&admission->authenticated, 1);
    result = UL_ADMISSION_AUTH_OK;

cleanup:
    SecureZeroMemory(admission->hello, sizeof(admission->hello));
    SecureZeroMemory(admission->ack, sizeof(admission->ack));
    SecureZeroMemory(admission->expected_session,
                     sizeof(admission->expected_session));
    SecureZeroMemory(&overlapped, sizeof(overlapped));
    if (io_event != NULL)
        CloseHandle(io_event);
    if (result != UL_ADMISSION_AUTH_OK &&
        admission->pipe != INVALID_HANDLE_VALUE)
        DisconnectNamedPipe(admission->pipe);
    return result;
}

void ul_admission_cancel(ul_admission *admission)
{
    if (admission == NULL)
        return;
    InterlockedExchange(&admission->cancelled, 1);
    if (admission->cancel_event != NULL)
        SetEvent(admission->cancel_event);
    if (admission->pipe != INVALID_HANDLE_VALUE)
        CancelIoEx(admission->pipe, NULL);
}

void ul_admission_destroy(ul_admission *admission)
{
    if (admission == NULL)
        return;
    if (admission->pipe != INVALID_HANDLE_VALUE) {
        DisconnectNamedPipe(admission->pipe);
        CloseHandle(admission->pipe);
    }
    if (admission->cancel_event != NULL)
        CloseHandle(admission->cancel_event);
    if (admission->expected_process != NULL)
        CloseHandle(admission->expected_process);
    identity_clear(&admission->expected_identity);
    identity_clear(&admission->server_identity);
    SecureZeroMemory(admission, sizeof(*admission));
    HeapFree(GetProcessHeap(), 0, admission);
}

DWORD ul_admission_read_count(const ul_admission *admission)
{
    if (admission == NULL)
        return 0u;
    return (DWORD)InterlockedCompareExchange(
        (volatile LONG *)&admission->read_count, 0, 0);
}

HANDLE ul_admission_pipe(const ul_admission *admission)
{
    if (admission == NULL ||
        InterlockedCompareExchange(
            (volatile LONG *)&admission->authenticated, 0, 0) == 0 ||
        InterlockedCompareExchange(
            (volatile LONG *)&admission->cancelled, 0, 0) != 0)
        return NULL;
    return admission->pipe;
}
