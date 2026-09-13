// SPDX-License-Identifier: GPL-2.0-or-later
#include "audio_stream.h"

#include "audio_protocol.h"
#include "audio_queue.h"
#include "session_protocol.h"
#if UL_AUDIO_RUNTIME_VERSION == UL_AUDIO_PROTOCOL_PROVENANCE_VERSION
#include "audio_metadata.h"
#endif

#include <math.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifndef UL_AUDIO_STREAM_FIRST_TIMEOUT_MS
#define UL_AUDIO_STREAM_FIRST_TIMEOUT_MS 5000u
#endif
#ifndef UL_AUDIO_STREAM_IDLE_TIMEOUT_MS
#define UL_AUDIO_STREAM_IDLE_TIMEOUT_MS 5000u
#endif
#ifndef UL_AUDIO_STREAM_WRITE_TIMEOUT_MS
#define UL_AUDIO_STREAM_WRITE_TIMEOUT_MS 1000u
#endif
#ifndef UL_AUDIO_STREAM_ACK_TIMEOUT_MS
#define UL_AUDIO_STREAM_ACK_TIMEOUT_MS 1000u
#endif
#ifndef UL_AUDIO_STREAM_POLL_MS
#define UL_AUDIO_STREAM_POLL_MS 5u
#endif
#ifndef UL_AUDIO_STREAM_DRAIN_TIMEOUT_MS
#define UL_AUDIO_STREAM_DRAIN_TIMEOUT_MS 5000u
#endif
#ifndef UL_AUDIO_STREAM_COMMAND_TIMEOUT_MS
#define UL_AUDIO_STREAM_COMMAND_TIMEOUT_MS 1000u
#endif
#ifndef UL_AUDIO_STREAM_METADATA_POLL_MS
#define UL_AUDIO_STREAM_METADATA_POLL_MS 250u
#endif

#define UL_AUDIO_STREAM_DISARMED_CONTROL 100
#define UL_AUDIO_STREAM_STOPPING_CONTROL 101

typedef struct stream_state {
    ul_audio_capture *capture;
    const ul_audio_capture_spec *spec;
    ul_admission *admission;
    const uint8_t *session;
    HANDLE stop_event;
    HANDLE cleanup_complete;
    ul_audio_disarm_callback disarm;
    void *disarm_context;
    uint8_t packet[UL_AUDIO_MAX_PACKET_BYTES];
    float stereo[UL_AUDIO_CAPTURE_STEREO_SAMPLES];
    float staged_stereo[UL_AUDIO_CAPTURE_MIXES]
                       [UL_AUDIO_CAPTURE_STEREO_SAMPLES];
    uint64_t origin_ns;
    uint64_t next_sequence[UL_AUDIO_CAPTURE_MIXES];
    uint64_t total_frames[UL_AUDIO_CAPTURE_MIXES];
    uint64_t last_sequence[UL_AUDIO_CAPTURE_MIXES];
    bool sent[UL_AUDIO_CAPTURE_MIXES];
    bool started;
    bool deactivated;
    bool draining;
    bool disarm_consumed;
    bool disarm_accepted;
    ULONGLONG drain_started_at;
#if UL_AUDIO_RUNTIME_VERSION == UL_AUDIO_PROTOCOL_PROVENANCE_VERSION
    uintptr_t metadata_generation;
    uint64_t metadata_token;
    uint64_t routing_revision;
    ULONGLONG metadata_requested_at;
#endif
} stream_state;

static DWORD io_timeout(const stream_state *state, DWORD requested);

static bool valid_rate(uint32_t rate)
{
    return rate == 16000u || rate == 32000u || rate == 44100u ||
           rate == 48000u || rate == 88200u || rate == 96000u;
}

static bool valid_arguments(const stream_state *state)
{
    const ul_audio_capture_spec *spec = state->spec;
    return state->capture != NULL && spec != NULL && state->admission != NULL &&
           state->session != NULL && state->stop_event != NULL &&
           state->stop_event != INVALID_HANDLE_VALUE && valid_rate(spec->sample_rate) &&
           state->cleanup_complete != NULL &&
           state->cleanup_complete != INVALID_HANDLE_VALUE &&
           (state->disarm != NULL || state->disarm_consumed) &&
           spec->channels >= 1u && spec->channels <= 8u &&
           spec->primary_bus < UL_AUDIO_CAPTURE_MIXES && spec->mix_mask != 0u &&
           (spec->mix_mask & ~0x3fu) == 0u &&
           (spec->mix_mask & (1u << spec->primary_bus)) != 0u &&
           spec->audio_identity != 0u && spec->output_identity != 0u;
}

