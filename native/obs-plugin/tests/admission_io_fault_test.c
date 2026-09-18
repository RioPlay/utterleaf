// SPDX-License-Identifier: GPL-2.0-or-later
#include <windows.h>

#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int fault_mode;
static LONG peer_checks;
static LONG cancel_on_peer_check;
static LONG delay_on_peer_check;
static volatile LONG *fault_cancelled;
static HANDLE fault_cancel_event;

static HANDLE fault_event_create(void)
{
    if (fault_mode == 1)
        return NULL;
    return CreateEventW(NULL, TRUE, FALSE, NULL);
}

static BOOL fault_peer_expected(const void *admission)
{
    LONG current;

    (void)admission;
    current = InterlockedIncrement(&peer_checks);
    if (current == InterlockedCompareExchange(&cancel_on_peer_check, 0, 0)) {
        InterlockedExchange(fault_cancelled, 1);
        SetEvent(fault_cancel_event);
    }
    if (current == InterlockedCompareExchange(&delay_on_peer_check, 0, 0))
        Sleep(30);
    return TRUE;
}

static void fault_read(void *buffer, DWORD size, DWORD *transferred)
{
    if (fault_mode == 2) {
        *transferred = 0;
    } else if (fault_mode == 3) {
        *transferred = size + 1u;
    } else {
        memset(buffer, 0x3c, 1);
        *transferred = 1;
    }
}

static BOOL fault_peek(HANDLE pipe, DWORD *available)
{
    (void)pipe;
    *available = 0;
    return fault_mode != 5;
}

#define UL_ADMISSION_IO_EVENT_CREATE() fault_event_create()
#define UL_ADMISSION_PEER_EXPECTED(admission) fault_peer_expected(admission)
#define UL_ADMISSION_READ_PIPE(admission, overlapped, buffer, size, started,  \
                               timeout_ms, transferred)                     \
    (fault_read(buffer, size, transferred), UL_OPERATION_OK)
#define UL_ADMISSION_PEEK_PIPE(pipe, available) fault_peek(pipe, available)
#include "../src/admission.c"

static int check(BOOL condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", message);
        return 1;
    }
    return 0;
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

static void initialize_admission(ul_admission *admission)
{
    SecureZeroMemory(admission, sizeof(*admission));
    admission->pipe = (HANDLE)(uintptr_t)1;
    admission->cancel_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    admission->authenticated = 1;
    fault_cancelled = &admission->cancelled;
    fault_cancel_event = admission->cancel_event;
}

static void finish_admission(ul_admission *admission)
{
    if (admission->cancel_event != NULL)
        CloseHandle(admission->cancel_event);
    fault_cancelled = NULL;
    fault_cancel_event = NULL;
    SecureZeroMemory(admission, sizeof(*admission));
}

static int failure_case(int mode, const char *message)
{
    ul_admission admission;
    uint8_t buffer[8];
    int failures = 0;

    fault_mode = mode;
    InterlockedExchange(&peer_checks, 0);
    InterlockedExchange(&cancel_on_peer_check, 0);
    InterlockedExchange(&delay_on_peer_check, 0);
    initialize_admission(&admission);
    failures += check(admission.cancel_event != NULL, "create cancel event");
    memset(buffer, 0xa5, sizeof(buffer));
    failures += check(ul_admission_read_exact(&admission, buffer,
                                              sizeof(buffer), 500) ==
                          UL_ADMISSION_IO_ERROR,
                      message);
    failures += check(all_zero(buffer, sizeof(buffer)),
                      "failed exact read wipes output");
    failures += check(admission.cancelled != 0,
                      "failed exact read terminally cancels");
    finish_admission(&admission);
    return failures;
}

int main(void)
{
    ul_admission admission;
    uint8_t buffer[4];
    DWORD available = 99;
    int failures = 0;

    failures += failure_case(1, "event creation failure cannot report success");
    failures += failure_case(2, "zero-byte completion cannot report success");
    failures += failure_case(3, "over-count completion cannot report success");

    fault_mode = 4;
    InterlockedExchange(&peer_checks, 0);
    initialize_admission(&admission);
    failures += check(ul_admission_read_exact(&admission, buffer,
                                              sizeof(buffer), 500) ==
                          UL_ADMISSION_AUTH_OK,
                      "fragmented injected read completes exactly");
    failures += check(InterlockedCompareExchange(&peer_checks, 0, 0) == 10,
                      "retained peer checked before and after every transfer");
    finish_admission(&admission);

    fault_mode = 4;
    InterlockedExchange(&peer_checks, 0);
    InterlockedExchange(&cancel_on_peer_check, 10);
    initialize_admission(&admission);
    memset(buffer, 0xa5, sizeof(buffer));
    failures += check(ul_admission_read_exact(&admission, buffer,
                                              sizeof(buffer), 500) ==
                          UL_ADMISSION_CANCELLED,
                      "cancellation during final peer check wins over success");
    failures += check(all_zero(buffer, sizeof(buffer)),
                      "final peer cancellation wipes copied bytes");
    finish_admission(&admission);

    InterlockedExchange(&peer_checks, 0);
    InterlockedExchange(&cancel_on_peer_check, 0);
    InterlockedExchange(&delay_on_peer_check, 10);
    initialize_admission(&admission);
    memset(buffer, 0xa5, sizeof(buffer));
    failures += check(ul_admission_read_exact(&admission, buffer,
                                              sizeof(buffer), 10) ==
                          UL_ADMISSION_TIMEOUT,
                      "deadline after final peer check wins over success");
    failures += check(all_zero(buffer, sizeof(buffer)),
                      "final peer timeout wipes copied bytes");
    finish_admission(&admission);

    fault_mode = 5;
    InterlockedExchange(&peer_checks, 0);
    InterlockedExchange(&delay_on_peer_check, 0);
    initialize_admission(&admission);
    failures += check(ul_admission_probe(&admission, &available) ==
                          UL_ADMISSION_IO_ERROR,
                      "PeekNamedPipe failure cannot report success");
    failures += check(available == 0u && admission.cancelled != 0,
                      "failed probe clears output and terminally cancels");
    finish_admission(&admission);

    puts(failures == 0 ? "admission I/O fault tests passed"
                       : "admission I/O fault tests failed");
    return failures == 0 ? 0 : 1;
}
