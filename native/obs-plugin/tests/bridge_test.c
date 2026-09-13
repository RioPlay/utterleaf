// SPDX-License-Identifier: GPL-2.0-or-later
/* Public wrapper substitutions: no OBS startup, store, UI or audio. */
#include <obs-module.h>
#include <obs-frontend-api.h>
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include <obs-websocket-api.h>
#include "../src/plugin_state.h"
#include "../src/pairing_ui.h"
#include "../src/vendor_dispatch.h"

static unsigned start_calls, register_calls, unregister_calls, tools_calls, event_calls;
static bool has_window, allow_start, allow_issue, allow_prepare, allow_unregister, enabled;
static bool exiting;
static unsigned api_version;
static char order[32];
static size_t order_size;
static ul_plugin_snapshot snapshot;
static ul_arm_scheduler arm_scheduler;
static obs_task_t queued_task;
static void *queued_parameter;
static uintptr_t checked_generation;
static bool allow_scheduler, current_active, current_output_active, has_output, checked_idle;
static unsigned queue_calls, idle_checks, output_releases, stream_events;
static ul_stream_event last_stream_event;
static obs_output_t *current_output = (obs_output_t *)(uintptr_t)3;
static bool after_exit;

static void record(char value) { assert(order_size + 1 < sizeof(order)); order[order_size++] = value; order[order_size] = 0; }
static uint32_t test_version(void) { return LIBOBS_API_VER; }
static obs_module_t *test_module(void) { return (obs_module_t *)(uintptr_t)1; }
static void *test_window(void) { return has_window ? (void *)(uintptr_t)1 : NULL; }
static unsigned test_api(void) { return api_version; }
static void test_event(obs_frontend_event_cb callback, void *data)
{ assert(callback != NULL && data == NULL); ++event_calls; }
static void test_menu(const char *name, obs_frontend_cb callback, void *data)
{ assert(strcmp(name, "Utterleaf pairing...") == 0 && callback != NULL && data == NULL); ++tools_calls; }
static obs_websocket_vendor test_vendor(const char *name)
{ assert(strcmp(name, "Utterleaf") == 0); ++register_calls; return (void *)(uintptr_t)2; }
static bool test_register(obs_websocket_vendor handle, const char *name,
                          obs_websocket_request_callback_function callback, void *data)
{
    assert(handle == (void *)(uintptr_t)2 && data == NULL && !enabled);
    ++register_calls;
    if (strcmp(name, "IssueAuthorization") == 0) { assert(callback == ul_vendor_issue); return allow_issue; }
    assert(strcmp(name, "PrepareSession") == 0 && callback == ul_vendor_prepare);
    return allow_prepare;
}
static bool test_unregister(obs_websocket_vendor handle, const char *name)
{
    assert(handle == (void *)(uintptr_t)2 && !enabled);
    if (exiting) assert(snapshot.status == UL_PLUGIN_CLOSED);
    ++unregister_calls;
    record(strcmp(name, "PrepareSession") == 0 ? 'P' : 'I');
    return allow_unregister;
}
static void test_log(int level, const char *format, ...) { (void)level; (void)format; }
bool ul_plugin_start(void) { ++start_calls; return allow_start; }
bool ul_plugin_set_arm_scheduler(ul_arm_scheduler scheduler)
{ arm_scheduler = scheduler; return allow_scheduler; }
void ul_plugin_arm_checked(uintptr_t generation, bool idle)
{ assert(!exiting); checked_generation = generation; checked_idle = idle; ++idle_checks; }
void ul_plugin_stream_event(ul_stream_event event)
{ assert(!exiting); ++stream_events; last_stream_event = event; }
static bool test_active(void) { assert(!exiting); return current_active; }
static obs_output_t *test_output(void)
{ assert(!after_exit); return has_output ? current_output : NULL; }
static bool test_output_active(const obs_output_t *output)
{ assert(!after_exit && output == current_output); return current_output_active; }
static void test_release(obs_output_t *output)
{ assert(!after_exit && output != NULL); ++output_releases; }
static void test_queue(enum obs_task_type type, obs_task_t task, void *parameter, bool wait)
{
    assert(!exiting && type == OBS_TASK_UI && !wait && task != NULL);
    queued_task = task; queued_parameter = parameter; ++queue_calls;
}
ul_plugin_snapshot ul_plugin_get_status(void) { return snapshot; }
void ul_plugin_stop_accepting(void) { assert(!enabled); snapshot.status = UL_PLUGIN_CLOSED; record('S'); }
void ul_plugin_close(void) { assert(!enabled); snapshot.status = UL_PLUGIN_CLOSED; record('C'); }
void ul_vendor_set_enabled(bool value) { enabled = value; record(value ? 'E' : 'D'); }
void ul_pairing_ui_show(HWND owner) { assert(owner != NULL); }
void ul_vendor_issue(obs_data_t *request, obs_data_t *response, void *data)
{ (void)request; (void)response; (void)data; }
void ul_vendor_prepare(obs_data_t *request, obs_data_t *response, void *data)
{ (void)request; (void)response; (void)data; }

