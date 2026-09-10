# Android typing surface

Released in **alpha05**. Revision f74b862 passed
[CI run 34432378047](https://github.com/RioPlay/utterleaf/actions/runs/34432378047):
4 JVM, 32 API 35 emulator and 3 release-contract tests, with zero emulator failures
or skips. Actual setup and synthetic live-IME screenshots were reviewed; see
[current images and release evidence](mobile.md#android--typing-and-local-dictation-preview).
Physical, landscape and assistive-technology acceptance remains open.

The alpha05 layout addresses feedback that the original keyboard felt like a grid
of application buttons. This is an independent implementation. We inspected the
[official FUTO keyboard visual](https://keyboard.futo.tech/assets/decoration-hero.webp)
for familiar keyboard proportions; no FUTO source, artwork, fonts or layouts were
imported into the app.

- Letter keys keep a consistent width. The home row is inset by half a key;
  Shift and Delete flank the third row.
- A wide spacebar and dedicated comma and period keys support ordinary writing.
  Enter displays the editor's action, such as Done or Send.
- Voice remains visible. Tools reveals Caps Lock, cursor arrows, settings and
  Android's keyboard switcher. Closing Tools restores the compact typing surface.
- Symbols use two pages with a visible page key. Returning to letters does not
  require a gesture or long press.
- Number row is independently optional. Terminal controls add Esc/Tab, one-shot
  Ctrl/Alt, navigation and a function layer with F1–F12, Insert and forward Delete.
  The function layer replaces letters rather than adding more height. Raw terminal
  fields accept ASCII key events only with this preference enabled; voice stays off.
- Neutral keycaps carry the letters; green marks the editor action and selected
  modifiers. Dark is the default, with light and larger-key preferences retained.
  Insets separate the visible keycaps without creating gaps in their touch areas.
- App content roots handle system bars and cutouts; the IME reserves navigation-bar
  space. Verify actual setup and keyboard captures after the inset regression gate,
  including the Fn layer, landscape and both navigation modes.

Native Android buttons retain spoken labels, focus and click actions. Keys fit
their labels to available width; larger mode increases row height and label size.
Ten columns still limit horizontal target size on narrow phones. This is not a
claim of full accessibility acceptance: TalkBack, Switch Access, large system
fonts, landscape, and physical typing comfort need user testing.

The typing surface adds no networking, text history, surrounding-text reads or
clipboard access. Password fields still disable dictation. The release IME window
remains protected against screenshots. CI captures only a synthetic debug test
window, temporarily restoring visibility within instrumentation and restoring its
secure flag immediately afterward.

Suggestions, autocorrect, multilingual layouts, emoji and swipe typing remain
separate [roadmap work](mobile-roadmap.md). A better-looking keyboard does not
make these features implemented.
