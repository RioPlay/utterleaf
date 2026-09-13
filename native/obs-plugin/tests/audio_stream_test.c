// SPDX-License-Identifier: GPL-2.0-or-later
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include "../src/audio_stream.h"
#include "../src/audio_protocol.h"
#include "../src/audio_queue.h"
#include "../src/session_protocol.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_ITEMS 160u
#define MAX_WRITES 320u
#define WRITE_PREFIX_BYTES 128u

typedef struct fake_item {
    uint64_t sequence, timestamp;
    ul_audio_gap gap;
    uint32_t frames;
    float value;
    bool bad_bytes;
} fake_item;

struct ul_audio_queue {
    fake_item items[MAX_ITEMS];
    unsigned count, next;
    ul_audio_queue_result status;
    ul_audio_gap final_gap;
};

struct ul_audio_capture {
    struct ul_audio_queue queues[UL_AUDIO_CAPTURE_MIXES];
    uint64_t origin;
    bool origin_ready, failed, nonfinite;
    unsigned convert_calls, convert_fail_at, deactivate_calls;
};

struct ul_admission {
    uint8_t writes[MAX_WRITES][WRITE_PREFIX_BYTES];
    DWORD sizes[MAX_WRITES];
    unsigned write_count, audio_count, fail_write_at, stop_after_audio;
    int probe_result, read_result;
    DWORD available, slow_audio_ms, ack_delay_ms, last_read_timeout;
    bool bad_ack, wrong_ack_session, wrong_ack_kind, wrong_ack_version;
    uint8_t *largest_write;
    DWORD largest_write_size;
    HANDLE stop_event;
};

static HANDLE signal_stop_on_stopped_status;

static const uint8_t session[16] = {
    1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16
};

static ul_audio_capture_spec spec_for(uint8_t mask)
{
    ul_audio_capture_spec spec = {48000u, 2u, 2u, 0u, mask, 1u, 2u};
    return spec;
}

static void enqueue(struct ul_audio_capture *capture, uint8_t bus,
                    uint64_t sequence, uint64_t timestamp, ul_audio_gap gap,
                    float value)
{
    struct ul_audio_queue *queue = &capture->queues[bus];
    fake_item *item = &queue->items[queue->count++];
    assert(queue->count <= MAX_ITEMS);
    *item = (fake_item){sequence, timestamp, gap, 1u, value, false};
}

static void enqueue_frames(struct ul_audio_capture *capture, uint8_t bus,
                           uint64_t sequence, uint64_t timestamp,
                           uint32_t frames, float value)
{
    struct ul_audio_queue *queue = &capture->queues[bus];
    fake_item *item = &queue->items[queue->count++];
    assert(queue->count <= MAX_ITEMS);
    assert(frames >= 1u && frames <= UL_AUDIO_BLOCK_FRAMES);
    *item = (fake_item){sequence, timestamp, {0}, frames, value, false};
}

bool ul_audio_queue_pop(ul_audio_queue *opaque, ul_audio_block *out)
{
    struct ul_audio_queue *queue = opaque;
    fake_item *item;
    uint32_t frame;
    float right;
    if (queue == NULL || out == NULL || queue->next == queue->count)
        return false;
    item = &queue->items[queue->next++];
    memset(out, 0, sizeof(*out));
    out->info.sequence = item->sequence;
    out->info.timestamp_ns = item->timestamp;
    out->info.gap = item->gap;
    out->info.frames = item->frames;
    out->info.bytes = item->bad_bytes ? 1u : item->frames * 8u;
    right = -item->value;
    for (frame = 0u; frame < item->frames; ++frame) {
        memcpy(out->data + frame * sizeof(float), &item->value,
               sizeof(float));
        memcpy(out->data + item->frames * sizeof(float) +
                   frame * sizeof(float), &right, sizeof(float));
    }
    return true;
}

ul_audio_queue_result ul_audio_queue_status(const ul_audio_queue *opaque)
{
    const struct ul_audio_queue *queue = opaque;
    ul_audio_queue_result status =
        queue == NULL ? UL_AUDIO_QUEUE_INVALID : queue->status;
    if (status == UL_AUDIO_QUEUE_STOPPED &&
        signal_stop_on_stopped_status != NULL) {
        SetEvent(signal_stop_on_stopped_status);
        signal_stop_on_stopped_status = NULL;
    }
    return status;
}

