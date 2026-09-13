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
    /* Independent terminal receipt: same session, no mask/status payload. */
    const uint8_t receipt[28] = {'U', 'L', 'A', 'C', 1, 3, 0, 0,
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 0, 0, 0, 0};
    assert(ul_session_end_ack(receipt, sizeof(receipt), session));
    assert(!ul_session_end_ack(NULL, sizeof(receipt), session));
    assert(!ul_session_end_ack(receipt, sizeof(receipt), NULL));
    assert(!ul_session_end_ack(receipt, sizeof(receipt), zero));
    assert(!ul_session_end_ack(fixture, sizeof(fixture), session));
    for (index = 0; index < sizeof(receipt); ++index) {
        assert(!ul_session_end_ack(receipt, index, session));
        memcpy(modified, receipt, sizeof(receipt));
        modified[index] ^= 1u;
        assert(!ul_session_end_ack(modified, sizeof(receipt), session));
    }
    memcpy(modified, receipt, sizeof(receipt));
    modified[28] = 0;
    assert(!ul_session_end_ack(modified, sizeof(modified), session));
    {
        const uint8_t disarm[28] = {'U', 'L', 'A', 'C', 1, 4, 0, 0,
            1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
            0, 0, 0, 0};
        assert(ul_session_disarm_request(disarm, sizeof(disarm), session));
        assert(!ul_session_disarm_request(NULL, sizeof(disarm), session));
        assert(!ul_session_disarm_request(disarm, sizeof(disarm), NULL));
        assert(!ul_session_disarm_request(disarm, sizeof(disarm), zero));
        assert(!ul_session_disarm_request(receipt, sizeof(receipt), session));
        for (index = 0; index < sizeof(disarm); ++index) {
            assert(!ul_session_disarm_request(disarm, index, session));
            memcpy(modified, disarm, sizeof(disarm));
            modified[index] ^= 1u;
            assert(!ul_session_disarm_request(modified, sizeof(disarm), session));
        }
        memcpy(modified, disarm, sizeof(disarm));
        modified[28] = 0;
        assert(!ul_session_disarm_request(modified, sizeof(modified), session));
    }
    puts("fixed Arm, Disarm, and terminal receipt contracts passed");
    return 0;
}
