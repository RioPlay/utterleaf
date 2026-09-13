// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0600
#endif

#include "../src/admission.h"
#include "../src/session_protocol.h"

#include <windows.h>

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

#define TEST_TIMEOUT_MS 5000u
#define PAYLOAD_BYTES 8193u

typedef struct test_peer {
    PROCESS_INFORMATION process;
    HANDLE ready;
    HANDLE release;
    HANDLE done;
    ul_admission *admission;
} test_peer;

typedef struct read_call {
    ul_admission *admission;
    uint8_t buffer[64];
    int result;
} read_call;

typedef struct write_call {
    ul_admission *admission;
    uint8_t buffer[UL_ADMISSION_MAX_IO_BYTES];
    int result;
} write_call;

static int check(BOOL condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "FAIL: %s (win32=%lu)\n", message,
                (unsigned long)GetLastError());
        return 1;
    }
    return 0;
}

static void make_session(uint8_t session[16], unsigned counter)
{
    ULONGLONG tick = GetTickCount64();
    DWORD pid = GetCurrentProcessId();

    memcpy(session, &tick, sizeof(tick));
    memcpy(session + 8, &pid, sizeof(pid));
    memcpy(session + 12, &counter, sizeof(counter));
}

static void session_hex(const uint8_t session[16], WCHAR output[33])
{
    static const WCHAR digits[] = L"0123456789abcdef";
    unsigned index;

    for (index = 0; index < 16u; ++index) {
        output[index * 2u] = digits[session[index] >> 4];
        output[index * 2u + 1u] = digits[session[index] & 15u];
    }
    output[32] = L'\0';
}

static BOOL parse_session(const WCHAR *input, uint8_t session[16])
{
    unsigned index;

    if (input == NULL || wcslen(input) != 32u)
        return FALSE;
    for (index = 0; index < 16u; ++index) {
        WCHAR high = input[index * 2u];
        WCHAR low = input[index * 2u + 1u];
        unsigned a;
        unsigned b;

        if (high >= L'0' && high <= L'9')
            a = (unsigned)(high - L'0');
        else if (high >= L'a' && high <= L'f')
            a = (unsigned)(high - L'a') + 10u;
        else
            return FALSE;
        if (low >= L'0' && low <= L'9')
            b = (unsigned)(low - L'0');
        else if (low >= L'a' && low <= L'f')
            b = (unsigned)(low - L'a') + 10u;
        else
            return FALSE;
        session[index] = (uint8_t)((a << 4) | b);
    }
    return TRUE;
}

static BOOL sync_write_all(HANDLE pipe, const uint8_t *buffer, DWORD size)
{
    DWORD offset = 0;

    while (offset < size) {
        DWORD transferred = 0;
        if (!WriteFile(pipe, buffer + offset, size - offset, &transferred,
                       NULL) || transferred == 0u)
            return FALSE;
        offset += transferred;
    }
    return TRUE;
}

static BOOL sync_read_exact(HANDLE pipe, uint8_t *buffer, DWORD size)
{
    DWORD offset = 0;

    while (offset < size) {
        DWORD transferred = 0;
        if (!ReadFile(pipe, buffer + offset, size - offset, &transferred,
                      NULL) || transferred == 0u)
            return FALSE;
        offset += transferred;
    }
    return TRUE;
}

