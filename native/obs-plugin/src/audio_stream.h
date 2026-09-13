// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_OBS_AUDIO_STREAM_H
#define UTTERLEAF_OBS_AUDIO_STREAM_H

#include "admission.h"
#include "audio_capture.h"

#include <windows.h>

#include <stdint.h>

typedef enum ul_audio_stream_result {
    UL_AUDIO_STREAM_OK = 0,
    UL_AUDIO_STREAM_INCOMPLETE = 1,
    UL_AUDIO_STREAM_SOURCE_CHANGED = 2,
    UL_AUDIO_STREAM_TRANSPORT_ERROR = 3,
} ul_audio_stream_result;

typedef enum ul_audio_disarm_action {
    UL_AUDIO_DISARM_REJECTED = 0,
    UL_AUDIO_DISARM_ACCEPTED = 1,
    UL_AUDIO_DISARM_ALREADY_STOPPING = 2,
} ul_audio_disarm_action;

/* Called by the single transport worker after it has parsed an exact Disarm
 * and deactivated the capture. It may only commit state and queue nonblocking
 * frontend cleanup; it must not wait for the frontend or call OBS. */
typedef ul_audio_disarm_action (*ul_audio_disarm_callback)(void *context);

/* Synchronous single-worker transport, entered only after the Arm reply and
 * frontend capture activation have committed. The function always deactivates
 * a non-NULL capture before returning. Clean success requires a decoded End
 * acknowledgement from the authenticated client. It never releases capture or
 * calls OBS/frontend APIs. Normal stop has a five-second total drain/I/O budget;
 * a slow reader leaves an incomplete capture. This does not limit stream length.
 * Hard cancellation/EXIT may close transport without a terminal End packet. */
int ul_audio_stream_run(ul_audio_capture *capture,
                        const ul_audio_capture_spec *spec,
                        ul_admission *admission,
                        const uint8_t session[16], HANDLE stop_event,
                        HANDLE cleanup_complete,
                        ul_audio_disarm_callback disarm,
                        void *disarm_context);

/* Version-selectable runtime entry used by the plugin session worker. A
 * version-2 run requires the current generation's metadata observation. Its
 * final immutable snapshot remains usable after frontend watcher disconnect
 * so an already-accepted stop/Disarm tail can finish; version 1 ignores it. */
int ul_audio_stream_run_metadata(ul_audio_capture *capture,
                                 const ul_audio_capture_spec *spec,
                                 ul_admission *admission,
                                 const uint8_t session[16], HANDLE stop_event,
                                 HANDLE cleanup_complete,
                                 ul_audio_disarm_callback disarm,
                                 void *disarm_context,
                                 uintptr_t metadata_generation);

/* Continues after plugin_state already consumed Disarm and atomically observed
 * an attached capture. The capture must already be deactivated. */
int ul_audio_stream_run_disarmed(ul_audio_capture *capture,
                                 const ul_audio_capture_spec *spec,
                                 ul_admission *admission,
                                 const uint8_t session[16], HANDLE stop_event,
                                 HANDLE cleanup_complete);
int ul_audio_stream_run_disarmed_metadata(
    ul_audio_capture *capture, const ul_audio_capture_spec *spec,
    ul_admission *admission, const uint8_t session[16], HANDLE stop_event,
    HANDLE cleanup_complete, uintptr_t metadata_generation);

/* Completes a valid Disarm before capture emitted Start. The only wire packet
 * is End(DISARMED) with zero sequence entries, followed by its exact receipt.
 * NULL cleanup_complete asserts that no frontend hook can still attach. */
int ul_audio_stream_finish_empty_disarm(ul_admission *admission,
                                        const uint8_t session[16],
                                        HANDLE cleanup_complete);

#endif
