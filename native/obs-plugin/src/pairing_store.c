// SPDX-License-Identifier: GPL-2.0-or-later
#include "pairing_store.h"

#include "crypto.h"

#include <aclapi.h>
#include <bcrypt.h>
#include <dpapi.h>
#include <shlobj.h>

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <wchar.h>
#include <wctype.h>

#define UL_PAIRING_ROLE_NATIVE 1u
#define UL_PAIRING_ROLE_TRANSFER 2u
#define UL_PAIRING_OUTER_BYTES 12u
#define UL_PAIRING_INNER_BYTES 72u
#define UL_PAIRING_MAX_BLOB_BYTES 4096u
#define UL_PAIRING_MAX_PATH_CHARS 1024u
#define UL_PAIRING_MAX_COMPONENTS 64u
#define UL_PAIRING_MAX_SID_BYTES 256u
#define UL_PAIRING_TEMP_ATTEMPTS 8u

static const uint8_t UL_PAIRING_DOMAIN[] =
    "Utterleaf OBS pairing package integrity v1";
static const uint8_t UL_PAIRING_OUTER_MAGIC[4] = {'U', 'L', 'P', 'K'};
static const uint8_t UL_PAIRING_INNER_MAGIC[4] = {'U', 'L', 'K', 'I'};

typedef struct ul_handle_set {
    HANDLE handles[UL_PAIRING_MAX_COMPONENTS];
    size_t count;
} ul_handle_set;

typedef struct ul_private_security {
    SECURITY_DESCRIPTOR descriptor;
    PACL acl;
    DWORD acl_size;
    SECURITY_ATTRIBUTES attributes;
} ul_private_security;

struct ul_pairing_store {
    SRWLOCK lock;
    PSID user_sid;
    DWORD user_sid_size;
    ul_handle_set directories;
    wchar_t directory[UL_PAIRING_MAX_PATH_CHARS];
    wchar_t store_path[UL_PAIRING_MAX_PATH_CHARS];
};

static void wipe_free(void *memory, SIZE_T size)
{
    if (memory != NULL) {
        SecureZeroMemory(memory, size);
        HeapFree(GetProcessHeap(), 0, memory);
    }
}

static bool bytes_are_zero(const uint8_t *bytes, size_t size)
{
    uint8_t aggregate = 0;
    size_t index;

    for (index = 0; index < size; ++index)
        aggregate |= bytes[index];
    return aggregate == 0u;
}

static bool constant_equal(const uint8_t *left, const uint8_t *right,
                           size_t size)
{
    volatile uint8_t different = 0;
    size_t index;

    for (index = 0; index < size; ++index)
        different |= (uint8_t)(left[index] ^ right[index]);
    return different == 0u;
}

static void store_u32_le(uint8_t output[4], DWORD value)
{
    output[0] = (uint8_t)value;
    output[1] = (uint8_t)(value >> 8);
    output[2] = (uint8_t)(value >> 16);
    output[3] = (uint8_t)(value >> 24);
}

static DWORD load_u32_le(const uint8_t input[4])
{
    return (DWORD)input[0] | ((DWORD)input[1] << 8) |
           ((DWORD)input[2] << 16) | ((DWORD)input[3] << 24);
}

static void handles_close(ul_handle_set *set)
{
    while (set->count > 0u) {
        --set->count;
        CloseHandle(set->handles[set->count]);
        set->handles[set->count] = INVALID_HANDLE_VALUE;
    }
}

static bool handles_add(ul_handle_set *set, HANDLE handle)
{
    if (set->count >= UL_PAIRING_MAX_COMPONENTS)
        return false;
    set->handles[set->count++] = handle;
    return true;
}

static bool bounded_token_user(PSID *sid_out, DWORD *sid_size_out)
{
    HANDLE token = NULL;
    void *buffer = NULL;
    DWORD needed = 0;
    DWORD returned = 0;
    TOKEN_USER *user;
    uintptr_t begin;
    uintptr_t candidate;
    const uint8_t *sid_bytes;
    DWORD offset;
    DWORD sid_size = 0;
    PSID copy = NULL;
    bool success = false;

    *sid_out = NULL;
    *sid_size_out = 0;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token))
        goto cleanup;
    if (GetTokenInformation(token, TokenUser, NULL, 0, &needed) ||
        GetLastError() != ERROR_INSUFFICIENT_BUFFER || needed < sizeof(TOKEN_USER) ||
        needed > 4096u)
        goto cleanup;
    buffer = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, needed);
    if (buffer == NULL)
        goto cleanup;
    if (!GetTokenInformation(token, TokenUser, buffer, needed, &returned) ||
        returned < sizeof(TOKEN_USER) || returned > needed)
        goto cleanup;
    user = (TOKEN_USER *)buffer;
    begin = (uintptr_t)buffer;
    candidate = (uintptr_t)user->User.Sid;
    if (user->User.Sid == NULL || candidate < begin ||
        candidate - begin > returned - 8u)
        goto cleanup;
    offset = (DWORD)(candidate - begin);
    sid_bytes = (const uint8_t *)user->User.Sid;
    if (sid_bytes[0] != SID_REVISION ||
        sid_bytes[1] > SID_MAX_SUB_AUTHORITIES)
        goto cleanup;
    sid_size = 8u + ((DWORD)sid_bytes[1] * sizeof(DWORD));
    if (sid_size > UL_PAIRING_MAX_SID_BYTES || sid_size > returned - offset ||
        !IsValidSid(user->User.Sid) ||
        GetLengthSid(user->User.Sid) != sid_size)
        goto cleanup;
    copy = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sid_size);
    if (copy == NULL || !CopySid(sid_size, copy, user->User.Sid))
        goto cleanup;
    *sid_out = copy;
    *sid_size_out = sid_size;
    copy = NULL;
    success = true;

cleanup:
    wipe_free(copy, sid_size);
    wipe_free(buffer, needed);
    if (token != NULL)
        CloseHandle(token);
    return success;
}

