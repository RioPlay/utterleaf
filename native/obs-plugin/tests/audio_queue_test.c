// SPDX-License-Identifier: GPL-2.0-or-later
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static size_t allocation_calls;
static size_t allocation_fail_at;
static size_t outstanding_allocations;
static size_t largest_allocation;

static void *fixture_calloc(size_t count, size_t size)
{
    void *value;
    size_t bytes = count * size;
    allocation_calls++;
    if (bytes > largest_allocation)
        largest_allocation = bytes;
    if (allocation_fail_at != 0u && allocation_calls == allocation_fail_at)
        return NULL;
    value = calloc(count, size);
    if (value != NULL)
        outstanding_allocations++;
    return value;
}

static void fixture_free(void *value)
{
    if (value != NULL) {
        assert(outstanding_allocations > 0u);
        outstanding_allocations--;
    }
    free(value);
}

#define calloc fixture_calloc
#define free fixture_free
#include "../src/audio_queue.c"
#undef free
#undef calloc

#define THREAD_ITERATIONS 4096u

static void reset_allocations(void)
{
    assert(outstanding_allocations == 0u);
    allocation_calls = 0u;
    allocation_fail_at = 0u;
    largest_allocation = 0u;
}

static ul_audio_queue_result push_one(ul_audio_queue *queue, uint8_t first,
                                      uint8_t second, uint64_t timestamp)
{
    const uint8_t *planes[8] = {&first, &second};
    return ul_audio_queue_push(queue, planes, 1u, timestamp);
}

static void test_create_and_allocation_faults(void)
{
    ul_audio_queue *queue;
    reset_allocations();
    assert(ul_audio_queue_create(0, 1, 1) == NULL);
    assert(ul_audio_queue_create(9, 1, 1) == NULL);
    assert(ul_audio_queue_create(1, 0, 1) == NULL);
    assert(ul_audio_queue_create(2, 17, 1) == NULL);
    assert(ul_audio_queue_create(1, 1, 0) == NULL);
    assert(ul_audio_queue_create(1, 1, UL_AUDIO_QUEUE_MAX_SLOTS + 1u) == NULL);
    assert(allocation_calls == 0u);

    allocation_fail_at = 1u;
    assert(ul_audio_queue_create(1, 1, 1) == NULL);
    assert(outstanding_allocations == 0u);
    reset_allocations();
    allocation_fail_at = 2u;
    assert(ul_audio_queue_create(1, 1, 1) == NULL);
    assert(allocation_calls == 2u);
    assert(outstanding_allocations == 0u);

    reset_allocations();
    queue = ul_audio_queue_create(8, 4, UL_AUDIO_QUEUE_MAX_SLOTS);
    assert(queue != NULL);
    assert(allocation_calls == 2u);
    assert(queue->allocation_bytes == queue->stride * UL_AUDIO_QUEUE_MAX_SLOTS);
    assert(largest_allocation == queue->allocation_bytes);
    assert(queue->allocation_bytes <=
           (sizeof(ul_audio_block_info) + UL_AUDIO_BLOCK_BYTES) *
               UL_AUDIO_QUEUE_MAX_SLOTS);
    ul_audio_queue_destroy(queue);
    assert(outstanding_allocations == 0u);
}

static void test_copy_and_planar_packing(void)
{
    uint8_t first[6] = {1, 2, 3, 4, 5, 6};
    uint8_t second[6] = {7, 8, 9, 10, 11, 12};
    uint8_t third[6] = {13, 14, 15, 16, 17, 18};
    const uint8_t expected[18] = {
        1,2,3,4,5,6, 7,8,9,10,11,12, 13,14,15,16,17,18
    };
    const uint8_t *planes[8] = {first, second, third};
    ul_audio_block out;
    ul_audio_queue *queue;

    reset_allocations();
    queue = ul_audio_queue_create(3, 2, 2);
    assert(queue != NULL);
    assert(ul_audio_queue_push(queue, planes, 3, 1234) == UL_AUDIO_QUEUE_OK);
    memset(first, 0, sizeof(first));
    memset(second, 0, sizeof(second));
    memset(third, 0, sizeof(third));
    memset(&out, 0xa5, sizeof(out));
    assert(ul_audio_queue_pop(queue, &out));
    assert(out.info.sequence == 0u && out.info.timestamp_ns == 1234u);
    assert(out.info.frames == 3u && out.info.bytes == sizeof(expected));
    assert(out.info.gap.count == 0u);
    assert(memcmp(out.data, expected, sizeof(expected)) == 0);
    assert(!ul_audio_queue_pop(queue, &out));
    assert(out.info.sequence == 0u);
    ul_audio_queue_destroy(queue);
    assert(outstanding_allocations == 0u);
}

