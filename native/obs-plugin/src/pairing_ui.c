// SPDX-License-Identifier: GPL-2.0-or-later
#define _WIN32_WINNT 0x0601
#include "pairing_ui.h"
#include "plugin_state.h"

#include <commctrl.h>
#include <shobjidl.h>
#include <stdbool.h>

#define UL_PAIR 101
#define UL_EXPORT 102
#define UL_REPLACE 103
#define UL_FORGET 104

typedef HRESULT (WINAPI *ul_task_dialog_fn)(const TASKDIALOGCONFIG *, int *, int *, BOOL *);
static volatile LONG dialog_running;

static HRESULT CALLBACK dialog_callback(HWND window, UINT notification,
                                        WPARAM wparam, LPARAM lparam, LONG_PTR data)
{
    (void)wparam;
    (void)lparam;
    if (notification == TDN_TIMER && ul_plugin_get_status().status == UL_PLUGIN_CLOSED)
        SendMessageW(window, TDM_CLICK_BUTTON, (WPARAM)data, 0);
    return S_OK;
}

static int show_dialog(ul_task_dialog_fn show, HWND owner, const wchar_t *heading,
                        const wchar_t *content, const TASKDIALOG_BUTTON *buttons,
                        unsigned count, int default_button)
{
    TASKDIALOGCONFIG config = {0};
    int selected = IDCANCEL;
    if (ul_plugin_get_status().status == UL_PLUGIN_CLOSED)
        return IDCANCEL;
    config.cbSize = sizeof(config);
    config.hwndParent = owner;
    config.dwFlags = TDF_ALLOW_DIALOG_CANCELLATION | TDF_POSITION_RELATIVE_TO_WINDOW |
                     TDF_SIZE_TO_CONTENT | TDF_CALLBACK_TIMER;
    if (count != 0u)
        config.dwFlags |= TDF_USE_COMMAND_LINKS;
    config.dwCommonButtons = count == 0u ? TDCBF_CLOSE_BUTTON : TDCBF_CANCEL_BUTTON;
    config.pszWindowTitle = L"Utterleaf - OBS pairing";
    config.pszMainInstruction = heading;
    config.pszContent = content;
    config.pszFooter = L"Pairing stays on this Windows account. Pairing never starts recording.";
    config.cButtons = count;
    config.pButtons = buttons;
    config.nDefaultButton = count == 0u ? IDCLOSE : default_button;
    config.pfCallback = dialog_callback;
    config.lpCallbackData = count == 0u ? IDCLOSE : IDCANCEL;
    if (FAILED(show(&config, &selected, NULL, NULL))) {
        if (ul_plugin_get_status().status != UL_PLUGIN_CLOSED && IsWindow(owner))
            MessageBoxW(owner, L"The pairing dialog could not be displayed. Restart OBS and try again.",
                          L"Utterleaf pairing", MB_OK | MB_ICONERROR);
        return IDCANCEL;
    }
    return selected;
}

static HRESULT choose_destination(HWND owner, wchar_t **path)
{
    IFileSaveDialog *dialog = NULL;
    IShellItem *item = NULL;
    FILEOPENDIALOGOPTIONS options;
    const COMDLG_FILTERSPEC filter = {L"Utterleaf OBS pairing", L"*.ulobs"};
    HRESULT result;
    *path = NULL;
    result = CoCreateInstance(&CLSID_FileSaveDialog, NULL, CLSCTX_INPROC_SERVER,
                               &IID_IFileSaveDialog, (void **)&dialog);
    if (FAILED(result))
        return result;
    result = dialog->lpVtbl->GetOptions(dialog, &options);
    if (SUCCEEDED(result))
        result = dialog->lpVtbl->SetOptions(dialog, (options & ~FOS_OVERWRITEPROMPT) | FOS_FORCEFILESYSTEM |
                                             FOS_PATHMUSTEXIST | FOS_DONTADDTORECENT |
                                             FOS_NOREADONLYRETURN);
    if (SUCCEEDED(result))
        result = dialog->lpVtbl->SetFileTypes(dialog, 1, &filter);
    if (SUCCEEDED(result))
        result = dialog->lpVtbl->SetDefaultExtension(dialog, L"ulobs");
    if (SUCCEEDED(result))
        result = dialog->lpVtbl->SetFileName(dialog, L"Utterleaf-OBS-pairing.ulobs");
    if (SUCCEEDED(result))
        result = dialog->lpVtbl->SetTitle(dialog, L"Save a new Utterleaf pairing file");
    if (SUCCEEDED(result))
        result = dialog->lpVtbl->Show(dialog, owner);
    if (SUCCEEDED(result))
        result = dialog->lpVtbl->GetResult(dialog, &item);
    if (SUCCEEDED(result))
        result = item->lpVtbl->GetDisplayName(item, SIGDN_FILESYSPATH, path);
    if (item != NULL)
        item->lpVtbl->Release(item);
    dialog->lpVtbl->Release(dialog);
    return result;
}

