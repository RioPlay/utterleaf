// SPDX-License-Identifier: GPL-2.0-or-later
#include <windows.h>

#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static HANDLE reader_entered;
static HANDLE reader_continue;
static HANDLE external_retired;
static HANDLE external_continue;
static volatile LONG pause_reader;
static volatile LONG pause_external_retire;
static void test_after_reader_enter(void);
static void test_after_external_retire(void);
#define UL_AUDIO_CAPTURE_AFTER_READER_ENTER() test_after_reader_enter()
#define UL_AUDIO_CAPTURE_AFTER_EXTERNAL_RETIRE() test_after_external_retire()
#include "../src/audio_capture.c"

struct ul_audio_converter {
    uint32_t rate;
    enum speaker_layout speakers;
};

static int output_a, output_b, encoder_a, audio_a, audio_b;
static uintptr_t current_output = (uintptr_t)&output_a;
static uintptr_t current_encoder = (uintptr_t)&encoder_a;
static uintptr_t current_audio = (uintptr_t)&audio_a;
static uintptr_t encoder_audio = (uintptr_t)&audio_a;
static bool output_is_active = true;
static enum obs_encoder_type encoder_type = OBS_ENCODER_AUDIO;
static size_t primary_bus;
static struct audio_output_info audio_info;
static size_t stub_block_size = sizeof(float);
static size_t stub_planes = 2u;
static size_t stub_channels = 2u;
static uint32_t stub_rate = 48000u;
static int fail_connect_bus = -1;
static uint8_t registered_mask;
static uint32_t connect_calls, disconnect_calls, release_calls;
static uint32_t get_audio_calls;
static uint32_t converter_creates, converter_destroys;
static int fail_converter_create_at = -1;

static void test_after_reader_enter(void)
{
    if (InterlockedCompareExchange(&pause_reader, 0, 0) != 0) {
        SetEvent(reader_entered);
        assert(WaitForSingleObject(reader_continue, 5000u) == WAIT_OBJECT_0);
    }
}

static void test_after_external_retire(void)
{
    if (InterlockedCompareExchange(&pause_external_retire, 0, 0) != 0) {
        SetEvent(external_retired);
        assert(WaitForSingleObject(external_continue, 5000u) == WAIT_OBJECT_0);
    }
}

obs_output_t *obs_frontend_get_streaming_output(void)
{
    return (obs_output_t *)current_output;
}

void obs_output_release(obs_output_t *output)
{
    assert((uintptr_t)output == current_output);
    ++release_calls;
}

bool obs_output_active(const obs_output_t *output)
{
    return (uintptr_t)output == current_output && output_is_active;
}

obs_encoder_t *obs_output_get_audio_encoder(const obs_output_t *output,
                                             size_t idx)
{
    return (uintptr_t)output == current_output && idx == 0u ?
           (obs_encoder_t *)current_encoder : NULL;
}

enum obs_encoder_type obs_encoder_get_type(const obs_encoder_t *encoder)
{
    return (uintptr_t)encoder == current_encoder ? encoder_type :
                                                   OBS_ENCODER_VIDEO;
}

audio_t *obs_encoder_audio(const obs_encoder_t *encoder)
{
    return (uintptr_t)encoder == current_encoder ?
           (audio_t *)encoder_audio : NULL;
}

size_t obs_encoder_get_mixer_index(const obs_encoder_t *encoder)
{
    return (uintptr_t)encoder == current_encoder ? primary_bus :
                                                   MAX_AUDIO_MIXES;
}

audio_t *obs_get_audio(void)
{
    ++get_audio_calls;
    return (audio_t *)current_audio;
}

const struct audio_output_info *audio_output_get_info(const audio_t *audio)
{
    return (uintptr_t)audio == current_audio ? &audio_info : NULL;
}

size_t audio_output_get_block_size(const audio_t *audio)
{
    return (uintptr_t)audio == current_audio ? stub_block_size : 0u;
}

size_t audio_output_get_planes(const audio_t *audio)
{
    return (uintptr_t)audio == current_audio ? stub_planes : 0u;
}

size_t audio_output_get_channels(const audio_t *audio)
{
    return (uintptr_t)audio == current_audio ? stub_channels : 0u;
}

