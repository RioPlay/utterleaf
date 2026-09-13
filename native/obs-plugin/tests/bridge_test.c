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
    api_version = OBS_WEBSOCKET_API_VERSION;
    snapshot = (ul_plugin_snapshot){UL_PLUGIN_UNPAIRED, UL_PAIRING_MISSING, true, false};
    vendor = NULL;
    issue_registered = prepare_registered = false;
    order_size = 0;
    order[0] = 0;
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
    puts("bridge wrapper lifecycle tests passed");
    return 0;
}