static const wchar_t *operation_error(ul_pairing_result result)
{
    switch (result) {
    case UL_PAIRING_EXISTS:
        return L"A file already exists at that location. Choose a new filename; existing files are never replaced.";
    case UL_PAIRING_IN_USE:
        return L"Another OBS process owns this pairing. Close that process, then restart this OBS instance.";
    case UL_PAIRING_UNSAFE_SECURITY:
    case UL_PAIRING_UNSUPPORTED:
        return L"This location cannot safely store pairing. Use a local Windows drive with private permissions and no linked folders.";
    case UL_PAIRING_CORRUPT:
        return L"The saved pairing could not be verified. Forget this pairing before creating another.";
    case UL_PAIRING_POSTCOMMIT_INVALID:
        return L"The save may have completed, but its final verification failed. Pairing is unavailable; check the storage location before trying again.";
    default:
        return L"The pairing operation could not finish. Check the storage location and available disk space, then try again.";
    }
}

static void pairing_actions(ul_task_dialog_fn show, HWND owner)
{
    static const TASKDIALOG_BUTTON pair[] = {{UL_PAIR, L"Pair Utterleaf\nCreate a private file to import in Utterleaf."}};
    static const TASKDIALOG_BUTTON paired[] = {
        {UL_EXPORT, L"Export pairing file\nCreate another file for the current pairing."},
        {UL_REPLACE, L"Replace pairing\nDisconnect existing clients and create a new pairing."},
        {UL_FORGET, L"Forget pairing\nRevoke this pairing, including copied pairing files."},
    };
    static const TASKDIALOG_BUTTON forget[] = {{UL_FORGET, L"Forget pairing\nRemove the saved pairing so you can start again."}};
    ul_plugin_snapshot before = ul_plugin_get_status();
    ul_pairing_result result;
    wchar_t *path = NULL;
    bool saved = false;
    int action;
    if (before.status == UL_PLUGIN_CLOSED)
        return;
    if (before.status == UL_PLUGIN_IN_USE) {
        show_dialog(show, owner, L"Pairing is open in another OBS process",
                      operation_error(UL_PAIRING_IN_USE), NULL, 0u, IDCANCEL);
        return;
    }
    if (before.status == UL_PLUGIN_UNPAIRED)
        action = show_dialog(show, owner, L"Connect Utterleaf to OBS",
                               L"Create a pairing file, then explicitly import it in Utterleaf. Live transcription is still in development.",
                               pair, 1u, UL_PAIR);
    else if (before.status == UL_PLUGIN_PAIRED)
        action = show_dialog(show, owner, L"Utterleaf is paired",
                               before.admission_pending ? L"A connection is prepared. Replacing or forgetting pairing disconnects it." :
                                                          L"Manage your pairing without changing OBS audio, stream or recording settings.",
                               paired, 3u, UL_EXPORT);
    else
        action = show_dialog(show, owner, L"Pairing needs attention", operation_error(before.storage_result),
                               before.owns_store ? forget : NULL, before.owns_store ? 1u : 0u, IDCANCEL);
    if (action == IDCANCEL || ul_plugin_get_status().status == UL_PLUGIN_CLOSED)
        return;
    if (action == UL_FORGET) {
        if (show_dialog(show, owner, L"Forget this pairing?",
                          L"Utterleaf will disconnect. Existing pairing files will no longer authorize new connections. Models and transcripts are kept.",
                          forget, 1u, IDCANCEL) != UL_FORGET)
            return;
        result = ul_plugin_forget();
        if (result != UL_PAIRING_OK && result != UL_PAIRING_MISSING) {
            show_dialog(show, owner, L"Disconnected, but pairing could not be removed",
                          L"Current connections are revoked. The saved pairing remains and may work again after OBS restarts. Resolve the storage problem and retry Forget pairing.",
                          NULL, 0u, IDCANCEL);
            return;
        }
        show_dialog(show, owner, L"Pairing forgotten", L"Create a new pairing when you want to connect Utterleaf again.", NULL, 0u, IDCANCEL);
        return;
    }
    if (action != UL_PAIR && action != UL_REPLACE && action != UL_EXPORT)
        return;
    HRESULT selected = choose_destination(owner, &path);
    if (FAILED(selected) || path == NULL) {
        if (selected != HRESULT_FROM_WIN32(ERROR_CANCELLED))
            show_dialog(show, owner, L"Could not choose a pairing file", L"No pairing changes were made. Try opening the file picker again.", NULL, 0u, IDCANCEL);
        CoTaskMemFree(path);
        return;
    }
    if (action == UL_REPLACE && show_dialog(show, owner, L"Replace this pairing?",
        L"Existing clients will disconnect and old pairing files will stop working. Import the new file in Utterleaf to reconnect.",
        &paired[1], 1u, IDCANCEL) != UL_REPLACE) {
        CoTaskMemFree(path);
        return;
    }
    result = action == UL_EXPORT ? ul_plugin_export(path) : ul_plugin_pair(path, action == UL_REPLACE, &saved);
    CoTaskMemFree(path);
    if (result == UL_PAIRING_CANCELLED)
        return;
    if (result == UL_PAIRING_OK)
        show_dialog(show, owner, L"Pairing file saved", L"Explicitly import this file in Utterleaf. A copied file remains valid for this Windows account until you replace or forget pairing in OBS.", NULL, 0u, IDCANCEL);
    else if (action == UL_EXPORT || saved) {
        const wchar_t *detail = result == UL_PAIRING_POSTCOMMIT_INVALID ?
            L"The pairing file may have been written, but its final verification failed. Your current pairing is still active. Choose a new filename and export again before importing it." :
            L"Your current pairing is still active. The file was not exported. Choose Export pairing file and a new local filename to try again; existing files are never overwritten.";
        show_dialog(show, owner, saved ? L"Pairing saved; export did not finish" : L"Pairing file could not be exported", detail, NULL, 0u, IDCANCEL);
    }
    else if (result == UL_PAIRING_POSTCOMMIT_INVALID)
        show_dialog(show, owner, L"Pairing could not be verified", operation_error(result), NULL, 0u, IDCANCEL);
    else if (ul_plugin_get_status().status == UL_PLUGIN_STORAGE_ERROR)
        show_dialog(show, owner, L"Pairing is unavailable",
                      L"The saved pairing could not be activated or verified. An earlier pairing may already have been replaced. Open pairing controls again to resolve the saved pairing before reconnecting.",
                      NULL, 0u, IDCANCEL);
    else
        show_dialog(show, owner, action == UL_REPLACE ? L"Existing pairing kept" : L"No pairing was created",
                      action == UL_REPLACE ?
                      L"The replacement could not be saved. Your existing pairing and connections remain active. Check the storage location and available disk space, then try again." :
                      L"The new pairing could not be saved. Check the storage location and available disk space, then try again.",
                      NULL, 0u, IDCANCEL);
}

