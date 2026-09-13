// SPDX-License-Identifier: GPL-2.0-or-later
#include <assert.h>
#include <stdio.h>
#include <windows.h>

#include "../src/frontend_dispatch.h"

static DWORD owner;
static unsigned seen_command;
static uintptr_t seen_generation;
static unsigned callbacks;
static int close_in_callback;
static volatile LONG callback_complete;

static void callback(unsigned command, uintptr_t generation)
{
    assert(GetCurrentThreadId() == owner);
    seen_command = command;
    seen_generation = generation;
    ++callbacks;
    InterlockedExchange(&callback_complete, 1);
    if (close_in_callback)
        ul_frontend_dispatch_close();
}

static DWORD WINAPI worker(void *unused)
{
    (void)unused;
    assert(ul_frontend_dispatch_post(4u, (uintptr_t)42u));
    assert(!ul_frontend_dispatch_post(0u, 42u));
    assert(!ul_frontend_dispatch_post(5u, 42u));
    assert(!ul_frontend_dispatch_post(1u, 0u));
    while (InterlockedCompareExchange(&callback_complete, 0, 0) == 0)
        Sleep(1u);
    ul_frontend_dispatch_close();
    return 0;
}

int main(void)
{
    MSG message;
    HANDLE thread;
    assert(ul_frontend_dispatch_open(callback));
    owner = GetCurrentThreadId();
    assert(!ul_frontend_dispatch_open(callback));
    close_in_callback = 1;
    thread = CreateThread(NULL, 0, worker, NULL, 0, NULL);
    assert(thread != NULL);
    while (callbacks == 0u && GetMessageW(&message, NULL, 0, 0) > 0) {
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }
    assert(WaitForSingleObject(thread, 2000u) == WAIT_OBJECT_0);
    CloseHandle(thread);
    assert(callbacks == 1u && seen_command == 4u && seen_generation == 42u);
    assert(!ul_frontend_dispatch_post(1u, (uintptr_t)43u));
    close_in_callback = 1;
    /* The worker's cross-thread close made the dispatcher inert; owner cleanup
     * remains the only valid destruction path. */
    ul_frontend_dispatch_close();
    assert(!ul_frontend_dispatch_post(2u, 45u));
    ul_frontend_dispatch_close();
    puts("frontend message dispatcher thread, bounds and close tests passed");
    return 0;
}
