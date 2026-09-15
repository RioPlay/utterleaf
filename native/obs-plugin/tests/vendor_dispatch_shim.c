// SPDX-License-Identifier: GPL-2.0-or-later
#include "../src/plugin_state.h"
#include "../src/vendor_dispatch.h"
#include <string.h>

static unsigned issue_count, prepare_count, malformed_count;
static bool enabled;

ul_plugin_snapshot ul_plugin_get_status(void)
{
    ul_plugin_snapshot state = {0};
    state.status = enabled ? UL_PLUGIN_PAIRED : UL_PLUGIN_CLOSED;
    return state;
}

void ul_vendor_test_reset(bool accept)
{
    issue_count = prepare_count = malformed_count = 0u;
    enabled = accept;
    ul_vendor_set_enabled(true);
}

unsigned ul_vendor_test_count(unsigned kind)
{
    return kind == 0u ? issue_count : kind == 1u ? prepare_count : malformed_count;
}

bool ul_plugin_issue(DWORD pid, const uint8_t session[16], uint8_t mask, uint8_t challenge[60])
{
    ++issue_count;
    memset(challenge, 0, 60);
    memcpy(challenge, "ULAA", 4);
    challenge[4] = challenge[5] = 1;
    challenge[7] = mask;
    for (unsigned i = 0; i < 4; ++i)
        challenge[8 + i] = (uint8_t)(pid >> (8 * i));
    memcpy(challenge + 12, session, 16);
    memset(challenge + 28, 17, 32);
    return enabled;
}

bool ul_plugin_prepare(const uint8_t *challenge, size_t challenge_size,
                       const uint8_t *proof, size_t proof_size)
{
    ++prepare_count;
    if (challenge == NULL || proof == NULL || challenge_size != 60 || proof_size != 32) {
        ++malformed_count;
        return false;
    }
    return enabled;
}
