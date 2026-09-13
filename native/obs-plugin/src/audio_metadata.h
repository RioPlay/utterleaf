// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_OBS_AUDIO_METADATA_H
#define UTTERLEAF_OBS_AUDIO_METADATA_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define UL_AUDIO_METADATA_MIXES 6u
#define UL_AUDIO_METADATA_MAX_SOURCES 128u
#define UL_AUDIO_METADATA_MAX_WATCHED_SOURCES 512u
#define UL_AUDIO_METADATA_MAX_BUS_LABEL_BYTES 64u
#define UL_AUDIO_METADATA_MAX_SOURCE_NAME_BYTES 128u

typedef struct ul_audio_metadata_bus {
    uint8_t bus;
    uint16_t label_length;
    uint8_t label[UL_AUDIO_METADATA_MAX_BUS_LABEL_BYTES];
} ul_audio_metadata_bus;

typedef struct ul_audio_metadata_source {
    uint8_t source_id[16];
    uint8_t selected_mask;
    uint16_t name_length;
    uint8_t name[UL_AUDIO_METADATA_MAX_SOURCE_NAME_BYTES];
} ul_audio_metadata_source;

/* token is a local publication token, not the contiguous wire revision. */
typedef struct ul_audio_metadata_snapshot {
    uint64_t token;
    uint64_t observed_at_ns;
    uint8_t primary_bus;
    uint8_t bus_mask;
    uint8_t bus_count;
    uint16_t source_count;
    ul_audio_metadata_bus buses[UL_AUDIO_METADATA_MIXES];
    ul_audio_metadata_source sources[UL_AUDIO_METADATA_MAX_SOURCES];
} ul_audio_metadata_snapshot;

typedef bool (*ul_audio_metadata_schedule)(uintptr_t generation);

/* One plugin-global observer is supported. These calls are frontend-thread
 * only except take_worker/request_worker/retire_worker/failed. The scheduler must only enqueue a numeric
 * generation. It must be thread-safe, nonblocking, and must never wait for a
 * frontend lock, refresh, close, or queued task; OBS invokes it while holding
 * its signal mutex. It must not invoke refresh reentrantly. open publishes the
 * complete initial snapshot before returning success.
 *
 * close must run while OBS is live and without a lock needed by the scheduler.
 * OBS signal disconnection may wait for foreign callbacks before the internal
 * callback-drain timeout begins, so this API does not bound that OBS wait. */
bool ul_audio_metadata_open_frontend(uintptr_t generation,
                                     uint8_t primary_bus, uint8_t bus_mask,
                                     ul_audio_metadata_schedule schedule);
bool ul_audio_metadata_refresh_frontend(uintptr_t generation);
bool ul_audio_metadata_close_frontend(uintptr_t generation, bool all);
void ul_audio_metadata_fail_frontend(uintptr_t generation);
/* Terminal unload fallback after OBS signal/global teardown may have begun.
 * Makes static callbacks inert and calls no OBS API. */
void ul_audio_metadata_abandon_after_shutdown(void);

/* Single transport-worker reader. A true return copies the newest immutable
 * observation whose local token is greater than after_token. The same
 * generation may take the final snapshot after frontend close disconnects
 * watchers, allowing an already-accepted tail to finish. Reopen changes the
 * generation before publishing new data, so stale workers cannot cross it. */
bool ul_audio_metadata_take_worker(uintptr_t generation, uint64_t after_token,
                                   ul_audio_metadata_snapshot *out);
bool ul_audio_metadata_request_worker(uintptr_t generation);
/* Final transport-worker release clears the private immutable snapshot and
 * prevents queued refresh from republishing it before frontend disconnect. */
void ul_audio_metadata_retire_worker(uintptr_t generation);
bool ul_audio_metadata_failed(uintptr_t generation);

#ifdef __cplusplus
}
#endif

#endif