uint32_t audio_output_get_sample_rate(const audio_t *audio)
{
    return (uintptr_t)audio == current_audio ? stub_rate : 0u;
}

bool audio_output_connect(audio_t *audio, size_t mix_idx,
                          const struct audio_convert_info *conversion,
                          audio_output_callback_t callback, void *parameter)
{
    ++connect_calls;
    assert((uintptr_t)audio == current_audio);
    assert(mix_idx < MAX_AUDIO_MIXES);
    assert(conversion != NULL);
    assert(conversion->samples_per_sec == stub_rate);
    assert(conversion->format == AUDIO_FORMAT_FLOAT_PLANAR);
    assert(conversion->speakers == audio_info.speakers);
    assert(!conversion->allow_clipping);
    assert(callback == audio_callback);
    assert(parameter == &capture_sink);
    if ((int)mix_idx == fail_connect_bus ||
        (registered_mask & (1u << mix_idx)) != 0u)
        return false;
    registered_mask |= (uint8_t)(1u << mix_idx);
    return true;
}

void audio_output_disconnect(audio_t *audio, size_t mix_idx,
                             audio_output_callback_t callback, void *parameter)
{
    ++disconnect_calls;
    assert((uintptr_t)audio == current_audio);
    assert(mix_idx < MAX_AUDIO_MIXES);
    assert(callback == audio_callback);
    assert(parameter == &capture_sink);
    registered_mask &= (uint8_t)~(1u << mix_idx);
}

ul_audio_converter *ul_audio_converter_create(uint32_t rate,
                                               enum speaker_layout speakers)
{
    ul_audio_converter *converter;
    if ((int)converter_creates == fail_converter_create_at) {
        ++converter_creates;
        return NULL;
    }
    ++converter_creates;
    converter = calloc(1u, sizeof(*converter));
    if (converter != NULL) {
        converter->rate = rate;
        converter->speakers = speakers;
    }
    return converter;
}

void ul_audio_converter_destroy(ul_audio_converter *converter)
{
    if (converter != NULL) {
        ++converter_destroys;
        free(converter);
    }
}

ul_audio_convert_result ul_audio_converter_convert(
    ul_audio_converter *converter, const float *const planes[8],
    uint32_t frames, float *stereo, uint32_t capacity, uint32_t *out_frames)
{
    uint32_t frame;
    assert(converter != NULL);
    *out_frames = 0u;
    if (planes == NULL || planes[0] == NULL || frames == 0u ||
        capacity < frames)
        return UL_AUDIO_CONVERT_INVALID;
    for (frame = 0u; frame < frames; ++frame) {
        if (!isfinite(planes[0][frame]) ||
            (stub_channels > 1u && !isfinite(planes[1][frame])))
            return UL_AUDIO_CONVERT_NONFINITE_INPUT;
        stereo[frame * 2u] = planes[0][frame];
        stereo[frame * 2u + 1u] = stub_channels == 1u ?
                                   planes[0][frame] : planes[1][frame];
    }
    *out_frames = frames;
    return UL_AUDIO_CONVERT_OK;
}

static void reset_fixture(void)
{
    current_output = (uintptr_t)&output_a;
    current_encoder = (uintptr_t)&encoder_a;
    current_audio = encoder_audio = (uintptr_t)&audio_a;
    output_is_active = true;
    encoder_type = OBS_ENCODER_AUDIO;
    primary_bus = 0u;
    memset(&audio_info, 0, sizeof(audio_info));
    audio_info.name = "fixture";
    audio_info.samples_per_sec = 48000u;
    audio_info.format = AUDIO_FORMAT_FLOAT_PLANAR;
    audio_info.speakers = SPEAKERS_STEREO;
    stub_block_size = sizeof(float);
    stub_planes = stub_channels = 2u;
    stub_rate = 48000u;
    fail_connect_bus = fail_converter_create_at = -1;
    registered_mask = 0u;
    connect_calls = disconnect_calls = release_calls = get_audio_calls = 0u;
    converter_creates = converter_destroys = 0u;
    InterlockedExchange(&pause_reader, 0);
    InterlockedExchange(&pause_external_retire, 0);
    ResetEvent(reader_entered);
    ResetEvent(reader_continue);
    ResetEvent(external_retired);
    ResetEvent(external_continue);
    atomic_store_explicit(&capture_sink.active, NULL, memory_order_seq_cst);
    atomic_store_explicit(&capture_sink.readers, 0u, memory_order_seq_cst);
    capture_sink.closed = false;
    capture_sink.retiring = false;
    capture_sink.hook_audio = 0u;
    capture_sink.hook_generation = 0u;
    capture_sink.hooked_mask = 0u;
}

