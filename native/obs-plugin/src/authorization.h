// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_OBS_AUTHORIZATION_H
#define UTTERLEAF_OBS_AUTHORIZATION_H

#include "admission.h"

#include <windows.h>

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define UL_AUTHORIZATION_CHALLENGE_BYTES 60u
#define UL_AUTHORIZATION_PROOF_BYTES 32u

typedef struct ul_authorizer ul_authorizer;

typedef struct ul_prepare_options {
    DWORD client_pid;
    uint8_t session[16];
    uint8_t additional_mix_mask;
} ul_prepare_options;

/* Create one authorizer generation. key is copied and must not be all zero. */
ul_authorizer *ul_authorizer_create(const uint8_t key[32]);

/*
 * Issue the sole outstanding 15-second prepare challenge. Repeating the same
 * parameters while it remains valid returns the same challenge; other
 * parameters cannot replace it. out_challenge is zeroed on failure.
 */
bool ul_authorizer_issue(
    ul_authorizer *authorizer, DWORD client_pid, const uint8_t session[16],
    uint8_t additional_mix_mask,
    uint8_t out_challenge[UL_AUTHORIZATION_CHALLENGE_BYTES]);

/*
 * Consume exactly one outstanding challenge attempt, including malformed or
 * invalid attempts. On success, returns a borrowed admission owned by the
 * authorizer and fills options. options is zeroed on failure. The caller owns
 * the admission worker and must join it before release or destroy.
 */
ul_admission *ul_authorizer_prepare(
    ul_authorizer *authorizer, const uint8_t *challenge, size_t challenge_size,
    const uint8_t *proof, size_t proof_size, ul_prepare_options *options);

/*
 * True only while this non-revoked authorizer owns a prepared admission. This
 * is an additional owner guard, not proof of completed pipe authentication,
 * current process liveness, or an idle OBS state, and cannot authorize Arm.
 */
bool ul_authorizer_is_active(ul_authorizer *authorizer);

/* Permanently revoke this generation and cancel its admission outside the lock. */
void ul_authorizer_revoke(ul_authorizer *authorizer);

/*
 * Clear any challenge and destroy the owned admission while retaining an
 * unrevoked pairing key. All authorizer calls and the admission worker must be
 * quiesced before entry. A borrowed admission must never be destroyed directly.
 */
void ul_authorizer_release(ul_authorizer *authorizer);

/* All calls and the admission worker must be quiesced before entry. */
void ul_authorizer_destroy(ul_authorizer *authorizer);

#ifdef __cplusplus
}
#endif

#endif
