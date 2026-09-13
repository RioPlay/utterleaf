// SPDX-License-Identifier: GPL-2.0-or-later
#include "../src/session_protocol.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    const uint8_t session[16] = {1, 2, 3, 4, 5, 6, 7, 8,
                                9, 10, 11, 12, 13, 14, 15, 16};
    const uint8_t fixture[28] = {'U', 'L', 'A', 'C', 1, 1, 0, 0,
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 37, 0, 0, 0};
    uint8_t modified[29], reply[28], expected[28], zero[28] = {0};
    size_t index;

    assert(ul_session_arm_request(fixture, sizeof(fixture), session, 37));
    assert(!ul_session_arm_request(NULL, sizeof(fixture), session, 37));
    assert(!ul_session_arm_request(fixture, sizeof(fixture), NULL, 37));
    assert(!ul_session_arm_request(fixture, sizeof(fixture), zero, 37));
    assert(!ul_session_arm_request(fixture, sizeof(fixture), session, 64));
    for (index = 0; index < sizeof(fixture); ++index) {
        assert(!ul_session_arm_request(fixture, index, session, 37));
        memcpy(modified, fixture, sizeof(fixture));
        modified[index] ^= 1u;
        assert(!ul_session_arm_request(modified, sizeof(fixture), session, 37));
    }
    memcpy(modified, fixture, sizeof(fixture));
    modified[28] = 0;
    assert(!ul_session_arm_request(modified, sizeof(modified), session, 37));

    memcpy(expected, fixture, sizeof(expected));
    expected[5] = 2;
    expected[25] = 1;
    assert(ul_session_arm_reply(session, 37, true, reply));
    assert(memcmp(reply, expected, sizeof(reply)) == 0);
    expected[25] = 2;
    assert(ul_session_arm_reply(session, 37, false, reply));
    assert(memcmp(reply, expected, sizeof(reply)) == 0);
    assert(!ul_session_arm_request(reply, sizeof(reply), session, 37));
    assert(!ul_session_arm_reply(session, 64, true, reply));
    assert(memcmp(reply, zero, sizeof(reply)) == 0);
    memset(reply, 255, sizeof(reply));
    assert(!ul_session_arm_reply(zero, 0, true, reply));
    assert(memcmp(reply, zero, sizeof(reply)) == 0);
    assert(!ul_session_arm_reply(session, 0, true, NULL));
    puts("fixed Arm request/reply contract passed");
    return 0;
}