static void deactivate(stream_state *state)
{
    if (state->capture != NULL && !state->deactivated) {
        ul_audio_capture_deactivate(state->capture);
        state->deactivated = true;
    }
}

static int probe_transport(stream_state *state)
{
    DWORD available = 0u;
    if (ul_admission_probe(state->admission, &available) != UL_ADMISSION_AUTH_OK ||
        available != 0u)
        return UL_AUDIO_STREAM_TRANSPORT_ERROR;
    return UL_AUDIO_STREAM_OK;
}

static int poll_control(stream_state *state)
{
    uint8_t command[UL_SESSION_COMMAND_BYTES];
    DWORD available = 0u;
    DWORD timeout;
    ul_audio_disarm_action action;
    if (ul_admission_probe(state->admission, &available) != UL_ADMISSION_AUTH_OK)
        return UL_AUDIO_STREAM_TRANSPORT_ERROR;
    if (available == 0u)
        return UL_AUDIO_STREAM_OK;
    if (state->disarm_consumed || state->disarm == NULL)
        return UL_AUDIO_STREAM_TRANSPORT_ERROR;
    timeout = io_timeout(state, UL_AUDIO_STREAM_COMMAND_TIMEOUT_MS);
    if (timeout == 0u ||
        ul_admission_read_exact(state->admission, command, sizeof(command),
                                timeout) != UL_ADMISSION_AUTH_OK ||
        !ul_session_disarm_request(command, sizeof(command), state->session))
        return UL_AUDIO_STREAM_TRANSPORT_ERROR;
    state->disarm_consumed = true;
    deactivate(state);
    action = state->disarm(state->disarm_context);
    if (action == UL_AUDIO_DISARM_REJECTED)
        return UL_AUDIO_STREAM_TRANSPORT_ERROR;
    if (!state->draining) {
        state->draining = true;
        state->drain_started_at = GetTickCount64();
    }
    state->disarm_accepted = action == UL_AUDIO_DISARM_ACCEPTED;
    return state->disarm_accepted ? UL_AUDIO_STREAM_DISARMED_CONTROL
                                  : UL_AUDIO_STREAM_STOPPING_CONTROL;
}

/* One total budget for the accepted tail and End receipt. Per-packet deadlines
 * alone would multiply the stop delay by every queued block on all six buses. */
static DWORD io_timeout(const stream_state *state, DWORD requested)
{
    if (state->draining) {
        ULONGLONG elapsed = GetTickCount64() - state->drain_started_at;
        if (elapsed >= UL_AUDIO_STREAM_DRAIN_TIMEOUT_MS)
            return 0u;
        DWORD remaining = (DWORD)(UL_AUDIO_STREAM_DRAIN_TIMEOUT_MS - elapsed);
        if (remaining < requested)
            return remaining;
    }
    return requested;
}

static bool write_packet(stream_state *state, size_t size)
{
    DWORD timeout = io_timeout(state, UL_AUDIO_STREAM_WRITE_TIMEOUT_MS);
    return size != 0u && timeout != 0u &&
           ul_admission_write_all(state->admission, state->packet, (DWORD)size,
                                  timeout) ==
               UL_ADMISSION_AUTH_OK;
}

static bool timestamp_expected(const stream_state *state, uint8_t bus,
                               uint64_t timestamp_ns)
{
    const uint64_t billion = UINT64_C(1000000000);
    uint64_t frames = state->total_frames[bus];
    uint64_t seconds = frames / state->spec->sample_rate;
    uint64_t remainder = frames % state->spec->sample_rate;
    uint64_t delta, expected, difference;
    if (seconds > (UINT64_MAX - state->origin_ns) / billion)
        return false;
    delta = seconds * billion +
            (remainder * billion) / state->spec->sample_rate;
    if (delta > UINT64_MAX - state->origin_ns)
        return false;
    expected = state->origin_ns + delta;
    difference = timestamp_ns >= expected ? timestamp_ns - expected
                                           : expected - timestamp_ns;
    return difference <= 1u;
}

static bool finite_stereo(const float *stereo, uint32_t frames)
{
    size_t index;
    for (index = 0u; index < (size_t)frames * 2u; ++index)
        if (!isfinite(stereo[index]))
            return false;
    return true;
}

