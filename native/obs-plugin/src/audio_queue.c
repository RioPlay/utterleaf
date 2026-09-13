// SPDX-License-Identifier: GPL-2.0-or-later
#include "audio_queue.h"

#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>

struct ul_audio_queue {
    atomic_uint_fast64_t head;
    atomic_uint_fast64_t tail;
    atomic_int status;
    uint32_t planes;
    uint32_t plane_frame_bytes;
    uint32_t slots;
    size_t stride;
    size_t allocation_bytes;
    uint8_t *storage;
    /* Producer-owned until the callback has been detached and joined. */
    uint64_t next_sequence;
    ul_audio_gap pending_gap;
};

static void wipe(void *buffer, size_t bytes)
{
    volatile uint8_t *cursor = buffer;
    while (bytes-- != 0u)
        *cursor++ = 0u;
}

ul_audio_queue *ul_audio_queue_create(uint32_t planes, uint32_t plane_frame_bytes,
                                     uint32_t slots)
{
    ul_audio_queue *queue;
    if (planes == 0u || planes > 8u || plane_frame_bytes == 0u ||
        plane_frame_bytes > 32u / planes || slots == 0u ||
        slots > UL_AUDIO_QUEUE_MAX_SLOTS)
        return NULL;
    queue = calloc(1u, sizeof(*queue));
    if (queue == NULL)
        return NULL;
    atomic_init(&queue->head, 0u);
    atomic_init(&queue->tail, 0u);
    atomic_init(&queue->status, UL_AUDIO_QUEUE_OK);
    /* Never silently replace the callback's atomics with library mutexes. */
    if (!atomic_is_lock_free(&queue->head) || !atomic_is_lock_free(&queue->tail) ||
        !atomic_is_lock_free(&queue->status)) {
        free(queue);
        return NULL;
    }
    queue->planes = planes;
    queue->plane_frame_bytes = plane_frame_bytes;
    queue->slots = slots;
    queue->stride = sizeof(ul_audio_block_info) +
                    (size_t)planes * plane_frame_bytes * UL_AUDIO_BLOCK_FRAMES;
    queue->allocation_bytes = queue->stride * slots;
    queue->storage = calloc(1u, queue->allocation_bytes);
    if (queue->storage == NULL) {
        free(queue);
        return NULL;
    }
    return queue;
}

static ul_audio_queue_result fail(ul_audio_queue *queue,
                                   ul_audio_queue_result reason)
{
    int expected = UL_AUDIO_QUEUE_OK;
    atomic_compare_exchange_strong_explicit(&queue->status, &expected, reason,
                                            memory_order_relaxed,
                                            memory_order_relaxed);
    return (ul_audio_queue_result)atomic_load_explicit(&queue->status,
                                                       memory_order_relaxed);
}

ul_audio_queue_result ul_audio_queue_push(ul_audio_queue *queue,
    const uint8_t *const planes[8], uint32_t frames, uint64_t timestamp_ns)
{
    uint64_t head, tail, sequence;
    uint32_t plane, plane_bytes;
    uint8_t *slot;
    ul_audio_block_info info;
    ul_audio_queue_result status;

    if (queue == NULL)
        return UL_AUDIO_QUEUE_INVALID;
    status = ul_audio_queue_status(queue);
    if (status != UL_AUDIO_QUEUE_OK)
        return status;
    if (planes == NULL || frames == 0u || frames > UL_AUDIO_BLOCK_FRAMES)
        return fail(queue, UL_AUDIO_QUEUE_INVALID);
    for (plane = 0u; plane < queue->planes; ++plane) {
        if (planes[plane] == NULL)
            return fail(queue, UL_AUDIO_QUEUE_INVALID);
    }
    if (queue->next_sequence == UINT64_MAX)
        return fail(queue, UL_AUDIO_QUEUE_EXHAUSTED);
    sequence = queue->next_sequence++;
    head = atomic_load_explicit(&queue->head, memory_order_relaxed);
    tail = atomic_load_explicit(&queue->tail, memory_order_acquire);
    if (head - tail >= queue->slots) {
        if (queue->pending_gap.count == 0u) {
            queue->pending_gap.first_sequence = sequence;
            queue->pending_gap.timestamp_ns = timestamp_ns;
        }
        queue->pending_gap.count++;
        return UL_AUDIO_QUEUE_DROPPED;
    }
    plane_bytes = frames * queue->plane_frame_bytes;
    info = (ul_audio_block_info){sequence, timestamp_ns, queue->pending_gap,
                                  frames, plane_bytes * queue->planes};
    slot = queue->storage + (head % queue->slots) * queue->stride;
    memcpy(slot, &info, sizeof(info));
    for (plane = 0u; plane < queue->planes; ++plane)
        memcpy(slot + sizeof(info) + plane * plane_bytes,
                planes[plane], plane_bytes);
    queue->pending_gap = (ul_audio_gap){0};
    atomic_store_explicit(&queue->head, head + 1u, memory_order_release);
    return UL_AUDIO_QUEUE_OK;
}

bool ul_audio_queue_pop(ul_audio_queue *queue, ul_audio_block *out)
{
    uint64_t head, tail;
    uint8_t *slot;
    if (queue == NULL || out == NULL)
        return false;
    tail = atomic_load_explicit(&queue->tail, memory_order_relaxed);
    head = atomic_load_explicit(&queue->head, memory_order_acquire);
    if (head == tail)
        return false;
    slot = queue->storage + (tail % queue->slots) * queue->stride;
    memcpy(&out->info, slot, sizeof(out->info));
    memcpy(out->data, slot + sizeof(out->info), out->info.bytes);
    memset(slot, 0, queue->stride);
    atomic_store_explicit(&queue->tail, tail + 1u, memory_order_release);
    return true;
}

void ul_audio_queue_stop(ul_audio_queue *queue)
{
    if (queue != NULL)
        (void)fail(queue, UL_AUDIO_QUEUE_STOPPED);
}

ul_audio_queue_result ul_audio_queue_status(const ul_audio_queue *queue)
{
    return queue == NULL ? UL_AUDIO_QUEUE_INVALID :
        (ul_audio_queue_result)atomic_load_explicit(&queue->status,
                                                    memory_order_relaxed);
}

ul_audio_gap ul_audio_queue_final_gap(const ul_audio_queue *queue)
{
    return queue == NULL ? (ul_audio_gap){0} : queue->pending_gap;
}

void ul_audio_queue_destroy(ul_audio_queue *queue)
{
    if (queue == NULL)
        return;
    wipe(queue->storage, queue->allocation_bytes);
    free(queue->storage);
    wipe(queue, sizeof(*queue));
    free(queue);
}
