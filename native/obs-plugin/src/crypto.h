// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_OBS_CRYPTO_H
#define UTTERLEAF_OBS_CRYPTO_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/*
 * Computes HMAC-SHA-256 using Windows CNG. The caller must provide a writable
 * 32-byte output disjoint from key, domain and data. The input ranges may
 * overlap. key is exactly 32 bytes; domain and data are bounded to 1..64 and
 * 1..256 bytes respectively. A non-null output is zeroed on every failure.
 */
bool ul_hmac_sha256(const uint8_t key[32], const uint8_t *domain,
                    size_t domain_size, const uint8_t *data, size_t data_size,
                    uint8_t output[32]);

#endif
