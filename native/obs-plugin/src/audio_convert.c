// SPDX-License-Identifier: GPL-2.0-or-later
#include "audio_convert.h"

#include <media-io/audio-resampler.h>

#include <math.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

struct ul_audio_converter {
    audio_resampler_t *resampler;
    uint32_t channels;
};

static bool supported_rate(uint32_t sample_rate)
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

static uint32_t layout_channels(enum speaker_layout speakers)
{
    switch (speakers) {
    case SPEAKERS_MONO: return 1u;
    case SPEAKERS_STEREO: return 2u;
    case SPEAKERS_2POINT1: return 3u;
    case SPEAKERS_4POINT0: return 4u;
    case SPEAKERS_4POINT1: return 5u;
    case SPEAKERS_5POINT1: return 6u;
    case SPEAKERS_7POINT1: return 8u;
    default: return 0u;
    }
}

ul_audio_converter *ul_audio_converter_create(
    uint32_t sample_rate, enum speaker_layout speakers)
{
    struct resample_info source;
    struct resample_info destination;
    ul_audio_converter *converter;
    uint32_t channels = layout_channels(speakers);
    if (!supported_rate(sample_rate) || channels == 0u)
        return NULL;
    converter = calloc(1u, sizeof(*converter));
    if (converter == NULL)
        return NULL;
    source = (struct resample_info){sample_rate, AUDIO_FORMAT_FLOAT_PLANAR,
                                    speakers};
    destination = (struct resample_info){sample_rate, AUDIO_FORMAT_FLOAT,
                                         SPEAKERS_STEREO};
    converter->resampler = audio_resampler_create(&destination, &source);
    if (converter->resampler == NULL) {
        free(converter);
        return NULL;
    }
    converter->channels = channels;
    return converter;
}

ul_audio_convert_result ul_audio_converter_convert(
    ul_audio_converter *converter, const float *const planes[8],
    uint32_t frames, float *stereo, uint32_t stereo_capacity_frames,
    uint32_t *out_frames)
{
    const uint8_t *inputs[8] = {0};
    uint8_t *outputs[8] = {0};
    uint32_t converted_frames = 0u;
    uint64_t timestamp_offset = 0u;
    uint32_t channel, frame;
    if (out_frames != NULL)
        *out_frames = 0u;
    if (converter == NULL || planes == NULL || stereo == NULL ||
        out_frames == NULL || frames == 0u ||
        frames > UL_AUDIO_CONVERT_MAX_FRAMES ||
        stereo_capacity_frames < frames)
        return UL_AUDIO_CONVERT_INVALID;
    for (channel = 0u; channel < converter->channels; ++channel) {
        if (planes[channel] == NULL)
            return UL_AUDIO_CONVERT_INVALID;
        for (frame = 0u; frame < frames; ++frame) {
            if (!isfinite(planes[channel][frame]))
                return UL_AUDIO_CONVERT_NONFINITE_INPUT;
        }
        inputs[channel] = (const uint8_t *)planes[channel];
    }
    if (!audio_resampler_resample(converter->resampler, outputs,
                                  &converted_frames, &timestamp_offset,
                                  inputs, frames))
        return UL_AUDIO_CONVERT_RESAMPLE_FAILED;
    if (converted_frames != frames || timestamp_offset != 0u)
        return UL_AUDIO_CONVERT_TIMING_CHANGED;
    if (outputs[0] == NULL)
        return UL_AUDIO_CONVERT_RESAMPLE_FAILED;
    for (frame = 0u; frame < frames * 2u; ++frame) {
        if (!isfinite(((const float *)outputs[0])[frame]))
            return UL_AUDIO_CONVERT_NONFINITE_OUTPUT;
    }
    memcpy(stereo, outputs[0], (size_t)frames * 2u * sizeof(*stereo));
    *out_frames = frames;
    return UL_AUDIO_CONVERT_OK;
}

void ul_audio_converter_destroy(ul_audio_converter *converter)
{
    if (converter == NULL)
        return;
    audio_resampler_destroy(converter->resampler);
    memset(converter, 0, sizeof(*converter));
    free(converter);
}
