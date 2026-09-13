// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_AUDIO_QUEUE_H
#define UTTERLEAF_AUDIO_QUEUE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define UL_AUDIO_BLOCK_FRAMES 1024u
#define UL_AUDIO_BLOCK_BYTES (UL_AUDIO_BLOCK_FRAMES * 8u * 4u)
#define UL_AUDIO_QUEUE_MAX_SLOTS 96u

typedef struct ul_audio_queue ul_audio_queue;

typedef struct ul_audio_gap {
    uint64_t first_sequence;
    uint64_t count;
    uint64_t timestamp_ns;
} ul_audio_gap;

typedef struct ul_audio_block_info {
    uint64_t sequence;
    uint64_t timestamp_ns;
    ul_audio_gap gap; /* Whole blocks dropped before this accepted block. */
    uint32_t frames;
    uint32_t bytes;
} ul_audio_block_info;

typedef struct ul_audio_block {
    ul_audio_block_info info;
    /* Native planes concatenated; each plane has frames * plane_frame_bytes. */
    uint8_t data[UL_AUDIO_BLOCK_BYTES];
} ul_audio_block;

typedef enum ul_audio_queue_result {
    UL_AUDIO_QUEUE_OK = 0,
    UL_AUDIO_QUEUE_DROPPED,
    UL_AUDIO_QUEUE_STOPPED,
    UL_AUDIO_QUEUE_INVALID,
    UL_AUDIO_QUEUE_EXHAUSTED
} ul_audio_queue_result;

/* Allocate before attaching a callback. One queue per selected OBS bus; exactly
 * one producer and one consumer. The adapter chooses slots to bound queued time.
 * planes * plane_frame_bytes must be <= 32. No format conversion happens here. */
ul_audio_queue *ul_audio_queue_create(uint32_t planes, uint32_t plane_frame_bytes,
                                     uint32_t slots);

/* Producer only: no allocation, wait, I/O or conversion. Full means whole-block
 * drop; sequence still advances. Plane pointers must cover the declared frames.
 * Invalid metadata and sequence exhaustion are terminal. */
ul_audio_queue_result ul_audio_queue_push(ul_audio_queue *queue,
    const uint8_t *const planes[8], uint32_t frames, uint64_t timestamp_ns);

/* Consumer only: copy one accepted block, releasing its slot before return.
 * False means empty/invalid argument; output is unchanged. May drain after stop. */
bool ul_audio_queue_pop(ul_audio_queue *queue, ul_audio_block *out);

/* Safe from a control thread, but does not wait for an in-flight producer.
 * The caller must detach/join callbacks before final_gap or destroy, and join
 * the consumer before destroy. Neither stop nor an empty queue proves quiescence. */
void ul_audio_queue_stop(ul_audio_queue *queue);
ul_audio_queue_result ul_audio_queue_status(const ul_audio_queue *queue);
ul_audio_gap ul_audio_queue_final_gap(const ul_audio_queue *queue);
void ul_audio_queue_destroy(ul_audio_queue *queue);

#endif