ul_audio_gap ul_audio_queue_final_gap(const ul_audio_queue *opaque)
{
    const struct ul_audio_queue *queue = opaque;
    return queue == NULL ? (ul_audio_gap){0} : queue->final_gap;
}

bool ul_audio_capture_origin(const ul_audio_capture *opaque, uint64_t *origin)
{
    const struct ul_audio_capture *capture = opaque;
    if (capture == NULL || origin == NULL || !capture->origin_ready)
        return false;
    *origin = capture->origin;
    return true;
}

bool ul_audio_capture_failed(const ul_audio_capture *opaque)
{
    const struct ul_audio_capture *capture = opaque;
    return capture == NULL || capture->failed;
}

ul_audio_queue *ul_audio_capture_queue(ul_audio_capture *opaque, uint8_t bus)
{
    struct ul_audio_capture *capture = opaque;
    return capture == NULL || bus >= UL_AUDIO_CAPTURE_MIXES
               ? NULL : &capture->queues[bus];
}

bool ul_audio_capture_convert(ul_audio_capture *opaque, uint8_t bus,
                              const ul_audio_block *block, float *stereo)
{
    struct ul_audio_capture *capture = opaque;
    uint32_t index;
    (void)bus;
    capture->convert_calls++;
    if (capture->convert_fail_at == capture->convert_calls) {
        capture->failed = true;
        return false;
    }
    for (index = 0u; index < block->info.frames; ++index) {
        memcpy(&stereo[index * 2u], block->data + index * sizeof(float),
               sizeof(float));
        memcpy(&stereo[index * 2u + 1u],
               block->data + block->info.frames * sizeof(float) +
                   index * sizeof(float), sizeof(float));
    }
    if (capture->nonfinite)
        stereo[block->info.frames * 2u - 1u] = NAN;
    return true;
}

void ul_audio_capture_deactivate(ul_audio_capture *opaque)
{
    struct ul_audio_capture *capture = opaque;
    uint8_t bus;
    if (capture == NULL)
        return;
    capture->deactivate_calls++;
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus)
        capture->queues[bus].status = UL_AUDIO_QUEUE_STOPPED;
}

int ul_admission_probe(ul_admission *opaque, DWORD *available)
{
    struct ul_admission *admission = opaque;
    if (admission->probe_result != UL_ADMISSION_AUTH_OK)
        return admission->probe_result;
    *available = admission->available;
    return UL_ADMISSION_AUTH_OK;
}

int ul_admission_write_all(ul_admission *opaque, const void *buffer,
                           DWORD size, DWORD timeout)
{
    struct ul_admission *admission = opaque;
    const uint8_t *bytes = buffer;
    (void)timeout;
    admission->write_count++;
    if (admission->write_count == admission->fail_write_at)
        return UL_ADMISSION_CANCELLED;
    assert(admission->write_count <= MAX_WRITES &&
           size <= UL_AUDIO_MAX_PACKET_BYTES);
    memcpy(admission->writes[admission->write_count - 1u], buffer,
           size < WRITE_PREFIX_BYTES ? size : WRITE_PREFIX_BYTES);
    admission->sizes[admission->write_count - 1u] = size;
    if (size > admission->largest_write_size) {
        admission->largest_write_size = size;
        if (size > WRITE_PREFIX_BYTES) {
            uint8_t *copy = realloc(admission->largest_write, size);
            assert(copy != NULL);
            admission->largest_write = copy;
            memcpy(copy, buffer, size);
        }
    }
    if (bytes[5] == 2u) {
        admission->audio_count++;
        if (admission->slow_audio_ms != 0u)
            Sleep(admission->slow_audio_ms);
        if (admission->audio_count == admission->stop_after_audio)
            SetEvent(admission->stop_event);
    }
    return UL_ADMISSION_AUTH_OK;
}

