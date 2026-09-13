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
                        const uint8_t session[16], HANDLE stop_event);

#endif