static int child_main(int argc, WCHAR **argv)
{
    uint8_t session[16];
    uint8_t hello[56];
    uint8_t ack[56];
    uint8_t payload[PAYLOAD_BYTES];
    uint8_t response[PAYLOAD_BYTES];
    WCHAR pipe_name[64];
    HANDLE pipe = INVALID_HANDLE_VALUE;
    HANDLE ready = NULL;
    HANDLE release = NULL;
    HANDLE done = NULL;
    ULONGLONG deadline = GetTickCount64() + TEST_TIMEOUT_MS;
    DWORD index;
    int result = 2;

    if (argc != 7 || !parse_session(argv[3], session))
        return 2;
    if (_snwprintf(pipe_name, 64, L"\\\\.\\pipe\\Utterleaf.OBS.%ls",
                   argv[3]) < 0)
        return 2;
    ready = OpenEventW(EVENT_MODIFY_STATE, FALSE, argv[4]);
    release = OpenEventW(SYNCHRONIZE, FALSE, argv[5]);
    done = OpenEventW(EVENT_MODIFY_STATE, FALSE, argv[6]);
    if (ready == NULL || release == NULL || done == NULL)
        goto cleanup;
    while (GetTickCount64() < deadline) {
        pipe = CreateFileW(pipe_name, GENERIC_READ | GENERIC_WRITE, 0, NULL,
                           OPEN_EXISTING, 0, NULL);
        if (pipe != INVALID_HANDLE_VALUE)
            break;
        Sleep(10);
    }
    if (pipe == INVALID_HANDLE_VALUE)
        goto cleanup;

    SecureZeroMemory(hello, sizeof(hello));
    memcpy(hello, "ULAH", 4);
    hello[4] = 1;
    hello[5] = 1;
    memcpy(hello + 8, session, 16);
    memset(hello + 24, 's', 32);
    if (!sync_write_all(pipe, hello, 7) ||
        !sync_write_all(pipe, hello + 7, 19) ||
        !sync_write_all(pipe, hello + 26, 30) ||
        !sync_read_exact(pipe, ack, sizeof(ack)))
        goto cleanup;

    if (wcscmp(argv[2], L"end_receipt") == 0) {
        uint8_t terminal[39], receipt[28] = {'U', 'L', 'A', 'C', 1, 3, 0, 0};
        DWORD count = 0;
        uint8_t extra;
        SetEvent(ready);
        if (!sync_read_exact(pipe, terminal, sizeof(terminal)) ||
            memcmp(terminal, "ULAP\1\4\0\0\33\0\0\0", 12) != 0 ||
            memcmp(terminal + 12, session, 16) != 0 ||
            terminal[28] != 1 || terminal[29] != 1 || terminal[30] != 0)
            goto cleanup;
        memcpy(receipt + 8, session, 16);
        if (!sync_write_all(pipe, receipt, 13) ||
            !sync_write_all(pipe, receipt + 13, 15))
            goto cleanup;
        /* Retain the client endpoint until server receipt/peer validation
         * completes. The server disconnect is the only allowed next input. */
        if (ReadFile(pipe, &extra, 1, &count, NULL) ||
            (GetLastError() != ERROR_BROKEN_PIPE &&
             GetLastError() != ERROR_PIPE_NOT_CONNECTED &&
             GetLastError() != ERROR_NO_DATA))
            goto cleanup;
        SetEvent(done);
        result = 0;
        goto cleanup;
    }
    if (wcscmp(argv[2], L"eof") == 0 ||
        wcscmp(argv[2], L"partial_eof") == 0) {
        if (wcscmp(argv[2], L"partial_eof") == 0 &&
            !sync_write_all(pipe, (const uint8_t *)"partial", 7))
            goto cleanup;
        CloseHandle(pipe);
        pipe = INVALID_HANDLE_VALUE;
        SetEvent(ready);
        Sleep(2000);
        result = 0;
        goto cleanup;
    }
    if (wcscmp(argv[2], L"exit") == 0) {
        SetEvent(ready);
        result = 0;
        goto cleanup;
    }
    if (wcscmp(argv[2], L"stall") == 0) {
        SetEvent(ready);
        WaitForSingleObject(release, TEST_TIMEOUT_MS * 2u);
        result = 0;
        goto cleanup;
    }
    if (wcscmp(argv[2], L"partial_stall") == 0) {
        if (!sync_write_all(pipe, (const uint8_t *)"partial", 7))
            goto cleanup;
        SetEvent(ready);
        WaitForSingleObject(release, TEST_TIMEOUT_MS * 2u);
        result = 0;
        goto cleanup;
    }
    if (wcscmp(argv[2], L"roundtrip") != 0)
        goto cleanup;
    for (index = 0; index < PAYLOAD_BYTES; ++index)
        payload[index] = (uint8_t)(index * 29u + 7u);
    if (!sync_write_all(pipe, payload, 3))
        goto cleanup;
    SetEvent(ready);
    if (WaitForSingleObject(release, TEST_TIMEOUT_MS) != WAIT_OBJECT_0 ||
        !sync_write_all(pipe, payload + 3, 97) ||
        !sync_write_all(pipe, payload + 100, PAYLOAD_BYTES - 100) ||
        !sync_read_exact(pipe, response, sizeof(response)) ||
        memcmp(response, payload, sizeof(payload)) != 0)
        goto cleanup;
    SetEvent(done);
    Sleep(TEST_TIMEOUT_MS);
    result = 0;

cleanup:
    SecureZeroMemory(hello, sizeof(hello));
    SecureZeroMemory(ack, sizeof(ack));
    SecureZeroMemory(payload, sizeof(payload));
    SecureZeroMemory(response, sizeof(response));
    if (pipe != INVALID_HANDLE_VALUE)
        CloseHandle(pipe);
    if (ready != NULL)
        CloseHandle(ready);
    if (release != NULL)
        CloseHandle(release);
    if (done != NULL)
        CloseHandle(done);
    return result;
}

