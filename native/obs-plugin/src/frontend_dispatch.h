// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_FRONTEND_DISPATCH_H
#define UTTERLEAF_FRONTEND_DISPATCH_H

#include <stdbool.h>
#include <stdint.h>

typedef void (*ul_frontend_dispatch_callback)(unsigned command,
                                               uintptr_t generation);

/* Open and owner cleanup run on the frontend thread, which pumps messages.
 * The caller pins this module. Open must finish before concurrent post/close;
 * it is one-shot for this DLL lifetime, including failure. Post is safe from any thread for
 * commands 1..4 and nonzero generations; the caller bounds pending work.
 * Close from another thread makes the dispatcher inert, and the frontend
 * thread must call close again to destroy the window and unregister the class.
 * A callback already copied by the owner may finish after non-owner close;
 * callbacks must recheck their own lifetime gate before accessing owned state. */
bool ul_frontend_dispatch_open(ul_frontend_dispatch_callback callback);
bool ul_frontend_dispatch_post(unsigned command, uintptr_t generation);
/* Callback-safe variant: fails immediately if dispatcher state is contended. */
bool ul_frontend_dispatch_try_post(unsigned command, uintptr_t generation);
void ul_frontend_dispatch_close(void);

#endif