static bool private_security_init(PSID sid, DWORD sid_size,
                                  ul_private_security *security)
{
    SIZE_T needed;

    SecureZeroMemory(security, sizeof(*security));
    if (sid == NULL || sid_size < 8u || sid_size > UL_PAIRING_MAX_SID_BYTES)
        return false;
    needed = sizeof(ACL) + sizeof(ACCESS_ALLOWED_ACE) - sizeof(DWORD) + sid_size;
    if (needed > 1024u)
        return false;
    security->acl = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, needed);
    if (security->acl == NULL)
        return false;
    security->acl_size = (DWORD)needed;
    if (!InitializeAcl(security->acl, security->acl_size, ACL_REVISION) ||
        !AddAccessAllowedAceEx(security->acl, ACL_REVISION, 0,
                               FILE_ALL_ACCESS, sid) ||
        !InitializeSecurityDescriptor(&security->descriptor,
                                      SECURITY_DESCRIPTOR_REVISION) ||
        !SetSecurityDescriptorOwner(&security->descriptor, sid, FALSE) ||
        !SetSecurityDescriptorDacl(&security->descriptor, TRUE, security->acl,
                                   FALSE) ||
        !SetSecurityDescriptorControl(&security->descriptor,
                                      SE_DACL_PROTECTED,
                                      SE_DACL_PROTECTED)) {
        wipe_free(security->acl, security->acl_size);
        SecureZeroMemory(security, sizeof(*security));
        return false;
    }
    security->attributes.nLength = sizeof(security->attributes);
    security->attributes.lpSecurityDescriptor = &security->descriptor;
    security->attributes.bInheritHandle = FALSE;
    return true;
}

static void private_security_clear(ul_private_security *security)
{
    wipe_free(security->acl, security->acl_size);
    SecureZeroMemory(security, sizeof(*security));
}

static ul_pairing_result verify_private_security(HANDLE handle, PSID sid)
{
    PSID owner = NULL;
    PACL dacl = NULL;
    PSECURITY_DESCRIPTOR descriptor = NULL;
    SECURITY_DESCRIPTOR_CONTROL control = 0;
    DWORD revision = 0;
    ACL_SIZE_INFORMATION information;
    void *raw_ace = NULL;
    ACCESS_ALLOWED_ACE *ace;
    DWORD error;
    ul_pairing_result result = UL_PAIRING_UNSAFE_SECURITY;

    SecureZeroMemory(&information, sizeof(information));
    error = GetSecurityInfo(handle, SE_FILE_OBJECT,
                            OWNER_SECURITY_INFORMATION |
                                DACL_SECURITY_INFORMATION,
                            &owner, NULL, &dacl, NULL, &descriptor);
    if (error != ERROR_SUCCESS)
        return UL_PAIRING_IO_ERROR;
    if (owner == NULL || !IsValidSid(owner) || !EqualSid(owner, sid) ||
        dacl == NULL || !IsValidAcl(dacl) ||
        !GetSecurityDescriptorControl(descriptor, &control, &revision) ||
        (control & SE_DACL_PROTECTED) == 0u ||
        !GetAclInformation(dacl, &information, sizeof(information),
                           AclSizeInformation) ||
        information.AceCount != 1u || !GetAce(dacl, 0, &raw_ace))
        goto cleanup;
    ace = (ACCESS_ALLOWED_ACE *)raw_ace;
    if (ace->Header.AceType != ACCESS_ALLOWED_ACE_TYPE ||
        ace->Header.AceFlags != 0u || ace->Mask != FILE_ALL_ACCESS ||
        !IsValidSid((PSID)&ace->SidStart) ||
        !EqualSid((PSID)&ace->SidStart, sid))
        goto cleanup;
    result = UL_PAIRING_OK;

cleanup:
    if (descriptor != NULL)
        LocalFree(descriptor);
    return result;
}

static bool reserved_component(const wchar_t *component, size_t length)
{
    wchar_t base[8];
    size_t base_length = 0;
    size_t index;

    while (base_length < length && component[base_length] != L'.' &&
           base_length + 1u < sizeof(base) / sizeof(base[0])) {
        base[base_length] = towupper(component[base_length]);
        ++base_length;
    }
    base[base_length] = L'\0';
    if (wcscmp(base, L"CON") == 0 || wcscmp(base, L"PRN") == 0 ||
        wcscmp(base, L"AUX") == 0 || wcscmp(base, L"NUL") == 0)
        return true;
    if (base_length == 4u &&
        ((wcsncmp(base, L"COM", 3u) == 0) ||
         (wcsncmp(base, L"LPT", 3u) == 0)) &&
        base[3] >= L'1' && base[3] <= L'9')
        return true;
    for (index = 0; index < length; ++index) {
        wchar_t value = component[index];
        if (value < 32 || value == L'<' || value == L'>' || value == L'"' ||
            value == L'|' || value == L'?' || value == L'*' || value == L':')
            return true;
    }
    return false;
}

static bool normalize_absolute_path(const wchar_t *input, bool directory,
                                    wchar_t output[UL_PAIRING_MAX_PATH_CHARS])
{
    wchar_t original[UL_PAIRING_MAX_PATH_CHARS];
    wchar_t full[UL_PAIRING_MAX_PATH_CHARS];
    size_t length = 0;
    size_t start;
    size_t index;
    DWORD result;

    if (input == NULL || !iswalpha(input[0]) || input[1] != L':' ||
        input[2] != L'\\')
        return false;
    while (length < UL_PAIRING_MAX_PATH_CHARS && input[length] != L'\0')
        ++length;
    if (length < 3u || length >= UL_PAIRING_MAX_PATH_CHARS)
        return false;
    memcpy(original, input, (length + 1u) * sizeof(wchar_t));
    if (directory) {
        while (length > 3u && original[length - 1u] == L'\\')
            original[--length] = L'\0';
    } else if (original[length - 1u] == L'\\') {
        return false;
    }
    if (length == 3u) {
        if (!directory)
            return false;
        memcpy(full, original, 4u * sizeof(wchar_t));
        if (swprintf(output, UL_PAIRING_MAX_PATH_CHARS, L"\\\\?\\%ls",
                     full) < 0)
            return false;
        return true;
    }
    start = 3u;
    for (index = 3u; index <= length; ++index) {
        if (original[index] == L'/')
            return false;
        if (original[index] == L'\\' || original[index] == L'\0') {
            size_t component_length = index - start;
            if (component_length == 0u || component_length > 255u ||
                (component_length == 1u && original[start] == L'.') ||
                (component_length == 2u && original[start] == L'.' &&
                 original[start + 1u] == L'.') ||
                original[index - 1u] == L'.' ||
                original[index - 1u] == L' ' ||
                reserved_component(original + start, component_length))
                return false;
            start = index + 1u;
        }
    }
    result = GetFullPathNameW(original, UL_PAIRING_MAX_PATH_CHARS, full, NULL);
    if (result == 0u || result >= UL_PAIRING_MAX_PATH_CHARS ||
        _wcsicmp(original, full) != 0)
        return false;
    if (wcslen(full) > UL_PAIRING_MAX_PATH_CHARS - 5u ||
        swprintf(output, UL_PAIRING_MAX_PATH_CHARS, L"\\\\?\\%ls", full) < 0)
        return false;
    return true;
}

