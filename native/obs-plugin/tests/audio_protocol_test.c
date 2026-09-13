// SPDX-License-Identifier: GPL-2.0-or-later
#include "../src/audio_protocol.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <fcntl.h>
#include <io.h>
#include <stdlib.h>
#include <string.h>

static const uint8_t session[16] = {
    '0','1','2','3','4','5','6','7','8','9','a','b','c','d','e','f'
};

static void assert_untouched(const uint8_t *out, size_t size)
{
    size_t index;
    for (index = 0; index < size; ++index)
        assert(out[index] == 0xa5u);
}

static void reset(uint8_t *out, size_t size)
{
    memset(out, 0xa5, size);
}

static void test_fixed_vectors(void)
{
    static const uint8_t expected_start[] = {
        'U','L','A','P',1,1,0,0,30,0,0,0,
        '0','1','2','3','4','5','6','7','8','9','a','b','c','d','e','f',
        0x80,0xbb,0,0,1,6,0x7b,0,0,0,0,0,0,0
    };
    static const uint8_t expected_audio[] = {
        'U','L','A','P',1,2,0,0,45,0,0,0,
        '0','1','2','3','4','5','6','7','8','9','a','b','c','d','e','f',1,
        7,0,0,0,0,0,0,0,0xc8,1,0,0,0,0,0,0,1,0,0,0,
        0,0,0x80,0x3e,0,0,0x80,0xbe
    };
    static const uint8_t expected_gap[] = {
        'U','L','A','P',1,3,0,0,41,0,0,0,
        '0','1','2','3','4','5','6','7','8','9','a','b','c','d','e','f',1,
        8,0,0,0,0,0,0,0,2,0,0,0,0,0,0,0,0x15,3,0,0,0,0,0,0
    };
    static const uint8_t expected_end[] = {
        'U','L','A','P',1,4,0,0,36,0,0,0,
        '0','1','2','3','4','5','6','7','8','9','a','b','c','d','e','f',1,2,
        1,9,0,0,0,0,0,0,0,
        2,0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff
    };
    const float pcm[2] = {0.25f, -0.25f};
    const ul_audio_end_sequence entries[2] = {
        {1, true, 9}, {2, false, 0}
    };
    uint8_t out[64];
    size_t size;

    size = ul_audio_encode_start(out, sizeof(out), session, 48000, 1, 6, 123);
    assert(size == sizeof(expected_start));
    assert(memcmp(out, expected_start, size) == 0);
    size = ul_audio_encode_audio(out, sizeof(out), session, 1, 7, 456, 1, pcm);
    assert(size == sizeof(expected_audio));
    assert(memcmp(out, expected_audio, size) == 0);
    size = ul_audio_encode_gap(out, sizeof(out), session, 1, 8, 2, 789);
    assert(size == sizeof(expected_gap));
    assert(memcmp(out, expected_gap, size) == 0);
    size = ul_audio_encode_end(out, sizeof(out), session,
                               UL_AUDIO_END_STREAM_STOPPED, entries, 2);
    assert(size == sizeof(expected_end));
    assert(memcmp(out, expected_end, size) == 0);
}

static void test_explicit_versions(void)
{
    const float pcm[2] = {0.25f, -0.25f};
    const ul_audio_end_sequence entry = {0u, true, 0u};
    uint8_t out[64];
    assert(ul_audio_encode_start_version(2u, out, sizeof(out), session,
                                         48000u, 0u, 1u, 0u) == 42u);
    assert(out[4] == 2u && out[5] == 1u);
    assert(ul_audio_encode_audio_version(2u, out, sizeof(out), session,
                                         0u, 0u, 0u, 1u, pcm) == 57u);
    assert(out[4] == 2u && out[5] == 2u);
    assert(ul_audio_encode_gap_version(2u, out, sizeof(out), session,
                                       0u, 0u, 1u, 0u) == 53u);
    assert(out[4] == 2u && out[5] == 3u);
    assert(ul_audio_encode_end_version(2u, out, sizeof(out), session,
                                       UL_AUDIO_END_STREAM_STOPPED,
                                       &entry, 1u) == 39u);
    assert(out[4] == 2u && out[5] == 4u);
    reset(out, sizeof(out));
    assert(ul_audio_encode_start_version(0u, out, sizeof(out), session,
                                         48000u, 0u, 1u, 0u) == 0u);
    assert(ul_audio_encode_audio_version(3u, out, sizeof(out), session,
                                         0u, 0u, 0u, 1u, pcm) == 0u);
    assert(ul_audio_encode_gap_version(0u, out, sizeof(out), session,
                                       0u, 0u, 1u, 0u) == 0u);
    assert(ul_audio_encode_end_version(3u, out, sizeof(out), session,
                                       UL_AUDIO_END_STREAM_STOPPED,
                                       &entry, 1u) == 0u);
    assert_untouched(out, sizeof(out));
}

