// SPDX-License-Identifier: GPL-2.0-or-later
#define _WIN32_WINNT 0x0601
#include <windows.h>
#include <commctrl.h>
#include <shlwapi.h>

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

#include "../src/pairing_ui.h"
#include "../src/plugin_state.h"

#ifndef PW_RENDERFULLCONTENT
#define PW_RENDERFULLCONTENT 0x00000002
#endif

typedef HRESULT (CALLBACK *ul_dll_get_version_fn)(DLLVERSIONINFO *);
typedef HRESULT (WINAPI *ul_task_dialog_fn)(const TASKDIALOGCONFIG *, int *,
                                             int *, BOOL *);

typedef struct fixture_state {
    HANDLE owner_ready;
    HANDLE begin_dialog;
    HANDLE dialog_done;
    HANDLE finish;
    HWND owner;
    DWORD ui_thread_id;
} fixture_state;

typedef struct dialog_search {
    HWND dialog;
    unsigned count;
} dialog_search;

#pragma pack(push, 1)
typedef struct bitmap_file_header {
    WORD type;
    DWORD size;
    WORD reserved1;
    WORD reserved2;
    DWORD pixel_offset;
} bitmap_file_header;
#pragma pack(pop)

static ul_plugin_snapshot fixture_snapshot;
static volatile LONG mutation_calls;
static volatile LONG config_checks;
static volatile LONG config_errors;
static HMODULE observed_common_controls;
static ul_task_dialog_fn observed_task_dialog;
static const wchar_t *expected_heading;
static const wchar_t *expected_content;
static const wchar_t *expected_buttons[3];
static unsigned expected_button_count;

static int check(bool condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", message);
        return 1;
    }
    return 0;
}

ul_plugin_snapshot ul_plugin_get_status(void)
{
    return fixture_snapshot;
}

ul_pairing_result ul_plugin_pair(const wchar_t *destination, bool replace,
                                 bool *pairing_saved)
{
    (void)destination;
    (void)replace;
    if (pairing_saved != NULL)
        *pairing_saved = false;
    InterlockedIncrement(&mutation_calls);
    return UL_PAIRING_CANCELLED;
}

ul_pairing_result ul_plugin_export(const wchar_t *destination)
{
    (void)destination;
    InterlockedIncrement(&mutation_calls);
    return UL_PAIRING_CANCELLED;
}

ul_pairing_result ul_plugin_forget(void)
{
    InterlockedIncrement(&mutation_calls);
    return UL_PAIRING_CANCELLED;
}

bool ul_plugin_start(void) { return false; }
void ul_plugin_stop_accepting(void) {}
void ul_plugin_close(void) {}
bool ul_plugin_issue(DWORD client_pid, const uint8_t session[16],
                     uint8_t additional_mix_mask, uint8_t out_challenge[60])
{
    (void)client_pid;
    (void)session;
    (void)additional_mix_mask;
    (void)out_challenge;
    return false;
}
bool ul_plugin_prepare(const uint8_t *challenge, size_t challenge_size,
                       const uint8_t *proof, size_t proof_size)
{
    (void)challenge;
    (void)challenge_size;
    (void)proof;
    (void)proof_size;
    return false;
}

static HRESULT WINAPI fixture_task_dialog(const TASKDIALOGCONFIG *config,
                                           int *button, int *radio,
                                           BOOL *verification)
{
    unsigned index;
    LONG errors = 0;

    if (config == NULL || config->hwndParent == NULL ||
        config->pszWindowTitle == NULL ||
        wcscmp(config->pszWindowTitle, L"Utterleaf - OBS pairing") != 0 ||
        config->pszMainInstruction == NULL || expected_heading == NULL ||
        wcscmp(config->pszMainInstruction, expected_heading) != 0 ||
        config->pszContent == NULL || expected_content == NULL ||
        wcscmp(config->pszContent, expected_content) != 0 ||
        config->pszFooter == NULL ||
        wcscmp(config->pszFooter,
               L"Pairing stays on this Windows account. Pairing never starts recording.") != 0 ||
        config->cButtons != expected_button_count ||
        (config->dwFlags & (TDF_ALLOW_DIALOG_CANCELLATION |
                            TDF_POSITION_RELATIVE_TO_WINDOW |
                            TDF_SIZE_TO_CONTENT | TDF_CALLBACK_TIMER)) !=
            (TDF_ALLOW_DIALOG_CANCELLATION |
             TDF_POSITION_RELATIVE_TO_WINDOW |
             TDF_SIZE_TO_CONTENT | TDF_CALLBACK_TIMER))
        ++errors;
    if (config != NULL) {
        for (index = 0; index < expected_button_count; ++index) {
            if (config->pButtons == NULL || expected_buttons[index] == NULL ||
                wcsstr(config->pButtons[index].pszButtonText,
                       expected_buttons[index]) == NULL)
                ++errors;
        }
    }
    InterlockedExchangeAdd(&config_errors, errors);
    InterlockedIncrement(&config_checks);
    if (observed_task_dialog == NULL)
        return E_UNEXPECTED;
    return observed_task_dialog(config, button, radio, verification);
}

