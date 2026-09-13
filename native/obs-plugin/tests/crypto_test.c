// SPDX-License-Identifier: GPL-2.0-or-later
#include "../src/crypto.h"

#include <stdio.h>
#include <string.h>

static int check(bool condition, const char *message)
{
    if (!condition)
        fprintf(stderr, "FAIL: %s\n", message);
    return condition ? 0 : 1;
}

static int all_zero(const uint8_t output[32])
{
    size_t index;
    for (index = 0; index < 32u; ++index)
        if (output[index] != 0)
            return 0;
    return 1;
}

int main(void)
{
    static const uint8_t expected[32] = {
        0x4e, 0x61, 0xa5, 0xf3, 0x4c, 0x3e, 0xaa, 0x55,
        0xf9, 0xd3, 0xbf, 0xd9, 0x05, 0x3c, 0xbd, 0xc3,
        0x91, 0x65, 0x95, 0x70, 0x6b, 0x2d, 0xe3, 0xe0,
        0x98, 0x98, 0xbc, 0x6d, 0x35, 0x9d, 0x41, 0xdc,
    };
    const uint8_t key[32] = {
        'k', 'k', 'k', 'k', 'k', 'k', 'k', 'k',
        'k', 'k', 'k', 'k', 'k', 'k', 'k', 'k',
        'k', 'k', 'k', 'k', 'k', 'k', 'k', 'k',
        'k', 'k', 'k', 'k', 'k', 'k', 'k', 'k',
    };
    const uint8_t domain[] = "Utterleaf OBS prepare authorization v1\0";
    uint8_t payload[60] = {'U', 'L', 'A', 'A', 1, 1, 0, 9};
    uint8_t output[32];
    uint8_t overlap[16] = "overlap-input";
    size_t index;
    int failures = 0;

    payload[8] = 12345u & 0xffu;
    payload[9] = (12345u >> 8) & 0xffu;
    payload[10] = (12345u >> 16) & 0xffu;
    payload[11] = (12345u >> 24) & 0xffu;
    for (index = 0; index < 16u; ++index)
        payload[12 + index] = (uint8_t)index;
    memset(payload + 28, 'n', 32);

    memset(output, 0xa5, sizeof(output));
    failures += check(ul_hmac_sha256(key, domain, sizeof(domain) - 1u, payload,
                                     sizeof(payload), output), "vector accepted");
    failures += check(memcmp(output, expected, sizeof(output)) == 0,
                      "independent authorization vector");

    memset(output, 0xa5, sizeof(output));
    failures += check(ul_hmac_sha256(key, domain, 0, payload, sizeof(payload), output) == false,
                      "zero domain rejected");
    failures += check(all_zero(output), "zero domain output cleared");
    memset(output, 0xa5, sizeof(output));
    failures += check(ul_hmac_sha256(key, domain, 65, payload, sizeof(payload), output) == false,
                      "oversized domain rejected");
    failures += check(all_zero(output), "oversized domain output cleared");
    memset(output, 0xa5, sizeof(output));
    failures += check(ul_hmac_sha256(key, domain, sizeof(domain) - 1u, payload, 0, output) == false,
                      "zero data rejected");
    failures += check(all_zero(output), "zero data output cleared");
    memset(output, 0xa5, sizeof(output));
    failures += check(ul_hmac_sha256(key, domain, sizeof(domain) - 1u, payload, 257, output) == false,
                      "oversized data rejected");
    failures += check(all_zero(output), "oversized data output cleared");

    memset(output, 0xa5, sizeof(output));
    failures += check(ul_hmac_sha256(NULL, domain, sizeof(domain), payload,
                                     sizeof(payload), output) == false,
                      "null key rejected");
    failures += check(all_zero(output), "null key output cleared");
    memset(output, 0xa5, sizeof(output));
    failures += check(ul_hmac_sha256(key, NULL, sizeof(domain), payload,
                                     sizeof(payload), output) == false,
                      "null domain rejected");
    failures += check(all_zero(output), "null domain output cleared");
    memset(output, 0xa5, sizeof(output));
    failures += check(ul_hmac_sha256(key, domain, sizeof(domain) - 1u, NULL,
                                     sizeof(payload), output) == false,
                      "null data rejected");
    failures += check(all_zero(output), "null data output cleared");
    failures += check(ul_hmac_sha256(key, domain, sizeof(domain) - 1u, payload,
                                     sizeof(payload), NULL) == false,
                      "null output rejected");

    failures += check(ul_hmac_sha256(key, overlap, 8, overlap + 2, 6, output),
                      "overlapping input ranges accepted");
    puts(failures == 0 ? "crypto tests passed" : "crypto tests failed");
    return failures == 0 ? 0 : 1;
}
