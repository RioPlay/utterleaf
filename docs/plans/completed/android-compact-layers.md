# Compact Android keyboard layers — completed

This layout correction shipped in [Android alpha15](android-alpha15-snapshot.md)
from tested source `52b0e6a`, merged at `bc1cc2b`. See the
[mobile roadmap](../../mobile-roadmap.md) for remaining product work.

## Result and constraints

Opening Tools previously stacked five 48dp rows above the letter keyboard.
The replacement uses one horizontal 48dp action strip with a fixed ABC exit.
Swipe the strip or use More to reveal additional actions; scrolling does not
activate them on release. Layout/settings, Edit and Terminal Fn/Nav occupy
replacement layers. Terminal keeps one modifier row, while the optional number
row remains an independent preference.

Comma tap inserts one comma. Holding opens the compact settings layer without
inserting punctuation or requiring finger travel; an accessibility long-click
route is also available. Cancellation, slide-off, multitouch, detach and stale
sessions discard pending actions. Private-draft restrictions remain enforced.
Ctrl/Alt state clears when its owning layer or session ends. Existing letter
rollover, long-press hints, editor guards and settings persistence/reset remain.

The installed app and primary IME are **Utterleaf**. The optional voice-only
provider is **Utterleaf dictation**. The application ID, signing channel,
preference keys, model storage, speech runtime and screenshot protection remain
unchanged. There are no new dependencies, permissions, network access, clipboard
history or typing collection.

FUTO's [public action organization](https://docs.keyboard.futo.tech/actions/assigningactions)
was an interaction reference. No FUTO or LatinIME source, assets or product
identity was copied; the keyboard remains Utterleaf's original implementation.

## Verification

Independent review covered production changes, native gesture/lifecycle tests,
settings and editor regressions, and app-owned renders. Local API 35 bundles
passed 56 touch/geometry/panel tests and 31 Compose/private/editor/gesture tests;
three live-IME structural checks also passed. The final local instrumentation
stdout was console-only, so it is not a durable full-suite release receipt.
Local and installed debug APK hashes were independently matched at that stage.

The final [canonical run 34747169547](https://github.com/RioPlay/utterleaf/actions/runs/34747169547)
retained complete results for all 148 API 35 tests and 31 JVM tests with no
failures or skips, plus tooling, lint and builds. The
[release record](android-alpha15-snapshot.md) contains protected signing and
independent downloaded-APK evidence.

Owned-view review covered normal typing, Tools before/after native horizontal
swiping, settings, Edit and Terminal Fn/Nav at 360dp dark/full and approximately
412dp light/large left/right alignment. The
[mobile guide](../../mobile.md) includes three unchanged captures of the compact
implementation at `a8e39af`. These contain no host text and retain screenshot
protection; they are not physical-phone or signed-APK screenshots.

## Remaining limits

Physical-phone comfort and TalkBack/Switch Access usability remain unverified,
along with landscape and broader editor coverage. No Incognito, touch heatmap,
learning, prediction or swipe-typing feature is claimed by this layout slice.
Those capabilities remain separate mobile-roadmap work.