static bool valid_block(const stream_state *state, uint8_t bus,
                        const ul_audio_block *block, bool allow_gap)
{
    uint64_t gap_end;
    if (block->info.frames == 0u ||
        block->info.frames > UL_AUDIO_BLOCK_FRAMES ||
        block->info.bytes != state->spec->channels * block->info.frames * 4u ||
        block->info.sequence > UL_AUDIO_MAX_SEQUENCE)
        return false;
    if (block->info.gap.count == 0u)
        return block->info.sequence == state->next_sequence[bus] &&
               timestamp_expected(state, bus, block->info.timestamp_ns);
    if (!allow_gap || block->info.gap.first_sequence !=
                          state->next_sequence[bus] ||
        block->info.gap.first_sequence > UL_AUDIO_MAX_SEQUENCE ||
        block->info.gap.count > UINT64_MAX - block->info.gap.first_sequence)
        return false;
    gap_end = block->info.gap.first_sequence + block->info.gap.count;
    return gap_end == block->info.sequence &&
           timestamp_expected(state, bus, block->info.gap.timestamp_ns);
}

static int send_converted_audio(stream_state *state, uint8_t bus,
                                const ul_audio_block *block,
                                const float *stereo)
{
    size_t size;
    size = ul_audio_encode_audio_version(
        UL_AUDIO_RUNTIME_VERSION, state->packet, sizeof(state->packet),
        state->session, bus, block->info.sequence, block->info.timestamp_ns,
        block->info.frames, stereo);
    if (!write_packet(state, size))
        return UL_AUDIO_STREAM_TRANSPORT_ERROR;
    state->sent[bus] = true;
    state->last_sequence[bus] = block->info.sequence;
    state->next_sequence[bus] = block->info.sequence + 1u;
    state->total_frames[bus] += block->info.frames;
    return UL_AUDIO_STREAM_OK;
}

static int send_audio(stream_state *state, uint8_t bus,
                      const ul_audio_block *block)
{
    if (!valid_block(state, bus, block, false) ||
        UINT64_MAX - state->total_frames[bus] < block->info.frames ||
        !ul_audio_capture_convert(state->capture, bus, block, state->stereo) ||
        !finite_stereo(state->stereo, block->info.frames))
        return UL_AUDIO_STREAM_SOURCE_CHANGED;
    return send_converted_audio(state, bus, block, state->stereo);
}

static bool receive_end_ack(stream_state *state, bool allow_disarm)
{
    uint8_t acknowledgement[UL_SESSION_COMMAND_BYTES];
    bool saw_disarm = false;
    ULONGLONG receipt_started = GetTickCount64();
    for (;;) {
        ULONGLONG elapsed = GetTickCount64() - receipt_started;
        DWORD timeout;
        DWORD available = 0u;
        if (elapsed >= UL_AUDIO_STREAM_ACK_TIMEOUT_MS)
            return false;
        timeout = io_timeout(state,
            UL_AUDIO_STREAM_ACK_TIMEOUT_MS - (DWORD)elapsed);
        if (timeout == 0u ||
            ul_admission_read_exact(state->admission, acknowledgement,
                                    sizeof(acknowledgement), timeout) !=
                UL_ADMISSION_AUTH_OK)
            return false;
        if (GetTickCount64() - receipt_started >=
            UL_AUDIO_STREAM_ACK_TIMEOUT_MS)
            return false;
        if (ul_session_end_ack(acknowledgement, sizeof(acknowledgement),
                               state->session)) {
            return ul_admission_probe(state->admission, &available) ==
                       UL_ADMISSION_AUTH_OK && available == 0u;
        }
        if (!allow_disarm || saw_disarm ||
            !ul_session_disarm_request(acknowledgement,
                                       sizeof(acknowledgement), state->session))
            return false;
        saw_disarm = true;
    }
}

static bool send_end(stream_state *state, uint8_t reason, bool allow_disarm)
{
    ul_audio_end_sequence entries[UL_AUDIO_CAPTURE_MIXES];
    size_t count = 0u, size;
    uint8_t bus;
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        if ((state->spec->mix_mask & (1u << bus)) == 0u)
            continue;
        entries[count].bus = bus;
        entries[count].has_sequence = state->sent[bus];
        entries[count].sequence = state->last_sequence[bus];
        count++;
    }
    size = ul_audio_encode_end_version(
        UL_AUDIO_RUNTIME_VERSION, state->packet, sizeof(state->packet),
        state->session, reason, entries, count);
    if (!write_packet(state, size))
        return false;
    return receive_end_ack(state, allow_disarm);
}

static int source_failure(stream_state *state, uint8_t reason)
{
    deactivate(state);
    if (state->started)
        (void)send_end(state, reason, false);
    return UL_AUDIO_STREAM_SOURCE_CHANGED;
}

