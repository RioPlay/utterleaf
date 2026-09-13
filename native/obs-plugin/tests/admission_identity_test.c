// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0600
#endif

/* Inspect original admission internals without adding production test hooks. */
#include "../src/admission.c"

#include <aclapi.h>

#include <stdio.h>
#include <string.h>
#include <wchar.h>

#define TEST_PATH_CHARS 900u
#define TEST_COMMAND_CHARS 940u
#define TEST_REPETITIONS 64u

static int check(BOOL condition, const char *message)
{
    if (condition)
        return 0;
    fprintf(stderr, "FAIL: %s\n", message);
    return 1;
}

static BOOL start_child(PROCESS_INFORMATION *process)
{
    static const WCHAR suffix[] = L"\" --identity-child";
    STARTUPINFOW startup;
    WCHAR path[TEST_PATH_CHARS];
    WCHAR command[TEST_COMMAND_CHARS];
    DWORD path_size;
    size_t path_length;
    size_t suffix_length = (sizeof(suffix) / sizeof(suffix[0])) - 1u;

    SecureZeroMemory(&startup, sizeof(startup));
    SecureZeroMemory(process, sizeof(*process));
    startup.cb = sizeof(startup);
    path_size = GetModuleFileNameW(NULL, path, TEST_PATH_CHARS);
    if (path_size == 0u || path_size >= TEST_PATH_CHARS)
        return FALSE;
    path_length = wcslen(path);
    if (1u + path_length + suffix_length + 1u > TEST_COMMAND_CHARS)
        return FALSE;
    command[0] = L'\"';
    memcpy(command + 1u, path, path_length * sizeof(WCHAR));
    memcpy(command + 1u + path_length, suffix,
           (suffix_length + 1u) * sizeof(WCHAR));
    return CreateProcessW(NULL, command, NULL, NULL, FALSE, CREATE_NO_WINDOW,
                          NULL, NULL, &startup, process);
}

static BOOL handle_is_not_inherited(HANDLE handle)
{
    DWORD flags = 0;

    return handle != NULL && handle != INVALID_HANDLE_VALUE &&
           GetHandleInformation(handle, &flags) &&
           (flags & HANDLE_FLAG_INHERIT) == 0u;
}

static int check_identity_dimensions(HANDLE child)
{
    ul_identity current;
    ul_identity peer;
    uint8_t *bytes;
    int failures = 0;

    SecureZeroMemory(&current, sizeof(current));
    SecureZeroMemory(&peer, sizeof(peer));
    failures += check(snapshot_identity(GetCurrentProcess(), &current),
                      "snapshot current process identity");
    failures += check(snapshot_identity(child, &peer),
                      "snapshot child process identity");
    if (failures != 0)
        goto cleanup;
    failures += check(identities_equal(&current, &peer),
                      "actual same-logon child identity matches server");

    failures += check(peer.user_sid_size > 8u,
                      "user SID has a mutable subauthority");
    if (peer.user_sid_size > 8u) {
        bytes = (uint8_t *)peer.user_sid;
        bytes[peer.user_sid_size - 1u] ^= 1u;
        failures += check(!identities_equal(&current, &peer),
                          "user SID mismatch is rejected");
        bytes[peer.user_sid_size - 1u] ^= 1u;
    }

    failures += check(peer.logon_sid_size > 8u,
                      "logon SID has a mutable subauthority");
    if (peer.logon_sid_size > 8u) {
        bytes = (uint8_t *)peer.logon_sid;
        bytes[peer.logon_sid_size - 1u] ^= 1u;
        failures += check(!identities_equal(&current, &peer),
                          "logon SID mismatch is rejected");
        bytes[peer.logon_sid_size - 1u] ^= 1u;
    }

    peer.session_id ^= 1u;
    failures += check(!identities_equal(&current, &peer),
                      "token session mismatch is rejected");
    peer.session_id ^= 1u;

    peer.authentication_id.LowPart ^= 1u;
    failures += check(!identities_equal(&current, &peer),
                      "authentication ID mismatch is rejected");
    peer.authentication_id.LowPart ^= 1u;
    failures += check(identities_equal(&current, &peer),
                      "identity matches after restoring mutations");

cleanup:
    identity_clear(&peer);
    identity_clear(&current);
    return failures;
}

