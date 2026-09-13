// SPDX-License-Identifier: GPL-2.0-or-later
#include "audio_metadata.h"

#include <obs-module.h>
#ifndef UL_AUDIO_METADATA_TIME_NS
#include <sys/stat.h>
#include <util/platform.h>
#define UL_AUDIO_METADATA_TIME_NS() os_gettime_ns()
#endif

#include <windows.h>

#include <stdatomic.h>
#include <string.h>

#ifndef UL_AUDIO_METADATA_CLOSE_TIMEOUT_MS
#define UL_AUDIO_METADATA_CLOSE_TIMEOUT_MS 1000u
#endif

#ifndef UL_AUDIO_METADATA_STABLE_ATTEMPTS
#define UL_AUDIO_METADATA_STABLE_ATTEMPTS 8u
#endif

#ifndef UL_AUDIO_METADATA_CALLBACK_ENTERED
#define UL_AUDIO_METADATA_CALLBACK_ENTERED() ((void)0)
#endif

#ifndef UL_AUDIO_METADATA_TAKE_LOCKED
#define UL_AUDIO_METADATA_TAKE_LOCKED() ((void)0)
#endif
#ifndef UL_AUDIO_METADATA_BEFORE_PUBLISH
#define UL_AUDIO_METADATA_BEFORE_PUBLISH() ((void)0)
#endif

typedef struct watched_source {
    obs_source_t *source;
} watched_source;

typedef struct metadata_state {
    SRWLOCK lock;
    atomic_bool active;
    atomic_bool failed;
    atomic_bool dirty;
    atomic_bool queued;
    atomic_bool poisoned;
    atomic_uint_fast64_t readers;
    atomic_uint_fast64_t token;
    atomic_uintptr_t generation;
    uint8_t primary_bus;
    uint8_t bus_mask;
    ul_audio_metadata_schedule schedule;
    signal_handler_t *core_handler;
    watched_source watched[UL_AUDIO_METADATA_MAX_WATCHED_SOURCES];
    size_t watched_count;
    ul_audio_metadata_snapshot latest;
} metadata_state;

typedef struct snapshot_build {
    ul_audio_metadata_snapshot snapshot;
    watched_source watched[UL_AUDIO_METADATA_MAX_WATCHED_SOURCES];
    bool newly_connected[UL_AUDIO_METADATA_MAX_WATCHED_SOURCES];
    size_t watched_count;
    bool failed;
} snapshot_build;

static metadata_state metadata = {
    SRWLOCK_INIT,
    ATOMIC_VAR_INIT(false), ATOMIC_VAR_INIT(false),
    ATOMIC_VAR_INIT(false), ATOMIC_VAR_INIT(false),
    ATOMIC_VAR_INIT(false), ATOMIC_VAR_INIT(0u),
    ATOMIC_VAR_INIT(0u), ATOMIC_VAR_INIT(0u),
    0u, 0u, NULL, NULL, {{0}}, 0u, {0},
};

static void metadata_signal(void *data, calldata_t *parameters);
static void core_signal(void *data, calldata_t *parameters);

static bool valid_mask(uint8_t primary_bus, uint8_t bus_mask)
{
    return primary_bus < UL_AUDIO_METADATA_MIXES && bus_mask != 0u &&
           (bus_mask & ~0x3fu) == 0u &&
           (bus_mask & (uint8_t)(1u << primary_bus)) != 0u;
}

static size_t bounded_c_string(const char *text, size_t maximum)
{
    size_t length = 0u;
    if (text == NULL)
        return maximum + 1u;
    while (length <= maximum && text[length] != '\0')
        length++;
    return length;
}

static bool parse_uuid(const char *text, uint8_t out[16])
{
    static const uint8_t positions[4] = {8u, 13u, 18u, 23u};
    size_t input = 0u, output = 0u, dash = 0u;
    if (text == NULL || bounded_c_string(text, 36u) != 36u)
        return false;
    while (input < 36u) {
        unsigned high, low;
        if (dash < 4u && input == positions[dash]) {
            if (text[input++] != '-')
                return false;
            dash++;
            continue;
        }
#define HEX_VALUE(ch, value) \
    (((ch) >= '0' && (ch) <= '9') ? ((value) = (unsigned)((ch) - '0'), true) : \
     ((ch) >= 'a' && (ch) <= 'f') ? ((value) = (unsigned)((ch) - 'a' + 10), true) : \
     ((ch) >= 'A' && (ch) <= 'F') ? ((value) = (unsigned)((ch) - 'A' + 10), true) : false)
        if (input + 1u >= 36u || output >= 16u ||
            !HEX_VALUE(text[input], high) ||
            !HEX_VALUE(text[input + 1u], low))
            return false;
#undef HEX_VALUE
        out[output++] = (uint8_t)((high << 4) | low);
        input += 2u;
    }
    return output == 16u && dash == 4u;
}