static int stage_first_blocks(stream_state *state,
                              ul_audio_block staged[UL_AUDIO_CAPTURE_MIXES])
{
    bool ready[UL_AUDIO_CAPTURE_MIXES] = {false};
    uint8_t remaining = 0u, ready_count = 0u, bus;
    ULONGLONG started_at = GetTickCount64();
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus)
        if ((state->spec->mix_mask & (1u << bus)) != 0u)
            remaining++;
    while (remaining != 0u) {
        bool all_stopped = true;
        DWORD wait_result;
        int control = poll_control(state);
        if (control != UL_AUDIO_STREAM_OK &&
            control != UL_AUDIO_STREAM_DISARMED_CONTROL &&
            control != UL_AUDIO_STREAM_STOPPING_CONTROL)
            return UL_AUDIO_STREAM_TRANSPORT_ERROR;
        if (ul_audio_capture_failed(state->capture))
            return UL_AUDIO_STREAM_SOURCE_CHANGED;
#if UL_AUDIO_RUNTIME_VERSION == UL_AUDIO_PROTOCOL_PROVENANCE_VERSION
        if (state->metadata_generation == 0u ||
            ul_audio_metadata_failed(state->metadata_generation))
            return UL_AUDIO_STREAM_SOURCE_CHANGED;
        if (GetTickCount64() - state->metadata_requested_at >=
            UL_AUDIO_STREAM_METADATA_POLL_MS) {
            if (!ul_audio_metadata_request_worker(
                    state->metadata_generation))
                return UL_AUDIO_STREAM_SOURCE_CHANGED;
            state->metadata_requested_at = GetTickCount64();
        }
#endif
        wait_result = WaitForSingleObject(state->stop_event, 0u);
        if (wait_result == WAIT_OBJECT_0 && !state->draining) {
            state->draining = true;
            state->drain_started_at = GetTickCount64();
            deactivate(state);
        }
        if (wait_result == WAIT_FAILED)
            return UL_AUDIO_STREAM_SOURCE_CHANGED;
        for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
            ul_audio_queue *queue;
            if ((state->spec->mix_mask & (1u << bus)) == 0u || ready[bus])
                continue;
            queue = ul_audio_capture_queue(state->capture, bus);
            if (queue == NULL)
                return UL_AUDIO_STREAM_SOURCE_CHANGED;
            if (ul_audio_queue_pop(queue, &staged[bus])) {
                if (staged[bus].info.sequence != 0u ||
                    staged[bus].info.gap.count != 0u)
                    return UL_AUDIO_STREAM_SOURCE_CHANGED;
                ready[bus] = true;
                ready_count++;
                remaining--;
            } else {
                ul_audio_queue_result status = ul_audio_queue_status(queue);
                if (status == UL_AUDIO_QUEUE_OK)
                    all_stopped = false;
                else if (status != UL_AUDIO_QUEUE_STOPPED)
                    return UL_AUDIO_STREAM_SOURCE_CHANGED;
            }
        }
        if (remaining == 0u)
            break;
        if (state->disarm_accepted && all_stopped)
            return ready_count == 0u ? UL_AUDIO_STREAM_DISARMED_CONTROL
                                     : UL_AUDIO_STREAM_INCOMPLETE;
        if (state->draining && all_stopped)
            return UL_AUDIO_STREAM_INCOMPLETE;
        if (state->draining && io_timeout(state, 1u) == 0u)
            return UL_AUDIO_STREAM_INCOMPLETE;
        if (GetTickCount64() - started_at >= UL_AUDIO_STREAM_FIRST_TIMEOUT_MS)
            return UL_AUDIO_STREAM_SOURCE_CHANGED;
        if (state->draining) {
            Sleep(UL_AUDIO_STREAM_POLL_MS);
        } else {
            wait_result = WaitForSingleObject(state->stop_event,
                                               UL_AUDIO_STREAM_POLL_MS);
            if (wait_result == WAIT_FAILED)
                return UL_AUDIO_STREAM_SOURCE_CHANGED;
        }
    }
    if (!ul_audio_capture_origin(state->capture, &state->origin_ns))
        return UL_AUDIO_STREAM_SOURCE_CHANGED;
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        if ((state->spec->mix_mask & (1u << bus)) != 0u &&
            staged[bus].info.timestamp_ns != state->origin_ns)
            return UL_AUDIO_STREAM_SOURCE_CHANGED;
    }
    return UL_AUDIO_STREAM_OK;
}