static void test_start_validation(void)
{
    static const uint32_t rates[] = {16000, 32000, 44100, 48000, 88200, 96000};
    uint8_t out[64];
    size_t index;
    for (index = 0; index < sizeof(rates) / sizeof(rates[0]); ++index)
        assert(ul_audio_encode_start(out, sizeof(out), session, rates[index], 0, 1, 0) == 42u);
    reset(out, sizeof(out));
    assert(ul_audio_encode_start(NULL, sizeof(out), session, 48000, 0, 1, 0) == 0u);
    assert(ul_audio_encode_start(out, sizeof(out), NULL, 48000, 0, 1, 0) == 0u);
    assert(ul_audio_encode_start(out, 41, session, 48000, 0, 1, 0) == 0u);
    assert(ul_audio_encode_start(out, sizeof(out), session, 22050, 0, 1, 0) == 0u);
    assert(ul_audio_encode_start(out, sizeof(out), session, 48000, 6, 1, 0) == 0u);
    assert(ul_audio_encode_start(out, sizeof(out), session, 48000, 1, 1, 0) == 0u);
    assert(ul_audio_encode_start(out, sizeof(out), session, 48000, 0, 0, 0) == 0u);
    assert(ul_audio_encode_start(out, sizeof(out), session, 48000, 0, 64, 0) == 0u);
    assert_untouched(out, sizeof(out));
}

static void test_audio_validation_and_maximum(void)
{
    float *pcm = malloc((size_t)UL_AUDIO_MAX_FRAMES * 2u * sizeof(*pcm));
    uint8_t *out = malloc(UL_AUDIO_MAX_PACKET_BYTES);
    size_t index;
    assert(pcm != NULL && out != NULL);
    for (index = 0; index < (size_t)UL_AUDIO_MAX_FRAMES * 2u; ++index)
        pcm[index] = index & 1u ? -1000.0f : 1000.0f;
    assert(ul_audio_encode_audio(out, UL_AUDIO_MAX_PACKET_BYTES, session, 5,
                                 UL_AUDIO_MAX_SEQUENCE, UINT64_MAX,
                                 UL_AUDIO_MAX_FRAMES, pcm) == UL_AUDIO_MAX_PACKET_BYTES);
    reset(out, UL_AUDIO_MAX_PACKET_BYTES);
    assert(ul_audio_encode_audio(out, UL_AUDIO_MAX_PACKET_BYTES - 1u, session, 0,
                                 0, 0, UL_AUDIO_MAX_FRAMES, pcm) == 0u);
    assert_untouched(out, UL_AUDIO_MAX_PACKET_BYTES);
    assert(ul_audio_encode_audio(out, UL_AUDIO_MAX_PACKET_BYTES, NULL, 0, 0, 0, 1, pcm) == 0u);
    assert(ul_audio_encode_audio(out, UL_AUDIO_MAX_PACKET_BYTES, session, 6, 0, 0, 1, pcm) == 0u);
    assert(ul_audio_encode_audio(out, UL_AUDIO_MAX_PACKET_BYTES, session, 0,
                                 UINT64_MAX, 0, 1, pcm) == 0u);
    assert(ul_audio_encode_audio(out, UL_AUDIO_MAX_PACKET_BYTES, session, 0, 0, 0, 0, pcm) == 0u);
    assert(ul_audio_encode_audio(out, UL_AUDIO_MAX_PACKET_BYTES, session, 0, 0, 0,
                                 UL_AUDIO_MAX_FRAMES + 1u, pcm) == 0u);
    assert(ul_audio_encode_audio(out, UL_AUDIO_MAX_PACKET_BYTES, session, 0, 0, 0, 1, NULL) == 0u);
    pcm[7] = NAN;
    assert(ul_audio_encode_audio(out, UL_AUDIO_MAX_PACKET_BYTES, session, 0, 0, 0, 4, pcm) == 0u);
    assert_untouched(out, UL_AUDIO_MAX_PACKET_BYTES);
    pcm[7] = INFINITY;
    assert(ul_audio_encode_audio(out, UL_AUDIO_MAX_PACKET_BYTES, session, 0, 0, 0, 4, pcm) == 0u);
    assert_untouched(out, UL_AUDIO_MAX_PACKET_BYTES);
    free(out);
    free(pcm);
}