HMODULE WINAPI fixture_LoadLibraryExW(LPCWSTR name, HANDLE file, DWORD flags)
{
    HMODULE module = LoadLibraryExW(name, file, flags);
    if (module != NULL && name != NULL && _wcsicmp(name, L"comctl32.dll") == 0)
        observed_common_controls = module;
    return module;
}

FARPROC WINAPI fixture_GetProcAddress(HMODULE module, LPCSTR name)
{
    FARPROC address = GetProcAddress(module, name);
    if (module == observed_common_controls && name != NULL &&
        strcmp(name, "TaskDialogIndirect") == 0 && address != NULL) {
        observed_task_dialog = (ul_task_dialog_fn)(void *)address;
        return (FARPROC)(void *)fixture_task_dialog;
    }
    return address;
}

static LRESULT CALLBACK owner_proc(HWND window, UINT message, WPARAM wparam,
                                   LPARAM lparam)
{
    if (message == WM_DESTROY) {
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(window, message, wparam, lparam);
}

static DWORD WINAPI ui_thread(void *parameter)
{
    fixture_state *state = parameter;
    WNDCLASSW klass = {0};
    unsigned index;

    state->ui_thread_id = GetCurrentThreadId();
    klass.lpfnWndProc = owner_proc;
    klass.hInstance = GetModuleHandleW(NULL);
    klass.lpszClassName = L"UtterleafPairingUiFixtureOwner";
    klass.hCursor = LoadCursorW(NULL, MAKEINTRESOURCEW(32512));
    klass.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    if (!RegisterClassW(&klass) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS)
        return 2;
    state->owner = CreateWindowExW(
        0, klass.lpszClassName, L"Utterleaf pairing fixture owner",
        WS_OVERLAPPEDWINDOW, 80, 80, 720, 440, NULL, NULL, klass.hInstance,
        NULL);
    if (state->owner == NULL)
        return 3;
    ShowWindow(state->owner, SW_SHOWNORMAL);
    UpdateWindow(state->owner);
    SetEvent(state->owner_ready);

    for (index = 0; index < 3; ++index) {
        if (WaitForSingleObject(state->begin_dialog, 5000) != WAIT_OBJECT_0)
            return 4;
        ResetEvent(state->begin_dialog);
        ul_pairing_ui_show(state->owner);
        SetEvent(state->dialog_done);
    }
    if (WaitForSingleObject(state->finish, 5000) != WAIT_OBJECT_0)
        return 5;
    DestroyWindow(state->owner);
    return 0;
}

static BOOL CALLBACK find_dialog_callback(HWND window, LPARAM parameter)
{
    dialog_search *search = (dialog_search *)parameter;
    wchar_t title[128];

    if (GetWindowTextW(window, title, 128) > 0 &&
        wcscmp(title, L"Utterleaf - OBS pairing") == 0) {
        search->dialog = window;
        ++search->count;
    }
    return TRUE;
}

static dialog_search find_dialog(DWORD thread_id)
{
    dialog_search search = {0};
    EnumThreadWindows(thread_id, find_dialog_callback, (LPARAM)&search);
    return search;
}

static HWND wait_for_dialog(DWORD thread_id, DWORD timeout_ms)
{
    ULONGLONG deadline = GetTickCount64() + timeout_ms;
    dialog_search search;

    do {
        search = find_dialog(thread_id);
        if (search.dialog != NULL)
            return search.dialog;
        Sleep(10);
    } while (GetTickCount64() < deadline);
    return NULL;
}

typedef struct text_search {
    const wchar_t *needle;
    bool found;
} text_search;

static BOOL CALLBACK find_text_callback(HWND window, LPARAM parameter)
{
    text_search *search = (text_search *)parameter;
    wchar_t text[1024];

    if (GetWindowTextW(window, text, 1024) > 0 &&
        wcsstr(text, search->needle) != NULL) {
        search->found = true;
        return FALSE;
    }
    return TRUE;
}

static bool dialog_has_text(HWND dialog, const wchar_t *needle)
{
    text_search search = {needle, false};

    EnumChildWindows(dialog, find_text_callback, (LPARAM)&search);
    return search.found;
}

static bool common_controls_v6_owns(HWND dialog, DWORD *major, DWORD *minor)
{
    HMODULE module = observed_common_controls;
    ul_dll_get_version_fn get_version;
    DLLVERSIONINFO version = {0};
    wchar_t path[MAX_PATH];
    wchar_t *name;

    (void)dialog;
    *major = 0;
    *minor = 0;
    if (module == NULL || GetModuleFileNameW(module, path, MAX_PATH) == 0)
        return false;
    name = wcsrchr(path, L'\\');
    name = name == NULL ? path : name + 1;
    if (_wcsicmp(name, L"comctl32.dll") != 0 ||
        GetProcAddress(module, "TaskDialogIndirect") == NULL)
        return false;
    get_version = (ul_dll_get_version_fn)(void *)GetProcAddress(
        module, "DllGetVersion");
    if (get_version == NULL)
        return false;
    version.cbSize = sizeof(version);
    if (FAILED(get_version(&version)))
        return false;
    *major = version.dwMajorVersion;
    *minor = version.dwMinorVersion;
    return version.dwMajorVersion >= 6;
}

static bool write_all(HANDLE file, const void *buffer, DWORD size)
{
    DWORD written = 0;
    return WriteFile(file, buffer, size, &written, NULL) && written == size;
}

static bool render_dialog(HWND dialog, const wchar_t *name,
                          unsigned long *distinct_pixels)
{
    RECT bounds;
    BITMAPINFO info = {0};
    bitmap_file_header file_header = {0};
    HDC window_dc = NULL;
    HDC memory_dc = NULL;
    HBITMAP bitmap = NULL;
    HGDIOBJ old_bitmap = NULL;
    uint32_t *pixels = NULL;
    HANDLE file = INVALID_HANDLE_VALUE;
    wchar_t directory[32768];
    wchar_t path[32768];
    int width, height;
    DWORD pixel_bytes;
    bool printed = false;
    bool ok = false;
    size_t index, count;
    uint32_t first;

    *distinct_pixels = 0;
    if (!GetWindowRect(dialog, &bounds))
        return false;
    width = bounds.right - bounds.left;
    height = bounds.bottom - bounds.top;
    if (width < 240 || height < 120)
        return false;
    info.bmiHeader.biSize = sizeof(info.bmiHeader);
    info.bmiHeader.biWidth = width;
    info.bmiHeader.biHeight = -height;
    info.bmiHeader.biPlanes = 1;
    info.bmiHeader.biBitCount = 32;
    info.bmiHeader.biCompression = BI_RGB;
    window_dc = GetDC(dialog);
    if (window_dc == NULL)
        goto cleanup;
    memory_dc = CreateCompatibleDC(window_dc);
    if (memory_dc == NULL)
        goto cleanup;
    bitmap = CreateDIBSection(window_dc, &info, DIB_RGB_COLORS,
                              (void **)&pixels, NULL, 0);
    if (bitmap == NULL || pixels == NULL)
        goto cleanup;
    old_bitmap = SelectObject(memory_dc, bitmap);
    if (old_bitmap == NULL || old_bitmap == HGDI_ERROR)
        goto cleanup;
    count = (size_t)width * (size_t)height;
    for (index = 0; index < count; ++index)
        pixels[index] = 0x00ff00ffu;
    RedrawWindow(dialog, NULL, NULL,
                 RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN);
    printed = PrintWindow(dialog, memory_dc, PW_RENDERFULLCONTENT) != FALSE;
    if (!printed)
        printed = BitBlt(memory_dc, 0, 0, width, height, window_dc, 0, 0,
                         SRCCOPY) != FALSE;
    if (!printed)
        goto cleanup;
    first = pixels[0];
    for (index = 1; index < count; ++index) {
        if (pixels[index] != first && pixels[index] != 0x00ff00ffu)
            ++*distinct_pixels;
    }
    if (*distinct_pixels < 100)
        goto cleanup;

    if (GetEnvironmentVariableW(L"UL_PAIRING_UI_CAPTURE_DIR", directory,
                                32768) != 0) {
        CreateDirectoryW(directory, NULL);
        if (_snwprintf(path, 32768, L"%ls\\%ls.bmp", directory, name) < 0)
            goto cleanup;
        file = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                           FILE_ATTRIBUTE_NORMAL, NULL);
        if (file == INVALID_HANDLE_VALUE)
            goto cleanup;
        pixel_bytes = (DWORD)(count * sizeof(*pixels));
        file_header.type = 0x4d42;
        file_header.pixel_offset = sizeof(file_header) + sizeof(info.bmiHeader);
        file_header.size = file_header.pixel_offset + pixel_bytes;
        if (!write_all(file, &file_header, sizeof(file_header)) ||
            !write_all(file, &info.bmiHeader, sizeof(info.bmiHeader)) ||
            !write_all(file, pixels, pixel_bytes))
            goto cleanup;
    }
    ok = true;

cleanup:
    if (file != INVALID_HANDLE_VALUE)
        CloseHandle(file);
    if (old_bitmap != NULL && old_bitmap != HGDI_ERROR)
        SelectObject(memory_dc, old_bitmap);
    if (bitmap != NULL)
        DeleteObject(bitmap);
    if (memory_dc != NULL)
        DeleteDC(memory_dc);
    if (window_dc != NULL)
        ReleaseDC(dialog, window_dc);
    return ok;
}

