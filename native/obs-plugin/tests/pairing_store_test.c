// SPDX-License-Identifier: GPL-2.0-or-later
#include <windows.h>
#include <bcrypt.h>
#include <dpapi.h>

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

static bool fail_random;
static bool fail_protect;
static bool fail_unprotect;
static bool fail_write;
static bool fail_flush;
static bool fail_move;
static bool fail_delete;
static bool partial_write_then_fail;
static unsigned int write_calls;
static bool fake_reparse;
static bool fake_no_persistent_acls;
static volatile LONG *cancel_on_flush;

static NTSTATUS WINAPI shim_BCryptGenRandom(BCRYPT_ALG_HANDLE algorithm,
                                            PUCHAR output, ULONG size,
                                            ULONG flags);
static BOOL WINAPI shim_CryptProtectData(DATA_BLOB *input, LPCWSTR description,
                                         DATA_BLOB *entropy, PVOID reserved,
                                         CRYPTPROTECT_PROMPTSTRUCT *prompt,
                                         DWORD flags, DATA_BLOB *output);
static BOOL WINAPI shim_CryptUnprotectData(
    DATA_BLOB *input, LPWSTR *description, DATA_BLOB *entropy, PVOID reserved,
    CRYPTPROTECT_PROMPTSTRUCT *prompt, DWORD flags, DATA_BLOB *output);
static BOOL WINAPI shim_WriteFile(HANDLE file, LPCVOID buffer, DWORD requested,
                                  LPDWORD written, LPOVERLAPPED overlapped);
static BOOL WINAPI shim_FlushFileBuffers(HANDLE file);
static BOOL WINAPI shim_MoveFileExW(LPCWSTR existing, LPCWSTR replacement,
                                    DWORD flags);
static BOOL WINAPI shim_SetFileInformationByHandle(
    HANDLE file, FILE_INFO_BY_HANDLE_CLASS kind, LPVOID information,
    DWORD information_size);
static BOOL WINAPI shim_GetFileInformationByHandleEx(
    HANDLE file, FILE_INFO_BY_HANDLE_CLASS kind, LPVOID information,
    DWORD information_size);
static BOOL WINAPI shim_GetVolumeInformationByHandleW(
    HANDLE root, LPWSTR volume_name, DWORD volume_name_size,
    LPDWORD serial_number, LPDWORD maximum_component_length,
    LPDWORD file_system_flags, LPWSTR file_system_name,
    DWORD file_system_name_size);

#define BCryptGenRandom shim_BCryptGenRandom
#define CryptProtectData shim_CryptProtectData
#define CryptUnprotectData shim_CryptUnprotectData
#define WriteFile shim_WriteFile
#define FlushFileBuffers shim_FlushFileBuffers
#define MoveFileExW shim_MoveFileExW
#define SetFileInformationByHandle shim_SetFileInformationByHandle
#define GetFileInformationByHandleEx shim_GetFileInformationByHandleEx
#define GetVolumeInformationByHandleW shim_GetVolumeInformationByHandleW
#include "../src/pairing_store.c"
#undef BCryptGenRandom
#undef CryptProtectData
#undef CryptUnprotectData
#undef WriteFile
#undef FlushFileBuffers
#undef MoveFileExW
#undef SetFileInformationByHandle
#undef GetFileInformationByHandleEx
#undef GetVolumeInformationByHandleW

static NTSTATUS WINAPI shim_BCryptGenRandom(BCRYPT_ALG_HANDLE algorithm,
                                            PUCHAR output, ULONG size,
                                            ULONG flags)
{
    if (fail_random)
        return (NTSTATUS)0xc0000001L;
    return BCryptGenRandom(algorithm, output, size, flags);
}

static BOOL WINAPI shim_CryptProtectData(DATA_BLOB *input, LPCWSTR description,
                                         DATA_BLOB *entropy, PVOID reserved,
                                         CRYPTPROTECT_PROMPTSTRUCT *prompt,
                                         DWORD flags, DATA_BLOB *output)
{
    if (fail_protect) {
        SetLastError(ERROR_INVALID_DATA);
        return FALSE;
    }
    return CryptProtectData(input, description, entropy, reserved, prompt,
                            flags, output);
}

static BOOL WINAPI shim_CryptUnprotectData(
    DATA_BLOB *input, LPWSTR *description, DATA_BLOB *entropy, PVOID reserved,
    CRYPTPROTECT_PROMPTSTRUCT *prompt, DWORD flags, DATA_BLOB *output)
{
    if (fail_unprotect) {
        SetLastError(ERROR_INVALID_DATA);
        return FALSE;
    }
    return CryptUnprotectData(input, description, entropy, reserved, prompt,
                              flags, output);
}