static void test_gap_validation(void)
{
    uint8_t out[64];
    reset(out, sizeof(out));
    assert(ul_audio_encode_gap(out, sizeof(out), session, 5,
                               UL_AUDIO_MAX_SEQUENCE, 1, UINT64_MAX) == 53u);
    reset(out, sizeof(out));
    assert(ul_audio_encode_gap(out, 52, session, 0, 0, 1, 0) == 0u);
    assert(ul_audio_encode_gap(out, sizeof(out), NULL, 0, 0, 1, 0) == 0u);
    assert(ul_audio_encode_gap(out, sizeof(out), session, 6, 0, 1, 0) == 0u);
    assert(ul_audio_encode_gap(out, sizeof(out), session, 0, UINT64_MAX, 1, 0) == 0u);
    assert(ul_audio_encode_gap(out, sizeof(out), session, 0, 0, 0, 0) == 0u);
    assert(ul_audio_encode_gap(out, sizeof(out), session, 0,
                               UL_AUDIO_MAX_SEQUENCE, 2, 0) == 0u);
    assert_untouched(out, sizeof(out));
}

static void test_end_validation(void)
{
    ul_audio_end_sequence entries[7] = {{0, false, 9}, {1, true, UL_AUDIO_MAX_SEQUENCE}};
    uint8_t out[96];
    reset(out, sizeof(out));
    assert(ul_audio_encode_end(out, sizeof(out), session, UL_AUDIO_END_OBS_EXIT,
                               entries, 2) == 48u);
    assert(ul_audio_encode_end(out, sizeof(out), session, UL_AUDIO_END_DISARMED,
                               NULL, 0) == 30u);
    assert(memcmp(out, "ULAP\1\4\0\0\22\0\0\0", 12u) == 0);
    assert(memcmp(out + 12u, session, 16u) == 0);
    assert(out[28] == UL_AUDIO_END_DISARMED && out[29] == 0u);
    reset(out, sizeof(out));
    assert(ul_audio_encode_end(out, 47, session, UL_AUDIO_END_OBS_EXIT, entries, 2) == 0u);
    assert(ul_audio_encode_end(out, sizeof(out), NULL, UL_AUDIO_END_OBS_EXIT, entries, 2) == 0u);
    assert(ul_audio_encode_end(out, sizeof(out), session, 0, entries, 2) == 0u);
    assert(ul_audio_encode_end(out, sizeof(out), session, 6, entries, 2) == 0u);
    assert(ul_audio_encode_end(out, sizeof(out), session, UL_AUDIO_END_OBS_EXIT, NULL, 2) == 0u);
    assert(ul_audio_encode_end(out, sizeof(out), session, UL_AUDIO_END_OBS_EXIT, entries, 0) == 0u);
    assert(ul_audio_encode_end(out, 29u, session, UL_AUDIO_END_DISARMED, NULL, 0) == 0u);
    assert(ul_audio_encode_end(out, sizeof(out), session, UL_AUDIO_END_OBS_EXIT, entries, 7) == 0u);
    entries[1].bus = 0;
    assert(ul_audio_encode_end(out, sizeof(out), session, UL_AUDIO_END_OBS_EXIT, entries, 2) == 0u);
    entries[1].bus = 6;
    assert(ul_audio_encode_end(out, sizeof(out), session, UL_AUDIO_END_OBS_EXIT, entries, 2) == 0u);
    entries[1].bus = 1;
    entries[1].sequence = UINT64_MAX;
    assert(ul_audio_encode_end(out, sizeof(out), session, UL_AUDIO_END_OBS_EXIT, entries, 2) == 0u);
    assert_untouched(out, sizeof(out));
}