static bool get_final_path(HANDLE handle,
                           wchar_t output[UL_PAIRING_MAX_PATH_CHARS])
{
    DWORD length = GetFinalPathNameByHandleW(
        handle, output, UL_PAIRING_MAX_PATH_CHARS,
        FILE_NAME_NORMALIZED | VOLUME_NAME_DOS);

    return length >= 7u && length < UL_PAIRING_MAX_PATH_CHARS &&
           wcsncmp(output, L"\\\\?\\", 4u) == 0 &&
           iswalpha(output[4]) && output[5] == L':' && output[6] == L'\\';
}

static ul_pairing_result validate_disk_object(
    HANDLE handle, const wchar_t *expected, bool directory, bool check_volume)
{
    FILE_ATTRIBUTE_TAG_INFO attributes;
    wchar_t final_path[UL_PAIRING_MAX_PATH_CHARS];
    DWORD flags = 0;

    SecureZeroMemory(&attributes, sizeof(attributes));
    SecureZeroMemory(final_path, sizeof(final_path));
    if (GetFileType(handle) != FILE_TYPE_DISK ||
        !GetFileInformationByHandleEx(handle, FileAttributeTagInfo, &attributes,
                                      sizeof(attributes)) ||
        ((attributes.FileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0u) !=
            directory ||
        (attributes.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0u ||
        !get_final_path(handle, final_path) ||
        _wcsicmp(final_path, expected) != 0)
        return UL_PAIRING_UNSUPPORTED;
    if (check_volume &&
        (!GetVolumeInformationByHandleW(handle, NULL, 0, NULL, NULL, &flags,
                                        NULL, 0) ||
         (flags & FILE_PERSISTENT_ACLS) == 0u))
        return UL_PAIRING_UNSUPPORTED;
    return UL_PAIRING_OK;
}

static ul_pairing_result open_directory_component(const wchar_t *path,
                                                  bool check_volume,
                                                  HANDLE *handle_out)
{
    HANDLE handle = CreateFileW(
        path, FILE_READ_ATTRIBUTES | READ_CONTROL,
        FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, NULL);
    ul_pairing_result result;

    *handle_out = INVALID_HANDLE_VALUE;
    if (handle == INVALID_HANDLE_VALUE)
        return UL_PAIRING_IO_ERROR;
    result = validate_disk_object(handle, path, true, check_volume);
    if (result != UL_PAIRING_OK) {
        CloseHandle(handle);
        return result;
    }
    *handle_out = handle;
    return UL_PAIRING_OK;
}

static ul_pairing_result walk_directory(
    const wchar_t *input, ul_handle_set *handles,
    wchar_t final_path[UL_PAIRING_MAX_PATH_CHARS])
{
    wchar_t normalized[UL_PAIRING_MAX_PATH_CHARS];
    wchar_t current[UL_PAIRING_MAX_PATH_CHARS];
    size_t length;
    size_t component_start;
    size_t index;
    HANDLE handle;
    ul_pairing_result result;

    SecureZeroMemory(normalized, sizeof(normalized));
    SecureZeroMemory(current, sizeof(current));
    if (!normalize_absolute_path(input, true, normalized))
        return UL_PAIRING_INVALID_ARGUMENT;
    memcpy(current, normalized, 7u * sizeof(wchar_t));
    current[7] = L'\0';
    result = open_directory_component(current, true, &handle);
    if (result != UL_PAIRING_OK)
        return result;
    if (!handles_add(handles, handle)) {
        CloseHandle(handle);
        return UL_PAIRING_UNSUPPORTED;
    }
    length = wcslen(normalized);
    component_start = 7u;
    for (index = 7u; index <= length; ++index) {
        if (normalized[index] == L'\\' || normalized[index] == L'\0') {
            if (index == component_start) {
                component_start = index + 1u;
                continue;
            }
            current[index] = L'\0';
            memcpy(current + component_start, normalized + component_start,
                   (index - component_start) * sizeof(wchar_t));
            result = open_directory_component(current, false, &handle);
            if (result != UL_PAIRING_OK)
                return result;
            if (!handles_add(handles, handle)) {
                CloseHandle(handle);
                return UL_PAIRING_UNSUPPORTED;
            }
            if (normalized[index] == L'\\')
                current[index] = L'\\';
            component_start = index + 1u;
        }
    }
    memcpy(final_path, normalized, (length + 1u) * sizeof(wchar_t));
    return UL_PAIRING_OK;
}

static bool join_path(const wchar_t *parent, const wchar_t *child,
                      wchar_t output[UL_PAIRING_MAX_PATH_CHARS])
{
    size_t parent_length = wcslen(parent);
    size_t child_length = wcslen(child);
    bool separator = parent_length > 0u && parent[parent_length - 1u] != L'\\';
    size_t total = parent_length + (separator ? 1u : 0u) + child_length;

    if (total >= UL_PAIRING_MAX_PATH_CHARS)
        return false;
    memcpy(output, parent, parent_length * sizeof(wchar_t));
    if (separator)
        output[parent_length++] = L'\\';
    memcpy(output + parent_length, child, (child_length + 1u) * sizeof(wchar_t));
    return true;
}

static ul_pairing_result ensure_private_directory(
    ul_handle_set *handles, const wchar_t *parent, const wchar_t *name,
    PSID sid, DWORD sid_size, wchar_t output[UL_PAIRING_MAX_PATH_CHARS])
{
    ul_private_security security;
    HANDLE handle = INVALID_HANDLE_VALUE;
    ul_pairing_result result;
    DWORD error;

    if (!join_path(parent, name, output) ||
        !private_security_init(sid, sid_size, &security))
        return UL_PAIRING_IO_ERROR;
    if (!CreateDirectoryW(output, &security.attributes)) {
        error = GetLastError();
        if (error != ERROR_ALREADY_EXISTS) {
            private_security_clear(&security);
            return UL_PAIRING_IO_ERROR;
        }
    }
    private_security_clear(&security);
    result = open_directory_component(output, false, &handle);
    if (result != UL_PAIRING_OK)
        return result;
    result = verify_private_security(handle, sid);
    if (result != UL_PAIRING_OK) {
        CloseHandle(handle);
        return result;
    }
    if (!handles_add(handles, handle)) {
        CloseHandle(handle);
        return UL_PAIRING_UNSUPPORTED;
    }
    return UL_PAIRING_OK;
}

static ul_pairing_result protect_record(
    uint8_t role, const uint8_t key[UL_PAIRING_KEY_BYTES],
    uint8_t output[UL_PAIRING_MAX_FILE_BYTES], DWORD *output_size)
{
    uint8_t plaintext[UL_PAIRING_INNER_BYTES];
    DATA_BLOB input_blob;
    DATA_BLOB protected_blob;
    bool hmac_ok = false;
    ul_pairing_result result = UL_PAIRING_CRYPTO_ERROR;

    SecureZeroMemory(output, UL_PAIRING_MAX_FILE_BYTES);
    *output_size = 0;
    SecureZeroMemory(plaintext, sizeof(plaintext));
    SecureZeroMemory(&input_blob, sizeof(input_blob));
    SecureZeroMemory(&protected_blob, sizeof(protected_blob));
    if ((role != UL_PAIRING_ROLE_NATIVE && role != UL_PAIRING_ROLE_TRANSFER) ||
        key == NULL || bytes_are_zero(key, UL_PAIRING_KEY_BYTES))
        return UL_PAIRING_INVALID_ARGUMENT;
    memcpy(plaintext, UL_PAIRING_INNER_MAGIC, sizeof(UL_PAIRING_INNER_MAGIC));
    plaintext[4] = 1u;
    plaintext[5] = role;
    memcpy(plaintext + 8u, key, UL_PAIRING_KEY_BYTES);
    hmac_ok = ul_hmac_sha256(key, UL_PAIRING_DOMAIN,
                             sizeof(UL_PAIRING_DOMAIN), plaintext, 40u,
                             plaintext + 40u);
    if (!hmac_ok)
        goto cleanup;
    input_blob.cbData = sizeof(plaintext);
    input_blob.pbData = plaintext;
    if (!CryptProtectData(&input_blob, NULL, NULL, NULL, NULL,
                          CRYPTPROTECT_UI_FORBIDDEN, &protected_blob) ||
        protected_blob.pbData == NULL || protected_blob.cbData < 1u ||
        protected_blob.cbData > UL_PAIRING_MAX_BLOB_BYTES)
        goto cleanup;
    memcpy(output, UL_PAIRING_OUTER_MAGIC, sizeof(UL_PAIRING_OUTER_MAGIC));
    output[4] = 1u;
    output[5] = role;
    store_u32_le(output + 8u, protected_blob.cbData);
    memcpy(output + UL_PAIRING_OUTER_BYTES, protected_blob.pbData,
           protected_blob.cbData);
    *output_size = UL_PAIRING_OUTER_BYTES + protected_blob.cbData;
    result = UL_PAIRING_OK;

cleanup:
    SecureZeroMemory(plaintext, sizeof(plaintext));
    if (protected_blob.pbData != NULL) {
        SecureZeroMemory(protected_blob.pbData, protected_blob.cbData);
        LocalFree(protected_blob.pbData);
    }
    if (result != UL_PAIRING_OK) {
        SecureZeroMemory(output, UL_PAIRING_MAX_FILE_BYTES);
        *output_size = 0;
    }
    return result;
}

static ul_pairing_result unprotect_record(
    uint8_t expected_role, const uint8_t *input, DWORD input_size,
    uint8_t key[UL_PAIRING_KEY_BYTES])
{
    DATA_BLOB protected_blob;
    DATA_BLOB plaintext_blob;
    uint8_t expected_tag[32];
    DWORD protected_size;
    ul_pairing_result result = UL_PAIRING_CORRUPT;

    SecureZeroMemory(key, UL_PAIRING_KEY_BYTES);
    SecureZeroMemory(&protected_blob, sizeof(protected_blob));
    SecureZeroMemory(&plaintext_blob, sizeof(plaintext_blob));
    SecureZeroMemory(expected_tag, sizeof(expected_tag));
    if ((expected_role != UL_PAIRING_ROLE_NATIVE &&
         expected_role != UL_PAIRING_ROLE_TRANSFER) ||
        input == NULL || input_size < UL_PAIRING_OUTER_BYTES + 1u ||
        input_size > UL_PAIRING_MAX_FILE_BYTES)
        return UL_PAIRING_CORRUPT;
    protected_size = load_u32_le(input + 8u);
    if (memcmp(input, UL_PAIRING_OUTER_MAGIC, 4u) != 0 || input[4] != 1u ||
        input[5] != expected_role || input[6] != 0u || input[7] != 0u ||
        protected_size < 1u || protected_size > UL_PAIRING_MAX_BLOB_BYTES ||
        input_size != UL_PAIRING_OUTER_BYTES + protected_size)
        return UL_PAIRING_CORRUPT;
    protected_blob.cbData = protected_size;
    protected_blob.pbData = (BYTE *)(uintptr_t)(input + UL_PAIRING_OUTER_BYTES);
    if (!CryptUnprotectData(&protected_blob, NULL, NULL, NULL, NULL,
                            CRYPTPROTECT_UI_FORBIDDEN, &plaintext_blob)) {
        result = UL_PAIRING_CRYPTO_ERROR;
        goto cleanup;
    }
    if (plaintext_blob.pbData == NULL ||
        plaintext_blob.cbData != UL_PAIRING_INNER_BYTES ||
        memcmp(plaintext_blob.pbData, UL_PAIRING_INNER_MAGIC, 4u) != 0 ||
        plaintext_blob.pbData[4] != 1u ||
        plaintext_blob.pbData[5] != expected_role ||
        plaintext_blob.pbData[6] != 0u || plaintext_blob.pbData[7] != 0u ||
        bytes_are_zero(plaintext_blob.pbData + 8u, UL_PAIRING_KEY_BYTES))
        goto cleanup;
    if (!ul_hmac_sha256(plaintext_blob.pbData + 8u, UL_PAIRING_DOMAIN,
                        sizeof(UL_PAIRING_DOMAIN), plaintext_blob.pbData, 40u,
                        expected_tag)) {
        result = UL_PAIRING_CRYPTO_ERROR;
        goto cleanup;
    }
    if (!constant_equal(expected_tag, plaintext_blob.pbData + 40u, 32u))
        goto cleanup;
    memcpy(key, plaintext_blob.pbData + 8u, UL_PAIRING_KEY_BYTES);
    result = UL_PAIRING_OK;

cleanup:
    SecureZeroMemory(expected_tag, sizeof(expected_tag));
    if (plaintext_blob.pbData != NULL) {
        SecureZeroMemory(plaintext_blob.pbData, plaintext_blob.cbData);
        LocalFree(plaintext_blob.pbData);
    }
    if (result != UL_PAIRING_OK)
        SecureZeroMemory(key, UL_PAIRING_KEY_BYTES);
    return result;
}

static ul_pairing_result open_verified_file(const wchar_t *path, PSID sid,
                                            DWORD access, DWORD sharing,
                                            HANDLE *handle_out)
{
    HANDLE handle;
    ul_pairing_result result;
    DWORD error;

    *handle_out = INVALID_HANDLE_VALUE;
    handle = CreateFileW(path, access | FILE_READ_ATTRIBUTES | READ_CONTROL,
                         sharing, NULL, OPEN_EXISTING,
                         FILE_FLAG_OPEN_REPARSE_POINT, NULL);
    if (handle == INVALID_HANDLE_VALUE) {
        error = GetLastError();
        if (error == ERROR_FILE_NOT_FOUND || error == ERROR_PATH_NOT_FOUND)
            return UL_PAIRING_MISSING;
        return UL_PAIRING_IO_ERROR;
    }
    result = validate_disk_object(handle, path, false, false);
    if (result == UL_PAIRING_OK)
        result = verify_private_security(handle, sid);
    if (result != UL_PAIRING_OK) {
        CloseHandle(handle);
        return result;
    }
    *handle_out = handle;
    return UL_PAIRING_OK;
}

static ul_pairing_result read_record(const wchar_t *path, PSID sid,
                                     uint8_t role,
                                     uint8_t key[UL_PAIRING_KEY_BYTES])
{
    HANDLE file = INVALID_HANDLE_VALUE;
    LARGE_INTEGER size;
    uint8_t buffer[UL_PAIRING_MAX_FILE_BYTES];
    DWORD offset = 0;
    DWORD read = 0;
    ul_pairing_result result;

    SecureZeroMemory(key, UL_PAIRING_KEY_BYTES);
    SecureZeroMemory(buffer, sizeof(buffer));
    SecureZeroMemory(&size, sizeof(size));
    result = open_verified_file(path, sid, GENERIC_READ, 0, &file);
    if (result != UL_PAIRING_OK)
        goto cleanup;
    if (!GetFileSizeEx(file, &size) || size.QuadPart < 13 ||
        size.QuadPart > UL_PAIRING_MAX_FILE_BYTES) {
        result = UL_PAIRING_CORRUPT;
        goto cleanup;
    }
    while (offset < (DWORD)size.QuadPart) {
        if (!ReadFile(file, buffer + offset, (DWORD)size.QuadPart - offset,
                      &read, NULL) || read == 0u) {
            result = UL_PAIRING_IO_ERROR;
            goto cleanup;
        }
        offset += read;
    }
    result = unprotect_record(role, buffer, offset, key);

cleanup:
    if (file != INVALID_HANDLE_VALUE)
        CloseHandle(file);
    SecureZeroMemory(buffer, sizeof(buffer));
    if (result != UL_PAIRING_OK)
        SecureZeroMemory(key, UL_PAIRING_KEY_BYTES);
    return result;
}

static bool cancel_claim_commit(const ul_pairing_cancel *cancel)
{
    volatile LONG *state;

    if (cancel == NULL)
        return true;
    state = (volatile LONG *)(uintptr_t)&cancel->requested;
    return InterlockedCompareExchange(state, 2, 0) == 0;
}

static bool cancel_is_requested(const ul_pairing_cancel *cancel)
{
    volatile LONG *state;

    if (cancel == NULL)
        return false;
    state = (volatile LONG *)(uintptr_t)&cancel->requested;
    return InterlockedCompareExchange(state, 0, 0) == 1;
}

static bool random_bytes(uint8_t *output, ULONG size)
{
    return BCryptGenRandom(NULL, output, size,
                           BCRYPT_USE_SYSTEM_PREFERRED_RNG) == 0;
}

static bool make_temp_path(const wchar_t *directory,
                           wchar_t output[UL_PAIRING_MAX_PATH_CHARS])
{
    static const wchar_t hex[] = L"0123456789abcdef";
    uint8_t random[16];
    wchar_t name[64];
    size_t index;
    bool success = false;

    SecureZeroMemory(random, sizeof(random));
    SecureZeroMemory(name, sizeof(name));
    if (!random_bytes(random, sizeof(random)))
        goto cleanup;
    memcpy(name, L".utterleaf-pairing-", 19u * sizeof(wchar_t));
    for (index = 0; index < sizeof(random); ++index) {
        name[19u + index * 2u] = hex[random[index] >> 4];
        name[20u + index * 2u] = hex[random[index] & 0x0fu];
    }
    memcpy(name + 51u, L".tmp", 5u * sizeof(wchar_t));
    success = join_path(directory, name, output);

cleanup:
    SecureZeroMemory(random, sizeof(random));
    SecureZeroMemory(name, sizeof(name));
    return success;
}

static ul_pairing_result create_temp_file(
    const wchar_t *directory, PSID sid, DWORD sid_size,
    wchar_t path[UL_PAIRING_MAX_PATH_CHARS], HANDLE *file_out)
{
    ul_private_security security;
    HANDLE file = INVALID_HANDLE_VALUE;
    ul_pairing_result result = UL_PAIRING_IO_ERROR;
    unsigned int attempt;

    *file_out = INVALID_HANDLE_VALUE;
    if (!private_security_init(sid, sid_size, &security))
        return UL_PAIRING_IO_ERROR;
    for (attempt = 0; attempt < UL_PAIRING_TEMP_ATTEMPTS; ++attempt) {
        if (!make_temp_path(directory, path)) {
            result = UL_PAIRING_CRYPTO_ERROR;
            break;
        }
        file = CreateFileW(
            path, GENERIC_READ | GENERIC_WRITE | READ_CONTROL, 0,
            &security.attributes, CREATE_NEW,
            FILE_ATTRIBUTE_TEMPORARY | FILE_FLAG_WRITE_THROUGH |
                FILE_FLAG_OPEN_REPARSE_POINT,
            NULL);
        if (file != INVALID_HANDLE_VALUE)
            break;
        if (GetLastError() != ERROR_FILE_EXISTS &&
            GetLastError() != ERROR_ALREADY_EXISTS)
            break;
    }
    private_security_clear(&security);
    if (file == INVALID_HANDLE_VALUE)
        return result;
    result = validate_disk_object(file, path, false, false);
    if (result == UL_PAIRING_OK)
        result = verify_private_security(file, sid);
    if (result != UL_PAIRING_OK) {
        CloseHandle(file);
        DeleteFileW(path);
        return result;
    }
    *file_out = file;
    return UL_PAIRING_OK;
}

static ul_pairing_result write_record(
    const wchar_t *directory, const wchar_t *destination, PSID sid,
    DWORD sid_size, bool replace, uint8_t role,
    const uint8_t key[UL_PAIRING_KEY_BYTES], const ul_pairing_cancel *cancel)
{
    uint8_t buffer[UL_PAIRING_MAX_FILE_BYTES];
    DWORD buffer_size = 0;
    DWORD offset = 0;
    DWORD written = 0;
    wchar_t temp_path[UL_PAIRING_MAX_PATH_CHARS];
    HANDLE temp = INVALID_HANDLE_VALUE;
    uint8_t verified_key[UL_PAIRING_KEY_BYTES];
    ul_pairing_result result;
    DWORD move_flags = MOVEFILE_WRITE_THROUGH;

    SecureZeroMemory(buffer, sizeof(buffer));
    SecureZeroMemory(temp_path, sizeof(temp_path));
    SecureZeroMemory(verified_key, sizeof(verified_key));
    result = protect_record(role, key, buffer, &buffer_size);
    if (result != UL_PAIRING_OK)
        goto cleanup;
    result = create_temp_file(directory, sid, sid_size, temp_path, &temp);
    if (result != UL_PAIRING_OK)
        goto cleanup;
    while (offset < buffer_size) {
        if (!WriteFile(temp, buffer + offset, buffer_size - offset, &written,
                       NULL) || written == 0u) {
            result = UL_PAIRING_IO_ERROR;
            goto cleanup;
        }
        offset += written;
    }
    if (!FlushFileBuffers(temp)) {
        result = UL_PAIRING_IO_ERROR;
        goto cleanup;
    }
    CloseHandle(temp);
    temp = INVALID_HANDLE_VALUE;
    if (!cancel_claim_commit(cancel)) {
        result = UL_PAIRING_CANCELLED;
        goto cleanup;
    }
    if (replace)
        move_flags |= MOVEFILE_REPLACE_EXISTING;
    if (!MoveFileExW(temp_path, destination, move_flags)) {
        DWORD error = GetLastError();
        result = (!replace &&
                  (error == ERROR_FILE_EXISTS || error == ERROR_ALREADY_EXISTS))
                     ? UL_PAIRING_EXISTS
                     : UL_PAIRING_IO_ERROR;
        goto cleanup;
    }
    temp_path[0] = L'\0';
    result = read_record(destination, sid, role, verified_key);
    if (result != UL_PAIRING_OK ||
        !constant_equal(key, verified_key, UL_PAIRING_KEY_BYTES))
        result = UL_PAIRING_POSTCOMMIT_INVALID;

cleanup:
    if (temp != INVALID_HANDLE_VALUE)
        CloseHandle(temp);
    if (temp_path[0] != L'\0')
        DeleteFileW(temp_path);
    SecureZeroMemory(buffer, sizeof(buffer));
    SecureZeroMemory(temp_path, sizeof(temp_path));
    SecureZeroMemory(verified_key, sizeof(verified_key));
    return result;
}

static ul_pairing_result destination_parent(
    const wchar_t *destination, ul_handle_set *handles,
    wchar_t parent[UL_PAIRING_MAX_PATH_CHARS],
    wchar_t normalized_destination[UL_PAIRING_MAX_PATH_CHARS])
{
    wchar_t normalized[UL_PAIRING_MAX_PATH_CHARS];
    wchar_t parent_input[UL_PAIRING_MAX_PATH_CHARS];
    wchar_t rebuilt[UL_PAIRING_MAX_PATH_CHARS];
    wchar_t *separator;
    const wchar_t *name;
    ul_pairing_result result;

    SecureZeroMemory(normalized, sizeof(normalized));
    SecureZeroMemory(parent_input, sizeof(parent_input));
    SecureZeroMemory(rebuilt, sizeof(rebuilt));
    if (!normalize_absolute_path(destination, false, normalized))
        return UL_PAIRING_INVALID_ARGUMENT;
    separator = wcsrchr(normalized, L'\\');
    if (separator == NULL || separator < normalized + 6 ||
        separator[1] == L'\0')
        return UL_PAIRING_INVALID_ARGUMENT;
    name = separator + 1;
    if (separator == normalized + 6) {
        memcpy(parent_input, normalized + 4, 3u * sizeof(wchar_t));
        parent_input[3] = L'\0';
    } else {
        memcpy(parent_input, normalized + 4,
               (size_t)(separator - (normalized + 4)) * sizeof(wchar_t));
        parent_input[separator - (normalized + 4)] = L'\0';
    }
    result = walk_directory(parent_input, handles, parent);
    if (result != UL_PAIRING_OK)
        return result;
    if (!join_path(parent, name, rebuilt) || _wcsicmp(rebuilt, normalized) != 0)
        return UL_PAIRING_UNSUPPORTED;
    memcpy(normalized_destination, normalized,
           (wcslen(normalized) + 1u) * sizeof(wchar_t));
    return UL_PAIRING_OK;
}

static ul_pairing_result store_open_root(const wchar_t *root,
                                         ul_pairing_store **store_out)
{
    ul_pairing_store *store = NULL;
    wchar_t root_path[UL_PAIRING_MAX_PATH_CHARS];
    wchar_t utterleaf_path[UL_PAIRING_MAX_PATH_CHARS];
    ul_pairing_result result;

    *store_out = NULL;
    SecureZeroMemory(root_path, sizeof(root_path));
    SecureZeroMemory(utterleaf_path, sizeof(utterleaf_path));
    store = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*store));
    if (store == NULL)
        return UL_PAIRING_IO_ERROR;
    InitializeSRWLock(&store->lock);
    if (!bounded_token_user(&store->user_sid, &store->user_sid_size)) {
        result = UL_PAIRING_IO_ERROR;
        goto cleanup;
    }
    result = walk_directory(root, &store->directories, root_path);
    if (result != UL_PAIRING_OK)
        goto cleanup;
    result = ensure_private_directory(&store->directories, root_path,
                                      L"Utterleaf", store->user_sid,
                                      store->user_sid_size, utterleaf_path);
    if (result != UL_PAIRING_OK)
        goto cleanup;
    result = ensure_private_directory(&store->directories, utterleaf_path,
                                      L"obs-plugin", store->user_sid,
                                      store->user_sid_size, store->directory);
    if (result != UL_PAIRING_OK)
        goto cleanup;
    if (!join_path(store->directory, L"pairing-v1.dat", store->store_path)) {
        result = UL_PAIRING_UNSUPPORTED;
        goto cleanup;
    }
    *store_out = store;
    return UL_PAIRING_OK;

cleanup:
    if (store != NULL) {
        handles_close(&store->directories);
        wipe_free(store->user_sid, store->user_sid_size);
        SecureZeroMemory(store, sizeof(*store));
        HeapFree(GetProcessHeap(), 0, store);
    }
    return result;
}