static bool wait_cleanup(stream_state *state)
{
    if (!state->disarm_accepted)
        return true;
    for (;;) {
        DWORD waited = WaitForSingleObject(state->cleanup_complete,
                                           UL_AUDIO_STREAM_POLL_MS);
        if (waited == WAIT_OBJECT_0)
            return true;
        if (waited == WAIT_FAILED || io_timeout(state, 1u) == 0u)
            return false;
        if (probe_transport(state) != UL_AUDIO_STREAM_OK)
            return false;
    }
}

static int finish_empty_disarm(stream_state *state)
{
    size_t size;
    if (!wait_cleanup(state))
        return UL_AUDIO_STREAM_INCOMPLETE;
    size = ul_audio_encode_end_version(
        UL_AUDIO_RUNTIME_VERSION, state->packet, sizeof(state->packet),
        state->session, UL_AUDIO_END_DISARMED, NULL, 0u);
    if (!write_packet(state, size) || !receive_end_ack(state, false))
        return UL_AUDIO_STREAM_TRANSPORT_ERROR;
    return UL_AUDIO_STREAM_OK;
}

static int send_gap_failure(stream_state *state, uint8_t bus,
                            const ul_audio_block *block)
{
    size_t size;
    if (!valid_block(state, bus, block, true) || block->info.gap.count == 0u)
        return source_failure(state, UL_AUDIO_END_SOURCE_CHANGED);
    size = ul_audio_encode_gap_version(
        UL_AUDIO_RUNTIME_VERSION, state->packet, sizeof(state->packet),
        state->session, bus, block->info.gap.first_sequence,
        block->info.gap.count, block->info.gap.timestamp_ns);
    if (!write_packet(state, size)) {
        deactivate(state);
        return UL_AUDIO_STREAM_TRANSPORT_ERROR;
    }
    deactivate(state);
    (void)send_end(state, UL_AUDIO_END_TRANSPORT_ERROR, false);
    return UL_AUDIO_STREAM_SOURCE_CHANGED;
}

#if UL_AUDIO_RUNTIME_VERSION == UL_AUDIO_PROTOCOL_PROVENANCE_VERSION
static int send_pending_routing(stream_state *state, bool required)
{
    ul_audio_metadata_snapshot snapshot;
    ul_audio_routing_bus buses[UL_AUDIO_CAPTURE_MIXES];
    ul_audio_routing_source sources[UL_AUDIO_METADATA_MAX_SOURCES];
    size_t bus_count = 0u, index, size;
    uint8_t bus;
    if (state->metadata_generation == 0u ||
        ul_audio_metadata_failed(state->metadata_generation))
        return UL_AUDIO_STREAM_SOURCE_CHANGED;
    if (!ul_audio_metadata_take_worker(state->metadata_generation,
                                       state->metadata_token, &snapshot))
        return required ? UL_AUDIO_STREAM_SOURCE_CHANGED : UL_AUDIO_STREAM_OK;
    if (snapshot.primary_bus != state->spec->primary_bus ||
        snapshot.bus_mask != state->spec->mix_mask ||
        snapshot.bus_count == 0u ||
        snapshot.bus_count > UL_AUDIO_CAPTURE_MIXES ||
        snapshot.source_count > UL_AUDIO_METADATA_MAX_SOURCES ||
        state->routing_revision >= UL_AUDIO_MAX_SEQUENCE)
        return UL_AUDIO_STREAM_SOURCE_CHANGED;
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        const ul_audio_metadata_bus *metadata_bus;
        if ((snapshot.bus_mask & (uint8_t)(1u << bus)) == 0u)
            continue;
        if (bus_count >= snapshot.bus_count)
            return UL_AUDIO_STREAM_SOURCE_CHANGED;
        metadata_bus = &snapshot.buses[bus_count];
        if (metadata_bus->bus != bus || metadata_bus->label_length == 0u ||
            metadata_bus->label_length > UL_AUDIO_MAX_BUS_LABEL_BYTES)
            return UL_AUDIO_STREAM_SOURCE_CHANGED;
        buses[bus_count].bus = bus;
        buses[bus_count].next_sequence = state->next_sequence[bus];
        buses[bus_count].label = metadata_bus->label;
        buses[bus_count].label_length = metadata_bus->label_length;
        bus_count++;
    }
    if (bus_count != snapshot.bus_count)
        return UL_AUDIO_STREAM_SOURCE_CHANGED;
    for (index = 0u; index < snapshot.source_count; ++index) {
        const ul_audio_metadata_source *source = &snapshot.sources[index];
        memcpy(sources[index].source_id, source->source_id, 16u);
        sources[index].selected_mask = source->selected_mask;
        sources[index].name = source->name;
        sources[index].name_length = source->name_length;
    }
    size = ul_audio_encode_routing(
        state->packet, sizeof(state->packet), state->session,
        state->routing_revision + 1u, snapshot.observed_at_ns,
        snapshot.primary_bus, snapshot.bus_mask, buses, bus_count, sources,
        snapshot.source_count);
    if (size == 0u)
        return UL_AUDIO_STREAM_SOURCE_CHANGED;
    if (!write_packet(state, size))
        return UL_AUDIO_STREAM_TRANSPORT_ERROR;
    state->routing_revision++;
    state->metadata_token = snapshot.token;
    return UL_AUDIO_STREAM_OK;
}

