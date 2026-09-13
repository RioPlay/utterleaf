// SPDX-License-Identifier: GPL-2.0-or-later
#include <obs-module.h>

OBS_DECLARE_MODULE()

bool obs_module_load(void)
{
    /* This first build is intentionally tied to the reviewed runtime. */
    if (obs_get_version() != LIBOBS_API_VER || obs_current_module() == NULL)
        return false;
    blog(LOG_INFO, "[Utterleaf OBS bridge] inert module loaded");
    return true;
}

void obs_module_unload(void)
{
    blog(LOG_INFO, "[Utterleaf OBS bridge] inert module unloaded");
}

const char *obs_module_name(void)
{
    return "Utterleaf OBS bridge (development)";
}

const char *obs_module_description(void)
{
    return "Inert build and loader verification. No audio capture or network endpoint.";
}

const char *obs_module_author(void)
{
    return "Utterleaf contributors";
}
