// SPDX-License-Identifier: GPL-2.0-or-later
#include "../src/handshake.h"

#include <windows.h>
#include <bcrypt.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum failure_point {
    FAIL_OPEN,
    FAIL_PROPERTY,
    FAIL_PROPERTY_SIZE,
    FAIL_PROPERTY_ZERO,
    FAIL_PROPERTY_LARGE,
    FAIL_ALLOC,
    FAIL_CREATE,
    FAIL_HASH_DOMAIN,
    FAIL_HASH_HEADER,
    FAIL_FINISH,
};

static enum failure_point failure;
static unsigned open_count, close_count, create_count, destroy_count;
static unsigned hash_calls;
static unsigned alloc_count, free_count, zero_before_free;
static unsigned object_size = 64;
static void *object_pointer;

NTSTATUS shim_BCryptOpenAlgorithmProvider(BCRYPT_ALG_HANDLE *algorithm,
                                           LPCWSTR id, LPCWSTR implementation,
                                           ULONG flags)
{
    (void)id; (void)implementation; (void)flags;
    if (failure == FAIL_OPEN)
        return (NTSTATUS)0xc0000001L;
    *algorithm = (BCRYPT_ALG_HANDLE)(uintptr_t)0x11;
    ++open_count;
    return 0;
}

NTSTATUS shim_BCryptGetProperty(BCRYPT_HANDLE object, LPCWSTR property,
                                PUCHAR output, ULONG output_size,
                                ULONG *result_size, ULONG flags)
{
    (void)object; (void)property; (void)flags;
    if (failure == FAIL_PROPERTY)
        return (NTSTATUS)0xc0000001L;
    *(DWORD *)output = object_size;
    *result_size = failure == FAIL_PROPERTY_SIZE ? sizeof(DWORD) - 1 : output_size;
    if (failure == FAIL_PROPERTY_ZERO)
        *(DWORD *)output = 0;
    if (failure == FAIL_PROPERTY_LARGE)
        *(DWORD *)output = 1025;
    return 0;
}

HANDLE WINAPI shim_GetProcessHeap(void)
{
    return (BCRYPT_HANDLE)(uintptr_t)0x22;
}

LPVOID WINAPI shim_HeapAlloc(HANDLE heap, DWORD flags, SIZE_T size)
{
    (void)heap; (void)flags;
    if (failure == FAIL_ALLOC)
        return NULL;
    object_pointer = malloc(size);
    if (object_pointer != NULL)
        memset(object_pointer, 0xa5, size);
    ++alloc_count;
    return object_pointer;
}

BOOL WINAPI shim_HeapFree(HANDLE heap, DWORD flags, LPVOID pointer)
{
    unsigned char *bytes = (unsigned char *)pointer;
    size_t index;
    (void)heap; (void)flags;
    ++free_count;
    for (index = 0; index < object_size; ++index)
        if (bytes[index] != 0) {
            zero_before_free = 0;
            break;
        }
    if (index == object_size)
        zero_before_free = 1;
    free(pointer);
    return TRUE;
}

NTSTATUS shim_BCryptCreateHash(BCRYPT_ALG_HANDLE algorithm,
                               BCRYPT_HASH_HANDLE *hash, PUCHAR object,
                               ULONG object_size_arg, PUCHAR secret,
                               ULONG secret_size, ULONG flags)
{
    (void)algorithm; (void)object; (void)object_size_arg;
    (void)secret; (void)secret_size; (void)flags;
    if (failure == FAIL_CREATE)
        return (NTSTATUS)0xc0000001L;
    *hash = (BCRYPT_HASH_HANDLE)(uintptr_t)0x33;
    ++create_count;
    return 0;
}

NTSTATUS shim_BCryptHashData(BCRYPT_HASH_HANDLE hash, PUCHAR data,
                             ULONG data_size, ULONG flags)
{
    (void)hash; (void)data; (void)data_size; (void)flags;
    ++hash_calls;
    if ((failure == FAIL_HASH_DOMAIN && hash_calls == 1) ||
        (failure == FAIL_HASH_HEADER && hash_calls == 2))
        return (NTSTATUS)0xc0000001L;
    return 0;
}

NTSTATUS shim_BCryptFinishHash(BCRYPT_HASH_HANDLE hash, PUCHAR output,
                               ULONG output_size, ULONG flags)
{
    (void)hash; (void)output_size; (void)flags;
    if (failure == FAIL_FINISH)
        return (NTSTATUS)0xc0000001L;
    memset(output, 0x5a, 32);
    return 0;
}

NTSTATUS shim_BCryptDestroyHash(BCRYPT_HASH_HANDLE hash)
{
    (void)hash;
    ++destroy_count;
    return 0;
}

NTSTATUS shim_BCryptCloseAlgorithmProvider(BCRYPT_ALG_HANDLE algorithm,
                                           ULONG flags)
{
    (void)algorithm; (void)flags;
    ++close_count;
    return 0;
}

static int check(bool condition, const char *message)
{
    if (!condition)
        fprintf(stderr, "FAIL: %s\n", message);
    return condition ? 0 : 1;
}

int main(void)
{
    uint8_t hello[ULAH_HANDSHAKE_BYTES] = {'U', 'L', 'A', 'H', 1, 1, 0, 0};
    uint8_t session[16];
    uint8_t hello_copy[ULAH_HANDSHAKE_BYTES];
    uint8_t session_copy[16];
    uint8_t ack[ULAH_HANDSHAKE_BYTES];
    size_t index;
    int failures = 0;

    for (index = 0; index < sizeof(session); ++index) {
        session[index] = (uint8_t)index;
        hello[8 + index] = (uint8_t)index;
    }
    memset(hello + 24, 's', 32);
    memcpy(hello_copy, hello, sizeof(hello));
    memcpy(session_copy, session, sizeof(session));
    for (failure = FAIL_OPEN; failure <= FAIL_FINISH; ++failure) {
        memset(ack, 0xa5, sizeof(ack));
        open_count = close_count = create_count = destroy_count = 0;
        hash_calls = alloc_count = free_count = zero_before_free = 0;
        if (failure == FAIL_PROPERTY_ZERO)
            object_size = 0;
        else if (failure == FAIL_PROPERTY_LARGE)
            object_size = 1025;
        else
            object_size = 64;
        failures += check(!ul_handshake_ack(hello, sizeof(hello), session, ack),
                          "injected failure rejected");
        for (index = 0; index < sizeof(ack); ++index)
            failures += check(ack[index] == 0, "failure ACK fully zeroed");
        failures += check(memcmp(hello, hello_copy, sizeof(hello)) == 0,
                          "failure leaves Hello unchanged");
        failures += check(memcmp(session, session_copy, sizeof(session)) == 0,
                          "failure leaves session unchanged");
        failures += check(close_count == open_count && destroy_count == create_count,
                          "acquired handles closed/destroyed exactly once");
        failures += check(alloc_count == free_count &&
                          (free_count == 0 || zero_before_free),
                          "allocated CNG object erased before free");
    }
    puts(failures == 0 ? "handshake failure tests passed" : "handshake failure tests failed");
    return failures == 0 ? 0 : 1;
}