void ul_pairing_cancel_init(ul_pairing_cancel *cancel)
{
    if (cancel != NULL)
        InterlockedExchange(&cancel->requested, 0);
}

void ul_pairing_cancel_request(ul_pairing_cancel *cancel)
{
    if (cancel != NULL)
        (void)InterlockedCompareExchange(&cancel->requested, 1, 0);
}

ul_pairing_result ul_pairing_store_open(ul_pairing_store **store_out)
{
    PWSTR local_app_data = NULL;
    ul_pairing_result result;

    if (store_out == NULL)
        return UL_PAIRING_INVALID_ARGUMENT;
    *store_out = NULL;
    if (FAILED(SHGetKnownFolderPath(&FOLDERID_LocalAppData, KF_FLAG_DEFAULT,
                                    NULL, &local_app_data)) ||
        local_app_data == NULL)
        return UL_PAIRING_IO_ERROR;
    result = store_open_root(local_app_data, store_out);
    SecureZeroMemory(local_app_data,
                     (wcslen(local_app_data) + 1u) * sizeof(wchar_t));
    CoTaskMemFree(local_app_data);
    return result;
}

ul_pairing_result
ul_pairing_store_open_test_root(const wchar_t *root,
                                ul_pairing_store **store_out)
{
    if (store_out == NULL)
        return UL_PAIRING_INVALID_ARGUMENT;
    *store_out = NULL;
    if (root == NULL)
        return UL_PAIRING_INVALID_ARGUMENT;
    return store_open_root(root, store_out);
}