int ul_admission_read_exact(ul_admission *opaque, void *buffer, DWORD size,
                            DWORD timeout)
{
    struct ul_admission *admission = opaque;
    uint8_t *ack = buffer;
    admission->last_read_timeout = timeout;
    if (admission->ack_delay_ms != 0u)
        Sleep(admission->ack_delay_ms);
    if (admission->read_result != UL_ADMISSION_AUTH_OK)
        return admission->read_result;
    assert(size == UL_SESSION_COMMAND_BYTES);
    memset(ack, 0, size);
    memcpy(ack, "ULAC", 4u);
    ack[4] = 1u;
    ack[5] = 3u;
    memcpy(ack + 8u, session, 16u);
    if (admission->wrong_ack_version)
        ack[4] = 2u;
    if (admission->wrong_ack_kind)
        ack[5] = 2u;
    if (admission->wrong_ack_session)
        ack[8] ^= 0xffu;
    if (admission->bad_ack)
        ack[27] = 1u;
    return UL_ADMISSION_AUTH_OK;
}

static void clear_admission(struct ul_admission *admission)
{
    free(admission->largest_write);
    admission->largest_write = NULL;
    admission->largest_write_size = 0u;
}

static uint64_t get_u64(const uint8_t *bytes)
{
    uint64_t value = 0u;
    unsigned index;
    for (index = 0u; index < 8u; ++index)
        value |= (uint64_t)bytes[index] << (index * 8u);
    return value;
}

static uint32_t get_u32(const uint8_t *bytes)
{
    uint32_t value = 0u;
    unsigned index;
    for (index = 0u; index < 4u; ++index)
        value |= (uint32_t)bytes[index] << (index * 8u);
    return value;
}

static int run_stream(struct ul_audio_capture *capture,
                      ul_audio_capture_spec *spec,
                      struct ul_admission *admission, HANDLE stop)
{
    uint8_t bus;
    admission->stop_event = stop;
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus)
        if (capture->queues[bus].status == 0)
            capture->queues[bus].status = UL_AUDIO_QUEUE_OK;
    return ul_audio_stream_run(capture, spec, admission, session, stop);
}

static int run_single_block_stop(struct ul_audio_capture *capture,
                                 struct ul_admission *admission)
{
    ul_audio_capture_spec spec = spec_for(1u);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    int result;
    assert(stop != NULL);
    capture->origin_ready = true;
    enqueue(capture, 0u, 0u, 0u, (ul_audio_gap){0}, 1.0f);
    admission->stop_after_audio = 1u;
    result = run_stream(capture, &spec, admission, stop);
    CloseHandle(stop);
    return result;
}

static void test_clean_fair_drain_and_ack(void)
{
    struct ul_audio_capture capture = {0};
    struct ul_admission admission = {0};
    ul_audio_capture_spec spec = spec_for(5u);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    capture.origin = 1000u;
    capture.origin_ready = true;
    enqueue(&capture, 0, 0, 1000, (ul_audio_gap){0}, 1.0f);
    enqueue(&capture, 0, 1, 21833, (ul_audio_gap){0}, 2.0f);
    enqueue(&capture, 0, 2, 42666, (ul_audio_gap){0}, 3.0f);
    enqueue(&capture, 2, 0, 1000, (ul_audio_gap){0}, 4.0f);
    enqueue(&capture, 2, 1, 21833, (ul_audio_gap){0}, 5.0f);
    admission.stop_after_audio = 5u;
    assert(run_stream(&capture, &spec, &admission, stop) == UL_AUDIO_STREAM_OK);
    assert(capture.deactivate_calls == 1u && admission.write_count == 7u);
    assert(admission.writes[0][5] == 1u);
    assert(admission.writes[1][5] == 2u && admission.writes[1][28] == 0u);
    assert(admission.writes[2][28] == 2u);
    assert(admission.writes[3][28] == 0u && get_u64(admission.writes[3] + 29u) == 1u);
    assert(admission.writes[4][28] == 2u && get_u64(admission.writes[4] + 29u) == 1u);
    assert(admission.writes[5][28] == 0u && get_u64(admission.writes[5] + 29u) == 2u);
    assert(admission.writes[6][5] == 4u && admission.writes[6][28] == 1u);
    assert(admission.writes[6][29] == 2u && admission.writes[6][30] == 0u);
    assert(get_u64(admission.writes[6] + 31u) == 2u);
    assert(admission.writes[6][39] == 2u && get_u64(admission.writes[6] + 40u) == 1u);
    CloseHandle(stop);
}

