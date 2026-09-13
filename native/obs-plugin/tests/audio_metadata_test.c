// SPDX-License-Identifier: GPL-2.0-or-later
#include <windows.h>

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static HANDLE callback_entered;
static HANDLE callback_continue;
static HANDLE take_locked;
static HANDLE take_continue;
static HANDLE scheduler_entered;
static HANDLE scheduler_continue;
static HANDLE before_publish;
static HANDLE publish_continue;
static volatile LONG pause_callback;
static volatile LONG pause_take;
static volatile LONG pause_scheduler;
static volatile LONG pause_publish;
static uint64_t test_time_ns(void);
static void test_callback_entered(void);
static void test_take_locked(void);
static void test_before_publish(void);
#define UL_AUDIO_METADATA_CALLBACK_ENTERED() test_callback_entered()
#define UL_AUDIO_METADATA_TAKE_LOCKED() test_take_locked()
#define UL_AUDIO_METADATA_TIME_NS() test_time_ns()
#define UL_AUDIO_METADATA_BEFORE_PUBLISH() test_before_publish()
#define UL_AUDIO_METADATA_CLOSE_TIMEOUT_MS 5000u
#include "../src/audio_metadata.c"

typedef struct signal_slot {
    const char *name;
    signal_callback_t callback;
    void *data;
} signal_slot;

struct signal_handler {
    signal_slot slots[8];
    size_t count;
};

struct obs_source {
    struct signal_handler handler;
    enum obs_source_type type;
    uint32_t flags;
    uint32_t mixers;
    bool removed;
    bool enumerable;
    bool no_handler;
    LONG refs;
    char uuid[37];
    char name[160];
};

static struct signal_handler core_handler;
static struct obs_source sources[UL_AUDIO_METADATA_MAX_WATCHED_SOURCES + 1u];
static size_t source_count;
static uint64_t fake_time;
static uint32_t schedule_calls;
static uintptr_t scheduled_generation;
static bool schedule_success;
static bool mutate_during_enumeration;

static void test_callback_entered(void)
{
    if (InterlockedCompareExchange(&pause_callback, 0, 0) != 0) {
        SetEvent(callback_entered);
        assert(WaitForSingleObject(callback_continue, 5000u) == WAIT_OBJECT_0);
    }
}

static void test_take_locked(void)
{
    if (InterlockedCompareExchange(&pause_take, 0, 0) != 0) {
        SetEvent(take_locked);
        assert(WaitForSingleObject(take_continue, 5000u) == WAIT_OBJECT_0);
    }
}

static void test_before_publish(void)
{
    if (InterlockedCompareExchange(&pause_publish, 0, 0) != 0) {
        SetEvent(before_publish);
        assert(WaitForSingleObject(publish_continue, 5000u) == WAIT_OBJECT_0);
    }
}

static bool schedule_refresh(uintptr_t generation)
{
    schedule_calls++;
    scheduled_generation = generation;
    if (InterlockedCompareExchange(&pause_scheduler, 0, 0) != 0) {
        SetEvent(scheduler_entered);
        assert(WaitForSingleObject(scheduler_continue, 5000u) == WAIT_OBJECT_0);
    }
    return schedule_success;
}

signal_handler_t *obs_get_signal_handler(void)
{
    return &core_handler;
}

void signal_handler_connect(signal_handler_t *handler, const char *name,
                            signal_callback_t callback, void *data)
{
    size_t index;
    assert(handler != NULL && name != NULL && callback != NULL);
    for (index = 0u; index < handler->count; ++index)
        if (strcmp(handler->slots[index].name, name) == 0 &&
            handler->slots[index].callback == callback &&
            handler->slots[index].data == data)
            return;
    assert(handler->count < sizeof(handler->slots) / sizeof(handler->slots[0]));
    handler->slots[handler->count++] = (signal_slot){name, callback, data};
}

void signal_handler_disconnect(signal_handler_t *handler, const char *name,
                               signal_callback_t callback, void *data)
{
    size_t index;
    assert(handler != NULL);
    for (index = 0u; index < handler->count; ++index) {
        signal_slot *slot = &handler->slots[index];
        if (strcmp(slot->name, name) == 0 && slot->callback == callback &&
            slot->data == data) {
            handler->slots[index] = handler->slots[--handler->count];
            return;
        }
    }
}