static int poll_metadata(stream_state *state)
{
    ULONGLONG now = GetTickCount64();
    int result = send_pending_routing(state, false);
    if (result != UL_AUDIO_STREAM_OK)
        return result;
    if (now - state->metadata_requested_at >= UL_AUDIO_STREAM_METADATA_POLL_MS) {
        if (!ul_audio_metadata_request_worker(state->metadata_generation))
            return UL_AUDIO_STREAM_SOURCE_CHANGED;
        state->metadata_requested_at = now;
    }
    return UL_AUDIO_STREAM_OK;
}
#else
static int send_pending_routing(stream_state *state, bool required)
{
    (void)state;
    (void)required;
    return UL_AUDIO_STREAM_OK;
}

static int poll_metadata(stream_state *state)
{
    (void)state;
    return UL_AUDIO_STREAM_OK;
}
#endif

static int drain_stream(stream_state *state)
{
    ULONGLONG last_activity = GetTickCount64();
    uint8_t cursor = 0u;
    bool stopping = state->draining;
    for (;;) {
        bool popped = false;
        uint8_t offset;
        DWORD wait_result;
        int control = poll_control(state);
        if (control == UL_AUDIO_STREAM_TRANSPORT_ERROR) {
            deactivate(state);
            return UL_AUDIO_STREAM_TRANSPORT_ERROR;
        }
        if (control == UL_AUDIO_STREAM_DISARMED_CONTROL ||
            control == UL_AUDIO_STREAM_STOPPING_CONTROL)
            stopping = true;
        if (!stopping) {
            int metadata_result = poll_metadata(state);
            if (metadata_result == UL_AUDIO_STREAM_SOURCE_CHANGED)
                return source_failure(state, UL_AUDIO_END_SOURCE_CHANGED);
            if (metadata_result != UL_AUDIO_STREAM_OK) {
                deactivate(state);
                return UL_AUDIO_STREAM_TRANSPORT_ERROR;
            }
        }
        if (ul_audio_capture_failed(state->capture))
            return source_failure(state, UL_AUDIO_END_SOURCE_CHANGED);
        if (!stopping) {
            wait_result = WaitForSingleObject(state->stop_event, 0u);
            if (wait_result == WAIT_FAILED)
                return source_failure(state, UL_AUDIO_END_SOURCE_CHANGED);
            if (wait_result == WAIT_OBJECT_0) {
                state->draining = true;
                state->drain_started_at = GetTickCount64();
                deactivate(state);
                stopping = true;
            }
        }
        if (stopping && io_timeout(state, 1u) == 0u)
            return UL_AUDIO_STREAM_INCOMPLETE;
        for (offset = 0u; offset < UL_AUDIO_CAPTURE_MIXES; ++offset) {
            uint8_t bus = (uint8_t)((cursor + offset) % UL_AUDIO_CAPTURE_MIXES);
            ul_audio_queue *queue;
            ul_audio_block block;
            ul_audio_queue_result status;
            if ((state->spec->mix_mask & (1u << bus)) == 0u)
                continue;
            queue = ul_audio_capture_queue(state->capture, bus);
            if (queue == NULL)
                return source_failure(state, UL_AUDIO_END_SOURCE_CHANGED);
            if (ul_audio_queue_pop(queue, &block)) {
                int block_result;
                cursor = (uint8_t)((bus + 1u) % UL_AUDIO_CAPTURE_MIXES);
                popped = true;
                last_activity = GetTickCount64();
                if (block.info.gap.count != 0u)
                    return send_gap_failure(state, bus, &block);
                block_result = send_audio(state, bus, &block);
                if (block_result != UL_AUDIO_STREAM_OK) {
                    if (block_result == UL_AUDIO_STREAM_SOURCE_CHANGED)
                        return source_failure(state,
                                              UL_AUDIO_END_SOURCE_CHANGED);
                    deactivate(state);
                    return UL_AUDIO_STREAM_TRANSPORT_ERROR;
                }
                break;
            }
            status = ul_audio_queue_status(queue);
            /* Frontend quiesces callbacks before publishing stream_stop. A
             * worker scheduled in that short interval may see STOPPED first.
             * Await the event under the idle deadline; other faults stay fatal. */
            if ((!stopping && status != UL_AUDIO_QUEUE_OK &&
                 status != UL_AUDIO_QUEUE_STOPPED) ||
                (stopping && status != UL_AUDIO_QUEUE_STOPPED))
                return source_failure(state, UL_AUDIO_END_SOURCE_CHANGED);
        }
        if (popped)
            continue;
        if (stopping) {
            uint8_t bus;
            if (state->disarm_accepted &&
                WaitForSingleObject(state->cleanup_complete, 0u) !=
                    WAIT_OBJECT_0) {
                if (io_timeout(state, 1u) == 0u)
                    return UL_AUDIO_STREAM_INCOMPLETE;
                if (WaitForSingleObject(state->cleanup_complete,
                                        UL_AUDIO_STREAM_POLL_MS) == WAIT_FAILED)
                    return UL_AUDIO_STREAM_INCOMPLETE;
                continue;
            }
            for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
                ul_audio_gap gap;
                if ((state->spec->mix_mask & (1u << bus)) == 0u)
                    continue;
                gap = ul_audio_queue_final_gap(
                    ul_audio_capture_queue(state->capture, bus));
                if (gap.count != 0u) {
                    if (gap.first_sequence != state->next_sequence[bus] ||
                        gap.first_sequence > UL_AUDIO_MAX_SEQUENCE ||
                        gap.count > UINT64_MAX - gap.first_sequence ||
                        !timestamp_expected(state, bus, gap.timestamp_ns)) {
                        (void)send_end(state, UL_AUDIO_END_SOURCE_CHANGED, false);
                        return UL_AUDIO_STREAM_SOURCE_CHANGED;
                    }
                    size_t size = ul_audio_encode_gap_version(
                        UL_AUDIO_RUNTIME_VERSION, state->packet,
                        sizeof(state->packet), state->session, bus,
                        gap.first_sequence, gap.count, gap.timestamp_ns);
                    if (!write_packet(state, size))
                        return UL_AUDIO_STREAM_TRANSPORT_ERROR;
                    (void)send_end(state, UL_AUDIO_END_TRANSPORT_ERROR, false);
                    return UL_AUDIO_STREAM_SOURCE_CHANGED;
                }
            }
            return send_end(state,
                            state->disarm_accepted ? UL_AUDIO_END_DISARMED
                                                   : UL_AUDIO_END_STREAM_STOPPED,
                            !state->disarm_consumed)
                       ? UL_AUDIO_STREAM_OK
                       : UL_AUDIO_STREAM_TRANSPORT_ERROR;
        }
        if (GetTickCount64() - last_activity >= UL_AUDIO_STREAM_IDLE_TIMEOUT_MS)
            return source_failure(state, UL_AUDIO_END_SOURCE_CHANGED);
        wait_result = WaitForSingleObject(state->stop_event,
                                           UL_AUDIO_STREAM_POLL_MS);
        if (wait_result == WAIT_FAILED)
            return source_failure(state, UL_AUDIO_END_SOURCE_CHANGED);
    }
}