void ul_pairing_ui_show(HWND owner)
{
    HMODULE self = NULL, common_controls = NULL;
    HANDLE context = INVALID_HANDLE_VALUE;
    ULONG_PTR cookie = 0;
    bool activated = false;
    HRESULT com = E_FAIL;
    ACTCTXW activation = {0};
    ul_task_dialog_fn show = NULL;
    if (owner == NULL || !IsWindow(owner) ||
        InterlockedCompareExchange(&dialog_running, 1, 0) != 0)
        return;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            (LPCWSTR)(const void *)&dialog_running, &self))
        goto cleanup;
    activation.cbSize = sizeof(activation);
    activation.dwFlags = ACTCTX_FLAG_RESOURCE_NAME_VALID | ACTCTX_FLAG_HMODULE_VALID;
    activation.hModule = self;
    activation.lpResourceName = MAKEINTRESOURCEW(2);
    context = CreateActCtxW(&activation);
    if (context == INVALID_HANDLE_VALUE || !ActivateActCtx(context, &cookie))
        goto cleanup;
    activated = true;
    common_controls = LoadLibraryExW(L"comctl32.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (common_controls == NULL)
        goto cleanup;
    show = (ul_task_dialog_fn)(void *)GetProcAddress(common_controls, "TaskDialogIndirect");
    if (show == NULL)
        goto cleanup;
    com = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE);
    if (SUCCEEDED(com))
        pairing_actions(show, owner);
    else
        show_dialog(show, owner, L"Pairing controls could not open", L"Restart OBS and try again. No pairing changes were made.", NULL, 0u, IDCANCEL);
cleanup:
    if (SUCCEEDED(com))
        CoUninitialize();
    if (common_controls != NULL)
        FreeLibrary(common_controls);
    if (activated)
        DeactivateActCtx(0, cookie);
    if (context != INVALID_HANDLE_VALUE)
        ReleaseActCtx(context);
    if (show == NULL && ul_plugin_get_status().status != UL_PLUGIN_CLOSED && IsWindow(owner))
        MessageBoxW(owner, L"Windows could not open the pairing controls. Restart OBS and try again. No pairing changes were made.",
                      L"Utterleaf pairing", MB_OK | MB_ICONERROR);
    InterlockedExchange(&dialog_running, 0);
}