static BOOL start_peer(test_peer *peer, const WCHAR *mode,
                       const uint8_t session[16], unsigned counter)
{
    WCHAR executable[MAX_PATH];
    WCHAR hex[33];
    WCHAR ready_name[96];
    WCHAR release_name[96];
    WCHAR done_name[96];
    WCHAR command[1024];
    STARTUPINFOW startup;

    SecureZeroMemory(peer, sizeof(*peer));
    SecureZeroMemory(&startup, sizeof(startup));
    startup.cb = sizeof(startup);
    if (GetModuleFileNameW(NULL, executable, MAX_PATH) == 0u)
        return FALSE;
    session_hex(session, hex);
    _snwprintf(ready_name, 96, L"Local\\ULAdmissionIo.%lu.%u.ready",
               (unsigned long)GetCurrentProcessId(), counter);
    _snwprintf(release_name, 96, L"Local\\ULAdmissionIo.%lu.%u.release",
               (unsigned long)GetCurrentProcessId(), counter);
    _snwprintf(done_name, 96, L"Local\\ULAdmissionIo.%lu.%u.done",
               (unsigned long)GetCurrentProcessId(), counter);
    peer->ready = CreateEventW(NULL, TRUE, FALSE, ready_name);
    peer->release = CreateEventW(NULL, TRUE, FALSE, release_name);
    peer->done = CreateEventW(NULL, TRUE, FALSE, done_name);
    if (peer->ready == NULL || peer->release == NULL || peer->done == NULL)
        return FALSE;
    if (_snwprintf(command, 1024, L"\"%ls\" --child %ls %ls %ls %ls %ls",
                   executable, mode, hex, ready_name, release_name,
                   done_name) < 0)
        return FALSE;
    return CreateProcessW(executable, command, NULL, NULL, FALSE,
                          CREATE_NO_WINDOW, NULL, NULL, &startup,
                          &peer->process);
}

static void stop_peer(test_peer *peer)
{
    if (peer->admission != NULL) {
        ul_admission_cancel(peer->admission);
        ul_admission_destroy(peer->admission);
    }
    if (peer->process.hProcess != NULL) {
        SetEvent(peer->release);
        if (WaitForSingleObject(peer->process.hProcess, 500) == WAIT_TIMEOUT) {
            TerminateProcess(peer->process.hProcess, 99);
            WaitForSingleObject(peer->process.hProcess, TEST_TIMEOUT_MS);
        }
        CloseHandle(peer->process.hProcess);
    }
    if (peer->process.hThread != NULL)
        CloseHandle(peer->process.hThread);
    if (peer->ready != NULL)
        CloseHandle(peer->ready);
    if (peer->release != NULL)
        CloseHandle(peer->release);
    if (peer->done != NULL)
        CloseHandle(peer->done);
    SecureZeroMemory(peer, sizeof(*peer));
}

