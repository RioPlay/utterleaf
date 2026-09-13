// SPDX-License-Identifier: GPL-2.0-or-later
/* Reuse the SDK-free capture/admission plane without rerunning its legacy main. */
#define main ul_audio_stream_legacy_fixture_main
#include "audio_stream_test.c"
#undef main

#include "../src/audio_metadata.h"

static struct ul_admission *routing_admission;
static bool routing_initial = true;
static bool routing_changed = true;
static bool routing_failed;
static bool routing_fail_after_audio;
static bool routing_invalid_update;
static uint8_t routing_mask = 1u;
static unsigned routing_change_after_audio = 1u;
static bool routing_closed;
static unsigned routing_requests;

static void fill_snapshot(ul_audio_metadata_snapshot *out, uint64_t token,
                          const char *source_name)
{
    static const uint8_t source_id[16] = {
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15
    };
    memset(out, 0, sizeof(*out));
    out->token = token;
    out->observed_at_ns = token == 1u ? 100u : 200u;
    out->primary_bus = 0u;
    out->bus_mask = routing_mask;
    for (uint8_t bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        ul_audio_metadata_bus *label;
        if ((routing_mask & (uint8_t)(1u << bus)) == 0u)
            continue;
        label = &out->buses[out->bus_count++];
        label->bus = bus;
        label->label_length = 5u;
        memcpy(label->label, "Mix 1", 5u);
        label->label[4] = (uint8_t)('1' + bus);
    }
    out->source_count = 1u;
    memcpy(out->sources[0].source_id, source_id, sizeof(source_id));
    out->sources[0].selected_mask = routing_mask;
    out->sources[0].name_length = routing_invalid_update && token == 2u
                                      ? 1u : (uint16_t)strlen(source_name);
    if (routing_invalid_update && token == 2u)
        out->sources[0].name[0] = ' ';
    else
        memcpy(out->sources[0].name, source_name,
               out->sources[0].name_length);
}

bool ul_audio_metadata_take_worker(uintptr_t generation, uint64_t after_token,
                                   ul_audio_metadata_snapshot *out)
{
    assert(generation == 77u && out != NULL);
    if (routing_failed)
        return false;
    if (routing_initial && after_token < 1u) {
        fill_snapshot(out, 1u, "Desktop");
        return true;
    }
    if (routing_changed && after_token < 2u && routing_admission != NULL &&
        routing_admission->audio_count >= routing_change_after_audio) {
        fill_snapshot(out, 2u, "Desktop renamed");
        return true;
    }
    return false;
}

bool ul_audio_metadata_request_worker(uintptr_t generation)
{
    assert(generation == 77u);
    routing_requests++;
    return !routing_failed && !routing_closed;
}

bool ul_audio_metadata_failed(uintptr_t generation)
{
    assert(generation == 77u);
    return routing_failed ||
           (routing_fail_after_audio && routing_admission != NULL &&
            routing_admission->audio_count >= 1u);
}

static uint64_t routing_revision(const struct ul_admission *admission,
                                 unsigned write_index)
{
    assert(admission->writes[write_index][4] == 2u &&
           admission->writes[write_index][5] == 5u);
    return get_u64(admission->writes[write_index] + 28u);
}

static uint64_t routing_position(const struct ul_admission *admission,
                                 unsigned write_index, unsigned bus_index)
{
    /* header12 + session16 + revision8 + observed8 + primary/mask/count2 */
    return get_u64(admission->writes[write_index] + 49u + bus_index * 16u);
}

static void test_initial_and_changed_routing_order(void)
{
    struct ul_audio_capture capture = {0};
    struct ul_admission admission = {0};
    ul_audio_capture_spec spec = spec_for(5u);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    HANDLE cleanup = CreateEventW(NULL, TRUE, FALSE, NULL);
    assert(stop != NULL && cleanup != NULL);
    capture.origin_ready = true;
    enqueue(&capture, 0u, 0u, 0u, (ul_audio_gap){0}, 1.0f);
    enqueue(&capture, 0u, 1u, 20833u, (ul_audio_gap){0}, 2.0f);
    enqueue(&capture, 0u, 2u, 41666u, (ul_audio_gap){0}, 5.0f);
    enqueue(&capture, 2u, 0u, 0u, (ul_audio_gap){0}, 3.0f);
    enqueue(&capture, 2u, 1u, 20833u, (ul_audio_gap){0}, 4.0f);
    admission.stop_event = stop;
    admission.stop_after_audio = 4u;
    admission.slow_audio_ms = 2u;
    routing_admission = &admission;
    routing_initial = routing_changed = true;
    routing_failed = false;
    routing_fail_after_audio = false;
    routing_invalid_update = false;
    routing_closed = false;
    routing_mask = 5u;
    routing_change_after_audio = 3u;
    routing_requests = 0u;
    assert(ul_audio_stream_run_metadata(
               &capture, &spec, &admission, session, stop, cleanup,
               fake_disarm, NULL, 77u) == UL_AUDIO_STREAM_OK);
    assert(admission.write_count == 9u);
    assert(admission.writes[0][4] == 2u && admission.writes[0][5] == 1u);
    assert(routing_revision(&admission, 1u) == 1u &&
           routing_position(&admission, 1u, 0u) == 0u &&
           routing_position(&admission, 1u, 1u) == 0u);
    assert(admission.writes[2][5] == 2u && admission.writes[2][28] == 0u &&
           get_u64(admission.writes[2] + 29u) == 0u);
    assert(admission.writes[3][5] == 2u && admission.writes[3][28] == 2u);
    assert(admission.writes[4][5] == 2u && admission.writes[4][28] == 0u &&
           get_u64(admission.writes[4] + 29u) == 1u);
    assert(routing_revision(&admission, 5u) == 2u &&
           routing_position(&admission, 5u, 0u) == 2u &&
           routing_position(&admission, 5u, 1u) == 1u);
    assert(admission.writes[6][5] == 2u && admission.writes[6][28] == 2u &&
           get_u64(admission.writes[6] + 29u) == 1u);
    assert(admission.writes[7][5] == 2u && admission.writes[7][28] == 0u &&
           get_u64(admission.writes[7] + 29u) == 2u);
    assert(admission.writes[8][5] == 4u && admission.writes[8][4] == 2u);
    assert(routing_requests != 0u);
    clear_admission(&admission);
    CloseHandle(cleanup);
    CloseHandle(stop);
    routing_admission = NULL;
    routing_mask = 1u;
    routing_change_after_audio = 1u;
}

