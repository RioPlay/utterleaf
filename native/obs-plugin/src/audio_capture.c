// SPDX-License-Identifier: GPL-2.0-or-later
#include "audio_capture.h"

#include "audio_convert.h"
#include "audio_queue.h"

#include <obs-frontend-api.h>
#include <obs-module.h>

#include <windows.h>

#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>

struct ul_audio_capture {
    atomic_uint refs;
    atomic_bool sealed;
    atomic_bool failed;
    atomic_bool origin_ready;
    atomic_uint_fast64_t origin_ns;
    ul_audio_capture_spec spec;
    ul_audio_queue *queues[UL_AUDIO_CAPTURE_MIXES];
    ul_audio_converter *converters[UL_AUDIO_CAPTURE_MIXES];
    uintptr_t generation;
    uint8_t lowest_bus;
    uint8_t seen_mask; /* Single OBS audio-thread producer only. */
    bool connected;   /* Protected by capture_sink.lock. */
};

typedef struct ul_audio_capture_sink {
    SRWLOCK lock;
    _Atomic(ul_audio_capture *) active;
    atomic_uint_fast64_t readers;
    bool closed;
    bool retiring;
    uintptr_t hook_audio;
    uintptr_t hook_generation;
    uint8_t hooked_mask;
} ul_audio_capture_sink;

static ul_audio_capture_sink capture_sink = {
    SRWLOCK_INIT,
    ATOMIC_VAR_INIT(NULL),
    ATOMIC_VAR_INIT(0u),
    false,
    false,
    0u,
    0u,
    0u,
};

#ifndef UL_AUDIO_CAPTURE_AFTER_READER_ENTER
#define UL_AUDIO_CAPTURE_AFTER_READER_ENTER() ((void)0)
#endif

#ifndef UL_AUDIO_CAPTURE_AFTER_EXTERNAL_RETIRE
#define UL_AUDIO_CAPTURE_AFTER_EXTERNAL_RETIRE() ((void)0)
#endif