static BOOL authenticated_peer(test_peer *peer, const WCHAR *mode,
                               uint8_t session[16], unsigned counter)
{
    make_session(session, counter);
    if (!start_peer(peer, mode, session, counter))
        return FALSE;
    peer->admission = ul_admission_create(peer->process.dwProcessId, session);
    return peer->admission != NULL &&
           ul_admission_authenticate(peer->admission, TEST_TIMEOUT_MS) ==
               UL_ADMISSION_AUTH_OK;
}

static DWORD WINAPI blocked_read(LPVOID parameter)
{
    read_call *call = (read_call *)parameter;

    memset(call->buffer, 0xa5, sizeof(call->buffer));
    call->result = ul_admission_read_exact(
        call->admission, call->buffer, sizeof(call->buffer), TEST_TIMEOUT_MS);
    return 0;
}

static DWORD WINAPI blocked_write(LPVOID parameter)
{
    write_call *call = (write_call *)parameter;

    memset(call->buffer, 0x5a, sizeof(call->buffer));
    call->result = ul_admission_write_all(
        call->admission, call->buffer, sizeof(call->buffer), TEST_TIMEOUT_MS);
    return 0;
}

static int test_roundtrip_and_probe(void)
{
    test_peer peer;
    uint8_t session[16];
    uint8_t payload[PAYLOAD_BYTES];
    DWORD available = 0;
    DWORD index;
    int failures = 0;

    failures += check(authenticated_peer(&peer, L"roundtrip", session, 1),
                      "authenticate roundtrip child");
    if (failures != 0) {
        stop_peer(&peer);
        return failures;
    }
    failures += check(WaitForSingleObject(peer.ready, TEST_TIMEOUT_MS) ==
                          WAIT_OBJECT_0,
                      "roundtrip child ready");
    failures += check(ul_admission_probe(peer.admission, &available) == 0 &&
                          available == 3u,
                      "probe reports queued fragment");
    available = 0;
    failures += check(ul_admission_probe(peer.admission, &available) == 0 &&
                          available == 3u,
                      "probe does not consume bytes");
    SetEvent(peer.release);
    failures += check(ul_admission_read_exact(peer.admission, payload,
                                              sizeof(payload),
                                              TEST_TIMEOUT_MS) == 0,
                      "fragmented exact read");
    for (index = 0; index < PAYLOAD_BYTES; ++index) {
        if (payload[index] != (uint8_t)(index * 29u + 7u)) {
            failures += check(FALSE, "exact read payload");
            break;
        }
    }
    failures += check(ul_admission_write_all(peer.admission, payload,
                                             sizeof(payload),
                                             TEST_TIMEOUT_MS) == 0,
                      "bounded full write");
    failures += check(WaitForSingleObject(peer.done, TEST_TIMEOUT_MS) ==
                          WAIT_OBJECT_0,
                      "child validates full write");
    SecureZeroMemory(payload, sizeof(payload));
    stop_peer(&peer);
    return failures;
}

static int test_pre_auth_is_terminal_and_wipes(void)
{
    test_peer peer;
    uint8_t session[16];
    uint8_t buffer[16];
    unsigned index;
    int failures = 0;

    make_session(session, 2);
    failures += check(start_peer(&peer, L"stall", session, 2),
                      "start preauth child");
    if (failures != 0) {
        stop_peer(&peer);
        return failures;
    }
    peer.admission = ul_admission_create(peer.process.dwProcessId, session);
    failures += check(peer.admission != NULL, "create preauth admission");
    memset(buffer, 0xa5, sizeof(buffer));
    failures += check(ul_admission_read_exact(peer.admission, buffer,
                                              sizeof(buffer), 500) ==
                          UL_ADMISSION_REJECTED,
                      "reject preauth read");
    for (index = 0; index < sizeof(buffer); ++index)
        failures += check(buffer[index] == 0, "wipe preauth read buffer");
    failures += check(ul_admission_authenticate(peer.admission, 100) ==
                          UL_ADMISSION_CANCELLED,
                      "preauth misuse terminally cancels");
    stop_peer(&peer);
    return failures;
}

