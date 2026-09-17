# What the public asks of privacy keyboards — September 2026 harvest

[Mobile roadmap](mobile-roadmap.md) · [Research report](mobile-keyboard-research.md) ·
[Product specification](android-keyboard-product-spec.md) · [Capability plan](android-keyboard-capabilities.md)

Review date: September 16, 2026. This pass extends the September 12
[community evidence](android-keyboard-product-spec.md#community-evidence-and-resulting-priorities)
with a systematic harvest: the top reaction-sorted open issues of the three
leading independent Android keyboards (HeliBoard, Unexpected Keyboard, FUTO —
55 issues), plus Hacker News discussion records. It is a purposive sample; no
tracker or forum measures how many people want a feature. Requests establish
tasks people want done; they do not verify defects or security claims. No
community messages were sent, and no code or assets were reviewed or imported.

## The ranked wants

| Want | Public evidence (reactions) | Utterleaf status after the daily redesign | Where it lands |
| --- | --- | --- | --- |
| Correction that works everywhere | FUTO [#1334](https://github.com/futo-org/android-keyboard/issues/1334) (42): spellchecker per language; HeliBoard [#2156](https://github.com/HeliBorg/HeliBoard/issues/2156) (9): autocorrect dies per field; [r/fossdroid, Aug 2026](https://www.reddit.com/r/fossdroid/comments/1w0rdaj/a_good_android_keyboard_i_wanna_share/): weak suggestions drive users away | Suggestions do not exist yet (deliberate); the R3 correction/vocabulary slice is the highest-value open work | R3 next slice |
| Gesture typing | HeliBoard [#2226](https://github.com/HeliBorg/HeliBoard/issues/2226) (70): NLnet-funded open gesture library; [#668](https://github.com/HeliBorg/HeliBoard/issues/668) (12) | Planned R5. Two licensing-friendly inputs now exist: the NLnet open library (drop-in, consented data gathering) and FUTO's released 1M-row [swipe dataset](https://huggingface.co/datasets/futo-org/swipe.futo.org) for evaluation | R5, after the [foundation decision](android-keyboard-foundation-decision.md) review |
| Word-level deletion units | HeliBoard [#1289](https://github.com/HeliBorg/HeliBoard/issues/1289) (34), [#535](https://github.com/HeliBorg/HeliBoard/issues/535) (13) | Partial: held delete repeats, drag-from-Backspace selects a bounded range. Missing: an explicit delete-by-word unit preference | R3/R5, bounded setting + tap alternative |
| Floating / tablet mode | HeliBoard [#326](https://github.com/HeliBorg/HeliBoard/issues/326) (35); Unexpected [#621](https://github.com/Julow/Unexpected-Keyboard/issues/621) (16), [#1031](https://github.com/Julow/Unexpected-Keyboard/issues/1031) (8), [#307](https://github.com/Julow/Unexpected-Keyboard/issues/307) (8) | Planned R5 after one-hand alignment; recurring Termux/X11 and tablet use cases | R5 |
| Settings backup/restore | Unexpected [#856](https://github.com/Julow/Unexpected-Keyboard/issues/856) (20), [#577](https://github.com/Julow/Unexpected-Keyboard/issues/577) (7) | Accepted idea ([ideas.md](ideas.md): local vocabulary + selective settings backup); the growing preference count raises its priority | M5, local-only export with explicit selection |
| CJK / Japanese / multilingual | HeliBoard [#786](https://github.com/HeliBorg/HeliBoard/issues/786) (18), [#639](https://github.com/HeliBorg/HeliBoard/issues/639) (20), [#452](https://github.com/HeliBorg/HeliBoard/issues/452) (12); FUTO [#1212](https://github.com/futo-org/android-keyboard/issues/1212) (39) | Planned R4/R6; open composition engines exist (MOZC, Rime, Anthy) and each needs its own provenance and native-speaker evidence | R4/R6 |
| Credential route to the password manager | FUTO [#325](https://github.com/futo-org/android-keyboard/issues/325) (42) | **Implemented in this pass**: an "Open password manager" toolbar key, gated to password fields only (see below) | Shipped |
| Add words to the dictionary while typing | HeliBoard [#1699](https://github.com/HeliBorg/HeliBoard/issues/1699) (13); FUTO [#311](https://github.com/futo-org/android-keyboard/issues/311) (17) | Planned R3: explicit, inspectable, deletable local vocabulary | R3 |
| Case toggle via suggestions | FUTO [#1693](https://github.com/futo-org/android-keyboard/issues/1693) (24), [#23](https://github.com/futo-org/android-keyboard/issues/23) (16) | Depends on suggestions; record as an acceptance case for the R4 suggestion strip | R4 |
| Streaming/continuous voice | FUTO [#130](https://github.com/futo-org/android-keyboard/issues/130) (28) | Partial: reviewed takes with the 120-second bound; continuous streaming is M4 work behind device measurements | M4 |
| Emoji search and pinned emoji | Unexpected [#173](https://github.com/Julow/Unexpected-Keyboard/issues/173) (27); FUTO [#324](https://github.com/futo-org/android-keyboard/issues/324) (15) | Shipped: local CLDR-48 search; pinning/recents needs off/clear controls first | R3 follow-up |
| Keypress character popup | Unexpected [#132](https://github.com/Julow/Unexpected-Keyboard/issues/132) (12) | Pressed-state feedback exists; an optional character popup is P5 feedback customization | P5 |
| Layout stability across updates | Unexpected [#955](https://github.com/Julow/Unexpected-Keyboard/issues/955) (7) | The one-time `optionsVersion` migration preserves explicit choices; upgrade-preservation acceptance remains a release gate | M6 acceptance |
| Toolbar/suggestion separation | HeliBoard [#695](https://github.com/HeliBorg/HeliBoard/issues/695) (14), [#963](https://github.com/HeliBorg/HeliBoard/issues/963) (13) | The single compact toolbar already follows the product rule; bounded toolbar customization is P5 | P5 |
| Show keyboard on demand (tile) | Unexpected [#1113](https://github.com/Julow/Unexpected-Keyboard/issues/1113) (8), [#496](https://github.com/Julow/Unexpected-Keyboard/issues/496) (7) | Deferred: Android limits deliberate keyboard invocation; no overlay-button workaround | Reassess with platform evidence |

## Privacy boundary decisions this harvest confirms

- GIF/ Tenor-style media insertion ([HeliBoard #363](https://github.com/HeliBorg/HeliBoard/issues/363), 25) requires a network service. That is outside the no-network boundary unless it becomes a reviewed, explicit, separately-permissioned data path — not currently planned.
- HeliBoard's NLnet gesture-data gathering ([#2226](https://github.com/HeliBorg/HeliBoard/issues/2226)) models the consent standard any future data collection must meet: opt-in modes, blocklists, review, and user-mediated submission. FUTO's released swipe dataset likewise needs a license and provenance review before any Utterleaf use.
- The Nov 2025 Hacker News thread ["Keyboards shouldn't connect to the internet"](https://news.ycombinator.com/item?id=46090679) (27 points) confirms the no-network property is the differentiator privacy-minded users name first; it stays the ship gate.
- Update-prompt behavior ([FUTO #400](https://github.com/futo-org/android-keyboard/issues/400), 15): Obtainium's model (user-initiated, outside the keyboard) already avoids browser launches while typing.

## The password-manager key — design decision

FUTO's top feature request (42 reactions) asks for a route to the user's
password manager from the keyboard, because autofill suggestions fail on some
hosts. Utterleaf's implementation is deliberately narrower:

- **Password fields only.** The key exists on exactly the restricted
  credential set — text password, visible password, web password, and number
  password variations. It never appears on ordinary text, email, URL or number
  fields, where a credential shortcut would invite wrong-field use. This set
  matches the field gate that already disables speech and drafts, and a JVM
  test pins the classification against the speech gate.
- **No data path.** The key launches the application configured as the system
  autofill service; the keyboard sends it nothing. If no autofill application
  is configured, the key does not exist at all — there is no default target,
  no picker to maintain, and no permission added.
- **Failure is visible.** If the launch fails, the keyboard reports
  "Key unavailable" rather than pretending success.
- **It never reads the field.** The shortcut is independent of field content;
  autocomplete, learning and speech stay disabled on these fields.

Verification: 1 JVM classification test, a direct-panel behavior test, and
live-IME assertions that the key follows the configured autofill application on
password fields and is absent on text and email fields.