static BOOL WINAPI shim_WriteFile(HANDLE file, LPCVOID buffer, DWORD requested,
                                  LPDWORD written, LPOVERLAPPED overlapped)
{
    if (partial_write_then_fail) {
        if (write_calls++ == 0u) {
            DWORD partial = requested > 7u ? 7u : requested;
            return WriteFile(file, buffer, partial, written, overlapped);
        }
        SetLastError(ERROR_WRITE_FAULT);
        return FALSE;
    }
    if (fail_write) {
        SetLastError(ERROR_WRITE_FAULT);
        return FALSE;
    }
    return WriteFile(file, buffer, requested, written, overlapped);
}

static BOOL WINAPI shim_FlushFileBuffers(HANDLE file)
{
    if (fail_flush) {
        SetLastError(ERROR_WRITE_FAULT);
        return FALSE;
    }
    if (!FlushFileBuffers(file))
        return FALSE;
    if (cancel_on_flush != NULL)
        (void)InterlockedCompareExchange(cancel_on_flush, 1, 0);
    return TRUE;
}

static BOOL WINAPI shim_MoveFileExW(LPCWSTR existing, LPCWSTR replacement,
                                    DWORD flags)
{
    if (fail_move) {
        SetLastError(ERROR_WRITE_FAULT);
        return FALSE;
    }
    return MoveFileExW(existing, replacement, flags);
}

static BOOL WINAPI shim_SetFileInformationByHandle(
    HANDLE file, FILE_INFO_BY_HANDLE_CLASS kind, LPVOID information,
    DWORD information_size)
{
    if (fail_delete) {
        SetLastError(ERROR_ACCESS_DENIED);
        return FALSE;
    }
    return SetFileInformationByHandle(file, kind, information,
                                      information_size);
}

static BOOL WINAPI shim_GetFileInformationByHandleEx(
    HANDLE file, FILE_INFO_BY_HANDLE_CLASS kind, LPVOID information,
    DWORD information_size)
{
    BOOL success = GetFileInformationByHandleEx(file, kind, information,
                                                 information_size);

    if (success && fake_reparse && kind == FileAttributeTagInfo &&
        information_size >= sizeof(FILE_ATTRIBUTE_TAG_INFO))
        ((FILE_ATTRIBUTE_TAG_INFO *)information)->FileAttributes |=
            FILE_ATTRIBUTE_REPARSE_POINT;
    return success;
}

static BOOL WINAPI shim_GetVolumeInformationByHandleW(
    HANDLE root, LPWSTR volume_name, DWORD volume_name_size,
    LPDWORD serial_number, LPDWORD maximum_component_length,
    LPDWORD file_system_flags, LPWSTR file_system_name,
    DWORD file_system_name_size)
{
    BOOL success = GetVolumeInformationByHandleW(
        root, volume_name, volume_name_size, serial_number,
        maximum_component_length, file_system_flags, file_system_name,
        file_system_name_size);

    if (success && fake_no_persistent_acls && file_system_flags != NULL)
        *file_system_flags &= ~FILE_PERSISTENT_ACLS;
    return success;
}

static int check(bool condition, const char *message)
{
    if (condition)
        return 0;
    fprintf(stderr, "FAIL: %s\n", message);
    return 1;
}

static bool make_root(wchar_t root[MAX_PATH])
{
    wchar_t temporary[MAX_PATH];

    SecureZeroMemory(temporary, sizeof(temporary));
    if (GetTempPathW(MAX_PATH, temporary) == 0u ||
        GetTempFileNameW(temporary, L"ulp", 0, root) == 0u ||
        !DeleteFileW(root) || !CreateDirectoryW(root, NULL))
        return false;
    return true;
}

static bool missing_path_error(DWORD error)
{
    return error == ERROR_FILE_NOT_FOUND || error == ERROR_PATH_NOT_FOUND;
}

static int delete_known_file(const wchar_t *path)
{
    DWORD attributes = GetFileAttributesW(path);

    if (attributes == INVALID_FILE_ATTRIBUTES)
        return missing_path_error(GetLastError())
                   ? 0
                   : check(false, "inspect known cleanup file");
    if ((attributes & (FILE_ATTRIBUTE_DIRECTORY |
                       FILE_ATTRIBUTE_REPARSE_POINT)) != 0u)
        return check(false, "known cleanup file changed object type");
    return check(DeleteFileW(path), "delete known cleanup file");
}

static bool pairing_temp_name(const wchar_t *name)
{
    static const wchar_t prefix[] = L".utterleaf-pairing-";
    static const wchar_t suffix[] = L".tmp";
    size_t length = wcslen(name);
    size_t index;

    if (length != 55u || wcsncmp(name, prefix, 19u) != 0 ||
        wcscmp(name + 51u, suffix) != 0)
        return false;
    for (index = 19u; index < 51u; ++index) {
        if (!((name[index] >= L'0' && name[index] <= L'9') ||
              (name[index] >= L'a' && name[index] <= L'f')))
            return false;
    }
    return true;
}

