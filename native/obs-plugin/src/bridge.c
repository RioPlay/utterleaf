// SPDX-License-Identifier: GPL-2.0-or-later
#include <obs-module.h>
#include <obs-frontend-api.h>
#include <assert.h>
#include <string.h>
#include <obs-websocket-api.h>

#include "plugin_state.h"
#include "pairing_ui.h"
#include "vendor_dispatch.h"

OBS_DECLARE_MODULE()

/* OBS serializes module hooks and frontend EXIT on the frontend thread.
 * Vendor callbacks can race these hooks; they carry no heap-owned state. */
static obs_websocket_vendor vendor;
static bool issue_registered;
static bool prepare_registered;
static SRWLOCK frontend_gate = SRWLOCK_INIT;
static bool frontend_open;
static uintptr_t queued_arm;
/* Public active queries can stay false during startup. Once STARTING arrives,
 * only STOPPED proves idle; a synchronous failure emits no public STOPPED and
 * therefore remains fail closed. */
static bool stream_busy;

/* OBS 32.2.2 queues worker UI tasks through Qt. The only task parameter is a
 * numeric generation, never a borrowed runtime/event/admission pointer. */
static void check_arm_on_frontend(void *parameter)
{
    uintptr_t generation = (uintptr_t)parameter;
    obs_output_t *output;
    bool idle;
    AcquireSRWLockExclusive(&frontend_gate);
    if (!frontend_open || generation == 0u || queued_arm != generation) {
        ReleaseSRWLockExclusive(&frontend_gate);
        return;
    }
    queued_arm = 0u;
    idle = !stream_busy && !obs_frontend_streaming_active();
    output = obs_frontend_get_streaming_output();  /* Already a new reference. */
    if (output != NULL) {
        idle = idle && !obs_output_active(output);
        obs_output_release(output);
    }
    ul_plugin_arm_checked(generation, idle);
    ReleaseSRWLockExclusive(&frontend_gate);
}

static bool queue_arm(uintptr_t generation)
{
    bool queued = false;
    AcquireSRWLockExclusive(&frontend_gate);
    if (frontend_open && generation != 0u && queued_arm == 0u) {
        queued_arm = generation;
        obs_queue_task(OBS_TASK_UI, check_arm_on_frontend,
                        (void *)generation, false);
        queued = true;
    }
    ReleaseSRWLockExclusive(&frontend_gate);
    return queued;
}

static void close_frontend(void)
{
    AcquireSRWLockExclusive(&frontend_gate);
    frontend_open = false;
    queued_arm = 0u;
    stream_busy = true;
    ReleaseSRWLockExclusive(&frontend_gate);
}

static void pairing_menu(void *private_data)
{
    (void)private_data;
    if (ul_plugin_get_status().status != UL_PLUGIN_CLOSED)
        ul_pairing_ui_show((HWND)obs_frontend_get_main_window_handle());
}

static void frontend_event(enum obs_frontend_event event, void *private_data)
{
    (void)private_data;
    if (event != OBS_FRONTEND_EVENT_EXIT) {
        AcquireSRWLockExclusive(&frontend_gate);
        if (frontend_open) {
            switch (event) {
            case OBS_FRONTEND_EVENT_STREAMING_STARTING:
                stream_busy = true;
                ul_plugin_stream_event(UL_STREAM_STARTING); break;
            case OBS_FRONTEND_EVENT_STREAMING_STARTED:
                stream_busy = true;
                ul_plugin_stream_event(UL_STREAM_STARTED); break;
            case OBS_FRONTEND_EVENT_STREAMING_STOPPING:
                stream_busy = true;
                ul_plugin_stream_event(UL_STREAM_STOPPING); break;
            case OBS_FRONTEND_EVENT_STREAMING_STOPPED:
                stream_busy = false;
                ul_plugin_stream_event(UL_STREAM_STOPPED); break;
            default: break;
            }
        }
        ReleaseSRWLockExclusive(&frontend_gate);
        return;
    }
    close_frontend();
    ul_vendor_set_enabled(false);
    ul_plugin_stop_accepting();
    if (prepare_registered)
        obs_websocket_vendor_unregister_request(vendor, "PrepareSession");
    if (issue_registered)
        obs_websocket_vendor_unregister_request(vendor, "IssueAuthorization");
    issue_registered = prepare_registered = false;
    ul_plugin_close();
    /* The frontend owns its callback/menu destruction. Static data and module
     * code stay pinned, so callbacks copied before close safely decline. */
}

bool obs_module_load(void)
{
    if (obs_get_version() != LIBOBS_API_VER || obs_current_module() == NULL ||
        obs_frontend_get_main_window_handle() == NULL)
        return false;
    if (!ul_plugin_start())
        return false;
    if (!ul_plugin_set_arm_scheduler(queue_arm)) {
        ul_plugin_close();
        return false;
    }
    AcquireSRWLockExclusive(&frontend_gate);
    frontend_open = true;
    ReleaseSRWLockExclusive(&frontend_gate);
    obs_frontend_add_event_callback(frontend_event, NULL);
    obs_frontend_add_tools_menu_item("Utterleaf pairing...", pairing_menu, NULL);
    blog(LOG_INFO, "[Utterleaf OBS bridge] pairing controls loaded; recording remains off");
    return true;
}

void obs_module_post_load(void)
{
    ul_plugin_snapshot state = ul_plugin_get_status();
    if (vendor != NULL)
        return;
    if (!state.owns_store || state.status == UL_PLUGIN_CLOSED)
        return;
    if (obs_websocket_get_api_version() != OBS_WEBSOCKET_API_VERSION) {
        blog(LOG_WARNING, "[Utterleaf OBS bridge] compatible obs-websocket API unavailable");
        return;
    }
    vendor = obs_websocket_register_vendor("Utterleaf");
    if (vendor == NULL)
        return;
    issue_registered = obs_websocket_vendor_register_request(vendor, "IssueAuthorization", ul_vendor_issue, NULL);
    if (issue_registered)
        prepare_registered = obs_websocket_vendor_register_request(vendor, "PrepareSession", ul_vendor_prepare, NULL);
    if (!prepare_registered && issue_registered) {
        issue_registered = !obs_websocket_vendor_unregister_request(vendor, "IssueAuthorization");
    }
    ul_vendor_set_enabled(issue_registered && prepare_registered);
    if (!prepare_registered)
        blog(LOG_WARNING, "[Utterleaf OBS bridge] request registration failed; connections disabled");
}

void obs_module_unload(void)
{
    /* Native-only fallback: frontend/websocket teardown order is not assumed. */
    close_frontend();
    ul_vendor_set_enabled(false);
    ul_plugin_close();
}

const char *obs_module_name(void)
{
    return "Utterleaf OBS bridge (development)";
}

const char *obs_module_description(void)
{
    return "Private Utterleaf pairing and authenticated session preparation. No audio capture yet.";
}

const char *obs_module_author(void)
{
    return "Utterleaf contributors";
}