static bool supported_rate(uint32_t rate)
{
    switch (rate) {
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

static bool valid_spec(const ul_audio_capture_spec *spec)
{
    uint32_t channels;
    if (spec == NULL || !supported_rate(spec->sample_rate) ||
        spec->primary_bus >= UL_AUDIO_CAPTURE_MIXES ||
        spec->mix_mask == 0u || (spec->mix_mask & ~0x3fu) != 0u ||
        (spec->mix_mask & (1u << spec->primary_bus)) == 0u ||
        spec->audio_identity == 0u || spec->output_identity == 0u)
        return false;
    channels = get_audio_channels((enum speaker_layout)spec->speakers);
    return channels != 0u && channels <= 8u && channels == spec->channels;
}

static bool same_spec(const ul_audio_capture_spec *left,
                      const ul_audio_capture_spec *right)
{
    return left->sample_rate == right->sample_rate &&
           left->speakers == right->speakers &&
           left->channels == right->channels &&
           left->primary_bus == right->primary_bus &&
           left->mix_mask == right->mix_mask &&
           left->audio_identity == right->audio_identity &&
           left->output_identity == right->output_identity;
}

static void fail_capture(ul_audio_capture *capture)
{
    atomic_store_explicit(&capture->failed, true, memory_order_release);
}

static void audio_callback(void *parameter, size_t mix_idx,
                           struct audio_data *data)
{
    ul_audio_capture *capture;
    const uint8_t *planes[8] = {0};
    ul_audio_queue_result pushed;
    uint8_t bit;
    uint32_t channel;

    if (parameter != &capture_sink)
        return;
    atomic_fetch_add_explicit(&capture_sink.readers, 1u,
                              memory_order_seq_cst);
    UL_AUDIO_CAPTURE_AFTER_READER_ENTER();
    capture = atomic_load_explicit(&capture_sink.active,
                                   memory_order_seq_cst);
    if (capture == NULL)
        goto leave;
    if (mix_idx >= UL_AUDIO_CAPTURE_MIXES) {
        fail_capture(capture);
        goto leave;
    }
    bit = (uint8_t)(1u << mix_idx);
    if ((capture->spec.mix_mask & bit) == 0u)
        goto leave; /* An inert stale hook may be called before cleanup. */
    if (atomic_load_explicit(&capture->failed, memory_order_acquire))
        goto leave;
    if (data == NULL || data->frames == 0u ||
        data->frames > UL_AUDIO_BLOCK_FRAMES) {
        fail_capture(capture);
        goto leave;
    }
    for (channel = 0u; channel < capture->spec.channels; ++channel) {
        if (data->data[channel] == NULL) {
            fail_capture(capture);
            goto leave;
        }
        planes[channel] = data->data[channel];
    }

    if (!atomic_load_explicit(&capture->origin_ready,
                              memory_order_acquire)) {
        if (mix_idx != capture->lowest_bus)
            goto leave;
        atomic_store_explicit(&capture->origin_ns, data->timestamp,
                              memory_order_relaxed);
        atomic_store_explicit(&capture->origin_ready, true,
                              memory_order_release);
    }
    if ((capture->seen_mask & bit) == 0u) {
        uint64_t origin = atomic_load_explicit(&capture->origin_ns,
                                               memory_order_relaxed);
        if (data->timestamp != origin) {
            fail_capture(capture);
            goto leave;
        }
        capture->seen_mask |= bit;
    }
    pushed = ul_audio_queue_push(capture->queues[mix_idx], planes,
                                 data->frames, data->timestamp);
    if (pushed != UL_AUDIO_QUEUE_OK && pushed != UL_AUDIO_QUEUE_DROPPED)
        fail_capture(capture);

leave:
    atomic_fetch_sub_explicit(&capture_sink.readers, 1u,
                              memory_order_seq_cst);
}

static void drain_readers(void)
{
    while (atomic_load_explicit(&capture_sink.readers,
                                memory_order_seq_cst) != 0u)
        SwitchToThread();
}

static void stop_queues(ul_audio_capture *capture)
{
    uint8_t bus;
    if (capture == NULL)
        return;
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        if (capture->queues[bus] != NULL)
            ul_audio_queue_stop(capture->queues[bus]);
    }
}

static bool inspect_frontend(uint8_t additional_mask,
                             ul_audio_capture_spec *out,
                             obs_output_t **retained_output,
                             audio_t **borrowed_audio)
{
    obs_output_t *output = NULL;
    obs_encoder_t *encoder;
    audio_t *audio, *global_audio;
    const struct audio_output_info *info;
    size_t primary;
    uint32_t channels;
    bool valid = false;

    if (out == NULL || retained_output == NULL || borrowed_audio == NULL)
        return false;
    memset(out, 0, sizeof(*out));
    *retained_output = NULL;
    *borrowed_audio = NULL;
    if ((additional_mask & ~0x3fu) != 0u)
        return false;
    output = obs_frontend_get_streaming_output();
    if (output == NULL || !obs_output_active(output))
        goto cleanup;
    encoder = obs_output_get_audio_encoder(output, 0u);
    if (encoder == NULL || obs_encoder_get_type(encoder) != OBS_ENCODER_AUDIO)
        goto cleanup;
    audio = obs_encoder_audio(encoder);
    global_audio = obs_get_audio();
    if (audio == NULL || audio != global_audio)
        goto cleanup;
    primary = obs_encoder_get_mixer_index(encoder);
    if (primary >= UL_AUDIO_CAPTURE_MIXES)
        goto cleanup;
    info = audio_output_get_info(audio);
    if (info == NULL || info->format != AUDIO_FORMAT_FLOAT_PLANAR ||
        !supported_rate(info->samples_per_sec))
        goto cleanup;
    channels = get_audio_channels(info->speakers);
    if (channels == 0u || channels > 8u ||
        audio_output_get_sample_rate(audio) != info->samples_per_sec ||
        audio_output_get_channels(audio) != channels ||
        audio_output_get_planes(audio) != channels ||
        audio_output_get_block_size(audio) != sizeof(float))
        goto cleanup;
    out->sample_rate = info->samples_per_sec;
    out->speakers = (uint32_t)info->speakers;
    out->channels = channels;
    out->primary_bus = (uint8_t)primary;
    out->mix_mask = (uint8_t)(additional_mask | (1u << primary));
    out->audio_identity = (uintptr_t)audio;
    out->output_identity = (uintptr_t)output;
    valid = valid_spec(out);
    if (valid) {
        *retained_output = output;
        *borrowed_audio = audio;
        output = NULL;
    }

cleanup:
    if (output != NULL)
        obs_output_release(output);
    if (!valid)
        memset(out, 0, sizeof(*out));
    return valid;
}

bool ul_audio_capture_inspect_frontend(uint8_t additional_mask,
                                       ul_audio_capture_spec *out)
{
    obs_output_t *output = NULL;
    audio_t *audio = NULL;
    bool valid = inspect_frontend(additional_mask, out, &output, &audio);
    (void)audio;
    if (output != NULL)
        obs_output_release(output);
    return valid;
}

ul_audio_capture *ul_audio_capture_create_worker(
    const ul_audio_capture_spec *spec)
{
    ul_audio_capture *capture;
    uint32_t slots;
    uint8_t bus;

    if (!valid_spec(spec) ||
        !atomic_is_lock_free(&capture_sink.active) ||
        !atomic_is_lock_free(&capture_sink.readers))
        return NULL;
    capture = calloc(1u, sizeof(*capture));
    if (capture == NULL)
        return NULL;
    atomic_init(&capture->refs, 1u);
    atomic_init(&capture->sealed, false);
    atomic_init(&capture->failed, false);
    atomic_init(&capture->origin_ready, false);
    atomic_init(&capture->origin_ns, 0u);
    if (!atomic_is_lock_free(&capture->failed) ||
        !atomic_is_lock_free(&capture->origin_ready) ||
        !atomic_is_lock_free(&capture->origin_ns))
        goto fail;
    capture->spec = *spec;
    slots = (2u * spec->sample_rate) / UL_AUDIO_BLOCK_FRAMES;
    if (slots > 48u)
        slots = 48u;
    if (slots == 0u)
        slots = 1u;
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        if ((spec->mix_mask & (1u << bus)) == 0u)
            continue;
        capture->queues[bus] = ul_audio_queue_create(
            spec->channels, sizeof(float), slots);
        capture->converters[bus] = ul_audio_converter_create(
            spec->sample_rate, (enum speaker_layout)spec->speakers);
        if (capture->queues[bus] == NULL ||
            capture->converters[bus] == NULL)
            goto fail;
    }
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        if ((spec->mix_mask & (1u << bus)) != 0u) {
            capture->lowest_bus = bus;
            break;
        }
    }
    return capture;