static void test_missing_initial_snapshot_is_terminal_before_pcm(void)
{
    struct ul_audio_capture capture = {0};
    struct ul_admission admission = {0};
    ul_audio_capture_spec spec = spec_for(1u);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    HANDLE cleanup = CreateEventW(NULL, TRUE, FALSE, NULL);
    assert(stop != NULL && cleanup != NULL);
    capture.origin_ready = true;
    enqueue(&capture, 0u, 0u, 0u, (ul_audio_gap){0}, 1.0f);
    admission.stop_event = stop;
    routing_admission = &admission;
    routing_initial = false;
    routing_changed = false;
    routing_failed = false;
    routing_fail_after_audio = false;
    routing_invalid_update = false;
    routing_mask = 1u;
    routing_closed = false;
    assert(ul_audio_stream_run_metadata(
               &capture, &spec, &admission, session, stop, cleanup,
               fake_disarm, NULL, 77u) == UL_AUDIO_STREAM_SOURCE_CHANGED);
    assert(admission.audio_count == 0u && admission.write_count == 2u);
    assert(admission.writes[0][5] == 1u && admission.writes[0][4] == 2u);
    assert(admission.writes[1][5] == 4u && admission.writes[1][28] ==
               UL_AUDIO_END_SOURCE_CHANGED);
    CloseHandle(cleanup);
    CloseHandle(stop);
    routing_admission = NULL;
}

static void test_refresh_failure_stops_after_accepted_prefix(void)
{
    struct ul_audio_capture capture = {0};
    struct ul_admission admission = {0};
    ul_audio_capture_spec spec = spec_for(1u);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    HANDLE cleanup = CreateEventW(NULL, TRUE, FALSE, NULL);
    assert(stop != NULL && cleanup != NULL);
    capture.origin_ready = true;
    enqueue(&capture, 0u, 0u, 0u, (ul_audio_gap){0}, 1.0f);
    enqueue(&capture, 0u, 1u, 20833u, (ul_audio_gap){0}, 2.0f);
    admission.stop_event = stop;
    routing_admission = &admission;
    routing_initial = true;
    routing_changed = false;
    routing_failed = false;
    routing_fail_after_audio = true;
    routing_invalid_update = false;
    routing_mask = 1u;
    routing_closed = false;
    assert(ul_audio_stream_run_metadata(
               &capture, &spec, &admission, session, stop, cleanup,
               fake_disarm, NULL, 77u) == UL_AUDIO_STREAM_SOURCE_CHANGED);
    assert(admission.audio_count == 1u && admission.write_count == 4u);
    assert(admission.writes[0][5] == 1u &&
           admission.writes[1][5] == 5u &&
           admission.writes[2][5] == 2u &&
           admission.writes[3][5] == 4u &&
           admission.writes[3][28] == UL_AUDIO_END_SOURCE_CHANGED);
    CloseHandle(cleanup);
    CloseHandle(stop);
    routing_admission = NULL;
    routing_fail_after_audio = false;
}

