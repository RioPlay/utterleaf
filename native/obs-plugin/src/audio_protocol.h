// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_OBS_AUDIO_PROTOCOL_H
#define UTTERLEAF_OBS_AUDIO_PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define UL_AUDIO_HEADER_BYTES 12u
#define UL_AUDIO_MAX_FRAMES 8192u
#define UL_AUDIO_MAX_PACKET_BYTES 65585u
#define UL_AUDIO_MAX_SEQUENCE (UINT64_MAX - UINT64_C(1))

enum ul_audio_end_reason {
    UL_AUDIO_END_STREAM_STOPPED = 1,
    UL_AUDIO_END_DISARMED = 2,
    UL_AUDIO_END_OBS_EXIT = 3,
    UL_AUDIO_END_SOURCE_CHANGED = 4,
    UL_AUDIO_END_TRANSPORT_ERROR = 5,
};

typedef struct ul_audio_end_sequence {
    uint8_t bus;
    bool has_sequence;
    uint64_t sequence;
} ul_audio_end_sequence;

/* These encoders allocate nothing and return the exact encoded byte count.
 * Zero means invalid metadata, invalid PCM, or insufficient output capacity.
 * The caller's output bytes are left untouched on failure. Session IDs are
 * protocol correlation values; transport authentication remains separate.
 * Input buffers must not overlap the caller-owned output allocation. */
size_t ul_audio_encode_start(uint8_t *out, size_t capacity,
                             const uint8_t session_id[16],
                             uint32_t sample_rate, uint8_t primary_bus,
                             uint8_t bus_mask, uint64_t origin_ns);

size_t ul_audio_encode_audio(uint8_t *out, size_t capacity,
                             const uint8_t session_id[16], uint8_t bus,
                             uint64_t sequence, uint64_t timestamp_ns,
                             uint32_t frames, const float *stereo_pcm);

size_t ul_audio_encode_gap(uint8_t *out, size_t capacity,
                           const uint8_t session_id[16], uint8_t bus,
                           uint64_t first_sequence, uint64_t count,
                           uint64_t timestamp_ns);

size_t ul_audio_encode_end(uint8_t *out, size_t capacity,
                           const uint8_t session_id[16], uint8_t reason,
                           const ul_audio_end_sequence *last_sequences,
                           size_t sequence_count);

#endif
