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
#include "../src/frontend_dispatch.h"

static unsigned start_calls, register_calls, unregister_calls, tools_calls, event_calls;
static bool has_window, allow_start, allow_status, allow_issue, allow_prepare, allow_unregister, enabled;
static bool exiting;
static unsigned api_version;
static char order[32];
static size_t order_size;
static ul_plugin_snapshot snapshot;
static ul_arm_scheduler arm_scheduler;
static ul_frontend_dispatch_callback queued_task;
static uintptr_t queued_parameter;
static unsigned queued_command;
static ul_arm_scheduler capture_scheduler, cleanup_scheduler;
static bool allow_dispatch, allow_post, allow_capture_schedulers;
static bool inspect_requested, allow_inspect, allow_connect, capture_available;
static unsigned inspect_calls, inspected_calls, connect_calls, attached_calls;
static unsigned capture_releases, stop_calls, disconnect_calls, abandon_calls;
static unsigned cleanup_completed_calls;
static uintptr_t capture_generation, disconnected_generation;
static bool inspected_ok, attached_ok, disconnected_all;
static ul_audio_capture *test_capture = (ul_audio_capture *)(uintptr_t)55;
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
    if (strcmp(name, "PrepareSession") == 0) { assert(callback == ul_vendor_prepare); return allow_prepare; }
    assert(strcmp(name, "GetStatus") == 0 && callback == ul_vendor_status);
    return allow_status;
}
static bool test_unregister(obs_websocket_vendor handle, const char *name)
{
    assert(handle == (void *)(uintptr_t)2 && !enabled);
    if (exiting) assert(snapshot.status == UL_PLUGIN_CLOSED);
    ++unregister_calls;
    record(strcmp(name, "PrepareSession") == 0 ? 'P' :
           strcmp(name, "IssueAuthorization") == 0 ? 'I' : 'G');
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
bool ul_frontend_dispatch_open(ul_frontend_dispatch_callback callback)
{ queued_task = callback; return allow_dispatch; }
bool ul_frontend_dispatch_post(unsigned command, uintptr_t generation)
{
    assert(!exiting && command >= 1 && command <= 3 && generation != 0);
    if (!allow_post) return false;
    queued_command = command; queued_parameter = generation; ++queue_calls; return true;
}
void ul_frontend_dispatch_close(void) { /* Retain copied callback for late delivery. */ }
bool ul_plugin_set_capture_schedulers(ul_arm_scheduler attach, ul_arm_scheduler cleanup)
{ capture_scheduler = attach; cleanup_scheduler = cleanup; return allow_capture_schedulers; }
bool ul_plugin_capture_inspect_request(uintptr_t *generation, uint8_t *mask)
{ assert(!after_exit); *generation = capture_generation; *mask = 4; return inspect_requested; }
bool ul_audio_capture_inspect_frontend(uint8_t mask, ul_audio_capture_spec *spec)
{
    assert(!after_exit && mask == 4); ++inspect_calls;
    *spec = (ul_audio_capture_spec){48000, 2, 2, 0, 5, 11, 12};
    return allow_inspect;
}
void ul_plugin_capture_inspected(uintptr_t generation, const ul_audio_capture_spec *spec)
{
    assert(!after_exit && generation == capture_generation); ++inspected_calls;
    inspected_ok = spec != NULL;
    if (spec != NULL) assert(spec->sample_rate == 48000 && spec->mix_mask == 5);
}
ul_audio_capture *ul_plugin_capture_retain(uintptr_t generation)
{ assert(!after_exit); return capture_available && generation == capture_generation ? test_capture : NULL; }
bool ul_audio_capture_connect_frontend(ul_audio_capture *capture, uintptr_t generation)
{ assert(!after_exit && capture == test_capture && generation == capture_generation); ++connect_calls; return allow_connect; }
void ul_plugin_capture_attached(uintptr_t generation, ul_audio_capture *capture, bool success)
{ assert(!after_exit && generation == capture_generation && capture == test_capture); ++attached_calls; attached_ok = success; }
void ul_audio_capture_release(ul_audio_capture *capture)
{ assert(capture == test_capture); ++capture_releases; }
void ul_plugin_capture_stop_frontend(void) { assert(!after_exit); ++stop_calls; }
void ul_audio_capture_disconnect_frontend(uintptr_t generation, bool all)
{ assert(!after_exit); ++disconnect_calls; disconnected_generation = generation; disconnected_all = all; }
void ul_plugin_capture_cleanup_complete(uintptr_t generation)
{
    assert(!after_exit && disconnect_calls != 0 && !disconnected_all);
    assert(disconnected_generation == generation);
    ++cleanup_completed_calls;
}
void ul_audio_capture_abandon_after_shutdown(void) { ++abandon_calls; }
ul_plugin_snapshot ul_plugin_get_status(void) { return snapshot; }
void ul_plugin_stop_accepting(void) { assert(!enabled); snapshot.status = UL_PLUGIN_CLOSED; record('S'); }
void ul_plugin_close(void) { assert(!enabled); snapshot.status = UL_PLUGIN_CLOSED; record('C'); }
void ul_vendor_set_enabled(bool value) { enabled = value; record(value ? 'E' : 'D'); }
void ul_pairing_ui_show(HWND owner) { assert(owner != NULL); }
void ul_vendor_issue(obs_data_t *request, obs_data_t *response, void *data)
{ (void)request; (void)response; (void)data; }
void ul_vendor_prepare(obs_data_t *request, obs_data_t *response, void *data)
{ (void)request; (void)response; (void)data; }
void ul_vendor_status(obs_data_t *request, obs_data_t *response, void *data)
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
#define obs_websocket_get_api_version test_api
#define obs_websocket_register_vendor test_vendor
#define obs_websocket_vendor_register_request test_register
#define obs_websocket_vendor_unregister_request test_unregister
#define blog test_log
#include "../src/bridge.c"

static void reset(void)
{
    start_calls = register_calls = unregister_calls = tools_calls = event_calls = 0;
    has_window = allow_start = allow_status = allow_issue = allow_prepare = allow_unregister = true;
    enabled = exiting = false;
    after_exit = false;
    api_version = OBS_WEBSOCKET_API_VERSION;
    snapshot = (ul_plugin_snapshot){UL_PLUGIN_UNPAIRED, UL_PAIRING_MISSING, true, false};
    vendor = NULL;
    status_registered = issue_registered = prepare_registered = false;
    order_size = 0;
    order[0] = 0;
    frontend_open = false; queued_arm = 0; stream_busy = false;
    arm_scheduler = capture_scheduler = cleanup_scheduler = NULL;
    queued_task = NULL; queued_parameter = 0; queued_command = 0;
    queued_capture = queued_cleanup = 0;
    allow_dispatch = allow_post = allow_capture_schedulers = true;
    allow_inspect = allow_connect = true;
    inspect_requested = capture_available = inspected_ok = attached_ok = disconnected_all = false;
    capture_generation = 40; disconnected_generation = 0;
    inspect_calls = inspected_calls = connect_calls = attached_calls = 0;
    capture_releases = stop_calls = disconnect_calls = abandon_calls = 0;
    cleanup_completed_calls = 0;
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
    assert(enabled && register_calls == 4 && status_registered && issue_registered && prepare_registered);
    obs_module_post_load(); assert(register_calls == 4);
    order_size = 0; order[0] = 0; exiting = true;
    frontend_event(OBS_FRONTEND_EVENT_EXIT, NULL);
    assert(strcmp(order, "DSPIGC") == 0 && unregister_calls == 3 && !enabled);

    reset(); allow_prepare = allow_unregister = false;
    obs_module_post_load();
    assert(!enabled && issue_registered && !prepare_registered && !status_registered && unregister_calls == 1);
    order_size = 0; order[0] = 0; exiting = true;
    frontend_event(OBS_FRONTEND_EVENT_EXIT, NULL);
    assert(strcmp(order, "DSIC") == 0 && unregister_calls == 2 && !enabled);

    reset(); allow_prepare = false;
    obs_module_post_load();
    assert(!enabled && !issue_registered && !prepare_registered && unregister_calls == 1);
    reset(); allow_issue = false;
    obs_module_post_load(); assert(!enabled && register_calls == 2 && unregister_calls == 0);
    reset(); allow_status = false;
    obs_module_post_load();
    assert(!enabled && register_calls == 4 && unregister_calls == 2);
    assert(strcmp(order, "PID") == 0);
    assert(!status_registered && !issue_registered && !prepare_registered);
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
    queued_task(queued_command, queued_parameter);
    assert(checked_generation == 7 && checked_idle && output_releases == 1);
    queued_task(queued_command, queued_parameter); assert(idle_checks == 1); /* Duplicate callback. */
    assert(arm_scheduler(8));
    check_arm_on_frontend((void *)(uintptr_t)7);
    assert(idle_checks == 1 && queued_arm == 8); /* Stale callback cannot consume new slot. */
    current_output_active = true;
    queued_task(queued_command, queued_parameter);
    assert(!checked_idle && checked_generation == 8 && output_releases == 2);
    current_output_active = false; current_active = true;
    assert(arm_scheduler(9)); queued_task(queued_command, queued_parameter);
    assert(!checked_idle && output_releases == 3);
    has_output = false; current_active = false;
    assert(arm_scheduler(10)); queued_task(queued_command, queued_parameter);
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
    queued_task(queued_command, queued_parameter); /* No OBS or retired runtime access after EXIT. */
    assert(!arm_scheduler(12) && idle_checks == 4);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTED, NULL);
    assert(stream_events == 4);
    reset(); assert(obs_module_load()); assert(arm_scheduler(13));
    exiting = true; obs_module_unload(); queued_task(queued_command, queued_parameter);
    assert(idle_checks == 0 && !arm_scheduler(14));

    /* STARTING, STARTED and STOPPING remain busy even while both public active
     * queries are false. Only the completed STOPPED lifecycle proves idle. */
    reset(); assert(obs_module_load());
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTING, NULL);
    assert(stream_busy);
    assert(arm_scheduler(21)); queued_task(queued_command, queued_parameter);
    assert(checked_generation == 21 && !checked_idle && idle_checks == 1);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTED, NULL);
    assert(arm_scheduler(22)); queued_task(queued_command, queued_parameter);
    assert(checked_generation == 22 && !checked_idle && idle_checks == 2);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STOPPING, NULL);
    assert(arm_scheduler(23)); queued_task(queued_command, queued_parameter);
    assert(checked_generation == 23 && !checked_idle && idle_checks == 3);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STOPPED, NULL);
    assert(arm_scheduler(24)); queued_task(queued_command, queued_parameter);
    assert(checked_generation == 24 && checked_idle && idle_checks == 4);

    /* A synchronous start failure has no public frontend STOPPED event, so it
     * stays fail closed. An unavailable output and repeated STARTING are also
     * unknown/busy until OBS reports STOPPED. */
    reset(); assert(obs_module_load()); has_output = false;
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTING, NULL);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTING, NULL);
    assert(arm_scheduler(25)); queued_task(queued_command, queued_parameter);
    assert(!checked_idle && stream_busy && output_releases == 0);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STOPPED, NULL);
    assert(arm_scheduler(26)); queued_task(queued_command, queued_parameter);
    assert(checked_idle && !stream_busy && output_releases == 0);

    /* EXIT closes before a queued Arm callback; it performs no frontend/output
     * query after the final frontend callback returns. */
    reset(); assert(obs_module_load());
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTING, NULL);
    assert(arm_scheduler(27));
    exiting = true;
    frontend_event(OBS_FRONTEND_EVENT_EXIT, NULL);
    after_exit = true;
    queued_task(queued_command, queued_parameter);
    assert(idle_checks == 0 && output_releases == 0 && !arm_scheduler(28));

    /* Unload is the native-only fallback if frontend EXIT was missed. */
    reset(); assert(obs_module_load());
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTING, NULL);
    assert(arm_scheduler(29));
    exiting = true; obs_module_unload();
    after_exit = true;
    queued_task(queued_command, queued_parameter);
    assert(idle_checks == 0 && output_releases == 0 && !arm_scheduler(30));

    reset(); allow_dispatch = false;
    assert(!obs_module_load() && tools_calls == 0 && event_calls == 0);
    reset(); allow_capture_schedulers = false;
    assert(!obs_module_load() && tools_calls == 0 && event_calls == 0);

    /* Read-only inspection belongs to STARTED and reports unsupported formats. */
    reset(); assert(obs_module_load()); inspect_requested = true;
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTING, NULL);
    assert(inspect_calls == 0 && connect_calls == 0);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTED, NULL);
    assert(inspect_calls == 1 && inspected_calls == 1 && inspected_ok && connect_calls == 0);
    allow_inspect = false;
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STARTED, NULL);
    assert(inspect_calls == 2 && inspected_calls == 2 && !inspected_ok);

    /* Failed posts free each pending slot. Attach retains its own capture and
     * stale/duplicate commands cannot consume a new request. */
    allow_post = false;
    assert(!arm_scheduler(40) && queued_arm == 0);
    assert(!capture_scheduler(40) && queued_capture == 0);
    assert(!cleanup_scheduler(40) && queued_cleanup == 0);
    allow_post = true; capture_available = true;
    assert(capture_scheduler(40) && !capture_scheduler(41));
    dispatch_frontend(2, 39);
    assert(queued_capture == 40 && connect_calls == 0);
    queued_task(queued_command, queued_parameter);
    assert(connect_calls == 1 && attached_calls == 1 && attached_ok && capture_releases == 1);
    queued_task(queued_command, queued_parameter);
    assert(connect_calls == 1 && capture_releases == 1);
    allow_connect = false;
    assert(capture_scheduler(40)); queued_task(queued_command, queued_parameter);
    assert(connect_calls == 2 && attached_calls == 2 && !attached_ok && capture_releases == 2);
    capture_available = false;
    assert(capture_scheduler(40)); queued_task(queued_command, queued_parameter);
    assert(connect_calls == 2 && queued_capture == 0);

    assert(cleanup_scheduler(40) && !cleanup_scheduler(41));
    dispatch_frontend(3, 39);
    assert(queued_cleanup == 40 && disconnect_calls == 0 && cleanup_completed_calls == 0);
    queued_task(queued_command, queued_parameter);
    assert(disconnect_calls == 1 && disconnected_generation == 40 && !disconnected_all
           && cleanup_completed_calls == 1);
    queued_task(queued_command, queued_parameter);
    assert(disconnect_calls == 1 && cleanup_completed_calls == 1);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STOPPING, NULL);
    assert(stop_calls == 1 && disconnect_calls == 2 && disconnected_all);
    frontend_event(OBS_FRONTEND_EVENT_STREAMING_STOPPED, NULL);
    assert(stop_calls == 2 && disconnect_calls == 3 && disconnected_all);
    assert(capture_scheduler(40) && cleanup_scheduler(40));
    frontend_event(OBS_FRONTEND_EVENT_EXIT, NULL); after_exit = true;
    dispatch_frontend(2, 40); dispatch_frontend(3, 40);
    assert(stop_calls == 3 && disconnect_calls == 4 && connect_calls == 2
           && cleanup_completed_calls == 1);
    assert(!capture_scheduler(40) && !cleanup_scheduler(40));
    obs_module_unload();
    assert(abandon_calls == 1 && disconnect_calls == 4);

    /* Missed EXIT must use only native abandonment, even with queued capture. */
    reset(); assert(obs_module_load()); capture_available = true;
    assert(capture_scheduler(40)); after_exit = true;
    obs_module_unload(); queued_task(queued_command, queued_parameter);
    assert(abandon_calls == 1 && disconnect_calls == 0 && connect_calls == 0);

    puts("bridge lifecycle, frontend handoff and stream-busy gate tests passed");
    return 0;
}