void ul_pairing_store_destroy(ul_pairing_store *store)
{
    if (store == NULL)
        return;
    handles_close(&store->directories);
    wipe_free(store->user_sid, store->user_sid_size);
    SecureZeroMemory(store, sizeof(*store));
    HeapFree(GetProcessHeap(), 0, store);
}

ul_pairing_result ul_pairing_store_load(ul_pairing_store *store,
                                        uint8_t key[UL_PAIRING_KEY_BYTES])
{
    ul_pairing_result result;

    if (key == NULL)
        return UL_PAIRING_INVALID_ARGUMENT;
    SecureZeroMemory(key, UL_PAIRING_KEY_BYTES);
    if (store == NULL)
        return UL_PAIRING_INVALID_ARGUMENT;
    AcquireSRWLockExclusive(&store->lock);
    result = read_record(store->store_path, store->user_sid,
                         UL_PAIRING_ROLE_NATIVE, key);
    ReleaseSRWLockExclusive(&store->lock);
    return result;
}

static ul_pairing_result generate_store(ul_pairing_store *store,
                                        const ul_pairing_cancel *cancel,
                                        bool replace,
                                        uint8_t key[UL_PAIRING_KEY_BYTES])
{
    uint8_t existing[UL_PAIRING_KEY_BYTES];
    uint8_t generated[UL_PAIRING_KEY_BYTES];
    ul_pairing_result result;
    unsigned int attempt;

    SecureZeroMemory(key, UL_PAIRING_KEY_BYTES);
    SecureZeroMemory(existing, sizeof(existing));
    SecureZeroMemory(generated, sizeof(generated));
    AcquireSRWLockExclusive(&store->lock);
    if (cancel_is_requested(cancel)) {
        result = UL_PAIRING_CANCELLED;
        goto cleanup;
    }
    result = read_record(store->store_path, store->user_sid,
                         UL_PAIRING_ROLE_NATIVE, existing);
    if (replace) {
        if (result != UL_PAIRING_OK)
            goto cleanup;
    } else {
        if (result == UL_PAIRING_OK) {
            result = UL_PAIRING_EXISTS;
            goto cleanup;
        }
        if (result != UL_PAIRING_MISSING)
            goto cleanup;
    }
    for (attempt = 0; attempt < 4u; ++attempt) {
        if (!random_bytes(generated, sizeof(generated))) {
            result = UL_PAIRING_CRYPTO_ERROR;
            goto cleanup;
        }
        if (!bytes_are_zero(generated, sizeof(generated)) &&
            (!replace ||
             !constant_equal(generated, existing, sizeof(generated))))
            break;
    }
    if (bytes_are_zero(generated, sizeof(generated)) ||
        (replace && constant_equal(generated, existing, sizeof(generated)))) {
        result = UL_PAIRING_CRYPTO_ERROR;
        goto cleanup;
    }
    result = write_record(store->directory, store->store_path, store->user_sid,
                          store->user_sid_size, replace,
                          UL_PAIRING_ROLE_NATIVE, generated, cancel);
    if (result == UL_PAIRING_OK)
        memcpy(key, generated, UL_PAIRING_KEY_BYTES);

cleanup:
    ReleaseSRWLockExclusive(&store->lock);
    SecureZeroMemory(existing, sizeof(existing));
    SecureZeroMemory(generated, sizeof(generated));
    if (result != UL_PAIRING_OK)
        SecureZeroMemory(key, UL_PAIRING_KEY_BYTES);
    return result;
}