fail:
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        ul_audio_converter_destroy(capture->converters[bus]);
        ul_audio_queue_destroy(capture->queues[bus]);
    }
    memset(capture, 0, sizeof(*capture));
    free(capture);
    return NULL;
}

void ul_audio_capture_retain(ul_audio_capture *capture)
{
    if (capture != NULL)
        atomic_fetch_add_explicit(&capture->refs, 1u, memory_order_relaxed);
}

static bool cleanup_hooks_locked(audio_t *audio)
{
    uint8_t bus;
    if (capture_sink.hooked_mask == 0u)
        return true;
    if (audio == NULL || capture_sink.hook_audio != (uintptr_t)audio) {
        capture_sink.closed = true;
        return false;
    }
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        if ((capture_sink.hooked_mask & (1u << bus)) != 0u)
            audio_output_disconnect(audio, bus, audio_callback, &capture_sink);
    }
    capture_sink.hooked_mask = 0u;
    capture_sink.hook_audio = 0u;
    capture_sink.hook_generation = 0u;
    return true;
}

bool ul_audio_capture_connect_frontend(ul_audio_capture *capture,
                                       uintptr_t generation)
{
    ul_audio_capture_spec current;
    struct audio_convert_info conversion;
    obs_output_t *output = NULL;
    audio_t *audio;
    uint8_t additional_mask, attached = 0u, bus;
    bool success = false;

    if (capture == NULL || generation == 0u ||
        atomic_load_explicit(&capture->sealed, memory_order_acquire))
        return false;
    additional_mask = (uint8_t)(capture->spec.mix_mask &
                         ~(1u << capture->spec.primary_bus));
    if (!inspect_frontend(additional_mask, &current, &output, &audio) ||
        !same_spec(&current, &capture->spec))
        goto done;
    conversion = (struct audio_convert_info){
        capture->spec.sample_rate,
        AUDIO_FORMAT_FLOAT_PLANAR,
        (enum speaker_layout)capture->spec.speakers,
        false,
    };

    AcquireSRWLockExclusive(&capture_sink.lock);
    if (capture_sink.closed || capture_sink.retiring ||
        atomic_load_explicit(&capture_sink.active, memory_order_seq_cst) != NULL ||
        capture->connected ||
        atomic_load_explicit(&capture->sealed, memory_order_acquire) ||
        !cleanup_hooks_locked(audio))
        goto cleanup;
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        uint8_t bit = (uint8_t)(1u << bus);
        if ((capture->spec.mix_mask & bit) == 0u)
            continue;
        if (!audio_output_connect(audio, bus, &conversion,
                                  audio_callback, &capture_sink))
            goto rollback;
        attached |= bit;
    }
    capture->generation = generation;
    capture->connected = true;
    capture_sink.hook_audio = (uintptr_t)audio;
    capture_sink.hook_generation = generation;
    capture_sink.hooked_mask = attached;
    success = true;
    goto cleanup;