static void test_full_gap_and_trailing_gap(void)
{
    ul_audio_queue *queue;
    ul_audio_block out;
    ul_audio_gap gap;
    reset_allocations();
    queue = ul_audio_queue_create(2, 1, 1);
    assert(queue != NULL);
    assert(push_one(queue, 1, 2, 10) == UL_AUDIO_QUEUE_OK);
    assert(push_one(queue, 3, 4, 20) == UL_AUDIO_QUEUE_DROPPED);
    assert(push_one(queue, 5, 6, 30) == UL_AUDIO_QUEUE_DROPPED);
    assert(ul_audio_queue_pop(queue, &out));
    assert(out.info.sequence == 0u && out.info.gap.count == 0u);
    assert(push_one(queue, 7, 8, 40) == UL_AUDIO_QUEUE_OK);
    assert(ul_audio_queue_pop(queue, &out));
    assert(out.info.sequence == 3u && out.info.gap.first_sequence == 1u);
    assert(out.info.gap.count == 2u && out.info.gap.timestamp_ns == 20u);
    assert(out.data[0] == 7u && out.data[1] == 8u);

    assert(push_one(queue, 9, 10, 50) == UL_AUDIO_QUEUE_OK);
    assert(push_one(queue, 11, 12, 60) == UL_AUDIO_QUEUE_DROPPED);
    assert(push_one(queue, 13, 14, 70) == UL_AUDIO_QUEUE_DROPPED);
    ul_audio_queue_stop(queue);
    assert(ul_audio_queue_status(queue) == UL_AUDIO_QUEUE_STOPPED);
    assert(push_one(queue, 15, 16, 80) == UL_AUDIO_QUEUE_STOPPED);
    assert(ul_audio_queue_pop(queue, &out));
    assert(out.info.sequence == 4u);
    assert(!ul_audio_queue_pop(queue, &out));
    gap = ul_audio_queue_final_gap(queue);
    assert(gap.first_sequence == 5u && gap.count == 2u && gap.timestamp_ns == 60u);
    ul_audio_queue_destroy(queue);
    assert(outstanding_allocations == 0u);
}

static void test_invalid_terminal_and_exhaustion(void)
{
    uint8_t sample = 1;
    const uint8_t *planes[8] = {&sample};
    ul_audio_block out;
    ul_audio_queue *queue;

    assert(ul_audio_queue_push(NULL, planes, 1, 0) == UL_AUDIO_QUEUE_INVALID);
    assert(ul_audio_queue_status(NULL) == UL_AUDIO_QUEUE_INVALID);
    assert(ul_audio_queue_final_gap(NULL).count == 0u);
    assert(!ul_audio_queue_pop(NULL, &out));
    ul_audio_queue_stop(NULL);
    ul_audio_queue_destroy(NULL);

    reset_allocations();
    queue = ul_audio_queue_create(1, 1, 2);
    assert(queue != NULL);
    assert(ul_audio_queue_push(queue, NULL, 1, 0) == UL_AUDIO_QUEUE_INVALID);
    assert(ul_audio_queue_status(queue) == UL_AUDIO_QUEUE_INVALID);
    assert(ul_audio_queue_push(queue, planes, 1, 0) == UL_AUDIO_QUEUE_INVALID);
    ul_audio_queue_destroy(queue);

    reset_allocations();
    queue = ul_audio_queue_create(1, 1, 2);
    assert(queue != NULL);
    planes[0] = NULL;
    assert(ul_audio_queue_push(queue, planes, 1, 0) == UL_AUDIO_QUEUE_INVALID);
    ul_audio_queue_destroy(queue);

    reset_allocations();
    queue = ul_audio_queue_create(1, 1, 2);
    assert(queue != NULL);
    planes[0] = &sample;
    assert(ul_audio_queue_push(queue, planes, 0, 0) == UL_AUDIO_QUEUE_INVALID);
    ul_audio_queue_destroy(queue);

    reset_allocations();
    queue = ul_audio_queue_create(1, 1, 2);
    assert(queue != NULL);
    assert(ul_audio_queue_push(queue, planes, UL_AUDIO_BLOCK_FRAMES + 1u, 0) ==
           UL_AUDIO_QUEUE_INVALID);
    ul_audio_queue_destroy(queue);

    reset_allocations();
    queue = ul_audio_queue_create(1, 1, 2);
    assert(queue != NULL);
    queue->next_sequence = UINT64_MAX - 1u;
    assert(ul_audio_queue_push(queue, planes, 1, UINT64_MAX) == UL_AUDIO_QUEUE_OK);
    assert(ul_audio_queue_pop(queue, &out));
    assert(out.info.sequence == UINT64_MAX - 1u);
    assert(ul_audio_queue_push(queue, planes, 1, 0) == UL_AUDIO_QUEUE_EXHAUSTED);
    assert(ul_audio_queue_status(queue) == UL_AUDIO_QUEUE_EXHAUSTED);
    assert(queue->next_sequence == UINT64_MAX);
    ul_audio_queue_destroy(queue);
    assert(outstanding_allocations == 0u);
}

