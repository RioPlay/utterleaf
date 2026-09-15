// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_OBS_VENDOR_DISPATCH_H
#define UTTERLEAF_OBS_VENDOR_DISPATCH_H

#include <obs.h>

/* Enable only after both endpoints are registered. Disable before teardown. */
void ul_vendor_set_enabled(bool enabled);

/* Static callbacks; private_data is unused and must never own runtime memory. */
void ul_vendor_issue(obs_data_t *request, obs_data_t *response, void *private_data);
void ul_vendor_prepare(obs_data_t *request, obs_data_t *response, void *private_data);

#endif