static int remove_known_directory(const wchar_t *path)
{
    DWORD attributes = GetFileAttributesW(path);

    if (attributes == INVALID_FILE_ATTRIBUTES)
        return missing_path_error(GetLastError())
                   ? 0
                   : check(false, "inspect cleanup directory");
    if ((attributes & FILE_ATTRIBUTE_DIRECTORY) == 0u ||
        (attributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0u)
        return check(false, "cleanup directory changed object type");
    return check(RemoveDirectoryW(path), "remove expected cleanup directory");
}

static int cleanup_root(const wchar_t *root)
{
    wchar_t path[MAX_PATH];
    wchar_t search[MAX_PATH];
    WIN32_FIND_DATAW entry;
    HANDLE find = INVALID_HANDLE_VALUE;
    DWORD leaf_attributes;
    unsigned int entries = 0;
    int failures = 0;

    swprintf(path, MAX_PATH, L"%ls\\package.utterleaf", root);
    failures += delete_known_file(path);
    swprintf(path, MAX_PATH, L"%ls\\cancelled.utterleaf", root);
    failures += delete_known_file(path);
    swprintf(path, MAX_PATH, L"%ls\\Utterleaf\\obs-plugin\\pairing-v1.dat",
             root);
    failures += delete_known_file(path);
    swprintf(path, MAX_PATH, L"%ls\\Utterleaf\\obs-plugin\\owner-v1.lock",
             root);
    failures += delete_known_file(path);
    swprintf(path, MAX_PATH, L"%ls\\Utterleaf\\obs-plugin", root);
    leaf_attributes = GetFileAttributesW(path);
    if (leaf_attributes != INVALID_FILE_ATTRIBUTES &&
        ((leaf_attributes & FILE_ATTRIBUTE_DIRECTORY) == 0u ||
         (leaf_attributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0u)) {
        failures += check(false, "private cleanup directory changed type");
        goto remove_directories;
    }
    if (leaf_attributes == INVALID_FILE_ATTRIBUTES &&
        !missing_path_error(GetLastError())) {
        failures += check(false, "inspect private cleanup directory");
        goto remove_directories;
    }
    swprintf(search, MAX_PATH, L"%ls\\*", path);
    SecureZeroMemory(&entry, sizeof(entry));
    find = FindFirstFileW(search, &entry);
    if (find != INVALID_HANDLE_VALUE) {
        do {
            if (wcscmp(entry.cFileName, L".") == 0 ||
                wcscmp(entry.cFileName, L"..") == 0)
                continue;
            ++entries;
            if (entries > 64u) {
                failures += check(false,
                                  "bounded private cleanup directory contents");
                break;
            }
            if (!pairing_temp_name(entry.cFileName) ||
                (entry.dwFileAttributes &
                 (FILE_ATTRIBUTE_DIRECTORY |
                  FILE_ATTRIBUTE_REPARSE_POINT)) != 0u) {
                failures += check(false,
                                  "unexpected private cleanup artifact");
                continue;
            }
            failures += check(false, "temporary pairing artifact leaked");
            if (join_path(path, entry.cFileName, search))
                failures += delete_known_file(search);
            else
                failures += check(false, "bounded temporary cleanup path");
        } while (FindNextFileW(find, &entry));
        if (GetLastError() != ERROR_NO_MORE_FILES)
            failures += check(false, "enumerate private cleanup directory");
        FindClose(find);
    } else if (!missing_path_error(GetLastError())) {
        failures += check(false, "open private cleanup directory");
    }
remove_directories:
    failures += remove_known_directory(path);
    swprintf(path, MAX_PATH, L"%ls\\Utterleaf", root);
    failures += remove_known_directory(path);
    failures += remove_known_directory(root);
    return failures;
}

static bool key_is_zero(const uint8_t key[UL_PAIRING_KEY_BYTES])
{
    return bytes_are_zero(key, UL_PAIRING_KEY_BYTES);
}

static int test_round_trip_and_security(void)
{
    wchar_t root[MAX_PATH];
    wchar_t package[MAX_PATH];
    uint8_t created[UL_PAIRING_KEY_BYTES];
    uint8_t loaded[UL_PAIRING_KEY_BYTES];
    uint8_t replacement[UL_PAIRING_KEY_BYTES];
    uint8_t package_key[UL_PAIRING_KEY_BYTES];
    uint8_t package_bytes[UL_PAIRING_MAX_FILE_BYTES];
    ul_pairing_store *store = NULL;
    HANDLE file = INVALID_HANDLE_VALUE;
    LARGE_INTEGER size;
    DWORD read = 0;
    int failures = 0;

    SecureZeroMemory(root, sizeof(root));
    SecureZeroMemory(package, sizeof(package));
    SecureZeroMemory(created, sizeof(created));
    SecureZeroMemory(loaded, sizeof(loaded));
    SecureZeroMemory(replacement, sizeof(replacement));
    SecureZeroMemory(package_key, sizeof(package_key));
    SecureZeroMemory(package_bytes, sizeof(package_bytes));
    SecureZeroMemory(&size, sizeof(size));
    failures += check(make_root(root), "create disposable root");
    if (failures != 0)
        return failures;
    failures += check(ul_pairing_store_open_test_root(root, &store) ==
                          UL_PAIRING_OK &&
                          store != NULL,
                      "open test store");
    if (store == NULL) {
        failures += cleanup_root(root);
        return failures;
    }
    failures += check(verify_private_security(
                          store->directories.handles[
                              store->directories.count - 1u],
                          store->user_sid) == UL_PAIRING_OK,
                      "private leaf directory ACL");
    failures += check(ul_pairing_store_load(store, loaded) ==
                          UL_PAIRING_MISSING &&
                          key_is_zero(loaded),
                      "missing store is distinct and output zero");
    failures += check(ul_pairing_store_create(store, NULL, created) ==
                          UL_PAIRING_OK &&
                          !key_is_zero(created),
                      "create role-1 store");
    failures += check(ul_pairing_store_load(store, loaded) == UL_PAIRING_OK &&
                          constant_equal(created, loaded, sizeof(created)),
                      "reload role-1 store");
    failures += check(ul_pairing_store_create(store, NULL, loaded) ==
                          UL_PAIRING_EXISTS &&
                          key_is_zero(loaded),
                      "create never replaces");
    swprintf(package, MAX_PATH, L"%ls\\package.utterleaf", root);
    failures += check(ul_pairing_store_export(store, package, NULL) ==
                          UL_PAIRING_OK,
                      "export role-2 package");
    failures += check(ul_pairing_store_export(store, package, NULL) ==
                          UL_PAIRING_EXISTS,
                      "export never replaces");
    file = CreateFileW(package, GENERIC_READ | READ_CONTROL, 0, NULL,
                       OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, NULL);
    failures += check(file != INVALID_HANDLE_VALUE, "open package");
    if (file != INVALID_HANDLE_VALUE) {
        failures += check(verify_private_security(file, store->user_sid) ==
                              UL_PAIRING_OK,
                          "package private ACL");
        failures += check(GetFileSizeEx(file, &size) && size.QuadPart >= 13 &&
                              size.QuadPart <= UL_PAIRING_MAX_FILE_BYTES &&
                              ReadFile(file, package_bytes, (DWORD)size.QuadPart,
                                       &read, NULL) &&
                              read == (DWORD)size.QuadPart,
                          "read bounded package");
        CloseHandle(file);
        file = INVALID_HANDLE_VALUE;
        failures += check(unprotect_record(UL_PAIRING_ROLE_TRANSFER,
                                           package_bytes, read,
                                           package_key) == UL_PAIRING_OK &&
                              constant_equal(created, package_key,
                                             sizeof(created)),
                          "role-2 package contains same capability");
    }
    failures += check(ul_pairing_store_replace(store, NULL, replacement) ==
                          UL_PAIRING_OK &&
                          !key_is_zero(replacement) &&
                          !constant_equal(created, replacement,
                                          sizeof(created)),
                      "explicit replace changes capability");
    failures += check(ul_pairing_store_load(store, loaded) == UL_PAIRING_OK &&
                          constant_equal(replacement, loaded,
                                         sizeof(replacement)),
                      "reload replacement");
    failures += check(ul_pairing_store_forget(store) == UL_PAIRING_OK,
                      "forget valid store");
    failures += check(ul_pairing_store_forget(store) == UL_PAIRING_MISSING,
                      "forget missing is distinct");
    ul_pairing_store_destroy(store);
    failures += cleanup_root(root);
    SecureZeroMemory(created, sizeof(created));
    SecureZeroMemory(loaded, sizeof(loaded));
    SecureZeroMemory(replacement, sizeof(replacement));
    SecureZeroMemory(package_key, sizeof(package_key));
    SecureZeroMemory(package_bytes, sizeof(package_bytes));
    return failures;
}

static int test_cancel_and_faults(void)
{
    wchar_t root[MAX_PATH];
    uint8_t key[UL_PAIRING_KEY_BYTES];
    ul_pairing_store *store = NULL;
    ul_pairing_cancel cancel;
    ul_pairing_result result;
    int failures = 0;

    SecureZeroMemory(root, sizeof(root));
    SecureZeroMemory(key, sizeof(key));
    failures += check(make_root(root), "create fault root");
    if (failures != 0)
        return failures;
    failures += check(ul_pairing_store_open_test_root(root, &store) ==
                          UL_PAIRING_OK,
                      "open fault store");
    if (store == NULL) {
        failures += cleanup_root(root);
        return failures;
    }
    ul_pairing_cancel_init(&cancel);
    cancel_on_flush = &cancel.requested;
    failures += check(ul_pairing_store_create(store, &cancel, key) ==
                          UL_PAIRING_CANCELLED &&
                          key_is_zero(key) &&
                          ul_pairing_store_load(store, key) ==
                              UL_PAIRING_MISSING,
                      "cancel before commit changes no store");
    cancel_on_flush = NULL;

    fail_random = true;
    failures += check(ul_pairing_store_create(store, NULL, key) ==
                          UL_PAIRING_CRYPTO_ERROR &&
                          key_is_zero(key),
                      "random failure");
    fail_random = false;
    fail_protect = true;
    failures += check(ul_pairing_store_create(store, NULL, key) ==
                          UL_PAIRING_CRYPTO_ERROR &&
                          key_is_zero(key),
                      "DPAPI protect failure");
    fail_protect = false;
    fail_write = true;
    failures += check(ul_pairing_store_create(store, NULL, key) ==
                          UL_PAIRING_IO_ERROR &&
                          key_is_zero(key),
                      "write failure leaves no reported key");
    fail_write = false;
    failures += check(ul_pairing_store_load(store, key) == UL_PAIRING_MISSING,
                      "write failure leaves no store");
    partial_write_then_fail = true;
    write_calls = 0u;
    failures += check(ul_pairing_store_create(store, NULL, key) ==
                          UL_PAIRING_IO_ERROR &&
                          write_calls == 2u,
                      "partial write then failure is cleaned up");
    partial_write_then_fail = false;
    failures += check(ul_pairing_store_load(store, key) == UL_PAIRING_MISSING,
                      "partial write failure leaves no store");
    fail_flush = true;
    failures += check(ul_pairing_store_create(store, NULL, key) ==
                          UL_PAIRING_IO_ERROR,
                      "flush failure");
    fail_flush = false;
    fail_move = true;
    failures += check(ul_pairing_store_create(store, NULL, key) ==
                          UL_PAIRING_IO_ERROR,
                      "commit failure");
    fail_move = false;
    failures += check(ul_pairing_store_load(store, key) == UL_PAIRING_MISSING,
                      "commit failure leaves no store");

    fail_unprotect = true;
    result = ul_pairing_store_create(store, NULL, key);
    fail_unprotect = false;
    failures += check(result == UL_PAIRING_POSTCOMMIT_INVALID &&
                          key_is_zero(key),
                      "post-commit verification failure is distinct");
    failures += check(ul_pairing_store_load(store, key) == UL_PAIRING_OK,
                      "post-commit record remains valid on reload");
    fail_delete = true;
    failures += check(ul_pairing_store_forget(store) == UL_PAIRING_IO_ERROR,
                      "forget failure is visible");
    fail_delete = false;
    failures += check(ul_pairing_store_load(store, key) == UL_PAIRING_OK,
                      "failed forget leaves store");
    failures += check(ul_pairing_store_forget(store) == UL_PAIRING_OK,
                      "forget succeeds after fault clears");

    ul_pairing_store_destroy(store);
    failures += cleanup_root(root);
    SecureZeroMemory(key, sizeof(key));
    return failures;
}

static int test_corruption_and_refusal(void)
{
    wchar_t root[MAX_PATH];
    wchar_t path[MAX_PATH];
    uint8_t key[UL_PAIRING_KEY_BYTES];
    ul_pairing_store *store = NULL;
    HANDLE file = INVALID_HANDLE_VALUE;
    DWORD written = 0;
    uint8_t bad = 0;
    int failures = 0;

    SecureZeroMemory(root, sizeof(root));
    SecureZeroMemory(path, sizeof(path));
    SecureZeroMemory(key, sizeof(key));
    failures += check(make_root(root), "create corruption root");
    if (failures != 0)
        return failures;
    failures += check(ul_pairing_store_open_test_root(root, &store) ==
                          UL_PAIRING_OK &&
                          ul_pairing_store_create(store, NULL, key) ==
                              UL_PAIRING_OK,
                      "create corruption fixture");
    if (store == NULL) {
        failures += cleanup_root(root);
        return failures;
    }
    file = CreateFileW(store->store_path, GENERIC_WRITE, 0, NULL, OPEN_EXISTING,
                       FILE_FLAG_OPEN_REPARSE_POINT, NULL);
    failures += check(file != INVALID_HANDLE_VALUE &&
                          WriteFile(file, &bad, 1, &written, NULL) &&
                          written == 1u,
                      "mutate store magic");
    if (file != INVALID_HANDLE_VALUE)
        CloseHandle(file);
    failures += check(ul_pairing_store_load(store, key) ==
                          UL_PAIRING_CORRUPT &&
                          key_is_zero(key),
                      "corrupt store is visible");
    failures += check(ul_pairing_store_replace(store, NULL, key) ==
                          UL_PAIRING_CORRUPT &&
                          key_is_zero(key),
                      "replace refuses corrupt existing store");
    failures += check(ul_pairing_store_export(store, L"relative.pkg", NULL) ==
                          UL_PAIRING_CORRUPT,
                      "export validates authoritative store first");
    failures += check(ul_pairing_store_forget(store) == UL_PAIRING_OK,
                      "forget repairs corrupt state explicitly");
    file = CreateFileW(store->store_path, GENERIC_WRITE, 0, NULL, CREATE_NEW,
                       FILE_ATTRIBUTE_NORMAL, NULL);
    failures += check(file != INVALID_HANDLE_VALUE,
                      "create wrong-DACL store fixture");
    if (file != INVALID_HANDLE_VALUE)
        CloseHandle(file);
    failures += check(ul_pairing_store_load(store, key) ==
                          UL_PAIRING_UNSAFE_SECURITY &&
                          key_is_zero(key),
                      "wrong-DACL store rejected before content");
    failures += check(ul_pairing_store_forget(store) ==
                          UL_PAIRING_UNSAFE_SECURITY,
                      "forget does not silently repair wrong-DACL store");
    DeleteFileW(store->store_path);
    failures += check(ul_pairing_store_create(store, NULL, key) ==
                          UL_PAIRING_OK,
                      "explicit repair can create after forget");
    failures += check(ul_pairing_store_export(store, L"relative.pkg", NULL) ==
                          UL_PAIRING_INVALID_ARGUMENT,
                      "relative export refused");
    swprintf(path, MAX_PATH, L"%ls\\bad:name.pkg", root);
    failures += check(ul_pairing_store_export(store, path, NULL) ==
                          UL_PAIRING_INVALID_ARGUMENT,
                      "ADS export refused");
    swprintf(path, MAX_PATH, L"%ls\\trailing.pkg. ", root);
    failures += check(ul_pairing_store_export(store, path, NULL) ==
                          UL_PAIRING_INVALID_ARGUMENT,
                      "trailing dot-space export refused");
    failures += check(ul_pairing_store_export(
                          store, L"\\\\server\\share\\pairing.pkg", NULL) ==
                          UL_PAIRING_INVALID_ARGUMENT,
                      "UNC export refused");
    ul_pairing_store_forget(store);
    ul_pairing_store_destroy(store);
    failures += cleanup_root(root);

    failures += check(make_root(root), "create wrong-ACL root");
    if (failures != 0)
        return failures;
    swprintf(path, MAX_PATH, L"%ls\\Utterleaf", root);
    failures += check(CreateDirectoryW(path, NULL),
                      "create inherited app directory");
    failures += check(ul_pairing_store_open_test_root(root, &store) ==
                          UL_PAIRING_UNSAFE_SECURITY &&
                          store == NULL,
                      "pre-existing wrong DACL rejected without repair");
    failures += cleanup_root(root);
    SecureZeroMemory(key, sizeof(key));
    return failures;
}

static int test_codec_strictness(void)
{
    uint8_t key[UL_PAIRING_KEY_BYTES];
    uint8_t decoded[UL_PAIRING_KEY_BYTES];
    uint8_t record[UL_PAIRING_MAX_FILE_BYTES + 1u];
    uint8_t original[UL_PAIRING_MAX_FILE_BYTES];
    DATA_BLOB protected_blob;
    DATA_BLOB plaintext_blob;
    DATA_BLOB altered_blob;
    DWORD size = 0;
    DWORD altered_size;
    int failures = 0;

    memset(key, 0x5a, sizeof(key));
    SecureZeroMemory(decoded, sizeof(decoded));
    SecureZeroMemory(record, sizeof(record));
    SecureZeroMemory(original, sizeof(original));
    SecureZeroMemory(&protected_blob, sizeof(protected_blob));
    SecureZeroMemory(&plaintext_blob, sizeof(plaintext_blob));
    SecureZeroMemory(&altered_blob, sizeof(altered_blob));
    failures += check(protect_record(UL_PAIRING_ROLE_TRANSFER, key, original,
                                     &size) == UL_PAIRING_OK,
                      "encode strict role-2 record");
    failures += check(unprotect_record(UL_PAIRING_ROLE_TRANSFER, original, size,
                                       decoded) == UL_PAIRING_OK &&
                          constant_equal(key, decoded, sizeof(key)),
                      "decode strict role-2 record");
    memcpy(record, original, size);
    record[5] = UL_PAIRING_ROLE_NATIVE;
    failures += check(unprotect_record(UL_PAIRING_ROLE_TRANSFER, record, size,
                                       decoded) == UL_PAIRING_CORRUPT,
                      "outer role mismatch rejected");
    memcpy(record, original, size);
    record[6] = 1u;
    failures += check(unprotect_record(UL_PAIRING_ROLE_TRANSFER, record, size,
                                       decoded) == UL_PAIRING_CORRUPT,
                      "reserved byte rejected");
    memcpy(record, original, size);
    store_u32_le(record + 8u, load_u32_le(record + 8u) + 1u);
    failures += check(unprotect_record(UL_PAIRING_ROLE_TRANSFER, record, size,
                                       decoded) == UL_PAIRING_CORRUPT,
                      "declared length mismatch rejected");
    memcpy(record, original, size);
    record[size] = 0u;
    failures += check(unprotect_record(UL_PAIRING_ROLE_TRANSFER, record,
                                       size + 1u, decoded) ==
                          UL_PAIRING_CORRUPT,
                      "trailing data rejected");

    protected_blob.cbData = load_u32_le(original + 8u);
    protected_blob.pbData = original + UL_PAIRING_OUTER_BYTES;
    failures += check(CryptUnprotectData(&protected_blob, NULL, NULL, NULL,
                                         NULL, CRYPTPROTECT_UI_FORBIDDEN,
                                         &plaintext_blob),
                      "unwrap tag mutation fixture");
    if (plaintext_blob.pbData != NULL &&
        plaintext_blob.cbData == UL_PAIRING_INNER_BYTES) {
        plaintext_blob.pbData[40] ^= 1u;
        failures += check(CryptProtectData(&plaintext_blob, NULL, NULL, NULL,
                                           NULL, CRYPTPROTECT_UI_FORBIDDEN,
                                           &altered_blob),
                          "rewrap tag mutation fixture");
    }
    if (altered_blob.pbData != NULL &&
        altered_blob.cbData <= UL_PAIRING_MAX_BLOB_BYTES) {
        altered_size = UL_PAIRING_OUTER_BYTES + altered_blob.cbData;
        memcpy(record, UL_PAIRING_OUTER_MAGIC, 4u);
        record[4] = 1u;
        record[5] = UL_PAIRING_ROLE_TRANSFER;
        record[6] = 0u;
        record[7] = 0u;
        store_u32_le(record + 8u, altered_blob.cbData);
        memcpy(record + UL_PAIRING_OUTER_BYTES, altered_blob.pbData,
               altered_blob.cbData);
        failures += check(unprotect_record(UL_PAIRING_ROLE_TRANSFER, record,
                                           altered_size, decoded) ==
                              UL_PAIRING_CORRUPT &&
                              key_is_zero(decoded),
                          "inner HMAC mismatch rejected");
    } else {
        failures += check(false, "bounded altered DPAPI record");
    }
    if (plaintext_blob.pbData != NULL) {
        SecureZeroMemory(plaintext_blob.pbData, plaintext_blob.cbData);
        LocalFree(plaintext_blob.pbData);
    }
    if (altered_blob.pbData != NULL) {
        SecureZeroMemory(altered_blob.pbData, altered_blob.cbData);
        LocalFree(altered_blob.pbData);
    }
    SecureZeroMemory(key, sizeof(key));
    SecureZeroMemory(decoded, sizeof(decoded));
    SecureZeroMemory(record, sizeof(record));
    SecureZeroMemory(original, sizeof(original));
    return failures;
}

static int test_volume_and_reparse_refusal(void)
{
    wchar_t root[MAX_PATH];
    ul_pairing_store *store = NULL;
    int failures = 0;

    SecureZeroMemory(root, sizeof(root));
    failures += check(make_root(root), "create unsupported-volume root");
    if (failures != 0)
        return failures;
    fake_no_persistent_acls = true;
    failures += check(ul_pairing_store_open_test_root(root, &store) ==
                          UL_PAIRING_UNSUPPORTED &&
                          store == NULL,
                      "volume without persistent ACLs refused");
    fake_no_persistent_acls = false;
    fake_reparse = true;
    failures += check(ul_pairing_store_open_test_root(root, &store) ==
                          UL_PAIRING_UNSUPPORTED &&
                          store == NULL,
                      "reparse ancestor refused");
    fake_reparse = false;
    failures += cleanup_root(root);
    return failures;
}

static int owner_child(void)
{
    wchar_t root[MAX_PATH];
    ul_pairing_store *store = NULL;
    ul_pairing_result result;

    SecureZeroMemory(root, sizeof(root));
    if (GetEnvironmentVariableW(L"UL_PAIRING_OWNER_TEST_ROOT", root,
                                MAX_PATH) == 0)
        return 1;
    result = ul_pairing_store_open_test_root(root, &store);
    if (result != UL_PAIRING_OK || store == NULL)
        return 1;
    result = ul_pairing_store_claim_owner(store);
    ul_pairing_store_destroy(store);
    return result == UL_PAIRING_IN_USE ? 0 : 1;
}

static int test_owner_claim(void)
{
    wchar_t root[MAX_PATH];
    wchar_t executable[MAX_PATH];
    wchar_t command[MAX_PATH + 32];
    STARTUPINFOW startup;
    PROCESS_INFORMATION process;
    ul_pairing_store *store = NULL;
    ul_pairing_store *successor = NULL;
    ul_pairing_store *invalid = NULL;
    HANDLE owner_file = INVALID_HANDLE_VALUE;
    BYTE marker = 1;
    DWORD written = 0;
    DWORD flags = HANDLE_FLAG_INHERIT;
    DWORD exit_code = 1;
    DWORD wait_result;
    int failures = 0;

    SecureZeroMemory(root, sizeof(root));
    SecureZeroMemory(executable, sizeof(executable));
    SecureZeroMemory(command, sizeof(command));
    SecureZeroMemory(&startup, sizeof(startup));
    SecureZeroMemory(&process, sizeof(process));
    startup.cb = sizeof(startup);
    failures += check(make_root(root), "create owner root");
    if (failures != 0)
        return failures;
    failures += check(ul_pairing_store_open_test_root(root, &store) ==
                          UL_PAIRING_OK &&
                          store != NULL,
                      "open owner store");
    if (store == NULL) {
        failures += cleanup_root(root);
        return failures;
    }
    failures += check(ul_pairing_store_claim_owner(store) == UL_PAIRING_OK,
                      "claim owner");
    failures += check(ul_pairing_store_claim_owner(store) == UL_PAIRING_OK,
                      "owner claim idempotent");
    failures += check(store->owner != INVALID_HANDLE_VALUE &&
                          verify_private_security(store->owner,
                                                  store->user_sid) ==
                              UL_PAIRING_OK,
                      "owner lock private ACL");
    failures += check(GetHandleInformation(store->owner, &flags) &&
                          (flags & HANDLE_FLAG_INHERIT) == 0,
                      "owner lock handle noninheritable");
    failures += check(GetModuleFileNameW(NULL, executable, MAX_PATH) > 0,
                      "locate owner test executable");
    failures += check(SetEnvironmentVariableW(L"UL_PAIRING_OWNER_TEST_ROOT",
                                               root),
                      "publish owner child root");
    if (_snwprintf(command, MAX_PATH + 32, L"\"%ls\" --owner-child",
                   executable) < 0)
        failures += check(false, "build owner child command");
    if (failures == 0)
        failures += check(CreateProcessW(executable, command, NULL, NULL,
                                         FALSE, 0, NULL, NULL, &startup,
                                         &process),
                          "start competing owner process");
    (void)SetEnvironmentVariableW(L"UL_PAIRING_OWNER_TEST_ROOT", NULL);
    if (process.hProcess != NULL) {
        wait_result = WaitForSingleObject(process.hProcess, 5000);
        if (wait_result != WAIT_OBJECT_0)
            ExitProcess(1);
        failures += check(GetExitCodeProcess(process.hProcess, &exit_code) &&
                              exit_code == 0,
                          "other process observes store in use");
        CloseHandle(process.hThread);
        CloseHandle(process.hProcess);
    }
    ul_pairing_store_destroy(store);
    store = NULL;
    failures += check(ul_pairing_store_open_test_root(root, &successor) ==
                          UL_PAIRING_OK &&
                          successor != NULL &&
                          ul_pairing_store_claim_owner(successor) ==
                              UL_PAIRING_OK,
                      "owner released at destroy");
    ul_pairing_store_destroy(successor);
    successor = NULL;
    swprintf(command, MAX_PATH + 32,
             L"%ls\\Utterleaf\\obs-plugin\\owner-v1.lock", root);
    owner_file = CreateFileW(command, GENERIC_WRITE, 0, NULL, OPEN_EXISTING,
                             FILE_ATTRIBUTE_NORMAL |
                                 FILE_FLAG_OPEN_REPARSE_POINT,
                             NULL);
    failures += check(owner_file != INVALID_HANDLE_VALUE &&
                          WriteFile(owner_file, &marker, sizeof(marker),
                                    &written, NULL) &&
                          written == sizeof(marker),
                      "make invalid nonempty owner file");
    if (owner_file != INVALID_HANDLE_VALUE)
        CloseHandle(owner_file);
    failures += check(ul_pairing_store_open_test_root(root, &invalid) ==
                          UL_PAIRING_OK &&
                          invalid != NULL &&
                          ul_pairing_store_claim_owner(invalid) ==
                              UL_PAIRING_UNSAFE_SECURITY,
                      "nonempty owner file refused");
    ul_pairing_store_destroy(invalid);
    failures += cleanup_root(root);
    return failures;
}

int main(int argc, char **argv)
{
    int failures = 0;

    if (argc == 2 && strcmp(argv[1], "--owner-child") == 0)
        return owner_child();
    failures += test_round_trip_and_security();
    failures += test_cancel_and_faults();
    failures += test_corruption_and_refusal();
    failures += test_codec_strictness();
    failures += test_volume_and_reparse_refusal();
    failures += test_owner_claim();
    if (failures == 0)
        puts("pairing store tests passed");
    return failures == 0 ? 0 : 1;
}