typedef struct thread_context {
    ul_audio_queue *queue;
    HANDLE consumer_start;
    HANDLE producer_resume;
    HANDLE reuse_published;
    HANDLE reuse_consumed;
    HANDLE producer_done;
    volatile LONG failed;
    uint64_t consumed;
    uint64_t accounted;
} thread_context;

static DWORD WINAPI producer_thread(void *opaque)
{
    thread_context *context = opaque;
    uint32_t sequence;
    for (sequence = 0u; sequence < THREAD_ITERATIONS; ++sequence) {
        uint8_t first[4], second[4];
        const uint8_t *planes[8] = {first, second};
        uint32_t index;
        ul_audio_queue_result result;
        for (index = 0u; index < 4u; ++index) {
            first[index] = (uint8_t)(sequence + index);
            second[index] = (uint8_t)(sequence * 3u + index);
        }
        result = ul_audio_queue_push(context->queue, planes, 4u,
                                     (uint64_t)sequence * 10u);
        if ((sequence < 4u && result != UL_AUDIO_QUEUE_OK) ||
            (sequence >= 4u && sequence <= 63u &&
             result != UL_AUDIO_QUEUE_DROPPED) ||
            (sequence == 64u && result != UL_AUDIO_QUEUE_OK) ||
            (result != UL_AUDIO_QUEUE_OK && result != UL_AUDIO_QUEUE_DROPPED))
            InterlockedExchange(&context->failed, 1);
        memset(first, 0, sizeof(first));
        memset(second, 0, sizeof(second));
        if (sequence == 63u) {
            SetEvent(context->consumer_start);
            if (WaitForSingleObject(context->producer_resume, 5000u) !=
                WAIT_OBJECT_0)
                InterlockedExchange(&context->failed, 1);
        } else if (sequence == 64u) {
            SetEvent(context->reuse_published);
            if (WaitForSingleObject(context->reuse_consumed, 5000u) !=
                WAIT_OBJECT_0)
                InterlockedExchange(&context->failed, 1);
        }
    }
    ul_audio_queue_stop(context->queue);
    SetEvent(context->producer_done);
    return 0;
}