static void fire_signal(struct signal_handler *handler, const char *name)
{
    signal_slot copy[8];
    size_t count = handler->count, index;
    memcpy(copy, handler->slots, count * sizeof(copy[0]));
    for (index = 0u; index < count; ++index)
        if (strcmp(copy[index].name, name) == 0)
            copy[index].callback(copy[index].data, NULL);
}

void obs_enum_sources(bool (*callback)(void *, obs_source_t *), void *data)
{
    size_t index;
    for (index = 0u; index < source_count; ++index)
        if (sources[index].enumerable && !sources[index].removed) {
            if (!callback(data, &sources[index]))
                break;
            if (mutate_during_enumeration) {
                mutate_during_enumeration = false;
                strcpy(sources[index].name, "After snapshot signal");
                fire_signal(&sources[index].handler, "rename");
            }
        }
}

enum obs_source_type obs_source_get_type(const obs_source_t *source)
{
    return source->type;
}

uint32_t obs_source_get_output_flags(const obs_source_t *source)
{
    return source->flags;
}

bool obs_source_removed(const obs_source_t *source)
{
    return source->removed;
}

obs_source_t *obs_source_get_ref(obs_source_t *source)
{
    if (source->removed)
        return NULL;
    InterlockedIncrement(&source->refs);
    return source;
}

void obs_source_release(obs_source_t *source)
{
    assert(InterlockedDecrement(&source->refs) >= 0);
}

signal_handler_t *obs_source_get_signal_handler(const obs_source_t *source)
{
    return source->no_handler ? NULL : (signal_handler_t *)&source->handler;
}

uint32_t obs_source_get_audio_mixers(const obs_source_t *source)
{
    return source->mixers;
}

const char *obs_source_get_uuid(const obs_source_t *source)
{
    return source->uuid;
}

const char *obs_source_get_name(const obs_source_t *source)
{
    return source->name;
}

static uint64_t test_time_ns(void)
{
    fake_time += 10u;
    return fake_time;
}

static void make_source(size_t index, uint32_t mixers)
{
    struct obs_source *source = &sources[index];
    memset(source, 0, sizeof(*source));
    source->type = OBS_SOURCE_TYPE_INPUT;
    source->flags = OBS_SOURCE_AUDIO;
    source->mixers = mixers;
    source->enumerable = true;
    assert(snprintf(source->uuid, sizeof(source->uuid),
                    "00000000-0000-0000-0000-%012llx",
                    (unsigned long long)(index + 1u)) == 36);
    assert(snprintf(source->name, sizeof(source->name),
                    "Input %u", (unsigned)index) > 0);
}

static void reset_fixture(void)
{
    size_t index;
    assert(!atomic_load_explicit(&metadata.active, memory_order_acquire));
    memset(&core_handler, 0, sizeof(core_handler));
    memset(sources, 0, sizeof(sources));
    source_count = 0u;
    fake_time = 1000u;
    schedule_calls = 0u;
    scheduled_generation = 0u;
    schedule_success = true;
    mutate_during_enumeration = false;
    InterlockedExchange(&pause_callback, 0);
    InterlockedExchange(&pause_take, 0);
    InterlockedExchange(&pause_scheduler, 0);
    InterlockedExchange(&pause_publish, 0);
    ResetEvent(callback_entered);
    ResetEvent(callback_continue);
    ResetEvent(take_locked);
    ResetEvent(take_continue);
    ResetEvent(scheduler_entered);
    ResetEvent(scheduler_continue);
    ResetEvent(before_publish);
    ResetEvent(publish_continue);
    atomic_store_explicit(&metadata.poisoned, false, memory_order_release);
    for (index = 0u; index < UL_AUDIO_METADATA_MAX_WATCHED_SOURCES + 1u;
         ++index)
        assert(sources[index].refs == 0);
}

static void test_initial_snapshot_stabilizes(void)
{
    ul_audio_metadata_snapshot snapshot;
    reset_fixture();
    source_count = 1u;
    make_source(0u, 1u);
    mutate_during_enumeration = true;
    assert(ul_audio_metadata_open_frontend(6u, 0u, 1u, schedule_refresh));
    assert(ul_audio_metadata_take_worker(6u, 0u, &snapshot));
    assert(snapshot.token == 2u && snapshot.source_count == 1u);
    assert(snapshot.sources[0].name_length == strlen("After snapshot signal"));
    assert(memcmp(snapshot.sources[0].name, "After snapshot signal",
                  snapshot.sources[0].name_length) == 0);
    assert(ul_audio_metadata_close_frontend(6u, false));
}

