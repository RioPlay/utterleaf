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
    reset(out, sizeof(out));
    assert(ul_audio_encode_end(out, 47, session, UL_AUDIO_END_OBS_EXIT, entries, 2) == 0u);
    assert(ul_audio_encode_end(out, sizeof(out), NULL, UL_AUDIO_END_OBS_EXIT, entries, 2) == 0u);
    assert(ul_audio_encode_end(out, sizeof(out), session, 0, entries, 2) == 0u);
    assert(ul_audio_encode_end(out, sizeof(out), session, 6, entries, 2) == 0u);
    assert(ul_audio_encode_end(out, sizeof(out), session, UL_AUDIO_END_OBS_EXIT, NULL, 2) == 0u);
    assert(ul_audio_encode_end(out, sizeof(out), session, UL_AUDIO_END_OBS_EXIT, entries, 0) == 0u);
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

int main(int argc, char **argv)
{
    if (argc == 2 && strcmp(argv[1], "--emit") == 0)
        return emit_frames();
    assert(argc == 1);
    test_fixed_vectors();
    test_start_validation();
    test_audio_validation_and_maximum();
    test_gap_validation();
    test_end_validation();
    puts("native ULAP encoder vectors and bounds passed");
    return 0;
}