static int check_pipe_security(const ul_admission *admission)
{
    PSECURITY_DESCRIPTOR descriptor = NULL;
    PACL dacl = NULL;
    ACL_SIZE_INFORMATION acl_info;
    void *raw_ace = NULL;
    ACCESS_ALLOWED_ACE *ace;
    PSID ace_sid;
    DWORD error;
    int failures = 0;

    SecureZeroMemory(&acl_info, sizeof(acl_info));
    error = GetSecurityInfo(admission->pipe, SE_KERNEL_OBJECT,
                            DACL_SECURITY_INFORMATION, NULL, NULL, &dacl,
                            NULL, &descriptor);
    failures += check(error == ERROR_SUCCESS && descriptor != NULL &&
                          dacl != NULL,
                      "read pending pipe DACL");
    if (error != ERROR_SUCCESS || descriptor == NULL || dacl == NULL)
        goto cleanup;
    failures += check(GetAclInformation(dacl, &acl_info, sizeof(acl_info),
                                        AclSizeInformation),
                      "read pending pipe ACL metadata");
    failures += check(acl_info.AceCount == 1u,
                      "pending pipe DACL has exactly one ACE");
    if (acl_info.AceCount != 1u)
        goto cleanup;
    failures += check(GetAce(dacl, 0, &raw_ace) && raw_ace != NULL,
                      "read pending pipe ACE");
    if (raw_ace == NULL)
        goto cleanup;
    ace = (ACCESS_ALLOWED_ACE *)raw_ace;
    ace_sid = (PSID)&ace->SidStart;
    failures += check(ace->Header.AceType == ACCESS_ALLOWED_ACE_TYPE,
                      "pending pipe ACE is access-allowed");
    failures += check(ace->Header.AceFlags == 0u,
                      "pending pipe ACE is not inherited");
    failures += check((ace->Mask & (FILE_GENERIC_READ | FILE_GENERIC_WRITE)) ==
                          (FILE_GENERIC_READ | FILE_GENERIC_WRITE),
                      "pending pipe ACE has mapped client read/write rights");
    failures += check(IsValidSid(ace_sid) &&
                          EqualSid(ace_sid,
                                   admission->server_identity.logon_sid),
                      "pending pipe ACE is the current logon SID");

cleanup:
    if (descriptor != NULL)
        LocalFree(descriptor);
    return failures;
}

static void make_session(uint8_t session[16], DWORD sequence)
{
    size_t index;

    for (index = 0; index < 16u; ++index)
        session[index] = (uint8_t)(sequence + (DWORD)index * 17u);
}

static int check_handle_balance(DWORD child_pid)
{
    DWORD before = 0;
    DWORD after = 0;
    DWORD iteration;
    uint8_t session[16];
    int failures = 0;

    failures += check(GetProcessHandleCount(GetCurrentProcess(), &before),
                      "read initial process handle count");
    if (failures != 0)
        return failures;
    for (iteration = 0; iteration < TEST_REPETITIONS; ++iteration) {
        ul_admission *admission;

        make_session(session, iteration + 1u);
        admission = ul_admission_create(child_pid, session);
        if (admission == NULL) {
            failures += check(FALSE, "create admission during handle loop");
            break;
        }
        ul_admission_destroy(admission);
    }
    failures += check(GetProcessHandleCount(GetCurrentProcess(), &after),
                      "read final process handle count");
    failures += check(before == after,
                      "repeated admission create/destroy balances handles");
    SecureZeroMemory(session, sizeof(session));
    return failures;
}

int main(int argc, char **argv)
{
    PROCESS_INFORMATION child;
    ul_admission *admission = NULL;
    uint8_t session[16];
    DWORD dead_pid = 0;
    int failures = 0;

    if (argc == 2 && strcmp(argv[1], "--identity-child") == 0) {
        Sleep(30000u);
        return 0;
    }
    if (argc != 1)
        return 2;

    make_session(session, 0u);
    failures += check(ul_admission_create(0u, session) == NULL,
                      "PID zero is reserved");
    failures += check(ul_admission_create(4u, session) == NULL,
                      "PID four is reserved");
    failures += check(ul_admission_create(GetCurrentProcessId(), session) ==
                          NULL,
                      "server process PID is reserved");
    failures += check(start_child(&child), "start disposable identity child");
    if (failures != 0)
        goto cleanup;
    dead_pid = child.dwProcessId;

    failures += check_identity_dimensions(child.hProcess);
    admission = ul_admission_create(child.dwProcessId, session);
    failures += check(admission != NULL,
                      "create pending admission for actual child process");
    if (admission != NULL) {
        ULONGLONG creation_time = 0;

        failures += check(process_is_alive(admission->expected_process),
                          "retained expected process is live");
        failures += check(process_creation_time(admission->expected_process,
                                                &creation_time) &&
                              creation_time ==
                                  admission->expected_creation_time,
                          "retained expected creation time is stable");
        failures += check(identities_equal(&admission->expected_identity,
                                           &admission->server_identity),
                          "retained expected identity matches server identity");
        failures += check(handle_is_not_inherited(admission->pipe),
                          "pipe handle is not inherited");
        failures += check(handle_is_not_inherited(admission->cancel_event),
                          "cancel-event handle is not inherited");
        failures += check(handle_is_not_inherited(admission->expected_process),
                          "expected-process handle is not inherited");
        failures += check_pipe_security(admission);
        ul_admission_destroy(admission);
        admission = NULL;
    }
    failures += check_handle_balance(child.dwProcessId);

cleanup:
    if (admission != NULL)
        ul_admission_destroy(admission);
    SecureZeroMemory(session, sizeof(session));
    if (child.hProcess != NULL) {
        TerminateProcess(child.hProcess, 0);
        WaitForSingleObject(child.hProcess, 10000u);
    }
    if (child.hThread != NULL)
        CloseHandle(child.hThread);
    if (child.hProcess != NULL)
        CloseHandle(child.hProcess);
    if (dead_pid != 0u) {
        uint8_t dead_session[16];

        make_session(dead_session, 255u);
        admission = ul_admission_create(dead_pid, dead_session);
        failures += check(admission == NULL, "dead process PID is rejected");
        if (admission != NULL)
            ul_admission_destroy(admission);
        SecureZeroMemory(dead_session, sizeof(dead_session));
    }
    if (failures == 0) {
        puts("admission identity/security tests passed");
        puts("identity mutations are unit-only; cross-user/logon is unverified");
    }
    return failures == 0 ? 0 : 1;
}
