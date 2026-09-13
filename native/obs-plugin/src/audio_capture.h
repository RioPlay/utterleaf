// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_OBS_AUDIO_CAPTURE_H
#define UTTERLEAF_OBS_AUDIO_CAPTURE_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define UL_AUDIO_CAPTURE_MIXES 6u
#define UL_AUDIO_CAPTURE_STEREO_SAMPLES 2048u

typedef struct ul_audio_capture ul_audio_capture;
typedef struct ul_audio_queue ul_audio_queue;
typedef struct ul_audio_block ul_audio_block;

/* OBS values are copied into plain fields so runtime-only fixtures do not need
 * OBS headers. Identity values are opaque comparison tokens, never handles. */
typedef struct ul_audio_capture_spec {
    uint32_t sample_rate;
    uint32_t speakers;
    uint32_t channels;
    uint8_t primary_bus;
    uint8_t mix_mask;
    uintptr_t audio_identity;
    uintptr_t output_identity;
} ul_audio_capture_spec;

/* Frontend-thread only while the frontend gate proves OBS is live. This takes
 * and releases its own reference to the current streaming output. */
bool ul_audio_capture_inspect_frontend(uint8_t additional_mask,
                                       ul_audio_capture_spec *out);
/* Frontend-thread identity/format guard for an active generation. */
bool ul_audio_capture_matches_frontend(const ul_audio_capture_spec *expected);

/* Worker-only. Allocates bounded per-bus queues and independent converters. */
ul_audio_capture *ul_audio_capture_create_worker(
    const ul_audio_capture_spec *spec);

void ul_audio_capture_retain(ul_audio_capture *capture);

/* Final release must be on a non-audio thread. It seals and deactivates before
 * destroying worker converters and queues. */
void ul_audio_capture_release(ul_audio_capture *capture);

/* Frontend-thread only under the frontend gate. Re-inspects the live output,
 * removes stale static hooks, and connects inactive hooks for this generation.
 * The caller must retain capture independently across this call. */
bool ul_audio_capture_connect_frontend(ul_audio_capture *capture,
                                       uintptr_t generation);

/* Control-thread operations. Activate only after the runtime revalidates the
 * generation and STARTED phase. Deactivate permanently seals this capture and
 * returns after every callback that could see it has left. */
bool ul_audio_capture_activate(ul_audio_capture *capture);
void ul_audio_capture_deactivate(ul_audio_capture *capture);

/* Frontend-thread only under the frontend gate. A generation cleanup cannot
 * remove newer hooks. all is reserved for normal STOP/EXIT teardown. */
void ul_audio_capture_disconnect_frontend(uintptr_t generation, bool all);

/* Terminal unload fallback after OBS may already have destroyed global audio.
 * Makes static callbacks inert and calls no OBS API. */
void ul_audio_capture_abandon_after_shutdown(void);

bool ul_audio_capture_origin(const ul_audio_capture *capture,
                             uint64_t *origin_ns);
bool ul_audio_capture_failed(const ul_audio_capture *capture);
ul_audio_queue *ul_audio_capture_queue(ul_audio_capture *capture, uint8_t bus);

/* Worker-only. Converts one native queue block to exactly block.frames stereo
 * frames. Any metadata or converter failure permanently fails the capture. */
bool ul_audio_capture_convert(ul_audio_capture *capture, uint8_t bus,
                              const ul_audio_block *block,
                              float stereo[UL_AUDIO_CAPTURE_STEREO_SAMPLES]);

#ifdef __cplusplus
}
#endif

#endif