static int test_timeout_and_cancel_wipe(void)
{
    test_peer peer;
    uint8_t session[16];
    uint8_t buffer[64];
    read_call call;
    HANDLE thread;
    DWORD available = 99;
    unsigned index;
    int failures = 0;

    failures += check(authenticated_peer(&peer, L"stall", session, 3),
                      "authenticate timeout child");
    failures += check(WaitForSingleObject(peer.ready, TEST_TIMEOUT_MS) ==
                          WAIT_OBJECT_0,
                      "timeout child ready");
    failures += check(ul_admission_probe(peer.admission, &available) == 0 &&
                          available == 0u,
                      "zero-byte probe is live");
    memset(buffer, 0xa5, sizeof(buffer));
    failures += check(ul_admission_read_exact(peer.admission, buffer,
                                              sizeof(buffer), 100) ==
                          UL_ADMISSION_TIMEOUT,
                      "exact read timeout");
    for (index = 0; index < sizeof(buffer); ++index)
        failures += check(buffer[index] == 0, "wipe timed-out read buffer");
    stop_peer(&peer);

    failures += check(authenticated_peer(&peer, L"stall", session, 4),
                      "authenticate cancellation child");
    failures += check(WaitForSingleObject(peer.ready, TEST_TIMEOUT_MS) ==
                          WAIT_OBJECT_0,
                      "cancellation child ready");
    SecureZeroMemory(&call, sizeof(call));
    call.admission = peer.admission;
    thread = CreateThread(NULL, 0, blocked_read, &call, 0, NULL);
    failures += check(thread != NULL, "start blocked exact read");
    if (thread != NULL) {
        Sleep(100);
        ul_admission_cancel(peer.admission);
        failures += check(WaitForSingleObject(thread, TEST_TIMEOUT_MS) ==
                              WAIT_OBJECT_0,
                          "cancel drains exact read");
        failures += check(call.result == UL_ADMISSION_CANCELLED,
                          "cancel result");
        for (index = 0; index < sizeof(call.buffer); ++index)
            failures += check(call.buffer[index] == 0,
                              "wipe cancelled read buffer");
        CloseHandle(thread);
    }
    stop_peer(&peer);
    return failures;
}

static BOOL all_zero(const uint8_t *buffer, DWORD size)
{
    DWORD index;

    for (index = 0; index < size; ++index) {
        if (buffer[index] != 0u)
            return FALSE;
    }
    return TRUE;
}

static int test_invalid_arguments(void)
{
    unsigned kind;
    int failures = 0;

    for (kind = 0; kind < 5u; ++kind) {
        test_peer peer;
        uint8_t session[16];
        uint8_t small[16];
        uint8_t *large = NULL;
        int result;

        failures += check(authenticated_peer(&peer, L"stall", session,
                                              10u + kind),
                          "authenticate invalid-argument child");
        failures += check(WaitForSingleObject(peer.ready, TEST_TIMEOUT_MS) ==
                              WAIT_OBJECT_0,
                          "invalid-argument child ready");
        memset(small, 0xa5, sizeof(small));
        if (kind == 0u)
            result = ul_admission_read_exact(peer.admission, small, 0, 500);
        else if (kind == 1u) {
            large = (uint8_t *)HeapAlloc(GetProcessHeap(), 0,
                                         UL_ADMISSION_MAX_IO_BYTES + 1u);
            failures += check(large != NULL, "allocate oversized fixture buffer");
            result = large == NULL
                         ? UL_ADMISSION_IO_ERROR
                         : ul_admission_read_exact(
                               peer.admission, large,
                               UL_ADMISSION_MAX_IO_BYTES + 1u, 500);
        } else if (kind == 2u)
            result = ul_admission_read_exact(peer.admission, small,
                                             sizeof(small), 0);
        else if (kind == 3u)
            result = ul_admission_read_exact(peer.admission, small,
                                             sizeof(small), 30001);
        else
            result = ul_admission_read_exact(peer.admission, NULL,
                                             sizeof(small), 500);
        failures += check(result == UL_ADMISSION_IO_ERROR,
                          "invalid argument returns I/O error");
        failures += check(ul_admission_pipe(peer.admission) == NULL,
                          "invalid argument is terminal");
        if (kind == 2u || kind == 3u)
            failures += check(all_zero(small, sizeof(small)),
                              "invalid timeout wipes read buffer");
        if (large != NULL) {
            SecureZeroMemory(large, UL_ADMISSION_MAX_IO_BYTES + 1u);
            HeapFree(GetProcessHeap(), 0, large);
        }
        stop_peer(&peer);
    }
    return failures;
}

