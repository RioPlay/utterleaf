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
#define UL_AUDIO_KIND_ROUTING 5u

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

static void put_u16(uint8_t *out, uint16_t value)
{
    out[0] = (uint8_t)value;
    out[1] = (uint8_t)(value >> 8);
}

static void put_u64(uint8_t *out, uint64_t value)
{
    size_t index;
    for (index = 0; index < 8u; ++index)
        out[index] = (uint8_t)(value >> (index * 8u));
}

static void put_header(uint8_t *out, uint8_t version, uint8_t kind,
                       uint32_t body_size)
{
    memcpy(out, "ULAP", 4u);
    out[4] = version;
    out[5] = kind;
    out[6] = 0u;
    out[7] = 0u;
    put_u32(out + 8u, body_size);
}

static bool valid_version(uint8_t version)
{
    return version == UL_AUDIO_PROTOCOL_LEGACY_VERSION ||
           version == UL_AUDIO_PROTOCOL_PROVENANCE_VERSION;
}

size_t ul_audio_encode_start_version(
    uint8_t version, uint8_t *out, size_t capacity,
    const uint8_t session_id[16], uint32_t sample_rate,
    uint8_t primary_bus, uint8_t bus_mask, uint64_t origin_ns)
{
    const size_t packet_size = UL_AUDIO_HEADER_BYTES + 30u;
    uint8_t *body;
    if (!valid_version(version) ||
        !valid_common(out, capacity, session_id, packet_size) ||
        !valid_sample_rate(sample_rate) || primary_bus > 5u ||
        bus_mask == 0u || bus_mask > 0x3fu ||
        (bus_mask & (uint8_t)(1u << primary_bus)) == 0u)
        return 0u;
    put_header(out, version, UL_AUDIO_KIND_START, 30u);
    body = out + UL_AUDIO_HEADER_BYTES;
    memcpy(body, session_id, 16u);
    put_u32(body + 16u, sample_rate);
    body[20] = primary_bus;
    body[21] = bus_mask;
    put_u64(body + 22u, origin_ns);
    return packet_size;
}

size_t ul_audio_encode_start(uint8_t *out, size_t capacity,
                             const uint8_t session_id[16],
                             uint32_t sample_rate, uint8_t primary_bus,
                             uint8_t bus_mask, uint64_t origin_ns)
{
    return ul_audio_encode_start_version(
        UL_AUDIO_PROTOCOL_LEGACY_VERSION, out, capacity, session_id,
        sample_rate, primary_bus, bus_mask, origin_ns);
}

