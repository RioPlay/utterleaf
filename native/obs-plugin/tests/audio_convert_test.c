// SPDX-License-Identifier: GPL-2.0-or-later
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#ifndef UL_AUDIO_CONVERT_REAL

#define audio_resampler_create ul_test_resampler_create
#define audio_resampler_destroy ul_test_resampler_destroy
#define audio_resampler_resample ul_test_resampler_resample
#include "../src/audio_convert.c"
#undef audio_resampler_create
#undef audio_resampler_destroy
#undef audio_resampler_resample

struct audio_resampler { int unused; };

enum stub_mode {
    STUB_OK, STUB_CREATE_FAIL, STUB_CONVERT_FAIL, STUB_FRAME_CHANGE,
    STUB_OFFSET, STUB_NULL_OUTPUT, STUB_NONFINITE_OUTPUT
};

static struct audio_resampler stub_resampler;
static struct resample_info stub_source;
static struct resample_info stub_destination;
static enum stub_mode stub_behavior;
static unsigned int stub_destroyed;
static float stub_output[UL_AUDIO_CONVERT_MAX_FRAMES * 2u];

audio_resampler_t *ul_test_resampler_create(const struct resample_info *destination,
                                             const struct resample_info *source)
{
    stub_destination = *destination;
    stub_source = *source;
    return stub_behavior == STUB_CREATE_FAIL ? NULL : &stub_resampler;
}

void ul_test_resampler_destroy(audio_resampler_t *resampler)
{
    assert(resampler == &stub_resampler);
    ++stub_destroyed;
}

bool ul_test_resampler_resample(audio_resampler_t *resampler, uint8_t *output[],
                                uint32_t *out_frames, uint64_t *timestamp_offset,
                                const uint8_t *const input[], uint32_t in_frames)
{
    uint32_t frame;
    assert(resampler == &stub_resampler);
    if (stub_behavior == STUB_CONVERT_FAIL)
        return false;
    *out_frames = stub_behavior == STUB_FRAME_CHANGE ? in_frames - 1u : in_frames;
    *timestamp_offset = stub_behavior == STUB_OFFSET ? 1u : 0u;
    output[0] = stub_behavior == STUB_NULL_OUTPUT ? NULL : (uint8_t *)stub_output;
    for (frame = 0u; frame < in_frames; ++frame) {
        const float *left = (const float *)input[0];
        const float *right = stub_source.speakers == SPEAKERS_MONO ? left :
                             (const float *)input[1];
        stub_output[frame * 2u] = left[frame];
        stub_output[frame * 2u + 1u] = right[frame];
    }
    if (stub_behavior == STUB_NONFINITE_OUTPUT)
        stub_output[1] = INFINITY;
    return true;
}

static void reset_stub(enum stub_mode mode)
{
    stub_behavior = mode;
    stub_destroyed = 0u;
    memset(&stub_source, 0, sizeof(stub_source));
    memset(&stub_destination, 0, sizeof(stub_destination));
    memset(stub_output, 0, sizeof(stub_output));
}

static void assert_untouched(const float *values, size_t count)
{
    size_t index;
    for (index = 0u; index < count; ++index)
        assert(values[index] == 1234.5f);
}