#undef OBS_DECLARE_MODULE
#define OBS_DECLARE_MODULE()
#define obs_get_version test_version
#define obs_current_module test_module
#define obs_frontend_get_main_window_handle test_window
#define obs_frontend_add_event_callback test_event
#define obs_frontend_add_tools_menu_item test_menu
#define obs_frontend_streaming_active test_active
#define obs_frontend_get_streaming_output test_output
#define obs_output_active test_output_active
#define obs_output_release test_release
#define obs_queue_task test_queue
#define obs_websocket_get_api_version test_api
#define obs_websocket_register_vendor test_vendor
#define obs_websocket_vendor_register_request test_register
#define obs_websocket_vendor_unregister_request test_unregister
#define blog test_log
#include "../src/bridge.c"

static void reset(void)
{
    start_calls = register_calls = unregister_calls = tools_calls = event_calls = 0;
    has_window = allow_start = allow_issue = allow_prepare = allow_unregister = true;
    enabled = exiting = false;
    after_exit = false;
    api_version = OBS_WEBSOCKET_API_VERSION;
    snapshot = (ul_plugin_snapshot){UL_PLUGIN_UNPAIRED, UL_PAIRING_MISSING, true, false};
    vendor = NULL;
    issue_registered = prepare_registered = false;
    order_size = 0;
    order[0] = 0;
    frontend_open = false; queued_arm = 0; stream_busy = false;
    arm_scheduler = NULL; queued_task = NULL; queued_parameter = NULL;
    checked_generation = 0;
    allow_scheduler = has_output = true;
    current_active = current_output_active = checked_idle = false;
    queue_calls = idle_checks = output_releases = stream_events = 0;
    current_output = (obs_output_t *)(uintptr_t)3;
}