static void test_staging_refusals_emit_nothing(void)
{
    struct ul_audio_capture capture = {0};
    struct ul_admission admission = {0};
    ul_audio_capture_spec spec = spec_for(3u);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    capture.origin = 10u;
    capture.origin_ready = true;
    enqueue(&capture, 0, 0, 10, (ul_audio_gap){0}, 1.0f);
    enqueue(&capture, 1, 0, 11, (ul_audio_gap){0}, 1.0f);
    assert(run_stream(&capture, &spec, &admission, stop) ==
           UL_AUDIO_STREAM_SOURCE_CHANGED);
    assert(admission.write_count == 0u && capture.deactivate_calls == 1u);
    CloseHandle(stop);

    memset(&capture, 0, sizeof(capture));
    memset(&admission, 0, sizeof(admission));
    stop = CreateEventW(NULL, TRUE, TRUE, NULL);
    capture.origin_ready = true;
    capture.origin = 10u;
    enqueue(&capture, 0, 0, 10, (ul_audio_gap){0}, 1.0f);
    spec = spec_for(1u);
    assert(run_stream(&capture, &spec, &admission, stop) ==
           UL_AUDIO_STREAM_INCOMPLETE);
    assert(admission.write_count == 0u && capture.deactivate_calls == 1u);
    CloseHandle(stop);

    memset(&capture, 0, sizeof(capture));
    memset(&admission, 0, sizeof(admission));
    stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    capture.origin_ready = true;
    capture.origin = 10u;
    enqueue(&capture, 0, 1, 10, (ul_audio_gap){0, 1, 10}, 1.0f);
    assert(run_stream(&capture, &spec, &admission, stop) ==
           UL_AUDIO_STREAM_SOURCE_CHANGED);
    assert(admission.write_count == 0u);
    CloseHandle(stop);
}

static void test_gap_and_source_failures(void)
{
    struct ul_audio_capture capture = {0};
    struct ul_admission admission = {0};
    ul_audio_capture_spec spec = spec_for(1u);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    capture.origin_ready = true;
    capture.origin = 1000u;
    enqueue(&capture, 0, 0, 1000, (ul_audio_gap){0}, 1.0f);
    enqueue(&capture, 0, 2, 42666, (ul_audio_gap){1, 1, 21833}, 2.0f);
    assert(run_stream(&capture, &spec, &admission, stop) ==
           UL_AUDIO_STREAM_SOURCE_CHANGED);
    assert(admission.write_count == 4u && admission.writes[2][5] == 3u);
    assert(admission.writes[3][5] == 4u && admission.writes[3][28] == 5u);
    assert(capture.deactivate_calls == 1u);
    CloseHandle(stop);

    memset(&capture, 0, sizeof(capture));
    memset(&admission, 0, sizeof(admission));
    stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    capture.origin_ready = true;
    capture.origin = 1000u;
    capture.convert_fail_at = 2u;
    enqueue(&capture, 0, 0, 1000, (ul_audio_gap){0}, 1.0f);
    enqueue(&capture, 0, 1, 21833, (ul_audio_gap){0}, 2.0f);
    assert(run_stream(&capture, &spec, &admission, stop) ==
           UL_AUDIO_STREAM_SOURCE_CHANGED);
    assert(admission.write_count == 3u && admission.writes[2][5] == 4u &&
           admission.writes[2][28] == 4u);
    CloseHandle(stop);
}

static void test_transport_and_ack_failures(void)
{
    struct ul_audio_capture capture = {0};
    struct ul_admission admission = {0};
    ul_audio_capture_spec spec = spec_for(1u);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    capture.origin_ready = true;
    capture.origin = 0u;
    enqueue(&capture, 0, 0, 0, (ul_audio_gap){0}, 1.0f);
    admission.fail_write_at = 2u;
    assert(run_stream(&capture, &spec, &admission, stop) ==
           UL_AUDIO_STREAM_TRANSPORT_ERROR);
    assert(admission.write_count == 2u && capture.deactivate_calls == 1u);
    CloseHandle(stop);

    memset(&capture, 0, sizeof(capture));
    memset(&admission, 0, sizeof(admission));
    stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    capture.origin_ready = true;
    admission.available = 1u;
    assert(run_stream(&capture, &spec, &admission, stop) ==
           UL_AUDIO_STREAM_TRANSPORT_ERROR);
    assert(admission.write_count == 0u);
    CloseHandle(stop);

    memset(&capture, 0, sizeof(capture));
    memset(&admission, 0, sizeof(admission));
    stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    capture.origin_ready = true;
    admission.probe_result = UL_ADMISSION_CANCELLED;
    assert(run_stream(&capture, &spec, &admission, stop) ==
           UL_AUDIO_STREAM_TRANSPORT_ERROR);
    assert(admission.write_count == 0u && capture.deactivate_calls == 1u);
    CloseHandle(stop);

    memset(&capture, 0, sizeof(capture));
    memset(&admission, 0, sizeof(admission));
    stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    capture.origin_ready = true;
    enqueue(&capture, 0, 0, 0, (ul_audio_gap){0}, 1.0f);
    admission.stop_after_audio = 1u;
    admission.bad_ack = true;
    assert(run_stream(&capture, &spec, &admission, stop) ==
           UL_AUDIO_STREAM_TRANSPORT_ERROR);
    assert(admission.writes[2][5] == 4u);
    CloseHandle(stop);
}