rollback:
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        if ((attached & (1u << bus)) != 0u)
            audio_output_disconnect(audio, bus, audio_callback, &capture_sink);
    }

cleanup:
    ReleaseSRWLockExclusive(&capture_sink.lock);
done:
    if (output != NULL)
        obs_output_release(output);
    return success;
}

bool ul_audio_capture_activate(ul_audio_capture *capture)
{
    bool success = false;
    if (capture == NULL)
        return false;
    AcquireSRWLockExclusive(&capture_sink.lock);
    if (!capture_sink.closed && !capture_sink.retiring && capture->connected &&
        capture->generation != 0u &&
        capture_sink.hook_generation == capture->generation &&
        capture_sink.hooked_mask == capture->spec.mix_mask &&
        !atomic_load_explicit(&capture->sealed, memory_order_acquire) &&
        atomic_load_explicit(&capture_sink.active,
                             memory_order_seq_cst) == NULL) {
        atomic_store_explicit(&capture_sink.active, capture,
                              memory_order_seq_cst);
        success = true;
    }
    ReleaseSRWLockExclusive(&capture_sink.lock);
    return success;
}

void ul_audio_capture_deactivate(ul_audio_capture *capture)
{
    ul_audio_capture *expected;
    bool retired = false;
    if (capture == NULL)
        return;
    AcquireSRWLockExclusive(&capture_sink.lock);
    atomic_store_explicit(&capture->sealed, true, memory_order_release);
    expected = capture;
    if (atomic_compare_exchange_strong_explicit(
            &capture_sink.active, &expected, NULL,
            memory_order_seq_cst, memory_order_seq_cst)) {
        capture_sink.retiring = true;
        retired = true;
    }
    ReleaseSRWLockExclusive(&capture_sink.lock);
    drain_readers();
    stop_queues(capture);
    if (retired) {
        AcquireSRWLockExclusive(&capture_sink.lock);
        capture_sink.retiring = false;
        ReleaseSRWLockExclusive(&capture_sink.lock);
    }
}

void ul_audio_capture_disconnect_frontend(uintptr_t generation, bool all)
{
    ul_audio_capture *retired = NULL;
    audio_t *audio = obs_get_audio();
    bool matches;

    AcquireSRWLockExclusive(&capture_sink.lock);
    matches = all || (generation != 0u &&
                      generation == capture_sink.hook_generation);
    if (!matches) {
        ReleaseSRWLockExclusive(&capture_sink.lock);
        return;
    }
    retired = atomic_exchange_explicit(&capture_sink.active, NULL,
                                       memory_order_seq_cst);
    if (retired != NULL) {
        /* Final release also takes this lock, so zero cannot race this retain. */
        atomic_fetch_add_explicit(&retired->refs, 1u, memory_order_relaxed);
        atomic_store_explicit(&retired->sealed, true, memory_order_release);
        capture_sink.retiring = true;
    }
    (void)cleanup_hooks_locked(audio);
    ReleaseSRWLockExclusive(&capture_sink.lock);
    if (retired != NULL)
        UL_AUDIO_CAPTURE_AFTER_EXTERNAL_RETIRE();
    drain_readers();
    stop_queues(retired);
    if (retired != NULL) {
        AcquireSRWLockExclusive(&capture_sink.lock);
        capture_sink.retiring = false;
        ReleaseSRWLockExclusive(&capture_sink.lock);
        ul_audio_capture_release(retired);
    }
}