static void test_initial_change_remove_and_close(void)
{
    ul_audio_metadata_snapshot snapshot;
    uint64_t token;
    reset_fixture();
    source_count = 4u;
    make_source(0u, 1u);
    make_source(1u, 3u);
    make_source(2u, 3u);
    make_source(3u, 0u);
    sources[0].uuid[35] = '2';
    sources[1].uuid[35] = '1';
    sources[2].flags = OBS_SOURCE_VIDEO;
    assert(ul_audio_metadata_open_frontend(7u, 0u, 3u, schedule_refresh));
    assert(ul_audio_metadata_take_worker(7u, 0u, &snapshot));
    assert(snapshot.token == 1u && snapshot.observed_at_ns == 1010u);
    assert(snapshot.primary_bus == 0u && snapshot.bus_mask == 3u);
    assert(snapshot.bus_count == 2u && snapshot.source_count == 2u);
    assert(snapshot.buses[0].bus == 0u && snapshot.buses[1].bus == 1u);
    assert(memcmp(snapshot.buses[0].label, "Mix 1", 5u) == 0);
    assert(memcmp(snapshot.buses[1].label, "Mix 2", 5u) == 0);
    assert(snapshot.sources[0].source_id[15] == 1u);
    assert(snapshot.sources[1].source_id[15] == 2u);
    assert(snapshot.sources[0].selected_mask == 3u);
    assert(snapshot.sources[1].selected_mask == 1u);
    assert(sources[0].refs == 1 && sources[1].refs == 1 &&
           sources[3].refs == 1);
    token = snapshot.token;

    sources[0].mixers = 2u;
    strcpy(sources[0].name, "Renamed");
    fire_signal(&sources[0].handler, "audio_mixers");
    fire_signal(&sources[0].handler, "rename");
    assert(schedule_calls == 1u && scheduled_generation == 7u);
    assert(ul_audio_metadata_refresh_frontend(7u));
    assert(ul_audio_metadata_take_worker(7u, token, &snapshot));
    assert(snapshot.token == 2u && snapshot.sources[1].selected_mask == 2u);
    token = snapshot.token;

    fire_signal(&sources[0].handler, "rename");
    assert(ul_audio_metadata_refresh_frontend(7u));
    assert(!ul_audio_metadata_take_worker(7u, token, &snapshot));

    sources[3].mixers = 1u;
    fire_signal(&sources[3].handler, "audio_mixers");
    assert(ul_audio_metadata_refresh_frontend(7u));
    assert(ul_audio_metadata_take_worker(7u, token, &snapshot));
    assert(snapshot.token == 3u && snapshot.source_count == 3u);
    token = snapshot.token;
    sources[3].removed = true;
    sources[3].enumerable = false;
    fire_signal(&sources[3].handler, "remove");
    assert(ul_audio_metadata_refresh_frontend(7u));
    assert(ul_audio_metadata_take_worker(7u, token, &snapshot));
    assert(snapshot.token == 4u && snapshot.source_count == 2u);
    assert(sources[3].refs == 0 && sources[3].handler.count == 0u);
    token = snapshot.token;

    sources[0].removed = true;
    sources[0].enumerable = false;
    fire_signal(&sources[0].handler, "remove");
    assert(ul_audio_metadata_refresh_frontend(7u));
    assert(ul_audio_metadata_take_worker(7u, token, &snapshot));
    assert(snapshot.token == 5u && snapshot.source_count == 1u);
    token = snapshot.token;
    assert(sources[0].refs == 0 && sources[0].handler.count == 0u);
    assert(ul_audio_metadata_close_frontend(7u, false));
    assert(sources[1].refs == 0 && sources[1].handler.count == 0u);
    assert(core_handler.count == 0u);
    assert(ul_audio_metadata_take_worker(7u, 0u, &snapshot));
    assert(snapshot.token == token);
    ul_audio_metadata_retire_worker(7u);
    assert(!ul_audio_metadata_take_worker(7u, 0u, &snapshot));
}