static void test_end_write_and_ack_paths(void)
{
    struct ul_audio_capture capture = {0};
    struct ul_admission admission = {0};
    const int read_failures[] = {
        UL_ADMISSION_TIMEOUT,
        UL_ADMISSION_IO_ERROR,
        UL_ADMISSION_CANCELLED,
    };
    unsigned index;

    admission.fail_write_at = 3u;
    assert(run_single_block_stop(&capture, &admission) ==
           UL_AUDIO_STREAM_TRANSPORT_ERROR);
    assert(admission.write_count == 3u && capture.deactivate_calls == 1u);

    for (index = 0u; index < sizeof(read_failures) / sizeof(read_failures[0]);
         ++index) {
        memset(&capture, 0, sizeof(capture));
        memset(&admission, 0, sizeof(admission));
        admission.read_result = read_failures[index];
        assert(run_single_block_stop(&capture, &admission) ==
               UL_AUDIO_STREAM_TRANSPORT_ERROR);
        assert(admission.write_count == 3u &&
               admission.writes[2][5] == 4u &&
               admission.last_read_timeout > 0u &&
               capture.deactivate_calls == 1u);
    }

    for (index = 0u; index < 4u; ++index) {
        memset(&capture, 0, sizeof(capture));
        memset(&admission, 0, sizeof(admission));
        admission.wrong_ack_session = index == 0u;
        admission.wrong_ack_kind = index == 1u;
        admission.wrong_ack_version = index == 2u;
        admission.bad_ack = index == 3u;
        assert(run_single_block_stop(&capture, &admission) ==
               UL_AUDIO_STREAM_TRANSPORT_ERROR);
        assert(admission.writes[2][5] == 4u &&
               admission.last_read_timeout > 0u);
    }

    memset(&capture, 0, sizeof(capture));
    memset(&admission, 0, sizeof(admission));
    admission.ack_delay_ms = 10u;
    ULONGLONG before = GetTickCount64();
    assert(run_single_block_stop(&capture, &admission) == UL_AUDIO_STREAM_OK);
    assert(GetTickCount64() - before >= 5u);
    assert(admission.last_read_timeout >= 1u);
}

static void test_stopped_queue_precedes_stop_event(void)
{
    struct ul_audio_capture capture = {0};
    struct ul_admission admission = {0};
    ul_audio_capture_spec spec = spec_for(1u);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    assert(stop != NULL);
    capture.origin_ready = true;
    enqueue(&capture, 0u, 0u, 0u, (ul_audio_gap){0}, 1.0f);
    capture.queues[0].status = UL_AUDIO_QUEUE_STOPPED;
    signal_stop_on_stopped_status = stop;
    assert(run_stream(&capture, &spec, &admission, stop) ==
           UL_AUDIO_STREAM_OK);
    signal_stop_on_stopped_status = NULL;
    assert(capture.deactivate_calls == 1u && admission.write_count == 3u);
    assert(admission.writes[2][5] == 4u && admission.writes[2][28] == 1u);
    CloseHandle(stop);
}

