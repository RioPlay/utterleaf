// SPDX-License-Identifier: GPL-2.0-or-later
#include "../src/handshake.h"

#include <stdio.h>
#include <string.h>

static int check(bool condition, const char *message)
{
    if (!condition)
        fprintf(stderr, "FAIL: %s\n", message);
    return condition ? 0 : 1;
}

int main(void)
{
    static const uint8_t expected_mac[32] = {
        0xf1, 0x89, 0x37, 0x39, 0x58, 0x8f, 0xa5, 0x7f,
        0x39, 0x3e, 0x5b, 0x7c, 0xa8, 0xff, 0xcc, 0x33,
        0x19, 0xa3, 0xd0, 0xf3, 0x32, 0xc4, 0x53, 0x39,
        0x94, 0xb8, 0x58, 0x1c, 0x37, 0xe8, 0xb6, 0x36,
    };
    uint8_t hello[ULAH_HANDSHAKE_BYTES] = {
        'U', 'L', 'A', 'H', 1, 1, 0, 0,
    };
    uint8_t expected_session[16];
    uint8_t session_copy[16];
    uint8_t hello_copy[ULAH_HANDSHAKE_BYTES];
    uint8_t ack[ULAH_HANDSHAKE_BYTES];
    uint8_t aliased_ack[ULAH_HANDSHAKE_BYTES];
    uint8_t changed[ULAH_HANDSHAKE_BYTES];
    size_t index;
    int failures = 0;

    for (index = 0; index < sizeof(expected_session); ++index) {
        expected_session[index] = (uint8_t)index;
        hello[8 + index] = (uint8_t)index;
    }
    memcpy(session_copy, expected_session, sizeof(session_copy));
    memset(hello + 24, 's', 32);
    memcpy(hello_copy, hello, sizeof(hello));
    failures += check(ul_handshake_ack(hello, sizeof(hello), expected_session, ack),
                      "fixed Hello accepted");
    failures += check(memcmp(hello, hello_copy, sizeof(hello)) == 0,
                      "caller Hello unchanged");
    failures += check(memcmp(expected_session, session_copy, sizeof(session_copy)) == 0,
                      "caller session unchanged");
    failures += check(ul_handshake_ack(hello, sizeof(hello), hello + 8,
                                       aliased_ack), "overlapping input accepted");
    failures += check(memcmp(aliased_ack, ack, sizeof(ack)) == 0,
                      "overlapping input has same ACK");
    failures += check(memcmp(ack, "ULAH\x01\x02\x00\x00", 8) == 0,
                      "ACK role header");
    failures += check(memcmp(ack + 8, expected_session, 16) == 0,
                      "ACK session");
    failures += check(memcmp(ack + 24, expected_mac, sizeof(expected_mac)) == 0,
                      "independent HMAC vector");

    for (index = 0; index < 6; ++index) {
        memcpy(changed, hello, sizeof(changed));
        changed[(const size_t[]){0, 4, 5, 6, 7, 8}[index]] ^= 1u;
        memset(ack, 0xa5, sizeof(ack));
        failures += check(!ul_handshake_ack(changed, sizeof(changed),
                                             expected_session, ack),
                          "malformed Hello rejected");
        for (size_t byte = 0; byte < sizeof(ack); ++byte)
            failures += check(ack[byte] == 0, "failed ACK zeroed");
    }
    memset(ack, 0xa5, sizeof(ack));
    failures += check(!ul_handshake_ack(hello, sizeof(hello) - 1,
                                         expected_session, ack), "truncated rejected");
    for (index = 0; index < sizeof(ack); ++index)
        failures += check(ack[index] == 0, "truncated ACK zeroed");
    memset(ack, 0xa5, sizeof(ack));
    failures += check(!ul_handshake_ack(hello, sizeof(hello) + 1,
                                         expected_session, ack), "extra bytes rejected");
    for (index = 0; index < sizeof(ack); ++index)
        failures += check(ack[index] == 0, "extra bytes ACK zeroed");
    memset(ack, 0xa5, sizeof(ack));
    failures += check(!ul_handshake_ack(NULL, sizeof(hello), expected_session, ack),
                      "null Hello rejected");
    for (index = 0; index < sizeof(ack); ++index)
        failures += check(ack[index] == 0, "null Hello ACK zeroed");
    memset(ack, 0xa5, sizeof(ack));
    failures += check(!ul_handshake_ack(hello, sizeof(hello), NULL, ack),
                      "null session rejected");
    for (index = 0; index < sizeof(ack); ++index)
        failures += check(ack[index] == 0, "null session ACK zeroed");
    failures += check(!ul_handshake_ack(hello, sizeof(hello), expected_session, NULL),
                      "null ACK rejected");
    puts(failures == 0 ? "handshake tests passed" : "handshake tests failed");
    return failures == 0 ? 0 : 1;
}
