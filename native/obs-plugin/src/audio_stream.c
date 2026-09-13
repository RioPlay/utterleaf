// SPDX-License-Identifier: GPL-2.0-or-later
#include "audio_stream.h"

#include "audio_protocol.h"
#include "audio_queue.h"
#include "session_protocol.h"

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

typedef struct stream_state {
    ul_audio_capture *capture;
    const ul_audio_capture_spec *spec;
    ul_admission *admission;
    const uint8_t *session;
    HANDLE stop_event;
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
    ULONGLONG drain_started_at;
} stream_state;

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
    size = ul_audio_encode_audio(state->packet, sizeof(state->packet),
                                 state->session, bus, block->info.sequence,
                                 block->info.timestamp_ns, block->info.frames,
                                 stereo);
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

static bool send_end(stream_state *state, uint8_t reason)
{
    ul_audio_end_sequence entries[UL_AUDIO_CAPTURE_MIXES];
    uint8_t acknowledgement[UL_SESSION_COMMAND_BYTES];
    size_t count = 0u, size;
    DWORD timeout;
    uint8_t bus;
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        if ((state->spec->mix_mask & (1u << bus)) == 0u)
            continue;
        entries[count].bus = bus;
        entries[count].has_sequence = state->sent[bus];
        entries[count].sequence = state->last_sequence[bus];
        count++;
    }
    size = ul_audio_encode_end(state->packet, sizeof(state->packet),
                               state->session, reason, entries, count);
    if (!write_packet(state, size))
        return false;
    timeout = io_timeout(state, UL_AUDIO_STREAM_ACK_TIMEOUT_MS);
    if (timeout == 0u || ul_admission_read_exact(state->admission, acknowledgement,
                                sizeof(acknowledgement),
                                timeout) !=
            UL_ADMISSION_AUTH_OK)
        return false;
    return ul_session_end_ack(acknowledgement, sizeof(acknowledgement),
                              state->session);
}

static int source_failure(stream_state *state, uint8_t reason)
{
    deactivate(state);
    if (state->started)
        (void)send_end(state, reason);
    return UL_AUDIO_STREAM_SOURCE_CHANGED;
}

static int stage_first_blocks(stream_state *state,
                              ul_audio_block staged[UL_AUDIO_CAPTURE_MIXES])
{
    bool ready[UL_AUDIO_CAPTURE_MIXES] = {false};
    uint8_t remaining = 0u, bus;
    ULONGLONG started_at = GetTickCount64();
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus)
        if ((state->spec->mix_mask & (1u << bus)) != 0u)
            remaining++;
    while (remaining != 0u) {
        DWORD wait_result;
        if (probe_transport(state) != UL_AUDIO_STREAM_OK)
            return UL_AUDIO_STREAM_TRANSPORT_ERROR;
        if (ul_audio_capture_failed(state->capture))
            return UL_AUDIO_STREAM_SOURCE_CHANGED;
        wait_result = WaitForSingleObject(state->stop_event, 0u);
        if (wait_result == WAIT_OBJECT_0)
            return UL_AUDIO_STREAM_INCOMPLETE;
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
                remaining--;
            } else if (ul_audio_queue_status(queue) != UL_AUDIO_QUEUE_OK) {
                return UL_AUDIO_STREAM_SOURCE_CHANGED;
            }
        }
        if (remaining == 0u)
            break;
        if (GetTickCount64() - started_at >= UL_AUDIO_STREAM_FIRST_TIMEOUT_MS)
            return UL_AUDIO_STREAM_SOURCE_CHANGED;
        wait_result = WaitForSingleObject(state->stop_event,
                                           UL_AUDIO_STREAM_POLL_MS);
        if (wait_result == WAIT_OBJECT_0)
            return UL_AUDIO_STREAM_INCOMPLETE;
        if (wait_result == WAIT_FAILED)
            return UL_AUDIO_STREAM_SOURCE_CHANGED;
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

