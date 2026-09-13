// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_OBS_ADMISSION_H
#define UTTERLEAF_OBS_ADMISSION_H

#include <windows.h>

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct ul_admission ul_admission;

enum ul_admission_result {
    UL_ADMISSION_AUTH_OK = 0,
    UL_ADMISSION_REJECTED = 1,
    UL_ADMISSION_CANCELLED = 2,
    UL_ADMISSION_TIMEOUT = 3,
    UL_ADMISSION_IO_ERROR = 4,
};

/*
 * Create a once-only pending admission for an expected process. This must only
 * be called from an already-authenticated, bounded vendor-request context.
 * expected_pid is the credential holder's assertion; authentication separately
 * binds the actual named-pipe client to the retained process object.
 */
ul_admission *ul_admission_create(DWORD expected_pid,
                                  const uint8_t session[16]);

/*
 * Consume the pending admission. Exactly one caller may invoke this function,
 * with a timeout from 1 through 30000 milliseconds. The caller owns any worker
 * thread and must join it before destroying the admission.
 */
int ul_admission_authenticate(ul_admission *admission, DWORD timeout_ms);

/*
 * May run concurrently with authenticate until the caller joins that worker.
 * Cancellation prevents future pipe borrowing but cannot revoke a handle that
 * a caller already borrowed; that caller must stop and join its worker first.
 */
void ul_admission_cancel(ul_admission *admission);

/* No authenticate or cancel call may still be running when this is called. */
void ul_admission_destroy(ul_admission *admission);

/* Number of Client Hello bytes completed by native admission. */
DWORD ul_admission_read_count(const ul_admission *admission);

/* Borrowed handle; non-NULL only after success and before cancellation. */
HANDLE ul_admission_pipe(const ul_admission *admission);

#ifdef __cplusplus
}
#endif

#endif
