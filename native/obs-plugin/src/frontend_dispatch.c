// SPDX-License-Identifier: GPL-2.0-or-later
#include "frontend_dispatch.h"

#include <windows.h>

#define UL_FRONTEND_WM_COMMAND (WM_APP + 0x51)
#define UL_FRONTEND_COMMAND_MIN 1u
#define UL_FRONTEND_COMMAND_MAX 3u

static SRWLOCK state_lock = SRWLOCK_INIT;
static HWND dispatch_window;
static DWORD owner_thread;
static ul_frontend_dispatch_callback dispatch_callback;
static bool opened;
static bool closing;
static ATOM dispatch_class;
static HINSTANCE dispatch_instance;

static LRESULT CALLBACK dispatch_window_proc(HWND window, UINT message,
                                             WPARAM wparam, LPARAM lparam)
{
    ul_frontend_dispatch_callback callback = NULL;
    unsigned command;
    uintptr_t generation;

    if (message == UL_FRONTEND_WM_COMMAND) {
        command = (unsigned)wparam;
        generation = (uintptr_t)lparam;
        if (command >= UL_FRONTEND_COMMAND_MIN &&
            command <= UL_FRONTEND_COMMAND_MAX && generation != 0u) {
            AcquireSRWLockShared(&state_lock);
            if (!closing && dispatch_window == window)
                callback = dispatch_callback;
            ReleaseSRWLockShared(&state_lock);
            if (callback != NULL)
                callback(command, generation);
            return 0;
        }
        return 0;
    }
    if (message == WM_NCDESTROY) {
        AcquireSRWLockExclusive(&state_lock);
        if (dispatch_window == window) {
            dispatch_window = NULL;
            closing = true;
            dispatch_callback = NULL;
        }
        ReleaseSRWLockExclusive(&state_lock);
    }
    return DefWindowProcW(window, message, wparam, lparam);
}

bool ul_frontend_dispatch_open(ul_frontend_dispatch_callback callback)
{
    WNDCLASSW window_class = {0};
    HWND window;

    if (callback == NULL)
        return false;
    AcquireSRWLockExclusive(&state_lock);
    if (opened) {
        ReleaseSRWLockExclusive(&state_lock);
        return false;
    }
    opened = true;
    dispatch_callback = callback;
    owner_thread = GetCurrentThreadId();
    ReleaseSRWLockExclusive(&state_lock);

    window_class.lpfnWndProc = dispatch_window_proc;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                            GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            (LPCWSTR)(const void *)&ul_frontend_dispatch_open,
                            &dispatch_instance))
        goto fail;
    window_class.hInstance = dispatch_instance;
    window_class.lpszClassName = L"Utterleaf.FrontendDispatch";
    dispatch_class = RegisterClassW(&window_class);
    if (dispatch_class == 0u)
        goto fail;
    window = CreateWindowExW(0, window_class.lpszClassName, L"Utterleaf",
                             0, 0, 0, 0, 0, HWND_MESSAGE, NULL,
                             window_class.hInstance, NULL);
    if (window == NULL)
        goto fail;
    AcquireSRWLockExclusive(&state_lock);
    dispatch_window = window;
    ReleaseSRWLockExclusive(&state_lock);
    return true;

fail:
    AcquireSRWLockExclusive(&state_lock);
    dispatch_callback = NULL;
    closing = true;
    ReleaseSRWLockExclusive(&state_lock);
    if (dispatch_class != 0u &&
        UnregisterClassW(window_class.lpszClassName, window_class.hInstance))
        dispatch_class = 0u;
    return false;
}

bool ul_frontend_dispatch_post(unsigned command, uintptr_t generation)
{
    HWND window;
    bool valid;

    if (command < UL_FRONTEND_COMMAND_MIN ||
        command > UL_FRONTEND_COMMAND_MAX || generation == 0u)
        return false;
    AcquireSRWLockShared(&state_lock);
    valid = opened && !closing && dispatch_window != NULL;
    window = dispatch_window;
    if (!valid) {
        ReleaseSRWLockShared(&state_lock);
        return false;
    }
    valid = PostMessageW(window, UL_FRONTEND_WM_COMMAND,
                         (WPARAM)command, (LPARAM)generation) != 0;
    ReleaseSRWLockShared(&state_lock);
    return valid;
}

void ul_frontend_dispatch_close(void)
{
    HWND window;
    HINSTANCE instance;
    bool owner;

    AcquireSRWLockExclusive(&state_lock);
    if (!opened) {
        ReleaseSRWLockExclusive(&state_lock);
        return;
    }
    closing = true;
    window = dispatch_window;
    instance = dispatch_instance;
    dispatch_callback = NULL;
    owner = owner_thread == GetCurrentThreadId();
    ReleaseSRWLockExclusive(&state_lock);
    if (!owner)
        return;
    if (window != NULL)
        DestroyWindow(window);
    if (dispatch_class != 0u &&
        UnregisterClassW(L"Utterleaf.FrontendDispatch", instance))
        dispatch_class = 0u;
}