static ul_audio_capture_spec inspect(uint8_t additional)
{
    ul_audio_capture_spec spec;
    assert(ul_audio_capture_inspect_frontend(additional, &spec));
    return spec;
}

static void disconnect_and_release(ul_audio_capture *capture,
                                   uintptr_t generation)
{
    ul_audio_capture_deactivate(capture);
    ul_audio_capture_disconnect_frontend(generation, false);
    ul_audio_capture_release(capture);
    assert(registered_mask == 0u);
}

static void test_inspection_and_replacement(void)
{
    ul_audio_capture_spec spec, zero = {0};
    ul_audio_capture *capture;
    reset_fixture();
    primary_bus = 2u;
    spec = inspect(0x09u);
    assert(spec.sample_rate == 48000u && spec.speakers == SPEAKERS_STEREO);
    assert(spec.channels == 2u && spec.primary_bus == 2u);
    assert(spec.mix_mask == 0x0du);
    assert(spec.audio_identity == (uintptr_t)&audio_a);
    assert(spec.output_identity == (uintptr_t)&output_a);
    assert(release_calls == 1u);
    assert(!ul_audio_capture_inspect_frontend(0x40u, &zero));
    assert(memcmp(&zero, &(ul_audio_capture_spec){0}, sizeof(zero)) == 0);
    current_output = 0u;
    assert(!ul_audio_capture_inspect_frontend(0u, &zero));
    current_output = (uintptr_t)&output_a;
    output_is_active = false;
    assert(!ul_audio_capture_inspect_frontend(0u, &zero));
    output_is_active = true;
    capture = ul_audio_capture_create_worker(&spec);
    assert(capture != NULL);
    current_output = (uintptr_t)&output_b;
    assert(!ul_audio_capture_connect_frontend(capture, 1u));
    current_output = (uintptr_t)&output_a;
    ul_audio_capture_release(capture);
    assert(converter_creates == 3u && converter_destroys == 3u);
}

static void test_inspection_rejects_invalid_audio(void)
{
    ul_audio_capture_spec spec;
    reset_fixture();
    encoder_type = OBS_ENCODER_VIDEO;
    assert(!ul_audio_capture_inspect_frontend(0u, &spec));
    encoder_type = OBS_ENCODER_AUDIO;
    encoder_audio = (uintptr_t)&audio_b;
    assert(!ul_audio_capture_inspect_frontend(0u, &spec));
    encoder_audio = current_audio;
    primary_bus = MAX_AUDIO_MIXES;
    assert(!ul_audio_capture_inspect_frontend(0u, &spec));
    primary_bus = 0u;
    audio_info.format = AUDIO_FORMAT_FLOAT;
    assert(!ul_audio_capture_inspect_frontend(0u, &spec));
    audio_info.format = AUDIO_FORMAT_FLOAT_PLANAR;
    audio_info.samples_per_sec = stub_rate = 22050u;
    assert(!ul_audio_capture_inspect_frontend(0u, &spec));
    audio_info.samples_per_sec = stub_rate = 48000u;
    stub_block_size = 8u;
    assert(!ul_audio_capture_inspect_frontend(0u, &spec));
}

static void test_create_and_partial_attach(void)
{
    ul_audio_capture_spec spec;
    ul_audio_capture *capture;
    reset_fixture();
    spec = inspect(0x02u);
    fail_converter_create_at = 1;
    assert(ul_audio_capture_create_worker(&spec) == NULL);
    assert(converter_destroys == 1u);
    fail_converter_create_at = -1;
    converter_creates = converter_destroys = 0u;
    capture = ul_audio_capture_create_worker(&spec);
    assert(capture != NULL);
    fail_connect_bus = 1;
    assert(!ul_audio_capture_connect_frontend(capture, 7u));
    assert(connect_calls == 2u && disconnect_calls == 1u);
    assert(registered_mask == 0u);
    assert(!ul_audio_capture_activate(capture));
    ul_audio_capture_release(capture);
    assert(converter_destroys == 2u);
}

