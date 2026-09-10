# Working on Utterleaf

- Security first, privacy second, convenience third. Do not add ambient recording,
  passive typing collection, or unverified model loading as convenience options.
- Sane defaults, useful customization and repeatable behavior are product
  requirements. Keep explicit preferences local, group related controls, and
  provide a clear Reset to defaults. Reset preferences must not delete models or
  other user data. Verify persistence, cancellation and reset when changing settings.
- Use Aden CLI/MCP for scoped code navigation when available: symbol tree,
  bounded search, then symbol/caller inspection. Validate its heuristic results
  against source and tests. Pass this guidance and file ownership to subagents.
- Keep desktop and mobile dependencies, source, tests, roadmaps and releases
  separate as described in [development boundaries](docs/development-boundaries.md).
- Prefer useful, accessible controls over extra menus. Document unsupported
  editor/platform behavior and distinguish implemented features from verified
  device behavior. Do not claim emulator tests establish physical-phone usability.
- Follow the [development guide](docs/development.md),
  [mobile capability plan](docs/android-keyboard-capabilities.md) and applicable
  platform roadmap. Run checks appropriate to the changed behavior.