static void test_visible_bounds_and_text_failures(void)
{
    size_t index;
    reset_fixture();
    source_count = UL_AUDIO_METADATA_MAX_SOURCES + 1u;
    for (index = 0u; index < source_count; ++index)
        make_source(index, 1u);
    assert(!ul_audio_metadata_open_frontend(8u, 0u, 1u, schedule_refresh));
    for (index = 0u; index < source_count; ++index)
        assert(sources[index].refs == 0 && sources[index].handler.count == 0u);

    reset_fixture();
    source_count = UL_AUDIO_METADATA_MAX_WATCHED_SOURCES + 1u;
    for (index = 0u; index < source_count; ++index)
        make_source(index, 0u);
    assert(!ul_audio_metadata_open_frontend(9u, 0u, 1u, schedule_refresh));
    for (index = 0u; index < source_count; ++index)
        assert(sources[index].refs == 0 && sources[index].handler.count == 0u);

    reset_fixture();
    source_count = 1u;
    make_source(0u, 1u);
    strcpy(sources[0].name, "   ");
    assert(!ul_audio_metadata_open_frontend(10u, 0u, 1u,
                                            schedule_refresh));
    assert(sources[0].refs == 0 && sources[0].handler.count == 0u);

    reset_fixture();
    source_count = 1u;
    make_source(0u, 1u);
    memcpy(sources[0].name, "\xe2\x80\x8d\xe2\x80\x8c", 7u);
    assert(!ul_audio_metadata_open_frontend(11u, 0u, 1u,
                                            schedule_refresh));

    reset_fixture();
    source_count = 1u;
    make_source(0u, 1u);
    memset(sources[0].name, 'x', UL_AUDIO_METADATA_MAX_SOURCE_NAME_BYTES + 1u);
    sources[0].name[UL_AUDIO_METADATA_MAX_SOURCE_NAME_BYTES + 1u] = '\0';
    assert(!ul_audio_metadata_open_frontend(11u, 0u, 1u,
                                            schedule_refresh));

    reset_fixture();
    source_count = 1u;
    make_source(0u, 1u);
    sources[0].no_handler = true;
    assert(!ul_audio_metadata_open_frontend(11u, 0u, 1u,
                                            schedule_refresh));
    assert(sources[0].refs == 0);
}

static void test_scheduler_failure_is_terminal(void)
{
    reset_fixture();
    source_count = 1u;
    make_source(0u, 1u);
    assert(ul_audio_metadata_open_frontend(12u, 0u, 1u, schedule_refresh));
    schedule_success = false;
    fire_signal(&sources[0].handler, "audio_mixers");
    assert(schedule_calls == 1u && ul_audio_metadata_failed(12u));
    assert(!ul_audio_metadata_refresh_frontend(12u));
    assert(ul_audio_metadata_close_frontend(12u, false));
}

static void test_worker_request_and_frontend_failure(void)
{
    ul_audio_metadata_snapshot snapshot;
    reset_fixture();
    source_count = 1u;
    make_source(0u, 1u);
    assert(ul_audio_metadata_open_frontend(13u, 0u, 1u, schedule_refresh));
    assert(ul_audio_metadata_take_worker(13u, 0u, &snapshot));
    schedule_calls = 0u;
    assert(!ul_audio_metadata_request_worker(12u));
    assert(ul_audio_metadata_request_worker(13u));
    assert(schedule_calls == 1u);
    assert(ul_audio_metadata_refresh_frontend(13u));
    assert(!ul_audio_metadata_failed(13u));
    ul_audio_metadata_fail_frontend(12u);
    assert(!ul_audio_metadata_failed(13u));
    ul_audio_metadata_fail_frontend(13u);
    assert(ul_audio_metadata_failed(13u));
    assert(!ul_audio_metadata_take_worker(13u, 0u, &snapshot));
    assert(!ul_audio_metadata_request_worker(13u));
    assert(ul_audio_metadata_close_frontend(13u, false));
}

static void test_abandon_makes_callbacks_inert(void)
{
    ul_audio_metadata_snapshot snapshot;
    reset_fixture();
    source_count = 1u;
    make_source(0u, 1u);
    assert(ul_audio_metadata_open_frontend(16u, 0u, 1u, schedule_refresh));
    schedule_calls = 0u;
    ul_audio_metadata_abandon_after_shutdown();
    fire_signal(&sources[0].handler, "audio_mixers");
    assert(schedule_calls == 0u && ul_audio_metadata_failed(16u));
    assert(!ul_audio_metadata_take_worker(16u, 0u, &snapshot));
    assert(!ul_audio_metadata_request_worker(16u));
}