static size_t encode_routing_fixture(uint8_t *out, size_t capacity)
{
    static const uint8_t main_label[] = "Main";
    static const uint8_t aux_label[] = "Aux";
    static const uint8_t alpha_name[] = "A";
    static const uint8_t beta_name[] = "B";
    static const ul_audio_routing_bus buses[] = {
        {1u, 7u, main_label, sizeof(main_label) - 1u},
        {2u, UINT64_MAX, aux_label, sizeof(aux_label) - 1u},
    };
    static const ul_audio_routing_source sources[] = {
        {{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1}, 2u,
         alpha_name, sizeof(alpha_name) - 1u},
        {{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2}, 4u,
         beta_name, sizeof(beta_name) - 1u},
    };
    return ul_audio_encode_routing(
        out, capacity, session, 1u, UINT64_C(0x0102030405060708),
        1u, 6u, buses, 2u, sources, 2u);
}

static void test_routing_fixed_vector(void)
{
    static const uint8_t expected[] = {
        'U','L','A','P',2,5,0,0,105,0,0,0,
        '0','1','2','3','4','5','6','7','8','9','a','b','c','d','e','f',
        1,0,0,0,0,0,0,0, 8,7,6,5,4,3,2,1, 1,6,2,0,
        1, 7,0,0,0,0,0,0,0, 4,0, 'M','a','i','n',
        2, 0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff, 3,0, 'A','u','x',
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1, 2, 1,0, 'A',
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2, 4, 1,0, 'B',
    };
    uint8_t out[sizeof(expected)];
    size_t size = encode_routing_fixture(out, sizeof(out));
    assert(size == sizeof(expected));
    assert(memcmp(out, expected, sizeof(expected)) == 0);
}

