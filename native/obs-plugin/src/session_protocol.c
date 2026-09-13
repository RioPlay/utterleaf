// SPDX-License-Identifier: GPL-2.0-or-later
#include "session_protocol.h"

#include <string.h>

static bool valid_session(const uint8_t session[16])
{
    uint8_t combined = 0;
    size_t index;
    if (session == NULL)
        return false;
    for (index = 0; index < 16u; ++index)
        combined |= session[index];
    return combined != 0;
}

bool ul_session_arm_request(const uint8_t *data, size_t size,
                            const uint8_t session[16], uint8_t mix_mask)
{
    return data != NULL && size == UL_SESSION_COMMAND_BYTES &&
           valid_session(session) && mix_mask <= 63u &&
           memcmp(data, "ULAC", 4u) == 0 &&
           data[4] == 1u && data[5] == 1u &&
           data[6] == 0u && data[7] == 0u &&
           memcmp(data + 8u, session, 16u) == 0 &&
           data[24] == mix_mask && data[25] == 0u &&
           data[26] == 0u && data[27] == 0u;
}

bool ul_session_arm_reply(const uint8_t session[16], uint8_t mix_mask,
                          bool accepted, uint8_t out[UL_SESSION_COMMAND_BYTES])
{
    if (out == NULL)
        return false;
    memset(out, 0, UL_SESSION_COMMAND_BYTES);
    if (!valid_session(session) || mix_mask > 63u)
        return false;
    memcpy(out, "ULAC", 4u);
    out[4] = 1u;
    out[5] = 2u;
    memcpy(out + 8u, session, 16u);
    out[24] = mix_mask;
    out[25] = accepted ? 1u : 2u;
    return true;
}

bool ul_session_end_ack(const uint8_t *data, size_t size,
                         const uint8_t session[16])
{
    return data != NULL && size == UL_SESSION_COMMAND_BYTES &&
           valid_session(session) && memcmp(data, "ULAC", 4u) == 0 &&
           data[4] == 1u && data[5] == 3u && data[6] == 0u && data[7] == 0u &&
           memcmp(data + 8u, session, 16u) == 0 &&
           data[24] == 0u && data[25] == 0u && data[26] == 0u && data[27] == 0u;
}