static DWORD WINAPI consumer_thread(void *opaque)
{
    thread_context *context = opaque;
    ul_audio_block block;
    uint64_t expected = 0u;
    bool reuse_released = false;
    ULONGLONG deadline = GetTickCount64() + 10000u;
    if (WaitForSingleObject(context->consumer_start, 5000u) != WAIT_OBJECT_0) {
        InterlockedExchange(&context->failed, 1);
        return 0;
    }
    for (;;) {
        bool popped;
        if (!reuse_released && context->consumed == 4u) {
            SetEvent(context->producer_resume);
            if (WaitForSingleObject(context->reuse_published, 5000u) !=
                WAIT_OBJECT_0) {
                InterlockedExchange(&context->failed, 1);
                return 0;
            }
            reuse_released = true;
        }
        popped = ul_audio_queue_pop(context->queue, &block);
        if (!popped &&
            WaitForSingleObject(context->producer_done, 0u) == WAIT_OBJECT_0) {
            /* The producer may publish immediately before signalling done,
             * after this consumer's first empty observation. */
            popped = ul_audio_queue_pop(context->queue, &block);
            if (!popped)
                break;
        }
        if (popped) {
            uint32_t index;
            if (block.info.gap.count != 0u) {
                if (block.info.gap.first_sequence != expected ||
                    block.info.gap.timestamp_ns != expected * 10u)
                    InterlockedExchange(&context->failed, 1);
                expected += block.info.gap.count;
            }
            if (block.info.sequence != expected || block.info.frames != 4u ||
                block.info.bytes != 8u ||
                block.info.timestamp_ns != expected * 10u)
                InterlockedExchange(&context->failed, 1);
            for (index = 0u; index < 4u; ++index) {
                if (block.data[index] != (uint8_t)(expected + index) ||
                    block.data[4u + index] != (uint8_t)(expected * 3u + index))
                    InterlockedExchange(&context->failed, 1);
            }
            expected++;
            context->consumed++;
            if (block.info.sequence == 64u)
                SetEvent(context->reuse_consumed);
            continue;
        }
        if (GetTickCount64() >= deadline) {
            InterlockedExchange(&context->failed, 1);
            break;
        }
        SwitchToThread();
    }
    context->accounted = expected;
    return 0;
}

static void test_threaded_order_and_bound(void)
{
    thread_context context = {0};
    HANDLE producer, consumer;
    ul_audio_gap trailing;
    size_t fixed_allocation_calls, fixed_allocation_bytes;
    reset_allocations();
    context.queue = ul_audio_queue_create(2, 1, 4);
    assert(context.queue != NULL);
    fixed_allocation_calls = allocation_calls;
    fixed_allocation_bytes = largest_allocation;
    context.consumer_start = CreateEventW(NULL, TRUE, FALSE, NULL);
    context.producer_resume = CreateEventW(NULL, TRUE, FALSE, NULL);
    context.reuse_published = CreateEventW(NULL, TRUE, FALSE, NULL);
    context.reuse_consumed = CreateEventW(NULL, TRUE, FALSE, NULL);
    context.producer_done = CreateEventW(NULL, TRUE, FALSE, NULL);
    assert(context.consumer_start != NULL && context.producer_resume != NULL &&
           context.reuse_published != NULL && context.reuse_consumed != NULL &&
           context.producer_done != NULL);
    consumer = CreateThread(NULL, 0, consumer_thread, &context, 0, NULL);
    producer = CreateThread(NULL, 0, producer_thread, &context, 0, NULL);
    assert(consumer != NULL && producer != NULL);
    assert(WaitForSingleObject(producer, 15000u) == WAIT_OBJECT_0);
    assert(WaitForSingleObject(consumer, 15000u) == WAIT_OBJECT_0);
    assert(InterlockedCompareExchange(&context.failed, 0, 0) == 0);
    assert(ul_audio_queue_status(context.queue) == UL_AUDIO_QUEUE_STOPPED);
    assert(!ul_audio_queue_pop(context.queue, &(ul_audio_block){0}));
    trailing = ul_audio_queue_final_gap(context.queue);
    if (trailing.count != 0u) {
        assert(trailing.first_sequence == context.accounted);
        assert(trailing.timestamp_ns == context.accounted * 10u);
        context.accounted += trailing.count;
    }
    assert(context.consumed > 0u && context.consumed < THREAD_ITERATIONS);
    assert(context.accounted == THREAD_ITERATIONS);
    assert(allocation_calls == fixed_allocation_calls);
    assert(largest_allocation == fixed_allocation_bytes);
    CloseHandle(producer);
    CloseHandle(consumer);
    CloseHandle(context.consumer_start);
    CloseHandle(context.producer_resume);
    CloseHandle(context.reuse_published);
    CloseHandle(context.reuse_consumed);
    CloseHandle(context.producer_done);
    ul_audio_queue_destroy(context.queue);
    assert(outstanding_allocations == 0u);
}

int main(void)
{
    test_create_and_allocation_faults();
    test_copy_and_planar_packing();
    test_full_gap_and_trailing_gap();
    test_invalid_terminal_and_exhaustion();
    test_threaded_order_and_bound();
    puts("audio queue bounds, gaps and SPSC ordering passed");
    return 0;
}