static bool valid_text(const uint8_t *text, size_t length, size_t maximum)
{
    size_t index = 0u;
    bool has_visible = false;
    if (text == NULL || length == 0u || length > maximum)
        return false;
    while (index < length) {
        uint32_t codepoint;
        uint8_t first = text[index++];
        if (first < 0x80u) {
            codepoint = first;
        } else if (first >= 0xc2u && first <= 0xdfu) {
            if (index >= length || (text[index] & 0xc0u) != 0x80u)
                return false;
            codepoint = ((uint32_t)(first & 0x1fu) << 6) |
                        (uint32_t)(text[index++] & 0x3fu);
        } else if (first >= 0xe0u && first <= 0xefu) {
            uint8_t second;
            if (length - index < 2u)
                return false;
            second = text[index];
            if ((second & 0xc0u) != 0x80u ||
                (text[index + 1u] & 0xc0u) != 0x80u ||
                (first == 0xe0u && second < 0xa0u) ||
                (first == 0xedu && second >= 0xa0u))
                return false;
            codepoint = ((uint32_t)(first & 0x0fu) << 12) |
                        ((uint32_t)(second & 0x3fu) << 6) |
                        (uint32_t)(text[index + 1u] & 0x3fu);
            index += 2u;
        } else if (first >= 0xf0u && first <= 0xf4u) {
            uint8_t second;
            if (length - index < 3u)
                return false;
            second = text[index];
            if ((second & 0xc0u) != 0x80u ||
                (text[index + 1u] & 0xc0u) != 0x80u ||
                (text[index + 2u] & 0xc0u) != 0x80u ||
                (first == 0xf0u && second < 0x90u) ||
                (first == 0xf4u && second > 0x8fu))
                return false;
            codepoint = ((uint32_t)(first & 0x07u) << 18) |
                        ((uint32_t)(second & 0x3fu) << 12) |
                        ((uint32_t)(text[index + 1u] & 0x3fu) << 6) |
                        (uint32_t)(text[index + 2u] & 0x3fu);
            index += 3u;
        } else {
            return false;
        }
        if (codepoint <= 0x1fu ||
            (codepoint >= 0x7fu && codepoint <= 0x9fu) ||
            codepoint == 0x061cu || codepoint == 0x200bu ||
            codepoint == 0x200eu || codepoint == 0x200fu ||
            (codepoint >= 0x2028u && codepoint <= 0x202eu) ||
            (codepoint >= 0x2066u && codepoint <= 0x2069u) ||
            codepoint == 0xfeffu)
            return false;
        if (codepoint != 0x20u && codepoint != 0x00a0u &&
            codepoint != 0x1680u &&
            !(codepoint >= 0x2000u && codepoint <= 0x200au) &&
            codepoint != 0x202fu && codepoint != 0x205fu &&
            codepoint != 0x3000u && codepoint != 0x200cu &&
            codepoint != 0x200du)
            has_visible = true;
    }
    return has_visible;
}

static bool was_watched(obs_source_t *source)
{
    size_t index;
    for (index = 0u; index < metadata.watched_count; ++index)
        if (metadata.watched[index].source == source)
            return true;
    return false;
}

static void disconnect_source(obs_source_t *source)
{
    signal_handler_t *handler = obs_source_get_signal_handler(source);
    if (handler != NULL) {
        signal_handler_disconnect(handler, "audio_mixers", metadata_signal,
                                  &metadata);
        signal_handler_disconnect(handler, "rename", metadata_signal,
                                  &metadata);
        signal_handler_disconnect(handler, "remove", metadata_signal,
                                  &metadata);
    }
}

static bool connect_source(obs_source_t *source)
{
    signal_handler_t *handler = obs_source_get_signal_handler(source);
    if (handler == NULL)
        return false;
    signal_handler_connect(handler, "audio_mixers", metadata_signal,
                           &metadata);
    signal_handler_connect(handler, "rename", metadata_signal, &metadata);
    signal_handler_connect(handler, "remove", metadata_signal, &metadata);
    return true;
}