static void test_create_contract(void)
{
    static const uint32_t rates[] = {16000u, 32000u, 44100u, 48000u,
                                     88200u, 96000u};
    static const enum speaker_layout layouts[] = {
        SPEAKERS_MONO, SPEAKERS_STEREO, SPEAKERS_2POINT1,
        SPEAKERS_4POINT0, SPEAKERS_4POINT1, SPEAKERS_5POINT1,
        SPEAKERS_7POINT1
    };
    size_t rate, layout;
    reset_stub(STUB_OK);
    for (rate = 0u; rate < sizeof(rates) / sizeof(rates[0]); ++rate) {
        for (layout = 0u; layout < sizeof(layouts) / sizeof(layouts[0]);
             ++layout) {
            ul_audio_converter *converter = ul_audio_converter_create(
                rates[rate], layouts[layout]);
            assert(converter != NULL);
            assert(stub_source.samples_per_sec == rates[rate]);
            assert(stub_source.format == AUDIO_FORMAT_FLOAT_PLANAR);
            assert(stub_source.speakers == layouts[layout]);
            assert(stub_destination.samples_per_sec == rates[rate]);
            assert(stub_destination.format == AUDIO_FORMAT_FLOAT);
            assert(stub_destination.speakers == SPEAKERS_STEREO);
            ul_audio_converter_destroy(converter);
        }
    }
    assert(stub_destroyed == sizeof(rates) / sizeof(rates[0]) *
                             (sizeof(layouts) / sizeof(layouts[0])));
    assert(ul_audio_converter_create(22050u, SPEAKERS_STEREO) == NULL);
    assert(ul_audio_converter_create(48000u, SPEAKERS_UNKNOWN) == NULL);
    reset_stub(STUB_CREATE_FAIL);
    assert(ul_audio_converter_create(48000u, SPEAKERS_STEREO) == NULL);
    ul_audio_converter_destroy(NULL);
}

static void test_conversion_validation_and_failures(void)
{
    float left[UL_AUDIO_CONVERT_MAX_FRAMES + 1u] = {0.25f, -0.5f};
    float right[UL_AUDIO_CONVERT_MAX_FRAMES + 1u] = {0.75f, 1.0f};
    const float *planes[8] = {left, right};
    float stereo[UL_AUDIO_CONVERT_MAX_FRAMES * 2u];
    ul_audio_converter *converter;
    uint32_t out_frames = 99u;

    reset_stub(STUB_OK);
    converter = ul_audio_converter_create(48000u, SPEAKERS_STEREO);
    assert(converter != NULL);
    assert(ul_audio_converter_convert(NULL, planes, 2u, stereo, 2u,
                                      &out_frames) == UL_AUDIO_CONVERT_INVALID);
    assert(out_frames == 0u);
    assert(ul_audio_converter_convert(converter, NULL, 2u, stereo, 2u,
                                      &out_frames) == UL_AUDIO_CONVERT_INVALID);
    assert(ul_audio_converter_convert(converter, planes, 2u, NULL, 2u,
                                      &out_frames) == UL_AUDIO_CONVERT_INVALID);
    assert(ul_audio_converter_convert(converter, planes, 2u, stereo, 2u,
                                      NULL) == UL_AUDIO_CONVERT_INVALID);
    assert(ul_audio_converter_convert(converter, planes, 0u, stereo, 2u,
                                      &out_frames) == UL_AUDIO_CONVERT_INVALID);
    assert(ul_audio_converter_convert(converter, planes,
                                      UL_AUDIO_CONVERT_MAX_FRAMES + 1u,
                                      stereo, UL_AUDIO_CONVERT_MAX_FRAMES + 1u,
                                      &out_frames) == UL_AUDIO_CONVERT_INVALID);
    assert(ul_audio_converter_convert(converter, planes, 2u, stereo, 1u,
                                      &out_frames) == UL_AUDIO_CONVERT_INVALID);
    planes[1] = NULL;
    assert(ul_audio_converter_convert(converter, planes, 2u, stereo, 2u,
                                      &out_frames) == UL_AUDIO_CONVERT_INVALID);
    planes[1] = right;
    left[1] = NAN;
    assert(ul_audio_converter_convert(converter, planes, 2u, stereo, 2u,
                                      &out_frames) == UL_AUDIO_CONVERT_NONFINITE_INPUT);
    left[1] = -0.5f;

    memset(stereo, 0, sizeof(stereo));
    stereo[0] = stereo[1] = stereo[2] = stereo[3] = 1234.5f;
    stub_behavior = STUB_CONVERT_FAIL;
    assert(ul_audio_converter_convert(converter, planes, 2u, stereo, 2u,
                                      &out_frames) == UL_AUDIO_CONVERT_RESAMPLE_FAILED);
    assert_untouched(stereo, 4u);
    stub_behavior = STUB_FRAME_CHANGE;
    assert(ul_audio_converter_convert(converter, planes, 2u, stereo, 2u,
                                      &out_frames) == UL_AUDIO_CONVERT_TIMING_CHANGED);
    assert_untouched(stereo, 4u);
    stub_behavior = STUB_OFFSET;
    assert(ul_audio_converter_convert(converter, planes, 2u, stereo, 2u,
                                      &out_frames) == UL_AUDIO_CONVERT_TIMING_CHANGED);
    assert_untouched(stereo, 4u);
    stub_behavior = STUB_NULL_OUTPUT;
    assert(ul_audio_converter_convert(converter, planes, 2u, stereo, 2u,
                                      &out_frames) == UL_AUDIO_CONVERT_RESAMPLE_FAILED);
    assert_untouched(stereo, 4u);
    stub_behavior = STUB_NONFINITE_OUTPUT;
    assert(ul_audio_converter_convert(converter, planes, 2u, stereo, 2u,
                                      &out_frames) == UL_AUDIO_CONVERT_NONFINITE_OUTPUT);
    assert_untouched(stereo, 4u);
    stub_behavior = STUB_OK;
    assert(ul_audio_converter_convert(converter, planes, 2u, stereo, 2u,
                                      &out_frames) == UL_AUDIO_CONVERT_OK);
    assert(out_frames == 2u);
    assert(stereo[0] == left[0] && stereo[1] == right[0]);
    assert(stereo[2] == left[1] && stereo[3] == right[1]);
    ul_audio_converter_destroy(converter);
    assert(stub_destroyed == 1u);
}