ul_pairing_result ul_pairing_store_create(
    ul_pairing_store *store, const ul_pairing_cancel *cancel,
    uint8_t key[UL_PAIRING_KEY_BYTES])
{
    if (key == NULL)
        return UL_PAIRING_INVALID_ARGUMENT;
    SecureZeroMemory(key, UL_PAIRING_KEY_BYTES);
    if (store == NULL)
        return UL_PAIRING_INVALID_ARGUMENT;
    return generate_store(store, cancel, false, key);
}

ul_pairing_result ul_pairing_store_replace(
    ul_pairing_store *store, const ul_pairing_cancel *cancel,
    uint8_t key[UL_PAIRING_KEY_BYTES])
{
    if (key == NULL)
        return UL_PAIRING_INVALID_ARGUMENT;
    SecureZeroMemory(key, UL_PAIRING_KEY_BYTES);
    if (store == NULL)
        return UL_PAIRING_INVALID_ARGUMENT;
    return generate_store(store, cancel, true, key);
}

ul_pairing_result ul_pairing_store_export(
    ul_pairing_store *store, const wchar_t *destination,
    const ul_pairing_cancel *cancel)
{
    uint8_t key[UL_PAIRING_KEY_BYTES];
    ul_handle_set parent_handles;
    wchar_t parent[UL_PAIRING_MAX_PATH_CHARS];
    wchar_t normalized[UL_PAIRING_MAX_PATH_CHARS];
    ul_pairing_result result;
    DWORD attributes;

    SecureZeroMemory(key, sizeof(key));
    SecureZeroMemory(&parent_handles, sizeof(parent_handles));
    SecureZeroMemory(parent, sizeof(parent));
    SecureZeroMemory(normalized, sizeof(normalized));
    if (store == NULL || destination == NULL)
        return UL_PAIRING_INVALID_ARGUMENT;
    AcquireSRWLockExclusive(&store->lock);
    if (cancel_is_requested(cancel)) {
        result = UL_PAIRING_CANCELLED;
        goto cleanup;
    }
    result = read_record(store->store_path, store->user_sid,
                         UL_PAIRING_ROLE_NATIVE, key);
    if (result != UL_PAIRING_OK)
        goto cleanup;
    result = destination_parent(destination, &parent_handles, parent,
                                normalized);
    if (result != UL_PAIRING_OK)
        goto cleanup;
    attributes = GetFileAttributesW(normalized);
    if (attributes != INVALID_FILE_ATTRIBUTES) {
        result = UL_PAIRING_EXISTS;
        goto cleanup;
    }
    if (GetLastError() != ERROR_FILE_NOT_FOUND &&
        GetLastError() != ERROR_PATH_NOT_FOUND) {
        result = UL_PAIRING_IO_ERROR;
        goto cleanup;
    }
    result = write_record(parent, normalized, store->user_sid,
                          store->user_sid_size, false,
                          UL_PAIRING_ROLE_TRANSFER, key, cancel);

cleanup:
    handles_close(&parent_handles);
    ReleaseSRWLockExclusive(&store->lock);
    SecureZeroMemory(key, sizeof(key));
    SecureZeroMemory(parent, sizeof(parent));
    SecureZeroMemory(normalized, sizeof(normalized));
    return result;
}