static void sort_sources(ul_audio_metadata_snapshot *snapshot)
{
    size_t index;
    for (index = 1u; index < snapshot->source_count; ++index) {
        ul_audio_metadata_source value = snapshot->sources[index];
        size_t position = index;
        while (position != 0u &&
               memcmp(snapshot->sources[position - 1u].source_id,
                      value.source_id, 16u) > 0) {
            snapshot->sources[position] = snapshot->sources[position - 1u];
            position--;
        }
        snapshot->sources[position] = value;
    }
}

static bool enumerate_source(void *data, obs_source_t *source)
{
    snapshot_build *build = data;
    ul_audio_metadata_source *record;
    obs_source_t *retained;
    const char *uuid, *name;
    uint32_t mixers;
    size_t length;
    bool old;
    if (build->failed || source == NULL || obs_source_removed(source) ||
        obs_source_get_type(source) != OBS_SOURCE_TYPE_INPUT ||
        (obs_source_get_output_flags(source) & OBS_SOURCE_AUDIO) == 0u)
        return !build->failed;
    if (build->watched_count == UL_AUDIO_METADATA_MAX_WATCHED_SOURCES) {
        build->failed = true;
        return false;
    }
    retained = obs_source_get_ref(source);
    if (retained == NULL) {
        build->failed = true;
        return false;
    }
    old = was_watched(source);
    build->watched[build->watched_count].source = retained;
    build->newly_connected[build->watched_count] = !old;
    build->watched_count++;
    if (!old && !connect_source(retained)) {
        build->failed = true;
        return false;
    }
    mixers = obs_source_get_audio_mixers(retained) & build->snapshot.bus_mask;
    if (mixers == 0u)
        return true;
    if (build->snapshot.source_count == UL_AUDIO_METADATA_MAX_SOURCES) {
        build->failed = true;
        return false;
    }
    record = &build->snapshot.sources[build->snapshot.source_count];
    /* The pinned obs_enum_sources implementation holds sources_mutex through
     * this callback; public rename/UUID reset takes the same mutex. Keep both
     * getters and their complete bounded copies inside this callback. */
    uuid = obs_source_get_uuid(retained);
    name = obs_source_get_name(retained);
    if (!parse_uuid(uuid, record->source_id) || name == NULL) {
        build->failed = true;
        return false;
    }
    length = bounded_c_string(name, UL_AUDIO_METADATA_MAX_SOURCE_NAME_BYTES);
    if (!valid_text((const uint8_t *)name, length,
                    UL_AUDIO_METADATA_MAX_SOURCE_NAME_BYTES)) {
        build->failed = true;
        return false;
    }
    record->selected_mask = (uint8_t)mixers;
    record->name_length = (uint16_t)length;
    memcpy(record->name, name, length);
    build->snapshot.source_count++;
    return true;
}

static void cleanup_build(snapshot_build *build, bool keep_connections)
{
    size_t index;
    for (index = 0u; index < build->watched_count; ++index) {
        if (!keep_connections && build->newly_connected[index])
            disconnect_source(build->watched[index].source);
        obs_source_release(build->watched[index].source);
    }
    build->watched_count = 0u;
}

static void adopt_watchers(snapshot_build *build)
{
    size_t index;
    for (index = 0u; index < metadata.watched_count; ++index) {
        size_t candidate;
        bool retained = false;
        for (candidate = 0u; candidate < build->watched_count; ++candidate)
            if (metadata.watched[index].source ==
                build->watched[candidate].source) {
                retained = true;
                break;
            }
        if (!retained)
            disconnect_source(metadata.watched[index].source);
        obs_source_release(metadata.watched[index].source);
    }
    metadata.watched_count = build->watched_count;
    memcpy(metadata.watched, build->watched,
           build->watched_count * sizeof(build->watched[0]));
    build->watched_count = 0u;
}

static bool same_payload(const ul_audio_metadata_snapshot *left,
                         const ul_audio_metadata_snapshot *right)
{
    ul_audio_metadata_snapshot first = *left, second = *right;
    first.token = second.token = 0u;
    first.observed_at_ns = second.observed_at_ns = 0u;
    return memcmp(&first, &second, sizeof(first)) == 0;
}

