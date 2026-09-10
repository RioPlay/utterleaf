# Android typing surface

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
- Neutral keycaps carry the letters; green marks the editor action and selected
  modifiers. Dark is the default, with light and larger-key preferences retained.
  Insets separate the visible keycaps without creating gaps in their touch areas.

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
