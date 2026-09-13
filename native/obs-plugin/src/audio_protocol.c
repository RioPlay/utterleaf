// SPDX-License-Identifier: GPL-2.0-or-later
#include "audio_protocol.h"

#include <float.h>
#include <math.h>
#include <string.h>

_Static_assert(sizeof(float) == 4u && FLT_RADIX == 2 && FLT_MANT_DIG == 24 &&
                   FLT_MAX_EXP == 128,
               "ULAP requires IEEE 754 binary32 float");

#define UL_AUDIO_KIND_START 1u
#define UL_AUDIO_KIND_AUDIO 2u
#define UL_AUDIO_KIND_GAP 3u
#define UL_AUDIO_KIND_END 4u

static bool valid_sample_rate(uint32_t sample_rate)
{
    switch (sample_rate) {
    case 16000u:
    case 32000u:
    case 44100u:
    case 48000u:
    case 88200u:
    case 96000u:
        return true;
    default:
        return false;
    }
}

static bool valid_common(uint8_t *out, size_t capacity,
                         const uint8_t session_id[16], size_t required)
{
    return out != NULL && session_id != NULL && capacity >= required;
}

static void put_u32(uint8_t *out, uint32_t value)
{
    out[0] = (uint8_t)value;
    out[1] = (uint8_t)(value >> 8);
    out[2] = (uint8_t)(value >> 16);
    out[3] = (uint8_t)(value >> 24);
}

static void put_u64(uint8_t *out, uint64_t value)
{
    size_t index;
    for (index = 0; index < 8u; ++index)
        out[index] = (uint8_t)(value >> (index * 8u));
}

static void put_header(uint8_t *out, uint8_t kind, uint32_t body_size)
{
    memcpy(out, "ULAP", 4u);
    out[4] = 1u;
    out[5] = kind;
    out[6] = 0u;
    out[7] = 0u;
    put_u32(out + 8u, body_size);
}

size_t ul_audio_encode_start(uint8_t *out, size_t capacity,
                             const uint8_t session_id[16],
                             uint32_t sample_rate, uint8_t primary_bus,
                             uint8_t bus_mask, uint64_t origin_ns)
{
    const size_t packet_size = UL_AUDIO_HEADER_BYTES + 30u;
    uint8_t *body;
    if (!valid_common(out, capacity, session_id, packet_size) ||
        !valid_sample_rate(sample_rate) || primary_bus > 5u ||
        bus_mask == 0u || bus_mask > 0x3fu ||
        (bus_mask & (uint8_t)(1u << primary_bus)) == 0u)
        return 0u;
    put_header(out, UL_AUDIO_KIND_START, 30u);
    body = out + UL_AUDIO_HEADER_BYTES;
    memcpy(body, session_id, 16u);
    put_u32(body + 16u, sample_rate);
    body[20] = primary_bus;
    body[21] = bus_mask;
    put_u64(body + 22u, origin_ns);
    return packet_size;
}

size_t ul_audio_encode_audio(uint8_t *out, size_t capacity,
                             const uint8_t session_id[16], uint8_t bus,
                             uint64_t sequence, uint64_t timestamp_ns,
                             uint32_t frames, const float *stereo_pcm)
{
    size_t sample_count, pcm_size, packet_size, index;
    uint8_t *body, *pcm_out;
    if (frames == 0u || frames > UL_AUDIO_MAX_FRAMES || bus > 5u ||
        sequence > UL_AUDIO_MAX_SEQUENCE || stereo_pcm == NULL)
        return 0u;
    sample_count = (size_t)frames * 2u;
    pcm_size = sample_count * sizeof(float);
    packet_size = UL_AUDIO_HEADER_BYTES + 37u + pcm_size;
    if (!valid_common(out, capacity, session_id, packet_size))
        return 0u;
    for (index = 0; index < sample_count; ++index) {
        if (!isfinite(stereo_pcm[index]))
            return 0u;
    }
    put_header(out, UL_AUDIO_KIND_AUDIO, (uint32_t)(37u + pcm_size));
    body = out + UL_AUDIO_HEADER_BYTES;
    memcpy(body, session_id, 16u);
    body[16] = bus;
    put_u64(body + 17u, sequence);
    put_u64(body + 25u, timestamp_ns);
    put_u32(body + 33u, frames);
    pcm_out = body + 37u;
    for (index = 0; index < sample_count; ++index) {
        uint32_t bits;
        memcpy(&bits, stereo_pcm + index, sizeof(bits));
        put_u32(pcm_out + index * 4u, bits);
    }
    return packet_size;
}

size_t ul_audio_encode_gap(uint8_t *out, size_t capacity,
                           const uint8_t session_id[16], uint8_t bus,
                           uint64_t first_sequence, uint64_t count,
                           uint64_t timestamp_ns)
{
    const size_t packet_size = UL_AUDIO_HEADER_BYTES + 41u;
    uint8_t *body;
    if (!valid_common(out, capacity, session_id, packet_size) || bus > 5u ||
        first_sequence > UL_AUDIO_MAX_SEQUENCE || count == 0u ||
        count > UINT64_MAX - first_sequence)
        return 0u;
    put_header(out, UL_AUDIO_KIND_GAP, 41u);
    body = out + UL_AUDIO_HEADER_BYTES;
    memcpy(body, session_id, 16u);
    body[16] = bus;
    put_u64(body + 17u, first_sequence);
    put_u64(body + 25u, count);
    put_u64(body + 33u, timestamp_ns);
    return packet_size;
}

size_t ul_audio_encode_end(uint8_t *out, size_t capacity,
                           const uint8_t session_id[16], uint8_t reason,
                           const ul_audio_end_sequence *last_sequences,
                           size_t sequence_count)
{
    size_t body_size, packet_size, index;
    uint8_t *body;
    if (sequence_count < 1u || sequence_count > 6u ||
        last_sequences == NULL || reason < UL_AUDIO_END_STREAM_STOPPED ||
        reason > UL_AUDIO_END_TRANSPORT_ERROR)
        return 0u;
    body_size = 18u + sequence_count * 9u;
    packet_size = UL_AUDIO_HEADER_BYTES + body_size;
    if (!valid_common(out, capacity, session_id, packet_size))
        return 0u;
    for (index = 0; index < sequence_count; ++index) {
        const ul_audio_end_sequence *entry = last_sequences + index;
        if (entry->bus > 5u || (index > 0u && entry[-1].bus >= entry->bus) ||
            (entry->has_sequence && entry->sequence > UL_AUDIO_MAX_SEQUENCE))
            return 0u;
    }
    put_header(out, UL_AUDIO_KIND_END, (uint32_t)body_size);
    body = out + UL_AUDIO_HEADER_BYTES;
    memcpy(body, session_id, 16u);
    body[16] = reason;
    body[17] = (uint8_t)sequence_count;
    for (index = 0; index < sequence_count; ++index) {
        body[18u + index * 9u] = last_sequences[index].bus;
        put_u64(body + 19u + index * 9u,
                last_sequences[index].has_sequence
                    ? last_sequences[index].sequence : UINT64_MAX);
    }
    return packet_size;
}