static void test_metadata_and_argument_failures(void)
{
    struct ul_audio_capture capture = {0};
    struct ul_admission admission = {0};
    ul_audio_capture_spec spec = spec_for(1u);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    capture.origin_ready = true;
    enqueue(&capture, 0, 0, 0, (ul_audio_gap){0}, 1.0f);
    enqueue(&capture, 0, UINT64_MAX, 20833, (ul_audio_gap){0}, 2.0f);
    assert(run_stream(&capture, &spec, &admission, stop) ==
           UL_AUDIO_STREAM_SOURCE_CHANGED);
    assert(admission.write_count == 3u && admission.writes[2][28] == 4u);
    CloseHandle(stop);

    memset(&capture, 0, sizeof(capture));
    memset(&admission, 0, sizeof(admission));
    stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    capture.origin_ready = true;
    enqueue(&capture, 0, 0, 0, (ul_audio_gap){0}, 1.0f);
    capture.nonfinite = true;
    assert(run_stream(&capture, &spec, &admission, stop) ==
           UL_AUDIO_STREAM_SOURCE_CHANGED);
    assert(admission.write_count == 0u);
    CloseHandle(stop);

    memset(&capture, 0, sizeof(capture));
    stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    spec.channels = 0u;
    assert(ul_audio_stream_run(&capture, &spec, &admission, session, stop) ==
           UL_AUDIO_STREAM_INCOMPLETE);
    assert(capture.deactivate_calls == 1u);
    assert(ul_audio_stream_run(NULL, &spec, &admission, session, stop) ==
           UL_AUDIO_STREAM_INCOMPLETE);
    CloseHandle(stop);
}

static void test_tail_idle_and_no_total_duration(void)
{
    struct ul_audio_capture capture = {0};
    struct ul_admission admission = {0};
    ul_audio_capture_spec spec = spec_for(1u);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    ULONGLONG before;
    unsigned index;
    capture.origin_ready = true;
    capture.origin = 0u;
    enqueue(&capture, 0, 0, 0, (ul_audio_gap){0}, 1.0f);
    before = GetTickCount64();
    assert(run_stream(&capture, &spec, &admission, stop) ==
           UL_AUDIO_STREAM_SOURCE_CHANGED);
    assert(GetTickCount64() - before < 1000u);
    assert(admission.write_count == 3u && admission.writes[2][28] == 4u);
    CloseHandle(stop);

    memset(&capture, 0, sizeof(capture));
    memset(&admission, 0, sizeof(admission));
    stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    capture.origin_ready = true;
    for (index = 0u; index < 100u; ++index)
        enqueue(&capture, 0, index, ((uint64_t)index * UINT64_C(1000000000)) /
                                   48000u, (ul_audio_gap){0}, (float)index);
    admission.slow_audio_ms = 1u;
    admission.stop_after_audio = 100u;
    assert(run_stream(&capture, &spec, &admission, stop) == UL_AUDIO_STREAM_OK);
    assert(admission.audio_count == 100u && admission.write_count == 102u);
    CloseHandle(stop);
}

static void test_clean_stop_drains_tail_and_final_gap(void)
{
    struct ul_audio_capture capture = {0};
    struct ul_admission admission = {0};
    ul_audio_capture_spec spec = spec_for(1u);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    capture.origin_ready = true;
    enqueue(&capture, 0, 0, 0, (ul_audio_gap){0}, 1.0f);
    enqueue(&capture, 0, 1, 20833, (ul_audio_gap){0}, 2.0f);
    enqueue(&capture, 0, 2, 41666, (ul_audio_gap){0}, 3.0f);
    admission.stop_after_audio = 1u;
    assert(run_stream(&capture, &spec, &admission, stop) == UL_AUDIO_STREAM_OK);
    assert(admission.audio_count == 3u && admission.writes[4][5] == 4u);
    CloseHandle(stop);

    memset(&capture, 0, sizeof(capture));
    memset(&admission, 0, sizeof(admission));
    stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    capture.origin_ready = true;
    enqueue(&capture, 0, 0, 0, (ul_audio_gap){0}, 1.0f);
    capture.queues[0].final_gap = (ul_audio_gap){1, 2, 20833};
    admission.stop_after_audio = 1u;
    assert(run_stream(&capture, &spec, &admission, stop) ==
           UL_AUDIO_STREAM_SOURCE_CHANGED);
    assert(admission.writes[2][5] == 3u && admission.writes[3][5] == 4u &&
           admission.writes[3][28] == 5u);
    CloseHandle(stop);
}

static uint64_t block_timestamp(uint64_t sequence, uint32_t frames,
                                uint32_t rate)
{
    return sequence * frames * UINT64_C(1000000000) / rate;
}

