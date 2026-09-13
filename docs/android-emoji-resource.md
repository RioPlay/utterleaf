# Android emoji catalog resource

Utterleaf's Android emoji catalog is generated from official Unicode data and is
available locally at runtime. It contains data only: no upstream keyboard code,
artwork, font, network client, telemetry, or user history is included.

## Pinned sources

The development inputs live in `mobile/android/tools/unicode/`. Resource updates
must replace the recorded identity and receive a new data, license, and parser
review.

| Publisher and source | Version | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Unicode Consortium, [`emoji-test.txt`](https://www.unicode.org/Public/17.0.0/emoji/emoji-test.txt) | Emoji 17.0, 2025-08-04 | 669,326 | `1d8a944f88d7952f7ef7c5167fef3c67995bcae24543949710231b03a201acda` |
| Unicode Consortium CLDR, [`common/annotations/en.xml`](https://github.com/unicode-org/cldr/blob/acd6d88ae493633240e19a87a721076a8a75c310/common/annotations/en.xml) | CLDR 48 commit `acd6d88ae493633240e19a87a721076a8a75c310` | 294,945 | `8511aadd046fdba2f0ffe590266ced8bbf48175ad139b2675d85d7141057b235` |
| Unicode Consortium CLDR, [`common/annotationsDerived/en.xml`](https://github.com/unicode-org/cldr/blob/acd6d88ae493633240e19a87a721076a8a75c310/common/annotationsDerived/en.xml) | CLDR 48, same commit | 548,066 | `d76bd041c8c9e7b00b716aff8b7d9dbf509877010e191d5efd068be2553e066e` |
| Unicode Consortium, [Unicode License V3](https://www.unicode.org/license.txt) | Retrieved 2026-09-12 | 1,995 | `e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96` |

The CLDR revision was resolved from the official `release-48` tag. The CLDR
files carry `SPDX-License-Identifier: Unicode-3.0`. Unicode's
[terms of use](https://www.unicode.org/copyright.html) apply the Unicode License
V3 to the data. The exact license is retained as a development input and bundled
at `app/src/main/assets/unicode-license.txt`; its terms remain separate from the
Apache-2.0 license for Utterleaf code.

## Deterministic output

Run this command from the repository root to verify the checked-in result without
network access:

```powershell
python mobile/android/tools/emoji_catalog.py
```

Maintainers use `--write` only after intentionally updating the pinned source
identity. The generator verifies every input's exact size and SHA-256 before it
parses anything. It removes only the exact official CLDR DOCTYPE and rejects any
other DOCTYPE or entity declaration; Python's XML parser never resolves an
external DTD. It accepts only `fully-qualified` Emoji 17 records, excludes the
standalone Component group, requires all nine expected groups and their pinned
counts, and requires a CLDR English name and keyword set for every emitted entry.
Android Git attributes disable newline conversion for these pinned inputs and
generated catalog/notice so Windows and Unix checkouts retain the reviewed bytes.

The generated `app/src/main/res/raw/emoji_catalog.txt` has 3,944 entries and is
558,943 bytes with SHA-256
`05319ac5b761f60eac2441c62ca253eb30b77313d7b8a20949157ccfd4b01914`.
Its header identifies the format, source versions, count, and
`SPDX-License-Identifier: Unicode-3.0`. Records use six tab-separated fields:
exact sequence code points, category id, subgroup, family code points, English
name, and pipe-separated English keywords. Code points reconstruct the exact
fully-qualified sequence at runtime.

Tone families remove only U+1F3FB through U+1F3FF and U+FE0F from their grouping
key. They retain every exact upstream sequence, keep gender forms separate, and
select the first actual no-tone member as canonical when one exists. The pinned
catalog has 1,926 families, including 342 families with variants; the largest has
26 exact members.

## Runtime bounds

`EmojiCatalog` is a pure Kotlin parser with no Android context, network, font, or
storage dependency. It limits the resource to 1,000,000 characters, each line to
4,096 characters, the catalog and search result limit to 4,096 entries, each
sequence to 32 Unicode scalar values, each entry to 128 keywords, and each query
to 48 characters. It rejects invalid scalars, unknown categories, duplicate
sequences or keywords, inconsistent family keys, malformed records, and count
mismatches. Parsed public collections are immutable. The caller owns and closes
any `Reader` passed to the parser.

Device font support controls whether a catalog sequence can be displayed. The
catalog does not download fonts and does not claim that every host editor or
physical phone renders every Emoji 17 sequence.