size_t ul_audio_encode_audio_version(
    uint8_t version, uint8_t *out, size_t capacity,
    const uint8_t session_id[16], uint8_t bus, uint64_t sequence,
    uint64_t timestamp_ns, uint32_t frames, const float *stereo_pcm)
{
    size_t sample_count, pcm_size, packet_size, index;
    uint8_t *body, *pcm_out;
    if (!valid_version(version) || frames == 0u ||
        frames > UL_AUDIO_MAX_FRAMES || bus > 5u ||
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
    put_header(out, version, UL_AUDIO_KIND_AUDIO,
               (uint32_t)(37u + pcm_size));
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

size_t ul_audio_encode_audio(uint8_t *out, size_t capacity,
                             const uint8_t session_id[16], uint8_t bus,
                             uint64_t sequence, uint64_t timestamp_ns,
                             uint32_t frames, const float *stereo_pcm)
{
    return ul_audio_encode_audio_version(
        UL_AUDIO_PROTOCOL_LEGACY_VERSION, out, capacity, session_id, bus,
        sequence, timestamp_ns, frames, stereo_pcm);
}

size_t ul_audio_encode_gap_version(
    uint8_t version, uint8_t *out, size_t capacity,
    const uint8_t session_id[16], uint8_t bus, uint64_t first_sequence,
    uint64_t count, uint64_t timestamp_ns)
{
    const size_t packet_size = UL_AUDIO_HEADER_BYTES + 41u;
    uint8_t *body;
    if (!valid_version(version) ||
        !valid_common(out, capacity, session_id, packet_size) || bus > 5u ||
        first_sequence > UL_AUDIO_MAX_SEQUENCE || count == 0u ||
        count > UINT64_MAX - first_sequence)
        return 0u;
    put_header(out, version, UL_AUDIO_KIND_GAP, 41u);
    body = out + UL_AUDIO_HEADER_BYTES;
    memcpy(body, session_id, 16u);
    body[16] = bus;
    put_u64(body + 17u, first_sequence);
    put_u64(body + 25u, count);
    put_u64(body + 33u, timestamp_ns);
    return packet_size;
}

size_t ul_audio_encode_gap(uint8_t *out, size_t capacity,
                           const uint8_t session_id[16], uint8_t bus,
                           uint64_t first_sequence, uint64_t count,
                           uint64_t timestamp_ns)
{
    return ul_audio_encode_gap_version(
        UL_AUDIO_PROTOCOL_LEGACY_VERSION, out, capacity, session_id, bus,
        first_sequence, count, timestamp_ns);
}

size_t ul_audio_encode_end_version(
    uint8_t version, uint8_t *out, size_t capacity,
    const uint8_t session_id[16], uint8_t reason,
    const ul_audio_end_sequence *last_sequences, size_t sequence_count)
{
    size_t body_size, packet_size, index;
    uint8_t *body;
    if (!valid_version(version) || sequence_count > 6u ||
        (sequence_count == 0u && reason != UL_AUDIO_END_DISARMED) ||
        (sequence_count != 0u && last_sequences == NULL) ||
        reason < UL_AUDIO_END_STREAM_STOPPED ||
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
    put_header(out, version, UL_AUDIO_KIND_END, (uint32_t)body_size);
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

size_t ul_audio_encode_end(uint8_t *out, size_t capacity,
                           const uint8_t session_id[16], uint8_t reason,
                           const ul_audio_end_sequence *last_sequences,
                           size_t sequence_count)
{
    return ul_audio_encode_end_version(
        UL_AUDIO_PROTOCOL_LEGACY_VERSION, out, capacity, session_id, reason,
        last_sequences, sequence_count);
}

static bool valid_utf8_label(const uint8_t *text, size_t length,
                             size_t maximum)
{
    size_t index = 0u;
    bool has_visible_codepoint = false;
    if (text == NULL || length == 0u || length > maximum)
        return false;
    while (index < length) {
        uint32_t codepoint;
        uint8_t first = text[index++];
        if (first < 0x80u) {
            codepoint = first;
        } else if (first >= 0xc2u && first <= 0xdfu) {
            if (index >= length || (text[index] & 0xc0u) != 0x80u)
                return false;
            codepoint = ((uint32_t)(first & 0x1fu) << 6) |
                        (uint32_t)(text[index++] & 0x3fu);
        } else if (first >= 0xe0u && first <= 0xefu) {
            uint8_t second;
            if (length - index < 2u)
                return false;
            second = text[index];
            if ((second & 0xc0u) != 0x80u ||
                (text[index + 1u] & 0xc0u) != 0x80u ||
                (first == 0xe0u && second < 0xa0u) ||
                (first == 0xedu && second >= 0xa0u))
                return false;
            codepoint = ((uint32_t)(first & 0x0fu) << 12) |
                        ((uint32_t)(second & 0x3fu) << 6) |
                        (uint32_t)(text[index + 1u] & 0x3fu);
            index += 2u;
        } else if (first >= 0xf0u && first <= 0xf4u) {
            uint8_t second;
            if (length - index < 3u)
                return false;
            second = text[index];
            if ((second & 0xc0u) != 0x80u ||
                (text[index + 1u] & 0xc0u) != 0x80u ||
                (text[index + 2u] & 0xc0u) != 0x80u ||
                (first == 0xf0u && second < 0x90u) ||
                (first == 0xf4u && second > 0x8fu))
                return false;
            codepoint = ((uint32_t)(first & 0x07u) << 18) |
                        ((uint32_t)(second & 0x3fu) << 12) |
                        ((uint32_t)(text[index + 1u] & 0x3fu) << 6) |
                        (uint32_t)(text[index + 2u] & 0x3fu);
            index += 3u;
        } else {
            return false;
        }
        if (codepoint <= 0x1fu ||
            (codepoint >= 0x7fu && codepoint <= 0x9fu) ||
            codepoint == 0x061cu || codepoint == 0x200bu ||
            codepoint == 0x200eu || codepoint == 0x200fu ||
            (codepoint >= 0x2028u && codepoint <= 0x202eu) ||
            (codepoint >= 0x2066u && codepoint <= 0x2069u) ||
            codepoint == 0xfeffu)
            return false;
        if (codepoint != 0x20u && codepoint != 0x00a0u &&
            codepoint != 0x1680u &&
            !(codepoint >= 0x2000u && codepoint <= 0x200au) &&
            codepoint != 0x202fu && codepoint != 0x205fu &&
            codepoint != 0x3000u && codepoint != 0x200cu &&
            codepoint != 0x200du)
            has_visible_codepoint = true;
    }
    return has_visible_codepoint;
}

size_t ul_audio_encode_routing(
    uint8_t *out, size_t capacity, const uint8_t session_id[16],
    uint64_t revision, uint64_t observed_at_ns, uint8_t primary_bus,
    uint8_t bus_mask, const ul_audio_routing_bus *buses, size_t bus_count,
    const ul_audio_routing_source *sources, size_t source_count)
{
    size_t body_size = 36u, packet_size, index;
    uint8_t expected_bus = 0u;
    uint8_t *body, *cursor;
    if (out == NULL || session_id == NULL ||
        capacity < UL_AUDIO_HEADER_BYTES + 36u ||
        revision == 0u || revision > UL_AUDIO_MAX_SEQUENCE ||
        primary_bus > 5u || bus_mask == 0u || bus_mask > 0x3fu ||
        (bus_mask & (uint8_t)(1u << primary_bus)) == 0u ||
        bus_count == 0u || bus_count > 6u || buses == NULL ||
        source_count > UL_AUDIO_MAX_ROUTING_SOURCES ||
        (source_count != 0u && sources == NULL))
        return 0u;
    for (index = 0u; index < bus_count; ++index) {
        while (expected_bus < 6u &&
               (bus_mask & (uint8_t)(1u << expected_bus)) == 0u)
            ++expected_bus;
        if (expected_bus >= 6u || buses[index].bus != expected_bus ||
            !valid_utf8_label(buses[index].label, buses[index].label_length,
                              UL_AUDIO_MAX_BUS_LABEL_BYTES))
            return 0u;
        body_size += 11u + buses[index].label_length;
        ++expected_bus;
    }
    while (expected_bus < 6u &&
           (bus_mask & (uint8_t)(1u << expected_bus)) == 0u)
        ++expected_bus;
    if (expected_bus != 6u)
        return 0u;
    for (index = 0u; index < source_count; ++index) {
        if (sources[index].selected_mask == 0u ||
            (sources[index].selected_mask & ~bus_mask) != 0u ||
            !valid_utf8_label(sources[index].name, sources[index].name_length,
                              UL_AUDIO_MAX_SOURCE_NAME_BYTES) ||
            (index != 0u &&
             memcmp(sources[index - 1u].source_id,
                    sources[index].source_id, 16u) >= 0))
            return 0u;
        body_size += 19u + sources[index].name_length;
    }
    if (body_size > UL_AUDIO_MAX_ROUTING_BODY_BYTES)
        return 0u;
    packet_size = UL_AUDIO_HEADER_BYTES + body_size;
    if (capacity < packet_size)
        return 0u;

    put_header(out, 2u, UL_AUDIO_KIND_ROUTING, (uint32_t)body_size);
    body = out + UL_AUDIO_HEADER_BYTES;
    memcpy(body, session_id, 16u);
    put_u64(body + 16u, revision);
    put_u64(body + 24u, observed_at_ns);
    body[32] = primary_bus;
    body[33] = bus_mask;
    put_u16(body + 34u, (uint16_t)source_count);
    cursor = body + 36u;
    for (index = 0u; index < bus_count; ++index) {
        *cursor++ = buses[index].bus;
        put_u64(cursor, buses[index].next_sequence);
        cursor += 8u;
        put_u16(cursor, (uint16_t)buses[index].label_length);
        cursor += 2u;
        memcpy(cursor, buses[index].label, buses[index].label_length);
        cursor += buses[index].label_length;
    }
    for (index = 0u; index < source_count; ++index) {
        memcpy(cursor, sources[index].source_id, 16u);
        cursor += 16u;
        *cursor++ = sources[index].selected_mask;
        put_u16(cursor, (uint16_t)sources[index].name_length);
        cursor += 2u;
        memcpy(cursor, sources[index].name, sources[index].name_length);
        cursor += sources[index].name_length;
    }
    return packet_size;
}