static bool build_and_publish(bool initial, uintptr_t expected_generation)
{
    snapshot_build build = {0};
    uint8_t bus;
    size_t index;
    uint64_t next_token, observed;
    build.snapshot.primary_bus = metadata.primary_bus;
    build.snapshot.bus_mask = metadata.bus_mask;
    for (bus = 0u; bus < UL_AUDIO_METADATA_MIXES; ++bus) {
        ul_audio_metadata_bus *label;
        if ((metadata.bus_mask & (uint8_t)(1u << bus)) == 0u)
            continue;
        label = &build.snapshot.buses[build.snapshot.bus_count++];
        label->bus = bus;
        label->label_length = 5u;
        memcpy(label->label, "Mix 1", 5u);
        label->label[4] = (uint8_t)('1' + bus);
    }
    obs_enum_sources(enumerate_source, &build);
    if (build.failed)
        goto failure;
    sort_sources(&build.snapshot);
    for (index = 1u; index < build.snapshot.source_count; ++index)
        if (memcmp(build.snapshot.sources[index - 1u].source_id,
                   build.snapshot.sources[index].source_id, 16u) == 0)
            goto failure;
    adopt_watchers(&build);
    UL_AUDIO_METADATA_BEFORE_PUBLISH();
    AcquireSRWLockExclusive(&metadata.lock);
    if (!atomic_load_explicit(&metadata.active, memory_order_acquire) ||
        atomic_load_explicit(&metadata.failed, memory_order_acquire) ||
        atomic_load_explicit(&metadata.generation, memory_order_acquire) !=
            expected_generation) {
        ReleaseSRWLockExclusive(&metadata.lock);
        goto failure;
    }
    if (!initial && same_payload(&build.snapshot, &metadata.latest)) {
        ReleaseSRWLockExclusive(&metadata.lock);
        return true;
    }
    next_token = atomic_load_explicit(&metadata.token, memory_order_relaxed);
    if (next_token == UINT64_MAX) {
        ReleaseSRWLockExclusive(&metadata.lock);
        goto failure;
    }
    observed = UL_AUDIO_METADATA_TIME_NS();
    if (!initial && observed <= metadata.latest.observed_at_ns) {
        if (metadata.latest.observed_at_ns == UINT64_MAX) {
            ReleaseSRWLockExclusive(&metadata.lock);
            goto failure;
        }
        observed = metadata.latest.observed_at_ns + 1u;
    }
    build.snapshot.token = next_token + 1u;
    build.snapshot.observed_at_ns = observed;
    metadata.latest = build.snapshot;
    atomic_store_explicit(&metadata.token, next_token + 1u,
                          memory_order_release);
    ReleaseSRWLockExclusive(&metadata.lock);
    return true;

failure:
    cleanup_build(&build, false);
    return false;
}

static void schedule_if_needed(void)
{
    bool expected = false;
    if (!atomic_load_explicit(&metadata.active, memory_order_acquire) ||
        atomic_load_explicit(&metadata.failed, memory_order_acquire) ||
        !atomic_load_explicit(&metadata.dirty, memory_order_acquire) ||
        !atomic_compare_exchange_strong_explicit(
            &metadata.queued, &expected, true,
            memory_order_acq_rel, memory_order_acquire))
        return;
    if (metadata.schedule == NULL ||
        !metadata.schedule(atomic_load_explicit(&metadata.generation,
                                                memory_order_acquire))) {
        atomic_store_explicit(&metadata.failed, true, memory_order_release);
        atomic_store_explicit(&metadata.queued, false, memory_order_release);
    }
}

static void mark_dirty(void)
{
    atomic_store_explicit(&metadata.dirty, true, memory_order_release);
    schedule_if_needed();
}

static void metadata_signal(void *data, calldata_t *parameters)
{
    (void)parameters;
    if (data != &metadata)
        return;
    atomic_fetch_add_explicit(&metadata.readers, 1u, memory_order_seq_cst);
    UL_AUDIO_METADATA_CALLBACK_ENTERED();
    if (atomic_load_explicit(&metadata.active, memory_order_acquire))
        mark_dirty();
    atomic_fetch_sub_explicit(&metadata.readers, 1u, memory_order_seq_cst);
}

static void core_signal(void *data, calldata_t *parameters)
{
    metadata_signal(data, parameters);
}