static int send_gap_failure(stream_state *state, uint8_t bus,
                            const ul_audio_block *block)
{
    size_t size;
    if (!valid_block(state, bus, block, true) || block->info.gap.count == 0u)
        return source_failure(state, UL_AUDIO_END_SOURCE_CHANGED);
    size = ul_audio_encode_gap(state->packet, sizeof(state->packet),
                               state->session, bus,
                               block->info.gap.first_sequence,
                               block->info.gap.count,
                               block->info.gap.timestamp_ns);
    if (!write_packet(state, size)) {
        deactivate(state);
        return UL_AUDIO_STREAM_TRANSPORT_ERROR;
    }
    deactivate(state);
    (void)send_end(state, UL_AUDIO_END_TRANSPORT_ERROR);
    return UL_AUDIO_STREAM_SOURCE_CHANGED;
}

static int drain_stream(stream_state *state)
{
    ULONGLONG last_activity = GetTickCount64();
    uint8_t cursor = 0u;
    bool stopping = false;
    for (;;) {
        bool popped = false;
        uint8_t offset;
        DWORD wait_result;
        if (probe_transport(state) != UL_AUDIO_STREAM_OK) {
            deactivate(state);
            return UL_AUDIO_STREAM_TRANSPORT_ERROR;
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
                        (void)send_end(state, UL_AUDIO_END_SOURCE_CHANGED);
                        return UL_AUDIO_STREAM_SOURCE_CHANGED;
                    }
                    size_t size = ul_audio_encode_gap(
                        state->packet, sizeof(state->packet), state->session,
                        bus, gap.first_sequence, gap.count, gap.timestamp_ns);
                    if (!write_packet(state, size))
                        return UL_AUDIO_STREAM_TRANSPORT_ERROR;
                    (void)send_end(state, UL_AUDIO_END_TRANSPORT_ERROR);
                    return UL_AUDIO_STREAM_SOURCE_CHANGED;
                }
            }
            return send_end(state, UL_AUDIO_END_STREAM_STOPPED)
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

int ul_audio_stream_run(ul_audio_capture *capture,
                        const ul_audio_capture_spec *spec,
                        ul_admission *admission,
                        const uint8_t session[16], HANDLE stop_event)
{
    ul_audio_block staged[UL_AUDIO_CAPTURE_MIXES];
    stream_state state = {0};
    size_t size;
    uint8_t bus;
    int result;
    state.capture = capture;
    state.spec = spec;
    state.admission = admission;
    state.session = session;
    state.stop_event = stop_event;
    if (!valid_arguments(&state)) {
        deactivate(&state);
        return UL_AUDIO_STREAM_INCOMPLETE;
    }
    result = stage_first_blocks(&state, staged);
    if (result != UL_AUDIO_STREAM_OK) {
        deactivate(&state);
        return result;
    }
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        if ((spec->mix_mask & (1u << bus)) == 0u)
            continue;
        if (!valid_block(&state, bus, &staged[bus], false) ||
            !ul_audio_capture_convert(capture, bus, &staged[bus],
                                      state.staged_stereo[bus]) ||
            !finite_stereo(state.staged_stereo[bus],
                           staged[bus].info.frames)) {
            deactivate(&state);
            return UL_AUDIO_STREAM_SOURCE_CHANGED;
        }
    }
    size = ul_audio_encode_start(state.packet, sizeof(state.packet), session,
                                 spec->sample_rate, spec->primary_bus,
                                 spec->mix_mask, state.origin_ns);
    if (!write_packet(&state, size)) {
        deactivate(&state);
        return UL_AUDIO_STREAM_TRANSPORT_ERROR;
    }
    state.started = true;
    for (bus = 0u; bus < UL_AUDIO_CAPTURE_MIXES; ++bus) {
        if ((spec->mix_mask & (1u << bus)) == 0u)
            continue;
        result = send_converted_audio(&state, bus, &staged[bus],
                                      state.staged_stereo[bus]);
        if (result != UL_AUDIO_STREAM_OK) {
            deactivate(&state);
            return UL_AUDIO_STREAM_TRANSPORT_ERROR;
        }
    }
    result = drain_stream(&state);
    if (result != UL_AUDIO_STREAM_OK && state.draining &&
        io_timeout(&state, 1u) == 0u)
        return UL_AUDIO_STREAM_INCOMPLETE;
    return result;
}