int main(void)
{
    reset(); has_window = false;
    assert(!obs_module_load() && start_calls == 0 && tools_calls == 0 && event_calls == 0);
    reset(); allow_start = false;
    assert(!obs_module_load() && start_calls == 1 && tools_calls == 0 && event_calls == 0);
    reset();
    assert(obs_module_load() && start_calls == 1 && tools_calls == 1 && event_calls == 1);
    obs_module_post_load();
    assert(enabled && register_calls == 3 && issue_registered && prepare_registered);
    obs_module_post_load(); assert(register_calls == 3);
    order_size = 0; order[0] = 0; exiting = true;
    frontend_event(OBS_FRONTEND_EVENT_EXIT, NULL);
    assert(strcmp(order, "DSPIC") == 0 && unregister_calls == 2 && !enabled);

    reset(); allow_prepare = allow_unregister = false;
    obs_module_post_load();
    assert(!enabled && issue_registered && !prepare_registered && unregister_calls == 1);
    order_size = 0; order[0] = 0; exiting = true;
    frontend_event(OBS_FRONTEND_EVENT_EXIT, NULL);
    assert(strcmp(order, "DSIC") == 0 && unregister_calls == 2 && !enabled);

    reset(); allow_prepare = false;
    obs_module_post_load();
    assert(!enabled && !issue_registered && !prepare_registered && unregister_calls == 1);
    reset(); allow_issue = false;
    obs_module_post_load(); assert(!enabled && register_calls == 2 && unregister_calls == 0);
    reset(); api_version = 0;
    obs_module_post_load(); assert(!enabled && register_calls == 0);
    reset(); snapshot.owns_store = false;
    obs_module_post_load(); assert(!enabled && register_calls == 0);

    reset(); obs_module_post_load();
    order_size = 0; order[0] = 0;
    obs_module_unload();
    assert(strcmp(order, "DC") == 0 && !enabled && unregister_calls == 0);
    assert(snapshot.status == UL_PLUGIN_CLOSED && event_calls == 0 && tools_calls == 0);
    reset(); allow_scheduler = false;
    assert(!obs_module_load() && tools_calls == 0 && event_calls == 0);
    reset(); assert(obs_module_load() && arm_scheduler != NULL);
    assert(!arm_scheduler(0));
    assert(arm_scheduler(7) && queue_calls == 1);
    assert(!arm_scheduler(8) && queue_calls == 1); /* One outstanding slot. */
    queued_task(queued_parameter);
    assert(checked_generation == 7 && checked_idle && output_releases == 1);
    queued_task(queued_parameter); assert(idle_checks == 1); /* Duplicate callback. */
    assert(arm_scheduler(8));
    check_arm_on_frontend((void *)(uintptr_t)7);
    assert(idle_checks == 1 && queued_arm == 8); /* Stale callback cannot consume new slot. */
    current_output_active = true;
    queued_task(queued_parameter);
    assert(!checked_idle && checked_generation == 8 && output_releases == 2);
    current_output_active = false; current_active = true;
    assert(arm_scheduler(9)); queued_task(queued_parameter);
    assert(!checked_idle && output_releases == 3);
    has_output = false; current_active = false;
    assert(arm_scheduler(10)); queued_task(queued_parameter);
    assert(checked_idle && output_releases == 3);
    has_output = true;
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTING, NULL);
    assert(stream_events == 1 && last_stream_event == UL_STREAM_STARTING);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTED, NULL);
    assert(stream_events == 2 && last_stream_event == UL_STREAM_STARTED);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STOPPING, NULL);
    assert(stream_events == 3 && last_stream_event == UL_STREAM_STOPPING);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STOPPED, NULL);
    assert(stream_events == 4 && last_stream_event == UL_STREAM_STOPPED);
    assert(arm_scheduler(11));
    exiting = true;
    frontend_event(OBS_FRONTEND_EVENT_EXIT, NULL);
    queued_task(queued_parameter); /* No OBS or retired runtime access after EXIT. */
    assert(!arm_scheduler(12) && idle_checks == 4);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTED, NULL);
    assert(stream_events == 4);
    reset(); assert(obs_module_load()); assert(arm_scheduler(13));
    exiting = true; obs_module_unload(); queued_task(queued_parameter);
    assert(idle_checks == 0 && !arm_scheduler(14));

    /* STARTING, STARTED and STOPPING remain busy even while both public active
     * queries are false. Only the completed STOPPED lifecycle proves idle. */
    reset(); assert(obs_module_load());
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTING, NULL);
    assert(stream_busy);
    assert(arm_scheduler(21)); queued_task(queued_parameter);
    assert(checked_generation == 21 && !checked_idle && idle_checks == 1);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTED, NULL);
    assert(arm_scheduler(22)); queued_task(queued_parameter);
    assert(checked_generation == 22 && !checked_idle && idle_checks == 2);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STOPPING, NULL);
    assert(arm_scheduler(23)); queued_task(queued_parameter);
    assert(checked_generation == 23 && !checked_idle && idle_checks == 3);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STOPPED, NULL);
    assert(arm_scheduler(24)); queued_task(queued_parameter);
    assert(checked_generation == 24 && checked_idle && idle_checks == 4);

    /* A synchronous start failure has no public frontend STOPPED event, so it
     * stays fail closed. An unavailable output and repeated STARTING are also
     * unknown/busy until OBS reports STOPPED. */
    reset(); assert(obs_module_load()); has_output = false;
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTING, NULL);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTING, NULL);
    assert(arm_scheduler(25)); queued_task(queued_parameter);
    assert(!checked_idle && stream_busy && output_releases == 0);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STOPPED, NULL);
    assert(arm_scheduler(26)); queued_task(queued_parameter);
    assert(checked_idle && !stream_busy && output_releases == 0);

    /* EXIT closes before a queued Arm callback; it performs no frontend/output
     * query after the final frontend callback returns. */
    reset(); assert(obs_module_load());
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTING, NULL);
    assert(arm_scheduler(27));
    exiting = true;
    frontend_event(OBS_FRONTEND_EVENT_EXIT, NULL);
    after_exit = true;
    queued_task(queued_parameter);
    assert(idle_checks == 0 && output_releases == 0 && !arm_scheduler(28));

    /* Unload is the native-only fallback if frontend EXIT was missed. */
    reset(); assert(obs_module_load());
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTING, NULL);
    assert(arm_scheduler(29));
    exiting = true; obs_module_unload();
    after_exit = true;
    queued_task(queued_parameter);
    assert(idle_checks == 0 && output_releases == 0 && !arm_scheduler(30));

    puts("bridge lifecycle, queued Arm and stream-busy gate tests passed");
    return 0;
}
