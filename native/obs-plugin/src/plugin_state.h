// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_OBS_PLUGIN_STATE_H
#define UTTERLEAF_OBS_PLUGIN_STATE_H

#include "authorization.h"
#include "pairing_store.h"

#include <windows.h>

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum ul_plugin_status {
    UL_PLUGIN_CLOSED = 0,
    UL_PLUGIN_UNPAIRED = 1,
    UL_PLUGIN_PAIRED = 2,
    UL_PLUGIN_STORAGE_ERROR = 3,
    UL_PLUGIN_IN_USE = 4
} ul_plugin_status;

typedef struct ul_plugin_snapshot {
    ul_plugin_status status;
    ul_pairing_result storage_result;
    bool owns_store;
    /* False means no active authentication/READY/armed worker. Reaping is deferred. */
    bool admission_pending;
} ul_plugin_snapshot;

typedef enum ul_session_phase {
    UL_SESSION_NONE = 0, UL_SESSION_READY, UL_SESSION_ARM_PENDING,
    UL_SESSION_ARMED, UL_SESSION_STARTING, UL_SESSION_STARTED,
    UL_SESSION_TERMINAL
} ul_session_phase;

typedef enum ul_stream_event {
    UL_STREAM_STARTING = 1, UL_STREAM_STARTED, UL_STREAM_STOPPING,
    UL_STREAM_STOPPED
} ul_stream_event;

/* Pinned callback; queues nonblocking frontend work with numeric generation
 * only. It must refuse after frontend shutdown, without calling OBS. */
typedef bool (*ul_arm_scheduler)(uintptr_t generation);
bool ul_plugin_set_arm_scheduler(ul_arm_scheduler scheduler);
void ul_plugin_arm_checked(uintptr_t generation, bool idle);
void ul_plugin_stream_event(ul_stream_event event);
ul_session_phase ul_plugin_session_status(void);

/*
 * Permanently pins this DLL generation before callbacks may be registered.
 * A process may start this component once; close is final and cannot be reset.
 * True means the status API is usable, including unpaired/error/in-use states.
 */
bool ul_plugin_start(void);

/*
 * Permanently closes callback admission and signals stable cancellation state.
 * This is nonblocking; call close after unregistering external callbacks.
 */
void ul_plugin_stop_accepting(void);

/* Safe to repeat. New calls fail once close begins; in-flight calls are drained. */
void ul_plugin_close(void);

/* Returns a value copy that remains valid after close. */
ul_plugin_snapshot ul_plugin_get_status(void);

/*
 * Persist a new role-1 key and export its role-2 package. pairing_saved is
 * cleared on entry and set only after the new role-1 record is verified and
 * its authorizer is installed. An export error can therefore be returned with
 * pairing_saved true and a PAIRED snapshot.
 */
ul_pairing_result ul_plugin_pair(const wchar_t *destination, bool replace,
                                 bool *pairing_saved);

ul_pairing_result ul_plugin_export(const wchar_t *destination);

/* Revokes live authorization before attempting durable deletion. */
ul_pairing_result ul_plugin_forget(void);

bool ul_plugin_issue(
    DWORD client_pid, const uint8_t session[16], uint8_t additional_mix_mask,
    uint8_t out_challenge[UL_AUTHORIZATION_CHALLENGE_BYTES]);

/* Malformed byte inputs are forwarded so they consume an outstanding attempt. */
bool ul_plugin_prepare(const uint8_t *challenge, size_t challenge_size,
                       const uint8_t *proof, size_t proof_size);

#ifdef __cplusplus
}
#endif

#endif