static void make_audio(struct audio_data *data, float storage[8][4],
                       uint32_t frames, uint64_t timestamp)
{
    uint32_t channel;
    memset(data, 0, sizeof(*data));
    for (channel = 0u; channel < stub_channels; ++channel) {
        storage[channel][0] = (float)(channel + 1u);
        data->data[channel] = (uint8_t *)storage[channel];
    }
    data->frames = frames;
    data->timestamp = timestamp;
}

static void invoke_bus(size_t bus, uint64_t timestamp)
{
    struct audio_data data;
    float storage[8][4] = {{0}};
    make_audio(&data, storage, 4u, timestamp);
    audio_callback(&capture_sink, bus, &data);
}

static void test_alignment_at_every_bus_position(void)
{
    int position;
    for (position = -1; position < (int)UL_AUDIO_CAPTURE_MIXES; ++position) {
        ul_audio_capture_spec spec;
        ul_audio_capture *capture;
        uint64_t origin = 0u, expected;
        uint8_t selected[] = {1u, 3u, 5u};
        size_t index;
        reset_fixture();
        primary_bus = 1u;
        spec = inspect((uint8_t)((1u << 3u) | (1u << 5u)));
        capture = ul_audio_capture_create_worker(&spec);
        assert(capture != NULL);
        assert(ul_audio_capture_connect_frontend(capture,
                                                 (uintptr_t)(20 + position)));
        assert(!ul_audio_capture_origin(capture, &origin));
        for (index = 0u; index < 3u; ++index) {
            if ((int)selected[index] <= position)
                invoke_bus(selected[index], 100u);
        }
        assert(ul_audio_capture_activate(capture));
        for (index = 0u; index < 3u; ++index) {
            if ((int)selected[index] > position)
                invoke_bus(selected[index], 100u);
        }
        for (index = 0u; index < 3u; ++index)
            invoke_bus(selected[index], 200u);
        expected = position < 1 ? 100u : 200u;
        assert(ul_audio_capture_origin(capture, &origin) && origin == expected);
        for (index = 0u; index < 3u; ++index) {
            ul_audio_block block;
            assert(ul_audio_queue_pop(
                ul_audio_capture_queue(capture, selected[index]), &block));
            assert(block.info.sequence == 0u);
            assert(block.info.timestamp_ns == expected);
        }
        assert(!ul_audio_capture_failed(capture));
        disconnect_and_release(capture, (uintptr_t)(20 + position));
    }
}

static void test_metadata_and_conversion_failure(void)
{
    ul_audio_capture_spec spec;
    ul_audio_capture *capture;
    struct audio_data data;
    ul_audio_block block;
    float storage[8][4] = {{0}};
    float stereo[UL_AUDIO_CAPTURE_STEREO_SAMPLES] = {0};

    reset_fixture();
    spec = inspect(0u);
    capture = ul_audio_capture_create_worker(&spec);
    assert(capture != NULL);
    assert(ul_audio_capture_connect_frontend(capture, 40u));
    assert(ul_audio_capture_activate(capture));
    make_audio(&data, storage, 0u, 100u);
    audio_callback(&capture_sink, 0u, &data);
    assert(ul_audio_capture_failed(capture));
    disconnect_and_release(capture, 40u);

    reset_fixture();
    spec = inspect(0u);
    capture = ul_audio_capture_create_worker(&spec);
    assert(capture != NULL);
    memset(&block, 0, sizeof(block));
    block.info.frames = 2u;
    block.info.bytes = 1u;
    assert(!ul_audio_capture_convert(capture, 0u, &block, stereo));
    assert(ul_audio_capture_failed(capture));
    ul_audio_capture_release(capture);

    reset_fixture();
    spec = inspect(0u);
    capture = ul_audio_capture_create_worker(&spec);
    assert(capture != NULL);
    memset(&block, 0, sizeof(block));
    block.info.frames = 2u;
    block.info.bytes = 2u * 2u * sizeof(float);
    ((float *)block.data)[0] = 0.25f;
    ((float *)block.data)[1] = 0.5f;
    ((float *)block.data)[2] = 0.75f;
    ((float *)block.data)[3] = 1.0f;
    assert(ul_audio_capture_convert(capture, 0u, &block, stereo));
    assert(stereo[0] == 0.25f && stereo[1] == 0.75f);
    ((float *)block.data)[0] = NAN;
    assert(!ul_audio_capture_convert(capture, 0u, &block, stereo));
    assert(ul_audio_capture_failed(capture));
    ul_audio_capture_release(capture);
}

