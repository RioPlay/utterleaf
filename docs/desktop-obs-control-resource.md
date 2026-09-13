# OBS control dependency record

This records the desktop control component's resource review, not a live OBS
release or proof of native plugin compatibility. Android does not use this library.

The desktop dependency is pinned to `websockets==16.1.1`. Its published metadata
declares Python `>=3.10`, no runtime dependencies, and `BSD-3-Clause`. The newer
17.1 release requires Python 3.11 and would exclude Utterleaf's declared Python
3.10 support. See the [16.1.1 metadata](https://pypi.org/pypi/websockets/16.1.1/json)
and [17.1 metadata](https://pypi.org/pypi/websockets/17.1/json).

The development environment received only the `websockets-16.1.1-py3-none-any.whl`
wheel, 173,814 bytes, after SHA-256 verification:

```text
6abbd3e82c731c8e531714466acd5d87b5e88ac3243465337ba71d68e23ae7e3
```

Installation used the verified local wheel with `--no-index --no-deps
--no-cache-dir`. The wheel is Python source without a native extension. Normal
project installation on other platforms may select a platform wheel with the
project's optional speedups extension; its exact bytes/native build remain part
of that platform's package provenance, not this pure-wheel receipt.

The complete installed BSD license was read and the desktop notice collector's
copy function reproduced it byte for byte in temporary test output. Its SHA-256 is:

```text
3d6a0c050d8bec52fabad502e45fb25bd02bcadbd70dea34d447b6a0ff4e6da8
```

`packaging/collect_notices.py` includes `websockets` in the runtime notice
inventory. Preserve the copyright, conditions and disclaimer with distributed
code and binaries. This receipt does not audit every existing dependency or
replace release provenance, license collection and platform package checks.

The control adapter disables compression, proxies and library payload logging,
restricts addresses to literal loopback, and bounds messages, queues and network
operations. It uses the library's maintained RFC 6455 implementation rather than
implementing WebSocket framing in the application. See the
[threaded client API](https://websockets.readthedocs.io/en/16.1/reference/sync/client.html)
and [OBS implementation plan](plans/active/obs-audio-implementation.md).

The OBS challenge-response authenticates the client; it does not prove the local
server process's identity. The internal Windows connection additionally requires
the [native TCP peer identity check](plans/active/windows-obs-peer-identity.md)
before authentication. This uses Windows system APIs and adds no dependency.
The [audio pipe client](plans/active/windows-obs-audio-pipe.md) now separately
checks the retained process and completes a fixed session handshake. The original
server's DACL/client verification and actual OBS acceptance remain open.
OBS's own debug logs may contain
WebSocket JSON, so that channel must never carry pipe secrets, audio or transcripts.