typedef struct refresh_context {
    uintptr_t generation;
    bool result;
} refresh_context;

static DWORD WINAPI refresh_thread(void *parameter)
{
    refresh_context *context = parameter;
    context->result = ul_audio_metadata_refresh_frontend(context->generation);
    return 0u;
}

static void test_retire_blocks_inflight_republish(void)
{
    ul_audio_metadata_snapshot snapshot;
    refresh_context context = {17u, true};
    HANDLE worker;
    reset_fixture();
    source_count = 1u;
    make_source(0u, 1u);
    assert(ul_audio_metadata_open_frontend(17u, 0u, 1u, schedule_refresh));
    assert(ul_audio_metadata_take_worker(17u, 0u, &snapshot));
    strcpy(sources[0].name, "Changed while retiring");
    InterlockedExchange(&pause_publish, 1);
    worker = CreateThread(NULL, 0u, refresh_thread, &context, 0u, NULL);
    assert(worker != NULL);
    assert(WaitForSingleObject(before_publish, 5000u) == WAIT_OBJECT_0);
    ul_audio_metadata_retire_worker(17u);
    SetEvent(publish_continue);
    assert(WaitForSingleObject(worker, 5000u) == WAIT_OBJECT_0);
    assert(!context.result && ul_audio_metadata_failed(17u));
    assert(!ul_audio_metadata_take_worker(17u, 0u, &snapshot));
    assert(ul_audio_metadata_close_frontend(17u, false));
    CloseHandle(worker);
    InterlockedExchange(&pause_publish, 0);
}

static DWORD WINAPI signal_thread(void *unused)
{
    (void)unused;
    fire_signal(&sources[0].handler, "audio_mixers");
    return 0u;
}

typedef struct close_context {
    HANDLE done;
    uintptr_t generation;
    bool result;
} close_context;

static DWORD WINAPI close_thread(void *parameter)
{
    close_context *context = parameter;
    context->result = ul_audio_metadata_close_frontend(context->generation,
                                                       false);
    SetEvent(context->done);
    return 0u;
}

static void test_close_waits_for_inflight_callback(void)
{
    close_context context = {0};
    HANDLE signal_worker, close_worker;
    reset_fixture();
    source_count = 1u;
    make_source(0u, 1u);
    assert(ul_audio_metadata_open_frontend(13u, 0u, 1u, schedule_refresh));
    InterlockedExchange(&pause_callback, 1);
    signal_worker = CreateThread(NULL, 0u, signal_thread, NULL, 0u, NULL);
    assert(signal_worker != NULL);
    assert(WaitForSingleObject(callback_entered, 5000u) == WAIT_OBJECT_0);
    context.done = CreateEventW(NULL, TRUE, FALSE, NULL);
    context.generation = 13u;
    assert(context.done != NULL);
    close_worker = CreateThread(NULL, 0u, close_thread, &context, 0u, NULL);
    assert(close_worker != NULL);
    assert(WaitForSingleObject(context.done, 20u) == WAIT_TIMEOUT);
    SetEvent(callback_continue);
    assert(WaitForSingleObject(signal_worker, 5000u) == WAIT_OBJECT_0);
    assert(WaitForSingleObject(close_worker, 5000u) == WAIT_OBJECT_0);
    assert(context.result);
    CloseHandle(signal_worker);
    CloseHandle(close_worker);
    CloseHandle(context.done);
}

static void test_close_waits_for_nonblocking_scheduler(void)
{
    close_context context = {0};
    HANDLE signal_worker, close_worker;
    reset_fixture();
    source_count = 1u;
    make_source(0u, 1u);
    assert(ul_audio_metadata_open_frontend(16u, 0u, 1u, schedule_refresh));
    InterlockedExchange(&pause_scheduler, 1);
    signal_worker = CreateThread(NULL, 0u, signal_thread, NULL, 0u, NULL);
    assert(signal_worker != NULL);
    assert(WaitForSingleObject(scheduler_entered, 5000u) == WAIT_OBJECT_0);
    context.done = CreateEventW(NULL, TRUE, FALSE, NULL);
    context.generation = 16u;
    assert(context.done != NULL);
    close_worker = CreateThread(NULL, 0u, close_thread, &context, 0u, NULL);
    assert(close_worker != NULL);
    assert(WaitForSingleObject(context.done, 20u) == WAIT_TIMEOUT);
    SetEvent(scheduler_continue);
    assert(WaitForSingleObject(signal_worker, 5000u) == WAIT_OBJECT_0);
    assert(WaitForSingleObject(close_worker, 5000u) == WAIT_OBJECT_0);
    assert(context.result);
    CloseHandle(signal_worker);
    CloseHandle(close_worker);
    CloseHandle(context.done);
}

