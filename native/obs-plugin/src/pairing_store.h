// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_OBS_PAIRING_STORE_H
#define UTTERLEAF_OBS_PAIRING_STORE_H

#include <windows.h>

#include <stdint.h>

#define UL_PAIRING_KEY_BYTES 32u
#define UL_PAIRING_MAX_FILE_BYTES 4108u

typedef struct ul_pairing_store ul_pairing_store;

typedef enum ul_pairing_result {
    UL_PAIRING_OK = 0,
    UL_PAIRING_MISSING = 1,
    UL_PAIRING_EXISTS = 2,
    UL_PAIRING_CANCELLED = 3,
    UL_PAIRING_INVALID_ARGUMENT = 4,
    UL_PAIRING_UNSUPPORTED = 5,
    UL_PAIRING_UNSAFE_SECURITY = 6,
    UL_PAIRING_CORRUPT = 7,
    UL_PAIRING_CRYPTO_ERROR = 8,
    UL_PAIRING_IO_ERROR = 9,
    UL_PAIRING_POSTCOMMIT_INVALID = 10
} ul_pairing_result;

typedef struct ul_pairing_cancel {
    volatile LONG requested;
} ul_pairing_cancel;

/* A cancel token is initialized immediately before one mutation and not reused. */
void ul_pairing_cancel_init(ul_pairing_cancel *cancel);
void ul_pairing_cancel_request(ul_pairing_cancel *cancel);

/*
 * Opens the current user's production store below LocalAppData. Missing
 * Utterleaf/obs-plugin directories are created with the store's private ACL.
 */
ul_pairing_result ul_pairing_store_open(ul_pairing_store **store_out);

/*
 * Test-only root substitution. root must name an existing, absolute local
 * drive directory used solely for disposable tests. It is treated like the
 * LocalAppData parent and its ACL is never changed; the private descendants
 * Utterleaf/obs-plugin are created and verified normally.
 */
ul_pairing_result
ul_pairing_store_open_test_root(const wchar_t *root,
                                ul_pairing_store **store_out);

/* The caller must quiesce operations before destroying the store. */
void ul_pairing_store_destroy(ul_pairing_store *store);

/* Loads the authoritative role-1 capability. */
ul_pairing_result ul_pairing_store_load(ul_pairing_store *store,
                                        uint8_t key[UL_PAIRING_KEY_BYTES]);

/* Generates and persists a new capability only when the store is absent. */
ul_pairing_result ul_pairing_store_create(
    ul_pairing_store *store, const ul_pairing_cancel *cancel,
    uint8_t key[UL_PAIRING_KEY_BYTES]);

/* Explicitly replaces an existing store and returns the new capability. */
ul_pairing_result ul_pairing_store_replace(
    ul_pairing_store *store, const ul_pairing_cancel *cancel,
    uint8_t key[UL_PAIRING_KEY_BYTES]);

/* Writes a non-replacing role-2 transfer package at an absolute local path. */
ul_pairing_result ul_pairing_store_export(
    ul_pairing_store *store, const wchar_t *destination,
    const ul_pairing_cancel *cancel);

/* Removes the authoritative store. Missing is returned distinctly. */
ul_pairing_result ul_pairing_store_forget(ul_pairing_store *store);

#endif
