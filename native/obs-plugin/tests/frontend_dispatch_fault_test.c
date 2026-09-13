// SPDX-License-Identifier: GPL-2.0-or-later
/* Real message-only HWNDs, with deterministic creation/post fault boundaries. */
#include <windows.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>

static HWND WINAPI create_window(DWORD, LPCWSTR, LPCWSTR, DWORD, int, int,
                                  int, int, HWND, HMENU, HINSTANCE, LPVOID);
static BOOL WINAPI post_message(HWND, UINT, WPARAM, LPARAM);
#define CreateWindowExW create_window
#define PostMessageW post_message
#include "../src/frontend_dispatch.c"
#undef CreateWindowExW
#undef PostMessageW

static bool fail_create, fail_post, check_post_lock;
static unsigned callbacks;
static HANDLE close_started, close_finished;

static HWND WINAPI create_window(DWORD ex, LPCWSTR cls, LPCWSTR name, DWORD style,
                                  int x, int y, int w, int h, HWND parent,
                                  HMENU menu, HINSTANCE instance, LPVOID param)
{
    if (fail_create) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return NULL; }
    return CreateWindowExW(ex, cls, name, style, x, y, w, h, parent, menu, instance, param);
}

static BOOL WINAPI post_message(HWND window, UINT msg, WPARAM wparam, LPARAM lparam)
{
    if (check_post_lock) {
        /* The endpoint cannot be destroyed/reused between validation and post. */
        assert(!TryAcquireSRWLockExclusive(&state_lock));
        SetEvent(close_started);
        assert(WaitForSingleObject(close_finished, 20) == WAIT_TIMEOUT);
    }
    if (fail_post) { SetLastError(ERROR_NOT_ENOUGH_QUOTA); return FALSE; }
    return PostMessageW(window, msg, wparam, lparam);
}

static void receive(unsigned command, uintptr_t generation)
{
    assert(command == 2 && generation == 42);
    ++callbacks;
}

static void pump(void)
{
    MSG message;
    while (PeekMessageW(&message, NULL, 0, 0, PM_REMOVE))
        DispatchMessageW(&message);
}

static DWORD WINAPI close_worker(void *parameter)
{
    if (parameter != NULL)
        assert(WaitForSingleObject(close_started, 2000) == WAIT_OBJECT_0);
    ul_frontend_dispatch_close();
    if (close_finished != NULL) SetEvent(close_finished);
    return 0;
}

static ATOM foreign_class(void)
{
    WNDCLASSW cls = {0};
    cls.lpfnWndProc = DefWindowProcW;
    cls.hInstance = GetModuleHandleW(NULL);
    cls.lpszClassName = L"Utterleaf.FrontendDispatch";
    return RegisterClassW(&cls);
}

static void class_is_foreign(void)
{
    WNDCLASSW cls;
    assert(GetClassInfoW(GetModuleHandleW(NULL), L"Utterleaf.FrontendDispatch", &cls));
    assert(cls.lpfnWndProc == DefWindowProcW);
}

static void scenario(int mode)
{
    HANDLE worker;
    if (mode == 1) {
        assert(foreign_class() != 0);
        assert(!ul_frontend_dispatch_open(receive));
        assert(closing && dispatch_window == NULL && dispatch_class == 0);
        ul_frontend_dispatch_close();
        class_is_foreign();
        assert(UnregisterClassW(L"Utterleaf.FrontendDispatch", GetModuleHandleW(NULL)));
        return;
    }
    if (mode == 2) {
        WNDCLASSW cls;
        fail_create = true;
        assert(!ul_frontend_dispatch_open(receive));
        assert(closing && dispatch_class == 0 && dispatch_window == NULL);
        assert(!GetClassInfoW(GetModuleHandleW(NULL), L"Utterleaf.FrontendDispatch", &cls));
        fail_create = false;
        assert(!ul_frontend_dispatch_open(receive));
        return;
    }
    assert(ul_frontend_dispatch_open(receive));
    assert(dispatch_instance == GetModuleHandleW(NULL));
    if (mode == 3) {
        assert(ul_frontend_dispatch_post(2, 42));
        worker = CreateThread(NULL, 0, close_worker, NULL, 0, NULL);
        assert(worker && WaitForSingleObject(worker, 2000) == WAIT_OBJECT_0);
        CloseHandle(worker);
        assert(closing && dispatch_callback == NULL && dispatch_window != NULL);
        pump();
        assert(callbacks == 0);
    } else if (mode == 4) {
        HWND old_window = dispatch_window;
        assert(DestroyWindow(old_window));
        assert(closing && dispatch_callback == NULL && dispatch_window == NULL);
        assert(!ul_frontend_dispatch_post(2, 42));
    } else if (mode == 5) {
        close_started = CreateEventW(NULL, TRUE, FALSE, NULL);
        close_finished = CreateEventW(NULL, TRUE, FALSE, NULL);
        assert(close_started && close_finished);
        check_post_lock = true;
        worker = CreateThread(NULL, 0, close_worker, (void *)1, 0, NULL);
        assert(worker && ul_frontend_dispatch_post(2, 42));
        assert(WaitForSingleObject(worker, 2000) == WAIT_OBJECT_0);
        CloseHandle(worker);
        CloseHandle(close_started); CloseHandle(close_finished);
        pump(); assert(callbacks == 0 && closing);
    } else if (mode == 6) {
        assert(!ul_frontend_dispatch_post(5, 42));
        fail_post = true;
        assert(!ul_frontend_dispatch_post(2, 42));
        fail_post = false;
        assert(ul_frontend_dispatch_post(2, 42));
        pump(); assert(callbacks == 1);
    } else {
        assert(mode == 7);
        AcquireSRWLockExclusive(&state_lock);
        assert(!ul_frontend_dispatch_try_post(2, 42));
        ReleaseSRWLockExclusive(&state_lock);
        assert(ul_frontend_dispatch_try_post(2, 42));
        pump(); assert(callbacks == 1);
    }
    ul_frontend_dispatch_close();
    assert(dispatch_window == NULL && dispatch_class == 0);
    /* Repeated close owns no later class registered under the same name. */
    assert(foreign_class() != 0);
    ul_frontend_dispatch_close();
    class_is_foreign();
    assert(UnregisterClassW(L"Utterleaf.FrontendDispatch", GetModuleHandleW(NULL)));
}

int main(int argc, char **argv)
{
    if (argc == 2) { scenario(atoi(argv[1])); return 0; }
    WCHAR executable[MAX_PATH], command[MAX_PATH + 16];
    assert(GetModuleFileNameW(NULL, executable, MAX_PATH));
    for (unsigned mode = 1; mode <= 7; ++mode) {
        STARTUPINFOW start = {0};
        PROCESS_INFORMATION process = {0};
        DWORD code;
        start.cb = sizeof(start);
        assert(_snwprintf(command, MAX_PATH + 16, L"\"%ls\" %u", executable, mode) > 0);
        assert(CreateProcessW(executable, command, NULL, NULL, FALSE, CREATE_NO_WINDOW,
                              NULL, NULL, &start, &process));
        assert(WaitForSingleObject(process.hProcess, 5000) == WAIT_OBJECT_0);
        assert(GetExitCodeProcess(process.hProcess, &code) && code == 0);
        CloseHandle(process.hThread); CloseHandle(process.hProcess);
    }
    puts("frontend dispatcher failure, collision, destruction and post/close races passed");
    return 0;
}