static int test_partial_failure_wipes(void)
{
    const WCHAR *modes[2] = {L"partial_eof", L"partial_stall"};
    unsigned mode_index;
    int failures = 0;

    for (mode_index = 0; mode_index < 2u; ++mode_index) {
        test_peer peer;
        uint8_t session[16];
        uint8_t buffer[64];
        int result;

        failures += check(authenticated_peer(&peer, modes[mode_index], session,
                                              20u + mode_index),
                          "authenticate partial-read child");
        failures += check(WaitForSingleObject(peer.ready, TEST_TIMEOUT_MS) ==
                              WAIT_OBJECT_0,
                          "partial-read child ready");
        memset(buffer, 0xa5, sizeof(buffer));
        result = ul_admission_read_exact(peer.admission, buffer,
                                         sizeof(buffer), 150);
        failures += check(
            result == (mode_index == 0u ? UL_ADMISSION_IO_ERROR
                                        : UL_ADMISSION_TIMEOUT),
            "partial read returns terminal cause");
        failures += check(all_zero(buffer, sizeof(buffer)),
                          "partial copied bytes are wiped");
        stop_peer(&peer);
    }
    return failures;
}

static int test_cancel_before_call_and_blocked_write(void)
{
    test_peer peer;
    uint8_t session[16];
    uint8_t buffer[16];
    write_call *call;
    HANDLE thread;
    int failures = 0;

    failures += check(authenticated_peer(&peer, L"stall", session, 30),
                      "authenticate pre-cancel child");
    failures += check(WaitForSingleObject(peer.ready, TEST_TIMEOUT_MS) ==
                          WAIT_OBJECT_0,
                      "pre-cancel child ready");
    ul_admission_cancel(peer.admission);
    memset(buffer, 0xa5, sizeof(buffer));
    failures += check(ul_admission_read_exact(peer.admission, buffer,
                                              sizeof(buffer), 500) ==
                          UL_ADMISSION_CANCELLED,
                      "cancel before call preserves cancelled result");
    failures += check(all_zero(buffer, sizeof(buffer)),
                      "pre-cancelled read buffer wiped");
    stop_peer(&peer);

    failures += check(authenticated_peer(&peer, L"stall", session, 31),
                      "authenticate blocked-write child");
    failures += check(WaitForSingleObject(peer.ready, TEST_TIMEOUT_MS) ==
                          WAIT_OBJECT_0,
                      "blocked-write child ready");
    call = (write_call *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY,
                                   sizeof(*call));
    failures += check(call != NULL, "allocate blocked-write call");
    if (call != NULL) {
        call->admission = peer.admission;
        thread = CreateThread(NULL, 0, blocked_write, call, 0, NULL);
        failures += check(thread != NULL, "start maximum blocked write");
        if (thread != NULL) {
            Sleep(100);
            ul_admission_cancel(peer.admission);
            failures += check(WaitForSingleObject(thread, TEST_TIMEOUT_MS) ==
                                  WAIT_OBJECT_0,
                              "cancel drains maximum blocked write");
            failures += check(call->result == UL_ADMISSION_CANCELLED,
                              "blocked write reports cancellation");
            CloseHandle(thread);
        }
        SecureZeroMemory(call, sizeof(*call));
        HeapFree(GetProcessHeap(), 0, call);
    }
    stop_peer(&peer);
    return failures;
}