ul_pairing_result ul_pairing_store_forget(ul_pairing_store *store)
{
    HANDLE file = INVALID_HANDLE_VALUE;
    FILE_DISPOSITION_INFO disposition;
    ul_pairing_result result;

    if (store == NULL)
        return UL_PAIRING_INVALID_ARGUMENT;
    SecureZeroMemory(&disposition, sizeof(disposition));
    AcquireSRWLockExclusive(&store->lock);
    result = open_verified_file(store->store_path, store->user_sid, DELETE,
                                FILE_SHARE_DELETE, &file);
    if (result != UL_PAIRING_OK)
        goto cleanup;
    disposition.DeleteFile = TRUE;
    if (!SetFileInformationByHandle(file, FileDispositionInfo, &disposition,
                                    sizeof(disposition))) {
        result = UL_PAIRING_IO_ERROR;
        goto cleanup;
    }
    CloseHandle(file);
    file = INVALID_HANDLE_VALUE;
    if (GetFileAttributesW(store->store_path) != INVALID_FILE_ATTRIBUTES ||
        (GetLastError() != ERROR_FILE_NOT_FOUND &&
         GetLastError() != ERROR_PATH_NOT_FOUND)) {
        result = UL_PAIRING_IO_ERROR;
        goto cleanup;
    }
    result = UL_PAIRING_OK;

cleanup:
    if (file != INVALID_HANDLE_VALUE)
        CloseHandle(file);
    ReleaseSRWLockExclusive(&store->lock);
    return result;
}