static int run_initialized(stream_state *state)
{
    ul_audio_block staged[UL_AUDIO_CAPTURE_MIXES];
    size_t size;
    uint8_t bus;
    int result;
    if (!valid_arguments(state)) {
        deactivate(state);
        return UL_AUDIO_STREAM_INCOMPLETE;
    }
    result = stage_first_blocks(state, staged);
    if (result == UL_AUDIO_STREAM_DISARMED_CONTROL)
        return finish_empty_disarm(state);
    if (result != UL_AUDIO_STREAM_OK) {
        deactivate(state);
        return result;
    }
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        if ((state->spec->mix_mask & (1u << bus)) == 0u)
            continue;
        if (!valid_block(state, bus, &staged[bus], false) ||
            !ul_audio_capture_convert(state->capture, bus, &staged[bus],
                                      state->staged_stereo[bus]) ||
            !finite_stereo(state->staged_stereo[bus],
                            staged[bus].info.frames)) {
            deactivate(state);
            return UL_AUDIO_STREAM_SOURCE_CHANGED;
        }
    }
    size = ul_audio_encode_start_version(
        UL_AUDIO_RUNTIME_VERSION, state->packet, sizeof(state->packet),
        state->session, state->spec->sample_rate, state->spec->primary_bus,
        state->spec->mix_mask, state->origin_ns);
    if (!write_packet(state, size)) {
        deactivate(state);
        return UL_AUDIO_STREAM_TRANSPORT_ERROR;
    }
    state->started = true;
    result = send_pending_routing(state, true);
    if (result != UL_AUDIO_STREAM_OK) {
        deactivate(state);
        if (result == UL_AUDIO_STREAM_SOURCE_CHANGED)
            (void)send_end(state, UL_AUDIO_END_SOURCE_CHANGED, false);
        return result;
    }
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        if ((state->spec->mix_mask & (1u << bus)) == 0u)
            continue;
        result = send_converted_audio(state, bus, &staged[bus],
                                      state->staged_stereo[bus]);
        if (result != UL_AUDIO_STREAM_OK) {
            deactivate(state);
            return UL_AUDIO_STREAM_TRANSPORT_ERROR;
        }
    }
    result = drain_stream(state);
    if (result != UL_AUDIO_STREAM_OK && state->draining &&
        io_timeout(state, 1u) == 0u)
        return UL_AUDIO_STREAM_INCOMPLETE;
    return result;
}