int main(void)
{
    test_create_contract();
    test_conversion_validation_and_failures();
    puts("audio converter stub tests passed");
    return 0;
}

#else

#include "../src/audio_convert.h"

static uint32_t channels_for_layout(enum speaker_layout layout)
{
    return get_audio_channels(layout);
}

static void assert_close(float actual, float expected)
{
    assert(fabsf(actual - expected) <= 0.00001f);
}

typedef struct layout_reference {
    enum speaker_layout layout;
    uint32_t channels;
    float matrix[8][2];
} layout_reference;

static const layout_reference references[] = {
    {SPEAKERS_MONO, 1u, {{1.0f, 1.0f}}},
    {SPEAKERS_STEREO, 2u, {{1.0f, 0.0f}, {0.0f, 1.0f}}},
    {SPEAKERS_2POINT1, 3u,
     {{1.0f, 0.0f}, {0.0f, 1.0f}, {0.0f, 0.0f}}},
    {SPEAKERS_4POINT0, 4u,
     {{1.0f, 0.0f}, {0.0f, 1.0f},
      {0.707106769f, 0.707106769f}, {0.5f, 0.5f}}},
    {SPEAKERS_4POINT1, 5u,
     {{1.0f, 0.0f}, {0.0f, 1.0f},
      {0.707106769f, 0.707106769f}, {0.0f, 0.0f}, {0.5f, 0.5f}}},
    {SPEAKERS_5POINT1, 6u,
     {{1.0f, 0.0f}, {0.0f, 1.0f},
      {0.707106769f, 0.707106769f}, {0.0f, 0.0f},
      {0.707106769f, 0.0f}, {0.0f, 0.707106769f}}},
    {SPEAKERS_7POINT1, 8u,
     {{1.0f, 0.0f}, {0.0f, 1.0f},
      {0.707106769f, 0.707106769f}, {0.0f, 0.0f},
      {0.707106769f, 0.0f}, {0.0f, 0.707106769f},
      {0.707106769f, 0.0f}, {0.0f, 0.707106769f}}}
};