static DWORD WINAPI competing_dialog(void *parameter)
{
    ul_pairing_ui_show((HWND)parameter);
    return 0;
}

static int inspect_and_cancel(fixture_state *state, const wchar_t *capture_name,
                              const wchar_t *heading, const wchar_t *content,
                              const wchar_t *button1, const wchar_t *button2,
                              const wchar_t *button3, bool check_double_open)
{
    HWND dialog = wait_for_dialog(state->ui_thread_id, 4000);
    wchar_t class_name[64];
    DWORD major = 0, minor = 0;
    unsigned long rendered_pixels = 0;
    dialog_search search;
    HANDLE competitor = NULL;
    DWORD competitor_id = 0;
    int failures = 0;

    failures += check(dialog != NULL, "TaskDialog appeared");
    if (dialog == NULL)
        return failures;
    failures += check(GetClassNameW(dialog, class_name, 64) > 0 &&
                          wcscmp(class_name, L"#32770") == 0,
                      "TaskDialog has the native dialog class");
    failures += check(GetWindow(dialog, GW_OWNER) == state->owner,
                      "TaskDialog has the fixture owner");
    failures += check(!IsWindowEnabled(state->owner),
                      "TaskDialog is modal to the fixture owner");
    failures += check(common_controls_v6_owns(dialog, &major, &minor),
                      "TaskDialog is owned by common-controls v6");
    failures += check(wcscmp(expected_heading, heading) == 0 &&
                          wcsstr(expected_content, content) != NULL &&
                          InterlockedCompareExchange(&config_errors, 0, 0) == 0 &&
                          InterlockedCompareExchange(&config_checks, 0, 0) > 0,
                      "real TaskDialog received the exact heading, content, footer and flags");
    if (button1 != NULL)
        failures += check(dialog_has_text(dialog, button1), "first action rendered");
    if (button2 != NULL)
        failures += check(dialog_has_text(dialog, button2), "second action rendered");
    if (button3 != NULL)
        failures += check(dialog_has_text(dialog, button3), "third action rendered");
    failures += check(render_dialog(dialog, capture_name, &rendered_pixels),
                      "TaskDialog produced nonuniform rendered pixels");

    if (check_double_open) {
        competitor = CreateThread(NULL, 0, competing_dialog, state->owner, 0,
                                  &competitor_id);
        failures += check(competitor != NULL, "created competing open thread");
        if (competitor != NULL) {
            failures += check(WaitForSingleObject(competitor, 1000) ==
                                  WAIT_OBJECT_0,
                              "a second open returned while modal dialog ran");
            search = find_dialog(state->ui_thread_id);
            failures += check(search.count == 1,
                              "double-open guard kept one TaskDialog");
            CloseHandle(competitor);
        }
    }

    failures += check(PostMessageW(dialog, WM_KEYDOWN, VK_ESCAPE, 0),
                      "posted Escape keydown to fixture dialog");
    failures += check(PostMessageW(dialog, WM_KEYUP, VK_ESCAPE, 0),
                      "posted Escape keyup to fixture dialog");
    if (WaitForSingleObject(state->dialog_done, 3000) != WAIT_OBJECT_0) {
        failures += check(false, "Escape closed the TaskDialog");
        PostMessageW(dialog, WM_CLOSE, 0, 0);
    }
    failures += check(!IsWindow(dialog), "modal TaskDialog cleaned up");
    failures += check(IsWindowEnabled(state->owner),
                      "fixture owner re-enabled after cancellation");
    failures += check(InterlockedCompareExchange(&mutation_calls, 0, 0) == 0,
                      "keyboard cancellation made no pairing mutation");
    printf("%ls: native TaskDialog comctl32 %lu.%lu, %lu rendered pixels, Escape cancelled\n",
           capture_name, (unsigned long)major, (unsigned long)minor,
           rendered_pixels);
    return failures;
}

