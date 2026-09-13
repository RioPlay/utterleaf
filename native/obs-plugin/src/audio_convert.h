// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_OBS_AUDIO_CONVERT_H
#define UTTERLEAF_OBS_AUDIO_CONVERT_H

#include <media-io/audio-io.h>

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define UL_AUDIO_CONVERT_MAX_FRAMES 1024u

typedef struct ul_audio_converter ul_audio_converter;

typedef enum ul_audio_convert_result {
    UL_AUDIO_CONVERT_OK = 0,
    UL_AUDIO_CONVERT_INVALID,
    UL_AUDIO_CONVERT_NONFINITE_INPUT,
    UL_AUDIO_CONVERT_RESAMPLE_FAILED,
    UL_AUDIO_CONVERT_TIMING_CHANGED,
    UL_AUDIO_CONVERT_NONFINITE_OUTPUT
} ul_audio_convert_result;

/* Worker-only API. Creation, conversion, and destruction may allocate or log
 * inside libobs and must never run on OBS's audio callback thread. The source
 * is native FLOAT_PLANAR and the destination is interleaved FLOAT stereo at
 * the same rate. All known OBS speaker layouts are accepted. */
ul_audio_converter *ul_audio_converter_create(
    uint32_t sample_rate, enum speaker_layout speakers);

/* On success, writes exactly frames stereo frames and sets out_frames=frames.
 * A same-rate conversion that reports a frame-count change or timestamp offset
 * is rejected so the caller can preserve the original OBS timestamp. On any
 * failure, stereo is untouched and out_frames is set to zero when non-null.
 * Destroy rather than reuse the converter after a resampler, timing, or output
 * failure because libobs may already have advanced its internal state. */
ul_audio_convert_result ul_audio_converter_convert(
    ul_audio_converter *converter, const float *const planes[8],
    uint32_t frames, float *stereo, uint32_t stereo_capacity_frames,
    uint32_t *out_frames);

void ul_audio_converter_destroy(ul_audio_converter *converter);

#ifdef __cplusplus
}
#endif

#endif
