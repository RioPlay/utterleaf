// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_OBS_SESSION_PROTOCOL_H
#define UTTERLEAF_OBS_SESSION_PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define UL_SESSION_COMMAND_BYTES 28u

/* Fixed metadata only, inside the authenticated pipe after Hello/ACK.
 * The prepared session and mix mask remain authoritative. A command does not
 * authenticate a caller or establish an idle OBS state on its own. */
bool ul_session_arm_request(const uint8_t *data, size_t size,
                            const uint8_t session[16], uint8_t mix_mask);

/* Reply status 1 acknowledges committed Arm; status 2 refuses it. Both are
 * terminal for this one Arm attempt. Clears output on invalid local arguments. */
bool ul_session_arm_reply(const uint8_t session[16], uint8_t mix_mask,
                          bool accepted, uint8_t out[UL_SESSION_COMMAND_BYTES]);

#endif
