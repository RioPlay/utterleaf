// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef UTTERLEAF_OBS_PAIRING_UI_H
#define UTTERLEAF_OBS_PAIRING_UI_H
#include <windows.h>

/* Called on the frontend thread, with its native top-level owner window. */
void ul_pairing_ui_show(HWND owner);

#endif