static void test_max_blocks_six_full_tails(void)
{
    struct ul_audio_capture *capture = calloc(1u, sizeof(*capture));
    struct ul_admission *admission = calloc(1u, sizeof(*admission));
    ul_audio_capture_spec spec = spec_for(0x3fu);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    uint8_t bus;
    uint64_t sequence;
    assert(capture != NULL && admission != NULL && stop != NULL);
    capture->origin_ready = true;
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        for (sequence = 0u; sequence <= 48u; ++sequence) {
            enqueue_frames(capture, bus, sequence,
                           block_timestamp(sequence,
                                           UL_AUDIO_BLOCK_FRAMES,
                                           spec.sample_rate),
                           UL_AUDIO_BLOCK_FRAMES,
                           (float)(bus + 1u));
        }
    }
    admission->stop_after_audio = UL_AUDIO_CAPTURE_MIXES;
    assert(run_stream(capture, &spec, admission, stop) == UL_AUDIO_STREAM_OK);
    assert(capture->deactivate_calls == 1u);
    assert(admission->audio_count == UL_AUDIO_CAPTURE_MIXES * 49u);
    assert(admission->write_count == 1u + UL_AUDIO_CAPTURE_MIXES * 49u + 1u);
    assert(admission->largest_write_size ==
           UL_AUDIO_HEADER_BYTES + 37u + UL_AUDIO_BLOCK_FRAMES * 2u * 4u);
    assert(admission->largest_write != NULL &&
           admission->largest_write[5] == 2u &&
           admission->largest_write[28] == 0u &&
           get_u64(admission->largest_write + 29u) == 0u &&
           get_u32(admission->largest_write + 45u) ==
               UL_AUDIO_BLOCK_FRAMES);
    assert(admission->writes[admission->write_count - 1u][5] == 4u);
    assert(admission->writes[admission->write_count - 1u][28] == 1u);
    assert(admission->writes[admission->write_count - 1u][29] ==
           UL_AUDIO_CAPTURE_MIXES);
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        const uint8_t *entry =
            admission->writes[admission->write_count - 1u] + 30u + bus * 9u;
        assert(entry[0] == bus && get_u64(entry + 1u) == 48u);
    }
    clear_admission(admission);
    CloseHandle(stop);
    free(admission);
    free(capture);
}

static void test_total_drain_deadline(void)
{
    struct ul_audio_capture *capture = calloc(1u, sizeof(*capture));
    struct ul_admission *admission = calloc(1u, sizeof(*admission));
    ul_audio_capture_spec spec = spec_for(1u);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    ULONGLONG before;
    uint64_t sequence;
    unsigned index;
    assert(capture != NULL && admission != NULL && stop != NULL);
    capture->origin_ready = true;
    for (sequence = 0u; sequence <= 80u; ++sequence) {
        enqueue(capture, 0u, sequence,
                block_timestamp(sequence, 1u, spec.sample_rate),
                (ul_audio_gap){0}, 1.0f);
    }
    admission->stop_after_audio = 1u;
    admission->slow_audio_ms = 10u;
    before = GetTickCount64();
    assert(run_stream(capture, &spec, admission, stop) ==
           UL_AUDIO_STREAM_INCOMPLETE);
    assert(GetTickCount64() - before >= 50u &&
           GetTickCount64() - before < 1000u);
    assert(capture->deactivate_calls == 1u && admission->audio_count > 1u &&
           admission->audio_count < 81u);
    for (index = 0u; index < admission->write_count; ++index)
        assert(admission->writes[index][5] != 4u);
    clear_admission(admission);
    CloseHandle(stop);
    free(admission);
    free(capture);
}

int main(void)
{
    test_clean_fair_drain_and_ack();
    test_staging_refusals_emit_nothing();
    test_gap_and_source_failures();
    test_transport_and_ack_failures();
    test_end_write_and_ack_paths();
    test_stopped_queue_precedes_stop_event();
    test_metadata_and_argument_failures();
    test_tail_idle_and_no_total_duration();
    test_clean_stop_drains_tail_and_final_gap();
    test_max_blocks_six_full_tails();
    test_total_drain_deadline();
    puts("audio stream staging, transport, gaps and clean End ACK passed");
    return 0;
}