int ul_audio_stream_run(ul_audio_capture *capture,
                        const ul_audio_capture_spec *spec,
                        ul_admission *admission,
                        const uint8_t session[16], HANDLE stop_event,
                        HANDLE cleanup_complete,
                        ul_audio_disarm_callback disarm,
                        void *disarm_context)
{
    return ul_audio_stream_run_metadata(
        capture, spec, admission, session, stop_event, cleanup_complete,
        disarm, disarm_context, 0u);
}

int ul_audio_stream_run_metadata(ul_audio_capture *capture,
                                 const ul_audio_capture_spec *spec,
                                 ul_admission *admission,
                                 const uint8_t session[16], HANDLE stop_event,
                                 HANDLE cleanup_complete,
                                 ul_audio_disarm_callback disarm,
                                 void *disarm_context,
                                 uintptr_t metadata_generation)
{
    stream_state state = {0};
    state.capture = capture;
    state.spec = spec;
    state.admission = admission;
    state.session = session;
    state.stop_event = stop_event;
    state.cleanup_complete = cleanup_complete;
    state.disarm = disarm;
    state.disarm_context = disarm_context;
#if UL_AUDIO_RUNTIME_VERSION == UL_AUDIO_PROTOCOL_PROVENANCE_VERSION
    state.metadata_generation = metadata_generation;
    state.metadata_requested_at = GetTickCount64();
#else
    (void)metadata_generation;
#endif
    return run_initialized(&state);
}

int ul_audio_stream_run_disarmed(ul_audio_capture *capture,
                                 const ul_audio_capture_spec *spec,
                                 ul_admission *admission,
                                 const uint8_t session[16], HANDLE stop_event,
                                 HANDLE cleanup_complete)
{
    return ul_audio_stream_run_disarmed_metadata(
        capture, spec, admission, session, stop_event, cleanup_complete, 0u);
}

int ul_audio_stream_run_disarmed_metadata(
    ul_audio_capture *capture, const ul_audio_capture_spec *spec,
    ul_admission *admission, const uint8_t session[16], HANDLE stop_event,
    HANDLE cleanup_complete, uintptr_t metadata_generation)
{
    stream_state state = {0};
    state.capture = capture;
    state.spec = spec;
    state.admission = admission;
    state.session = session;
    state.stop_event = stop_event;
    state.cleanup_complete = cleanup_complete;
    state.disarm_consumed = true;
    state.disarm_accepted = true;
    state.draining = true;
    state.drain_started_at = GetTickCount64();
#if UL_AUDIO_RUNTIME_VERSION == UL_AUDIO_PROTOCOL_PROVENANCE_VERSION
    state.metadata_generation = metadata_generation;
    state.metadata_requested_at = GetTickCount64();
#else
    (void)metadata_generation;
#endif
    return run_initialized(&state);
}

int ul_audio_stream_finish_empty_disarm(ul_admission *admission,
                                        const uint8_t session[16],
                                        HANDLE cleanup_complete)
{
    stream_state state = {0};
    state.admission = admission;
    state.session = session;
    state.cleanup_complete = cleanup_complete;
    state.disarm_accepted = cleanup_complete != NULL &&
                            cleanup_complete != INVALID_HANDLE_VALUE;
    state.draining = true;
    state.drain_started_at = GetTickCount64();
    if (admission == NULL || session == NULL ||
        cleanup_complete == INVALID_HANDLE_VALUE)
        return UL_AUDIO_STREAM_INCOMPLETE;
    return finish_empty_disarm(&state);
}