static void disconnect_all(void)
{
    size_t index;
    if (metadata.core_handler != NULL) {
        signal_handler_disconnect(metadata.core_handler, "source_create",
                                  core_signal, &metadata);
        signal_handler_disconnect(metadata.core_handler, "source_remove",
                                  core_signal, &metadata);
        signal_handler_disconnect(metadata.core_handler, "source_destroy",
                                  core_signal, &metadata);
        signal_handler_disconnect(metadata.core_handler, "source_rename",
                                  core_signal, &metadata);
    }
    for (index = 0u; index < metadata.watched_count; ++index) {
        disconnect_source(metadata.watched[index].source);
        obs_source_release(metadata.watched[index].source);
    }
    metadata.watched_count = 0u;
    metadata.core_handler = NULL;
}

bool ul_audio_metadata_open_frontend(uintptr_t generation,
                                     uint8_t primary_bus, uint8_t bus_mask,
                                     ul_audio_metadata_schedule schedule)
{
    unsigned attempt;
    bool stable = false;
    if (generation == 0u || schedule == NULL ||
        !valid_mask(primary_bus, bus_mask) ||
        atomic_load_explicit(&metadata.active, memory_order_acquire) ||
        atomic_load_explicit(&metadata.poisoned, memory_order_acquire) ||
        atomic_load_explicit(&metadata.readers, memory_order_acquire) != 0u)
        return false;
    metadata.primary_bus = primary_bus;
    metadata.bus_mask = bus_mask;
    metadata.schedule = schedule;
    metadata.core_handler = obs_get_signal_handler();
    if (metadata.core_handler == NULL)
        return false;
    metadata.watched_count = 0u;
    atomic_store_explicit(&metadata.failed, false, memory_order_release);
    atomic_store_explicit(&metadata.dirty, false, memory_order_release);
    atomic_store_explicit(&metadata.queued, false, memory_order_release);
    AcquireSRWLockExclusive(&metadata.lock);
    memset(&metadata.latest, 0, sizeof(metadata.latest));
    atomic_store_explicit(&metadata.token, 0u, memory_order_release);
    atomic_store_explicit(&metadata.generation, generation,
                          memory_order_release);
    atomic_store_explicit(&metadata.active, true, memory_order_release);
    ReleaseSRWLockExclusive(&metadata.lock);
    signal_handler_connect(metadata.core_handler, "source_create", core_signal,
                           &metadata);
    signal_handler_connect(metadata.core_handler, "source_remove", core_signal,
                           &metadata);
    signal_handler_connect(metadata.core_handler, "source_destroy", core_signal,
                           &metadata);
    signal_handler_connect(metadata.core_handler, "source_rename", core_signal,
                           &metadata);
    for (attempt = 0u; attempt < UL_AUDIO_METADATA_STABLE_ATTEMPTS; ++attempt) {
        atomic_store_explicit(&metadata.dirty, false, memory_order_release);
        if (!build_and_publish(attempt == 0u, generation))
            break;
        if (atomic_load_explicit(&metadata.failed, memory_order_acquire))
            break;
        if (!atomic_load_explicit(&metadata.dirty, memory_order_acquire)) {
            stable = true;
            break;
        }
    }
    if (!stable ||
        atomic_load_explicit(&metadata.failed, memory_order_acquire)) {
        atomic_store_explicit(&metadata.failed, true, memory_order_release);
        (void)ul_audio_metadata_close_frontend(generation, false);
        return false;
    }
    atomic_store_explicit(&metadata.queued, false, memory_order_release);
    schedule_if_needed();
    return true;
}

bool ul_audio_metadata_refresh_frontend(uintptr_t generation)
{
    bool success;
    if (!atomic_load_explicit(&metadata.active, memory_order_acquire) ||
        generation == 0u || generation != atomic_load_explicit(
            &metadata.generation, memory_order_acquire) ||
        atomic_load_explicit(&metadata.failed, memory_order_acquire))
        return false;
    atomic_store_explicit(&metadata.dirty, false, memory_order_release);
    success = build_and_publish(false, generation);
    if (atomic_load_explicit(&metadata.failed, memory_order_acquire))
        success = false;
    if (!success)
        atomic_store_explicit(&metadata.failed, true, memory_order_release);
    atomic_store_explicit(&metadata.queued, false, memory_order_release);
    if (success)
        schedule_if_needed();
    return success;
}