static void test_real_impulses(uint32_t sample_rate,
                               const layout_reference *reference)
{
    float storage[8][UL_AUDIO_CONVERT_MAX_FRAMES] = {{0}};
    const float *planes[8] = {0};
    float stereo[UL_AUDIO_CONVERT_MAX_FRAMES * 2u];
    uint32_t channel, frame;
    for (channel = 0u; channel < reference->channels; ++channel)
        planes[channel] = storage[channel];
    assert(channels_for_layout(reference->layout) == reference->channels);
    for (channel = 0u; channel < reference->channels; ++channel) {
        ul_audio_converter *converter;
        uint32_t out_frames = 0u;
        memset(storage, 0, sizeof(storage));
        memset(stereo, 0xa5, sizeof(stereo));
        storage[channel][0] = 1.0f;
        converter = ul_audio_converter_create(sample_rate, reference->layout);
        assert(converter != NULL);
        assert(ul_audio_converter_convert(converter, planes, 1024u, stereo,
                                          1024u, &out_frames) ==
               UL_AUDIO_CONVERT_OK);
        assert(out_frames == 1024u);
        assert_close(stereo[0], reference->matrix[channel][0]);
        assert_close(stereo[1], reference->matrix[channel][1]);
        for (frame = 1u; frame < 1024u; ++frame) {
            assert_close(stereo[frame * 2u], 0.0f);
            assert_close(stereo[frame * 2u + 1u], 0.0f);
        }
        ul_audio_converter_destroy(converter);
    }
}

static void test_real_reference_vector(const layout_reference *reference)
{
    float storage[8][UL_AUDIO_CONVERT_MAX_FRAMES] = {{0}};
    const float *planes[8] = {0};
    float stereo[UL_AUDIO_CONVERT_MAX_FRAMES * 2u];
    float expected_left = 0.0f, expected_right = 0.0f;
    ul_audio_converter *converter;
    uint32_t channel, out_frames = 0u;
    for (channel = 0u; channel < reference->channels; ++channel) {
        float value = (float)(channel + 1u) / 16.0f;
        planes[channel] = storage[channel];
        storage[channel][0] = value;
        storage[channel][1] = -value / 2.0f;
        expected_left += value * reference->matrix[channel][0];
        expected_right += value * reference->matrix[channel][1];
    }
    converter = ul_audio_converter_create(48000u, reference->layout);
    assert(converter != NULL);
    assert(ul_audio_converter_convert(converter, planes, 1024u, stereo,
                                      1024u, &out_frames) ==
           UL_AUDIO_CONVERT_OK);
    assert(out_frames == 1024u);
    assert_close(stereo[0], expected_left);
    assert_close(stereo[1], expected_right);
    assert_close(stereo[2], -expected_left / 2.0f);
    assert_close(stereo[3], -expected_right / 2.0f);
    ul_audio_converter_destroy(converter);
}

static void test_real_one_frame_without_clamping(void)
{
    const float left[1] = {2.5f};
    const float right[1] = {-3.0f};
    const float *planes[8] = {left, right};
    float stereo[2] = {0.0f, 0.0f};
    ul_audio_converter *converter = ul_audio_converter_create(
        48000u, SPEAKERS_STEREO);
    uint32_t out_frames = 0u;
    assert(converter != NULL);
    assert(ul_audio_converter_convert(converter, planes, 1u, stereo, 1u,
                                      &out_frames) == UL_AUDIO_CONVERT_OK);
    assert(out_frames == 1u);
    assert_close(stereo[0], 2.5f);
    assert_close(stereo[1], -3.0f);
    ul_audio_converter_destroy(converter);
}

int main(void)
{
    static const uint32_t rates[] = {16000u, 32000u, 44100u, 48000u,
                                     88200u, 96000u};
    size_t rate, layout;
    for (rate = 0u; rate < sizeof(rates) / sizeof(rates[0]); ++rate) {
        for (layout = 0u; layout < sizeof(references) / sizeof(references[0]);
             ++layout)
            test_real_impulses(rates[rate], &references[layout]);
    }
    for (layout = 0u; layout < sizeof(references) / sizeof(references[0]);
         ++layout)
        test_real_reference_vector(&references[layout]);
    test_real_one_frame_without_clamping();
    puts("audio converter pinned libobs tests passed");
    return 0;
}

#endif
