// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_OBS_HANDSHAKE_H
#define UTTERLEAF_OBS_HANDSHAKE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ULAH_HANDSHAKE_BYTES 56u

/*
 * Validate one complete client Hello and build its server ACK. The caller must
 * have authenticated the peer process before its first read and must consume
 * this session exactly once. This stateless function does not perform either
 * socket/pipe or peer-identity operation.
 *
 * expected_session is the server's already-authorized session identifier.
 * The caller owns hello, expected_session and ack. A valid writable 56-byte
 * ack buffer must be disjoint from both input buffers; hello and
 * expected_session may overlap. The function does not erase or modify either
 * input and writes all-zero bytes to a disjoint ack buffer on failure.
 */
bool ul_handshake_ack(const uint8_t *hello, size_t hello_size,
                      const uint8_t expected_session[16],
                      uint8_t ack[ULAH_HANDSHAKE_BYTES]);

#endif