typedef struct take_context {
    uintptr_t generation;
    bool result;
    ul_audio_metadata_snapshot snapshot;
} take_context;

static DWORD WINAPI take_thread(void *parameter)
{
    take_context *context = parameter;
    context->result = ul_audio_metadata_take_worker(
        context->generation, 0u, &context->snapshot);
    return 0u;
}

static void test_take_serializes_close_and_reopen(void)
{
    take_context taking = {14u, false, {0}};
    close_context closing = {0};
    ul_audio_metadata_snapshot snapshot;
    HANDLE take_worker, close_worker;
    reset_fixture();
    source_count = 1u;
    make_source(0u, 1u);
    assert(ul_audio_metadata_open_frontend(14u, 0u, 1u, schedule_refresh));
    InterlockedExchange(&pause_take, 1);
    take_worker = CreateThread(NULL, 0u, take_thread, &taking, 0u, NULL);
    assert(take_worker != NULL);
    assert(WaitForSingleObject(take_locked, 5000u) == WAIT_OBJECT_0);
    closing.done = CreateEventW(NULL, TRUE, FALSE, NULL);
    closing.generation = 14u;
    assert(closing.done != NULL);
    close_worker = CreateThread(NULL, 0u, close_thread, &closing, 0u, NULL);
    assert(close_worker != NULL);
    assert(WaitForSingleObject(closing.done, 20u) == WAIT_TIMEOUT);
    SetEvent(take_continue);
    assert(WaitForSingleObject(take_worker, 5000u) == WAIT_OBJECT_0);
    assert(WaitForSingleObject(close_worker, 5000u) == WAIT_OBJECT_0);
    assert(taking.result && taking.snapshot.token == 1u && closing.result);
    InterlockedExchange(&pause_take, 0);
    assert(ul_audio_metadata_open_frontend(15u, 0u, 1u, schedule_refresh));
    assert(!ul_audio_metadata_take_worker(14u, 0u, &snapshot));
    assert(ul_audio_metadata_take_worker(15u, 0u, &snapshot));
    assert(snapshot.token == 1u);
    assert(ul_audio_metadata_close_frontend(15u, false));
    CloseHandle(take_worker);
    CloseHandle(close_worker);
    CloseHandle(closing.done);
}

int main(void)
{
    callback_entered = CreateEventW(NULL, TRUE, FALSE, NULL);
    callback_continue = CreateEventW(NULL, TRUE, FALSE, NULL);
    take_locked = CreateEventW(NULL, TRUE, FALSE, NULL);
    take_continue = CreateEventW(NULL, TRUE, FALSE, NULL);
    scheduler_entered = CreateEventW(NULL, TRUE, FALSE, NULL);
    scheduler_continue = CreateEventW(NULL, TRUE, FALSE, NULL);
    before_publish = CreateEventW(NULL, TRUE, FALSE, NULL);
    publish_continue = CreateEventW(NULL, TRUE, FALSE, NULL);
    assert(callback_entered != NULL && callback_continue != NULL &&
           take_locked != NULL && take_continue != NULL &&
           scheduler_entered != NULL && scheduler_continue != NULL &&
           before_publish != NULL && publish_continue != NULL);
    test_initial_snapshot_stabilizes();
    test_initial_change_remove_and_close();
    test_visible_bounds_and_text_failures();
    test_scheduler_failure_is_terminal();
    test_worker_request_and_frontend_failure();
    test_close_waits_for_inflight_callback();
    test_close_waits_for_nonblocking_scheduler();
    test_take_serializes_close_and_reopen();
    test_retire_blocks_inflight_republish();
    test_abandon_makes_callbacks_inert();
    CloseHandle(callback_entered);
    CloseHandle(callback_continue);
    CloseHandle(take_locked);
    CloseHandle(take_continue);
    CloseHandle(scheduler_entered);
    CloseHandle(scheduler_continue);
    CloseHandle(before_publish);
    CloseHandle(publish_continue);
    puts("native OBS metadata observation and lifecycle passed");
    return 0;
}
