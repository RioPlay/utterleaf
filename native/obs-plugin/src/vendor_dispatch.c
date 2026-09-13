// SPDX-License-Identifier: GPL-2.0-or-later
#include "vendor_dispatch.h"
#include "authorization.h"
#include "plugin_state.h"

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

static volatile LONG dispatch_enabled;

void ul_vendor_set_enabled(bool enabled)
{
    InterlockedExchange(&dispatch_enabled, enabled ? 1 : 0);
}

/* OBS owns JSON decoding. These checks describe the parsed public obs_data
 * boundary, not access to the original JSON text or duplicate-key spelling. */
static bool exact_fields(obs_data_t *request, const char *const *names,
                         const enum obs_data_type *types, size_t count)
{
    unsigned seen = 0u;
    obs_data_item_t *item;
    if (request == NULL)
        return false;
    item = obs_data_first(request);
    while (item != NULL) {
        const char *name = obs_data_item_get_name(item);
        size_t index;
        for (index = 0u; index < count; ++index)
            if (name != NULL && strcmp(name, names[index]) == 0)
                break;
        if (index == count || (seen & (1u << index)) != 0u ||
            !obs_data_item_has_user_value(item) ||
            obs_data_item_gettype(item) != types[index] ||
            (types[index] == OBS_DATA_NUMBER &&
             obs_data_item_numtype(item) != OBS_DATA_NUM_INT)) {
            obs_data_item_release(&item);
            return false;
        }
        seen |= 1u << index;
        obs_data_item_next(&item);
    }
    return seen == (1u << count) - 1u;
}

static int hex_digit(char value)
{
    if (value >= '0' && value <= '9')
        return value - '0';
    if (value >= 'a' && value <= 'f')
        return value - 'a' + 10;
    return -1;
}

static bool decode_hex(const char *value, uint8_t *output, size_t length)
{
    if (value == NULL)
        return false;
    for (size_t i = 0u; i < length; ++i) {
        int high = hex_digit(value[i * 2u]);
        int low;
        /* Stop on the first terminator; never read beyond a short C string. */
        if (high < 0)
            return false;
        low = hex_digit(value[i * 2u + 1u]);
        if (low < 0)
            return false;
        output[i] = (uint8_t)((high << 4) | low);
    }
    return value[length * 2u] == '\0';
}

static void encode_hex(const uint8_t *value, size_t length, char *output)
{
    static const char digits[] = "0123456789abcdef";
    for (size_t i = 0u; i < length; ++i) {
        output[i * 2u] = digits[value[i] >> 4];
        output[i * 2u + 1u] = digits[value[i] & 15u];
    }
    output[length * 2u] = '\0';
}

void ul_vendor_issue(obs_data_t *request, obs_data_t *response, void *private_data)
{
    static const char *const names[] = {"clientPid", "sessionId", "additionalMixMask"};
    static const enum obs_data_type types[] = {OBS_DATA_NUMBER, OBS_DATA_STRING, OBS_DATA_NUMBER};
    uint8_t session[16] = {0};
    uint8_t challenge[UL_AUTHORIZATION_CHALLENGE_BYTES] = {0};
    char encoded[UL_AUTHORIZATION_CHALLENGE_BYTES * 2u + 1u];
    long long pid, mask;
    unsigned nonzero = 0u;
    (void)private_data;
    if (response == NULL)
        return;
    obs_data_clear(response);
    obs_data_set_bool(response, "ok", false);
    if (InterlockedCompareExchange(&dispatch_enabled, 0, 0) == 0 ||
        ul_plugin_get_status().status == UL_PLUGIN_CLOSED)
        return;
    if (!exact_fields(request, names, types, 3u))
        return;
    pid = obs_data_get_int(request, "clientPid");
    mask = obs_data_get_int(request, "additionalMixMask");
    if (pid < 5 || pid > UINT32_MAX || mask < 0 || mask > 63 ||
        !decode_hex(obs_data_get_string(request, "sessionId"), session, sizeof(session)))
        return;
    for (size_t i = 0u; i < sizeof(session); ++i)
        nonzero |= session[i];
    if (nonzero == 0u || !ul_plugin_issue((DWORD)pid, session, (uint8_t)mask, challenge))
        return;
    encode_hex(challenge, sizeof(challenge), encoded);
    obs_data_set_int(response, "protocolVersion", 1);
    obs_data_set_string(response, "challenge", encoded);
    obs_data_set_bool(response, "ok", true);
}

void ul_vendor_prepare(obs_data_t *request, obs_data_t *response, void *private_data)
{
    static const char *const names[] = {"challenge", "proof"};
    static const enum obs_data_type types[] = {OBS_DATA_STRING, OBS_DATA_STRING};
    uint8_t challenge[UL_AUTHORIZATION_CHALLENGE_BYTES] = {0};
    uint8_t proof[UL_AUTHORIZATION_PROOF_BYTES] = {0};
    bool valid, prepared;
    (void)private_data;
    if (response == NULL)
        return;
    obs_data_clear(response);
    obs_data_set_bool(response, "ok", false);
    if (InterlockedCompareExchange(&dispatch_enabled, 0, 0) == 0 ||
        ul_plugin_get_status().status == UL_PLUGIN_CLOSED)
        return;
    valid = exact_fields(request, names, types, 2u) &&
            decode_hex(obs_data_get_string(request, "challenge"), challenge, sizeof(challenge)) &&
            decode_hex(obs_data_get_string(request, "proof"), proof, sizeof(proof));
    /* Even a malformed attempt consumes the one outstanding challenge. */
    prepared = ul_plugin_prepare(valid ? challenge : NULL, valid ? sizeof(challenge) : 0u,
                                 valid ? proof : NULL, valid ? sizeof(proof) : 0u);
    SecureZeroMemory(proof, sizeof(proof));
    if (valid && prepared) {
        obs_data_set_int(response, "protocolVersion", 1);
        obs_data_set_bool(response, "ok", true);
    }
}