void ul_audio_capture_abandon_after_shutdown(void)
{
    ul_audio_capture *retired;
    AcquireSRWLockExclusive(&capture_sink.lock);
    capture_sink.closed = true;
    retired = atomic_exchange_explicit(&capture_sink.active, NULL,
                                       memory_order_seq_cst);
    if (retired != NULL) {
        atomic_fetch_add_explicit(&retired->refs, 1u, memory_order_relaxed);
        atomic_store_explicit(&retired->sealed, true, memory_order_release);
        capture_sink.retiring = true;
    }
    ReleaseSRWLockExclusive(&capture_sink.lock);
    if (retired != NULL)
        UL_AUDIO_CAPTURE_AFTER_EXTERNAL_RETIRE();
    drain_readers();
    stop_queues(retired);
    if (retired != NULL) {
        AcquireSRWLockExclusive(&capture_sink.lock);
        capture_sink.retiring = false;
        ReleaseSRWLockExclusive(&capture_sink.lock);
        ul_audio_capture_release(retired);
    }
}

bool ul_audio_capture_origin(const ul_audio_capture *capture,
                             uint64_t *origin_ns)
{
    if (capture == NULL || origin_ns == NULL ||
        !atomic_load_explicit(&capture->origin_ready, memory_order_acquire))
        return false;
    *origin_ns = atomic_load_explicit(&capture->origin_ns,
                                      memory_order_relaxed);
    return true;
}

bool ul_audio_capture_failed(const ul_audio_capture *capture)
{
    return capture == NULL ||
           atomic_load_explicit(&capture->failed, memory_order_acquire);
}

ul_audio_queue *ul_audio_capture_queue(ul_audio_capture *capture, uint8_t bus)
{
    if (capture == NULL || bus >= UL_AUDIO_CAPTURE_MIXES ||
        (capture->spec.mix_mask & (1u << bus)) == 0u)
        return NULL;
    return capture->queues[bus];
}

bool ul_audio_capture_convert(ul_audio_capture *capture, uint8_t bus,
                              const ul_audio_block *block,
                              float stereo[UL_AUDIO_CAPTURE_STEREO_SAMPLES])
{
    const float *planes[8] = {0};
    uint32_t plane_bytes, expected_bytes, out_frames = 0u, channel;
    ul_audio_convert_result result;
    if (capture == NULL || block == NULL || stereo == NULL ||
        bus >= UL_AUDIO_CAPTURE_MIXES ||
        capture->converters[bus] == NULL || block->info.frames == 0u ||
        block->info.frames > UL_AUDIO_BLOCK_FRAMES)
        goto fail;
    plane_bytes = block->info.frames * sizeof(float);
    expected_bytes = plane_bytes * capture->spec.channels;
    if (block->info.bytes != expected_bytes)
        goto fail;
    for (channel = 0u; channel < capture->spec.channels; ++channel)
        planes[channel] = (const float *)(block->data + channel * plane_bytes);
    result = ul_audio_converter_convert(capture->converters[bus], planes,
                                        block->info.frames, stereo,
                                        UL_AUDIO_BLOCK_FRAMES, &out_frames);
    if (result != UL_AUDIO_CONVERT_OK || out_frames != block->info.frames)
        goto fail;
    return true;

fail:
    if (capture != NULL)
        fail_capture(capture);
    return false;
}

void ul_audio_capture_release(ul_audio_capture *capture)
{
    ul_audio_capture *expected;
    bool retired = false;
    bool final = false;
    uint8_t bus;
    if (capture == NULL)
        return;
    AcquireSRWLockExclusive(&capture_sink.lock);
    if (atomic_fetch_sub_explicit(&capture->refs, 1u,
                                  memory_order_acq_rel) == 1u) {
        atomic_store_explicit(&capture->sealed, true, memory_order_release);
        expected = capture;
        if (atomic_compare_exchange_strong_explicit(
                &capture_sink.active, &expected, NULL,
                memory_order_seq_cst, memory_order_seq_cst)) {
            capture_sink.retiring = true;
            retired = true;
        }
        final = true;
    }
    ReleaseSRWLockExclusive(&capture_sink.lock);
    if (!final)
        return;
    drain_readers();
    stop_queues(capture);
    if (retired) {
        AcquireSRWLockExclusive(&capture_sink.lock);
        capture_sink.retiring = false;
        ReleaseSRWLockExclusive(&capture_sink.lock);
    }
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        ul_audio_converter_destroy(capture->converters[bus]);
        ul_audio_queue_destroy(capture->queues[bus]);
    }
    memset(capture, 0, sizeof(*capture));
    free(capture);
}
