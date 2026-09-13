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
#define UL_AUDIO_MAX_ROUTING_SOURCES 128u
#define UL_AUDIO_MAX_BUS_LABEL_BYTES 64u
#define UL_AUDIO_MAX_SOURCE_NAME_BYTES 128u
#define UL_AUDIO_MAX_ROUTING_BODY_BYTES 19302u
#define UL_AUDIO_MAX_ROUTING_PACKET_BYTES \
    (UL_AUDIO_HEADER_BYTES + UL_AUDIO_MAX_ROUTING_BODY_BYTES)
#define UL_AUDIO_PROTOCOL_LEGACY_VERSION 1u
#define UL_AUDIO_PROTOCOL_PROVENANCE_VERSION 2u
#ifndef UL_AUDIO_RUNTIME_VERSION
#define UL_AUDIO_RUNTIME_VERSION UL_AUDIO_PROTOCOL_PROVENANCE_VERSION
#endif
#if UL_AUDIO_RUNTIME_VERSION != UL_AUDIO_PROTOCOL_LEGACY_VERSION && \
    UL_AUDIO_RUNTIME_VERSION != UL_AUDIO_PROTOCOL_PROVENANCE_VERSION
#error "UL_AUDIO_RUNTIME_VERSION must be 1 or 2"
#endif

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

typedef struct ul_audio_routing_bus {
    uint8_t bus;
    uint64_t next_sequence;
    const uint8_t *label;
    size_t label_length;
} ul_audio_routing_bus;

typedef struct ul_audio_routing_source {
    uint8_t source_id[16];
    uint8_t selected_mask;
    const uint8_t *name;
    size_t name_length;
} ul_audio_routing_source;

/* These encoders allocate nothing and return the exact encoded byte count.
 * Zero means invalid metadata, invalid PCM, or insufficient output capacity.
 * The caller's output bytes are left untouched on failure. Session IDs are
 * protocol correlation values; transport authentication remains separate.
 * Input buffers must not overlap the caller-owned output allocation. */
size_t ul_audio_encode_start(uint8_t *out, size_t capacity,
                             const uint8_t session_id[16],
                             uint32_t sample_rate, uint8_t primary_bus,
                             uint8_t bus_mask, uint64_t origin_ns);
size_t ul_audio_encode_start_version(
    uint8_t version, uint8_t *out, size_t capacity,
    const uint8_t session_id[16], uint32_t sample_rate,
    uint8_t primary_bus, uint8_t bus_mask, uint64_t origin_ns);

size_t ul_audio_encode_audio(uint8_t *out, size_t capacity,
                             const uint8_t session_id[16], uint8_t bus,
                             uint64_t sequence, uint64_t timestamp_ns,
                             uint32_t frames, const float *stereo_pcm);
size_t ul_audio_encode_audio_version(
    uint8_t version, uint8_t *out, size_t capacity,
    const uint8_t session_id[16], uint8_t bus, uint64_t sequence,
    uint64_t timestamp_ns, uint32_t frames, const float *stereo_pcm);

size_t ul_audio_encode_gap(uint8_t *out, size_t capacity,
                           const uint8_t session_id[16], uint8_t bus,
                           uint64_t first_sequence, uint64_t count,
                           uint64_t timestamp_ns);
size_t ul_audio_encode_gap_version(
    uint8_t version, uint8_t *out, size_t capacity,
    const uint8_t session_id[16], uint8_t bus, uint64_t first_sequence,
    uint64_t count, uint64_t timestamp_ns);

size_t ul_audio_encode_end(uint8_t *out, size_t capacity,
                           const uint8_t session_id[16], uint8_t reason,
                           const ul_audio_end_sequence *last_sequences,
                           size_t sequence_count);
size_t ul_audio_encode_end_version(
    uint8_t version, uint8_t *out, size_t capacity,
    const uint8_t session_id[16], uint8_t reason,
    const ul_audio_end_sequence *last_sequences, size_t sequence_count);

/* Routing is an observation-only version-2 record. Labels and source names
 * are already-private UTF-8 bytes and are never logged here. */
size_t ul_audio_encode_routing(
    uint8_t *out, size_t capacity, const uint8_t session_id[16],
    uint64_t revision, uint64_t observed_at_ns, uint8_t primary_bus,
    uint8_t bus_mask, const ul_audio_routing_bus *buses, size_t bus_count,
    const ul_audio_routing_source *sources, size_t source_count);

#endif
