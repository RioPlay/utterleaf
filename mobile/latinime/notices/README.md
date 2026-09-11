# Utterleaf foundation notices

These documents identify source and dependencies used by the experimental LatinIME
foundation. They are source inputs for the packaged, local notice viewer in Preferences.
The shipping Android app is separate.

The original AOSP notices are copied without modification. Their historical
Lexiteria statement refers to upstream dictionaries that are NOT bundled here.
No FUTO or Hacker's Keyboard code/assets, external fonts, dictionary binaries or
speech models are added by this bundle.

`runtime-dependencies.json` records the resolved release graph, artifact/POM hashes
and declared licenses. Some graph entries are metadata rather than runtime code.
`provenance.json` records verbatim-copy and local NDK extraction or pinned-source evidence.
`catalog.json` identifies the reviewed document inputs; its recorded hashes describe
this source snapshot. Packaging must recompute hashes after refreshing the three
upstream documents from the indicated original paths.

Static runtime notices cover selected LLVM/compiler_rt/libc++/libc++abi sections,
the full libunwind license and relevant Android startup-source notices. Sources
are pinned by the toolchain manifest; exact CRT source-to-object reproducibility,
retained archive-member mapping and component-specific nested notices remain
review items. This bundle is packaging progress, not a declaration
of complete release compliance or permission to publish an unfinished replacement.

See `DEPENDENCY-INVENTORY.md` at the foundation project root for detailed scope,
asset provenance, selected source ranges and remaining checks.