static int test_eof_and_dead_peer(void)
{
    test_peer peer;
    uint8_t session[16];
    uint8_t buffer[16];
    DWORD available = 99;
    unsigned index;
    int failures = 0;

    failures += check(authenticated_peer(&peer, L"eof", session, 5),
                      "authenticate EOF child");
    failures += check(WaitForSingleObject(peer.ready, TEST_TIMEOUT_MS) ==
                          WAIT_OBJECT_0,
                      "EOF child closed pipe");
    memset(buffer, 0xa5, sizeof(buffer));
    failures += check(ul_admission_read_exact(peer.admission, buffer,
                                              sizeof(buffer), 500) != 0,
                      "EOF is terminal");
    for (index = 0; index < sizeof(buffer); ++index)
        failures += check(buffer[index] == 0, "wipe EOF read buffer");
    stop_peer(&peer);

    failures += check(authenticated_peer(&peer, L"exit", session, 6),
                      "authenticate exiting child");
    failures += check(WaitForSingleObject(peer.ready, TEST_TIMEOUT_MS) ==
                          WAIT_OBJECT_0,
                      "exiting child ready");
    failures += check(WaitForSingleObject(peer.process.hProcess,
                                          TEST_TIMEOUT_MS) == WAIT_OBJECT_0,
                      "expected peer exits");
    failures += check(ul_admission_probe(peer.admission, &available) ==
                          UL_ADMISSION_REJECTED && available == 0u,
                      "probe rejects dead retained peer");
    failures += check(ul_admission_pipe(peer.admission) == NULL,
                      "probe failure closes admission gate");
    stop_peer(&peer);
    return failures;
}

static int test_terminal_receipt_and_server_disconnect(void)
{
    test_peer peer;
    uint8_t session[16], receipt[28];
    uint8_t terminal[39] = {'U', 'L', 'A', 'P', 1, 4, 0, 0, 27, 0, 0, 0};
    int failures = 0;
    failures += check(authenticated_peer(&peer, L"end_receipt", session, 40),
                      "authenticate terminal receipt client");
    if (failures) { stop_peer(&peer); return failures; }
    memcpy(terminal + 12, session, 16);
    terminal[28] = terminal[29] = 1; /* Stream stopped; bus zero sequence zero. */
    failures += check(WaitForSingleObject(peer.ready, TEST_TIMEOUT_MS) == WAIT_OBJECT_0,
                      "terminal receipt client ready");
    failures += check(ul_admission_write_all(peer.admission, terminal, sizeof(terminal), 1000) ==
                          UL_ADMISSION_AUTH_OK, "write terminal packet");
    failures += check(ul_admission_read_exact(peer.admission, receipt, sizeof(receipt), 1000) ==
                          UL_ADMISSION_AUTH_OK && ul_session_end_ack(receipt, sizeof(receipt), session),
                      "read fragmented terminal receipt with final peer validation");
    ul_admission_cancel(peer.admission);
    ul_admission_destroy(peer.admission);
    peer.admission = NULL;
    failures += check(WaitForSingleObject(peer.done, TEST_TIMEOUT_MS) == WAIT_OBJECT_0,
                      "client observes server disconnect without flush");
    stop_peer(&peer);
    return failures;
}

int wmain(int argc, WCHAR **argv)
{
    int failures;

    if (argc > 1 && wcscmp(argv[1], L"--child") == 0)
        return child_main(argc, argv);
    failures = test_roundtrip_and_probe();
    failures += test_pre_auth_is_terminal_and_wipes();
    failures += test_timeout_and_cancel_wipe();
    failures += test_invalid_arguments();
    failures += test_partial_failure_wipes();
    failures += test_cancel_before_call_and_blocked_write();
    failures += test_eof_and_dead_peer();
    failures += test_terminal_receipt_and_server_disconnect();
    puts(failures == 0 ? "admission I/O tests passed"
                       : "admission I/O tests failed");
    return failures == 0 ? 0 : 1;
}