int main(void)
{
    fixture_state state = {0};
    HANDLE thread = NULL;
    DWORD exit_code = 1;
    int failures = 0;

    state.owner_ready = CreateEventW(NULL, TRUE, FALSE, NULL);
    state.begin_dialog = CreateEventW(NULL, TRUE, FALSE, NULL);
    state.dialog_done = CreateEventW(NULL, TRUE, FALSE, NULL);
    state.finish = CreateEventW(NULL, TRUE, FALSE, NULL);
    failures += check(state.owner_ready != NULL && state.begin_dialog != NULL &&
                          state.dialog_done != NULL && state.finish != NULL,
                      "created fixture synchronization events");
    if (failures != 0)
        return 1;
    thread = CreateThread(NULL, 0, ui_thread, &state, 0, NULL);
    failures += check(thread != NULL, "created fixture UI thread");
    failures += check(thread != NULL &&
                          WaitForSingleObject(state.owner_ready, 3000) ==
                              WAIT_OBJECT_0,
                      "fixture owner appeared");
    if (failures != 0)
        goto cleanup;

    fixture_snapshot = (ul_plugin_snapshot){UL_PLUGIN_UNPAIRED,
                                             UL_PAIRING_MISSING, true, false};
    expected_heading = L"Connect Utterleaf to OBS";
    expected_content = L"Create a pairing file, then explicitly import it in Utterleaf. Live transcription is still in development.";
    expected_buttons[0] = L"Pair Utterleaf";
    expected_button_count = 1;
    InterlockedExchange(&config_checks, 0);
    InterlockedExchange(&config_errors, 0);
    ResetEvent(state.dialog_done);
    SetEvent(state.begin_dialog);
    failures += inspect_and_cancel(
        &state, L"unpaired", L"Connect Utterleaf to OBS",
        L"Create a pairing file, then explicitly import it in Utterleaf.",
        L"Pair Utterleaf", NULL, NULL, true);

    fixture_snapshot = (ul_plugin_snapshot){UL_PLUGIN_PAIRED, UL_PAIRING_OK,
                                             true, true};
    expected_heading = L"Utterleaf is paired";
    expected_content = L"A connection is prepared. Replacing or forgetting pairing disconnects it.";
    expected_buttons[0] = L"Export pairing file";
    expected_buttons[1] = L"Replace pairing";
    expected_buttons[2] = L"Forget pairing";
    expected_button_count = 3;
    InterlockedExchange(&config_checks, 0);
    InterlockedExchange(&config_errors, 0);
    ResetEvent(state.dialog_done);
    SetEvent(state.begin_dialog);
    failures += inspect_and_cancel(
        &state, L"paired", L"Utterleaf is paired",
        L"A connection is prepared. Replacing or forgetting pairing disconnects it.",
        L"Export pairing file", L"Replace pairing", L"Forget pairing", false);

    fixture_snapshot = (ul_plugin_snapshot){UL_PLUGIN_STORAGE_ERROR,
                                             UL_PAIRING_CORRUPT, false, false};
    expected_heading = L"Pairing needs attention";
    expected_content = L"The saved pairing could not be verified. Forget this pairing before creating another.";
    expected_buttons[0] = NULL;
    expected_buttons[1] = NULL;
    expected_buttons[2] = NULL;
    expected_button_count = 0;
    InterlockedExchange(&config_checks, 0);
    InterlockedExchange(&config_errors, 0);
    ResetEvent(state.dialog_done);
    SetEvent(state.begin_dialog);
    failures += inspect_and_cancel(
        &state, L"storage-error", L"Pairing needs attention",
        L"The saved pairing could not be verified.", NULL, NULL, NULL, false);

cleanup:
    SetEvent(state.finish);
    if (thread != NULL) {
        if (WaitForSingleObject(thread, 3000) != WAIT_OBJECT_0)
            failures += check(false, "fixture UI thread exited");
        if (GetExitCodeThread(thread, &exit_code))
            failures += check(exit_code == 0, "fixture UI thread succeeded");
        CloseHandle(thread);
    }
    CloseHandle(state.owner_ready);
    CloseHandle(state.begin_dialog);
    CloseHandle(state.dialog_done);
    CloseHandle(state.finish);
    if (failures == 0)
        puts("pairing UI acceptance fixture passed");
    return failures == 0 ? 0 : 1;
}
