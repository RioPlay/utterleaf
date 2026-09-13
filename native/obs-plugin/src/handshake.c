// SPDX-License-Identifier: GPL-2.0-or-later
#include "handshake.h"

#include "crypto.h"

#include <windows.h>

#include <string.h>

static const uint8_t ULAH_MAGIC[4] = {'U', 'L', 'A', 'H'};
static const uint8_t ULAH_DOMAIN[] = "Utterleaf OBS audio server ack v1";

static bool constant_equal(const uint8_t *left, const uint8_t *right,
                           size_t size)
{
    uint8_t difference = 0;
    size_t index;

    for (index = 0; index < size; ++index)
        difference |= (uint8_t)(left[index] ^ right[index]);
    return difference == 0;
}

bool ul_handshake_ack(const uint8_t *hello, size_t hello_size,
                      const uint8_t expected_session[16],
                      uint8_t ack[ULAH_HANDSHAKE_BYTES])
{
    uint8_t canonical[24];
    uint8_t secret[32];
    bool success;

    if (ack == NULL)
        return false;
    SecureZeroMemory(ack, ULAH_HANDSHAKE_BYTES);
    if (hello == NULL || expected_session == NULL ||
        hello_size != ULAH_HANDSHAKE_BYTES)
        return false;
    if (!constant_equal(hello, ULAH_MAGIC, sizeof(ULAH_MAGIC)) ||
        hello[4] != 1u || hello[5] != 1u || hello[6] != 0u || hello[7] != 0u ||
        !constant_equal(hello + 8, expected_session, 16u))
        return false;

    memcpy(canonical, hello, sizeof(canonical));
    memcpy(secret, hello + sizeof(canonical), sizeof(secret));
    memcpy(ack, canonical, sizeof(canonical));
    ack[5] = 2u;

    success = ul_hmac_sha256(secret, ULAH_DOMAIN, sizeof(ULAH_DOMAIN),
                             canonical, sizeof(canonical), ack + sizeof(canonical));
    SecureZeroMemory(secret, sizeof(secret));
    SecureZeroMemory(canonical, sizeof(canonical));
    if (!success)
        SecureZeroMemory(ack, ULAH_HANDSHAKE_BYTES);
    return success;
}