static void test_invalid_changed_snapshot_is_source_failure(void)
{
    struct ul_audio_capture capture = {0};
    struct ul_admission admission = {0};
    ul_audio_capture_spec spec = spec_for(1u);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    HANDLE cleanup = CreateEventW(NULL, TRUE, FALSE, NULL);
    assert(stop != NULL && cleanup != NULL);
    capture.origin_ready = true;
    enqueue(&capture, 0u, 0u, 0u, (ul_audio_gap){0}, 1.0f);
    enqueue(&capture, 0u, 1u, 20833u, (ul_audio_gap){0}, 2.0f);
    admission.stop_event = stop;
    routing_admission = &admission;
    routing_initial = routing_changed = true;
    routing_failed = routing_fail_after_audio = false;
    routing_invalid_update = true;
    routing_mask = 1u;
    routing_closed = false;
    assert(ul_audio_stream_run_metadata(
               &capture, &spec, &admission, session, stop, cleanup,
               fake_disarm, NULL, 77u) == UL_AUDIO_STREAM_SOURCE_CHANGED);
    assert(admission.audio_count == 1u && admission.write_count == 4u);
    assert(admission.writes[3][5] == 4u &&
           admission.writes[3][28] == UL_AUDIO_END_SOURCE_CHANGED);
    CloseHandle(cleanup);
    CloseHandle(stop);
    routing_admission = NULL;
    routing_invalid_update = false;
}

static void test_v2_gap_and_empty_disarm_terminal_packets(void)
{
    struct ul_audio_capture capture = {0};
    struct ul_admission admission = {0};
    ul_audio_capture_spec spec = spec_for(1u);
    HANDLE stop = CreateEventW(NULL, TRUE, FALSE, NULL);
    HANDLE cleanup = CreateEventW(NULL, TRUE, TRUE, NULL);
    assert(stop != NULL && cleanup != NULL);
    capture.origin_ready = true;
    enqueue(&capture, 0u, 0u, 0u, (ul_audio_gap){0}, 1.0f);
    enqueue(&capture, 0u, 2u, 41666u,
            (ul_audio_gap){1u, 1u, 20833u}, 2.0f);
    admission.stop_event = stop;
    routing_admission = &admission;
    routing_initial = true;
    routing_changed = routing_failed = routing_fail_after_audio = false;
    routing_invalid_update = false;
    routing_mask = 1u;
    routing_closed = false;
    assert(ul_audio_stream_run_metadata(
               &capture, &spec, &admission, session, stop, cleanup,
               fake_disarm, NULL, 77u) == UL_AUDIO_STREAM_SOURCE_CHANGED);
    assert(admission.write_count == 5u &&
           admission.writes[3][5] == 3u &&
           admission.writes[4][5] == 4u);
    for (unsigned index = 0u; index < admission.write_count; ++index)
        assert(admission.writes[index][4] == 2u);
    clear_admission(&admission);
    memset(&admission, 0, sizeof(admission));
    assert(ul_audio_stream_finish_empty_disarm(&admission, session, cleanup) ==
           UL_AUDIO_STREAM_OK);
    assert(admission.write_count == 1u && admission.writes[0][4] == 2u &&
           admission.writes[0][5] == 4u &&
           admission.writes[0][28] == UL_AUDIO_END_DISARMED &&
           admission.writes[0][29] == 0u);
    CloseHandle(cleanup);
    CloseHandle(stop);
    routing_admission = NULL;
}

static void test_closed_snapshot_finishes_precommitted_tails(void)
{
    for (unsigned disarmed = 0u; disarmed < 2u; ++disarmed) {
        struct ul_audio_capture capture = {0};
        struct ul_admission admission = {0};
        ul_audio_capture_spec spec = spec_for(1u);
        HANDLE stop = CreateEventW(NULL, TRUE, disarmed == 0u, NULL);
        HANDLE cleanup = CreateEventW(NULL, TRUE, TRUE, NULL);
        int result;
        assert(stop != NULL && cleanup != NULL);
        capture.origin_ready = true;
        capture.queues[0].status = UL_AUDIO_QUEUE_STOPPED;
        enqueue(&capture, 0u, 0u, 0u, (ul_audio_gap){0}, 1.0f);
        admission.stop_event = stop;
        routing_admission = &admission;
        routing_initial = true;
        routing_changed = routing_failed = routing_fail_after_audio = false;
        routing_invalid_update = false;
        routing_mask = 1u;
        routing_closed = true;
        if (disarmed != 0u)
            result = ul_audio_stream_run_disarmed_metadata(
                &capture, &spec, &admission, session, stop, cleanup, 77u);
        else
            result = ul_audio_stream_run_metadata(
                &capture, &spec, &admission, session, stop, cleanup,
                fake_disarm, NULL, 77u);
        assert(result == UL_AUDIO_STREAM_OK && admission.write_count == 4u);
        assert(admission.writes[0][5] == 1u &&
               admission.writes[1][5] == 5u &&
               admission.writes[2][5] == 2u &&
               admission.writes[3][5] == 4u &&
               admission.writes[3][28] ==
                   (disarmed != 0u ? UL_AUDIO_END_DISARMED
                                   : UL_AUDIO_END_STREAM_STOPPED));
        CloseHandle(cleanup);
        CloseHandle(stop);
    }
    routing_admission = NULL;
    routing_closed = false;
}

int main(void)
{
    test_initial_and_changed_routing_order();
    test_missing_initial_snapshot_is_terminal_before_pcm();
    test_refresh_failure_stops_after_accepted_prefix();
    test_invalid_changed_snapshot_is_source_failure();
    test_v2_gap_and_empty_disarm_terminal_packets();
    test_closed_snapshot_finishes_precommitted_tails();
    puts("audio stream v2 routing ordering and failure passed");
    return 0;
}