static void test_alignment_mismatch_fails(void)
{
    ul_audio_capture_spec spec;
    ul_audio_capture *capture;
    reset_fixture();
    primary_bus = 1u;
    spec = inspect((uint8_t)(1u << 3u));
    capture = ul_audio_capture_create_worker(&spec);
    assert(capture != NULL);
    assert(ul_audio_capture_connect_frontend(capture, 45u));
    assert(ul_audio_capture_activate(capture));
    invoke_bus(1u, 100u);
    invoke_bus(3u, 101u);
    assert(ul_audio_capture_failed(capture));
    disconnect_and_release(capture, 45u);
}

typedef struct thread_capture {
    ul_audio_capture *capture;
} thread_capture;

typedef struct retire_context {
    uintptr_t generation;
    bool abandon;
} retire_context;

static DWORD WINAPI callback_thread(void *parameter)
{
    (void)parameter;
    invoke_bus(0u, 123u);
    return 0u;
}

static DWORD WINAPI deactivate_thread(void *parameter)
{
    thread_capture *context = parameter;
    ul_audio_capture_deactivate(context->capture);
    return 0u;
}

static DWORD WINAPI external_retire_thread(void *parameter)
{
    retire_context *context = parameter;
    if (context->abandon)
        ul_audio_capture_abandon_after_shutdown();
    else
        ul_audio_capture_disconnect_frontend(context->generation, false);
    return 0u;
}

static void test_reader_drain_and_refs(void)
{
    ul_audio_capture_spec spec;
    ul_audio_capture *capture;
    thread_capture context;
    HANDLE callback, deactivator;
    uint32_t destroys;

    reset_fixture();
    spec = inspect(0u);
    capture = ul_audio_capture_create_worker(&spec);
    assert(capture != NULL);
    assert(ul_audio_capture_connect_frontend(capture, 50u));
    assert(ul_audio_capture_activate(capture));
    context.capture = capture;
    InterlockedExchange(&pause_reader, 1);
    callback = CreateThread(NULL, 0, callback_thread, NULL, 0, NULL);
    assert(callback != NULL);
    assert(WaitForSingleObject(reader_entered, 5000u) == WAIT_OBJECT_0);
    deactivator = CreateThread(NULL, 0, deactivate_thread, &context, 0, NULL);
    assert(deactivator != NULL);
    assert(WaitForSingleObject(deactivator, 50u) == WAIT_TIMEOUT);
    SetEvent(reader_continue);
    assert(WaitForSingleObject(callback, 5000u) == WAIT_OBJECT_0);
    assert(WaitForSingleObject(deactivator, 5000u) == WAIT_OBJECT_0);
    CloseHandle(callback);
    CloseHandle(deactivator);
    InterlockedExchange(&pause_reader, 0);
    assert(atomic_load_explicit(&capture_sink.active,
                                memory_order_seq_cst) == NULL);
    ul_audio_capture_disconnect_frontend(50u, false);
    destroys = converter_destroys;
    ul_audio_capture_retain(capture);
    ul_audio_capture_release(capture);
    assert(converter_destroys == destroys);
    ul_audio_capture_release(capture);
    assert(converter_destroys == destroys + 1u);
}