static void test_routing_validation(void)
{
    static const uint8_t label[] = "Main";
    static const uint8_t name[] = "Input";
    static const uint8_t emoji[] = {
        0xf0,0x9f,0x91,0xa9, 0xe2,0x80,0x8d, 0xf0,0x9f,0x92,0xbb
    };
    static const uint8_t persian_zwnj[] = {
        0xd9,0x85, 0xdb,0x8c, 0xe2,0x80,0x8c,
        0xd8,0xb1, 0xd9,0x88, 0xd9,0x85
    };
    static const uint8_t blank_whitespace[] = {' ', 0xc2,0xa0};
    static const uint8_t blank_joiners[] = {
        0xe2,0x80,0x8c, 0xe2,0x80,0x8d
    };
    static const uint8_t blank_ideographic[] = {0xe3,0x80,0x80};
    static const uint8_t invalid_text[][3] = {
        {'x','\n','y'}, {0xc0,0xaf,'x'}, {0xed,0xa0,0x80},
        {0xf4,0x90,0x80}, {0xc2,0x85,'x'}, {0xe2,0x80,0xa8},
        {0xe2,0x81,0xa6}, {0xe2,'x','y'}, {0xd8,0x9c,'x'},
        {0xe2,0x80,0x8b}, {0xe2,0x80,0x8e}, {0xe2,0x80,0x8f},
        {0xef,0xbb,0xbf},
    };
    ul_audio_routing_bus buses[2] = {
        {0u, 0u, label, sizeof(label) - 1u},
        {1u, UINT64_MAX, emoji, sizeof(emoji)},
    };
    ul_audio_routing_source sources[2] = {
        {{0}, 1u, name, sizeof(name) - 1u},
        {{0}, 2u, name, sizeof(name) - 1u},
    };
    uint8_t out[256];
    size_t index;
    sources[1].source_id[15] = 1u;
    assert(ul_audio_encode_routing(out, sizeof(out), session, 1u, 0u,
                                   0u, 3u, buses, 2u, sources, 2u) != 0u);
    reset(out, sizeof(out));
#define BAD_ROUTE(...) do { \
    assert(ul_audio_encode_routing(__VA_ARGS__) == 0u); \
    assert_untouched(out, sizeof(out)); \
} while (0)
    BAD_ROUTE(NULL, sizeof(out), session, 1u, 0u, 0u, 3u,
              buses, 2u, sources, 2u);
    BAD_ROUTE(out, sizeof(out), NULL, 1u, 0u, 0u, 3u,
              buses, 2u, sources, 2u);
    BAD_ROUTE(out, sizeof(out), session, 0u, 0u, 0u, 3u,
              buses, 2u, sources, 2u);
    BAD_ROUTE(out, sizeof(out), session, UINT64_MAX, 0u, 0u, 3u,
              buses, 2u, sources, 2u);
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 2u, 1u,
              buses, 1u, sources, 1u);
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 0u,
              buses, 0u, sources, 0u);
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 64u,
              buses, 1u, sources, 1u);
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
              NULL, 2u, sources, 2u);
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
              buses, 2u, NULL, 1u);
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
              buses, 2u, sources, UL_AUDIO_MAX_ROUTING_SOURCES + 1u);
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
              buses, 1u, sources, 2u);
    buses[0].bus = 1u;
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
              buses, 2u, sources, 2u);
    buses[0].bus = 0u;
    buses[0].label_length = 0u;
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
              buses, 2u, sources, 2u);
    buses[0].label_length = UL_AUDIO_MAX_BUS_LABEL_BYTES + 1u;
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
              buses, 2u, sources, 2u);
    buses[0].label_length = sizeof(label) - 1u;
    for (index = 0u; index < sizeof(invalid_text) / sizeof(invalid_text[0]); ++index) {
        buses[0].label = invalid_text[index];
        buses[0].label_length = sizeof(invalid_text[index]);
        BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
                  buses, 2u, sources, 2u);
    }
    buses[0].label = blank_whitespace;
    buses[0].label_length = sizeof(blank_whitespace);
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
              buses, 2u, sources, 2u);
    buses[0].label = blank_joiners;
    buses[0].label_length = sizeof(blank_joiners);
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
              buses, 2u, sources, 2u);
    buses[0].label = blank_ideographic;
    buses[0].label_length = sizeof(blank_ideographic);
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
              buses, 2u, sources, 2u);
    buses[0].label = persian_zwnj;
    buses[0].label_length = sizeof(persian_zwnj);
    assert(ul_audio_encode_routing(out, sizeof(out), session, 1u, 0u,
                                   0u, 3u, buses, 2u, sources, 2u) != 0u);
    reset(out, sizeof(out));
    buses[0].label = label;
    buses[0].label_length = sizeof(label) - 1u;
    sources[0].selected_mask = 0u;
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
              buses, 2u, sources, 2u);
    sources[0].selected_mask = 4u;
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
              buses, 2u, sources, 2u);
    sources[0].selected_mask = 1u;
    sources[0].name_length = UL_AUDIO_MAX_SOURCE_NAME_BYTES + 1u;
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
              buses, 2u, sources, 2u);
    sources[0].name_length = sizeof(name) - 1u;
    memcpy(sources[1].source_id, sources[0].source_id, 16u);
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
              buses, 2u, sources, 2u);
    sources[1].source_id[15] = 1u;
    sources[0].source_id[15] = 2u;
    BAD_ROUTE(out, sizeof(out), session, 1u, 0u, 0u, 3u,
              buses, 2u, sources, 2u);
#undef BAD_ROUTE
}

static void test_routing_maximum_and_capacity(void)
{
    uint8_t *out = malloc(UL_AUDIO_MAX_ROUTING_PACKET_BYTES);
    uint8_t label[UL_AUDIO_MAX_BUS_LABEL_BYTES];
    uint8_t name[UL_AUDIO_MAX_SOURCE_NAME_BYTES];
    ul_audio_routing_bus buses[6];
    ul_audio_routing_source sources[UL_AUDIO_MAX_ROUTING_SOURCES];
    size_t index;
    assert(out != NULL);
    memset(label, 'L', sizeof(label));
    memset(name, 'N', sizeof(name));
    memset(sources, 0, sizeof(sources));
    for (index = 0u; index < 6u; ++index)
        buses[index] = (ul_audio_routing_bus){
            (uint8_t)index, (uint64_t)index, label, sizeof(label)};
    for (index = 0u; index < UL_AUDIO_MAX_ROUTING_SOURCES; ++index) {
        sources[index].source_id[15] = (uint8_t)index;
        sources[index].selected_mask = 1u;
        sources[index].name = name;
        sources[index].name_length = sizeof(name);
    }
    assert(ul_audio_encode_routing(
        out, UL_AUDIO_MAX_ROUTING_PACKET_BYTES, session,
        UL_AUDIO_MAX_SEQUENCE, UINT64_MAX, 0u, 0x3fu,
        buses, 6u, sources, UL_AUDIO_MAX_ROUTING_SOURCES) ==
        UL_AUDIO_MAX_ROUTING_PACKET_BYTES);
    reset(out, UL_AUDIO_MAX_ROUTING_PACKET_BYTES);
    assert(ul_audio_encode_routing(
        out, UL_AUDIO_MAX_ROUTING_PACKET_BYTES - 1u, session,
        1u, 0u, 0u, 0x3fu, buses, 6u,
        sources, UL_AUDIO_MAX_ROUTING_SOURCES) == 0u);
    assert_untouched(out, UL_AUDIO_MAX_ROUTING_PACKET_BYTES);
    free(out);
}