bool ul_audio_metadata_close_frontend(uintptr_t generation, bool all)
{
    ULONGLONG started;
    uintptr_t current;
    AcquireSRWLockExclusive(&metadata.lock);
    current = atomic_load_explicit(&metadata.generation, memory_order_acquire);
    if (!atomic_load_explicit(&metadata.active, memory_order_acquire)) {
        ReleaseSRWLockExclusive(&metadata.lock);
        return generation == current || (all && current != 0u);
    }
    if (!all && (generation == 0u || generation != current)) {
        ReleaseSRWLockExclusive(&metadata.lock);
        return false;
    }
    atomic_store_explicit(&metadata.active, false, memory_order_release);
    ReleaseSRWLockExclusive(&metadata.lock);
    disconnect_all();
    started = GetTickCount64();
    while (atomic_load_explicit(&metadata.readers, memory_order_acquire) != 0u) {
        if (GetTickCount64() - started >= UL_AUDIO_METADATA_CLOSE_TIMEOUT_MS) {
            atomic_store_explicit(&metadata.poisoned, true,
                                  memory_order_release);
            return false;
        }
        SwitchToThread();
    }
    atomic_store_explicit(&metadata.queued, false, memory_order_release);
    atomic_store_explicit(&metadata.dirty, false, memory_order_release);
    return true;
}

void ul_audio_metadata_fail_frontend(uintptr_t generation)
{
    AcquireSRWLockShared(&metadata.lock);
    if (generation != 0u &&
        atomic_load_explicit(&metadata.active, memory_order_acquire) &&
        generation == atomic_load_explicit(&metadata.generation,
                                            memory_order_acquire))
        atomic_store_explicit(&metadata.failed, true, memory_order_release);
    ReleaseSRWLockShared(&metadata.lock);
}

void ul_audio_metadata_abandon_after_shutdown(void)
{
    AcquireSRWLockExclusive(&metadata.lock);
    atomic_store_explicit(&metadata.active, false, memory_order_release);
    atomic_store_explicit(&metadata.failed, true, memory_order_release);
    atomic_store_explicit(&metadata.poisoned, true, memory_order_release);
    atomic_store_explicit(&metadata.queued, false, memory_order_release);
    atomic_store_explicit(&metadata.dirty, false, memory_order_release);
    ReleaseSRWLockExclusive(&metadata.lock);
}

bool ul_audio_metadata_take_worker(uintptr_t generation, uint64_t after_token,
                                   ul_audio_metadata_snapshot *out)
{
    if (generation == 0u || out == NULL)
        return false;
    AcquireSRWLockShared(&metadata.lock);
    UL_AUDIO_METADATA_TAKE_LOCKED();
    if (generation != atomic_load_explicit(&metadata.generation,
                                            memory_order_acquire) ||
        atomic_load_explicit(&metadata.failed, memory_order_acquire) ||
        metadata.latest.token <= after_token) {
        ReleaseSRWLockShared(&metadata.lock);
        return false;
    }
    *out = metadata.latest;
    ReleaseSRWLockShared(&metadata.lock);
    return true;
}

bool ul_audio_metadata_failed(uintptr_t generation)
{
    return generation != 0u && generation == atomic_load_explicit(
               &metadata.generation, memory_order_acquire) &&
           atomic_load_explicit(&metadata.failed, memory_order_acquire);
}

void ul_audio_metadata_retire_worker(uintptr_t generation)
{
    if (generation == 0u)
        return;
    AcquireSRWLockExclusive(&metadata.lock);
    if (generation == atomic_load_explicit(&metadata.generation,
                                            memory_order_acquire)) {
        atomic_store_explicit(&metadata.failed, true, memory_order_release);
        atomic_store_explicit(&metadata.queued, false, memory_order_release);
        atomic_store_explicit(&metadata.dirty, false, memory_order_release);
        atomic_store_explicit(&metadata.token, 0u, memory_order_release);
        SecureZeroMemory(&metadata.latest, sizeof(metadata.latest));
    }
    ReleaseSRWLockExclusive(&metadata.lock);
}

bool ul_audio_metadata_request_worker(uintptr_t generation)
{
    bool accepted = false;
    AcquireSRWLockShared(&metadata.lock);
    if (generation != 0u &&
        atomic_load_explicit(&metadata.active, memory_order_acquire) &&
        generation == atomic_load_explicit(&metadata.generation,
                                            memory_order_acquire) &&
        !atomic_load_explicit(&metadata.failed, memory_order_acquire)) {
        mark_dirty();
        accepted = !atomic_load_explicit(&metadata.failed,
                                         memory_order_acquire);
    }
    ReleaseSRWLockShared(&metadata.lock);
    return accepted;
}