static void test_final_release_racing_external_retire(void)
{
    bool abandon;
    for (abandon = false;; abandon = true) {
        ul_audio_capture_spec spec;
        ul_audio_capture *capture;
        retire_context context;
        HANDLE retire_thread;
        uint32_t destroys;

        reset_fixture();
        spec = inspect(0u);
        capture = ul_audio_capture_create_worker(&spec);
        assert(capture != NULL);
        context.generation = abandon ? 81u : 80u;
        context.abandon = abandon;
        assert(ul_audio_capture_connect_frontend(capture,
                                                 context.generation));
        assert(ul_audio_capture_activate(capture));
        destroys = converter_destroys;
        InterlockedExchange(&pause_external_retire, 1);
        retire_thread = CreateThread(NULL, 0, external_retire_thread,
                                     &context, 0, NULL);
        assert(retire_thread != NULL);
        assert(WaitForSingleObject(external_retired, 5000u) == WAIT_OBJECT_0);
        assert(atomic_load_explicit(&capture_sink.active,
                                    memory_order_seq_cst) == NULL);

        /* Drop the worker's last logical ref while the sink owns its temp ref. */
        ul_audio_capture_release(capture);
        assert(atomic_load_explicit(&capture->refs,
                                    memory_order_relaxed) == 1u);
        assert(converter_destroys == destroys);
        assert(WaitForSingleObject(retire_thread, 50u) == WAIT_TIMEOUT);
        SetEvent(external_continue);
        assert(WaitForSingleObject(retire_thread, 5000u) == WAIT_OBJECT_0);
        CloseHandle(retire_thread);
        InterlockedExchange(&pause_external_retire, 0);
        assert(converter_destroys == destroys + 1u);
        if (abandon)
            break;
    }
}

static void test_stale_cleanup_and_abandon(void)
{
    ul_audio_capture_spec spec;
    ul_audio_capture *capture;
    uint32_t disconnected;
    uint32_t audio_calls;

    reset_fixture();
    spec = inspect(0u);
    capture = ul_audio_capture_create_worker(&spec);
    assert(capture != NULL);
    assert(ul_audio_capture_connect_frontend(capture, 60u));
    assert(ul_audio_capture_activate(capture));
    ul_audio_capture_deactivate(capture);
    current_audio = encoder_audio = (uintptr_t)&audio_b;
    disconnected = disconnect_calls;
    ul_audio_capture_disconnect_frontend(59u, false);
    assert(disconnect_calls == disconnected && !capture_sink.closed);
    ul_audio_capture_disconnect_frontend(60u, false);
    assert(disconnect_calls == disconnected && capture_sink.closed);
    assert(!ul_audio_capture_connect_frontend(capture, 61u));
    ul_audio_capture_release(capture);

    reset_fixture();
    spec = inspect(0u);
    capture = ul_audio_capture_create_worker(&spec);
    assert(capture != NULL);
    assert(ul_audio_capture_connect_frontend(capture, 70u));
    assert(ul_audio_capture_activate(capture));
    disconnected = disconnect_calls;
    audio_calls = get_audio_calls;
    ul_audio_capture_abandon_after_shutdown();
    assert(disconnect_calls == disconnected);
    assert(get_audio_calls == audio_calls);
    assert(capture_sink.closed);
    assert(atomic_load_explicit(&capture_sink.active,
                                memory_order_seq_cst) == NULL);
    assert(!ul_audio_capture_activate(capture));
    ul_audio_capture_release(capture);
}

int main(void)
{
    reader_entered = CreateEventW(NULL, TRUE, FALSE, NULL);
    reader_continue = CreateEventW(NULL, TRUE, FALSE, NULL);
    external_retired = CreateEventW(NULL, TRUE, FALSE, NULL);
    external_continue = CreateEventW(NULL, TRUE, FALSE, NULL);
    assert(reader_entered != NULL && reader_continue != NULL &&
           external_retired != NULL && external_continue != NULL);
    test_inspection_and_replacement();
    test_inspection_rejects_invalid_audio();
    test_create_and_partial_attach();
    test_alignment_at_every_bus_position();
    test_metadata_and_conversion_failure();
    test_alignment_mismatch_fails();
    test_reader_drain_and_refs();
    test_final_release_racing_external_retire();
    test_stale_cleanup_and_abandon();
    CloseHandle(external_continue);
    CloseHandle(external_retired);
    CloseHandle(reader_continue);
    CloseHandle(reader_entered);
    puts("audio capture ownership and callback tests passed");
    return 0;
}