static int emit_frames(void)
{
    const float pcm[2] = {0.25f, -0.25f};
    const ul_audio_end_sequence entries[2] = {{1, true, 9}, {2, false, 0}};
    uint8_t out[64];
    size_t sizes[4], index;
    if (_setmode(_fileno(stdout), _O_BINARY) == -1) return 1;
    /* 0x0a must remain one wire byte even with the Windows CRT. */
    sizes[0] = ul_audio_encode_start(out, sizeof(out), session, 48000, 1, 6, 10);
    if (sizes[0] == 0u || fwrite(out, 1, sizes[0], stdout) != sizes[0]) return 1;
    sizes[1] = ul_audio_encode_audio(out, sizeof(out), session, 1, 7, 456, 1, pcm);
    if (sizes[1] == 0u || fwrite(out, 1, sizes[1], stdout) != sizes[1]) return 1;
    sizes[2] = ul_audio_encode_gap(out, sizeof(out), session, 1, 8, 2, 789);
    if (sizes[2] == 0u || fwrite(out, 1, sizes[2], stdout) != sizes[2]) return 1;
    sizes[3] = ul_audio_encode_end(out, sizeof(out), session,
                                   UL_AUDIO_END_STREAM_STOPPED, entries, 2);
    if (sizes[3] == 0u || fwrite(out, 1, sizes[3], stdout) != sizes[3]) return 1;
    for (index = 0; index < 4u; ++index)
        assert(sizes[index] > 0u);
    return 0;
}

static int emit_frames_v2(void)
{
    const float pcm[2] = {0.25f, -0.25f};
    const ul_audio_end_sequence entries[2] = {{1, true, 9}, {2, false, 0}};
    uint8_t out[64];
    size_t size;
    if (_setmode(_fileno(stdout), _O_BINARY) == -1)
        return 1;
#define EMIT(expression) do { \
    size = (expression); \
    if (size == 0u || fwrite(out, 1u, size, stdout) != size) return 1; \
} while (0)
    EMIT(ul_audio_encode_start_version(2u, out, sizeof(out), session,
                                       48000u, 1u, 6u, 10u));
    EMIT(ul_audio_encode_audio_version(2u, out, sizeof(out), session,
                                       1u, 7u, 456u, 1u, pcm));
    EMIT(ul_audio_encode_gap_version(2u, out, sizeof(out), session,
                                     1u, 8u, 2u, 789u));
    EMIT(ul_audio_encode_end_version(2u, out, sizeof(out), session,
                                     UL_AUDIO_END_STREAM_STOPPED,
                                     entries, 2u));
#undef EMIT
    return 0;
}

static int emit_routing(void)
{
    uint8_t out[128];
    size_t size;
    if (_setmode(_fileno(stdout), _O_BINARY) == -1)
        return 1;
    size = encode_routing_fixture(out, sizeof(out));
    return size == 0u || fwrite(out, 1u, size, stdout) != size;
}

int main(int argc, char **argv)
{
    if (argc == 2 && strcmp(argv[1], "--emit") == 0)
        return emit_frames();
    if (argc == 2 && strcmp(argv[1], "--emit-v2") == 0)
        return emit_frames_v2();
    if (argc == 2 && strcmp(argv[1], "--emit-routing") == 0)
        return emit_routing();
    assert(argc == 1);
    test_fixed_vectors();
    test_explicit_versions();
    test_start_validation();
    test_audio_validation_and_maximum();
    test_gap_validation();
    test_end_validation();
    test_routing_fixed_vector();
    test_routing_validation();
    test_routing_maximum_and_capacity();
    puts("native ULAP encoder and routing vectors and bounds passed");
    return 0;
}
